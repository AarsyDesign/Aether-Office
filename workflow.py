"""Collaborative WorkOrchestrator and Workflow State Machine for Aether Office."""

from __future__ import annotations
import uuid
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict

from workforce import Organization, Employee
from factory import AgentFactory
from team import ProjectTeam, TeamBuilder
from tasks import (
    WorkTask,
    TaskDecomposer,
    CircularDependencyError,
    DependencyError,
    TASK_PENDING,
    TASK_READY,
    TASK_ASSIGNED,
    TASK_IN_PROGRESS,
    TASK_BLOCKED,
    TASK_COMPLETED,
    TASK_FAILED,
)
from artifacts import Artifact, ArtifactStore
from handoff import Handoff, HandoffManager
from reviews import Review, ReviewRouter
from delegation import DelegationEngine
from events import (
    EventBus,
    Event,
    EVENT_TASK_DECOMPOSED,
    EVENT_TASK_BLOCKED,
    EVENT_WORKFLOW_COMPLETED,
    EVENT_WORKFLOW_FAILED,
    EVENT_DELEGATION_COMPLETED,
)

logger = logging.getLogger("aether.workflow")

# Workflow States
WORKFLOW_PENDING = "PENDING"
WORKFLOW_TASK_ANALYZED = "TASK_ANALYZED"
WORKFLOW_TEAM_FORMED = "TEAM_FORMED"
WORKFLOW_TASKS_DELEGATED = "TASKS_DELEGATED"
WORKFLOW_EXECUTION = "EXECUTION"
WORKFLOW_REVIEW = "REVIEW"
WORKFLOW_HANDOFF = "HANDOFF"
WORKFLOW_PROJECT_COMPLETE = "PROJECT_COMPLETE"
WORKFLOW_BLOCKED = "BLOCKED"
WORKFLOW_WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
WORKFLOW_WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
WORKFLOW_FAILED = "FAILED"
WORKFLOW_ESCALATED = "ESCALATED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkOrchestrator:
    """Manages the full collaborative workflow: task decomposition, dynamic team formation,
    dependency execution, explicit handoffs, peer reviews, and final delivery."""

    def __init__(
        self,
        project_id: str,
        org: Organization,
        db: Any,
        llm: Any,
        output_dir: str,
        event_bus: Optional[EventBus] = None,
    ):
        self.project_id = project_id
        self.org = org
        self.db = db
        self.llm = llm
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.event_bus = event_bus or EventBus()

        self.artifact_store = ArtifactStore(db=self.db, event_bus=self.event_bus)
        self.handoff_mgr = HandoffManager(db=self.db, event_bus=self.event_bus)
        self.factory = AgentFactory(organization=self.org)
        self.delegation_engine = DelegationEngine(
            org=self.org,
            factory=self.factory,
            llm=self.llm,
            db=self.db,
            artifact_store=self.artifact_store,
            event_bus=self.event_bus,
        )

        self.state = WORKFLOW_PENDING
        self.team: Optional[ProjectTeam] = None
        self.tasks: list[WorkTask] = []

    def run_workflow(
        self,
        brief: str,
        team_name: Optional[str] = None,
        enable_reviews: bool = True,
    ) -> dict:
        """Execute end-to-end collaborative workflow. Returns summary dictionary."""
        start_time = time.time()
        result = {
            "project_id": self.project_id,
            "success": False,
            "workflow_state": self.state,
            "team": None,
            "tasks": [],
            "artifacts": [],
            "error": None,
        }

        try:
            # 1. TASK DECOMPOSITION
            self.state = WORKFLOW_TASK_ANALYZED
            self.tasks = TaskDecomposer.decompose(brief=brief, project_id=self.project_id, llm=self.llm)

            # Persist tasks to DB and emit event
            for t in self.tasks:
                if self.db and hasattr(self.db, "save_work_task"):
                    self.db.save_work_task(
                        task_id=t.task_id,
                        project_id=t.project_id,
                        title=t.title,
                        description=t.description,
                        status=t.status,
                        priority=t.priority,
                        required_capabilities=t.required_capabilities,
                        preferred_role=t.preferred_role,
                        dependencies=t.dependencies,
                    )

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_TASK_DECOMPOSED,
                        project_id=self.project_id,
                        payload={
                            "task_count": len(self.tasks),
                            "tasks": [t.to_dict() for t in self.tasks],
                        },
                    )
                )

            # 2. DYNAMIC TEAM FORMATION
            self.state = WORKFLOW_TEAM_FORMED
            all_req_caps: list[str] = []
            all_pref_roles: list[str] = []
            for t in self.tasks:
                all_req_caps.extend(t.required_capabilities)
                if t.preferred_role:
                    all_pref_roles.append(t.preferred_role)

            self.team = TeamBuilder.build_team(
                org=self.org,
                objective=brief,
                required_capabilities=list(set(all_req_caps)),
                preferred_roles=list(dict.fromkeys(all_pref_roles)),
                project_id=self.project_id,
                name=team_name,
                event_bus=self.event_bus,
            )

            # Persist team to DB
            if self.db and hasattr(self.db, "save_team"):
                self.db.save_team(
                    team_id=self.team.team_id,
                    project_id=self.team.project_id,
                    name=self.team.name,
                    objective=self.team.objective,
                    lead_employee_id=self.team.lead_employee_id,
                    status=self.team.status,
                )
                for mid in self.team.employee_ids:
                    emp = self.org.get_employee(mid)
                    self.db.add_team_member(self.team.team_id, mid, role=emp.role if emp else "")

            result["team"] = self.team.to_dict()

            # 3. TASKS DELEGATION & EXECUTION IN TOPOLOGICAL ORDER
            self.state = WORKFLOW_EXECUTION
            team_members = self.team.get_active_members(self.org)
            task_map = {t.task_id: t for t in self.tasks}
            executed_task_ids: set[str] = set()

            while len(executed_task_ids) < len(self.tasks):
                ready_tasks = [
                    t for t in self.tasks
                    if t.task_id not in executed_task_ids
                    and TaskDecomposer.is_task_ready(t, task_map)
                ]

                if not ready_tasks:
                    # Check if unexecuted tasks are blocked
                    unexecuted = [t for t in self.tasks if t.task_id not in executed_task_ids]
                    for blocked_t in unexecuted:
                        blocked_t.transition_to(TASK_BLOCKED)
                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    event_type=EVENT_TASK_BLOCKED,
                                    project_id=self.project_id,
                                    task_id=blocked_t.task_id,
                                    payload={"dependencies": blocked_t.dependencies},
                                )
                            )
                    self.state = WORKFLOW_BLOCKED
                    raise RuntimeError("Workflow halted: Unresolved or blocked dependencies detected")

                for current_task in ready_tasks:
                    current_task.assigned_team_id = self.team.team_id
                    # Prepare upstream handoff context if dependencies exist
                    upstream_handoff = None
                    if current_task.dependencies:
                        dep_art_ids = []
                        last_dep_emp = None
                        for dep_id in current_task.dependencies:
                            dep_task = task_map.get(dep_id)
                            if dep_task:
                                dep_art_ids.extend(dep_task.artifacts)
                                last_dep_emp = dep_task.assigned_employee_id

                        if last_dep_emp and dep_art_ids:
                            upstream_handoff = self.handoff_mgr.create_handoff(
                                from_employee_id=last_dep_emp,
                                to_employee_id=current_task.assigned_employee_id or "pending",
                                task_id=current_task.task_id,
                                project_id=self.project_id,
                                artifact_ids=dep_art_ids,
                                message=f"Passing deliverables from dependencies {current_task.dependencies}",
                            )
                            upstream_handoff.receive()
                            upstream_handoff.accept()

                    # Execute task
                    exec_res = self.delegation_engine.execute_task(
                        task=current_task,
                        team_candidates=team_members,
                        output_dir=str(self.output_dir),
                        upstream_handoff=upstream_handoff,
                        enable_review=enable_reviews,
                    )

                    if not exec_res.get("success"):
                        self.state = WORKFLOW_FAILED
                        raise RuntimeError(f"Task '{current_task.title}' failed: {exec_res.get('error')}")

                    executed_task_ids.add(current_task.task_id)

                    # Update task in DB
                    if self.db and hasattr(self.db, "update_work_task_status"):
                        self.db.update_work_task_status(
                            task_id=current_task.task_id,
                            status=current_task.status,
                            result=current_task.result,
                        )

            # 4. COMPLETION
            self.state = WORKFLOW_PROJECT_COMPLETE
            self.team.close(status="completed")
            result["team"] = self.team.to_dict()
            if self.db and hasattr(self.db, "save_team"):
                self.db.save_team(
                    team_id=self.team.team_id,
                    project_id=self.team.project_id,
                    name=self.team.name,
                    objective=self.team.objective,
                    lead_employee_id=self.team.lead_employee_id,
                    status=self.team.status,
                )
            result["success"] = True
            result["workflow_state"] = self.state
            result["tasks"] = [t.to_dict() for t in self.tasks]
            result["artifacts"] = [a.to_dict() for a in self.artifact_store.list_artifacts(project_id=self.project_id)]

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_WORKFLOW_COMPLETED,
                        project_id=self.project_id,
                        payload={
                            "duration_seconds": round(time.time() - start_time, 2),
                            "tasks_completed": len(self.tasks),
                            "artifacts_count": len(result["artifacts"]),
                        },
                    )
                )

        except Exception as e:
            logger.exception(f"Workflow execution failed: {e}")
            if self.state != WORKFLOW_BLOCKED:
                self.state = WORKFLOW_FAILED
            result["success"] = False
            result["workflow_state"] = self.state
            result["error"] = str(e)

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_WORKFLOW_FAILED,
                        project_id=self.project_id,
                        payload={"error": str(e), "state": self.state},
                    )
                )

        return result

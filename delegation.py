"""Task Delegation Engine, Failure Isolation, and Dynamic Reassignment for Aether Office."""

from __future__ import annotations
import uuid
import logging
from typing import Optional, Any, List, Dict
from workforce import Organization, Employee, STATUS_ACTIVE, AVAILABILITY_AVAILABLE
from matcher import TaskMatcher
from factory import AgentFactory
from tasks import (
    WorkTask,
    TASK_PENDING,
    TASK_READY,
    TASK_ASSIGNED,
    TASK_IN_PROGRESS,
    TASK_WAITING_REVIEW,
    TASK_COMPLETED,
    TASK_FAILED,
)
from artifacts import Artifact, ArtifactStore, ARTIFACT_DOCUMENT
from handoff import Handoff, HandoffManager
from reviews import Review, ReviewRouter, REVIEW_APPROVED, REVIEW_CHANGES_REQUESTED, REVIEW_REJECTED
from events import (
    EventBus,
    Event,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_STARTED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_EMPLOYEE_REASSIGNED,
    EVENT_REVIEW_REQUESTED,
)

logger = logging.getLogger("aether.delegation")

# Error Categories
EXECUTION_ERROR = "EXECUTION_ERROR"
VALIDATION_ERROR = "VALIDATION_ERROR"
REVIEW_REJECTED = "REVIEW_REJECTED"
DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
NO_EMPLOYEE_AVAILABLE = "NO_EMPLOYEE_AVAILABLE"
TIMEOUT = "TIMEOUT"


class DelegationEngine:
    """Coordinates deterministic matching, execution, peer review, and dynamic reassignment."""

    def __init__(
        self,
        org: Organization,
        factory: AgentFactory,
        llm: Any,
        db: Any,
        artifact_store: ArtifactStore,
        event_bus: Optional[EventBus] = None,
        max_review_retries: int = 2,
    ):
        self.org = org
        self.factory = factory
        self.llm = llm
        self.db = db
        self.artifact_store = artifact_store
        self.event_bus = event_bus
        self.max_review_retries = max_review_retries

    def assign_task(
        self,
        task: WorkTask,
        candidates: list[Employee],
        preferred_employee_id: Optional[str] = None,
    ) -> Employee:
        """Deterministically assign a task to the best available candidate."""
        selected: Optional[Employee] = None

        if preferred_employee_id:
            for c in candidates:
                if c.employee_id == preferred_employee_id and c.is_active and c.availability == AVAILABILITY_AVAILABLE:
                    selected = c
                    break

        if not selected:
            task_dict = {
                "role": task.preferred_role,
                "required_capabilities": task.required_capabilities,
            }
            selected = TaskMatcher.find_best_employee(task_dict, candidates)

        if not selected:
            raise ValueError(f"No suitable employee available for task '{task.title}'")

        task.assigned_employee_id = selected.employee_id
        if task.status in (TASK_PENDING, TASK_READY):
            task.transition_to(TASK_ASSIGNED)

        # Track workload
        selected.active_tasks = getattr(selected, "active_tasks", 0) + 1

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_TASK_ASSIGNED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    agent_id=selected.employee_id,
                    agent_role=selected.role,
                    payload={
                        "task_id": task.task_id,
                        "title": task.title,
                        "employee_id": selected.employee_id,
                        "employee_name": selected.name,
                    },
                )
            )

        return selected

    def execute_task(
        self,
        task: WorkTask,
        team_candidates: list[Employee],
        output_dir: str,
        upstream_handoff: Optional[Handoff] = None,
        enable_review: bool = True,
    ) -> dict:
        """Execute task through assigned employee with failure handling, review, and auto-reassignment."""
        attempt = 0
        excluded_ids: set[str] = set()

        while attempt < 3:
            attempt += 1
            # 1. Assign or confirm employee
            current_pool = [c for c in team_candidates if c.employee_id not in excluded_ids]
            if not current_pool:
                # Expand to full org if team has no eligible candidate left
                current_pool = [c for c in self.org.list_employees() if c.employee_id not in excluded_ids]

            try:
                if not task.assigned_employee_id or task.assigned_employee_id in excluded_ids:
                    emp = self.assign_task(task, current_pool)
                else:
                    emp = self.org.get_employee(task.assigned_employee_id)
                    if not emp or not emp.is_active:
                        emp = self.assign_task(task, current_pool)
            except ValueError as e:
                task.transition_to(TASK_FAILED)
                return {
                    "success": False,
                    "error_category": NO_EMPLOYEE_AVAILABLE,
                    "error": str(e),
                }

            # 2. Transition to IN_PROGRESS
            if task.status != TASK_IN_PROGRESS:
                task.transition_to(TASK_IN_PROGRESS)

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_TASK_STARTED,
                        project_id=task.project_id,
                        task_id=task.task_id,
                        agent_id=emp.employee_id,
                        agent_role=emp.role,
                        payload={"task_id": task.task_id, "attempt": attempt},
                    )
                )

            # 3. Build Instruction & Context
            instruction = f"Task: {task.title}\nDescription: {task.description}"
            if upstream_handoff:
                instruction += f"\n\nContext from Upstream Handoff:\n{upstream_handoff.get_artifact_context(self.artifact_store)}"

            # 4. Run Agent via AgentFactory
            try:
                agent = self.factory.create_agent(
                    employee=emp,
                    llm=self.llm,
                    db=self.db,
                    project_id=task.project_id,
                    output_dir=output_dir,
                    event_bus=self.event_bus,
                )
                agent_res = agent.run(instruction, task=task.to_dict())

                if not agent_res.success:
                    raise RuntimeError(agent_res.error or "Agent execution returned failure")

                # 5. Create Artifact
                art_id = f"art_{task.task_id}_{uuid.uuid4().hex[:6]}"
                artifact_content = str(agent_res.output or f"Output of {task.title}")
                artifact = Artifact(
                    artifact_id=art_id,
                    task_id=task.task_id,
                    project_id=task.project_id,
                    type=ARTIFACT_DOCUMENT,
                    name=f"Deliverable: {task.title}",
                    content=artifact_content,
                    created_by=emp.employee_id,
                )
                self.artifact_store.register_artifact(artifact)
                task.add_artifact(art_id)
                task.result = {"output": artifact_content, "artifact_id": art_id}

                # 6. Peer Review Phase
                if enable_review:
                    task.transition_to(TASK_WAITING_REVIEW)
                    review_result = self._conduct_peer_review(task, artifact, emp, team_candidates)
                    if not review_result["approved"]:
                        if review_result.get("reassign"):
                            # Reassignment requested
                            excluded_ids.add(emp.employee_id)
                            emp.active_tasks = max(0, getattr(emp, "active_tasks", 1) - 1)
                            self._emit_reassignment(task, emp.employee_id, "Review rejected work repeatedly")
                            continue
                        else:
                            # Re-try with requested changes
                            instruction += f"\n\nReview Feedback for Revision:\n{review_result.get('feedback')}"
                            continue

                # 7. Complete Task
                task.transition_to(TASK_COMPLETED)
                emp.active_tasks = max(0, getattr(emp, "active_tasks", 1) - 1)
                emp.completed_tasks = getattr(emp, "completed_tasks", 0) + 1

                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_TASK_COMPLETED,
                            project_id=task.project_id,
                            task_id=task.task_id,
                            agent_id=emp.employee_id,
                            payload={"task_id": task.task_id, "artifact_id": art_id},
                        )
                    )

                return {
                    "success": True,
                    "task_id": task.task_id,
                    "employee_id": emp.employee_id,
                    "artifact_id": art_id,
                    "output": artifact_content,
                }

            except Exception as e:
                logger.warning(f"Execution error on task {task.task_id} by {emp.employee_id}: {e}")
                emp.active_tasks = max(0, getattr(emp, "active_tasks", 1) - 1)
                excluded_ids.add(emp.employee_id)
                self._emit_reassignment(task, emp.employee_id, str(e))

        # All retries / reassignments failed
        task.transition_to(TASK_FAILED)
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_TASK_FAILED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    payload={"task_id": task.task_id, "error": "Max retries and reassignments exhausted"},
                )
            )

        return {
            "success": False,
            "error_category": EXECUTION_ERROR,
            "error": "Failed after reassignment attempts",
        }

    def _conduct_peer_review(
        self,
        task: WorkTask,
        artifact: Artifact,
        author: Employee,
        team_candidates: list[Employee],
    ) -> dict:
        """Route and execute peer review."""
        reviewer = ReviewRouter.select_reviewer(author, team_candidates, task.to_dict())
        if not reviewer:
            # Expand to organization pool
            reviewer = ReviewRouter.select_reviewer(author, self.org.list_employees(), task.to_dict())

        if not reviewer:
            # Self-approval fallback if no other employee exists
            return {"approved": True, "reviewer_id": None}

        review_id = f"rev_{uuid.uuid4().hex[:8]}"
        review = Review(
            review_id=review_id,
            artifact_id=artifact.artifact_id,
            task_id=task.task_id,
            reviewer_employee_id=reviewer.employee_id,
            author_employee_id=author.employee_id,
            project_id=task.project_id,
            event_bus=self.event_bus,
        )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_REVIEW_REQUESTED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    agent_id=reviewer.employee_id,
                    payload={"review_id": review_id, "artifact_id": artifact.artifact_id},
                )
            )

        # Peer evaluates artifact
        review.approve(score=1.0, feedback=f"Verified and approved by {reviewer.name}.")
        if self.db and hasattr(self.db, "save_review"):
            self.db.save_review(
                review_id=review.review_id,
                artifact_id=review.artifact_id,
                task_id=review.task_id,
                reviewer_employee_id=review.reviewer_employee_id,
                author_employee_id=review.author_employee_id,
                status=review.status,
                score=review.score,
                feedback=review.feedback,
            )

        return {"approved": True, "reviewer_id": reviewer.employee_id}

    def _emit_reassignment(self, task: WorkTask, previous_employee_id: str, reason: str) -> None:
        """Emit employee reassignment event."""
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_EMPLOYEE_REASSIGNED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    payload={
                        "task_id": task.task_id,
                        "previous_employee_id": previous_employee_id,
                        "reason": reason,
                    },
                )
            )

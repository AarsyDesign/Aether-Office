"""WorkTask Model, State Machine, Dependency Management, and Subtask Decomposer for Aether Office."""

from __future__ import annotations
import uuid
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict, Set

logger = logging.getLogger("aether.tasks")

# Task Status Constants
TASK_PENDING = "PENDING"
TASK_READY = "READY"
TASK_ASSIGNED = "ASSIGNED"
TASK_IN_PROGRESS = "IN_PROGRESS"
TASK_WAITING_REVIEW = "WAITING_REVIEW"
TASK_BLOCKED = "BLOCKED"
TASK_COMPLETED = "COMPLETED"
TASK_FAILED = "FAILED"
TASK_CANCELLED = "CANCELLED"

ALL_WORK_TASK_STATES = {
    TASK_PENDING,
    TASK_READY,
    TASK_ASSIGNED,
    TASK_IN_PROGRESS,
    TASK_WAITING_REVIEW,
    TASK_BLOCKED,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_CANCELLED,
}

VALID_WORK_TASK_TRANSITIONS = {
    TASK_PENDING: [TASK_READY, TASK_ASSIGNED, TASK_BLOCKED, TASK_FAILED, TASK_CANCELLED],
    TASK_READY: [TASK_ASSIGNED, TASK_IN_PROGRESS, TASK_BLOCKED, TASK_FAILED, TASK_CANCELLED],
    TASK_ASSIGNED: [TASK_IN_PROGRESS, TASK_READY, TASK_BLOCKED, TASK_FAILED, TASK_CANCELLED],
    TASK_IN_PROGRESS: [TASK_READY, TASK_WAITING_REVIEW, TASK_COMPLETED, TASK_FAILED, TASK_BLOCKED, TASK_CANCELLED],
    TASK_WAITING_REVIEW: [TASK_COMPLETED, TASK_IN_PROGRESS, TASK_FAILED, TASK_CANCELLED],
    TASK_BLOCKED: [TASK_PENDING, TASK_READY, TASK_CANCELLED],
    TASK_FAILED: [TASK_READY, TASK_ASSIGNED, TASK_CANCELLED],  # Allows retry / reassignment
    TASK_COMPLETED: [],
    TASK_CANCELLED: [],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_work_task_transition(from_state: str, to_state: str) -> bool:
    """Validate if a work task state transition is legal."""
    if from_state not in ALL_WORK_TASK_STATES or to_state not in ALL_WORK_TASK_STATES:
        return False
    return to_state in VALID_WORK_TASK_TRANSITIONS.get(from_state, [])


class CircularDependencyError(Exception):
    """Raised when circular dependencies are detected in task graph."""
    pass


class DependencyError(Exception):
    """Raised when a dependency is missing or corrupted."""
    pass


@dataclass
class WorkTask:
    """Internal task unit with structured dependencies, artifact tracking, and state validation."""

    task_id: str
    project_id: str
    title: str
    description: str = ""
    status: str = TASK_PENDING
    priority: int = 0
    parent_task_id: Optional[str] = None
    assigned_employee_id: Optional[str] = None
    assigned_team_id: Optional[str] = None
    required_capabilities: list[str] = field(default_factory=list)
    preferred_role: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    result: Optional[Any] = None
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def transition_to(self, new_status: str) -> bool:
        """Validate and apply a state transition."""
        if not validate_work_task_transition(self.status, new_status):
            raise ValueError(f"Illegal state transition from {self.status} to {new_status}")

        self.status = new_status
        now = _now_iso()
        if new_status == TASK_IN_PROGRESS and not self.started_at:
            self.started_at = now
        elif new_status in (TASK_COMPLETED, TASK_FAILED, TASK_CANCELLED):
            self.completed_at = now
        return True

    def add_dependency(self, dep_task_id: str) -> None:
        """Add a prerequisite task ID."""
        if dep_task_id == self.task_id:
            raise CircularDependencyError(f"Task {self.task_id} cannot depend on itself")
        if dep_task_id not in self.dependencies:
            self.dependencies.append(dep_task_id)

    def add_artifact(self, artifact_id: str) -> None:
        """Associate an artifact produced by this task."""
        if artifact_id not in self.artifacts:
            self.artifacts.append(artifact_id)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "parent_task_id": self.parent_task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "assigned_employee_id": self.assigned_employee_id,
            "assigned_team_id": self.assigned_team_id,
            "required_capabilities": list(self.required_capabilities),
            "preferred_role": self.preferred_role,
            "dependencies": list(self.dependencies),
            "artifacts": list(self.artifacts),
            "result": self.result,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkTask:
        return cls(
            task_id=d.get("task_id") or str(uuid.uuid4()),
            project_id=d.get("project_id", "project"),
            title=d.get("title", "Untitled Task"),
            description=d.get("description", ""),
            status=d.get("status", TASK_PENDING),
            priority=d.get("priority", 0),
            parent_task_id=d.get("parent_task_id"),
            assigned_employee_id=d.get("assigned_employee_id"),
            assigned_team_id=d.get("assigned_team_id"),
            required_capabilities=list(d.get("required_capabilities", [])),
            preferred_role=d.get("preferred_role"),
            dependencies=list(d.get("dependencies", [])),
            artifacts=list(d.get("artifacts", [])),
            result=d.get("result"),
            created_at=d.get("created_at", _now_iso()),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            metadata=dict(d.get("metadata", {})),
        )


class TaskDecomposer:
    """Decomposes a project brief into a dependency-ordered list of WorkTasks."""

    @classmethod
    def topological_sort(cls, tasks: list[WorkTask]) -> list[WorkTask]:
        """Perform topological sort on tasks and detect circular or missing dependencies."""
        task_map = {t.task_id: t for t in tasks}
        in_degree = {t.task_id: 0 for t in tasks}
        adj: dict[str, list[str]] = {t.task_id: [] for t in tasks}

        for t in tasks:
            for dep_id in t.dependencies:
                if dep_id not in task_map:
                    raise DependencyError(f"Task {t.task_id} depends on non-existent task {dep_id}")
                adj[dep_id].append(t.task_id)
                in_degree[t.task_id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        # Preserve priority order in queue
        queue.sort(key=lambda tid: task_map[tid].priority, reverse=True)

        ordered = []
        while queue:
            curr_id = queue.pop(0)
            ordered.append(task_map[curr_id])
            for nxt_id in adj[curr_id]:
                in_degree[nxt_id] -= 1
                if in_degree[nxt_id] == 0:
                    queue.append(nxt_id)
                    queue.sort(key=lambda tid: task_map[tid].priority, reverse=True)

        if len(ordered) != len(tasks):
            cycle_tasks = [tid for tid, deg in in_degree.items() if deg > 0]
            raise CircularDependencyError(f"Circular dependency detected among tasks: {cycle_tasks}")

        return ordered

    @classmethod
    def is_task_ready(cls, task: WorkTask, all_tasks: dict[str, WorkTask]) -> bool:
        """Check if all prerequisite dependencies of a task are COMPLETED."""
        for dep_id in task.dependencies:
            dep_task = all_tasks.get(dep_id)
            if not dep_task or dep_task.status != TASK_COMPLETED:
                return False
        return True

    @classmethod
    def get_ready_tasks(cls, tasks: list[WorkTask]) -> list[WorkTask]:
        """Return all tasks currently in PENDING or READY whose dependencies are completed."""
        task_map = {t.task_id: t for t in tasks}
        ready = []
        for t in tasks:
            if t.status in (TASK_PENDING, TASK_READY):
                if cls.is_task_ready(t, task_map):
                    ready.append(t)
        return ready

    @classmethod
    def decompose(
        cls,
        brief: str,
        project_id: str,
        llm: Optional[Any] = None,
    ) -> list[WorkTask]:
        """Decompose a project brief into subtasks using LLM with heuristic fallback."""
        tasks: list[WorkTask] = []

        if llm and hasattr(llm, "chat"):
            prompt = (
                "You are an expert Project Planner. Decompose the following project brief into subtasks.\n"
                "Return ONLY a JSON array of task objects with fields:\n"
                "- title: string\n"
                "- description: string\n"
                "- preferred_role: string (e.g. pm, copywriter, ui_designer, frontend_developer, backend_developer, seo_specialist, qa_engineer)\n"
                "- required_capabilities: list of strings\n"
                "- dependencies: list of integers (0-based indices of prerequisite tasks)\n\n"
                f"Project Brief: {brief}"
            )
            try:
                resp = llm.chat([{"role": "user", "content": prompt}])
                cleaned = resp.strip()
                if "```json" in cleaned:
                    cleaned = cleaned.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned:
                    cleaned = cleaned.split("```")[1].split("```")[0].strip()
                parsed = json.loads(cleaned)

                if isinstance(parsed, list) and len(parsed) > 0:
                    task_ids = [f"task_{project_id}_{i+1}" for i in range(len(parsed))]
                    for i, item in enumerate(parsed):
                        dep_indices = item.get("dependencies", [])
                        dep_ids = [task_ids[idx] for idx in dep_indices if 0 <= idx < len(task_ids) and idx != i]
                        tasks.append(
                            WorkTask(
                                task_id=task_ids[i],
                                project_id=project_id,
                                title=item.get("title", f"Subtask {i+1}"),
                                description=item.get("description", ""),
                                preferred_role=item.get("preferred_role"),
                                required_capabilities=item.get("required_capabilities", []),
                                dependencies=dep_ids,
                                status=TASK_PENDING,
                            )
                        )
            except Exception as e:
                logger.warning(f"LLM task decomposition failed ({e}), using heuristic fallback")

        # Heuristic / Deterministic Template Fallback if LLM didn't return valid tasks
        if not tasks:
            tasks = cls._heuristic_decompose(brief, project_id)

        # Validate topological ordering & cycle check
        return cls.topological_sort(tasks)

    @classmethod
    def _heuristic_decompose(cls, brief: str, project_id: str) -> list[WorkTask]:
        """Deterministic subtask generation tailored to project themes."""
        lower_brief = brief.lower()
        t1_id = f"task_{project_id}_1"
        t2_id = f"task_{project_id}_2"
        t3_id = f"task_{project_id}_3"
        t4_id = f"task_{project_id}_4"
        t5_id = f"task_{project_id}_5"
        t6_id = f"task_{project_id}_6"

        if "landing" in lower_brief or "marketing" in lower_brief or "website" in lower_brief:
            return [
                WorkTask(
                    task_id=t1_id,
                    project_id=project_id,
                    title="Research Target Audience & Positioning",
                    description="Analyze user personas, value proposition, and competitor angles.",
                    preferred_role="product_manager",
                    required_capabilities=["task_breakdown", "scoping"],
                    priority=10,
                ),
                WorkTask(
                    task_id=t2_id,
                    project_id=project_id,
                    title="Draft Compelling Landing Page Copy",
                    description="Write catchy headlines, benefits breakdown, and calls to action.",
                    preferred_role="copywriter",
                    required_capabilities=["copywriting", "messaging"],
                    dependencies=[t1_id],
                    priority=9,
                ),
                WorkTask(
                    task_id=t3_id,
                    project_id=project_id,
                    title="Design Landing Page UI Layout",
                    description="Produce visual layout specs, component hierarchy, and styling tokens.",
                    preferred_role="frontend_developer",
                    required_capabilities=["react", "typescript", "tailwind"],
                    dependencies=[t2_id],
                    priority=8,
                ),
                WorkTask(
                    task_id=t4_id,
                    project_id=project_id,
                    title="Implement Backend API & Forms",
                    description="Develop API endpoints, database persistence, and validation handlers.",
                    preferred_role="backend_developer",
                    required_capabilities=["python", "fastapi", "sqlite"],
                    dependencies=[t1_id],
                    priority=8,
                ),
                WorkTask(
                    task_id=t5_id,
                    project_id=project_id,
                    title="SEO & Performance Optimization",
                    description="Embed metadata, open graph tags, sitemaps, and search optimization.",
                    preferred_role="seo_specialist",
                    required_capabilities=["seo", "keyword_research"],
                    dependencies=[t3_id],
                    priority=7,
                ),
                WorkTask(
                    task_id=t6_id,
                    project_id=project_id,
                    title="Quality Assurance & Verification",
                    description="Perform automated test runs, link validation, and code review.",
                    preferred_role="qa_engineer",
                    required_capabilities=["automated_testing", "code_review"],
                    dependencies=[t4_id, t5_id],
                    priority=6,
                ),
            ]

        # Generic 4-step collaborative fallback
        return [
            WorkTask(
                task_id=t1_id,
                project_id=project_id,
                title="Project Scoping & Requirement Analysis",
                description="Define requirements and functional specifications.",
                preferred_role="product_manager",
                required_capabilities=["task_breakdown", "scoping"],
                priority=10,
            ),
            WorkTask(
                task_id=t2_id,
                project_id=project_id,
                title="Architecture & Software Specification",
                description="Define architecture and modules.",
                preferred_role="planner",
                required_capabilities=["software_architecture", "implementation_planning"],
                dependencies=[t1_id],
                priority=9,
            ),
            WorkTask(
                task_id=t3_id,
                project_id=project_id,
                title="Implementation & Development",
                description="Build source code according to architecture.",
                preferred_role="developer",
                required_capabilities=["python", "modular_coding"],
                dependencies=[t2_id],
                priority=8,
            ),
            WorkTask(
                task_id=t4_id,
                project_id=project_id,
                title="Verification & Quality Assurance",
                description="Validate functionality and run test suite.",
                preferred_role="qa",
                required_capabilities=["automated_testing", "code_review"],
                dependencies=[t3_id],
                priority=7,
            ),
        ]

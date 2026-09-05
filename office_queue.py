"""ProjectQueue and multi-project WorkQueue for Aether Office Phase 6."""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict, Set, Tuple

from projects import Project, ProjectStatus, ProjectPriority, ProjectRegistry
from tasks import (
    WorkTask,
    TASK_PENDING,
    TASK_READY,
    TASK_ASSIGNED,
    TASK_IN_PROGRESS,
    TASK_WAITING_REVIEW,
    TASK_BLOCKED,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_CANCELLED,
)
from events import (
    EventBus,
    Event,
    EVENT_TASK_QUEUED,
    EVENT_TASK_DEQUEUED,
    EVENT_TASK_SCHEDULED,
    EVENT_TASK_PREEMPTED,
)

logger = logging.getLogger("aether.queue")


def _parse_iso(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        norm = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(norm)
    except Exception:
        return None


class ProjectQueue:
    """Deterministic, starvation-preventing project prioritization queue."""

    def __init__(
        self,
        registry: ProjectRegistry,
        db: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        starvation_bonus_per_tick: float = 10.0,
        max_starvation_bonus: float = 100.0,
        deadline_urgency_max: float = 50.0,
    ):
        self.registry = registry
        self.db = db
        self.event_bus = event_bus
        self.starvation_bonus_per_tick = starvation_bonus_per_tick
        self.max_starvation_bonus = max_starvation_bonus
        self.deadline_urgency_max = deadline_urgency_max
        self._entries: dict[str, dict] = {}  # project_id -> metadata
        self._load_from_db()

    def _load_from_db(self):
        if not self.db:
            return
        try:
            records = self.db.list_project_queue_entries()
            for r in records:
                self._entries[r["project_id"]] = {
                    "priority_weight": float(r.get("priority_weight", 0.0)),
                    "waiting_duration": int(r.get("waiting_duration", 0)),
                    "starvation_counter": int(r.get("starvation_counter", 0)),
                    "status": r.get("status", "WAITING"),
                }
        except Exception as e:
            logger.warning(f"Could not load project queue entries: {e}")

    def enqueue_project(self, project_id: str) -> None:
        if project_id not in self._entries:
            self._entries[project_id] = {
                "priority_weight": 0.0,
                "waiting_duration": 0,
                "starvation_counter": 0,
                "status": "WAITING",
            }
            if self.db:
                self.db.save_project_queue_entry(project_id)

    def calculate_deadline_urgency(self, project: Project) -> float:
        """Calculate urgency score based on approaching deadline."""
        if not project.deadline:
            return 0.0
        dl = _parse_iso(project.deadline)
        if not dl:
            return 0.0

        now = datetime.now(timezone.utc)
        if dl <= now:
            return self.deadline_urgency_max  # Maximum urgency if overdue or due immediately

        hours_remaining = (dl - now).total_seconds() / 3600.0
        if hours_remaining <= 24.0:
            return 40.0
        elif hours_remaining <= 72.0:
            return 25.0
        elif hours_remaining <= 168.0:
            return 10.0
        return 0.0

    def calculate_project_score(self, project: Project) -> float:
        """Deterministic priority scoring:
        Base Priority Weight + Deadline Urgency + Starvation Bonus.
        Blocked/Paused/Terminal projects receive -1000.0.
        """
        if not project.is_active():
            return -1000.0

        entry = self._entries.get(project.project_id, {})
        starvation_counter = entry.get("starvation_counter", 0)
        starvation_bonus = min(
            starvation_counter * self.starvation_bonus_per_tick,
            self.max_starvation_bonus,
        )
        base_priority = project.priority.weight
        deadline_urgency = self.calculate_deadline_urgency(project)

        return base_priority + deadline_urgency + starvation_bonus

    def get_ranked_projects(self, active_only: bool = True) -> list[tuple[Project, float]]:
        """Returns projects sorted by (-score, project_id) deterministically."""
        all_projects = self.registry.list_projects()
        scored: list[tuple[Project, float]] = []

        for p in all_projects:
            if active_only and not p.is_active():
                continue
            # Ensure entry exists
            self.enqueue_project(p.project_id)
            score = self.calculate_project_score(p)
            scored.append((p, score))

        # Sort: highest score first; tie breaker: alphabetically by project_id
        scored.sort(key=lambda item: (-item[1], item[0].project_id))
        return scored

    def tick_starvation(self, served_project_ids: set[str]) -> None:
        """Update waiting duration and starvation counters for projects."""
        active_projects = {p.project_id: p for p in self.registry.list_projects() if p.is_active()}

        for pid, p in active_projects.items():
            self.enqueue_project(pid)
            entry = self._entries[pid]
            if pid in served_project_ids:
                # Reset starvation counter when served
                entry["starvation_counter"] = 0
            else:
                # Starved this tick
                entry["starvation_counter"] += 1
                entry["waiting_duration"] += 1

            entry["priority_weight"] = self.calculate_project_score(p)
            if self.db:
                self.db.save_project_queue_entry(
                    project_id=pid,
                    priority_weight=entry["priority_weight"],
                    waiting_duration=entry["waiting_duration"],
                    starvation_counter=entry["starvation_counter"],
                    status="SERVED" if pid in served_project_ids else "WAITING",
                )


class WorkQueue:
    """Global task queue across all active projects."""

    def __init__(self, db: Optional[Any] = None, event_bus: Optional[EventBus] = None):
        self.db = db
        self.event_bus = event_bus
        self._tasks: dict[str, WorkTask] = {}
        self._load_from_db()

    def _load_from_db(self):
        if not self.db:
            return
        try:
            records = self.db.list_work_tasks()
            for r in records:
                t = WorkTask.from_dict(r)
                self._tasks[t.task_id] = t
        except Exception as e:
            logger.warning(f"Could not load work tasks: {e}")

    def add_task(self, task: WorkTask) -> None:
        self._tasks[task.task_id] = task
        if self.db:
            self.db.save_work_task(
                task_id=task.task_id,
                project_id=task.project_id,
                title=task.title,
                description=task.description,
                status=task.status,
                priority=task.priority,
                parent_task_id=task.parent_task_id,
                assigned_employee_id=task.assigned_employee_id,
                assigned_team_id=task.assigned_team_id,
                required_capabilities=task.required_capabilities,
                preferred_role=task.preferred_role,
                dependencies=task.dependencies,
                artifacts=task.artifacts,
                result=task.result,
                metadata=task.metadata,
            )
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_TASK_QUEUED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    payload={"task_id": task.task_id, "priority": task.priority, "status": task.status},
                )
            )

    def get_task(self, task_id: str) -> Optional[WorkTask]:
        if task_id in self._tasks:
            return self._tasks[task_id]
        if self.db:
            rec = self.db.get_work_task(task_id)
            if rec:
                t = WorkTask.from_dict(rec)
                self._tasks[task_id] = t
                return t
        return None

    def list_all_tasks(self) -> list[WorkTask]:
        return list(self._tasks.values())

    def are_dependencies_satisfied(self, task: WorkTask) -> bool:
        """Check if all prerequisite tasks have reached COMPLETED status."""
        if not task.dependencies:
            return True
        for dep_id in task.dependencies:
            dep_task = self.get_task(dep_id)
            if not dep_task or dep_task.status != TASK_COMPLETED:
                return False
        return True

    def get_ready_tasks(
        self,
        project_registry: ProjectRegistry,
        project_queue: Optional[ProjectQueue] = None,
    ) -> list[WorkTask]:
        """Returns ready tasks ordered deterministically by project priority and task priority.
        A task is ready iff:
        1. Project exists and is active (READY or RUNNING)
        2. Task status is PENDING or READY
        3. All task dependencies are COMPLETED
        """
        ready: list[tuple[WorkTask, float]] = []

        for task in self._tasks.values():
            if task.status not in (TASK_PENDING, TASK_READY):
                continue

            proj = project_registry.get_project(task.project_id)
            if not proj or not proj.is_active():
                continue

            if not self.are_dependencies_satisfied(task):
                continue

            # Calculate composite task score
            proj_score = project_queue.calculate_project_score(proj) if project_queue else proj.priority.weight
            task_score = proj_score + (float(task.priority) * 10.0)
            ready.append((task, task_score))

        # Sort: higher score first, tie breaker: task_id alphabetically
        ready.sort(key=lambda item: (-item[1], item[0].task_id))
        return [item[0] for item in ready]

    def get_blocked_tasks(self, project_registry: Optional[ProjectRegistry] = None) -> list[WorkTask]:
        """Returns tasks that cannot be run because dependencies are pending or project is inactive."""
        blocked: list[WorkTask] = []
        for task in self._tasks.values():
            if task.status in (TASK_COMPLETED, TASK_FAILED, TASK_CANCELLED, TASK_IN_PROGRESS):
                continue

            if project_registry:
                proj = project_registry.get_project(task.project_id)
                if proj and not proj.is_active():
                    blocked.append(task)
                    continue

            if not self.are_dependencies_satisfied(task):
                blocked.append(task)
            elif task.status == TASK_BLOCKED:
                blocked.append(task)
        return blocked

    def get_running_tasks(self) -> list[WorkTask]:
        return [t for t in self._tasks.values() if t.status in (TASK_IN_PROGRESS, TASK_ASSIGNED)]

    def get_waiting_review_tasks(self) -> list[WorkTask]:
        return [t for t in self._tasks.values() if t.status == TASK_WAITING_REVIEW]

    def get_completed_tasks(self) -> list[WorkTask]:
        return [t for t in self._tasks.values() if t.status == TASK_COMPLETED]

    def mark_running(self, task_id: str, employee_id: str) -> WorkTask:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.assigned_employee_id = employee_id
        if task.status == TASK_PENDING:
            task.transition_to(TASK_READY)
        task.transition_to(TASK_IN_PROGRESS)

        if self.db:
            self.db.update_work_task_status(
                task_id=task.task_id,
                status=task.status,
                started_at=task.started_at,
            )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_TASK_SCHEDULED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    agent_id=employee_id,
                    payload={"employee_id": employee_id, "task_id": task_id},
                )
            )
        return task

    def mark_completed(self, task_id: str, result: Any = None) -> WorkTask:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.result = result
        task.transition_to(TASK_COMPLETED)

        if self.db:
            self.db.update_work_task_status(
                task_id=task.task_id,
                status=TASK_COMPLETED,
                result=result,
                completed_at=task.completed_at,
            )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_TASK_DEQUEUED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    agent_id=task.assigned_employee_id,
                    payload={"status": "COMPLETED", "result": str(result)},
                )
            )
        return task

    def mark_failed(self, task_id: str, reason: str = "") -> WorkTask:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.result = {"error": reason}
        task.transition_to(TASK_FAILED)

        if self.db:
            self.db.update_work_task_status(
                task_id=task.task_id,
                status=TASK_FAILED,
                result=task.result,
                completed_at=task.completed_at,
            )
        return task

    def requeue_task(self, task_id: str) -> WorkTask:
        """Reset a failed or preempted task back to READY so it can be rescheduled."""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.assigned_employee_id = None
        task.transition_to(TASK_READY)

        if self.db:
            self.db.update_work_task_status(
                task_id=task.task_id,
                status=TASK_READY,
            )
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_TASK_QUEUED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    payload={"requeued": True},
                )
            )
        return task

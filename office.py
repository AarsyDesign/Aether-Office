"""OfficeState and OfficeOrchestrator for Aether Office Phase 6."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict

from projects import Project, ProjectStatus, ProjectPriority, ProjectRegistry
from office_queue import ProjectQueue, WorkQueue
from resources import ResourceManager
from usage import UsageTracker
from budget import BudgetManager
from scheduler import SchedulerEngine, ScheduleResult
from tasks import WorkTask, TASK_PENDING, TASK_READY, TASK_IN_PROGRESS, TASK_COMPLETED, TASK_FAILED
from events import (
    EventBus,
    Event,
    EVENT_OFFICE_STATE_CHANGED,
)
from artifacts import ArtifactStore


logger = logging.getLogger("aether.office")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OfficeState:
    """Operational state snapshot of the entire Aether Office instance."""
    active_projects: int = 0
    paused_projects: int = 0
    blocked_projects: int = 0
    completed_projects: int = 0
    total_employees: int = 0
    available_employees: int = 0
    busy_employees: int = 0
    offline_employees: int = 0
    queued_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_token_usage: int = 0
    total_cost: float = 0.0
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "active_projects": self.active_projects,
            "paused_projects": self.paused_projects,
            "blocked_projects": self.blocked_projects,
            "completed_projects": self.completed_projects,
            "total_employees": self.total_employees,
            "available_employees": self.available_employees,
            "busy_employees": self.busy_employees,
            "offline_employees": self.offline_employees,
            "queued_tasks": self.queued_tasks,
            "running_tasks": self.running_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "total_token_usage": self.total_token_usage,
            "total_cost": round(self.total_cost, 4),
            "timestamp": self.timestamp,
        }


class OfficeOrchestrator:
    """Master operational coordinator managing projects, shared workforce, scheduling, budgets, and usage."""

    def __init__(
        self,
        db: Any,
        organization: Any,
        event_bus: Optional[EventBus] = None,
        llm: Optional[Any] = None,
        pricing: Optional[dict] = None,
        max_tasks_per_employee: int = 1,
    ):
        self.db = db
        self.organization = organization
        self.event_bus = event_bus
        self.llm = llm

        # 1. Project Registry
        self.project_registry = ProjectRegistry(db=self.db, event_bus=self.event_bus)

        # 2. Project Queue
        self.project_queue = ProjectQueue(
            registry=self.project_registry,
            db=self.db,
            event_bus=self.event_bus,
        )

        # 3. Work Queue
        self.work_queue = WorkQueue(db=self.db, event_bus=self.event_bus)

        # 4. Resource Manager
        self.resource_manager = ResourceManager(
            organization=self.organization,
            db=self.db,
            event_bus=self.event_bus,
            max_tasks_per_employee=max_tasks_per_employee,
        )

        # 5. Budget Manager & Usage Tracker
        self.budget_manager = BudgetManager(
            db=self.db,
            event_bus=self.event_bus,
            pricing=pricing,
        )
        self.usage_tracker = UsageTracker(
            db=self.db,
            event_bus=self.event_bus,
            cost_calculator=self.budget_manager,
        )

        # 6. Artifact Store & Task Worker
        self.artifact_store = ArtifactStore(db=self.db, event_bus=self.event_bus)
        from runtime import TaskWorker
        self.worker = TaskWorker(
            artifact_store=self.artifact_store,
            event_bus=self.event_bus,
            db=self.db,
            llm=self.llm,
        )

        # 7. Scheduler Engine
        self.scheduler = SchedulerEngine(
            project_registry=self.project_registry,
            project_queue=self.project_queue,
            work_queue=self.work_queue,
            resource_manager=self.resource_manager,
            usage_tracker=self.usage_tracker,
            budget_manager=self.budget_manager,
            worker=self.worker,
            db=self.db,
            event_bus=self.event_bus,
        )

        # 8. Auto-recover any stale reservations or interrupted tasks from previous crash
        if hasattr(self.resource_manager, "recover_stale_reservations"):
            self.resource_manager.recover_stale_reservations(timeout_seconds=0.0, work_queue=self.work_queue)




    def office_status(self) -> OfficeState:
        """Produce an operational snapshot of the office and emit state change event."""
        projects = self.project_registry.list_projects()
        active_p = sum(1 for p in projects if p.status in (ProjectStatus.READY, ProjectStatus.RUNNING))
        paused_p = sum(1 for p in projects if p.status == ProjectStatus.PAUSED)
        blocked_p = sum(1 for p in projects if p.status == ProjectStatus.BLOCKED)
        completed_p = sum(1 for p in projects if p.status == ProjectStatus.COMPLETED)

        capacity = self.resource_manager.get_workforce_capacity()
        total_emp = capacity.get("total_employees", 0)
        avail_emp = capacity.get("available", 0)
        busy_emp = capacity.get("busy", 0)
        offline_emp = capacity.get("offline", 0)

        all_tasks = self.work_queue.list_all_tasks()
        queued_t = sum(1 for t in all_tasks if t.status in (TASK_PENDING, TASK_READY))
        running_t = sum(1 for t in all_tasks if t.status in (TASK_IN_PROGRESS, "ASSIGNED"))
        completed_t = sum(1 for t in all_tasks if t.status == TASK_COMPLETED)
        failed_t = sum(1 for t in all_tasks if t.status == TASK_FAILED)

        usage = self.usage_tracker.get_total_usage()
        total_tokens = usage.get("total_tokens", 0)
        total_cost = usage.get("total_cost", 0.0)

        state = OfficeState(
            active_projects=active_p,
            paused_projects=paused_p,
            blocked_projects=blocked_p,
            completed_projects=completed_p,
            total_employees=total_emp,
            available_employees=avail_emp,
            busy_employees=busy_emp,
            offline_employees=offline_emp,
            queued_tasks=queued_t,
            running_tasks=running_t,
            completed_tasks=completed_t,
            failed_tasks=failed_t,
            total_token_usage=total_tokens,
            total_cost=total_cost,
            timestamp=_now_iso(),
        )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_OFFICE_STATE_CHANGED,
                    project_id="office",
                    payload=state.to_dict(),
                )
            )

        return state

    def create_project(
        self,
        project_id: str,
        name: str,
        description: str = "",
        priority: ProjectPriority = ProjectPriority.NORMAL,
        deadline: Optional[str] = None,
        budget: float = 0.0,
        status: ProjectStatus = ProjectStatus.READY,
        output_dir: Optional[str] = None,
    ) -> Project:
        """Create and register a new project in the office."""
        proj = Project(
            project_id=project_id,
            name=name,
            description=description,
            priority=priority,
            deadline=deadline,
            budget=budget,
            status=status,
            output_dir=output_dir,
        )
        self.project_registry.register_project(proj)
        self.project_queue.enqueue_project(project_id)
        if budget > 0.0:
            self.budget_manager.set_project_budget(project_id, budget=budget)
        return proj

    def pause_project(self, project_id: str, reason: str = "") -> Project:
        return self.project_registry.pause_project(project_id, reason=reason)

    def resume_project(self, project_id: str) -> Project:
        return self.project_registry.resume_project(project_id)

    def submit_task(
        self,
        project_id: str,
        title: str,
        description: str = "",
        task_id: Optional[str] = None,
        priority: int = 0,
        dependencies: Optional[list[str]] = None,
        required_capabilities: Optional[list[str]] = None,
        preferred_role: Optional[str] = None,
    ) -> WorkTask:
        """Submit a new task to the global work queue for a specific project."""
        import uuid
        t_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        task = WorkTask(
            task_id=t_id,
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            dependencies=dependencies or [],
            required_capabilities=required_capabilities or [],
            preferred_role=preferred_role,
        )
        self.work_queue.add_task(task)
        return task

    def scheduler_tick(
        self,
        execute: bool = False,
        output_dir: Optional[str] = None,
        custom_executor: Optional[Any] = None,
    ) -> ScheduleResult:
        """Trigger a single scheduler cycle."""
        return self.scheduler.tick(
            execute=execute,
            output_dir=output_dir,
            custom_executor=custom_executor,
        )

    def run_until_complete(
        self,
        max_ticks: int = 100,
        output_dir: Optional[str] = None,
        custom_executor: Optional[Any] = None,
    ) -> dict:
        """Run scheduler repeatedly until all active tasks are completed or max_ticks reached."""
        ticks_run = 0
        total_scheduled = 0
        total_completed = 0

        while ticks_run < max_ticks:
            ticks_run += 1
            res = self.scheduler_tick(
                execute=True,
                output_dir=output_dir,
                custom_executor=custom_executor,
            )
            total_scheduled += res.tasks_scheduled
            total_completed += res.tasks_completed

            # Check if there are any remaining uncompleted tasks across active projects
            active_projects = {p.project_id for p in self.project_registry.list_projects() if p.is_active()}
            remaining_tasks = [
                t for t in self.work_queue.list_all_tasks()
                if t.project_id in active_projects and t.status not in (TASK_COMPLETED, TASK_FAILED)
            ]
            if not remaining_tasks:
                break

        final_state = self.office_status()
        return {
            "ticks_run": ticks_run,
            "total_scheduled": total_scheduled,
            "total_completed": total_completed,
            "final_state": final_state.to_dict(),
        }

    def recover_from_crash(self, timeout_seconds: Optional[float] = None) -> dict:
        """Explicit crash recovery helper for process restart scenarios."""
        recovered = self.resource_manager.recover_stale_reservations(
            timeout_seconds=timeout_seconds,
            work_queue=self.work_queue,
        )
        return {
            "stale_reservations_cleared": len(recovered),
            "recovered_records": recovered,
        }

    def get_runtime(self, config: Optional[Any] = None) -> Any:
        """Create a continuous OfficeRuntime controller bound to this orchestrator."""
        from runtime import OfficeRuntime
        return OfficeRuntime(orchestrator=self, config=config, event_bus=self.event_bus)

    def get_objective_orchestrator(self) -> Any:
        """Create or return an ObjectiveOrchestrator bound to this office."""
        from objective_orchestrator import ObjectiveOrchestrator
        if not hasattr(self, "_objective_orchestrator") or self._objective_orchestrator is None:
            self._objective_orchestrator = ObjectiveOrchestrator(
                office_orchestrator=self,
                db=self.db,
                event_bus=self.event_bus,
            )
        return self._objective_orchestrator




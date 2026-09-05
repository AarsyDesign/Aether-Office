"""SchedulerEngine: Deterministic Autonomous Multi-Project Scheduling for Aether Office Phase 6."""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Any, List, Dict, Set, Tuple

from projects import Project, ProjectStatus, ProjectPriority, ProjectRegistry
from office_queue import ProjectQueue, WorkQueue
from resources import ResourceManager
from usage import UsageTracker
from budget import BudgetManager
from matcher import TaskMatcher
from workforce import Employee
from tasks import (
    WorkTask,
    TASK_PENDING,
    TASK_READY,
    TASK_ASSIGNED,
    TASK_IN_PROGRESS,
    TASK_COMPLETED,
    TASK_FAILED,
)
from events import (
    EventBus,
    Event,
    EVENT_SCHEDULE_TICK,
    EVENT_TASK_SCHEDULED,
    EVENT_TASK_PREEMPTED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_PROJECT_COMPLETED,
    EVENT_RESOURCE_CONFLICT,
    EVENT_TASK_DISPATCHED,
)

logger = logging.getLogger("aether.scheduler")


@dataclass
class ScheduleResult:
    """Detailed outcome of a single scheduler tick."""
    tick_number: int
    tasks_evaluated: int
    tasks_scheduled: int
    tasks_completed: int
    tasks_failed: int
    conflicts_detected: int
    duration_ms: float
    scheduled_assignments: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tick_number": self.tick_number,
            "tasks_evaluated": self.tasks_evaluated,
            "tasks_scheduled": self.tasks_scheduled,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "conflicts_detected": self.conflicts_detected,
            "duration_ms": self.duration_ms,
            "scheduled_assignments": list(self.scheduled_assignments),
        }


class SchedulerEngine:
    """Core scheduling engine coordinating multi-project execution across a shared workforce pool."""

    def __init__(
        self,
        project_registry: ProjectRegistry,
        project_queue: ProjectQueue,
        work_queue: WorkQueue,
        resource_manager: ResourceManager,
        usage_tracker: Optional[UsageTracker] = None,
        budget_manager: Optional[BudgetManager] = None,
        delegation_engine: Optional[Any] = None,
        worker: Optional[Any] = None,
        db: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        cost_aware: bool = True,
    ):
        self.project_registry = project_registry
        self.project_queue = project_queue
        self.work_queue = work_queue
        self.resource_manager = resource_manager
        self.usage_tracker = usage_tracker
        self.budget_manager = budget_manager
        self.delegation_engine = delegation_engine
        self.worker = worker
        self.db = db
        self.event_bus = event_bus
        self.cost_aware = cost_aware
        self.tick_number = 0


    def _rank_candidates_cost_aware(
        self,
        task: WorkTask,
        project: Project,
        candidates: list[Employee],
    ) -> list[tuple[Employee, int]]:
        """Rank candidate employees with optional cost awareness:
        For LOW priority tasks, prefer employees configured with cheaper models.
        """
        base_ranked = TaskMatcher.rank_candidates(task.to_dict(), candidates)
        if not self.cost_aware or not self.budget_manager:
            return base_ranked

        adjusted: list[tuple[Employee, int]] = []
        for emp, score in base_ranked:
            bonus = 0
            emp_model = emp.model.get("model") if isinstance(emp.model, dict) else str(emp.model)
            pricing = self.budget_manager.pricing.get(emp_model or "default", {})
            rate = pricing.get("input_cost_per_1k", 0.0015)

            if project.priority == ProjectPriority.LOW:
                # Cheaper model gets bonus points for LOW priority
                if rate < 0.001:
                    bonus += 10
                elif rate <= 0.002:
                    bonus += 5
            elif project.priority == ProjectPriority.CRITICAL:
                # Specialized or high capacity gets slight preference
                if len(emp.capabilities) >= 3:
                    bonus += 5

            adjusted.append((emp, score + bonus))

        adjusted.sort(
            key=lambda item: (item[1], -getattr(item[0], "active_tasks", 0), len(item[0].capabilities), item[0].employee_id),
            reverse=True,
        )
        return adjusted

    def tick(
        self,
        execute: bool = False,
        output_dir: Optional[str] = None,
        custom_executor: Optional[Any] = None,
    ) -> ScheduleResult:
        """Executes one deterministic scheduling cycle:
        1. Discover ready tasks across active projects
        2. Rank project & task priorities
        3. Match available employees from shared pool
        4. Atomically reserve employees
        5. Enqueue execution (or synchronously execute if execute=True)
        6. Release employees upon task completion/failure
        7. Recalculate starvation and state
        """
        t0 = time.perf_counter()
        self.tick_number += 1

        # Acquire scheduler lock if DB supports it to prevent concurrent executions
        lock_acquired = False
        runner_id = f"sched_{id(self)}_{self.tick_number}"
        if self.db and hasattr(self.db, "acquire_scheduler_lock"):
            lock_acquired = self.db.acquire_scheduler_lock(
                lock_name="office_scheduler", locked_by=runner_id, ttl_seconds=30.0
            )
            if not lock_acquired:
                logger.warning("Scheduler tick collision: another scheduler instance holds the lock.")
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_RESOURCE_CONFLICT,
                            project_id="office",
                            payload={"conflict": "concurrent_scheduler_execution_blocked"},
                        )
                    )
                return ScheduleResult(
                    tick_number=self.tick_number,
                    tasks_evaluated=0,
                    tasks_scheduled=0,
                    tasks_completed=0,
                    tasks_failed=0,
                    conflicts_detected=1,
                    duration_ms=0.0,
                    scheduled_assignments=[],
                )

        try:
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_SCHEDULE_TICK,
                        project_id="office",
                        payload={"tick_number": self.tick_number},
                    )
                )

            # 0. Stale reservation recovery: recover workers whose leases expired or worker crashed
            if hasattr(self.resource_manager, "recover_stale_reservations"):
                self.resource_manager.recover_stale_reservations(work_queue=self.work_queue)

            # 1. Discover ready tasks
            ready_tasks = self.work_queue.get_ready_tasks(self.project_registry, self.project_queue)
            tasks_evaluated = len(ready_tasks)
            tasks_scheduled = 0
            tasks_completed = 0
            tasks_failed = 0
            conflicts_detected = 0
            assignments: list[dict] = []
            served_project_ids: set[str] = set()

            # Available employees pool for this tick
            available_pool = self.resource_manager.get_available_employees()
            available_pool_map = {e.employee_id: e for e in available_pool}

            # 2. Iterate through prioritized ready tasks
            for task in ready_tasks:
                if not available_pool_map:
                    break  # No more employees available in this tick

                project = self.project_registry.get_project(task.project_id)
                if not project or not project.is_active():
                    continue

                # Budget Check: verify project has not exhausted its budget
                if self.budget_manager and not self.budget_manager.can_spend(task.project_id):
                    # Auto-block project due to budget exhaustion
                    if project.status != ProjectStatus.BLOCKED:
                        self.project_registry.update_status(
                            task.project_id,
                            ProjectStatus.BLOCKED,
                            reason="Budget limit exceeded. Project blocked automatically.",
                        )
                    continue

                # Match best candidate from currently available pool
                ranked_candidates = self._rank_candidates_cost_aware(
                    task, project, list(available_pool_map.values())
                )

                if not ranked_candidates:
                    continue

                chosen_emp, match_score = ranked_candidates[0]

                # 3. Reserve Employee
                reserved = self.resource_manager.reserve_employee(
                    employee_id=chosen_emp.employee_id,
                    task_id=task.task_id,
                    project_id=task.project_id,
                )

                if not reserved:
                    conflicts_detected += 1
                    continue

                # Reservation succeeded -> Mark running in WorkQueue & update available pool
                available_pool_map.pop(chosen_emp.employee_id, None)
                self.work_queue.mark_running(task.task_id, chosen_emp.employee_id)
                tasks_scheduled += 1
                served_project_ids.add(task.project_id)

                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_TASK_DISPATCHED,
                            project_id=task.project_id,
                            task_id=task.task_id,
                            agent_id=chosen_emp.employee_id,
                            payload={"task_id": task.task_id, "employee_id": chosen_emp.employee_id},
                        )
                    )

                if project.status in (ProjectStatus.READY, ProjectStatus.PLANNED):
                    self.project_registry.update_status(task.project_id, ProjectStatus.RUNNING)


                assignment_record = {
                    "task_id": task.task_id,
                    "project_id": task.project_id,
                    "employee_id": chosen_emp.employee_id,
                    "employee_name": chosen_emp.name,
                    "match_score": match_score,
                    "task_title": task.title,
                }
                assignments.append(assignment_record)

                # 4. Execution (if requested)
                if execute:
                    task_success = False
                    result_data = None
                    tokens_in = 400
                    tokens_out = 200

                    try:
                        if custom_executor:
                            raw_res = custom_executor(task, chosen_emp)
                            if hasattr(raw_res, "success"):
                                task_success = raw_res.success
                                result_data = raw_res.to_dict() if hasattr(raw_res, "to_dict") else {"success": raw_res.success, "output": getattr(raw_res, "output", None)}
                                if getattr(raw_res, "usage", None):
                                    tokens_in = raw_res.usage.get("input_tokens", tokens_in)
                                    tokens_out = raw_res.usage.get("output_tokens", tokens_out)
                            else:
                                result_data = raw_res
                                task_success = True
                        elif self.worker:
                            # Use TaskWorker
                            agent_res = self.worker.execute_task(
                                task=task,
                                employee=chosen_emp,
                                output_dir=output_dir,
                            )
                            task_success = agent_res.success
                            result_data = agent_res.to_dict()
                            if agent_res.usage:
                                tokens_in = agent_res.usage.get("input_tokens", tokens_in)
                                tokens_out = agent_res.usage.get("output_tokens", tokens_out)
                        elif self.delegation_engine:
                            # Use delegation engine if available
                            del_res = self.delegation_engine.execute_task(
                                task=task,
                                team_candidates=[chosen_emp],
                                output_dir=output_dir or "./output",
                            )
                            task_success = del_res.get("success", False)
                            result_data = del_res
                        else:
                            # Deterministic simulated execution
                            result_data = {
                                "status": "COMPLETED",
                                "output": f"Executed by {chosen_emp.name} ({chosen_emp.role})",
                                "task_id": task.task_id,
                            }
                            task_success = True


                    except Exception as ex:
                        logger.error(f"Task execution error on task {task.task_id}: {ex}")
                        task_success = False
                        result_data = {"error": str(ex)}

                    # Track usage and record expense
                    model_name = chosen_emp.model.get("model") if isinstance(chosen_emp.model, dict) else "default"
                    if self.budget_manager:
                        cost = self.budget_manager.calculate_cost(model_name or "default", tokens_in, tokens_out)
                        self.budget_manager.record_expense(task.project_id, cost)
                    else:
                        cost = 0.001

                    if self.usage_tracker:
                        self.usage_tracker.record_usage(
                            project_id=task.project_id,
                            task_id=task.task_id,
                            employee_id=chosen_emp.employee_id,
                            model=model_name or "default",
                            input_tokens=tokens_in,
                            output_tokens=tokens_out,
                            estimated_cost=cost,
                        )

                    # Handle Completion or Failure
                    if task_success:
                        self.work_queue.mark_completed(task.task_id, result=result_data)
                        self.resource_manager.release_employee(chosen_emp.employee_id)
                        tasks_completed += 1
                        if hasattr(chosen_emp, "completed_tasks"):
                            chosen_emp.completed_tasks += 1

                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    event_type=EVENT_TASK_COMPLETED,
                                    project_id=task.project_id,
                                    task_id=task.task_id,
                                    agent_id=chosen_emp.employee_id,
                                    payload={"result": result_data},
                                )
                            )

                        # Check if project has completed all tasks
                        self._check_project_completion(task.project_id)
                    else:
                        # Failure handling & automatic recovery
                        self.work_queue.mark_failed(task.task_id, reason=str(result_data))
                        self.resource_manager.release_employee(chosen_emp.employee_id)
                        tasks_failed += 1

                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    event_type=EVENT_TASK_FAILED,
                                    project_id=task.project_id,
                                    task_id=task.task_id,
                                    agent_id=chosen_emp.employee_id,
                                    payload={"reason": str(result_data)},
                                )
                            )

                        # Recover: requeue task so another employee can take it next tick
                        self.work_queue.requeue_task(task.task_id)

            # 5. Starvation prevention tick
            self.project_queue.tick_starvation(served_project_ids)

            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            result = ScheduleResult(
                tick_number=self.tick_number,
                tasks_evaluated=tasks_evaluated,
                tasks_scheduled=tasks_scheduled,
                tasks_completed=tasks_completed,
                tasks_failed=tasks_failed,
                conflicts_detected=conflicts_detected,
                duration_ms=duration_ms,
                scheduled_assignments=assignments,
            )

            if self.db:
                self.db.save_scheduler_run(
                    run_id=f"run_{self.tick_number}_{int(time.time()*1000)}",
                    tick_number=self.tick_number,
                    tasks_evaluated=tasks_evaluated,
                    tasks_scheduled=tasks_scheduled,
                    conflicts_detected=conflicts_detected,
                    duration_ms=duration_ms,
                )

            return result
        finally:
            if lock_acquired and self.db and hasattr(self.db, "release_scheduler_lock"):
                self.db.release_scheduler_lock(lock_name="office_scheduler", locked_by=runner_id)

    def _check_project_completion(self, project_id: str) -> None:
        """Checks if all tasks belonging to the project have reached COMPLETED status."""
        all_tasks = [t for t in self.work_queue.list_all_tasks() if t.project_id == project_id]
        if not all_tasks:
            return

        all_completed = all(t.status == TASK_COMPLETED for t in all_tasks)
        if all_completed:
            proj = self.project_registry.get_project(project_id)
            if proj and proj.metadata and proj.metadata.get("objective_id"):
                # Project completion is governed by the Objective lifecycle & evaluation
                return

            if proj and proj.status not in (ProjectStatus.COMPLETED, ProjectStatus.FAILED):
                self.project_registry.complete_project(project_id)
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_PROJECT_COMPLETED,
                            project_id=project_id,
                            payload={"total_tasks": len(all_tasks), "status": "COMPLETED"},
                        )
                    )

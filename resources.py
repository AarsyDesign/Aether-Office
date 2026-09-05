"""ResourceManager and Employee Resource Lock for Aether Office Phase 6."""

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, List, Dict, Set

from workforce import (
    Employee,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    AVAILABILITY_AVAILABLE,
    AVAILABILITY_BUSY,
    AVAILABILITY_OFFLINE,
    STATE_IDLE,
    STATE_WORKING,
)
from events import (
    EventBus,
    Event,
    EVENT_EMPLOYEE_RESERVED,
    EVENT_EMPLOYEE_RELEASED,
    EVENT_EMPLOYEE_OVERLOADED,
    EVENT_RESOURCE_CONFLICT,
)

logger = logging.getLogger("aether.resources")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResourceManager:
    """Manages workforce availability, capacity calculation, and atomic reservation locks."""

    def __init__(
        self,
        organization: Any,
        db: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        max_tasks_per_employee: int = 1,
    ):
        self.organization = organization
        self.db = db
        self.event_bus = event_bus
        self.max_tasks_per_employee = max_tasks_per_employee
        self._reservations: dict[str, dict] = {}  # employee_id -> reservation data
        self._sync_reservations_from_db()

    def _sync_reservations_from_db(self):
        if not self.db:
            return
        try:
            records = self.db.list_reservations()
            for r in records:
                self._reservations[r["employee_id"]] = {
                    "employee_id": r["employee_id"],
                    "task_id": r["task_id"],
                    "project_id": r["project_id"],
                    "reserved_at": r["reserved_at"],
                }
        except Exception as e:
            logger.warning(f"Could not load reservations from DB: {e}")

    def get_employee(self, employee_id: str) -> Optional[Employee]:
        if hasattr(self.organization, "get_employee"):
            return self.organization.get_employee(employee_id)
        if hasattr(self.organization, "employees"):
            emps = self.organization.employees
            if isinstance(emps, dict):
                return emps.get(employee_id)
            elif isinstance(emps, list):
                for e in emps:
                    if getattr(e, "employee_id", None) == employee_id or getattr(e, "id", None) == employee_id:
                        return e
        return None

    def list_all_employees(self) -> list[Employee]:
        if hasattr(self.organization, "list_employees"):
            return self.organization.list_employees()
        if hasattr(self.organization, "employees"):
            emps = self.organization.employees
            if isinstance(emps, dict):
                return list(emps.values())
            elif isinstance(emps, list):
                return emps
        return []

    def is_reserved(self, employee_id: str) -> bool:
        """Check whether employee is currently locked by a reservation."""
        if employee_id in self._reservations:
            res = self._reservations[employee_id]
            exp = res.get("expires_at")
            if exp and exp < _now_iso():
                self._reservations.pop(employee_id, None)
            else:
                return True
        if self.db:
            return self.db.is_employee_reserved(employee_id)
        return False

    def get_reservation(self, employee_id: str) -> Optional[dict]:
        if employee_id in self._reservations:
            res = self._reservations[employee_id]
            exp = res.get("expires_at")
            if exp and exp < _now_iso():
                self._reservations.pop(employee_id, None)
            else:
                return res
        if self.db:
            return self.db.get_reservation(employee_id)
        return None

    def reserve_employee(
        self,
        employee_id: str,
        task_id: str,
        project_id: str,
        lease_seconds: float = 300.0,
    ) -> bool:
        """Atomically lock an employee for task execution.
        Prevents double-assignment across multiple projects.
        """
        emp = self.get_employee(employee_id)
        if not emp:
            logger.warning(f"Reserve failed: Employee {employee_id} not found")
            return False

        if getattr(emp, "availability", None) == AVAILABILITY_OFFLINE or getattr(emp, "status", None) == STATUS_INACTIVE:
            logger.warning(f"Reserve failed: Employee {employee_id} is offline/inactive")
            return False

        if self.is_reserved(employee_id):
            logger.warning(f"Reserve failed: Employee {employee_id} is already reserved for another task")
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_RESOURCE_CONFLICT,
                        project_id=project_id,
                        task_id=task_id,
                        agent_id=employee_id,
                        payload={"conflict": "double_reservation_attempt", "employee_id": employee_id},
                    )
                )
            return False

        if emp.active_tasks >= self.max_tasks_per_employee:
            logger.warning(f"Reserve failed: Employee {employee_id} workload limit reached ({emp.active_tasks})")
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_EMPLOYEE_OVERLOADED,
                        project_id=project_id,
                        task_id=task_id,
                        agent_id=employee_id,
                        payload={"employee_id": employee_id, "active_tasks": emp.active_tasks},
                    )
                )
            return False

        # SQLite atomic reservation lock with lease duration
        if self.db:
            acquired = self.db.reserve_employee(
                employee_id, task_id, project_id, lease_seconds=lease_seconds
            )
            if not acquired:
                logger.warning(f"Reserve failed: DB lock collision on employee {employee_id}")
                return False

        # Update in-memory state
        now = _now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat() if lease_seconds else None
        self._reservations[employee_id] = {
            "employee_id": employee_id,
            "task_id": task_id,
            "project_id": project_id,
            "reserved_at": now,
            "expires_at": expires_at,
        }
        emp.availability = AVAILABILITY_BUSY
        emp.live_state = STATE_WORKING
        emp.active_tasks += 1

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_EMPLOYEE_RESERVED,
                    project_id=project_id,
                    task_id=task_id,
                    agent_id=employee_id,
                    payload={
                        "employee_id": employee_id,
                        "task_id": task_id,
                        "project_id": project_id,
                    },
                )
            )
        return True

    def release_employee(self, employee_id: str) -> bool:
        """Release reservation lock on an employee upon task completion or failure."""
        if not self.is_reserved(employee_id):
            return False

        res_info = self._reservations.pop(employee_id, None)
        project_id = res_info.get("project_id", "") if res_info else ""
        task_id = res_info.get("task_id", "") if res_info else ""

        if self.db:
            self.db.release_employee(employee_id)

        emp = self.get_employee(employee_id)
        if emp:
            emp.availability = AVAILABILITY_AVAILABLE
            emp.live_state = STATE_IDLE
            emp.active_tasks = max(0, emp.active_tasks - 1)

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_EMPLOYEE_RELEASED,
                    project_id=project_id,
                    task_id=task_id,
                    agent_id=employee_id,
                    payload={"employee_id": employee_id, "released_from_task": task_id},
                )
            )
        return True

    def recover_stale_reservations(
        self,
        timeout_seconds: Optional[float] = None,
        work_queue: Optional[Any] = None,
    ) -> list[dict]:
        """Recovers and resets stale employee reservations left by crashed workers or expired leases.
        Re-releases employees and optionally requeues interrupted tasks.
        """
        stale_records = []
        if self.db:
            stale_records = self.db.clean_stale_reservations(timeout_seconds)

        # Also check in-memory reservations for expirations
        now_iso = _now_iso()
        expired_in_memory = [
            emp_id for emp_id, info in self._reservations.items()
            if info.get("expires_at") and info["expires_at"] < now_iso
        ]
        for emp_id in expired_in_memory:
            info = self._reservations.pop(emp_id, None)
            if info and not any(r.get("employee_id") == emp_id for r in stale_records):
                stale_records.append(info)

        for rec in stale_records:
            emp_id = rec.get("employee_id")
            task_id = rec.get("task_id")
            proj_id = rec.get("project_id")

            # Clean memory cache
            self._reservations.pop(emp_id, None)

            emp = self.get_employee(emp_id)
            if emp:
                emp.availability = AVAILABILITY_AVAILABLE
                emp.live_state = STATE_IDLE
                emp.active_tasks = max(0, emp.active_tasks - 1)

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_EMPLOYEE_RELEASED,
                        project_id=proj_id,
                        task_id=task_id,
                        agent_id=emp_id,
                        payload={"employee_id": emp_id, "reason": "stale_lease_recovery"},
                    )
                )

            # Requeue or reset task so it doesn't stay stuck forever
            if work_queue and task_id:
                try:
                    work_queue.requeue_task(task_id)
                except Exception as ex:
                    logger.warning(f"Failed to requeue task {task_id} during stale recovery: {ex}")

        return stale_records


    def get_available_employees(self) -> list[Employee]:
        """Returns employees that are active, not reserved, and have capacity."""
        available: list[Employee] = []
        for emp in self.list_all_employees():
            if getattr(emp, "status", None) != STATUS_ACTIVE:
                continue
            if getattr(emp, "availability", None) == AVAILABILITY_OFFLINE:
                continue
            if self.is_reserved(emp.employee_id):
                continue
            if emp.active_tasks >= self.max_tasks_per_employee:
                continue
            available.append(emp)
        return available

    def get_workforce_capacity(self) -> dict:
        """Computes office-level workforce capacity metrics."""
        employees = self.list_all_employees()
        total = len(employees)
        offline = sum(1 for e in employees if getattr(e, "availability", None) == AVAILABILITY_OFFLINE or getattr(e, "status", None) == STATUS_INACTIVE)
        busy = sum(1 for e in employees if self.is_reserved(e.employee_id) or getattr(e, "availability", None) == AVAILABILITY_BUSY)
        available = max(0, total - busy - offline)
        running_tasks = len(self._reservations)
        utilization = round(busy / total, 4) if total > 0 else 0.0

        return {
            "total_employees": total,
            "available": available,
            "busy": busy,
            "offline": offline,
            "active_tasks": running_tasks,
            "running_tasks": running_tasks,
            "utilization": utilization,
        }

    def get_employee_utilization(self, employee_id: str) -> Optional[dict]:
        """Provides operational details for a specific employee."""
        emp = self.get_employee(employee_id)
        if not emp:
            return None
        res = self.get_reservation(employee_id)
        return {
            "employee_id": emp.employee_id,
            "name": emp.name,
            "role": emp.role,
            "department": emp.department,
            "status": emp.status,
            "availability": emp.availability,
            "live_state": emp.live_state,
            "is_reserved": res is not None,
            "current_reservation": res,
            "active_tasks": emp.active_tasks,
            "completed_tasks": getattr(emp, "completed_tasks", 0),
        }

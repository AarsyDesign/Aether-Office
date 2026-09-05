"""Aether Office - Telemetry Ingestion Bridge.

Connects external AI tools (Hermes Agent, Antigravity IDE, VS Code, Cron Jobs)
to the Aether Office virtual organization, mapping real actions into live employee states,
desk animations, SSE event streams, and activity logs.
"""

from __future__ import annotations
import uuid
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from events import (
    EventBus,
    Event,
    EVENT_TASK_STARTED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_AGENT_STATE_CHANGED,
)

logger = logging.getLogger("aether.telemetry")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TelemetryActivity:
    activity_id: str
    source: str
    project: str
    role: str
    employee_id: str
    employee_name: str
    task_title: str
    status: str  # WORKING, COMPLETED, FAILED, IDLE
    details: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "source": self.source,
            "project": self.project,
            "role": self.role,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "task_title": self.task_title,
            "status": self.status,
            "details": self.details,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# Role mapping fallback for standard 5-employee roster
ROLE_TO_EMPLOYEE_HINT = {
    "developer": ("developer_001", "Eko Prasetyo"),
    "backend": ("developer_001", "Eko Prasetyo"),
    "frontend": ("developer_001", "Eko Prasetyo"),
    "engineer": ("developer_001", "Eko Prasetyo"),
    "coder": ("developer_001", "Eko Prasetyo"),
    "qa": ("qa_001", "Ratna Sari"),
    "tester": ("qa_001", "Ratna Sari"),
    "audit": ("qa_001", "Ratna Sari"),
    "linter": ("qa_001", "Ratna Sari"),
    "security": ("qa_001", "Ratna Sari"),
    "planner": ("planner_001", "Rian Pratama"),
    "architect": ("planner_001", "Rian Pratama"),
    "devops": ("planner_001", "Rian Pratama"),
    "cron": ("planner_001", "Rian Pratama"),
    "sysadmin": ("planner_001", "Rian Pratama"),
    "pm": ("pm_001", "Budi Santoso"),
    "product": ("pm_001", "Budi Santoso"),
    "lead": ("pm_001", "Budi Santoso"),
    "conceptor": ("conceptor_001", "Dewi Lestari"),
    "design": ("conceptor_001", "Dewi Lestari"),
    "research": ("conceptor_001", "Dewi Lestari"),
    "marketing": ("conceptor_001", "Dewi Lestari"),
}


class TelemetryManager:
    """Manages ingestion of external agent activities and synchronizes with office state."""

    def __init__(self, db: Any = None, event_bus: Optional[EventBus] = None):
        self.db = db
        self.event_bus = event_bus
        self._active_activities: Dict[str, TelemetryActivity] = {}
        self._history: List[TelemetryActivity] = []
        self._init_db_schema()

    def _init_db_schema(self) -> None:
        """Create telemetry table in SQLite if available."""
        if not self.db or not hasattr(self.db, "conn"):
            return
        try:
            with self.db.conn:
                self.db.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry_activities (
                        id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        project TEXT DEFAULT '',
                        role TEXT DEFAULT '',
                        employee_id TEXT NOT NULL,
                        employee_name TEXT DEFAULT '',
                        task_title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        details TEXT DEFAULT '',
                        metadata TEXT DEFAULT '{}',
                        created_at TEXT,
                        updated_at TEXT
                    )
                    """
                )
        except Exception as e:
            logger.warning(f"Could not initialize telemetry table: {e}")

    def resolve_employee(
        self,
        employee_id: Optional[str] = None,
        role: Optional[str] = None,
        employee_name: Optional[str] = None,
    ) -> tuple[str, str]:
        """Resolves target employee_id and name based on input hints."""
        # 1. Direct employee_id match
        if employee_id:
            if self.db and hasattr(self.db, "get_employee"):
                emp = self.db.get_employee(employee_id)
                if emp:
                    return emp["id"], emp["name"]
            # Fallback to hint table
            for r_key, (e_id, e_name) in ROLE_TO_EMPLOYEE_HINT.items():
                if e_id == employee_id:
                    return e_id, employee_name or e_name
            return employee_id, employee_name or employee_id

        # 2. Match by role
        norm_role = (role or "developer").lower().strip()
        for r_key, (e_id, e_name) in ROLE_TO_EMPLOYEE_HINT.items():
            if r_key in norm_role:
                return e_id, employee_name or e_name

        # Default fallback
        return "developer_001", employee_name or "Eko Prasetyo"

    def record_activity(
        self,
        source: str = "hermes",
        task_title: str = "",
        status: str = "WORKING",
        role: Optional[str] = None,
        employee_id: Optional[str] = None,
        employee_name: Optional[str] = None,
        project: str = "Aplikasi Kasir Pondok",
        details: str = "",
        metadata: Optional[dict] = None,
    ) -> TelemetryActivity:
        """Records an external activity update and propagates live state."""
        e_id, e_name = self.resolve_employee(employee_id, role, employee_name)
        norm_status = status.upper().strip()
        if norm_status in ("START", "STARTED", "BUSY", "IN_PROGRESS"):
            norm_status = "WORKING"
        elif norm_status in ("DONE", "FINISHED", "SUCCESS"):
            norm_status = "COMPLETED"
        elif norm_status in ("ERROR", "FAIL"):
            norm_status = "FAILED"

        # Check existing active activity for this employee
        existing = self._active_activities.get(e_id)
        if existing and existing.task_title == task_title:
            activity_id = existing.activity_id
        else:
            activity_id = f"tel_{uuid.uuid4().hex[:8]}"

        activity = TelemetryActivity(
            activity_id=activity_id,
            source=source,
            project=project,
            role=role or "developer",
            employee_id=e_id,
            employee_name=e_name,
            task_title=task_title or "Processing AI Task",
            status=norm_status,
            details=details,
            metadata=metadata or {},
            updated_at=_now_iso(),
        )

        # Update in-memory live tracking
        if norm_status == "WORKING":
            self._active_activities[e_id] = activity
            is_busy = True
            live_st = "WORKING"
        else:
            self._active_activities.pop(e_id, None)
            is_busy = False
            live_st = "IDLE"

        self._history.insert(0, activity)
        if len(self._history) > 100:
            self._history = self._history[:100]

        # Update employee live state in DB
        if self.db and hasattr(self.db, "update_employee_state"):
            try:
                avail = "busy" if is_busy else "available"
                self.db.update_employee_state(e_id, availability=avail, live_state=live_st)
            except Exception as e:
                logger.warning(f"Failed to update employee live state: {e}")

        # Persist activity to DB
        if self.db and hasattr(self.db, "conn"):
            try:
                import json
                with self.db.conn:
                    self.db.conn.execute(
                        """
                        INSERT OR REPLACE INTO telemetry_activities
                        (id, source, project, role, employee_id, employee_name, task_title, status, details, metadata, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            activity.activity_id,
                            activity.source,
                            activity.project,
                            activity.role,
                            activity.employee_id,
                            activity.employee_name,
                            activity.task_title,
                            activity.status,
                            activity.details,
                            json.dumps(activity.metadata),
                            activity.created_at,
                            activity.updated_at,
                        ),
                    )
            except Exception as e:
                logger.warning(f"Could not persist telemetry activity: {e}")

        # Emit real-time event to SSE listeners
        if self.event_bus:
            evt_type = (
                EVENT_TASK_STARTED
                if norm_status == "WORKING"
                else (EVENT_TASK_COMPLETED if norm_status == "COMPLETED" else EVENT_TASK_FAILED)
            )
            self.event_bus.publish(
                Event(
                    event_type=evt_type,
                    project_id=project,
                    agent_role=f"{activity.source.upper()} / {activity.role.capitalize()}",
                    agent_id=e_id,
                    payload=activity.to_dict(),
                )
            )

        return activity

    def update_activity(
        self,
        activity_id: str,
        status: str = "COMPLETED",
        details: str = "",
        metadata: Optional[dict] = None,
    ) -> Optional[TelemetryActivity]:
        """Update an existing activity by ID (e.g. mark COMPLETED or FAILED)."""
        target: Optional[TelemetryActivity] = None
        for a in self._active_activities.values():
            if a.activity_id == activity_id:
                target = a
                break
        if not target:
            for a in self._history:
                if a.activity_id == activity_id:
                    target = a
                    break
        if not target:
            return None

        return self.record_activity(
            source=target.source,
            role=target.role,
            task_title=target.task_title,
            status=status,
            details=details or target.details,
            project=target.project,
            employee_id=target.employee_id,
            metadata=metadata or target.metadata,
        )

    def get_active_activity(self, employee_id: str) -> Optional[TelemetryActivity]:
        return self._active_activities.get(employee_id)

    def get_active_activities(self) -> List[dict]:
        return [a.to_dict() for a in self._active_activities.values()]

    def get_history(self, limit: int = 40) -> List[dict]:
        return [a.to_dict() for a in self._history[:limit]]

    def clear_active(self, employee_id: Optional[str] = None) -> None:
        if employee_id:
            self._active_activities.pop(employee_id, None)
            if self.db and hasattr(self.db, "update_employee_state"):
                try:
                    self.db.update_employee_state(employee_id, availability="available", live_state="IDLE")
                except Exception:
                    pass
        else:
            for eid in list(self._active_activities.keys()):
                self._active_activities.pop(eid, None)
                if self.db and hasattr(self.db, "update_employee_state"):
                    try:
                        self.db.update_employee_state(eid, availability="available", live_state="IDLE")
                    except Exception:
                        pass

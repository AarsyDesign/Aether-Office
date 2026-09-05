"""Project registry and Project model for Aether Office Phase 6."""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any, List, Dict

from events import (
    EventBus,
    Event,
    EVENT_PROJECT_CREATED,
    EVENT_PROJECT_STARTED,
    EVENT_PROJECT_PAUSED,
    EVENT_PROJECT_RESUMED,
    EVENT_PROJECT_COMPLETED,
    EVENT_PROJECT_FAILED,
)

logger = logging.getLogger("aether.projects")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStatus(str, Enum):
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


VALID_PROJECT_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.PLANNED: {
        ProjectStatus.READY,
        ProjectStatus.RUNNING,
        ProjectStatus.CANCELLED,
    },
    ProjectStatus.READY: {
        ProjectStatus.RUNNING,
        ProjectStatus.PAUSED,
        ProjectStatus.BLOCKED,
        ProjectStatus.COMPLETED,
        ProjectStatus.FAILED,
        ProjectStatus.CANCELLED,
    },
    ProjectStatus.RUNNING: {
        ProjectStatus.PAUSED,
        ProjectStatus.BLOCKED,
        ProjectStatus.COMPLETED,
        ProjectStatus.FAILED,
        ProjectStatus.CANCELLED,
    },
    ProjectStatus.PAUSED: {
        ProjectStatus.RUNNING,
        ProjectStatus.BLOCKED,
        ProjectStatus.CANCELLED,
    },
    ProjectStatus.BLOCKED: {
        ProjectStatus.READY,
        ProjectStatus.RUNNING,
        ProjectStatus.PAUSED,
        ProjectStatus.CANCELLED,
        ProjectStatus.FAILED,
    },
    ProjectStatus.COMPLETED: set(),  # Terminal state
    ProjectStatus.FAILED: set(),     # Terminal state
    ProjectStatus.CANCELLED: set(),  # Terminal state
}


class InvalidProjectStateTransition(ValueError):
    """Raised when an illegal project state transition is attempted."""
    pass


def validate_project_transition(current: ProjectStatus, target: ProjectStatus) -> bool:
    """Validate if a project state transition is permitted."""
    if current == target:
        return True
    allowed = VALID_PROJECT_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidProjectStateTransition(
            f"Invalid project transition: {current.value} -> {target.value}. Allowed transitions: {[s.value for s in allowed]}"
        )
    return True


class ProjectPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


    @property
    def weight(self) -> float:
        weights = {
            ProjectPriority.CRITICAL: 100.0,
            ProjectPriority.HIGH: 50.0,
            ProjectPriority.NORMAL: 20.0,
            ProjectPriority.LOW: 5.0,
        }
        return weights.get(self, 20.0)


@dataclass
class Project:
    """Represents an independent project within Aether Office."""

    project_id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.PLANNED
    priority: ProjectPriority = ProjectPriority.NORMAL
    deadline: Optional[str] = None  # ISO-8601 string
    owner_employee_id: Optional[str] = None
    team_id: Optional[str] = None
    budget: float = 0.0
    spent: float = 0.0
    output_dir: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def is_active(self) -> bool:
        return self.status in (ProjectStatus.READY, ProjectStatus.RUNNING)

    def is_terminal(self) -> bool:
        return self.status in (ProjectStatus.COMPLETED, ProjectStatus.FAILED, ProjectStatus.CANCELLED)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value if isinstance(self.status, ProjectStatus) else str(self.status),
            "priority": self.priority.value if isinstance(self.priority, ProjectPriority) else str(self.priority),
            "deadline": self.deadline,
            "owner_employee_id": self.owner_employee_id,
            "team_id": self.team_id,
            "budget": self.budget,
            "spent": self.spent,
            "output_dir": self.output_dir,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        p_status = data.get("status", "PLANNED")
        if isinstance(p_status, str):
            try:
                p_status = ProjectStatus(p_status)
            except ValueError:
                p_status = ProjectStatus.PLANNED

        p_priority = data.get("priority", "NORMAL")
        if isinstance(p_priority, str):
            try:
                p_priority = ProjectPriority(p_priority)
            except ValueError:
                p_priority = ProjectPriority.NORMAL

        metadata = data.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        return cls(
            project_id=data.get("project_id") or data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description") or data.get("brief", ""),
            status=p_status,
            priority=p_priority,
            deadline=data.get("deadline"),
            owner_employee_id=data.get("owner_employee_id"),
            team_id=data.get("team_id"),
            budget=float(data.get("budget", 0.0) or 0.0),
            spent=float(data.get("spent", 0.0) or 0.0),
            output_dir=data.get("output_dir"),
            metadata=metadata,
            created_at=data.get("created_at") or _now_iso(),
            updated_at=data.get("updated_at") or _now_iso(),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )


class ProjectRegistry:
    """Manages active and historical projects with DB synchronization and EventBus notifications."""

    def __init__(self, db: Any, event_bus: Optional[EventBus] = None):
        self.db = db
        self.event_bus = event_bus
        self._projects: dict[str, Project] = {}
        self._load_from_db()

    def _load_from_db(self):
        try:
            records = self.db.list_projects()
            for r in records:
                p = Project.from_dict(r)
                self._projects[p.project_id] = p
        except Exception as e:
            logger.warning(f"Could not load projects from DB: {e}")

    def register_project(self, project: Project) -> Project:
        now = _now_iso()
        project.updated_at = now
        self._projects[project.project_id] = project
        self.db.save_project(
            project_id=project.project_id,
            name=project.name,
            description=project.description,
            status=project.status.value,
            priority=project.priority.value,
            deadline=project.deadline,
            owner_employee_id=project.owner_employee_id,
            team_id=project.team_id,
            budget=project.budget,
            spent=project.spent,
            output_dir=project.output_dir,
            metadata=project.metadata,
            started_at=project.started_at,
            completed_at=project.completed_at,
        )
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_PROJECT_CREATED,
                    project_id=project.project_id,
                    payload=project.to_dict(),
                )
            )
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        if project_id in self._projects:
            return self._projects[project_id]
        rec = self.db.get_project(project_id)
        if rec:
            p = Project.from_dict(rec)
            self._projects[project_id] = p
            return p
        return None

    def list_projects(self, status: Optional[ProjectStatus] = None) -> list[Project]:
        self._load_from_db()
        if status:
            return [p for p in self._projects.values() if p.status == status]
        return list(self._projects.values())

    def update_status(self, project_id: str, new_status: ProjectStatus, reason: str = "") -> Project:
        p = self.get_project(project_id)
        if not p:
            raise ValueError(f"Project {project_id} not found")
        old_status = p.status
        if isinstance(new_status, str):
            try:
                new_status = ProjectStatus(new_status)
            except ValueError:
                raise InvalidProjectStateTransition(f"Unknown project status: {new_status}")
        validate_project_transition(old_status, new_status)
        p.status = new_status
        now = _now_iso()
        p.updated_at = now

        event_type = None
        if old_status == ProjectStatus.PAUSED and new_status == ProjectStatus.RUNNING:
            event_type = EVENT_PROJECT_RESUMED
        elif new_status == ProjectStatus.RUNNING and not p.started_at:
            p.started_at = now
            event_type = EVENT_PROJECT_STARTED
        elif new_status == ProjectStatus.PAUSED:
            event_type = EVENT_PROJECT_PAUSED
        elif new_status == ProjectStatus.COMPLETED:
            p.completed_at = now
            event_type = EVENT_PROJECT_COMPLETED
        elif new_status == ProjectStatus.FAILED:
            p.completed_at = now
            event_type = EVENT_PROJECT_FAILED

        self.db.save_project(
            project_id=p.project_id,
            name=p.name,
            description=p.description,
            status=p.status.value,
            priority=p.priority.value,
            deadline=p.deadline,
            owner_employee_id=p.owner_employee_id,
            team_id=p.team_id,
            budget=p.budget,
            spent=p.spent,
            output_dir=p.output_dir,
            metadata=p.metadata,
            started_at=p.started_at,
            completed_at=p.completed_at,
        )

        if self.event_bus and event_type:
            self.event_bus.publish(
                Event(
                    event_type=event_type,
                    project_id=p.project_id,
                    payload={"old_status": old_status.value, "new_status": new_status.value, "reason": reason},
                )
            )
        return p

    def pause_project(self, project_id: str, reason: str = "") -> Project:
        return self.update_status(project_id, ProjectStatus.PAUSED, reason=reason)

    def resume_project(self, project_id: str) -> Project:
        return self.update_status(project_id, ProjectStatus.RUNNING)

    def complete_project(self, project_id: str) -> Project:
        return self.update_status(project_id, ProjectStatus.COMPLETED)

    def fail_project(self, project_id: str, reason: str = "") -> Project:
        return self.update_status(project_id, ProjectStatus.FAILED, reason=reason)

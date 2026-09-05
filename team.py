"""Dynamic Project Team and Deterministic TeamBuilder for Aether Office."""

from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict
from workforce import Organization, Employee, STATUS_ACTIVE, AVAILABILITY_AVAILABLE
from matcher import TaskMatcher
from events import (
    EventBus,
    Event,
    EVENT_TEAM_CREATED,
    EVENT_TEAM_MEMBER_ADDED,
    EVENT_TEAM_MEMBER_REMOVED,
)

logger = logging.getLogger("aether.team")

TEAM_ACTIVE = "active"
TEAM_COMPLETED = "completed"
TEAM_DISBANDED = "disbanded"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProjectTeam:
    """Represents a dynamic cross-functional team assembled for a specific project."""

    team_id: str
    project_id: str
    name: str
    objective: str = ""
    employee_ids: list[str] = field(default_factory=list)
    lead_employee_id: Optional[str] = None
    status: str = TEAM_ACTIVE
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    event_bus: Optional[EventBus] = field(default=None, repr=False)

    def add_employee(self, employee_id: str, role: Optional[str] = None) -> bool:
        """Add an employee to the team."""
        if employee_id not in self.employee_ids:
            self.employee_ids.append(employee_id)
            self.updated_at = _now_iso()
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_TEAM_MEMBER_ADDED,
                        project_id=self.project_id,
                        agent_id=employee_id,
                        agent_role=role,
                        payload={"team_id": self.team_id, "role": role},
                    )
                )
            return True
        return False

    def remove_employee(self, employee_id: str) -> bool:
        """Remove an employee from the team."""
        if employee_id in self.employee_ids:
            self.employee_ids.remove(employee_id)
            if self.lead_employee_id == employee_id:
                self.lead_employee_id = self.employee_ids[0] if self.employee_ids else None
            self.updated_at = _now_iso()
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_TEAM_MEMBER_REMOVED,
                        project_id=self.project_id,
                        agent_id=employee_id,
                        payload={"team_id": self.team_id},
                    )
                )
            return True
        return False

    def set_lead(self, employee_id: str) -> None:
        """Assign an employee as the team lead."""
        if employee_id not in self.employee_ids:
            self.add_employee(employee_id)
        self.lead_employee_id = employee_id
        self.updated_at = _now_iso()

    def get_active_members(self, org: Organization) -> list[Employee]:
        """Return list of active Employee instances belonging to this team."""
        members = []
        for emp_id in self.employee_ids:
            emp = org.get_employee(emp_id)
            if emp and emp.is_active:
                members.append(emp)
        return members

    def get_member_roles(self, org: Organization) -> dict[str, str]:
        """Return mapping of employee_id -> role."""
        res = {}
        for emp_id in self.employee_ids:
            emp = org.get_employee(emp_id)
            if emp:
                res[emp_id] = emp.role
        return res

    def get_member_capabilities(self, org: Organization) -> dict[str, list[str]]:
        """Return mapping of employee_id -> list of capabilities."""
        res = {}
        for emp_id in self.employee_ids:
            emp = org.get_employee(emp_id)
            if emp:
                res[emp_id] = list(emp.capabilities)
        return res

    def close(self, status: str = TEAM_COMPLETED) -> None:
        """Deactivate/close the team."""
        self.status = status
        self.updated_at = _now_iso()

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "project_id": self.project_id,
            "name": self.name,
            "objective": self.objective,
            "employee_ids": list(self.employee_ids),
            "lead_employee_id": self.lead_employee_id,
            "status": self.status,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict, event_bus: Optional[EventBus] = None) -> ProjectTeam:
        return cls(
            team_id=d.get("team_id") or d.get("id", str(uuid.uuid4())),
            project_id=d.get("project_id", "project"),
            name=d.get("name", "Project Team"),
            objective=d.get("objective", ""),
            employee_ids=list(d.get("employee_ids", [])),
            lead_employee_id=d.get("lead_employee_id"),
            status=d.get("status", TEAM_ACTIVE),
            metadata=dict(d.get("metadata", {})),
            created_at=d.get("created_at", _now_iso()),
            updated_at=d.get("updated_at", _now_iso()),
            event_bus=event_bus,
        )


class TeamBuilder:
    """Builds dynamic project teams deterministically using TaskMatcher and Organization."""

    @classmethod
    def build_team(
        cls,
        org: Organization,
        objective: str,
        required_capabilities: Optional[list[str]] = None,
        preferred_roles: Optional[list[str]] = None,
        department_preferences: Optional[list[str]] = None,
        project_id: Optional[str] = None,
        name: Optional[str] = None,
        lead_role: Optional[str] = None,
        event_bus: Optional[EventBus] = None,
    ) -> ProjectTeam:
        """Deterministically assemble a team matching requirements.
        Selection priority:
        1. Role match
        2. Capability match
        3. Department match
        4. Availability & status
        5. Workload (least active tasks)
        """
        proj_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        team_id = f"team_{uuid.uuid4().hex[:8]}"
        team_name = name or f"Team: {objective[:30]}"

        all_candidates = org.list_employees()
        selected_employees: list[Employee] = []
        selected_ids: set[str] = set()

        # 1. Fill Preferred Roles
        if preferred_roles:
            for role in preferred_roles:
                task_spec = {"role": role, "required_capabilities": required_capabilities or []}
                # Filter out already selected to avoid duplicates
                available_pool = [e for e in all_candidates if e.employee_id not in selected_ids]
                best = TaskMatcher.find_best_employee(task_spec, available_pool)
                if best:
                    selected_employees.append(best)
                    selected_ids.add(best.employee_id)

        # 2. Fill Missing Required Capabilities
        req_caps = set(required_capabilities or [])
        covered_caps: set[str] = set()
        for emp in selected_employees:
            covered_caps.update(c.lower() for c in emp.capabilities)

        missing_caps = [c for c in req_caps if c.lower() not in covered_caps]
        for cap in missing_caps:
            # Check if recently added employee covers it
            if cap.lower() in covered_caps:
                continue
            task_spec = {"required_capabilities": [cap]}
            if department_preferences:
                task_spec["department"] = department_preferences[0]
            available_pool = [e for e in all_candidates if e.employee_id not in selected_ids]
            best = TaskMatcher.find_best_employee(task_spec, available_pool)
            if best:
                selected_employees.append(best)
                selected_ids.add(best.employee_id)
                covered_caps.update(c.lower() for c in best.capabilities)

        # 3. Ensure at least one member exists
        if not selected_employees:
            # Fallback: Pick top active & available employees with lightest workload
            active_pool = [e for e in all_candidates if e.is_active and e.availability == AVAILABILITY_AVAILABLE]
            active_pool.sort(key=lambda e: (getattr(e, "active_tasks", 0), -len(e.capabilities)))
            if active_pool:
                selected_employees.append(active_pool[0])
                selected_ids.add(active_pool[0].employee_id)

        # 4. Determine Lead Employee
        lead_id = None
        if lead_role:
            for emp in selected_employees:
                if emp.role.lower() == lead_role.lower():
                    lead_id = emp.employee_id
                    break

        if not lead_id:
            # Prioritize PM / Product Manager / Architect / Planner
            for emp in selected_employees:
                if emp.role.lower() in ("pm", "product_manager", "planner", "software_architect"):
                    lead_id = emp.employee_id
                    break

        if not lead_id and selected_employees:
            lead_id = selected_employees[0].employee_id

        team = ProjectTeam(
            team_id=team_id,
            project_id=proj_id,
            name=team_name,
            objective=objective,
            employee_ids=[e.employee_id for e in selected_employees],
            lead_employee_id=lead_id,
            status=TEAM_ACTIVE,
            event_bus=event_bus,
        )

        if event_bus:
            event_bus.publish(
                Event(
                    event_type=EVENT_TEAM_CREATED,
                    project_id=proj_id,
                    agent_id=lead_id,
                    payload={
                        "team_id": team_id,
                        "name": team_name,
                        "member_count": len(team.employee_ids),
                        "members": team.employee_ids,
                        "lead": lead_id,
                    },
                )
            )

        return team

"""Token usage tracking and operational metrics for Aether Office Phase 6."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict

from events import (
    EventBus,
    Event,
    EVENT_USAGE_RECORDED,
)

logger = logging.getLogger("aether.usage")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class UsageRecord:
    organization_id: str = "aether_office"
    project_id: str = ""
    task_id: Optional[str] = None
    employee_id: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int = 1
    estimated_cost: float = 0.0
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "employee_id": self.employee_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "requests": self.requests,
            "estimated_cost": self.estimated_cost,
            "created_at": self.created_at,
        }


class UsageTracker:
    """Tracks token consumption and estimated computational costs across all dimensions."""

    def __init__(
        self,
        db: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        cost_calculator: Optional[Any] = None,
    ):
        self.db = db
        self.event_bus = event_bus
        self.cost_calculator = cost_calculator
        self._records: list[UsageRecord] = []

    def record_usage(
        self,
        project_id: str,
        task_id: Optional[str] = None,
        employee_id: Optional[str] = None,
        model: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        requests: int = 1,
        estimated_cost: Optional[float] = None,
        organization_id: str = "aether_office",
    ) -> UsageRecord:
        """Record model and token consumption."""
        total_tokens = input_tokens + output_tokens

        # Compute cost if not provided directly
        if estimated_cost is None:
            if self.cost_calculator and hasattr(self.cost_calculator, "calculate_cost"):
                estimated_cost = self.cost_calculator.calculate_cost(
                    model_name=model or "default",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            else:
                estimated_cost = 0.0

        rec = UsageRecord(
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            employee_id=employee_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            requests=requests,
            estimated_cost=round(estimated_cost, 6),
            created_at=_now_iso(),
        )
        self._records.append(rec)

        if self.db:
            self.db.save_usage_record(
                project_id=project_id,
                task_id=task_id,
                employee_id=employee_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                requests=requests,
                estimated_cost=rec.estimated_cost,
                organization_id=organization_id,
            )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_USAGE_RECORDED,
                    project_id=project_id,
                    task_id=task_id,
                    agent_id=employee_id,
                    payload=rec.to_dict(),
                )
            )
        return rec

    def get_project_usage(self, project_id: str) -> dict:
        """Get aggregate usage metrics for a project."""
        if self.db:
            return self.db.get_project_usage_summary(project_id)

        matching = [r for r in self._records if r.project_id == project_id]
        return {
            "total_input_tokens": sum(r.input_tokens for r in matching),
            "total_output_tokens": sum(r.output_tokens for r in matching),
            "total_tokens": sum(r.total_tokens for r in matching),
            "total_requests": sum(r.requests for r in matching),
            "total_cost": round(sum(r.estimated_cost for r in matching), 4),
        }

    def get_employee_usage(self, employee_id: str) -> dict:
        """Get aggregate usage metrics for an employee."""
        matching = [r for r in self._records if r.employee_id == employee_id]
        return {
            "total_input_tokens": sum(r.input_tokens for r in matching),
            "total_output_tokens": sum(r.output_tokens for r in matching),
            "total_tokens": sum(r.total_tokens for r in matching),
            "total_requests": sum(r.requests for r in matching),
            "total_cost": round(sum(r.estimated_cost for r in matching), 4),
        }

    def get_total_usage(self) -> dict:
        """Get office-wide aggregate usage metrics."""
        if self.db:
            return self.db.get_office_usage_summary()

        return {
            "total_input_tokens": sum(r.input_tokens for r in self._records),
            "total_output_tokens": sum(r.output_tokens for r in self._records),
            "total_tokens": sum(r.total_tokens for r in self._records),
            "total_requests": sum(r.requests for r in self._records),
            "total_cost": round(sum(r.estimated_cost for r in self._records), 4),
        }

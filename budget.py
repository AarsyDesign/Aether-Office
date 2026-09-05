"""Model pricing configuration and project budget tracking for Aether Office Phase 6."""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional, Any, Dict

from events import (
    EventBus,
    Event,
    EVENT_BUDGET_WARNING,
    EVENT_BUDGET_EXCEEDED,
)

logger = logging.getLogger("aether.budget")

# Standard pricing table: cost in USD per 1,000 tokens
DEFAULT_MODEL_PRICING = {
    "default": {"input_cost_per_1k": 0.0015, "output_cost_per_1k": 0.0020},
    "mock-model": {"input_cost_per_1k": 0.0010, "output_cost_per_1k": 0.0020},
    "gpt-4o": {"input_cost_per_1k": 0.0050, "output_cost_per_1k": 0.0150},
    "gpt-4o-mini": {"input_cost_per_1k": 0.00015, "output_cost_per_1k": 0.0006},
    "claude-3-5-sonnet": {"input_cost_per_1k": 0.0030, "output_cost_per_1k": 0.0150},
    "gemini-1.5-pro": {"input_cost_per_1k": 0.00125, "output_cost_per_1k": 0.0050},
    "gemini-1.5-flash": {"input_cost_per_1k": 0.000075, "output_cost_per_1k": 0.0003},
}


class BudgetManager:
    """Manages model cost calculation, project budgets, and enforcement of financial thresholds."""

    def __init__(
        self,
        db: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        pricing: Optional[dict] = None,
    ):
        self.db = db
        self.event_bus = event_bus
        self.pricing = pricing or dict(DEFAULT_MODEL_PRICING)
        self._budgets: dict[str, dict] = {}
        self._warnings_emitted: dict[str, set[int]] = {}  # project_id -> {80, 90, 100}
        self._load_from_db()

    def _load_from_db(self):
        if not self.db:
            return
        # Project budgets are synced on demand via get_project_budget

    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost using configured pricing rates."""
        rate = self.pricing.get(model_name) or self.pricing.get("default", {"input_cost_per_1k": 0.0015, "output_cost_per_1k": 0.0020})
        input_cost = (input_tokens / 1000.0) * rate.get("input_cost_per_1k", 0.0015)
        output_cost = (output_tokens / 1000.0) * rate.get("output_cost_per_1k", 0.0020)
        return round(input_cost + output_cost, 6)

    def set_project_budget(
        self,
        project_id: str,
        budget: float,
        warning_threshold: float = 0.8,
    ) -> dict:
        """Assign budget limit to a project."""
        cur = self.get_project_budget(project_id)
        spent = cur.get("spent", 0.0)
        is_blocked = 1 if (budget > 0.0 and spent >= budget) else 0

        data = {
            "project_id": project_id,
            "budget": float(budget),
            "spent": float(spent),
            "remaining": max(0.0, float(budget) - float(spent)) if budget > 0.0 else float("inf"),
            "warning_threshold": float(warning_threshold),
            "is_blocked": bool(is_blocked),
        }
        self._budgets[project_id] = data

        if self.db:
            self.db.save_project_budget(
                project_id=project_id,
                budget=budget,
                spent=spent,
                warning_threshold=warning_threshold,
                is_blocked=is_blocked,
            )
        return data

    def get_project_budget(self, project_id: str) -> dict:
        """Retrieve current budget state for a project."""
        if self.db:
            db_rec = self.db.get_project_budget(project_id)
            if db_rec:
                b = float(db_rec.get("budget", 0.0))
                s = float(db_rec.get("spent", 0.0))
                return {
                    "project_id": project_id,
                    "budget": b,
                    "spent": s,
                    "remaining": max(0.0, b - s) if b > 0.0 else float("inf"),
                    "warning_threshold": float(db_rec.get("warning_threshold", 0.8)),
                    "is_blocked": bool(db_rec.get("is_blocked", 0)),
                }

        if project_id in self._budgets:
            return self._budgets[project_id]

        # Default empty budget
        return {
            "project_id": project_id,
            "budget": 0.0,
            "spent": 0.0,
            "remaining": float("inf"),
            "warning_threshold": 0.8,
            "is_blocked": False,
        }

    def can_spend(self, project_id: str, estimated_amount: float = 0.0) -> bool:
        """Verify if project has sufficient remaining budget to execute work."""
        b_info = self.get_project_budget(project_id)
        budget = b_info["budget"]
        spent = b_info["spent"]

        if budget <= 0.0:
            return True  # Unbounded budget

        return (spent + estimated_amount) <= budget

    def is_blocked(self, project_id: str) -> bool:
        """Check if project is currently blocked due to budget exhaustion."""
        b_info = self.get_project_budget(project_id)
        return bool(b_info.get("is_blocked", False))


    def record_expense(self, project_id: str, amount: float) -> dict:
        """Apply an expense to a project, checking warning thresholds and budget ceilings."""
        b_info = self.get_project_budget(project_id)
        budget = b_info["budget"]
        new_spent = b_info["spent"] + amount
        remaining = max(0.0, budget - new_spent) if budget > 0.0 else float("inf")
        is_blocked = (budget > 0.0 and new_spent >= budget)

        updated_info = {
            "project_id": project_id,
            "budget": budget,
            "spent": round(new_spent, 6),
            "remaining": round(remaining, 6),
            "warning_threshold": b_info.get("warning_threshold", 0.8),
            "is_blocked": is_blocked,
        }
        self._budgets[project_id] = updated_info

        if self.db:
            self.db.update_project_budget_spent(project_id, amount)

        # Threshold checking & event dispatch
        if budget > 0.0:
            ratio = new_spent / budget
            emitted = self._warnings_emitted.setdefault(project_id, set())

            if is_blocked and 100 not in emitted:
                emitted.add(100)
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_BUDGET_EXCEEDED,
                            project_id=project_id,
                            payload={
                                "project_id": project_id,
                                "budget": budget,
                                "spent": updated_info["spent"],
                                "remaining": 0.0,
                                "reason": "Budget limit exceeded. Project blocked.",
                            },
                        )
                    )
            elif ratio >= 0.9 and 90 not in emitted:
                emitted.add(90)
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_BUDGET_WARNING,
                            project_id=project_id,
                            payload={
                                "project_id": project_id,
                                "budget": budget,
                                "spent": updated_info["spent"],
                                "threshold": 0.90,
                                "message": f"Project budget reached 90%: ${updated_info['spent']:.2f} / ${budget:.2f}",
                            },
                        )
                    )
            elif ratio >= updated_info["warning_threshold"] and 80 not in emitted:
                emitted.add(80)
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_BUDGET_WARNING,
                            project_id=project_id,
                            payload={
                                "project_id": project_id,
                                "budget": budget,
                                "spent": updated_info["spent"],
                                "threshold": updated_info["warning_threshold"],
                                "message": f"Project budget reached {int(updated_info['warning_threshold']*100)}%: ${updated_info['spent']:.2f} / ${budget:.2f}",
                            },
                        )
                    )

        return updated_info

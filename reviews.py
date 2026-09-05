"""Peer Review System and Review Router for Aether Office."""

from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict
from workforce import Organization, Employee
from matcher import TaskMatcher
from events import EventBus, Event, EVENT_REVIEW_REQUESTED, EVENT_REVIEW_COMPLETED

logger = logging.getLogger("aether.reviews")

REVIEW_PENDING = "PENDING"
REVIEW_APPROVED = "APPROVED"
REVIEW_CHANGES_REQUESTED = "CHANGES_REQUESTED"
REVIEW_REJECTED = "REJECTED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Review:
    """Formal evaluation of a work artifact by a qualified peer reviewer."""

    review_id: str
    artifact_id: str
    task_id: str
    reviewer_employee_id: str
    author_employee_id: str
    project_id: str = "project"
    status: str = REVIEW_PENDING
    score: float = 0.0
    feedback: str = ""
    required_changes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    event_bus: Optional[EventBus] = field(default=None, repr=False)

    def approve(self, score: float = 1.0, feedback: str = "Approved. All criteria satisfied.") -> bool:
        """Approve the artifact."""
        self.status = REVIEW_APPROVED
        self.score = score
        self.feedback = feedback
        self.required_changes = []
        self.updated_at = _now_iso()
        self._emit_completed()
        return True

    def request_changes(self, feedback: str, required_changes: list[str], score: float = 0.5) -> bool:
        """Request revisions on the artifact."""
        self.status = REVIEW_CHANGES_REQUESTED
        self.score = score
        self.feedback = feedback
        self.required_changes = list(required_changes)
        self.updated_at = _now_iso()
        self._emit_completed()
        return True

    def reject(self, feedback: str, score: float = 0.0) -> bool:
        """Reject the artifact."""
        self.status = REVIEW_REJECTED
        self.score = score
        self.feedback = feedback
        self.required_changes = []
        self.updated_at = _now_iso()
        self._emit_completed()
        return True

    def _emit_completed(self) -> None:
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_REVIEW_COMPLETED,
                    project_id=self.project_id,
                    task_id=self.task_id,
                    agent_id=self.reviewer_employee_id,
                    status=self.status,
                    payload={
                        "review_id": self.review_id,
                        "artifact_id": self.artifact_id,
                        "status": self.status,
                        "score": self.score,
                        "feedback": self.feedback,
                        "required_changes": self.required_changes,
                    },
                )
            )

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "artifact_id": self.artifact_id,
            "task_id": self.task_id,
            "reviewer_employee_id": self.reviewer_employee_id,
            "author_employee_id": self.author_employee_id,
            "project_id": self.project_id,
            "status": self.status,
            "score": self.score,
            "feedback": self.feedback,
            "required_changes": list(self.required_changes),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict, event_bus: Optional[EventBus] = None) -> Review:
        return cls(
            review_id=d.get("review_id") or str(uuid.uuid4()),
            artifact_id=d.get("artifact_id", ""),
            task_id=d.get("task_id", ""),
            reviewer_employee_id=d.get("reviewer_employee_id", ""),
            author_employee_id=d.get("author_employee_id", ""),
            project_id=d.get("project_id", "project"),
            status=d.get("status", REVIEW_PENDING),
            score=float(d.get("score", 0.0)),
            feedback=d.get("feedback", ""),
            required_changes=list(d.get("required_changes", [])),
            metadata=dict(d.get("metadata", {})),
            created_at=d.get("created_at", _now_iso()),
            updated_at=d.get("updated_at", _now_iso()),
            event_bus=event_bus,
        )


class ReviewRouter:
    """Routes artifacts to the most competent reviewer based on role and capability pairings."""

    ROLE_PAIRINGS = {
        "developer": ["qa", "qa_engineer"],
        "backend_developer": ["qa", "qa_engineer", "security_engineer"],
        "frontend_developer": ["qa", "qa_engineer", "ux_designer"],
        "copywriter": ["content_strategist", "marketing_strategist", "product_manager", "pm"],
        "ui_designer": ["ux_designer", "product_manager", "pm"],
        "ux_designer": ["product_manager", "pm"],
        "seo_specialist": ["marketing_strategist", "content_strategist", "pm"],
        "data_engineer": ["qa_engineer", "software_architect", "backend_developer"],
    }

    @classmethod
    def select_reviewer(
        cls,
        author: Employee,
        candidate_pool: list[Employee],
        task: Optional[dict] = None,
    ) -> Optional[Employee]:
        """Select the best qualified peer reviewer, ensuring author cannot review their own work."""
        eligible = [c for c in candidate_pool if c.employee_id != author.employee_id and c.is_active]
        if not eligible:
            return None

        preferred_review_roles = cls.ROLE_PAIRINGS.get(author.role.lower(), [])
        # 1. Try to find candidate with preferred review role
        for target_role in preferred_review_roles:
            task_spec = {"role": target_role, "required_capabilities": ["code_review", "automated_testing", "content_planning"]}
            best = TaskMatcher.find_best_employee(task_spec, eligible)
            if best:
                return best

        # 2. Match by capabilities (review, verification, testing)
        task_spec = {"required_capabilities": ["code_review", "automated_testing", "test_runner", "task_breakdown"]}
        best = TaskMatcher.find_best_employee(task_spec, eligible)
        if best:
            return best

        # 3. Fallback: Eligible peer with lowest workload
        eligible.sort(key=lambda e: (getattr(e, "active_tasks", 0), -len(e.capabilities)))
        return eligible[0]

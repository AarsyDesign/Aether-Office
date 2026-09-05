"""Explicit Handoff System for transferring artifacts and context between employees."""

from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict
from events import EventBus, Event, EVENT_ARTIFACT_HANDOFF
from artifacts import Artifact, ArtifactStore

logger = logging.getLogger("aether.handoff")

HANDOFF_CREATED = "CREATED"
HANDOFF_RECEIVED = "RECEIVED"
HANDOFF_ACCEPTED = "ACCEPTED"
HANDOFF_REJECTED = "REJECTED"

VALID_HANDOFF_TRANSITIONS = {
    HANDOFF_CREATED: [HANDOFF_RECEIVED, HANDOFF_REJECTED],
    HANDOFF_RECEIVED: [HANDOFF_ACCEPTED, HANDOFF_REJECTED],
    HANDOFF_ACCEPTED: [],
    HANDOFF_REJECTED: [HANDOFF_CREATED],  # Can be revised/resubmitted
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Handoff:
    """Formal artifact and context handoff between employees across task dependencies."""

    handoff_id: str
    from_employee_id: str
    to_employee_id: str
    task_id: str
    project_id: str
    artifact_ids: list[str] = field(default_factory=list)
    message: str = ""
    status: str = HANDOFF_CREATED
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    event_bus: Optional[EventBus] = field(default=None, repr=False)

    def receive(self) -> bool:
        """Mark handoff as received by the recipient employee."""
        if self.status not in (HANDOFF_CREATED, HANDOFF_REJECTED):
            raise ValueError(f"Cannot transition handoff {self.handoff_id} to RECEIVED from {self.status}")
        self.status = HANDOFF_RECEIVED
        self.updated_at = _now_iso()
        return True

    def accept(self) -> bool:
        """Accept the handoff artifacts and context."""
        if self.status != HANDOFF_RECEIVED:
            raise ValueError(f"Cannot accept handoff {self.handoff_id} when in state {self.status}")
        self.status = HANDOFF_ACCEPTED
        self.updated_at = _now_iso()
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_ARTIFACT_HANDOFF,
                    project_id=self.project_id,
                    task_id=self.task_id,
                    agent_id=self.to_employee_id,
                    payload={
                        "handoff_id": self.handoff_id,
                        "from_employee": self.from_employee_id,
                        "to_employee": self.to_employee_id,
                        "artifacts": self.artifact_ids,
                        "status": self.status,
                    },
                )
            )
        return True

    def reject(self, reason: str) -> bool:
        """Reject the handoff and provide feedback."""
        self.status = HANDOFF_REJECTED
        self.metadata["rejection_reason"] = reason
        self.updated_at = _now_iso()
        return True

    def get_artifact_context(self, artifact_store: ArtifactStore) -> str:
        """Bundle artifacts into an informative markdown summary for the receiver."""
        parts = [
            f"### Handoff from Employee `{self.from_employee_id}` to `{self.to_employee_id}`",
            f"**Message**: {self.message or 'No handoff notes provided.'}",
            "**Transferred Artifacts**:",
        ]
        for aid in self.artifact_ids:
            art = artifact_store.get_artifact(aid)
            if art:
                parts.append(
                    f"#### Artifact: {art.name} (Type: {art.type}, v{art.version})\n"
                    f"```\n{art.content}\n```"
                )
            else:
                parts.append(f"- Artifact `{aid}`: (Not found in store)")
        return "\n\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "handoff_id": self.handoff_id,
            "from_employee_id": self.from_employee_id,
            "to_employee_id": self.to_employee_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "artifact_ids": list(self.artifact_ids),
            "message": self.message,
            "status": self.status,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict, event_bus: Optional[EventBus] = None) -> Handoff:
        return cls(
            handoff_id=d.get("handoff_id") or str(uuid.uuid4()),
            from_employee_id=d.get("from_employee_id", ""),
            to_employee_id=d.get("to_employee_id", ""),
            task_id=d.get("task_id", ""),
            project_id=d.get("project_id", "project"),
            artifact_ids=list(d.get("artifact_ids", [])),
            message=d.get("message", ""),
            status=d.get("status", HANDOFF_CREATED),
            metadata=dict(d.get("metadata", {})),
            created_at=d.get("created_at", _now_iso()),
            updated_at=d.get("updated_at", _now_iso()),
            event_bus=event_bus,
        )


class HandoffManager:
    """Manages creation, storage, and retrieval of handoffs."""

    def __init__(self, db: Optional[Any] = None, event_bus: Optional[EventBus] = None):
        self.db = db
        self.event_bus = event_bus
        self._handoffs: dict[str, Handoff] = {}

    def create_handoff(
        self,
        from_employee_id: str,
        to_employee_id: str,
        task_id: str,
        project_id: str,
        artifact_ids: list[str],
        message: str = "",
    ) -> Handoff:
        """Create a new handoff and persist to DB/memory."""
        handoff_id = f"handoff_{uuid.uuid4().hex[:8]}"
        handoff = Handoff(
            handoff_id=handoff_id,
            from_employee_id=from_employee_id,
            to_employee_id=to_employee_id,
            task_id=task_id,
            project_id=project_id,
            artifact_ids=artifact_ids,
            message=message,
            status=HANDOFF_CREATED,
            event_bus=self.event_bus,
        )
        self._handoffs[handoff_id] = handoff

        if self.db and hasattr(self.db, "save_handoff"):
            self.db.save_handoff(
                handoff_id=handoff.handoff_id,
                from_employee_id=handoff.from_employee_id,
                to_employee_id=handoff.to_employee_id,
                task_id=handoff.task_id,
                project_id=handoff.project_id,
                artifact_ids=handoff.artifact_ids,
                message=handoff.message,
                status=handoff.status,
            )

        return handoff

    def get_handoff(self, handoff_id: str) -> Optional[Handoff]:
        """Fetch handoff by ID."""
        if handoff_id in self._handoffs:
            return self._handoffs[handoff_id]
        if self.db and hasattr(self.db, "get_handoff"):
            data = self.db.get_handoff(handoff_id)
            if data:
                h = Handoff.from_dict(data, event_bus=self.event_bus)
                self._handoffs[h.handoff_id] = h
                return h
        return None

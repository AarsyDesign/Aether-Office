"""Structured Task-Bounded Internal Communication for Aether Office."""

from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict
from events import EventBus, Event, EVENT_DISCUSSION_STARTED, EVENT_DISCUSSION_MESSAGE

logger = logging.getLogger("aether.discussion")

# Structured Message Types
MSG_QUESTION = "QUESTION"
MSG_ANSWER = "ANSWER"
MSG_REQUEST = "REQUEST"
MSG_CLARIFICATION = "CLARIFICATION"
MSG_DECISION = "DECISION"
MSG_WARNING = "WARNING"
MSG_HANDOFF = "HANDOFF"
MSG_REVIEW_FEEDBACK = "REVIEW_FEEDBACK"

ALL_MESSAGE_TYPES = {
    MSG_QUESTION,
    MSG_ANSWER,
    MSG_REQUEST,
    MSG_CLARIFICATION,
    MSG_DECISION,
    MSG_WARNING,
    MSG_HANDOFF,
    MSG_REVIEW_FEEDBACK,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DiscussionMessage:
    """A single structured message exchanged between virtual office employees."""

    message_id: str
    discussion_id: str
    sender_employee_id: str
    content: str
    recipient_employee_id: Optional[str] = None
    task_id: Optional[str] = None
    message_type: str = MSG_QUESTION
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "discussion_id": self.discussion_id,
            "sender_employee_id": self.sender_employee_id,
            "recipient_employee_id": self.recipient_employee_id,
            "task_id": self.task_id,
            "message_type": self.message_type,
            "content": self.content,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DiscussionMessage:
        return cls(
            message_id=d.get("message_id") or str(uuid.uuid4()),
            discussion_id=d.get("discussion_id", ""),
            sender_employee_id=d.get("sender_employee_id", ""),
            recipient_employee_id=d.get("recipient_employee_id"),
            task_id=d.get("task_id"),
            message_type=d.get("message_type", MSG_QUESTION),
            content=d.get("content", ""),
            created_at=d.get("created_at", _now_iso()),
        )


@dataclass
class Discussion:
    """Project- or Task-bounded structured discussion thread."""

    discussion_id: str
    project_id: str
    topic: str
    task_id: Optional[str] = None
    status: str = "OPEN"
    messages: list[DiscussionMessage] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    event_bus: Optional[EventBus] = field(default=None, repr=False)

    def add_message(
        self,
        sender_employee_id: str,
        content: str,
        message_type: str = MSG_QUESTION,
        recipient_employee_id: Optional[str] = None,
    ) -> DiscussionMessage:
        """Add a structured message to this thread and emit event."""
        if message_type not in ALL_MESSAGE_TYPES:
            raise ValueError(f"Invalid message type '{message_type}'. Must be one of {ALL_MESSAGE_TYPES}")

        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        msg = DiscussionMessage(
            message_id=msg_id,
            discussion_id=self.discussion_id,
            sender_employee_id=sender_employee_id,
            recipient_employee_id=recipient_employee_id,
            task_id=self.task_id,
            message_type=message_type,
            content=content,
            created_at=_now_iso(),
        )
        self.messages.append(msg)
        self.updated_at = _now_iso()

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_DISCUSSION_MESSAGE,
                    project_id=self.project_id,
                    task_id=self.task_id,
                    agent_id=sender_employee_id,
                    payload={
                        "discussion_id": self.discussion_id,
                        "message_id": msg_id,
                        "message_type": message_type,
                        "sender": sender_employee_id,
                        "recipient": recipient_employee_id,
                        "preview": content[:120],
                    },
                )
            )

        return msg

    def resolve(self) -> None:
        """Mark the discussion thread as resolved."""
        self.status = "RESOLVED"
        self.updated_at = _now_iso()

    def to_dict(self) -> dict:
        return {
            "discussion_id": self.discussion_id,
            "project_id": self.project_id,
            "topic": self.topic,
            "task_id": self.task_id,
            "status": self.status,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict, event_bus: Optional[EventBus] = None) -> Discussion:
        msgs = [DiscussionMessage.from_dict(m) for m in d.get("messages", [])]
        return cls(
            discussion_id=d.get("discussion_id") or str(uuid.uuid4()),
            project_id=d.get("project_id", "project"),
            topic=d.get("topic", "Task Discussion"),
            task_id=d.get("task_id"),
            status=d.get("status", "OPEN"),
            messages=msgs,
            created_at=d.get("created_at", _now_iso()),
            updated_at=d.get("updated_at", _now_iso()),
            event_bus=event_bus,
        )

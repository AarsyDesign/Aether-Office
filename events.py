"""Generic Event Envelope, EventBus, and Streaming Abstraction for Aether Office."""

from __future__ import annotations
import uuid
import queue
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Any, Optional, Generator

logger = logging.getLogger("aether.events")

# --- Standard Event Types ---
EVENT_AGENT_REGISTERED = "agent_registered"
EVENT_AGENT_STATE_CHANGED = "agent_state_changed"
EVENT_AGENT_STARTED = "agent_started"
EVENT_AGENT_PROGRESS = "agent_progress"
EVENT_AGENT_WAITING = "agent_waiting"
EVENT_AGENT_RETRY = "agent_retry"
EVENT_AGENT_COMPLETED = "agent_completed"
EVENT_AGENT_FAILED = "agent_failed"

EVENT_TASK_CREATED = "task_created"
EVENT_TASK_STARTED = "task_started"
EVENT_TASK_PROGRESS = "task_progress"
EVENT_TASK_COMPLETED = "task_completed"
EVENT_TASK_FAILED = "task_failed"

EVENT_ARTIFACT_CREATED = "artifact_created"
EVENT_ARTIFACT_UPDATED = "artifact_updated"

EVENT_PIPELINE_STARTED = "pipeline_started"
EVENT_PIPELINE_PROGRESS = "pipeline_progress"
EVENT_PIPELINE_COMPLETED = "pipeline_completed"
EVENT_PIPELINE_FAILED = "pipeline_failed"

# Developer & QA Specific
EVENT_DEV_PLAN_CREATED = "developer_plan_created"
EVENT_DEV_UNIT_STARTED = "developer_unit_started"
EVENT_DEV_UNIT_RETRY = "developer_unit_retry"
EVENT_DEV_UNIT_VALIDATED = "developer_unit_validated"
EVENT_DEV_UNIT_COMPLETED = "developer_unit_completed"
EVENT_DEV_UNIT_FAILED = "developer_unit_failed"
EVENT_DEV_GEN_COMPLETED = "developer_generation_completed"
EVENT_DEV_GEN_FAILED = "developer_generation_failed"

EVENT_QA_TEST_STARTED = "qa_test_started"
EVENT_QA_TEST_PASSED = "qa_test_passed"
EVENT_QA_TEST_FAILED = "qa_test_failed"
EVENT_QA_COMPLETED = "qa_completed"

# Organization & Workforce Specific (Phase 4)
EVENT_EMPLOYEE_HIRED = "employee_hired"
EVENT_EMPLOYEE_ACTIVATED = "employee_activated"
EVENT_EMPLOYEE_DEACTIVATED = "employee_deactivated"
EVENT_EMPLOYEE_UPDATED = "employee_updated"
EVENT_ROLE_REGISTERED = "role_registered"
EVENT_DEPARTMENT_REGISTERED = "department_registered"
EVENT_TASK_ASSIGNED = "task_assigned"
EVENT_TASK_UNASSIGNED = "task_unassigned"

# Team Collaboration & Task Delegation (Phase 5)
EVENT_TEAM_CREATED = "team_created"
EVENT_TEAM_MEMBER_ADDED = "team_member_added"
EVENT_TEAM_MEMBER_REMOVED = "team_member_removed"
EVENT_TASK_DECOMPOSED = "task_decomposed"
EVENT_TASK_BLOCKED = "task_blocked"
EVENT_ARTIFACT_HANDOFF = "artifact_handoff"
EVENT_REVIEW_REQUESTED = "review_requested"
EVENT_REVIEW_COMPLETED = "review_completed"
EVENT_DISCUSSION_STARTED = "discussion_started"
EVENT_DISCUSSION_MESSAGE = "discussion_message"
EVENT_DELEGATION_COMPLETED = "delegation_completed"
EVENT_WORKFLOW_COMPLETED = "workflow_completed"
EVENT_WORKFLOW_FAILED = "workflow_failed"
EVENT_EMPLOYEE_REASSIGNED = "employee_reassigned"

# Autonomous Operations & Multi-Project Scheduling (Phase 6)
EVENT_PROJECT_CREATED = "project_created"
EVENT_PROJECT_STARTED = "project_started"
EVENT_PROJECT_PAUSED = "project_paused"
EVENT_PROJECT_RESUMED = "project_resumed"
EVENT_PROJECT_COMPLETED = "project_completed"
EVENT_PROJECT_FAILED = "project_failed"

EVENT_TASK_QUEUED = "task_queued"
EVENT_TASK_DEQUEUED = "task_dequeued"
EVENT_TASK_SCHEDULED = "task_scheduled"
EVENT_TASK_PREEMPTED = "task_preempted"

EVENT_EMPLOYEE_RESERVED = "employee_reserved"
EVENT_EMPLOYEE_RELEASED = "employee_released"
EVENT_EMPLOYEE_OVERLOADED = "employee_overloaded"

EVENT_SCHEDULE_TICK = "schedule_tick"
EVENT_RESOURCE_CONFLICT = "resource_conflict"

EVENT_USAGE_RECORDED = "usage_recorded"
EVENT_BUDGET_WARNING = "budget_warning"
EVENT_BUDGET_EXCEEDED = "budget_exceeded"

EVENT_OFFICE_STATE_CHANGED = "office_state_changed"

# Phase 7: Persistent Runtime Engine & Worker Observability
EVENT_RUNTIME_STARTED = "runtime_started"
EVENT_RUNTIME_STOPPED = "runtime_stopped"
EVENT_SCHEDULER_TICK_STARTED = "scheduler_tick_started"
EVENT_SCHEDULER_TICK_COMPLETED = "scheduler_tick_completed"
EVENT_TASK_DISPATCHED = "task_dispatched"
EVENT_WORKER_RESERVED = "worker_reserved"
EVENT_WORKER_RELEASED = "worker_released"

# Phase 8: Objective-to-Outcome Engine
EVENT_OBJECTIVE_CREATED = "objective_created"
EVENT_OBJECTIVE_PLANNING_STARTED = "objective_planning_started"
EVENT_OBJECTIVE_PLAN_CREATED = "objective_plan_created"
EVENT_OBJECTIVE_PLAN_FAILED = "objective_plan_failed"
EVENT_OBJECTIVE_STARTED = "objective_started"
EVENT_OBJECTIVE_EVALUATION_STARTED = "objective_evaluation_started"
EVENT_OBJECTIVE_REVISION_REQUESTED = "objective_revision_requested"
EVENT_OBJECTIVE_COMPLETED = "objective_completed"
EVENT_OBJECTIVE_FAILED = "objective_failed"

# Phase 9: Adaptive Planning & Intelligence
EVENT_OBJECTIVE_ANALYSIS_STARTED = "objective_analysis_started"
EVENT_OBJECTIVE_ANALYZED = "objective_analyzed"
EVENT_PLANNING_STRATEGY_SELECTED = "planning_strategy_selected"
EVENT_PLAN_GENERATED = "plan_generated"
EVENT_PLAN_VALIDATED = "plan_validated"
EVENT_PLAN_QUALITY_EVALUATED = "plan_quality_evaluated"
EVENT_PLAN_OPTIMIZATION_STARTED = "plan_optimization_started"
EVENT_PLAN_OPTIMIZATION_COMPLETED = "plan_optimization_completed"
EVENT_CLARIFICATION_REQUIRED = "clarification_required"
EVENT_MILESTONE_EVALUATION_STARTED = "milestone_evaluation_started"
EVENT_MILESTONE_GATE_PASSED = "milestone_gate_passed"
EVENT_MILESTONE_GATE_FAILED = "milestone_gate_failed"




def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Event:
    """Standard generic event envelope across the entire Aether Office platform."""
    event_type: str
    project_id: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=_now_iso)
    task_id: Optional[int | str] = None
    agent_id: Optional[str] = None
    agent_role: Optional[str] = None
    status: Optional[str] = None
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "event_type": self.event_type,
            "status": self.status,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Event:
        return cls(
            event_id=d.get("event_id", str(uuid.uuid4())),
            timestamp=d.get("timestamp", _now_iso()),
            project_id=d.get("project_id", ""),
            task_id=d.get("task_id"),
            agent_id=d.get("agent_id"),
            agent_role=d.get("agent_role"),
            event_type=d.get("event_type", "unknown"),
            status=d.get("status"),
            payload=d.get("payload", {}) or {},
            metadata=d.get("metadata", {}) or {},
        )


class EventBus:
    """Thread-safe in-memory publish/subscribe event bus with isolated subscriber errors."""

    def __init__(self):
        self._subscribers: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        self.subscriber_errors: list[dict] = []

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        """Register a subscriber handler."""
        with self._lock:
            if handler not in self._subscribers:
                self._subscribers.append(handler)

    def unsubscribe(self, handler: Callable[[Event], None]) -> None:
        """Unregister a subscriber handler."""
        with self._lock:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers. Subscriber exceptions are isolated."""
        with self._lock:
            handlers = list(self._subscribers)

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                err_record = {
                    "event_id": event.event_id,
                    "handler": getattr(handler, "__name__", str(handler)),
                    "error": str(e),
                }
                self.subscriber_errors.append(err_record)
                logger.error(f"EventBus subscriber error in {err_record['handler']}: {e}", exc_info=True)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


class Stream:
    """Generic stream abstraction over an EventBus.
    Can be used by live CLI, WebSocket, SSE, and frontend UIs.
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or EventBus()
        self._queue: queue.Queue[Optional[Event]] = queue.Queue()
        self._closed = False
        self._lock = threading.Lock()

        # Connect stream internal queue to bus
        self.event_bus.subscribe(self._on_bus_event)

    def _on_bus_event(self, event: Event) -> None:
        with self._lock:
            if not self._closed:
                self._queue.put(event)

    def publish(self, event: Event) -> None:
        """Publish event via the underlying bus."""
        self.event_bus.publish(event)

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        """Register an active callback handler on the bus."""
        self.event_bus.subscribe(handler)

    def unsubscribe(self, handler: Callable[[Event], None]) -> None:
        """Unregister a callback handler from the bus."""
        self.event_bus.unsubscribe(handler)

    def iter_events(self, timeout: Optional[float] = None) -> Generator[Event, None, None]:
        """Yield events from queue until closed or timeout."""
        while True:
            with self._lock:
                if self._closed and self._queue.empty():
                    break
            try:
                item = self._queue.get(timeout=timeout)
                if item is None:  # Sentinel indicating close
                    break
                yield item
            except queue.Empty:
                break

    def close(self) -> None:
        """Close stream and detach from bus."""
        with self._lock:
            if not self._closed:
                self._closed = True
                self._queue.put(None)  # Sentinel to unblock iter_events
        self.event_bus.unsubscribe(self._on_bus_event)


def format_cli_event(event: Event) -> Optional[str]:
    """Format an event into the real-time CLI progress line."""
    try:
        if event.timestamp:
            ts_str = event.timestamp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            time_str = dt.strftime("%H:%M:%S")
        else:
            time_str = datetime.now().strftime("%H:%M:%S")
    except Exception:
        time_str = datetime.now().strftime("%H:%M:%S")

    role = (event.agent_role or "SYSTEM").upper().ljust(11)

    if event.event_type == EVENT_AGENT_STATE_CHANGED:
        payload = event.payload or {}
        state = (event.status or payload.get("state", "")).upper()
        unit = payload.get("unit")
        progress = payload.get("progress")
        verdict = payload.get("verdict")

        if unit and progress:
            return f"{time_str}  {role} {unit:<13} {progress}"
        elif unit and state == "RETRYING":
            return f"{time_str}  {role} {unit:<13} RETRY"
        elif role.strip() == "QA" and verdict:
            return f"{time_str}  {role} {verdict}"
        elif state in ("THINKING", "PLANNING", "WORKING", "TESTING", "COMPLETED", "FAILED", "WAITING", "BLOCKED"):
            return f"{time_str}  {role} {state}"
        return f"{time_str}  {role} {state}"

    elif event.event_type in (EVENT_PIPELINE_COMPLETED, "pipeline.completed"):
        return "\nPROJECT COMPLETE"
    elif event.event_type in (EVENT_PIPELINE_FAILED, "pipeline.failed"):
        return "\nPROJECT FAILED"

    return None


class CLIProgressStreamer:
    """Subscribes to stream or event bus and prints real-time formatted events."""

    def __init__(self, print_fn=print):
        self.print_fn = print_fn
        self._last_role = None
        self._header_printed = False

    def on_event(self, event: Event) -> None:
        line = format_cli_event(event)
        if not line:
            return

        if not self._header_printed:
            self.print_fn("\n[AETHER OFFICE]\n")
            self._header_printed = True

        current_role = event.agent_role or "SYSTEM"
        if self._last_role and current_role != self._last_role and not line.startswith("\n"):
            self.print_fn("")

        self.print_fn(line)
        self._last_role = current_role

"""Aether Office to PixelOffice Event Bridge.

Translates internal Aether Office EventBus events into the canonical PixelOffice
AgentEvent protocol and emits them over UDP (127.0.0.1:9997) and HTTP (http://127.0.0.1:3003/api/events).
Fail-open design: If PixelOffice is not running, emissions fail silently without
interrupting Aether Office execution.
"""

from __future__ import annotations

import os
import time
import json
import socket
import logging
import threading
from typing import Optional, Dict, Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from events import (
    Event,
    EventBus,
    EVENT_AGENT_STATE_CHANGED,
    EVENT_AGENT_STARTED,
    EVENT_AGENT_WAITING,
    EVENT_AGENT_RETRY,
    EVENT_AGENT_COMPLETED,
    EVENT_AGENT_FAILED,
    EVENT_TASK_STARTED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_DEV_UNIT_STARTED,
    EVENT_DEV_UNIT_RETRY,
    EVENT_DEV_UNIT_COMPLETED,
    EVENT_DEV_UNIT_FAILED,
    EVENT_QA_TEST_STARTED,
    EVENT_QA_TEST_PASSED,
    EVENT_QA_TEST_FAILED,
    EVENT_OBJECTIVE_PLANNING_STARTED,
    EVENT_OBJECTIVE_ANALYSIS_STARTED,
    EVENT_OBJECTIVE_COMPLETED,
    EVENT_OBJECTIVE_FAILED,
    EVENT_PIPELINE_COMPLETED,
    EVENT_PIPELINE_FAILED,
)

logger = logging.getLogger("aether.pixel_bridge")

# PixelOffice Canonical States
PIXEL_STATE_IDLE = "idle"
PIXEL_STATE_THINKING = "thinking"
PIXEL_STATE_PLANNING = "planning"
PIXEL_STATE_RESEARCHING = "researching"
PIXEL_STATE_CODING = "coding"
PIXEL_STATE_RUNNING = "running"
PIXEL_STATE_WAITING = "waiting"
PIXEL_STATE_SUCCESS = "success"
PIXEL_STATE_FAILURE = "failure"

VALID_PIXEL_STATES = {
    PIXEL_STATE_IDLE,
    PIXEL_STATE_THINKING,
    PIXEL_STATE_PLANNING,
    PIXEL_STATE_RESEARCHING,
    PIXEL_STATE_CODING,
    PIXEL_STATE_RUNNING,
    PIXEL_STATE_WAITING,
    PIXEL_STATE_SUCCESS,
    PIXEL_STATE_FAILURE,
}

# Aether agent status to PixelOffice state mapping
AETHER_TO_PIXEL_STATE: Dict[str, str] = {
    "IDLE": PIXEL_STATE_IDLE,
    "THINKING": PIXEL_STATE_THINKING,
    "PLANNING": PIXEL_STATE_PLANNING,
    "WORKING": PIXEL_STATE_CODING,
    "RETRYING": PIXEL_STATE_CODING,
    "TESTING": PIXEL_STATE_RUNNING,
    "WAITING": PIXEL_STATE_WAITING,
    "BLOCKED": PIXEL_STATE_WAITING,
    "COMPLETED": PIXEL_STATE_SUCCESS,
    "FAILED": PIXEL_STATE_FAILURE,
}

# Specific event types override mapping
EVENT_TYPE_TO_PIXEL_STATE: Dict[str, str] = {
    EVENT_DEV_UNIT_STARTED: PIXEL_STATE_CODING,
    EVENT_DEV_UNIT_RETRY: PIXEL_STATE_CODING,
    EVENT_DEV_UNIT_COMPLETED: PIXEL_STATE_SUCCESS,
    EVENT_DEV_UNIT_FAILED: PIXEL_STATE_FAILURE,
    EVENT_QA_TEST_STARTED: PIXEL_STATE_RUNNING,
    EVENT_QA_TEST_PASSED: PIXEL_STATE_SUCCESS,
    EVENT_QA_TEST_FAILED: PIXEL_STATE_FAILURE,
    EVENT_OBJECTIVE_PLANNING_STARTED: PIXEL_STATE_PLANNING,
    EVENT_OBJECTIVE_ANALYSIS_STARTED: PIXEL_STATE_RESEARCHING,
    EVENT_OBJECTIVE_COMPLETED: PIXEL_STATE_SUCCESS,
    EVENT_OBJECTIVE_FAILED: PIXEL_STATE_FAILURE,
    EVENT_PIPELINE_COMPLETED: PIXEL_STATE_SUCCESS,
    EVENT_PIPELINE_FAILED: PIXEL_STATE_FAILURE,
    EVENT_TASK_COMPLETED: PIXEL_STATE_SUCCESS,
    EVENT_TASK_FAILED: PIXEL_STATE_FAILURE,
    EVENT_AGENT_WAITING: PIXEL_STATE_WAITING,
    EVENT_AGENT_FAILED: PIXEL_STATE_FAILURE,
    EVENT_AGENT_COMPLETED: PIXEL_STATE_SUCCESS,
}


def map_aether_event_to_pixel(event: Event) -> Optional[Dict[str, Any]]:
    """Convert an Aether Event into a PixelOffice AgentEvent dictionary.
    
    PixelOffice schema:
    {
        "version": 1,
        "provider": "aether",
        "sessionId": "<project_id>",
        "agentId": "<agent_id>",
        "projectId": "<cwd>",
        "projectLabel": "<label>",
        "kind": "upsert",
        "state": "coding",
        "activity": "<activity>",
        "occurredAt": 1785452400000
    }
    """
    # 1. Determine Agent ID
    agent_id = event.agent_id or event.agent_role or "system"
    session_id = event.project_id or "aether_session"
    project_label = f"Aether: {session_id}" if session_id != "aether_session" else "Aether Office"

    # 2. Determine State
    pixel_state = PIXEL_STATE_IDLE
    if event.event_type in EVENT_TYPE_TO_PIXEL_STATE:
        pixel_state = EVENT_TYPE_TO_PIXEL_STATE[event.event_type]
    elif event.status and event.status.upper() in AETHER_TO_PIXEL_STATE:
        pixel_state = AETHER_TO_PIXEL_STATE[event.status.upper()]
    elif event.event_type == EVENT_AGENT_STATE_CHANGED:
        new_state = event.payload.get("state") or event.status or ""
        pixel_state = AETHER_TO_PIXEL_STATE.get(new_state.upper(), PIXEL_STATE_IDLE)
    elif event.event_type == EVENT_TASK_STARTED:
        pixel_state = PIXEL_STATE_CODING
    elif event.event_type == EVENT_AGENT_STARTED:
        pixel_state = PIXEL_STATE_THINKING
    else:
        # If not a state transition event, ignore
        return None

    # 3. Determine Activity Description
    activity = ""
    if event.payload.get("action"):
        activity = str(event.payload["action"])
    elif event.payload.get("title"):
        activity = str(event.payload["title"])
    elif event.payload.get("unit_id"):
        activity = f"File: {event.payload['unit_id']}"
    elif event.task_id:
        activity = f"Task: {event.task_id}"
    else:
        activity = event.event_type.replace("_", " ")

    # 4. Determine Kind (upsert, touch, end)
    kind = "upsert"
    if pixel_state in (PIXEL_STATE_SUCCESS, PIXEL_STATE_FAILURE) and event.event_type in (
        EVENT_PIPELINE_COMPLETED,
        EVENT_PIPELINE_FAILED,
        EVENT_OBJECTIVE_COMPLETED,
        EVENT_OBJECTIVE_FAILED,
    ):
        kind = "end"

    occurred_at = int(time.time() * 1000)

    return {
        "version": 1,
        "provider": "aether",
        "sessionId": str(session_id),
        "agentId": str(agent_id),
        "projectId": os.path.abspath("."),
        "projectLabel": str(project_label),
        "kind": kind,
        "state": pixel_state,
        "activity": activity[:60],
        "occurredAt": occurred_at,
    }


class PixelOfficeBridge:
    """Non-blocking, fail-open bridge that streams events to PixelOffice."""

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        udp_host: str = "127.0.0.1",
        udp_port: int = 9997,
        http_url: str = "http://127.0.0.1:3003/api/events",
        enabled: bool = True,
        use_http_fallback: bool = False,
    ):
        self.event_bus = event_bus
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.http_url = http_url
        self.enabled = enabled
        self.use_http_fallback = use_http_fallback

        self._udp_sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        """Initialize sockets and subscribe to event bus."""
        with self._lock:
            if self._started:
                return
            try:
                self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._udp_sock.setblocking(False)
            except Exception as e:
                logger.debug(f"Failed to create UDP socket for PixelOffice bridge: {e}")
                self._udp_sock = None

            if self.event_bus:
                self.event_bus.subscribe(self.on_event)
            self._started = True
            logger.info("PixelOffice bridge started.")

    def stop(self) -> None:
        """Clean up resources."""
        with self._lock:
            if not self._started:
                return
            if self.event_bus:
                self.event_bus.unsubscribe(self.on_event)
            if self._udp_sock:
                try:
                    self._udp_sock.close()
                except Exception:
                    pass
                self._udp_sock = None
            self._started = False

    @property
    def running(self) -> bool:
        return self._started

    @property
    def is_running(self) -> bool:
        return self._started

    def on_event(self, event: Event) -> None:
        """Callback for EventBus."""
        if not self.enabled:
            return
        payload = map_aether_event_to_pixel(event)
        if payload:
            self.send_payload(payload)

    def send_payload(self, payload: Dict[str, Any]) -> bool:
        """Send PixelOffice AgentEvent via UDP and optional HTTP."""
        raw_json = json.dumps(payload).encode("utf-8")
        sent = False

        # 1. UDP Datagram (Primary PixelOffice channel)
        if self._udp_sock:
            try:
                self._udp_sock.sendto(raw_json, (self.udp_host, self.udp_port))
                sent = True
            except Exception as e:
                logger.debug(f"UDP datagram failed (expected if PixelOffice closed): {e}")

        # 2. HTTP POST Fallback (Asynchronous)
        if self.use_http_fallback and HAS_REQUESTS:
            def _post_http():
                try:
                    requests.post(
                        self.http_url,
                        data=raw_json,
                        headers={"Content-Type": "application/json"},
                        timeout=0.2,
                    )
                except Exception:
                    pass

            threading.Thread(target=_post_http, daemon=True).start()

        return sent

    def emit_agent_state(
        self,
        agent_id: str,
        state: str,
        activity: str = "",
        session_id: str = "aether_session",
    ) -> bool:
        """Convenience method to manually dispatch an agent state update."""
        if state not in VALID_PIXEL_STATES:
            state = AETHER_TO_PIXEL_STATE.get(state.upper(), PIXEL_STATE_IDLE)

        payload = {
            "version": 1,
            "provider": "aether",
            "sessionId": str(session_id),
            "agentId": str(agent_id),
            "projectId": os.path.abspath("."),
            "projectLabel": "Aether Office",
            "kind": "upsert",
            "state": state,
            "activity": activity[:60],
            "occurredAt": int(time.time() * 1000),
        }
        return self.send_payload(payload)

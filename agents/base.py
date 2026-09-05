"""Base agent class with standardized result and validation."""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
from llm import LLMClient, LLMError
from db import Database
from result import AgentResult
from events import Event, EventBus, EVENT_AGENT_STATE_CHANGED
from registry import STATE_IDLE, validate_agent_state

logger = logging.getLogger("aether.agent")


class Agent:
    """Base agent with identity, role, LLM access, project context, and state model."""

    role: str = "base"
    system_prompt: str = "You are a helpful assistant."

    def __init__(self, llm: LLMClient, db: Database, project_id: str, output_dir: str,
                 agent_id: Optional[str] = None, event_bus: Optional[EventBus] = None):
        self.llm = llm
        self.db = db
        self.project_id = project_id
        self.output_dir = Path(output_dir)
        self.agent_id = agent_id or f"{self.role}_001"
        self.event_bus = event_bus or getattr(self.db, "event_bus", None)
        self.state = STATE_IDLE
        try:
            self.db.set_agent_state(self.agent_id, self.project_id, self.role, self.state)
        except Exception:
            pass

    def set_state(self, new_state: str, details: dict = None, task_id: int = None) -> Event:
        """Transition agent to a new state and emit agent_state_changed event."""
        prev_state = self.state
        self.state = new_state
        payload = {
            "agent_id": self.agent_id,
            "agent_role": self.role,
            "previous_state": prev_state,
            "state": new_state,
            "details": details or {},
        }
        if details:
            payload.update(details)

        try:
            self.db.set_agent_state(self.agent_id, self.project_id, self.role, new_state, details)
        except Exception as e:
            logger.error(f"Failed to persist agent state in DB: {e}")

        return self.emit_event(
            event_type=EVENT_AGENT_STATE_CHANGED,
            status=new_state,
            task_id=task_id,
            payload=payload,
        )

    def emit_event(self, event_type: str, status: str = None, task_id: int = None,
                   payload: dict = None, metadata: dict = None) -> Event:
        """Create and emit an event envelope to DB and EventBus."""
        evt = Event(
            event_type=event_type,
            project_id=self.project_id,
            task_id=task_id,
            agent_id=self.agent_id,
            agent_role=self.role,
            status=status or self.state,
            payload=payload or {},
            metadata=metadata or {},
        )
        self.db.log_event(self.project_id, event_type, agent_role=self.role,
                          task_id=task_id, data=evt.payload, agent_id=self.agent_id,
                          status=evt.status, event=evt)
        self.db.audit(self.project_id, self.role, event_type, evt.payload)
        return evt

    def run(self, context: str, *args, **kwargs) -> AgentResult:
        """Run agent with context. Override in subclasses."""
        task_info = kwargs.get("task")
        details = {"task": task_info} if task_info else None
        self.set_state("WORKING", details)

        try:
            output = self.llm.chat(self.system_prompt, context)
            self.set_state("COMPLETED")
            return AgentResult(success=True, output=output)
        except LLMError as e:
            self.set_state("FAILED", {"error": str(e)})
            self._log("agent.failed", {"error": str(e)})
            return AgentResult(success=False, error=str(e))

    def _safe_run(self, fn, *args, **kwargs) -> AgentResult:
        """Wrap any agent method in error boundary."""
        try:
            return fn(*args, **kwargs)
        except LLMError as e:
            self.set_state("FAILED", {"error": str(e), "type": "llm_error"})
            self._log("agent.failed", {"error": str(e), "type": "llm_error"})
            return AgentResult(success=False, error=f"LLM error: {e}")
        except Exception as e:
            self.set_state("FAILED", {"error": str(e), "type": "unexpected"})
            self._log("agent.failed", {"error": str(e), "type": "unexpected"})
            logger.exception(f"Agent {self.role} unexpected error")
            return AgentResult(success=False, error=f"Unexpected error: {e}")

    def _log(self, event_type: str, data: dict = None, status: str = None, task_id: int = None):
        self.emit_event(event_type=event_type, status=status or self.state, task_id=task_id, payload=data or {})

    def _write_file(self, rel_path: str, content: str) -> bool:
        """Write file to project output directory. Returns success."""
        try:
            path = self.output_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self._log("file_generated", {"path": rel_path, "size": len(content)})
            return True
        except Exception as e:
            self._log("file_write_failed", {"path": rel_path, "error": str(e)})
            logger.error(f"Failed to write {rel_path}: {e}")
            return False

    def _write_doc(self, name: str, content: str) -> bool:
        """Write to docs/ subdirectory."""
        return self._write_file(f"docs/{name}", content)

    def _read_file(self, rel_path: str) -> str:
        """Read file from project output directory."""
        path = self.output_dir / rel_path
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _read_docs(self) -> str:
        """Read all shared docs."""
        docs = []
        docs_dir = self.output_dir / "docs"
        if docs_dir.exists():
            for f in sorted(docs_dir.glob("*.md")):
                docs.append(f"--- {f.name} ---\n{f.read_text(encoding='utf-8')}")
        return "\n\n".join(docs) if docs else "(no docs yet)"

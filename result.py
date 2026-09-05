"""AgentResult — standardized return type for all agents."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Standardized result contract for every agent."""
    success: bool
    output: Any = None          # agent-specific: str, dict, list
    files: list[str] = field(default_factory=list)
    error: str | None = None
    usage: dict | None = None   # token usage from LLM
    events: list[dict] = field(default_factory=list)  # events to log

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_type": type(self.output).__name__,
            "files": self.files,
            "error": self.error,
            "usage": self.usage,
            "events_count": len(self.events),
        }

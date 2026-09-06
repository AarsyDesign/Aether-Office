"""Developer Planner — creates structured implementation plan from requirements and context."""

from __future__ import annotations
import json
import logging
from typing import List, Dict, Any, Optional

from .base import Agent
from result import AgentResult
from llm import LLMError

logger = logging.getLogger("aether.agent.planner")

PLANNER_PROMPT = """You are a Principal Software Architect and Developer Planner.
Your job is to design a robust, production-grade software architecture and break it into clean, isolated generation units (1 file = 1 unit).

Architectural Principles:
1. Modular Separation of Concerns: Split responsibilities cleanly. Avoid monolithic single files (>200-300 lines) that risk token truncation.
   - For UI apps: Separate window shell, specific views/frames, dialogs, and styles.
   - For Data: Separate database schema/connection, data models, and repository operations.
   - For Business Logic: Decouple domain logic from UI presentation so services are independently testable.
2. Unidirectional Dependency Flow:
   - Level 1 (Foundation): Configuration, constants, data models, utility helpers.
   - Level 2 (Data / Storage): Database connection, tables, queries, migrations.
   - Level 3 (Business Logic / Services): Domain operations, state management, validations.
   - Level 4 (Presentation / Interface): UI views, CLI commands, controllers.
   - Level 5 (Entrypoint): Application runner (e.g. main.py or app.py).
3. Explicit Contracts: Clearly specify `exports` (exact class and function names) and `depends_on` (exact relative paths to internal files) so developers can import them accurately.
4. Clean Dependencies: Ensure there are NO circular dependencies.

You MUST output ONLY valid JSON with this exact structure:
{
  "project_summary": "High-level summary of the system architecture and responsibilities",
  "tech_stack": "Languages, frameworks, and libraries used (e.g., Python 3.10+, Tkinter, SQLite3)",
  "files": [
    {
      "path": "relative/path/to/file.ext",
      "purpose": "Precise architectural responsibility and what this unit implements",
      "dependencies": ["external_pip_package_if_any"],
      "exports": ["PrimaryClass", "helper_function"],
      "depends_on": ["relative/path/to/prerequisite_unit.ext"],
      "priority": 1
    }
  ]
}

Rules:
- 1 file = 1 unit.
- Priority: Lower number = higher priority (e.g., foundation priority 1, entrypoint priority 5).
- All file paths must be relative to project root (e.g. 'models/database.py', 'main.py').
- Output ONLY the raw JSON object, no explanation or chatter outside JSON.
"""


def topological_sort(files: list[dict]) -> tuple[list[str] | None, str | None]:
    """
    Topologically sort files based on internal depends_on relationships.
    External dependencies (not defined in `files`) are ignored.
    Returns (order, None) on success or (None, error_message) on cycle.
    """
    all_paths = {f["path"] for f in files if isinstance(f, dict) and "path" in f}

    adj = {p: [] for p in all_paths}
    in_degree = {p: 0 for p in all_paths}
    path_order_idx = {f["path"]: i for i, f in enumerate(files) if isinstance(f, dict) and "path" in f}

    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("path")
        if not path:
            continue
        deps = f.get("depends_on") or []
        for dep in deps:
            if dep in all_paths and dep != path:
                adj[dep].append(path)
                in_degree[path] += 1
            elif dep == path:
                return None, f"Circular dependency detected: {path} depends on itself"

    queue = [p for p in all_paths if in_degree[p] == 0]
    queue.sort(key=lambda p: path_order_idx.get(p, 0))

    order = []
    while queue:
        u = queue.pop(0)
        order.append(u)
        for v in sorted(adj[u], key=lambda p: path_order_idx.get(p, 0)):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if len(order) != len(all_paths):
        cycle_nodes = [p for p, deg in in_degree.items() if deg > 0]
        return None, f"Circular dependency detected among files: {', '.join(cycle_nodes)}"

    return order, None


class Planner:
    """Developer Planner — creates structured implementation plan from requirements."""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.logger = logging.getLogger("aether.agent.planner")

    def plan(self, fix_files: Optional[List[str]] = None) -> AgentResult:
        """Create implementation plan from project context."""
        # Import event constant
        from events import EVENT_AGENT_STATE_CHANGED

        self.agent._log("developer_planning_started", {"fix_mode": fix_files is not None})
        self.agent.set_state("PLANNING", {"fix_mode": fix_files is not None})
        # Emit planner role state for live progress & UI
        self.agent.emit_event(
            EVENT_AGENT_STATE_CHANGED,
            status="PLANNING",
            payload={"agent_id": "planner_001", "agent_role": "planner", "state": "PLANNING"},
        )
        try:
            self.agent.db.set_agent_state("planner_001", self.agent.project_id, "planner", "PLANNING")
        except Exception:
            pass

        # Gather context
        docs = self.agent._read_docs()
        tasks = self.agent.db.get_tasks(self.agent.project_id)

        user_msg = (
            f"## Shared Docs\n{docs}\n\n"
            f"## Tasks\n{self._tasks_summary(tasks)}\n\n"
            f"## Instructions\n"
            f"Create a detailed implementation plan. Include:\n"
            f"- All necessary files with purposes\n"
            f"- Dependencies between files (depends_on)\n"
            f"- Priority ordering\n"
            f"- Export functions and classes\n"
            f"Focus on logical grouping and dependency flow."
        )

        if fix_files:
            user_msg += f"\n\n## Fix Scope\nRegenerate only these files: {', '.join(fix_files)}"

        try:
            planner_llm = self.agent.llm.for_role("planner") if hasattr(self.agent.llm, "for_role") else self.agent.llm
            result = planner_llm.chat(PLANNER_PROMPT, user_msg, json_mode=True)
        except LLMError as e:
            self.agent._log("agent.failed", {"error": str(e), "phase": "planning"})
            self.agent.emit_event(
                EVENT_AGENT_STATE_CHANGED,
                status="FAILED",
                payload={"agent_id": "planner_001", "agent_role": "planner", "state": "FAILED", "error": str(e)},
            )
            return AgentResult(success=False, error=f"Planner LLM failed: {e}")

        # Validate response structure
        self.last_raw_response = result
        if isinstance(result, str):
            import re
            cleaned = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()
            fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned)
            if fence_match:
                try:
                    result = json.loads(fence_match.group(1).strip())
                except Exception:
                    pass
            if not isinstance(result, dict):
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end > start:
                    try:
                        result = json.loads(cleaned[start:end+1])
                    except Exception:
                        pass

        if not isinstance(result, dict):
            self.agent._log("validation_failed", {"reason": f"Expected dict, got {type(result).__name__}"})
            return AgentResult(success=False, error=f"Invalid response type: expected dict, got {type(result).__name__}")

        if "project_summary" not in result or "files" not in result:
            missing = {"project_summary", "files"} - set(result.keys())
            self.agent._log("validation_failed", {"reason": f"Missing fields: {missing}"})
            return AgentResult(success=False, error=f"Missing required fields: {missing}")

        files = result.get("files", [])
        if not files:
            self.agent._log("validation_failed", {"reason": "No files in plan"})
            return AgentResult(success=False, error="Planner produced 0 files")

        # Validate each file entry
        for i, f in enumerate(files):
            if not isinstance(f, dict) or "path" not in f:
                self.agent._log("validation_failed", {"reason": f"File {i} missing 'path'"})
                return AgentResult(success=False, error=f"File {i} missing 'path'")
            f.setdefault("purpose", "")
            f.setdefault("priority", 1)
            f.setdefault("exports", [])
            f.setdefault("depends_on", [])
            f.setdefault("dependencies", [])

        # Check for circular dependencies & calculate generation order
        order, error = topological_sort(files)
        if error:
            self.agent._log("validation_failed", {"reason": "circular_dependency", "error": error})
            return AgentResult(success=False, error=f"Dependency cycle detected: {error}")

        # Build ordered plan document
        file_by_path = {f["path"]: f for f in files}
        ordered_files = [file_by_path[p] for p in order if p in file_by_path]

        plan_doc = {
            "project_summary": result.get("project_summary", ""),
            "tech_stack": result.get("tech_stack", "Python"),
            "files": ordered_files,
            "generation_order": order,
        }

        self.agent._write_doc("implementation_plan.json", json.dumps(plan_doc, indent=2))
        self.agent._log("developer_plan_created", {"file_count": len(files)})
        self.agent.emit_event(
            EVENT_AGENT_STATE_CHANGED,
            status="COMPLETED",
            payload={"agent_id": "planner_001", "agent_role": "planner", "state": "COMPLETED", "file_count": len(files)},
        )
        try:
            self.agent.db.set_agent_state("planner_001", self.agent.project_id, "planner", "COMPLETED")
        except Exception:
            pass

        return AgentResult(
            success=True,
            output=plan_doc,
            files=["docs/implementation_plan.json"],
        )

    def _tasks_summary(self, tasks: List[dict]) -> str:
        """Format task list for prompt."""
        return "\n".join(f"- {t.get('title', 'Task')}: {t.get('description', '')} (priority: {t.get('priority', 3)})" for t in tasks)
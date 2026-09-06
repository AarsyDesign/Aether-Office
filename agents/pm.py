"""Project Manager agent — breaks brief into tasks."""

from __future__ import annotations
import json
import logging
from .base import Agent
from result import AgentResult
from llm import LLMError

logger = logging.getLogger("aether.agent.pm")

# Required fields in PM JSON output
REQUIRED_PM_FIELDS = {"project_name", "tasks"}
REQUIRED_TASK_FIELDS = {"title"}


class PMAgent(Agent):
    role = "pm"
    system_prompt = """You are a Senior Technical Product Manager and Engineering Lead.
Your responsibility is to analyze project briefs and translate them into a structured, production-grade engineering roadmap.

Engineering Decomposition Principles:
1. Phased Task Sequencing:
   - Phase 1 (Foundation): Configuration, constants, environment setup, and data models.
   - Phase 2 (Data Layer): Database schemas, tables, migrations, and data access objects.
   - Phase 3 (Core Services): Business logic, domain calculation engines, and validation rules.
   - Phase 4 (User Presentation): UI windows/views, command-line interfaces, and interaction flows.
   - Phase 5 (Integration & Verification): System wiring, test harnesses, error recovery, and packaging.
2. Concrete & Actionable Tasks:
   - Avoid vague tasks like "do styling" or "add logic".
   - State exact functional goals, target interfaces, data inputs, outputs, and edge cases to consider.
3. Dependency Integrity:
   - Dependencies must strictly reference valid 0-based indices of prior prerequisite tasks.
   - Ensure an acyclic, logical pipeline flow.

You MUST output ONLY valid JSON with this exact structure:
{
    "project_name": "Concise, descriptive project name",
    "project_description": "Comprehensive summary explaining domain, primary users, and core workflow",
    "tasks": [
        {
            "title": "Clear, imperative task title (e.g. Implement SQLite Transaction Repository)",
            "description": "Detailed explanation of technical requirements, expected interfaces, and edge cases",
            "priority": 1-5 (5 = highest / foundational, 1 = lowest / polish),
            "dependencies": [0, 1]
        }
    ],
    "tech_stack": "Recommended production-grade technology stack and standard libraries",
    "file_structure": "Clean, idiomatic proposed directory layout"
}

Rules:
- Tasks should be scoped to cohesive, isolated units.
- Dependencies must only reference earlier or parallel valid task indices.
- Output ONLY the raw JSON object, no explanation or chatter outside JSON."""

    def create_project(self, brief: str) -> AgentResult:
        """Parse brief → create project + tasks."""
        self._log("agent.started", {"brief_length": len(brief)})
        self.set_state("THINKING", {"action": "analyzing_brief", "brief_length": len(brief)})

        # Call LLM
        try:
            result = self.llm.chat(self.system_prompt, brief, json_mode=True)
        except LLMError as e:
            self.set_state("FAILED", {"error": str(e)})
            self._log("agent.failed", {"error": str(e)})
            return AgentResult(success=False, error=f"PM LLM failed: {e}")

        # Resilient fallback parsing for reasoning models or string responses
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

        # Validate response
        if not isinstance(result, dict):
            self.set_state("FAILED", {"reason": "non_dict_output"})
            self._log("validation_failed", {"reason": "LLM returned non-dict", "type": type(result).__name__})
            return AgentResult(success=False, error=f"PM expected dict, got {type(result).__name__}")

        missing = REQUIRED_PM_FIELDS - set(result.keys())
        if missing:
            self.set_state("FAILED", {"reason": f"Missing fields: {missing}"})
            self._log("validation_failed", {"reason": f"Missing fields: {missing}"})
            return AgentResult(success=False, error=f"PM response missing fields: {missing}")

        tasks = result.get("tasks", [])
        if not tasks:
            self.set_state("FAILED", {"reason": "zero_tasks"})
            self._log("validation_failed", {"reason": "No tasks in PM output"})
            return AgentResult(success=False, error="PM produced 0 tasks")

        # Validate each task
        bad_tasks = []
        for i, t in enumerate(tasks):
            tmiss = REQUIRED_TASK_FIELDS - set(t.keys())
            if tmiss:
                bad_tasks.append({"index": i, "missing": list(tmiss)})
        if bad_tasks:
            self._log("validation_failed", {"reason": "Invalid tasks", "bad_tasks": bad_tasks})
            # Continue anyway — log warning but don't fail

        self.set_state("WORKING", {"action": "creating_project_and_tasks", "task_count": len(tasks)})

        # Create project
        project_name = result.get("project_name", "untitled")
        self._log("project.parsed", {"name": project_name, "task_count": len(tasks)})

        # Create tasks in DB
        task_ids = []
        for t in tasks:
            deps = t.get("dependencies", [])
            if not isinstance(deps, list):
                deps = []
            task_id = self.db.create_task(
                self.project_id,
                title=t.get("title", "untitled"),
                description=t.get("description", ""),
                assigned_to="developer",
                priority=t.get("priority", 3),
                dependencies=deps,
            )
            task_ids.append(task_id)
            self.db.log_event(self.project_id, "task.created", self.role,
                              task_id=task_id, data={"title": t.get("title", "")})

        # Write initial docs
        doc_content = (
            f"# {project_name}\n\n"
            f"{result.get('project_description', brief)}\n\n"
            f"## Tech Stack\n{result.get('tech_stack', 'TBD')}\n\n"
            f"## File Structure\n```\n{result.get('file_structure', 'TBD')}\n```"
        )
        self._write_doc("product.md", doc_content)

        # Mark all tasks READY
        for tid in task_ids:
            self.db.update_task_status(tid, "READY")

        self.set_state("COMPLETED", {"tasks_created": len(task_ids)})
        self._log("agent.completed", {"tasks_created": len(task_ids)})

        return AgentResult(
            success=True,
            output={"project_name": project_name, "task_count": len(task_ids)},
            files=["docs/product.md"],
        )

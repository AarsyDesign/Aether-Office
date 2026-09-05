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
    system_prompt = """You are a Project Manager. Your job:
1. Read the project brief
2. Break it into concrete development tasks
3. Assign priorities and dependencies
4. Define the project structure

You MUST output valid JSON with this exact structure:
{
    "project_name": "short name",
    "project_description": "one paragraph",
    "tasks": [
        {
            "title": "task title",
            "description": "what needs to be done",
            "priority": 1-5 (5=highest),
            "dependencies": [indices of dependent tasks, 0-based]
        }
    ],
    "tech_stack": "recommended technology",
    "file_structure": "proposed directory layout"
}

Rules:
- Tasks should be small enough for one developer session
- Include setup/task, feature tasks, and integration tasks
- Dependencies must reference valid task indices
- Be specific — "implement login" not "add auth"
- Output ONLY the JSON object, no other text"""

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

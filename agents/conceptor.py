"""Conceptor agent — turns tasks into requirements + acceptance criteria."""

from __future__ import annotations
import logging
from .base import Agent
from result import AgentResult
from llm import LLMError

logger = logging.getLogger("aether.agent.conceptor")


class ConceptorAgent(Agent):
    role = "conceptor"
    system_prompt = """You are a Conceptor/Analyst. Your job:
1. Read the project tasks and product brief
2. Create detailed requirements, user stories, and acceptance criteria
3. Write a technical design document

Output your analysis as MARKDOWN with these sections:

# Requirements Document

## Product Overview
[summary]

## Functional Requirements
[numbered list of specific requirements]

## User Stories
[as a [user], I want [feature], so that [benefit]]

## Acceptance Criteria
[numbered, testable criteria — each MUST be pass/fail checkable]

## Technical Design
[architecture, key decisions, data model, API endpoints if applicable]

## Edge Cases
[potential issues to handle]

## Testing Strategy
[how QA should verify each requirement]

Be thorough. Each acceptance criterion must be specific enough that a tester can verify it objectively."""

    def create_requirements(self, tasks_summary: str = None) -> AgentResult:
        """Read project context → write requirements doc."""
        self._log("agent.started", {})
        self.set_state("THINKING", {"action": "analyzing_context"})

        # Gather context
        docs = self._read_docs()
        task_list = self.db.get_tasks(self.project_id)
        if not task_list:
            self.set_state("FAILED", {"error": "No tasks found"})
            self._log("agent.failed", {"error": "No tasks found"})
            return AgentResult(success=False, error="No tasks found for this project")

        tasks_text = "\n".join(
            f"- [{t['id']}] {t['title']}: {t['description']} (priority: {t['priority']})"
            for t in task_list
        )

        user_msg = (
            f"## Shared Docs\n{docs}\n\n"
            f"## Tasks\n{tasks_text}\n\n"
            f"## Instructions\n"
            f"Create a comprehensive requirements document for this project. "
            f"Focus on acceptance criteria that can be tested."
        )
        if tasks_summary:
            user_msg = f"{tasks_summary}\n\n{user_msg}"

        # Call LLM
        try:
            result = self.llm.chat(self.system_prompt, user_msg)
        except LLMError as e:
            self.set_state("FAILED", {"error": str(e)})
            self._log("agent.failed", {"error": str(e)})
            return AgentResult(success=False, error=f"Conceptor LLM failed: {e}")

        # Validate
        if not isinstance(result, str):
            self.set_state("FAILED", {"reason": f"Expected str, got {type(result).__name__}"})
            self._log("validation_failed", {"reason": f"Expected str, got {type(result).__name__}"})
            return AgentResult(success=False, error=f"Expected str output, got {type(result).__name__}")

        if len(result.strip()) < 10:
            self.set_state("FAILED", {"reason": f"Output too short ({len(result)} chars)"})
            self._log("validation_failed", {"reason": f"Output too short ({len(result)} chars)"})
            return AgentResult(success=False, error=f"Requirements doc too short ({len(result)} chars)")

        self.set_state("WORKING", {"action": "writing_requirements_and_tests"})

        # Write requirements doc
        files = []
        if self._write_doc("requirements.md", result):
            files.append("docs/requirements.md")

        # Create test plan from requirements
        testing_doc = self._derive_test_plan(task_list, result)
        if self._write_doc("testing.md", testing_doc):
            files.append("docs/testing.md")

        self.set_state("COMPLETED", {"files": files})
        self._log("agent.completed", {"doc_length": len(result), "files": len(files)})

        return AgentResult(
            success=True,
            output=result,
            files=files,
        )

    def _derive_test_plan(self, tasks: list[dict], requirements: str) -> str:
        """Derive test plan from requirements doc without an extra LLM call."""
        if "## Testing Strategy" in requirements:
            strategy = requirements.split("## Testing Strategy")[1].split("##")[0].strip()
        else:
            strategy = "Verify all acceptance criteria against implementation."

        task_lines = "\n".join(f"- {t.get('title', 'Task')}" for t in tasks)
        return (
            f"# Test Plan\n\n"
            f"## Strategy\n{strategy}\n\n"
            f"## Scope\n{task_lines}\n"
        )

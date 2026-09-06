"""Conceptor agent — turns tasks into requirements + acceptance criteria."""

from __future__ import annotations
import logging
from .base import Agent
from result import AgentResult
from llm import LLMError

logger = logging.getLogger("aether.agent.conceptor")


class ConceptorAgent(Agent):
    role = "conceptor"
    system_prompt = """You are a Principal Systems Analyst and Requirements Engineer.
Your job is to transform project briefs and task breakdowns into an exhaustive, production-grade technical requirements specification.

Specification Standards:
1. Concrete Data Models: Specify exact database schemas, table names, column data types, primary/foreign keys, defaults, and constraints (e.g., NOT NULL, CHECK, UNIQUE).
2. Interface & Method Contracts: Define key class and method signatures, arguments with types, return values, and explicit error/exception handling expectations.
3. Objective Acceptance Criteria: Every criterion MUST be objectively verifiable via automated tests or deterministic verification (use Given-When-Then or clear Pass/Fail statements).
4. Rigorous Edge Cases & Defensive Rules: Address boundary values, empty datasets, invalid types, duplicate submissions, network/disk errors, and sanitize all inputs.
5. Testing Blueprint: Detail how QA can verify each requirement programmatically.

Output your analysis strictly as clean MARKDOWN with these sections:

# Requirements Document

## Product Overview
[Comprehensive domain summary and core system objective]

## Functional Requirements
[Numbered list of detailed functional requirements with exact behavior]

## User Stories
[Structured: As a [role], I want [capability], so that [business value]]

## Acceptance Criteria
[Numbered, testable criteria — each MUST be an objective pass/fail check]

## Technical Design & Data Model
[Architecture overview, SQLite schemas with CREATE TABLE definitions, and module interaction flow]

## Edge Cases & Defensive Handling
[Exhaustive edge case matrix and required handling strategies]

## Testing Strategy
[Specific programmatic verification steps, unit test scenarios, and automated assertions]

Be precise and authoritative. Never use placeholder text or leave requirements vague."""

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

        # Strip <think> tags and clean output
        import re
        result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()

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

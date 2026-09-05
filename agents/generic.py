"""Generic Agent implementation for dynamic workforce roles."""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional, Any

from llm import LLMClient, LLMError
from db import Database
from result import AgentResult
from events import Event, EventBus
from agents.base import Agent
from workforce import Employee, Role
from prompt_builder import PromptBuilder

logger = logging.getLogger("aether.agent.generic")


class GenericAgent(Agent):
    """Universal agent able to execute arbitrary tasks for any role via prompt composition."""

    def __init__(
        self,
        llm: LLMClient,
        db: Database,
        project_id: str,
        output_dir: str,
        employee: Employee,
        role_def: Optional[Role] = None,
        event_bus: Optional[EventBus] = None,
        prompt_builder: Optional[PromptBuilder] = None,
    ):
        self.employee = employee
        self.role_def = role_def
        self.role = employee.role
        self.prompt_builder = prompt_builder or PromptBuilder()
        super().__init__(
            llm=llm,
            db=db,
            project_id=project_id,
            output_dir=output_dir,
            agent_id=employee.employee_id,
            event_bus=event_bus,
        )

    def run(self, context: str, task: Optional[dict | str] = None) -> AgentResult:
        """Execute a task given context and instructions."""
        task_info = task if isinstance(task, dict) else ({"description": str(task)} if task else {})
        self.set_state("WORKING", {"action": "executing_task", "task": task_info})

        system_prompt = self.prompt_builder.build(
            employee=self.employee,
            role=self.role_def,
            task=task_info,
            context=context,
        )

        try:
            output = self.llm.chat(system_prompt, context)
            self.set_state("COMPLETED", {"output_length": len(output)})
            return AgentResult(success=True, output=output)
        except LLMError as e:
            self.set_state("FAILED", {"error": str(e), "type": "llm_error"})
            return AgentResult(success=False, error=f"LLM error: {e}")
        except Exception as e:
            self.set_state("FAILED", {"error": str(e), "type": "execution_error"})
            return AgentResult(success=False, error=f"Execution error: {e}")

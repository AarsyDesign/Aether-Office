"""Agent Factory for instantiating specialized and generic agents."""

from __future__ import annotations
from typing import Optional, Dict, Type, Any

from llm import LLMClient
from db import Database
from events import EventBus
from agents.base import Agent
from agents.pm import PMAgent
from agents.conceptor import ConceptorAgent
from agents.planner import Planner as PlannerAgent
from agents.developer import DeveloperAgent
from agents.qa import QAAgent
from agents.generic import GenericAgent
from workforce import Employee, Role, Organization
from prompt_builder import PromptBuilder


class AgentFactory:
    """Creates agent instances based on employee profile, role mapping, and fallback."""

    def __init__(
        self,
        organization: Optional[Organization] = None,
        prompt_builder: Optional[PromptBuilder] = None,
    ):
        self.organization = organization
        self.prompt_builder = prompt_builder or PromptBuilder()
        self._specialized_map: dict[str, Type[Agent]] = {
            "pm": PMAgent,
            "product_manager": PMAgent,
            "conceptor": ConceptorAgent,
            "planner": PlannerAgent,
            "software_architect": PlannerAgent,
            "developer": DeveloperAgent,
            "backend_developer": DeveloperAgent,
            "frontend_developer": DeveloperAgent,
            "fullstack_developer": DeveloperAgent,
            "qa": QAAgent,
            "qa_engineer": QAAgent,
        }

    def register_agent_class(self, role: str, agent_class: Type[Agent]) -> None:
        """Register a custom specialized agent class for a role."""
        self._specialized_map[role.lower()] = agent_class

    def is_specialized_role(self, role: str) -> bool:
        """Check if a role has a specialized agent class."""
        return role.lower() in self._specialized_map

    def create_agent(
        self,
        employee: Employee,
        llm: LLMClient,
        db: Database,
        project_id: str,
        output_dir: str,
        config: Optional[dict] = None,
        event_bus: Optional[EventBus] = None,
    ) -> Agent:
        """Instantiate an agent appropriate for the employee's role."""
        role_key = employee.role.lower()
        agent_cls = self._specialized_map.get(role_key)

        bus = event_bus or getattr(db, "event_bus", None)

        if agent_cls:
            if issubclass(agent_cls, DeveloperAgent):
                return agent_cls(
                    llm=llm,
                    db=db,
                    project_id=project_id,
                    output_dir=str(output_dir),
                    config=config or {},
                    agent_id=employee.employee_id,
                    event_bus=bus,
                )
            else:
                return agent_cls(
                    llm=llm,
                    db=db,
                    project_id=project_id,
                    output_dir=str(output_dir),
                    agent_id=employee.employee_id,
                    event_bus=bus,
                )

        # Fallback to GenericAgent for all other roles
        role_def = None
        if self.organization:
            role_def = self.organization.get_role(employee.role)

        return GenericAgent(
            llm=llm,
            db=db,
            project_id=project_id,
            output_dir=str(output_dir),
            employee=employee,
            role_def=role_def,
            event_bus=bus,
            prompt_builder=self.prompt_builder,
        )

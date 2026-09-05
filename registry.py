"""Agent Registry, Manifest, State Model, and Organization Architecture.
Upgraded in Phase 4 to integrate with workforce.py while maintaining 100% backward compatibility.
"""

from __future__ import annotations
import threading
from typing import Optional, List, Dict, Any

from workforce import (
    STATE_IDLE,
    STATE_THINKING,
    STATE_PLANNING,
    STATE_WORKING,
    STATE_WAITING,
    STATE_RETRYING,
    STATE_TESTING,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_BLOCKED,
    ALL_AGENT_STATES,
    Employee,
    AgentManifest,
    EmployeeRegistry,
    Department,
    Organization,
    Role,
    RoleCatalog,
    create_default_organization,
)

# Backward-compatibility alias
AgentRegistry = EmployeeRegistry

# Permissible state transitions for agents
VALID_AGENT_TRANSITIONS = {
    STATE_IDLE: {STATE_THINKING, STATE_PLANNING, STATE_WORKING, STATE_TESTING, STATE_BLOCKED},
    STATE_THINKING: {STATE_PLANNING, STATE_WORKING, STATE_COMPLETED, STATE_FAILED, STATE_WAITING},
    STATE_PLANNING: {STATE_WORKING, STATE_COMPLETED, STATE_FAILED, STATE_WAITING},
    STATE_WORKING: {STATE_WORKING, STATE_RETRYING, STATE_TESTING, STATE_COMPLETED, STATE_FAILED, STATE_WAITING, STATE_BLOCKED},
    STATE_WAITING: {STATE_THINKING, STATE_PLANNING, STATE_WORKING, STATE_TESTING, STATE_FAILED},
    STATE_RETRYING: {STATE_WORKING, STATE_FAILED, STATE_TESTING},
    STATE_TESTING: {STATE_COMPLETED, STATE_FAILED, STATE_RETRYING, STATE_WORKING},
    STATE_BLOCKED: {STATE_IDLE, STATE_WORKING, STATE_FAILED},
    STATE_COMPLETED: {STATE_IDLE, STATE_THINKING, STATE_PLANNING, STATE_WORKING},  # For re-run or next task
    STATE_FAILED: {STATE_IDLE, STATE_RETRYING, STATE_WORKING},
}


def validate_agent_state(state: str) -> bool:
    """Validate that state is one of the recognized agent states."""
    return state in ALL_AGENT_STATES


def validate_agent_transition(from_state: str, to_state: str) -> bool:
    """Validate whether transitioning from from_state to to_state is permissible."""
    if from_state not in ALL_AGENT_STATES or to_state not in ALL_AGENT_STATES:
        return False
    return to_state in VALID_AGENT_TRANSITIONS.get(from_state, set())


__all__ = [
    "STATE_IDLE",
    "STATE_THINKING",
    "STATE_PLANNING",
    "STATE_WORKING",
    "STATE_WAITING",
    "STATE_RETRYING",
    "STATE_TESTING",
    "STATE_COMPLETED",
    "STATE_FAILED",
    "STATE_BLOCKED",
    "ALL_AGENT_STATES",
    "VALID_AGENT_TRANSITIONS",
    "validate_agent_state",
    "validate_agent_transition",
    "Employee",
    "AgentManifest",
    "AgentRegistry",
    "EmployeeRegistry",
    "Department",
    "Organization",
    "Role",
    "RoleCatalog",
    "create_default_organization",
]

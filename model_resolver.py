"""Model Assignment Resolution and Inheritance Hierarchy."""

from __future__ import annotations
from typing import Optional, Dict, Any
from workforce import Employee, Role, Department, Organization


DEFAULT_MODEL_CONFIG = {
    "provider": "openai-compatible",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
    "timeout": 300,
    "max_retries": 3,
}


def _clean_dict(d: Optional[dict]) -> dict:
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items() if v is not None}


def resolve_model_config(
    employee: Optional[Employee] = None,
    role: Optional[Role] = None,
    department: Optional[Department] = None,
    organization: Optional[Organization] = None,
    global_config: Optional[dict] = None,
) -> dict:
    """Resolve model configuration through hierarchical inheritance.

    Resolution hierarchy (most specific wins):
      1. Global config (e.g. config['llm'])
      2. Organization default
      3. Department default
      4. Role default
      5. Employee config
    """
    resolved = dict(DEFAULT_MODEL_CONFIG)

    # 1. Global config
    if global_config:
        llm_cfg = global_config.get("llm", global_config)
        resolved.update(_clean_dict(llm_cfg))

        # Check if the router defines role-specific models
        models_map = llm_cfg.get("models")
        if isinstance(models_map, dict):
            role_key = None
            if role and hasattr(role, "role_id"):
                role_key = role.role_id
            elif employee and hasattr(employee, "role"):
                role_key = employee.role

            if role_key:
                role_lower = str(role_key).lower()
                matched = models_map.get(role_lower)
                if not matched and "_" in role_lower:
                    for part in role_lower.split("_"):
                        if part in models_map:
                            matched = models_map[part]
                            break
                if matched:
                    resolved["model"] = matched

    # 2. Organization default
    if organization and hasattr(organization, "default_model"):
        resolved.update(_clean_dict(organization.default_model))

    # 3. Department default
    if department and hasattr(department, "default_model"):
        resolved.update(_clean_dict(department.default_model))

    # 4. Role default
    if role and hasattr(role, "default_model"):
        resolved.update(_clean_dict(role.default_model))

    # 5. Employee config
    if employee and hasattr(employee, "model"):
        resolved.update(_clean_dict(employee.model))

    return resolved

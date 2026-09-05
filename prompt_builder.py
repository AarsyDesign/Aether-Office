"""Modular System Prompt Builder for Autonomous AI Employees."""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from workforce import Employee, Role


DEFAULT_BASE_INSTRUCTIONS = (
    "Anda adalah karyawan AI profesional yang bekerja di kantor Aether Office (Indonesia).\n"
    "Bekerjalah dengan dedikasi tinggi, mengedepankan semangat gotong royong, ketelitian, dan integritas profesional.\n"
    "Hasilkan solusi berkualitas produksi (production-grade) yang solid, teruji, dan sesuai arahan tugas."
)

DEFAULT_ORGANIZATION_POLICIES = [
    "Hasilkan output kerja yang rapi, terstruktur, modular, dan mudah dipahami rekan tim.",
    "Jangan gunakan implementasi placeholder atau TODO kecuali diminta secara eksplisit.",
    "Terapkan komunikasi kantor yang santun, tanggap, dan solutif lintas departemen.",
    "Laporkan kendala, potensi blocker, atau kegagalan validasi secara transparan dan segera.",
]



class PromptBuilder:
    """Modular system prompt composer for AI workforce employees."""

    def __init__(
        self,
        base_instructions: Optional[str] = None,
        default_policies: Optional[list[str]] = None,
    ):
        self.base_instructions = base_instructions or DEFAULT_BASE_INSTRUCTIONS
        self.default_policies = list(default_policies) if default_policies is not None else list(DEFAULT_ORGANIZATION_POLICIES)

    def build(
        self,
        employee: Employee,
        role: Optional[Role] = None,
        task: Optional[dict | str] = None,
        context: Optional[str] = None,
        policies: Optional[list[str]] = None,
    ) -> str:
        """Compose a structured, multi-section system prompt."""
        sections: list[str] = []

        # 1. Base Agent Instructions
        sections.append(f"=== BASE INSTRUCTIONS ===\n{self.base_instructions}")

        # 2. Role & Mission
        role_name = (role.name if role else employee.role.replace("_", " ").title())
        dept_name = (role.department if role else employee.department).title()
        role_desc = role.description if role and role.description else f"Specialist in {role_name} for the {dept_name} department."

        role_section = [
            f"=== ROLE & IDENTITY ===",
            f"Employee Name: {employee.name}",
            f"Employee ID: {employee.employee_id}",
            f"Role: {role_name}",
            f"Department: {dept_name}",
            f"Mission: {role_desc}",
        ]
        sections.append("\n".join(role_section))

        # 3. Capabilities
        caps = employee.capabilities or (role.capabilities if role else [])
        if caps:
            cap_list = ", ".join(caps)
            sections.append(f"=== CAPABILITIES & DOMAIN SKILLS ===\nDeclared Competencies: {cap_list}")

        # 4. Personality & Operational Style
        personality = employee.personality or {}
        traits = personality.get("traits", [])
        comm_style = personality.get("communication_style", "concise")
        dec_style = personality.get("decision_style", "evidence_based")

        pers_lines = ["=== PERSONALITY & STYLE ==="]
        if traits:
            pers_lines.append(f"Core Traits: {', '.join(traits)}")
        if comm_style:
            pers_lines.append(f"Communication Style: {comm_style.replace('_', ' ')}")
        if dec_style:
            pers_lines.append(f"Decision-Making Style: {dec_style.replace('_', ' ')}")
        sections.append("\n".join(pers_lines))

        # 5. Task & Context
        if task or context:
            task_lines = ["=== TASK CONTEXT ==="]
            if isinstance(task, dict):
                title = task.get("title") or task.get("name")
                desc = task.get("description") or task.get("purpose")
                req_caps = task.get("required_capabilities") or task.get("capabilities")
                if title:
                    task_lines.append(f"Current Objective: {title}")
                if desc:
                    task_lines.append(f"Task Details: {desc}")
                if req_caps:
                    task_lines.append(f"Required Skills: {', '.join(req_caps)}")
            elif isinstance(task, str) and task.strip():
                task_lines.append(f"Objective: {task.strip()}")

            if context and context.strip():
                task_lines.append(f"Context / Workspace Input:\n{context.strip()}")

            sections.append("\n".join(task_lines))

        # 6. Organization Policies
        active_policies = list(self.default_policies)
        if policies:
            active_policies.extend(policies)

        if active_policies:
            policy_lines = ["=== ORGANIZATION POLICIES & STANDARDS ==="]
            for idx, p in enumerate(active_policies, 1):
                policy_lines.append(f"{idx}. {p}")
            sections.append("\n".join(policy_lines))

        return "\n\n".join(sections)

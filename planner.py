"""ExecutionPlan, PlanValidator, and ObjectivePlanner for Phase 8."""

from __future__ import annotations
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set, Tuple

from objectives import Objective, ObjectiveStatus
from workforce import Organization, Employee, STATUS_ACTIVE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Milestone:
    """Milestone grouping related execution tasks."""
    milestone_id: str
    name: str
    description: str = ""
    task_ids: list[str] = field(default_factory=list)
    order: int = 0

    def to_dict(self) -> dict:
        return {
            "milestone_id": self.milestone_id,
            "name": self.name,
            "description": self.description,
            "task_ids": list(self.task_ids),
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Milestone:
        return cls(
            milestone_id=d["milestone_id"],
            name=d["name"],
            description=d.get("description", ""),
            task_ids=list(d.get("task_ids", [])),
            order=int(d.get("order", 0)),
        )


@dataclass
class ExecutionPlan:
    """Complete execution blueprint generated from an Objective."""
    id: str
    objective_id: str
    milestones: list[Milestone] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    estimated_cost: float = 0.0
    required_skills: list[str] = field(default_factory=list)
    is_valid: bool = True
    validation_error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def get_task(self, task_id: str) -> Optional[dict]:
        for t in self.tasks:
            if t.get("task_id") == task_id:
                return t
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "objective_id": self.objective_id,
            "milestones": [m.to_dict() for m in self.milestones],
            "tasks": list(self.tasks),
            "dependencies": {k: list(v) for k, v in self.dependencies.items()},
            "estimated_cost": self.estimated_cost,
            "required_skills": list(self.required_skills),
            "is_valid": self.is_valid,
            "validation_error": self.validation_error,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ExecutionPlan:
        return cls(
            id=d["id"],
            objective_id=d["objective_id"],
            milestones=[Milestone.from_dict(m) for m in d.get("milestones", [])],
            tasks=list(d.get("tasks", [])),
            dependencies={k: list(v) for k, v in d.get("dependencies", {}).items()},
            estimated_cost=float(d.get("estimated_cost", 0.0)),
            required_skills=list(d.get("required_skills", [])),
            is_valid=bool(d.get("is_valid", True)),
            validation_error=d.get("validation_error"),
            metadata=dict(d.get("metadata", {})),
            created_at=d.get("created_at") or _now_iso(),
        )


class PlanValidator:
    """Enforces strict structural and operational validity on an ExecutionPlan."""

    @classmethod
    def validate_plan(
        cls,
        plan: ExecutionPlan,
        organization: Optional[Organization] = None,
        budget_limit: float = 0.0,
    ) -> tuple[bool, Optional[str]]:
        """Validates the execution plan:
        1. Non-empty tasks
        2. Unique task IDs
        3. Valid dependency references
        4. No circular dependencies (Topological sort DAG check)
        5. Skill/role requirements present on each task
        6. Workforce capability feasibility (if organization provided)
        7. Budget constraint sufficiency (if budget_limit > 0)
        """
        if not plan.tasks:
            return False, "ExecutionPlan contains no tasks."

        task_ids = set()
        for t in plan.tasks:
            t_id = t.get("task_id")
            if not t_id:
                return False, "Found task without 'task_id'."
            if t_id in task_ids:
                return False, f"Duplicate task_id '{t_id}' found in ExecutionPlan."
            task_ids.add(t_id)

            # Check skill or role requirement
            req_caps = t.get("required_capabilities") or []
            role = t.get("preferred_role") or t.get("role")
            if not req_caps and not role:
                return False, f"Task '{t_id}' missing both required_capabilities and preferred_role."

        # Validate dependency references
        for t_id, deps in plan.dependencies.items():
            if t_id not in task_ids:
                return False, f"Dependency specified for non-existent task '{t_id}'."
            for dep in deps:
                if dep not in task_ids:
                    return False, f"Task '{t_id}' depends on non-existent task '{dep}'."
                if dep == t_id:
                    return False, f"Task '{t_id}' cannot depend on itself."

        # Circular dependency check using Kahn's algorithm (Topological sort)
        in_degree = {t_id: 0 for t_id in task_ids}
        adj: dict[str, list[str]] = {t_id: [] for t_id in task_ids}

        for t_id, deps in plan.dependencies.items():
            for dep in deps:
                adj[dep].append(t_id)
                in_degree[t_id] += 1

        queue = [t_id for t_id, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            node = queue.pop(0)
            visited_count += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count < len(task_ids):
            unresolved = [t_id for t_id, deg in in_degree.items() if deg > 0]
            return False, f"Circular dependency detected in execution graph involving tasks: {unresolved}"

        # Workforce feasibility check
        if organization:
            active_employees = [e for e in organization.employees.list() if e.status == STATUS_ACTIVE]
            if not active_employees:
                return False, "Organization has no active employees in the workforce pool."

            for t in plan.tasks:
                t_id = t["task_id"]
                req_caps = set(c.lower() for c in (t.get("required_capabilities") or []))
                role = (t.get("preferred_role") or t.get("role") or "").lower()

                has_candidate = False
                for emp in active_employees:
                    emp_caps = set(c.lower() for c in emp.capabilities)
                    emp_role = emp.role.lower()
                    # Either role matches or at least one required capability matches
                    if role and (emp_role == role or role in emp_role or emp_role in role):
                        has_candidate = True
                        break
                    if req_caps:
                        if req_caps.intersection(emp_caps):
                            has_candidate = True
                            break
                        for rc in req_caps:
                            if any(rc in ec or ec in rc for ec in emp_caps):
                                has_candidate = True
                                break
                    if has_candidate:
                        break

                if not has_candidate:
                    return False, (
                        f"No eligible workforce candidate in organization matches requirements for task '{t_id}' "
                        f"(role: '{role}', capabilities: {list(req_caps)})."
                    )

        # Budget sufficiency check
        if budget_limit > 0 and plan.estimated_cost > budget_limit:
            return False, (
                f"Estimated plan cost (${plan.estimated_cost:.2f}) exceeds objective budget limit (${budget_limit:.2f})."
            )

        return True, None


class ObjectivePlanner:
    """Decomposes an Objective into a multi-milestone ExecutionPlan."""

    def __init__(self, organization: Optional[Organization] = None):
        self.organization = organization

    def plan(self, objective: Objective) -> ExecutionPlan:
        """Transforms an Objective into an ExecutionPlan with 4 milestones,
        explicit dependencies, task specifications, and cost estimations.
        """
        plan_id = f"plan_{objective.id}_{int(time.time())}"
        milestones: list[Milestone] = []
        tasks: list[dict] = []
        dependencies: dict[str, list[str]] = {}
        all_skills: set[str] = set()

        # Generate 4 sequential Milestones
        m1_id = f"m1_{objective.id}"
        m2_id = f"m2_{objective.id}"
        m3_id = f"m3_{objective.id}"
        m4_id = f"m4_{objective.id}"

        # --- Milestone 1: Research & Discovery ---
        t1_id = f"{objective.id}_t1_research"
        t1 = {
            "task_id": t1_id,
            "project_id": objective.project_id or objective.id,
            "milestone_id": m1_id,
            "title": f"Riset & Spesifikasi: {objective.title}",
            "description": f"Analisis kebutuhan, riset pasar, dan definisi spesifikasi teknis untuk {objective.title}.",
            "priority": 10,
            "preferred_role": "conceptor",
            "required_capabilities": ["requirements_analysis", "acceptance_criteria"],
        }
        tasks.append(t1)
        dependencies[t1_id] = []
        all_skills.update(t1["required_capabilities"])

        m1 = Milestone(
            milestone_id=m1_id,
            name="Riset & Spesifikasi",
            description="Analisis kebutuhan dan perumusan dokumen spesifikasi.",
            task_ids=[t1_id],
            order=1,
        )
        milestones.append(m1)

        # --- Milestone 2: Architecture & Design ---
        t2_id = f"{objective.id}_t2_design"
        t2 = {
            "task_id": t2_id,
            "project_id": objective.project_id or objective.id,
            "milestone_id": m2_id,
            "title": f"Perancangan Arsitektur & Wireframe: {objective.title}",
            "description": f"Pembuatan arsitektur sistem, struktur data, dan wireframe visual antarmuka.",
            "priority": 8,
            "preferred_role": "planner",
            "required_capabilities": ["software_architecture", "implementation_planning"],
        }
        tasks.append(t2)
        dependencies[t2_id] = [t1_id]
        all_skills.update(t2["required_capabilities"])

        m2 = Milestone(
            milestone_id=m2_id,
            name="Desain & Arsitektur",
            description="Perancangan arsitektur teknis dan cetak biru visual.",
            task_ids=[t2_id],
            order=2,
        )
        milestones.append(m2)

        # --- Milestone 3: Implementation ---
        t3_id = f"{objective.id}_t3_impl"
        t3 = {
            "task_id": t3_id,
            "project_id": objective.project_id or objective.id,
            "milestone_id": m3_id,
            "title": f"Implementasi Kode & Modul: {objective.title}",
            "description": f"Pengembangan komponen utama, integrasi fungsi, dan penulisan kode fungsional.",
            "priority": 6,
            "preferred_role": "developer",
            "required_capabilities": ["python", "modular_coding", "debugging"],
        }
        tasks.append(t3)
        dependencies[t3_id] = [t2_id]
        all_skills.update(t3["required_capabilities"])

        m3 = Milestone(
            milestone_id=m3_id,
            name="Implementasi",
            description="Pengembangan modul teknis dan konstruksi deliverable.",
            task_ids=[t3_id],
            order=3,
        )
        milestones.append(m3)

        # --- Milestone 4: QA & Acceptance Verification ---
        t4_id = f"{objective.id}_t4_qa"
        t4 = {
            "task_id": t4_id,
            "project_id": objective.project_id or objective.id,
            "milestone_id": m4_id,
            "title": f"Verifikasi Kualitas & Evaluasi Akhir: {objective.title}",
            "description": f"Pemeriksaan kualitas, pengujian regresi, dan validasi kriteria penerimaan.",
            "priority": 5,
            "preferred_role": "qa",
            "required_capabilities": ["automated_testing", "code_review", "bug_diagnosis"],
        }
        tasks.append(t4)
        dependencies[t4_id] = [t3_id]
        all_skills.update(t4["required_capabilities"])

        m4 = Milestone(
            milestone_id=m4_id,
            name="QA & Verifikasi",
            description="Verifikasi kualitas deliverable dan pengujian fungsionalitas.",
            task_ids=[t4_id],
            order=4,
        )
        milestones.append(m4)

        # Estimate cost: approx ~600 tokens per task * 4 tasks = 2400 tokens (~$0.005)
        estimated_cost = round(len(tasks) * 0.0025, 4)

        plan = ExecutionPlan(
            id=plan_id,
            objective_id=objective.id,
            milestones=milestones,
            tasks=tasks,
            dependencies=dependencies,
            estimated_cost=estimated_cost,
            required_skills=sorted(list(all_skills)),
            is_valid=True,
            validation_error=None,
        )

        # Validate generated plan immediately
        is_valid, err = PlanValidator.validate_plan(
            plan=plan,
            organization=self.organization,
            budget_limit=objective.budget,
        )
        plan.is_valid = is_valid
        plan.validation_error = err

        return plan


# Legacy compatibility alias
LegacyObjectivePlanner = ObjectivePlanner


def __getattr__(name: str):
    if name == "AdaptiveObjectivePlanner":
        from adaptive_planner import AdaptiveObjectivePlanner
        return AdaptiveObjectivePlanner
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


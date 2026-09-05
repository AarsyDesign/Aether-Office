"""Plan Quality Evaluator & Optimizer for Phase 9 Adaptive Planning.

Evaluates multi-dimensional plan quality, checks acceptance criteria coverage,
and optimizes execution graphs for cost, latency, and parallelism.
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from objectives import Objective
from planner import ExecutionPlan, PlanValidator
from workforce import Organization, STATUS_ACTIVE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlanQualityReport:
    """Consolidated assessment of plan quality and feasibility."""
    score: float                         # 0.0 to 100.0
    completeness_score: float = 0.0      # 0 to 20
    dependency_score: float = 0.0        # 0 to 20
    capability_score: float = 0.0        # 0 to 20
    budget_score: float = 0.0            # 0 to 20
    criteria_coverage_score: float = 0.0 # 0 to 20
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    @property
    def is_viable(self) -> bool:
        """Indicates if the plan has sufficient quality to proceed with execution."""
        return self.score >= 50.0 and len(self.issues) == 0

    @property
    def grade(self) -> str:
        if self.score >= 90:
            return "A+"
        if self.score >= 80:
            return "A"
        if self.score >= 70:
            return "B"
        if self.score >= 60:
            return "C"
        if self.score >= 50:
            return "D"
        return "F"

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "grade": self.grade,
            "completeness_score": round(self.completeness_score, 1),
            "dependency_score": round(self.dependency_score, 1),
            "capability_score": round(self.capability_score, 1),
            "budget_score": round(self.budget_score, 1),
            "criteria_coverage_score": round(self.criteria_coverage_score, 1),
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


class _EvaluatorDescriptor:
    def __get__(self, instance, owner=None):
        if instance is None:
            def class_call(plan: ExecutionPlan, objective: Objective, organization: Optional[Organization] = None) -> PlanQualityReport:
                return owner._evaluate_impl(plan, objective, organization)
            return class_call
        else:
            def instance_call(plan: ExecutionPlan, objective: Objective, organization: Optional[Organization] = None) -> PlanQualityReport:
                target_org = organization if organization is not None else getattr(instance, "organization", None)
                return owner._evaluate_impl(plan, objective, target_org)
            return instance_call


class PlanQualityEvaluator:
    """Rigorously evaluates the quality and execution feasibility of an ExecutionPlan."""

    def __init__(self, organization: Optional[Organization] = None):
        self.organization = organization

    @staticmethod
    def _evaluate_impl(
        plan: ExecutionPlan,
        objective: Objective,
        organization: Optional[Organization] = None,
    ) -> PlanQualityReport:
        issues: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        # 1. Completeness Score (0-20)
        c_score = 0.0
        if plan.tasks:
            c_score += 8.0
            if len(plan.tasks) >= 3:
                c_score += 4.0
            if plan.milestones:
                c_score += 4.0
            # All tasks have preferred role and capabilities
            all_specified = all(t.get("preferred_role") and t.get("required_capabilities") for t in plan.tasks)
            if all_specified:
                c_score += 4.0
            else:
                warnings.append("Sebagian tugas tidak memiliki preferensi role atau daftar kemampuan eksplisit.")
        else:
            issues.append("Rencana eksekusi tidak memuat satupun tugas (empty tasks).")

        # 2. Dependency Validity Score (0-20)
        d_score = 0.0
        is_valid_dag, dag_err = PlanValidator.validate_plan(plan, organization=None, budget_limit=0.0)
        if is_valid_dag:
            d_score = 20.0
        else:
            issues.append(f"Graf dependensi tugas tidak valid: {dag_err}")
            d_score = 0.0

        # 3. Capability Coverage Score (0-20)
        cap_score = 20.0
        if organization:
            active_emps = [e for e in organization.employees.list() if e.status == STATUS_ACTIVE]
            available_caps = set()
            available_roles = set()
            for e in active_emps:
                available_roles.add(e.role.lower())
                for c in e.capabilities:
                    available_caps.add(c.lower())

            uncovered_tasks = []
            for t in plan.tasks:
                t_role = (t.get("preferred_role") or "").lower()
                t_caps = set(c.lower() for c in t.get("required_capabilities", []))

                role_ok = any(t_role == r or t_role in r or r in t_role for r in available_roles) if t_role else False
                cap_ok = any(any(rc in ac or ac in rc for ac in available_caps) for rc in t_caps) if t_caps else False

                if not role_ok and not cap_ok:
                    uncovered_tasks.append(t.get("task_id", "unknown"))

            if uncovered_tasks:
                deduction = min(15.0, len(uncovered_tasks) * 5.0)
                cap_score -= deduction
                warnings.append(f"Workforce pool saat ini tidak memiliki kemampuan/kapabilitas untuk tugas: {uncovered_tasks} (keahlian tidak tersedia)")
                recommendations.append("Pertimbangkan rekrutmen spesialis atau sesuaikan kualifikasi tugas.")

        # 4. Budget Feasibility Score (0-20)
        b_score = 20.0
        if objective.budget > 0:
            if plan.estimated_cost > objective.budget:
                b_score = 0.0
                issues.append(f"Estimasi biaya (${plan.estimated_cost:.2f}) melampaui alokasi anggaran (${objective.budget:.2f}).")
                recommendations.append("Jalankan optimasi rencana untuk mereduksi model token atau pangkas tugas non-esensial.")
            elif plan.estimated_cost > (objective.budget * 0.85):
                b_score = 12.0
                warnings.append(f"Estimasi biaya (${plan.estimated_cost:.2f}) mendekati pagu anggaran (${objective.budget:.2f}).")
            else:
                b_score = 20.0

        # 5. Acceptance Criteria Coverage Score (0-20)
        crit_score = 20.0
        criteria_list = objective.acceptance_criteria.criteria if objective.acceptance_criteria else []
        if criteria_list:
            # Check if deliverables produced by plan align with criteria
            plan_text = " ".join([t.get("title", "") + " " + t.get("description", "") for t in plan.tasks]).lower()
            uncovered_criteria = []
            for c in criteria_list:
                c_name = c.name.lower()
                c_target = (c.target_value or "").lower()
                matched = (c_name in plan_text) or (c_target and c_target in plan_text)
                if not matched and c.required:
                    uncovered_criteria.append(c.name)

            if uncovered_criteria:
                crit_score = max(5.0, 20.0 - (len(uncovered_criteria) * 5.0))
                warnings.append(f"Kriteria penerimaan berikut belum tercakup eksplisit dalam deskripsi tugas: {uncovered_criteria}")
                recommendations.append("Pastikan tugas akhir memverifikasi kriteria penerimaan tersebut.")

        total_score = max(0.0, min(100.0, c_score + d_score + cap_score + b_score + crit_score))

        return PlanQualityReport(
            score=total_score,
            completeness_score=c_score,
            dependency_score=d_score,
            capability_score=cap_score,
            budget_score=b_score,
            criteria_coverage_score=crit_score,
            issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            metadata={
                "task_count": len(plan.tasks),
                "milestone_count": len(plan.milestones),
                "estimated_cost": plan.estimated_cost,
                "is_dag_valid": is_valid_dag,
            },
        )

    evaluate = _EvaluatorDescriptor()


class PlanOptimizer:
    """Optimizes an ExecutionPlan for latency (parallelism) and cost efficiency."""

    @classmethod
    def calculate_critical_path(cls, plan: ExecutionPlan) -> list[str]:
        """Calculates the longest path (critical path) of task dependencies."""
        task_ids = [t["task_id"] for t in plan.tasks]
        adj: dict[str, list[str]] = {t_id: [] for t_id in task_ids}
        in_deg = {t_id: 0 for t_id in task_ids}

        for t_id, deps in plan.dependencies.items():
            for d in deps:
                if d in adj:
                    adj[d].append(t_id)
                    in_deg[t_id] += 1

        dist = {t_id: 1 for t_id in task_ids}
        prev: dict[str, Optional[str]] = {t_id: None for t_id in task_ids}

        # Topological traversal
        queue = [t_id for t_id, deg in in_deg.items() if deg == 0]
        while queue:
            node = queue.pop(0)
            for nxt in adj[node]:
                if dist[node] + 1 > dist[nxt]:
                    dist[nxt] = dist[node] + 1
                    prev[nxt] = node
                in_deg[nxt] -= 1
                if in_deg[nxt] == 0:
                    queue.append(nxt)

        if not dist:
            return []

        end_node = max(dist, key=dist.get)
        path = []
        curr: Optional[str] = end_node
        while curr:
            path.append(curr)
            curr = prev[curr]
        path.reverse()
        return path

    @classmethod
    def optimize_plan(
        cls,
        plan: ExecutionPlan,
        objective: Objective,
        organization: Optional[Organization] = None,
    ) -> tuple[ExecutionPlan, bool, list[str]]:
        """Optimizes the plan by:
        1. Calculating critical path
        2. Identifying parallelizable tasks
        3. Pruning redundant dependencies
        4. Adjusting model tiers for cost compliance if budget is constrained
        Returns (optimized_plan, is_modified, list_of_optimizations).
        """
        optimizations: list[str] = []
        is_modified = False

        opt_plan = copy.deepcopy(plan)

        # 1. Critical path calculation
        crit_path = cls.calculate_critical_path(opt_plan)
        opt_plan.metadata["critical_path"] = crit_path
        if crit_path:
            opt_plan.metadata["critical_path_length"] = len(crit_path)

        # 2. Dependency Pruning (remove duplicate and redundant transitive edges)
        pruned_count = 0
        for t_id, deps in list(opt_plan.dependencies.items()):
            # Deduplicate list first
            unique_deps = list(dict.fromkeys(deps))
            if len(unique_deps) < len(deps):
                pruned_count += (len(deps) - len(unique_deps))
                deps = unique_deps
                opt_plan.dependencies[t_id] = deps

            if len(deps) > 1:
                # If dep A can reach dep B, then direct edge to A is redundant if order is preserved
                to_remove = set()
                for d1 in deps:
                    # check reachable from any other d2
                    for d2 in deps:
                        if d1 != d2 and d1 in opt_plan.dependencies.get(d2, []):
                            to_remove.add(d1)
                if to_remove:
                    opt_plan.dependencies[t_id] = [d for d in deps if d not in to_remove]
                    pruned_count += len(to_remove)

        if pruned_count > 0:
            is_modified = True
            optimizations.append(f"Dipangkas {pruned_count} relasi dependensi yang duplikat/redundan.")

        # 3. Parallelization tagging
        # Tasks in same milestone with same dependencies can execute concurrently
        for m in opt_plan.milestones:
            m_tasks = [t for t in opt_plan.tasks if t.get("milestone_id") == m.milestone_id]
            if len(m_tasks) > 1:
                dep_groups: dict[str, list[dict]] = {}
                for t in m_tasks:
                    dep_key = ",".join(sorted(opt_plan.dependencies.get(t["task_id"], [])))
                    dep_groups.setdefault(dep_key, []).append(t)
                for key, grp in dep_groups.items():
                    if len(grp) > 1:
                        for t in grp:
                            t["parallelizable"] = True
                        optimizations.append(f"Ditandai {len(grp)} tugas paralel dalam milestone '{m.name}'.")
                        is_modified = True

        # 4. Budget-Aware Model Tier Adjustment
        if objective.budget > 0 and opt_plan.estimated_cost > objective.budget:
            # Downscale model tiers on secondary/leaf tasks
            cost_reduced = 0.0
            for t in opt_plan.tasks:
                if t.get("priority", 5) <= 6 and t.get("model_tier") in ("strong", "standard"):
                    old_tier = t.get("model_tier")
                    new_tier = "cheap" if old_tier == "standard" else "standard"
                    t["model_tier"] = new_tier
                    cost_reduced += 0.001
                    is_modified = True
                    if opt_plan.estimated_cost - cost_reduced <= objective.budget:
                        break

            if cost_reduced > 0:
                opt_plan.estimated_cost = max(0.001, round(opt_plan.estimated_cost - cost_reduced, 4))
                optimizations.append(f"Penyesuaian tingkatan model (tier optimization) menghemat estimasi ${cost_reduced:.4f}.")

        return opt_plan, is_modified, optimizations

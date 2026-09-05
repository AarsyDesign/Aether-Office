"""Deterministic Task Assignment Matcher."""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from workforce import Employee, STATUS_ACTIVE, AVAILABILITY_AVAILABLE


class TaskMatcher:
    """Evaluates and ranks candidate employees for a given task using deterministic scoring."""

    SCORE_ROLE_MATCH = 20
    SCORE_CAPABILITY_MATCH = 10
    SCORE_DEPARTMENT_MATCH = 5
    PENALTY_PER_ACTIVE_TASK = 2

    @classmethod
    def score_candidate(
        cls,
        candidate: Employee,
        task: dict | Any,
        priority: Optional[str] = None,
        cost_rate: Optional[float] = None,
    ) -> int:
        """Score an employee candidate for a task using multi-factor matching:
        MATCH SCORE = skill compatibility + availability + priority + workload suitability + cost efficiency + historical performance.
        Returns -1 if candidate is disqualified.
        """
        # 1. Eligibility Check: Must be active and available
        if not getattr(candidate, "is_active", True) or candidate.status != STATUS_ACTIVE:
            return -1
        if candidate.availability != AVAILABILITY_AVAILABLE:
            return -1

        task_dict = task if isinstance(task, dict) else (task.to_dict() if hasattr(task, "to_dict") else {})
        score = 0

        # 2. Skill Compatibility & Specialization
        # Role Match (+20)
        target_role = task_dict.get("preferred_role") or task_dict.get("role") or task_dict.get("assigned_role")
        if target_role and candidate.role.lower() == target_role.lower():
            score += cls.SCORE_ROLE_MATCH

        # Department Match (+5)
        target_dept = task_dict.get("department")
        if target_dept and candidate.department.lower() == target_dept.lower():
            score += cls.SCORE_DEPARTMENT_MATCH

        # Capability Match (+10 per capability)
        req_caps = set(
            task_dict.get("required_capabilities")
            or task_dict.get("capabilities")
            or []
        )
        if req_caps:
            cand_caps = {c.lower() for c in candidate.capabilities}
            matches = len(cand_caps & {c.lower() for c in req_caps})
            score += matches * cls.SCORE_CAPABILITY_MATCH

        # 3. Priority Alignment
        task_priority = task_dict.get("priority", 0)
        if isinstance(task_priority, int) and task_priority >= 8:
            score += 5
        if priority in ("CRITICAL", "HIGH"):
            score += 5

        # 4. Workload Suitability (-2 per active task, -1 per queued task)
        active_tasks = getattr(candidate, "active_tasks", 0)
        queued_tasks = getattr(candidate, "queued_tasks", 0)
        score -= active_tasks * cls.PENALTY_PER_ACTIVE_TASK
        score -= queued_tasks * 1

        # 5. Cost Efficiency
        if cost_rate is not None:
            if cost_rate < 0.001:
                score += 5
            elif cost_rate > 0.003 and priority != "CRITICAL":
                score -= 3

        # 6. Historical Performance
        completed = getattr(candidate, "completed_tasks", 0)
        if completed > 0:
            score += min(5, completed // 5)

        return score

    @classmethod
    def rank_candidates(
        cls,
        task: dict | Any,
        candidates: list[Employee],
        priority: Optional[str] = None,
        cost_rates: Optional[dict[str, float]] = None,
    ) -> list[tuple[Employee, int]]:
        """Rank qualified candidate employees by score in descending order."""
        scored = []
        for c in candidates:
            c_rate = cost_rates.get(c.employee_id) if cost_rates else None
            s = cls.score_candidate(c, task, priority=priority, cost_rate=c_rate)
            if s >= 0:
                scored.append((c, s))

        # Sort by score descending; tiebreak by lowest active tasks, then number of capabilities, then employee_id
        scored.sort(
            key=lambda item: (item[1], -getattr(item[0], "active_tasks", 0), len(item[0].capabilities), item[0].employee_id),
            reverse=True,
        )
        return scored

    @classmethod
    def find_best_employee(
        cls, task: dict | Any, candidates: list[Employee]
    ) -> Optional[Employee]:
        """Find the single best matching candidate employee for a task."""
        ranked = cls.rank_candidates(task, candidates)
        if ranked:
            return ranked[0][0]
        return None

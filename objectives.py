"""Objective Model, Lifecycle State Machine, and Acceptance Criteria Framework for Phase 8."""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from projects import ProjectPriority


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ObjectiveStatus(str, Enum):
    """Explicit lifecycle states for an Objective."""
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    EXECUTING = "EXECUTING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


VALID_OBJECTIVE_TRANSITIONS: dict[ObjectiveStatus, set[ObjectiveStatus]] = {
    ObjectiveStatus.CREATED: {ObjectiveStatus.PLANNING, ObjectiveStatus.CANCELLED},
    ObjectiveStatus.PLANNING: {ObjectiveStatus.READY, ObjectiveStatus.FAILED, ObjectiveStatus.CANCELLED},
    ObjectiveStatus.READY: {ObjectiveStatus.EXECUTING, ObjectiveStatus.CANCELLED},
    ObjectiveStatus.EXECUTING: {ObjectiveStatus.EVALUATING, ObjectiveStatus.FAILED, ObjectiveStatus.CANCELLED},
    ObjectiveStatus.EVALUATING: {
        ObjectiveStatus.COMPLETED,
        ObjectiveStatus.EXECUTING,  # Revision loop re-execution
        ObjectiveStatus.FAILED,
        ObjectiveStatus.CANCELLED,
    },
    ObjectiveStatus.COMPLETED: set(),
    ObjectiveStatus.FAILED: {ObjectiveStatus.PLANNING},  # Re-plan / retry allowed
    ObjectiveStatus.CANCELLED: set(),
}


class InvalidObjectiveStateTransition(Exception):
    """Raised when an illegal transition is attempted on an Objective."""
    pass


def validate_objective_transition(from_status: ObjectiveStatus, to_status: ObjectiveStatus) -> None:
    """Validates whether transition between Objective statuses is strictly legal."""
    if not isinstance(from_status, ObjectiveStatus):
        from_status = ObjectiveStatus(from_status)
    if not isinstance(to_status, ObjectiveStatus):
        to_status = ObjectiveStatus(to_status)

    if from_status == to_status:
        return

    allowed = VALID_OBJECTIVE_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidObjectiveStateTransition(
            f"Illegal Objective transition from '{from_status.value}' to '{to_status.value}'. "
            f"Allowed next states: {[s.value for s in allowed]}"
        )


class CriterionType(str, Enum):
    """Supported types of acceptance criteria."""
    TEXT = "text_criteria"
    BOOLEAN = "boolean_criteria"
    ARTIFACT = "artifact_existence"
    TASK = "task_completion"
    TEST = "test_result"


@dataclass
class AcceptanceCriterion:
    """Explicit, verifiable Acceptance Criterion for an Objective."""
    name: str
    criterion_type: CriterionType
    description: str = ""
    target_value: Any = None
    required: bool = True
    metadata: dict = field(default_factory=dict)

    def evaluate(self, context: dict) -> tuple[bool, str]:
        """Evaluates criterion against execution outcome context:
        context keys typically include:
          - artifacts: list of Artifact objects or dicts
          - tasks: list of WorkTask objects or dicts
          - tests: dict of test results or pass/fail flags
          - output_text: aggregated deliverable string
          - custom: arbitrary flags/values
        """
        c_type = self.criterion_type
        if isinstance(c_type, str):
            c_type = CriterionType(c_type)

        if c_type == CriterionType.TEXT:
            # Check for keyword existence in deliverables/artifacts/tasks
            search_text = context.get("deliverables_text") or context.get("output_text") or ""
            if not search_text and "artifacts" in context:
                search_text = " ".join(
                    str(a.get("content", "") if isinstance(a, dict) else getattr(a, "content", ""))
                    for a in context.get("artifacts", [])
                )
            if not search_text and "tasks" in context:
                task_outputs = []
                for t in context.get("tasks", []):
                    res = t.get("result") if isinstance(t, dict) else getattr(t, "result", None)
                    if isinstance(res, dict) and res.get("output"):
                        task_outputs.append(str(res["output"]))
                    elif isinstance(res, str):
                        task_outputs.append(res)
                search_text = " ".join(task_outputs)

            target = str(self.target_value or self.name).lower()
            if target in search_text.lower():
                return True, f"Text criterion '{self.name}' met (found keyword '{target}')."
            return False, f"Text criterion '{self.name}' failed: '{target}' not found in deliverables."

        elif c_type == CriterionType.BOOLEAN:
            # Check boolean condition in context custom flags
            flags = context.get("flags", {})
            val = flags.get(self.name, context.get(self.name))
            expected = bool(self.target_value if self.target_value is not None else True)
            if bool(val) == expected:
                return True, f"Boolean criterion '{self.name}' met."
            return False, f"Boolean criterion '{self.name}' failed (expected {expected}, got {val})."

        elif c_type == CriterionType.ARTIFACT:
            # Check existence of deliverable artifact matching name or type
            artifacts = context.get("artifacts", [])
            target = str(self.target_value or self.name).lower()
            found = False
            for art in artifacts:
                art_name = art.get("name", "") if isinstance(art, dict) else getattr(art, "name", "")
                art_type = art.get("type", "") if isinstance(art, dict) else getattr(art, "type", "")
                if target in art_name.lower() or target in art_type.lower():
                    found = True
                    break
            if found or (not self.target_value and len(artifacts) > 0):
                return True, f"Artifact criterion '{self.name}' met (matching artifact found)."
            return False, f"Artifact criterion '{self.name}' failed: no matching artifact found."

        elif c_type == CriterionType.TASK:
            # Check that all or specific tasks reached COMPLETED status
            tasks = context.get("tasks", [])
            target_task_id = self.target_value
            if target_task_id:
                for t in tasks:
                    t_id = t.get("task_id") if isinstance(t, dict) else getattr(t, "task_id", "")
                    t_stat = t.get("status") if isinstance(t, dict) else getattr(t, "status", "")
                    if t_id == target_task_id:
                        if t_stat == "COMPLETED":
                            return True, f"Task '{target_task_id}' completed successfully."
                        return False, f"Task '{target_task_id}' status is '{t_stat}', expected COMPLETED."
                return False, f"Task '{target_task_id}' not found in task list."
            else:
                # All tasks must be completed
                if not tasks:
                    return False, "No tasks were executed."
                incomplete = []
                for t in tasks:
                    t_id = t.get("task_id") if isinstance(t, dict) else getattr(t, "task_id", "")
                    t_stat = t.get("status") if isinstance(t, dict) else getattr(t, "status", "")
                    if t_stat != "COMPLETED":
                        incomplete.append(f"{t_id} ({t_stat})")
                if not incomplete:
                    return True, f"All {len(tasks)} tasks completed successfully."
                return False, f"Incomplete tasks: {', '.join(incomplete)}."

        elif c_type == CriterionType.TEST:
            # Check test suite outcome
            test_results = context.get("tests", {})
            passed = test_results.get("passed", False)
            failures = test_results.get("failures", 0)
            if passed or (failures == 0 and test_results.get("total", 0) > 0):
                return True, f"Test criterion '{self.name}' passed."
            return False, f"Test criterion '{self.name}' failed: {failures} failures recorded."

        return True, "Criterion passed."

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "criterion_type": self.criterion_type.value if isinstance(self.criterion_type, CriterionType) else str(self.criterion_type),
            "description": self.description,
            "target_value": self.target_value,
            "required": self.required,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict) -> AcceptanceCriterion:
        return cls(
            name=d["name"],
            criterion_type=CriterionType(d.get("criterion_type", CriterionType.TEXT)),
            description=d.get("description", ""),
            target_value=d.get("target_value"),
            required=d.get("required", True),
            metadata=d.get("metadata", {}) or {},
        )


class AcceptanceCriteriaSet:
    """Collection of Acceptance Criteria for an Objective."""

    def __init__(self, criteria: Optional[list[AcceptanceCriterion]] = None):
        self.criteria: list[AcceptanceCriterion] = list(criteria) if criteria else []

    def add_criterion(self, criterion: AcceptanceCriterion) -> None:
        self.criteria.append(criterion)

    def evaluate_all(self, context: dict) -> tuple[bool, list[dict]]:
        """Evaluates all criteria against the context.
        Returns (all_passed, criteria_results).
        """
        all_passed = True
        results = []
        for crit in self.criteria:
            passed, feedback = crit.evaluate(context)
            results.append({
                "name": crit.name,
                "type": crit.criterion_type.value if isinstance(crit.criterion_type, CriterionType) else str(crit.criterion_type),
                "passed": passed,
                "feedback": feedback,
                "required": crit.required,
            })
            if crit.required and not passed:
                all_passed = False

        return all_passed, results

    def __iter__(self):
        return iter(self.criteria)

    def __len__(self) -> int:
        return len(self.criteria)

    def to_list(self) -> list[dict]:
        return [c.to_dict() for c in self.criteria]

    @classmethod
    def from_list(cls, items) -> AcceptanceCriteriaSet:
        if isinstance(items, AcceptanceCriteriaSet):
            return items
        if not items:
            return cls([])
        criteria = []
        for item in items:
            if isinstance(item, AcceptanceCriterion):
                criteria.append(item)
            elif isinstance(item, dict):
                criteria.append(AcceptanceCriterion.from_dict(item))
            elif isinstance(item, str):
                # Auto-wrap raw string into a text criteria
                criteria.append(AcceptanceCriterion(
                    name=item,
                    criterion_type=CriterionType.TEXT,
                    description=f"Requires {item}",
                    target_value=item,
                ))
        return cls(criteria)


@dataclass
class Objective:
    """Master Objective domain model."""
    id: str
    title: str
    description: str = ""
    status: ObjectiveStatus = ObjectiveStatus.CREATED
    priority: ProjectPriority = ProjectPriority.NORMAL
    deadline: Optional[str] = None
    budget: float = 0.0
    acceptance_criteria: AcceptanceCriteriaSet = field(default_factory=AcceptanceCriteriaSet)
    project_id: Optional[str] = None
    execution_plan_id: Optional[str] = None
    revision_count: int = 0
    max_revisions: int = 3
    result: dict = field(default_factory=dict)
    failure_reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def transition_to(self, target_status: ObjectiveStatus, reason: Optional[str] = None) -> None:
        """Atomically transition Objective to next state enforcing lifecycle rules."""
        validate_objective_transition(self.status, target_status)
        self.status = target_status
        now = _now_iso()

        if target_status == ObjectiveStatus.EXECUTING and not self.started_at:
            self.started_at = now
        elif target_status in (ObjectiveStatus.COMPLETED, ObjectiveStatus.FAILED, ObjectiveStatus.CANCELLED):
            self.completed_at = now
            if reason:
                self.failure_reason = reason

    def is_terminal(self) -> bool:
        """Returns True if objective is in an immutable end state."""
        return self.status in (ObjectiveStatus.COMPLETED, ObjectiveStatus.FAILED, ObjectiveStatus.CANCELLED)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value if isinstance(self.status, ObjectiveStatus) else str(self.status),
            "priority": self.priority.value if isinstance(self.priority, ProjectPriority) else str(self.priority),
            "deadline": self.deadline,
            "budget": self.budget,
            "acceptance_criteria": self.acceptance_criteria.to_list(),
            "project_id": self.project_id,
            "execution_plan_id": self.execution_plan_id,
            "revision_count": self.revision_count,
            "max_revisions": self.max_revisions,
            "result": dict(self.result),
            "failure_reason": self.failure_reason,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Objective:
        raw_status = d.get("status", ObjectiveStatus.CREATED)
        status = ObjectiveStatus(raw_status) if isinstance(raw_status, str) else raw_status

        raw_priority = d.get("priority", ProjectPriority.NORMAL)
        priority = ProjectPriority(raw_priority) if isinstance(raw_priority, str) else raw_priority

        raw_criteria = d.get("acceptance_criteria", [])
        if isinstance(raw_criteria, AcceptanceCriteriaSet):
            criteria_set = raw_criteria
        else:
            criteria_set = AcceptanceCriteriaSet.from_list(raw_criteria or [])

        return cls(
            id=d["id"],
            title=d["title"],
            description=d.get("description", ""),
            status=status,
            priority=priority,
            deadline=d.get("deadline"),
            budget=float(d.get("budget", 0.0)),
            acceptance_criteria=criteria_set,
            project_id=d.get("project_id"),
            execution_plan_id=d.get("execution_plan_id"),
            revision_count=int(d.get("revision_count", 0)),
            max_revisions=int(d.get("max_revisions", 3)),
            result=d.get("result", {}) or {},
            failure_reason=d.get("failure_reason"),
            metadata=d.get("metadata", {}) or {},
            created_at=d.get("created_at") or _now_iso(),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
        )

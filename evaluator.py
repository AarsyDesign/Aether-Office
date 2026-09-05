"""Artifact & Outcome Evaluator for Phase 8 Objective-to-Outcome Engine."""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from objectives import Objective, ObjectiveStatus, AcceptanceCriteriaSet
from artifacts import Artifact
from tasks import WorkTask


class EvaluationVerdict(str, Enum):
    """Possible outcomes of an objective outcome evaluation."""
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVISION = "NEEDS_REVISION"


@dataclass
class EvaluationResult:
    """Detailed outcome evaluation result."""
    verdict: EvaluationVerdict
    criteria_results: list[dict] = field(default_factory=list)
    feedback: str = ""
    revision_tasks: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value if isinstance(self.verdict, EvaluationVerdict) else str(self.verdict),
            "criteria_results": list(self.criteria_results),
            "feedback": self.feedback,
            "revision_tasks": list(self.revision_tasks),
            "metadata": dict(self.metadata),
        }


class OutcomeEvaluator:
    """Evaluates task execution outcomes and generated artifacts against Objective Acceptance Criteria."""

    def __init__(self, default_max_revisions: int = 3):
        self.default_max_revisions = default_max_revisions

    def evaluate(
        self,
        objective: Objective,
        tasks: list[WorkTask | dict],
        artifacts: list[Artifact | dict],
        test_results: Optional[dict] = None,
        custom_flags: Optional[dict] = None,
    ) -> EvaluationResult:
        """Evaluates deliverables against acceptance criteria and determines outcome verdict."""
        # 1. Compile consolidated evaluation context
        task_dicts = [t if isinstance(t, dict) else t.to_dict() for t in tasks]
        artifact_dicts = [a if isinstance(a, dict) else a.to_dict() for a in artifacts]

        output_fragments = []
        for a in artifact_dicts:
            if a.get("content"):
                output_fragments.append(str(a["content"]))
        for t in task_dicts:
            res = t.get("result")
            if isinstance(res, dict) and res.get("output"):
                output_fragments.append(str(res["output"]))
            elif isinstance(res, str):
                output_fragments.append(res)

        output_text = "\n".join(output_fragments)

        context = {
            "objective_id": objective.id,
            "tasks": task_dicts,
            "artifacts": artifact_dicts,
            "tests": test_results or {},
            "flags": custom_flags or {},
            "output_text": output_text,
            "deliverables_text": output_text,
        }

        # 2. Evaluate criteria set
        all_passed, criteria_details = objective.acceptance_criteria.evaluate_all(context)

        # 3. Formulate verdict
        if all_passed:
            return EvaluationResult(
                verdict=EvaluationVerdict.PASS,
                criteria_results=criteria_details,
                feedback=f"Seluruh {len(criteria_details)} kriteria penerimaan berhasil dipenuhi dengan sukses.",
                revision_tasks=[],
                metadata={"evaluated_artifacts_count": len(artifacts), "evaluated_tasks_count": len(tasks)},
            )

        failed_criteria = [c for c in criteria_details if not c.get("passed") and c.get("required", True)]
        failed_names = [c["name"] for c in failed_criteria]
        max_rev = objective.max_revisions if objective.max_revisions > 0 else self.default_max_revisions

        if objective.revision_count < max_rev:
            # Generate targeted revision task
            rev_task_id = f"{objective.id}_rev_{objective.revision_count + 1}"
            rev_title = f"Perbaikan & Revisi #{objective.revision_count + 1}: {', '.join(failed_names[:2])}"
            rev_desc = (
                f"Lakukan perbaikan deliverable objektif '{objective.title}'. "
                f"Kriteria yang belum terpenuhi: {'; '.join(c['feedback'] for c in failed_criteria)}."
            )

            revision_task = {
                "task_id": rev_task_id,
                "project_id": objective.project_id or objective.id,
                "title": rev_title,
                "description": rev_desc,
                "priority": 15,  # High priority to resolve quickly
                "preferred_role": "developer",
                "required_capabilities": ["debugging", "python"],
                "dependencies": [t["task_id"] for t in task_dicts[-2:] if "task_id" in t],  # Depend on last executed tasks
            }

            feedback_msg = (
                f"Ditemukan {len(failed_criteria)} kriteria yang belum terpenuhi. "
                f"Meminta siklus revisi #{objective.revision_count + 1} (maksimum {max_rev}). "
                f"Detail: {', '.join(failed_names)}"
            )

            return EvaluationResult(
                verdict=EvaluationVerdict.NEEDS_REVISION,
                criteria_results=criteria_details,
                feedback=feedback_msg,
                revision_tasks=[revision_task],
                metadata={"failed_criteria_count": len(failed_criteria), "attempt": objective.revision_count + 1},
            )
        else:
            # Exceeded maximum revisions
            feedback_msg = (
                f"Batas maksimum revisi ({max_rev}) telah tercapai, namun kriteria penerimaan "
                f"tetap belum terpenuhi: {', '.join(failed_names)}."
            )
            return EvaluationResult(
                verdict=EvaluationVerdict.FAIL,
                criteria_results=criteria_details,
                feedback=feedback_msg,
                revision_tasks=[],
                metadata={"failed_criteria_count": len(failed_criteria), "max_revisions_exceeded": True},
            )

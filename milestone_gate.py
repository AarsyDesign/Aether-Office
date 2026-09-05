"""Intermediate Milestone Gating for Phase 9 Adaptive Planning.

Provides sequential quality gate validation at milestone boundaries,
ensuring prerequisites and deliverables pass before the next milestone executes.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from objectives import AcceptanceCriterion, AcceptanceCriteriaSet, CriterionType
from artifacts import Artifact


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MilestoneGateStatus(str, Enum):
    """Execution status of an intermediate milestone quality gate."""
    PENDING = "PENDING"
    PASSED = "PASSED"
    NEEDS_REVISION = "NEEDS_REVISION"
    FAILED = "FAILED"


@dataclass
class MilestoneGate:
    """Quality gate attached to a specific milestone."""
    milestone_id: str
    name: str
    order: int = 1
    gating_criteria: AcceptanceCriteriaSet = field(default_factory=AcceptanceCriteriaSet)
    status: MilestoneGateStatus = MilestoneGateStatus.PENDING
    feedback: str = ""
    revision_count: int = 0
    max_revisions: int = 2
    evaluated_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "milestone_id": self.milestone_id,
            "name": self.name,
            "order": self.order,
            "status": self.status.value,
            "feedback": self.feedback,
            "revision_count": self.revision_count,
            "max_revisions": self.max_revisions,
            "gating_criteria": self.gating_criteria.to_list(),
            "evaluated_at": self.evaluated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict) -> MilestoneGate:
        crit_set = AcceptanceCriteriaSet.from_list(d.get("gating_criteria", []))
        return cls(
            milestone_id=d["milestone_id"],
            name=d.get("name", "Milestone Gate"),
            order=int(d.get("order", 1)),
            gating_criteria=crit_set,
            status=MilestoneGateStatus(d.get("status", MilestoneGateStatus.PENDING)),
            feedback=d.get("feedback", ""),
            revision_count=int(d.get("revision_count", 0)),
            max_revisions=int(d.get("max_revisions", 2)),
            evaluated_at=d.get("evaluated_at"),
            metadata=dict(d.get("metadata", {})),
        )


class MilestoneGateEvaluator:
    """Evaluates intermediate deliverables produced at the conclusion of a milestone."""

    @classmethod
    def evaluate_gate(
        cls,
        gate: MilestoneGate,
        tasks: list[Any],
        artifacts: list[Any],
    ) -> tuple[MilestoneGateStatus, str, list[dict], list[dict]]:
        """Evaluates gating criteria for the given milestone tasks and deliverables.
        Returns (status, feedback, criteria_results, revision_tasks).
        """
        gate.evaluated_at = _now_iso()

        # Compile evaluation context
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
        combined_text = "\n".join(output_fragments)

        context = {
            "tasks": task_dicts,
            "artifacts": artifact_dicts,
            "deliverables_text": combined_text,
            "output_text": combined_text,
        }

        # If no explicit gating criteria, default to verifying all milestone tasks are COMPLETED
        if not gate.gating_criteria or len(gate.gating_criteria) == 0:
            all_done = bool(task_dicts) and all(t.get("status") == "COMPLETED" for t in task_dicts)
            if all_done:
                gate.status = MilestoneGateStatus.PASSED
                gate.feedback = f"Seluruh {len(task_dicts)} tugas pada milestone '{gate.name}' selesai sempurna."
                return gate.status, gate.feedback, [], []
            else:
                gate.status = MilestoneGateStatus.FAILED
                gate.feedback = f"Sebagian tugas pada milestone '{gate.name}' belum berstatus COMPLETED."
                return gate.status, gate.feedback, [], []

        # Evaluate criteria set
        all_passed, results = gate.gating_criteria.evaluate_all(context)

        if all_passed:
            gate.status = MilestoneGateStatus.PASSED
            gate.feedback = f"Gerbang kualitas milestone '{gate.name}' LOLOS. Seluruh kriteria terpenuhi."
            return gate.status, gate.feedback, results, []

        failed = [r for r in results if not r.get("passed") and r.get("required", True)]
        failed_names = [f["name"] for f in failed]

        if gate.revision_count < gate.max_revisions:
            gate.revision_count += 1
            gate.status = MilestoneGateStatus.NEEDS_REVISION
            gate.feedback = (
                f"Gerbang kualitas milestone '{gate.name}' memerlukan revisi "
                f"(Percobaan {gate.revision_count}/{gate.max_revisions}). "
                f"Kriteria belum terpenuhi: {', '.join(failed_names)}."
            )

            # Generate targeted milestone revision task
            rev_task_id = f"gate_rev_{gate.milestone_id}_{gate.revision_count}"
            rev_task = {
                "task_id": rev_task_id,
                "project_id": task_dicts[0].get("project_id", "project") if task_dicts else "project",
                "milestone_id": gate.milestone_id,
                "title": f"Revisi Gerbang Milestone '{gate.name}': {', '.join(failed_names[:2])}",
                "description": f"Perbaiki deliverable milestone {gate.name}. Catatan: {gate.feedback}",
                "priority": 12,
                "preferred_role": "developer",
                "required_capabilities": ["debugging", "python"],
                "dependencies": [t["task_id"] for t in task_dicts if "task_id" in t],
            }
            return gate.status, gate.feedback, results, [rev_task]

        else:
            gate.status = MilestoneGateStatus.FAILED
            gate.feedback = (
                f"Batas revisi gerbang milestone '{gate.name}' ({gate.max_revisions}) terlampaui. "
                f"Kriteria gagal: {', '.join(failed_names)}."
            )
            return gate.status, gate.feedback, results, []

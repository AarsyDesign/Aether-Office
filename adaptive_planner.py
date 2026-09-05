"""Adaptive Objective Planner for Phase 9.

Orchestrates multi-phase adaptive planning:
Objective -> Analyze -> Classify -> Complexity -> Strategy Selection ->
Plan Generation -> Validation -> Quality Check -> Optimization -> Final Plan.
"""

from __future__ import annotations
import uuid
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

from objectives import Objective, ObjectiveStatus
from planner import ExecutionPlan, Milestone, PlanValidator, ObjectivePlanner
from analysis import (
    ObjectiveType,
    ObjectiveComplexity,
    ObjectiveAnalysis,
    ObjectiveAnalyzer,
    ClarificationRequest,
)
from strategies import (
    PlanningStrategy,
    get_strategy_for_type,
    SoftwarePlanningStrategy,
    GeneralPlanningStrategy,
)
from plan_evaluator import PlanQualityEvaluator, PlanQualityReport, PlanOptimizer
from milestone_gate import MilestoneGate, MilestoneGateStatus
from workforce import Organization
from events import (
    EventBus,
    Event,
    EVENT_OBJECTIVE_ANALYSIS_STARTED,
    EVENT_OBJECTIVE_ANALYZED,
    EVENT_PLANNING_STRATEGY_SELECTED,
    EVENT_PLAN_GENERATED,
    EVENT_PLAN_VALIDATED,
    EVENT_PLAN_QUALITY_EVALUATED,
    EVENT_PLAN_OPTIMIZATION_STARTED,
    EVENT_PLAN_OPTIMIZATION_COMPLETED,
    EVENT_CLARIFICATION_REQUIRED,
)

logger = logging.getLogger("aether.adaptive_planner")


class LLMPlannerAssistant:
    """Optional LLM assistance interface with strictly validated schema boundary."""

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def suggest_plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
    ) -> Optional[dict]:
        """Calls LLM for planning suggestions.
        Returns raw plan dict or None if LLM is unavailable or fails.
        """
        if not self.llm_client:
            return None

        prompt = (
            f"Generate structured tasks for objective: {objective.title}\n"
            f"Domain: {analysis.objective_type.value}, Complexity: {analysis.complexity.value}\n"
            "Format: JSON list of milestones with tasks."
        )
        try:
            # Safe call boundary
            raw_response = self.llm_client(prompt)
            if isinstance(raw_response, dict) and "tasks" in raw_response:
                return raw_response
            return None
        except Exception as e:
            logger.warning(f"LLM planner assistant call failed: {e}. Falling back to deterministic strategy.")
            return None


class AdaptiveObjectivePlanner:
    """Master intelligent planner decomposing Objectives dynamically based on domain and context."""

    def __init__(
        self,
        organization: Optional[Organization] = None,
        analyzer: Optional[ObjectiveAnalyzer] = None,
        llm_assistant: Optional[LLMPlannerAssistant] = None,
        enable_optimization: bool = True,
        enable_milestone_gating: bool = True,
        event_bus: Optional[EventBus] = None,
    ):
        self.organization = organization
        self.analyzer = analyzer or ObjectiveAnalyzer(organization=organization)
        self.llm_assistant = llm_assistant or LLMPlannerAssistant()
        self.enable_optimization = enable_optimization
        self.enable_milestone_gating = enable_milestone_gating
        self.event_bus = event_bus

    def _emit(self, event_type: str, project_id: Optional[str], payload: dict) -> None:
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=event_type,
                    project_id=project_id,
                    payload=payload,
                )
            )

    def analyze(self, objective: Objective) -> ObjectiveAnalysis:
        """Analyzes domain, complexity, ambiguity, and risk for the objective."""
        self._emit(EVENT_OBJECTIVE_ANALYSIS_STARTED, objective.project_id, {"objective_id": objective.id})
        analysis = self.analyzer.analyze(objective)
        self._emit(
            EVENT_OBJECTIVE_ANALYZED,
            objective.project_id,
            {
                "objective_id": objective.id,
                "objective_type": analysis.objective_type.value,
                "complexity": analysis.complexity.value,
                "confidence": analysis.confidence,
                "ambiguity": analysis.ambiguity,
            },
        )
        return analysis

    def plan(self, objective: Objective) -> ExecutionPlan:
        """Executes the end-to-end adaptive planning pipeline."""
        # 1. Analyze Objective
        analysis = self.analyze(objective)

        # 2. Ambiguity & Clarification Gate
        if analysis.needs_clarification and any(c.blocking for c in analysis.clarifications):
            blocking_questions = [c.question for c in analysis.clarifications if c.blocking]
            error_msg = f"Objektif memerlukan klarifikasi sebelum dapat direncanakan: {'; '.join(blocking_questions)}"
            plan_id = f"plan_clarify_{objective.id}_{int(time.time())}"
            self._emit(
                EVENT_CLARIFICATION_REQUIRED,
                objective.project_id,
                {
                    "objective_id": objective.id,
                    "clarifications": [c.to_dict() for c in analysis.clarifications],
                },
            )
            return ExecutionPlan(
                id=plan_id,
                objective_id=objective.id,
                tasks=[],
                dependencies={},
                is_valid=False,
                validation_error=error_msg,
                metadata={
                    "needs_clarification": True,
                    "clarifications": [c.to_dict() for c in analysis.clarifications],
                    "analysis": analysis.to_dict(),
                    "confidence": analysis.confidence,
                },
            )

        # 3. Select Planning Strategy
        strategy = get_strategy_for_type(analysis.objective_type)
        self._emit(
            EVENT_PLANNING_STRATEGY_SELECTED,
            objective.project_id,
            {
                "objective_id": objective.id,
                "strategy": strategy.strategy_name,
                "objective_type": analysis.objective_type.value,
            },
        )

        # 4. Generate ExecutionPlan (with optional LLM assistant and deterministic fallback)
        plan: Optional[ExecutionPlan] = None
        used_llm = False

        llm_dict = self.llm_assistant.suggest_plan(objective, analysis)
        if llm_dict:
            try:
                # Schema validation for LLM output
                candidate_plan = ExecutionPlan.from_dict(llm_dict)
                is_dag_valid, dag_err = PlanValidator.validate_plan(
                    candidate_plan,
                    organization=self.organization,
                    budget_limit=objective.budget,
                )
                if is_dag_valid:
                    plan = candidate_plan
                    used_llm = True
                else:
                    logger.warning(f"LLM proposed plan rejected by deterministic PlanValidator: {dag_err}. Using deterministic strategy fallback.")
            except Exception as ex:
                logger.warning(f"Failed to parse LLM plan proposal: {ex}. Using fallback.")

        if not plan:
            # Deterministic domain strategy execution
            plan = strategy.plan(objective, analysis, organization=self.organization)

        self._emit(
            EVENT_PLAN_GENERATED,
            objective.project_id,
            {
                "objective_id": objective.id,
                "plan_id": plan.id,
                "tasks_count": len(plan.tasks),
                "milestones_count": len(plan.milestones),
            },
        )

        # 5. Deterministic Validation (Kahn's DAG sort, workforce feasibility, budget limit)
        is_valid, val_err = PlanValidator.validate_plan(
            plan,
            organization=self.organization,
            budget_limit=objective.budget,
        )
        plan.is_valid = is_valid
        plan.validation_error = val_err

        self._emit(
            EVENT_PLAN_VALIDATED,
            objective.project_id,
            {
                "objective_id": objective.id,
                "plan_id": plan.id,
                "is_valid": is_valid,
                "validation_error": val_err,
            },
        )

        # 6. Quality Evaluation
        quality_report = PlanQualityEvaluator.evaluate(
            plan=plan,
            objective=objective,
            organization=self.organization,
        )

        self._emit(
            EVENT_PLAN_QUALITY_EVALUATED,
            objective.project_id,
            {
                "objective_id": objective.id,
                "plan_id": plan.id,
                "score": quality_report.score,
                "grade": quality_report.grade,
            },
        )

        # 7. Plan Optimization (if valid and enabled)
        optimizations = []
        if plan.is_valid and self.enable_optimization:
            self._emit(
                EVENT_PLAN_OPTIMIZATION_STARTED,
                objective.project_id,
                {"objective_id": objective.id, "plan_id": plan.id},
            )
            opt_plan, is_modified, opt_notes = PlanOptimizer.optimize_plan(
                plan=plan,
                objective=objective,
                organization=self.organization,
            )
            if is_modified:
                plan = opt_plan
                optimizations = opt_notes

            self._emit(
                EVENT_PLAN_OPTIMIZATION_COMPLETED,
                objective.project_id,
                {
                    "objective_id": objective.id,
                    "plan_id": plan.id,
                    "modified": is_modified,
                    "optimizations": optimizations,
                },
            )

        # 8. Setup Milestone Quality Gates (if enabled)
        milestone_gates = {}
        if self.enable_milestone_gating and plan.milestones:
            for idx, m in enumerate(plan.milestones):
                gate = MilestoneGate(
                    milestone_id=m.milestone_id,
                    name=m.name,
                    order=m.order or (idx + 1),
                    status=MilestoneGateStatus.PENDING,
                )
                milestone_gates[m.milestone_id] = gate.to_dict()

        # 9. Enrich Metadata
        plan.metadata.update({
            "strategy": strategy.strategy_name,
            "objective_type": analysis.objective_type.value,
            "complexity": analysis.complexity.value,
            "confidence": analysis.confidence,
            "confidence_level": analysis.confidence_level,
            "quality_score": quality_report.score,
            "quality_grade": quality_report.grade,
            "quality_report": quality_report.to_dict(),
            "analysis": analysis.to_dict(),
            "optimizations": optimizations,
            "used_llm_assist": used_llm,
            "milestone_gates": milestone_gates,
        })

        return plan

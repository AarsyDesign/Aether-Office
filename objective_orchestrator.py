"""Objective Orchestrator for Phase 8 & 9: Autonomous Objective-to-Outcome Engine."""

from __future__ import annotations
import uuid
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

from objectives import (
    Objective,
    ObjectiveStatus,
    AcceptanceCriterion,
    AcceptanceCriteriaSet,
    CriterionType,
)
from planner import ObjectivePlanner, ExecutionPlan, PlanValidator
from adaptive_planner import AdaptiveObjectivePlanner
from analysis import ObjectiveAnalyzer, ObjectiveAnalysis
from plan_evaluator import PlanQualityEvaluator, PlanQualityReport, PlanOptimizer
from milestone_gate import MilestoneGate, MilestoneGateStatus, MilestoneGateEvaluator
from evaluator import OutcomeEvaluator, EvaluationVerdict, EvaluationResult
from office import OfficeOrchestrator
from projects import Project, ProjectStatus, ProjectPriority
from tasks import WorkTask, TASK_COMPLETED
from events import (
    EventBus,
    Event,
    EVENT_OBJECTIVE_CREATED,
    EVENT_OBJECTIVE_PLANNING_STARTED,
    EVENT_OBJECTIVE_PLAN_CREATED,
    EVENT_OBJECTIVE_PLAN_FAILED,
    EVENT_OBJECTIVE_STARTED,
    EVENT_OBJECTIVE_EVALUATION_STARTED,
    EVENT_OBJECTIVE_REVISION_REQUESTED,
    EVENT_OBJECTIVE_COMPLETED,
    EVENT_OBJECTIVE_FAILED,
    EVENT_OBJECTIVE_ANALYSIS_STARTED,
    EVENT_OBJECTIVE_ANALYZED,
    EVENT_PLANNING_STRATEGY_SELECTED,
    EVENT_PLAN_GENERATED,
    EVENT_PLAN_VALIDATED,
    EVENT_PLAN_QUALITY_EVALUATED,
    EVENT_PLAN_OPTIMIZATION_STARTED,
    EVENT_PLAN_OPTIMIZATION_COMPLETED,
    EVENT_CLARIFICATION_REQUIRED,
    EVENT_MILESTONE_EVALUATION_STARTED,
    EVENT_MILESTONE_GATE_PASSED,
    EVENT_MILESTONE_GATE_FAILED,
)
from db import Database

logger = logging.getLogger("aether.objective_orchestrator")


class ObjectiveOrchestrator:
    """Master orchestrator converting high-level Objectives into verified business Outcomes.
    Coordinates:
    Objective -> ObjectiveAnalyzer -> PlanningStrategy -> ExecutionPlan ->
    PlanValidator -> PlanQualityEvaluator -> PlanOptimizer ->
    Milestone Quality Gates -> Workforce Execution -> ArtifactStore ->
    OutcomeEvaluator -> Self-Correction Revision Loop -> Outcome.
    """

    def __init__(
        self,
        office_orchestrator: OfficeOrchestrator,
        planner: Optional[Any] = None,
        evaluator: Optional[OutcomeEvaluator] = None,
        db: Optional[Database] = None,
        event_bus: Optional[EventBus] = None,
        use_adaptive: bool = False,
    ):
        self.office = office_orchestrator
        self.db = db or getattr(office_orchestrator, "db", None)
        self.event_bus = event_bus or getattr(office_orchestrator, "event_bus", None)
        if planner is not None:
            self.planner = planner
        elif use_adaptive:
            self.planner = AdaptiveObjectivePlanner(
                organization=office_orchestrator.organization,
                event_bus=self.event_bus,
            )
        else:
            self.planner = ObjectivePlanner()
        self.evaluator = evaluator or OutcomeEvaluator()
        self.analyzer = ObjectiveAnalyzer(organization=office_orchestrator.organization)
        self.milestone_gate_evaluator = MilestoneGateEvaluator()
        self.plan_quality_evaluator = PlanQualityEvaluator(organization=office_orchestrator.organization)

        self._objectives: dict[str, Objective] = {}
        self._plans: dict[str, ExecutionPlan] = {}

        # Sync existing objectives from DB if available
        self._load_objectives_from_db()

        # Execute cold-start recovery on initialization
        self.recover_objectives()

    def _load_objectives_from_db(self) -> None:
        """Load stored objectives from SQLite database."""
        if not self.db:
            return
        try:
            records = self.db.list_objectives()
            for r in records:
                obj = Objective.from_dict(r)
                self._objectives[obj.id] = obj
        except Exception as e:
            logger.warning(f"Could not load objectives from DB: {e}")

    def create_objective(
        self,
        title: str,
        description: str = "",
        budget: float = 0.0,
        deadline: Optional[str] = None,
        priority: ProjectPriority = ProjectPriority.NORMAL,
        acceptance_criteria: Optional[list[AcceptanceCriterion | dict | str]] = None,
        max_revisions: int = 3,
        metadata: Optional[dict] = None,
    ) -> Objective:
        """Create and register a new user-level business Objective."""
        obj_id = f"obj_{uuid.uuid4().hex[:8]}"
        proj_id = f"proj_{obj_id}"

        if acceptance_criteria is not None:
            crit_set = AcceptanceCriteriaSet.from_list(acceptance_criteria)
        else:
            # Default standard acceptance criteria if none explicitly specified
            crit_set = AcceptanceCriteriaSet.from_list([
                AcceptanceCriterion(
                    name="Penyelesaian Tugas Keseluruhan",
                    criterion_type=CriterionType.TASK,
                    description="Seluruh tugas dalam rencana eksekusi harus selesai (COMPLETED).",
                ),
                AcceptanceCriterion(
                    name="Ketersediaan Dokumen Deliverable",
                    criterion_type=CriterionType.ARTIFACT,
                    description="Menghasilkan dokumen deliverable artefak untuk proyek.",
                ),
            ])

        objective = Objective(
            id=obj_id,
            title=title,
            description=description,
            status=ObjectiveStatus.CREATED,
            priority=priority,
            deadline=deadline,
            budget=budget,
            acceptance_criteria=crit_set,
            project_id=proj_id,
            max_revisions=max_revisions,
            metadata=metadata or {},
        )

        self._objectives[obj_id] = objective
        if self.db:
            self.db.save_objective(
                objective_id=objective.id,
                title=objective.title,
                description=objective.description,
                status=objective.status.value,
                priority=objective.priority.value,
                deadline=objective.deadline,
                budget=objective.budget,
                acceptance_criteria=objective.acceptance_criteria.to_list(),
                project_id=objective.project_id,
                max_revisions=objective.max_revisions,
                metadata=objective.metadata,
                created_at=objective.created_at,
            )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_OBJECTIVE_CREATED,
                    project_id=proj_id,
                    payload=objective.to_dict(),
                )
            )

        return objective

    def get_objective(self, objective_id: str) -> Optional[Objective]:
        """Retrieve an Objective by its identifier."""
        if objective_id in self._objectives:
            return self._objectives[objective_id]
        if self.db:
            d = self.db.get_objective(objective_id)
            if d:
                obj = Objective.from_dict(d)
                self._objectives[obj.id] = obj
                return obj
        return None

    def list_objectives(self, status: Optional[str] = None) -> list[Objective]:
        """List all tracked Objectives, optionally filtered by status."""
        objs = list(self._objectives.values())
        if status:
            stat_str = status.upper()
            return [o for o in objs if (o.status.value if isinstance(o.status, ObjectiveStatus) else str(o.status)).upper() == stat_str]
        return objs

    def analyze_objective(self, objective_id: str) -> ObjectiveAnalysis:
        """Analyzes an Objective for domain classification, complexity, ambiguity, and risks."""
        objective = self.get_objective(objective_id)
        if not objective:
            raise ValueError(f"Objective '{objective_id}' not found.")

        if hasattr(self.planner, "analyze"):
            analysis = self.planner.analyze(objective)
        else:
            analysis = self.analyzer.analyze(objective)

        if self.db:
            try:
                self.db.save_objective_analysis(analysis.to_dict())
            except Exception as e:
                logger.warning(f"Could not persist objective analysis: {e}")

        return analysis

    def evaluate_plan_quality(self, objective_id: str) -> Optional[PlanQualityReport]:
        """Evaluates plan quality across completeness, capability coverage, risks, and budget."""
        objective = self.get_objective(objective_id)
        if not objective:
            raise ValueError(f"Objective '{objective_id}' not found.")

        plan_id = objective.execution_plan_id
        plan = self._plans.get(plan_id) if plan_id else None
        if not plan and self.db:
            d = self.db.get_execution_plan_by_objective(objective.id)
            if d:
                plan = ExecutionPlan.from_dict(d)
                self._plans[plan.id] = plan

        if not plan:
            return None

        report = self.plan_quality_evaluator.evaluate(
            plan=plan,
            objective=objective,
            organization=self.office.organization,
        )

        if self.db:
            try:
                self.db.save_plan_quality_report(
                    report_id=f"pqr_{plan.id}_{int(time.time())}",
                    objective_id=objective.id,
                    plan_id=plan.id,
                    score=report.score,
                    grade=report.grade,
                    issues=report.issues,
                    warnings=report.warnings,
                    recommendations=report.recommendations,
                )
            except Exception as e:
                logger.warning(f"Could not persist plan quality report: {e}")

        return report

    def evaluate_milestone_gate(
        self,
        objective_id: str,
        milestone_id: str,
    ) -> tuple[MilestoneGateStatus, str, list[dict], list[dict]]:
        """Evaluates gating criteria for a specific milestone boundary."""
        objective = self.get_objective(objective_id)
        if not objective:
            raise ValueError(f"Objective '{objective_id}' not found.")

        plan_id = objective.execution_plan_id
        plan = self._plans.get(plan_id) if plan_id else None
        if not plan and self.db:
            d = self.db.get_execution_plan_by_objective(objective.id)
            if d:
                plan = ExecutionPlan.from_dict(d)
                self._plans[plan.id] = plan

        if not plan:
            raise ValueError(f"Execution plan for objective '{objective_id}' not found.")

        milestone = next((m for m in plan.milestones if m.milestone_id == milestone_id), None)
        if not milestone:
            raise ValueError(f"Milestone '{milestone_id}' not found in plan for objective '{objective_id}'.")

        # Retrieve or initialize gate
        gates_dict = plan.metadata.get("milestone_gates", {})
        if milestone_id in gates_dict:
            gate = MilestoneGate.from_dict(gates_dict[milestone_id])
        else:
            gate = MilestoneGate(
                milestone_id=milestone.milestone_id,
                name=milestone.name,
                order=milestone.order,
                status=MilestoneGateStatus.PENDING,
            )

        # Collect tasks belonging to this milestone
        m_task_ids = set(milestone.tasks)
        proj_tasks = [
            t for t in self.office.work_queue.list_all_tasks()
            if t.project_id == objective.project_id and t.task_id in m_task_ids
        ]
        proj_artifacts = []
        if hasattr(self.office, "artifact_store") and self.office.artifact_store:
            proj_artifacts = self.office.artifact_store.list_artifacts(project_id=objective.project_id)

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_MILESTONE_EVALUATION_STARTED,
                    project_id=objective.project_id,
                    payload={"objective_id": objective.id, "milestone_id": milestone_id},
                )
            )

        status, feedback, crit_results, rev_tasks = self.milestone_gate_evaluator.evaluate_gate(
            gate=gate,
            tasks=proj_tasks,
            artifacts=proj_artifacts,
        )

        # Persist updated gate in plan metadata
        if "milestone_gates" not in plan.metadata:
            plan.metadata["milestone_gates"] = {}
        plan.metadata["milestone_gates"][milestone_id] = gate.to_dict()

        if status == MilestoneGateStatus.PASSED:
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_MILESTONE_GATE_PASSED,
                        project_id=objective.project_id,
                        payload={"objective_id": objective.id, "milestone_id": milestone_id, "feedback": feedback},
                    )
                )
        elif status in (MilestoneGateStatus.FAILED, MilestoneGateStatus.NEEDS_REVISION):
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_MILESTONE_GATE_FAILED,
                        project_id=objective.project_id,
                        payload={
                            "objective_id": objective.id,
                            "milestone_id": milestone_id,
                            "feedback": feedback,
                            "status": status.value,
                        },
                    )
                )
            # Inject milestone revision tasks into work queue
            for rev_t in rev_tasks:
                task = WorkTask(
                    task_id=rev_t["task_id"],
                    project_id=objective.project_id,
                    title=rev_t["title"],
                    description=rev_t["description"],
                    priority=rev_t.get("priority", 12),
                    required_capabilities=rev_t.get("required_capabilities", ["bug_fixing"]),
                    preferred_role=rev_t.get("preferred_role", "developer"),
                    dependencies=rev_t.get("dependencies", []),
                )
                self.office.work_queue.add_task(task)

        return status, feedback, crit_results, rev_tasks

    def plan_objective(self, objective_id: str) -> ExecutionPlan:
        """Decompose an Objective into an ExecutionPlan and validate the plan."""
        objective = self.get_objective(objective_id)
        if not objective:
            raise ValueError(f"Objective '{objective_id}' not found.")

        # Transition to PLANNING
        objective.transition_to(ObjectiveStatus.PLANNING)
        self._sync_objective_db(objective)

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_OBJECTIVE_PLANNING_STARTED,
                    project_id=objective.project_id,
                    payload={"objective_id": objective.id, "title": objective.title},
                )
            )

        # Generate plan via AdaptiveObjectivePlanner or ObjectivePlanner
        plan = self.planner.plan(objective)
        self._plans[plan.id] = plan

        # Persist analysis if available in metadata
        if self.db and plan.metadata.get("analysis"):
            try:
                self.db.save_objective_analysis(plan.metadata["analysis"])
            except Exception as e:
                logger.warning(f"Could not persist objective analysis: {e}")

        # Persist quality report if available in metadata
        if self.db and plan.metadata.get("quality_report"):
            try:
                qr = plan.metadata["quality_report"]
                self.db.save_plan_quality_report(
                    report_id=f"pqr_{plan.id}",
                    objective_id=objective.id,
                    plan_id=plan.id,
                    score=qr.get("score", 0),
                    grade=qr.get("grade", "F"),
                    issues=qr.get("issues", []),
                    warnings=qr.get("warnings", []),
                    recommendations=qr.get("recommendations", []),
                )
            except Exception as e:
                logger.warning(f"Could not persist plan quality report: {e}")

        if not plan.is_valid:
            # Plan validation failed or needs clarification
            if plan.metadata.get("needs_clarification"):
                objective.metadata["clarifications"] = plan.metadata.get("clarifications", [])

            objective.transition_to(ObjectiveStatus.FAILED, reason=plan.validation_error)
            self._sync_objective_db(objective)
            if self.db:
                self.db.save_execution_plan(
                    plan_id=plan.id,
                    objective_id=objective.id,
                    milestones=[m.to_dict() for m in plan.milestones],
                    tasks=plan.tasks,
                    dependencies=plan.dependencies,
                    estimated_cost=plan.estimated_cost,
                    required_skills=plan.required_skills,
                    is_valid=False,
                    validation_error=plan.validation_error,
                    metadata=plan.metadata,
                )

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_OBJECTIVE_PLAN_FAILED,
                        project_id=objective.project_id,
                        payload={"objective_id": objective.id, "error": plan.validation_error},
                    )
                )
            return plan

        # Plan validation passed -> transition to READY
        objective.execution_plan_id = plan.id
        objective.transition_to(ObjectiveStatus.READY)
        self._sync_objective_db(objective)

        if self.db:
            self.db.save_execution_plan(
                plan_id=plan.id,
                objective_id=objective.id,
                milestones=[m.to_dict() for m in plan.milestones],
                tasks=plan.tasks,
                dependencies=plan.dependencies,
                estimated_cost=plan.estimated_cost,
                required_skills=plan.required_skills,
                is_valid=True,
                validation_error=None,
                metadata=plan.metadata,
            )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_OBJECTIVE_PLAN_CREATED,
                    project_id=objective.project_id,
                    payload={"objective_id": objective.id, "plan_id": plan.id, "tasks_count": len(plan.tasks)},
                )
            )

        return plan

    def run_objective(
        self,
        objective_id: str,
        auto_tick: bool = True,
        max_ticks: int = 50,
        enable_milestone_gating: bool = False,
    ) -> Objective:
        """Execute the end-to-end Objective -> Outcome workflow with self-correction revision loop."""
        objective = self.get_objective(objective_id)
        if not objective:
            raise ValueError(f"Objective '{objective_id}' not found.")

        # 1. Auto-plan if objective is in CREATED
        if objective.status == ObjectiveStatus.CREATED:
            plan = self.plan_objective(objective.id)
            if not plan.is_valid:
                return objective

        if objective.status == ObjectiveStatus.FAILED:
            return objective

        # 2. Materialize Project & Tasks if objective is READY
        if objective.status == ObjectiveStatus.READY:
            plan_id = objective.execution_plan_id
            plan = self._plans.get(plan_id)
            if not plan and self.db:
                d = self.db.get_execution_plan_by_objective(objective.id)
                if d:
                    plan = ExecutionPlan.from_dict(d)
                    self._plans[plan.id] = plan

            if not plan:
                raise RuntimeError(f"ExecutionPlan for objective '{objective.id}' not found.")

            # Create and register project in OfficeOrchestrator
            proj = Project(
                project_id=objective.project_id or objective.id,
                name=f"Objective: {objective.title}",
                description=objective.description,
                priority=objective.priority,
                deadline=objective.deadline,
                budget=objective.budget,
                status=ProjectStatus.READY,
                metadata={"objective_id": objective.id},
            )
            self.office.project_registry.register_project(proj)
            if objective.budget > 0 and self.office.budget_manager:
                self.office.budget_manager.set_project_budget(proj.project_id, objective.budget)

            # Ingest tasks into WorkQueue
            for t_def in plan.tasks:
                t_id = t_def["task_id"]
                deps = plan.dependencies.get(t_id, [])
                task = WorkTask(
                    task_id=t_id,
                    project_id=proj.project_id,
                    title=t_def.get("title", t_id),
                    description=t_def.get("description", ""),
                    priority=t_def.get("priority", 5),
                    required_capabilities=t_def.get("required_capabilities", []),
                    preferred_role=t_def.get("preferred_role"),
                    dependencies=deps,
                )
                self.office.work_queue.add_task(task)

            # Transition Objective to EXECUTING
            objective.transition_to(ObjectiveStatus.EXECUTING)
            self._sync_objective_db(objective)

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_OBJECTIVE_STARTED,
                        project_id=objective.project_id,
                        payload={"objective_id": objective.id, "project_id": proj.project_id},
                    )
                )

        # 3. Execution & Evaluation Loop
        ticks_executed = 0
        plan = self._plans.get(objective.execution_plan_id)
        while objective.status == ObjectiveStatus.EXECUTING and ticks_executed < max_ticks:
            # Intermediate Milestone Gating (if enabled)
            if enable_milestone_gating and plan and plan.milestones:
                gates_dict = plan.metadata.get("milestone_gates", {})
                for m in plan.milestones:
                    g_info = gates_dict.get(m.milestone_id, {})
                    if g_info.get("status") == MilestoneGateStatus.PENDING.value:
                        m_tasks = [t for t in self.office.work_queue.list_all_tasks() if t.project_id == objective.project_id and t.task_id in m.tasks]
                        if m_tasks and all(t.status == TASK_COMPLETED for t in m_tasks):
                            gate_stat, feedback, _, _ = self.evaluate_milestone_gate(objective.id, m.milestone_id)
                            if gate_stat == MilestoneGateStatus.FAILED:
                                objective.transition_to(ObjectiveStatus.FAILED, reason=f"Gerbang milestone {m.name} gagal: {feedback}")
                                self._sync_objective_db(objective)
                                return objective

            # Check if all tasks in work queue for this project are complete
            proj_tasks = [t for t in self.office.work_queue.list_all_tasks() if t.project_id == objective.project_id]
            all_done = bool(proj_tasks) and all(t.status == TASK_COMPLETED for t in proj_tasks)

            if not all_done:
                if auto_tick:
                    self.office.scheduler_tick(execute=True)
                    ticks_executed += 1
                else:
                    # Non-auto-tick mode, step one tick and return
                    self.office.scheduler_tick(execute=True)
                    ticks_executed += 1
                    break
            else:
                # All current tasks completed -> advance to EVALUATING
                objective.transition_to(ObjectiveStatus.EVALUATING)
                self._sync_objective_db(objective)

                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EVENT_OBJECTIVE_EVALUATION_STARTED,
                            project_id=objective.project_id,
                            payload={"objective_id": objective.id},
                        )
                    )

                # Fetch all completed artifacts
                proj_artifacts = []
                if hasattr(self.office, "artifact_store") and self.office.artifact_store:
                    proj_artifacts = self.office.artifact_store.list_artifacts(project_id=objective.project_id)

                # Run outcome evaluation
                evaluation = self.evaluator.evaluate(
                    objective=objective,
                    tasks=proj_tasks,
                    artifacts=proj_artifacts,
                )

                eval_id = f"eval_{objective.id}_{uuid.uuid4().hex[:6]}"
                if self.db:
                    self.db.save_objective_evaluation(
                        evaluation_id=eval_id,
                        objective_id=objective.id,
                        verdict=evaluation.verdict.value,
                        criteria_results=evaluation.criteria_results,
                        feedback=evaluation.feedback,
                        revision_requested=(evaluation.verdict == EvaluationVerdict.NEEDS_REVISION),
                    )

                if evaluation.verdict == EvaluationVerdict.PASS:
                    # Objective successfully completed!
                    objective.result = {
                        "feedback": evaluation.feedback,
                        "criteria": evaluation.criteria_results,
                        "artifacts_count": len(proj_artifacts),
                        "tasks_completed": len(proj_tasks),
                    }
                    objective.transition_to(ObjectiveStatus.COMPLETED)
                    self._sync_objective_db(objective)

                    # Ensure underlying project is marked COMPLETED
                    proj = self.office.project_registry.get_project(objective.project_id)
                    if proj and proj.status != ProjectStatus.COMPLETED:
                        self.office.project_registry.complete_project(objective.project_id)

                    if self.event_bus:
                        self.event_bus.publish(
                            Event(
                                event_type=EVENT_OBJECTIVE_COMPLETED,
                                project_id=objective.project_id,
                                payload={"objective_id": objective.id, "result": objective.result},
                            )
                        )
                    break

                elif evaluation.verdict == EvaluationVerdict.NEEDS_REVISION:
                    # Revision loop: inject revision tasks and re-enter EXECUTING
                    objective.revision_count += 1
                    objective.transition_to(ObjectiveStatus.EXECUTING)
                    self._sync_objective_db(objective)

                    if self.event_bus:
                        self.event_bus.publish(
                            Event(
                                event_type=EVENT_OBJECTIVE_REVISION_REQUESTED,
                                project_id=objective.project_id,
                                payload={
                                    "objective_id": objective.id,
                                    "revision_count": objective.revision_count,
                                    "feedback": evaluation.feedback,
                                },
                            )
                        )

                    for rev_t in evaluation.revision_tasks:
                        task = WorkTask(
                            task_id=rev_t["task_id"],
                            project_id=objective.project_id,
                            title=rev_t["title"],
                            description=rev_t["description"],
                            priority=rev_t.get("priority", 12),
                            required_capabilities=rev_t.get("required_capabilities", ["bug_fixing"]),
                            preferred_role=rev_t.get("preferred_role", "developer"),
                            dependencies=rev_t.get("dependencies", []),
                        )
                        self.office.work_queue.add_task(task)

                    if not auto_tick:
                        break

                elif evaluation.verdict == EvaluationVerdict.FAIL:
                    # Exceeded max revisions or unrecoverable criteria failure
                    objective.transition_to(ObjectiveStatus.FAILED, reason=evaluation.feedback)
                    objective.result = {"feedback": evaluation.feedback, "criteria": evaluation.criteria_results}
                    self._sync_objective_db(objective)

                    if self.event_bus:
                        self.event_bus.publish(
                            Event(
                                event_type=EVENT_OBJECTIVE_FAILED,
                                project_id=objective.project_id,
                                payload={"objective_id": objective.id, "reason": evaluation.feedback},
                            )
                        )
                    break

        return objective

    def cancel_objective(self, objective_id: str, reason: str = "Dibatalkan oleh pengguna via CLI") -> Objective:
        """Cancel an active Objective cleanly."""
        objective = self.get_objective(objective_id)
        if not objective:
            raise ValueError(f"Objective '{objective_id}' not found.")

        if objective.is_terminal():
            return objective

        objective.transition_to(ObjectiveStatus.CANCELLED, reason=reason)
        self._sync_objective_db(objective)

        if objective.project_id and hasattr(self.office, "pause_project"):
            try:
                self.office.pause_project(objective.project_id, reason=reason)
            except Exception:
                pass

        return objective

    def recover_objectives(self) -> None:
        """Cold-start recovery: heal objectives left in intermediate states from unexpected shutdowns."""
        if not self.db:
            return

        in_flight = [
            o for o in self._objectives.values()
            if o.status in (ObjectiveStatus.PLANNING, ObjectiveStatus.EXECUTING, ObjectiveStatus.EVALUATING)
        ]

        for obj in in_flight:
            if obj.status == ObjectiveStatus.PLANNING:
                # If plan was saved, transition to READY, else rollback to CREATED
                plan = self.db.get_execution_plan_by_objective(obj.id)
                if plan and plan.get("is_valid"):
                    obj.status = ObjectiveStatus.READY
                    obj.execution_plan_id = plan["id"]
                else:
                    obj.status = ObjectiveStatus.CREATED
                self._sync_objective_db(obj)

            elif obj.status == ObjectiveStatus.EVALUATING:
                # Re-evaluate deliverables or restore to EXECUTING
                obj.status = ObjectiveStatus.EXECUTING
                self._sync_objective_db(obj)

            elif obj.status == ObjectiveStatus.EXECUTING:
                # Verify project tasks in WorkQueue
                proj_tasks = [t for t in self.office.work_queue.list_all_tasks() if t.project_id == obj.project_id]
                if proj_tasks and all(t.status == TASK_COMPLETED for t in proj_tasks):
                    obj.status = ObjectiveStatus.EVALUATING
                    self._sync_objective_db(obj)

    def _sync_objective_db(self, objective: Objective) -> None:
        """Helper to sync Objective state back to SQLite database."""
        if not self.db:
            return
        self.db.update_objective_status(
            objective_id=objective.id,
            status=objective.status.value,
            started_at=objective.started_at,
            completed_at=objective.completed_at,
            failure_reason=objective.failure_reason,
            result=objective.result,
            revision_count=objective.revision_count,
        )

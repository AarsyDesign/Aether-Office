"""Phase 8 Objective-to-Outcome Engine Test Suite.
Tests the full Objective lifecycle, planning, plan validation, dependency resolution,
skill-based workforce matching, artifact evaluation, self-correction revision loop,
restart recovery, and end-to-end Objective -> Plan -> Execution -> Evaluation -> Outcome.
"""

import pytest
import time
from pathlib import Path

from db import Database
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
)
from workforce import (
    Organization,
    Employee,
    STATUS_ACTIVE,
    AVAILABILITY_AVAILABLE,
    create_default_organization,
)
from projects import Project, ProjectStatus, ProjectPriority
from office import OfficeOrchestrator
from matcher import TaskMatcher
from artifacts import Artifact, ArtifactStore, ARTIFACT_DOCUMENT
from objectives import (
    Objective,
    ObjectiveStatus,
    AcceptanceCriterion,
    AcceptanceCriteriaSet,
    CriterionType,
    InvalidObjectiveStateTransition,
    validate_objective_transition,
)
from planner import (
    ExecutionPlan,
    Milestone,
    PlanValidator,
    ObjectivePlanner,
)
from evaluator import (
    OutcomeEvaluator,
    EvaluationVerdict,
    EvaluationResult,
)
from objective_orchestrator import ObjectiveOrchestrator


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "aether_objective.db")
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def test_org():
    org, _ = create_default_organization()
    return org


@pytest.fixture
def sample_office(temp_db, test_org, event_bus):
    temp_db.sync_organization_to_db(test_org)
    office = OfficeOrchestrator(
        db=temp_db,
        organization=test_org,
        event_bus=event_bus,
    )
    return office


@pytest.fixture
def sample_obj_orchestrator(sample_office, temp_db, event_bus):
    return ObjectiveOrchestrator(
        office_orchestrator=sample_office,
        db=temp_db,
        event_bus=event_bus,
    )


# =====================================================================
# 1. test_objective_lifecycle
# =====================================================================

def test_objective_lifecycle():
    """Verify standard happy-path Objective lifecycle transitions."""
    obj = Objective(id="obj_test_1", title="Test Objective")
    assert obj.status == ObjectiveStatus.CREATED

    obj.transition_to(ObjectiveStatus.PLANNING)
    assert obj.status == ObjectiveStatus.PLANNING

    obj.transition_to(ObjectiveStatus.READY)
    assert obj.status == ObjectiveStatus.READY

    obj.transition_to(ObjectiveStatus.EXECUTING)
    assert obj.status == ObjectiveStatus.EXECUTING
    assert obj.started_at is not None

    obj.transition_to(ObjectiveStatus.EVALUATING)
    assert obj.status == ObjectiveStatus.EVALUATING

    obj.transition_to(ObjectiveStatus.COMPLETED)
    assert obj.status == ObjectiveStatus.COMPLETED
    assert obj.completed_at is not None
    assert obj.is_terminal() is True


# =====================================================================
# 2. test_objective_invalid_transitions
# =====================================================================

def test_objective_invalid_transitions():
    """Verify illegal jumps are strictly rejected by the state machine."""
    obj = Objective(id="obj_test_inv", title="Invalid Transition Test")

    # Direct jump from CREATED to COMPLETED is forbidden
    with pytest.raises(InvalidObjectiveStateTransition):
        obj.transition_to(ObjectiveStatus.COMPLETED)

    # Direct jump from CREATED to EXECUTING is forbidden
    with pytest.raises(InvalidObjectiveStateTransition):
        obj.transition_to(ObjectiveStatus.EXECUTING)

    obj.transition_to(ObjectiveStatus.PLANNING)
    obj.transition_to(ObjectiveStatus.FAILED, reason="Planning impossible")

    # FAILED can re-plan, but cannot jump directly to COMPLETED
    with pytest.raises(InvalidObjectiveStateTransition):
        obj.transition_to(ObjectiveStatus.COMPLETED)


# =====================================================================
# 3. test_objective_planning_success
# =====================================================================

def test_objective_planning_success(test_org):
    """Verify ObjectivePlanner generates 4 milestones and a valid DAG."""
    planner = ObjectivePlanner(organization=test_org)
    obj = Objective(
        id="obj_saas",
        title="Buatkan Landing Page SaaS",
        description="Landing page modern dengan pricing dan CTA",
        budget=100.0,
    )

    plan = planner.plan(obj)
    assert plan.is_valid is True
    assert plan.validation_error is None
    assert len(plan.milestones) == 4
    assert len(plan.tasks) == 4
    assert plan.estimated_cost > 0.0

    # Verify sequential milestone dependencies
    task_map = {t["task_id"]: t for t in plan.tasks}
    t1_id = f"{obj.id}_t1_research"
    t2_id = f"{obj.id}_t2_design"
    t3_id = f"{obj.id}_t3_impl"
    t4_id = f"{obj.id}_t4_qa"

    assert plan.dependencies[t1_id] == []
    assert t1_id in plan.dependencies[t2_id]
    assert t2_id in plan.dependencies[t3_id]
    assert t3_id in plan.dependencies[t4_id]


# =====================================================================
# 4. test_plan_validation_circular_dependency
# =====================================================================

def test_plan_validation_circular_dependency():
    """Verify PlanValidator detects circular dependency cycles."""
    tasks = [
        {"task_id": "t_a", "title": "Task A", "required_capabilities": ["python"]},
        {"task_id": "t_b", "title": "Task B", "required_capabilities": ["testing"]},
    ]
    # Cycle: A depends on B, B depends on A
    deps = {
        "t_a": ["t_b"],
        "t_b": ["t_a"],
    }
    plan = ExecutionPlan(
        id="plan_cycle",
        objective_id="obj_cycle",
        tasks=tasks,
        dependencies=deps,
    )

    is_valid, err = PlanValidator.validate_plan(plan)
    assert is_valid is False
    assert "Circular dependency detected" in err


# =====================================================================
# 5. test_plan_validation_invalid_dependency
# =====================================================================

def test_plan_validation_invalid_dependency():
    """Verify PlanValidator rejects tasks depending on non-existent task IDs."""
    tasks = [
        {"task_id": "t_1", "title": "Task 1", "required_capabilities": ["python"]},
    ]
    deps = {
        "t_1": ["t_ghost_missing"],
    }
    plan = ExecutionPlan(
        id="plan_missing_dep",
        objective_id="obj_missing",
        tasks=tasks,
        dependencies=deps,
    )

    is_valid, err = PlanValidator.validate_plan(plan)
    assert is_valid is False
    assert "depends on non-existent task" in err


# =====================================================================
# 6. test_plan_validation_no_matching_employee
# =====================================================================

def test_plan_validation_no_matching_employee(test_org):
    """Verify PlanValidator flags tasks requiring capabilities absent from workforce."""
    tasks = [
        {
            "task_id": "t_alien",
            "title": "Quantum Teleportation",
            "required_capabilities": ["quantum_cryptography_alien_tech"],
            "preferred_role": "quantum_alchemist",
        }
    ]
    plan = ExecutionPlan(
        id="plan_alien",
        objective_id="obj_alien",
        tasks=tasks,
        dependencies={"t_alien": []},
    )

    is_valid, err = PlanValidator.validate_plan(plan, organization=test_org)
    assert is_valid is False
    assert "No eligible workforce candidate in organization matches requirements" in err


# =====================================================================
# 7. test_plan_validation_budget_exceeded
# =====================================================================

def test_plan_validation_budget_exceeded():
    """Verify PlanValidator catches when estimated cost exceeds budget limit."""
    tasks = [
        {"task_id": "t_1", "title": "Task 1", "required_capabilities": ["python"]},
    ]
    plan = ExecutionPlan(
        id="plan_expensive",
        objective_id="obj_exp",
        tasks=tasks,
        dependencies={"t_1": []},
        estimated_cost=50.0,
    )

    # Budget limit is $10.0, plan costs $50.0
    is_valid, err = PlanValidator.validate_plan(plan, budget_limit=10.0)
    assert is_valid is False
    assert "exceeds objective budget limit" in err


# =====================================================================
# 8. test_skill_based_workforce_matching
# =====================================================================

def test_skill_based_workforce_matching(test_org):
    """Verify enhanced multi-factor matching scoring in TaskMatcher."""
    task = {
        "task_id": "task_backend",
        "preferred_role": "backend_developer",
        "department": "engineering",
        "required_capabilities": ["python", "api", "database"],
        "priority": 10,
    }

    # Register a specialized backend developer alongside standard workforce
    specialist = Employee(
        employee_id="emp_backend_specialist",
        name="Arya Kusuma",
        role="backend_developer",
        department="engineering",
        capabilities=["python", "api", "database", "sql"],
        status=STATUS_ACTIVE,
        availability=AVAILABILITY_AVAILABLE,
    )
    test_org.employees.register(specialist)

    candidates = test_org.employees.list()
    ranked = TaskMatcher.rank_candidates(task, candidates, priority="HIGH")

    assert len(ranked) > 0
    best_emp, best_score = ranked[0]

    # Best employee should be the backend developer with high capability match
    assert best_emp.role == "backend_developer"
    assert best_emp.employee_id == "emp_backend_specialist"
    assert best_score >= 40  # Role(20) + Dept(5) + Caps(30) + Priority(5) = ~60


# =====================================================================
# 9. test_artifact_evaluation_pass
# =====================================================================

def test_artifact_evaluation_pass():
    """Verify OutcomeEvaluator returns PASS when deliverables fulfill all criteria."""
    crit_set = AcceptanceCriteriaSet.from_list([
        AcceptanceCriterion(
            name="Dokumen Desain",
            criterion_type=CriterionType.ARTIFACT,
            target_value="desain",
        ),
        AcceptanceCriterion(
            name="Fitur Pricing",
            criterion_type=CriterionType.TEXT,
            target_value="pricing",
        ),
        AcceptanceCriterion(
            name="Semua Tugas Selesai",
            criterion_type=CriterionType.TASK,
        ),
    ])

    obj = Objective(id="obj_eval_p", title="SaaS Page", acceptance_criteria=crit_set)
    evaluator = OutcomeEvaluator()

    tasks = [
        {"task_id": "t1", "status": "COMPLETED", "result": {"output": "SaaS with pricing table."}},
        {"task_id": "t2", "status": "COMPLETED", "result": {"output": "All components styled."}},
    ]
    artifacts = [
        {"name": "Dokumen Desain SaaS", "type": "document", "content": "SaaS wireframe and pricing model."},
    ]

    res = evaluator.evaluate(objective=obj, tasks=tasks, artifacts=artifacts)
    assert res.verdict == EvaluationVerdict.PASS
    assert len(res.revision_tasks) == 0
    assert "berhasil dipenuhi" in res.feedback


# =====================================================================
# 10. test_artifact_evaluation_needs_revision
# =====================================================================

def test_artifact_evaluation_needs_revision():
    """Verify OutcomeEvaluator returns NEEDS_REVISION and generates revision tasks when criteria fail."""
    crit_set = AcceptanceCriteriaSet.from_list([
        AcceptanceCriterion(
            name="Bagian Pricing Tersedia",
            criterion_type=CriterionType.TEXT,
            target_value="pricing_table_v2",
        ),
    ])

    obj = Objective(id="obj_eval_r", title="SaaS Page", acceptance_criteria=crit_set, revision_count=0, max_revisions=3)
    evaluator = OutcomeEvaluator()

    tasks = [{"task_id": "t1", "status": "COMPLETED", "result": {"output": "General landing page."}}]
    artifacts = [{"name": "HTML File", "content": "Welcome to our app."}]

    res = evaluator.evaluate(objective=obj, tasks=tasks, artifacts=artifacts)
    assert res.verdict == EvaluationVerdict.NEEDS_REVISION
    assert len(res.revision_tasks) == 1
    assert "pricing_table_v2" in res.revision_tasks[0]["description"]


# =====================================================================
# 11. test_self_correction_revision_loop
# =====================================================================

def test_self_correction_revision_loop(sample_obj_orchestrator, sample_office):
    """Verify objective execution with a self-correction revision cycle:
    Initial execution fails acceptance criteria -> revision task generated -> re-executed -> PASS.
    """
    crit_set = AcceptanceCriteriaSet.from_list([
        AcceptanceCriterion(
            name="Dokumen Deliverable",
            criterion_type=CriterionType.ARTIFACT,
        ),
        AcceptanceCriterion(
            name="Kata Kunci Mandatory",
            criterion_type=CriterionType.TEXT,
            target_value="ENTERPRISE_READY",
        ),
    ])

    obj = sample_obj_orchestrator.create_objective(
        title="Enterprise Security Integration",
        acceptance_criteria=crit_set,
        max_revisions=2,
    )

    # Mock TaskWorker output: initially doesn't contain ENTERPRISE_READY, revision includes it
    def smart_executor(task, emp):
        is_rev = "rev" in task.task_id
        # Ensure deliverable artifact is saved in ArtifactStore
        if sample_office.artifact_store:
            sample_office.artifact_store.save_artifact(
                project_id=task.project_id,
                task_id=task.task_id,
                created_by=emp.employee_id,
                name="Dokumen Deliverable",
                artifact_type=ARTIFACT_DOCUMENT,
                content="Enterprise Security module updated and ENTERPRISE_READY." if is_rev else "Initial security draft without keywords.",
            )
        if is_rev:
            return {"success": True, "output": "Security module fully updated and ENTERPRISE_READY."}
        return {"success": True, "output": "Initial security draft without keywords."}

    sample_office.scheduler.worker = None  # Use custom executor

    # Run objective with custom executor simulating revision success
    # First step: plan
    plan = sample_obj_orchestrator.plan_objective(obj.id)
    assert plan.is_valid is True

    # Custom run loop invoking smart_executor during scheduler ticks
    obj = sample_obj_orchestrator.run_objective(obj.id, auto_tick=False)

    # Tick through initial tasks
    for _ in range(6):
        sample_office.scheduler_tick(execute=True, custom_executor=smart_executor)

    # Check objective - it will trigger evaluation and request revision
    obj = sample_obj_orchestrator.run_objective(obj.id, auto_tick=False)
    assert obj.revision_count == 1
    assert obj.status == ObjectiveStatus.EXECUTING

    # Now tick the revision task with smart_executor (which now produces ENTERPRISE_READY)
    sample_office.scheduler_tick(execute=True, custom_executor=smart_executor)

    # Final run step evaluates and completes
    obj = sample_obj_orchestrator.run_objective(obj.id, auto_tick=False)
    assert obj.status == ObjectiveStatus.COMPLETED
    assert obj.revision_count == 1


# =====================================================================
# 12. test_max_revisions_exceeded
# =====================================================================

def test_max_revisions_exceeded():
    """Verify objective fails when max revision attempts are exhausted."""
    crit_set = AcceptanceCriteriaSet.from_list([
        AcceptanceCriterion(
            name="Impossible Condition",
            criterion_type=CriterionType.TEXT,
            target_value="UNOBTAINABLE_SECRET_KEY",
        ),
    ])

    obj = Objective(
        id="obj_max_rev",
        title="Failing Objective",
        acceptance_criteria=crit_set,
        revision_count=3,
        max_revisions=3,
    )
    evaluator = OutcomeEvaluator()

    res = evaluator.evaluate(
        objective=obj,
        tasks=[{"task_id": "t1", "status": "COMPLETED", "result": {"output": "Normal output"}}],
        artifacts=[],
    )
    assert res.verdict == EvaluationVerdict.FAIL
    assert "Batas maksimum revisi" in res.feedback


# =====================================================================
# 13. test_objective_restart_recovery
# =====================================================================

def test_objective_restart_recovery(temp_db, test_org, event_bus):
    """Verify cold-start recovery restores objectives in flight after sudden process death."""
    temp_db.sync_organization_to_db(test_org)
    office1 = OfficeOrchestrator(db=temp_db, organization=test_org, event_bus=event_bus)
    obj_orch1 = ObjectiveOrchestrator(office_orchestrator=office1, db=temp_db, event_bus=event_bus)

    obj = obj_orch1.create_objective(title="Crash Recovery Objective")
    obj_orch1.plan_objective(obj.id)
    assert obj.status == ObjectiveStatus.READY

    # Simulate in-flight crash by manually writing EXECUTING status into DB
    temp_db.update_objective_status(obj.id, status="EXECUTING")

    # Cold restart: instantiate fresh orchestrators on the same DB
    office2 = OfficeOrchestrator(db=temp_db, organization=test_org, event_bus=event_bus)
    obj_orch2 = ObjectiveOrchestrator(office_orchestrator=office2, db=temp_db, event_bus=event_bus)

    recovered_obj = obj_orch2.get_objective(obj.id)
    assert recovered_obj is not None
    # Recovered objective should be recognized and manageable
    assert recovered_obj.status in (ObjectiveStatus.EXECUTING, ObjectiveStatus.READY)


# =====================================================================
# 14. test_end_to_end_objective_to_outcome
# =====================================================================

def test_end_to_end_objective_to_outcome(sample_obj_orchestrator, event_bus):
    """Integration Test:
    CREATE OBJECTIVE -> PLAN -> VALIDATE PLAN -> CREATE PROJECT ->
    CREATE TASKS -> RESOLVE DEPENDENCIES -> SCHEDULE -> RESERVE EMPLOYEE ->
    EXECUTE AGENT -> CREATE ARTIFACT -> EVALUATE ARTIFACT -> PASS -> OBJECTIVE COMPLETED.
    """
    events_logged = []
    target_events = {
        EVENT_OBJECTIVE_CREATED,
        EVENT_OBJECTIVE_PLANNING_STARTED,
        EVENT_OBJECTIVE_PLAN_CREATED,
        EVENT_OBJECTIVE_STARTED,
        EVENT_OBJECTIVE_EVALUATION_STARTED,
        EVENT_OBJECTIVE_COMPLETED,
    }
    event_bus.subscribe(lambda e: events_logged.append(e.event_type) if e.event_type in target_events else None)

    # 1. CREATE OBJECTIVE
    crit = AcceptanceCriteriaSet.from_list([
        AcceptanceCriterion(
            name="Semua Tugas Selesai",
            criterion_type=CriterionType.TASK,
        ),
        AcceptanceCriterion(
            name="Deliverable Terbentuk",
            criterion_type=CriterionType.ARTIFACT,
        ),
    ])

    obj = sample_obj_orchestrator.create_objective(
        title="Bangun Sistem Autentikasi OAuth2",
        description="Layanan backend login, registrasi, dan token JWT",
        budget=100.0,
        priority=ProjectPriority.HIGH,
        acceptance_criteria=crit,
    )
    assert obj.status == ObjectiveStatus.CREATED

    # 2. RUN OBJECTIVE (Auto-plans, creates project, executes tasks, evaluates, completes)
    final_obj = sample_obj_orchestrator.run_objective(obj.id, auto_tick=True, max_ticks=20)

    # 3. VERIFY OUTCOME
    assert final_obj.status == ObjectiveStatus.COMPLETED
    assert final_obj.completed_at is not None
    assert final_obj.result.get("tasks_completed") == 4
    assert final_obj.result.get("artifacts_count") >= 1

    # 4. VERIFY EVENT CHAIN
    assert EVENT_OBJECTIVE_CREATED in events_logged
    assert EVENT_OBJECTIVE_PLANNING_STARTED in events_logged
    assert EVENT_OBJECTIVE_PLAN_CREATED in events_logged
    assert EVENT_OBJECTIVE_STARTED in events_logged
    assert EVENT_OBJECTIVE_EVALUATION_STARTED in events_logged
    assert EVENT_OBJECTIVE_COMPLETED in events_logged


# =====================================================================
# 15. test_objective_cancel
# =====================================================================

def test_objective_cancel(sample_obj_orchestrator):
    """Verify cancelling an Objective pauses underlying project and transitions to CANCELLED."""
    obj = sample_obj_orchestrator.create_objective(title="Objective to be Cancelled")
    sample_obj_orchestrator.plan_objective(obj.id)

    cancelled = sample_obj_orchestrator.cancel_objective(obj.id, reason="Changed business priorities")
    assert cancelled.status == ObjectiveStatus.CANCELLED
    assert cancelled.failure_reason == "Changed business priorities"
    assert cancelled.is_terminal() is True

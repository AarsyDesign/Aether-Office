"""Comprehensive test suite for Phase 6 — Autonomous Office Operations & Multi-Project Scheduling."""

import pytest
import time
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from db import Database
from events import (
    EventBus,
    Event,
    EVENT_PROJECT_CREATED,
    EVENT_PROJECT_STARTED,
    EVENT_PROJECT_PAUSED,
    EVENT_PROJECT_RESUMED,
    EVENT_PROJECT_COMPLETED,
    EVENT_PROJECT_FAILED,
    EVENT_TASK_SCHEDULED,
    EVENT_TASK_COMPLETED,
    EVENT_EMPLOYEE_RESERVED,
    EVENT_EMPLOYEE_RELEASED,
    EVENT_BUDGET_WARNING,
    EVENT_BUDGET_EXCEEDED,
    EVENT_OFFICE_STATE_CHANGED,
)
from workforce import (
    Organization,
    Department,
    Role,
    Employee,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    AVAILABILITY_AVAILABLE,
    AVAILABILITY_BUSY,
    AVAILABILITY_OFFLINE,
    STATE_IDLE,
    STATE_WORKING,
    create_default_organization,
)
from tasks import (
    WorkTask,
    TASK_PENDING,
    TASK_READY,
    TASK_IN_PROGRESS,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_BLOCKED,
)
from projects import Project, ProjectStatus, ProjectPriority, ProjectRegistry
from office_queue import ProjectQueue, WorkQueue
from resources import ResourceManager
from usage import UsageTracker
from budget import BudgetManager, DEFAULT_MODEL_PRICING
from scheduler import SchedulerEngine, ScheduleResult
from office import OfficeOrchestrator, OfficeState


@pytest.fixture
def temp_db():
    db = Database(":memory:")
    yield db
    db.close()


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def test_org():
    org, _ = create_default_organization()
    return org


# =====================================================================
# 1. Project Registry Tests
# =====================================================================

def test_project_model_and_states():
    p = Project(
        project_id="proj_01",
        name="AI Landing Page",
        description="Landing page for accounting SaaS",
        priority=ProjectPriority.CRITICAL,
        budget=10.0,
    )
    assert p.status == ProjectStatus.PLANNED
    assert p.priority == ProjectPriority.CRITICAL
    assert p.priority.weight == 100.0
    assert not p.is_active()

    p.status = ProjectStatus.RUNNING
    assert p.is_active()
    assert not p.is_terminal()

    d = p.to_dict()
    assert d["project_id"] == "proj_01"
    assert d["priority"] == "CRITICAL"
    assert d["budget"] == 10.0

    p2 = Project.from_dict(d)
    assert p2.project_id == p.project_id
    assert p2.priority == ProjectPriority.CRITICAL


def test_project_registry_persistence(temp_db, event_bus):
    registry = ProjectRegistry(db=temp_db, event_bus=event_bus)
    events_received = []
    event_bus.subscribe(lambda e: events_received.append(e))

    p = Project(
        project_id="p_alpha",
        name="Project Alpha",
        description="First test project",
        priority=ProjectPriority.HIGH,
        budget=50.0,
    )
    registry.register_project(p)

    assert any(e.event_type == EVENT_PROJECT_CREATED for e in events_received)

    fetched = registry.get_project("p_alpha")
    assert fetched is not None
    assert fetched.name == "Project Alpha"
    assert fetched.budget == 50.0

    # Start project
    registry.update_status("p_alpha", ProjectStatus.RUNNING)
    assert fetched.status == ProjectStatus.RUNNING
    assert fetched.started_at is not None
    assert any(e.event_type == EVENT_PROJECT_STARTED for e in events_received)

    # Complete project
    registry.complete_project("p_alpha")
    assert fetched.status == ProjectStatus.COMPLETED
    assert fetched.completed_at is not None
    assert any(e.event_type == EVENT_PROJECT_COMPLETED for e in events_received)


def test_project_pause_resume(temp_db, event_bus):
    registry = ProjectRegistry(db=temp_db, event_bus=event_bus)
    events_received = []
    event_bus.subscribe(lambda e: events_received.append(e))

    p = Project(
        project_id="p_beta",
        name="Project Beta",
        status=ProjectStatus.RUNNING,
    )
    registry.register_project(p)

    # Pause
    registry.pause_project("p_beta", reason="Waiting for client feedback")
    assert p.status == ProjectStatus.PAUSED
    assert any(e.event_type == EVENT_PROJECT_PAUSED for e in events_received)

    # Resume
    registry.resume_project("p_beta")
    assert p.status == ProjectStatus.RUNNING
    assert any(e.event_type == EVENT_PROJECT_RESUMED for e in events_received)


# =====================================================================
# 2. Project & Work Queue Tests
# =====================================================================

def test_project_queue_priority_ranking(temp_db):
    registry = ProjectRegistry(db=temp_db)
    queue = ProjectQueue(registry=registry, db=temp_db)

    p_crit = Project(project_id="p_crit", name="Critical Proj", priority=ProjectPriority.CRITICAL, status=ProjectStatus.READY)
    p_high = Project(project_id="p_high", name="High Proj", priority=ProjectPriority.HIGH, status=ProjectStatus.READY)
    p_norm = Project(project_id="p_norm", name="Normal Proj", priority=ProjectPriority.NORMAL, status=ProjectStatus.READY)
    p_low = Project(project_id="p_low", name="Low Proj", priority=ProjectPriority.LOW, status=ProjectStatus.READY)

    for p in [p_low, p_crit, p_norm, p_high]:
        registry.register_project(p)

    ranked = queue.get_ranked_projects()
    order = [p.project_id for p, _ in ranked]
    assert order == ["p_crit", "p_high", "p_norm", "p_low"]


def test_project_queue_deadline_urgency(temp_db):
    registry = ProjectRegistry(db=temp_db)
    queue = ProjectQueue(registry=registry, db=temp_db)

    now = datetime.now(timezone.utc)
    dl_urgent = (now + timedelta(hours=6)).isoformat()
    dl_later = (now + timedelta(days=14)).isoformat()

    p_urgent = Project(project_id="p_urgent", name="Urgent Normal", priority=ProjectPriority.NORMAL, deadline=dl_urgent, status=ProjectStatus.READY)
    p_later = Project(project_id="p_later", name="Later Normal", priority=ProjectPriority.NORMAL, deadline=dl_later, status=ProjectStatus.READY)

    registry.register_project(p_urgent)
    registry.register_project(p_later)

    score_urgent = queue.calculate_project_score(p_urgent)
    score_later = queue.calculate_project_score(p_later)

    assert score_urgent > score_later


def test_project_queue_starvation_prevention(temp_db):
    registry = ProjectRegistry(db=temp_db)
    queue = ProjectQueue(registry=registry, db=temp_db, starvation_bonus_per_tick=15.0)

    p_high = Project(project_id="p_high", name="High Proj", priority=ProjectPriority.HIGH, status=ProjectStatus.READY) # 50 pts
    p_low = Project(project_id="p_low", name="Low Proj", priority=ProjectPriority.LOW, status=ProjectStatus.READY)   # 5 pts

    registry.register_project(p_high)
    registry.register_project(p_low)

    # Initially HIGH > LOW
    ranked = queue.get_ranked_projects()
    assert ranked[0][0].project_id == "p_high"

    # Simulate serving p_high for 4 ticks while p_low starves
    for _ in range(4):
        queue.tick_starvation(served_project_ids={"p_high"})

    # After 4 ticks, p_low starvation bonus = 4 * 15 = 60 pts -> total 65 > p_high (50 pts)
    ranked_after = queue.get_ranked_projects()
    assert ranked_after[0][0].project_id == "p_low"

    # Once p_low is served, starvation resets
    queue.tick_starvation(served_project_ids={"p_low"})
    ranked_reset = queue.get_ranked_projects()
    assert ranked_reset[0][0].project_id == "p_high"


def test_work_queue_task_partitioning(temp_db):
    registry = ProjectRegistry(db=temp_db)
    w_queue = WorkQueue(db=temp_db)

    p = Project(project_id="p_wf", name="Workflow Proj", status=ProjectStatus.READY)
    registry.register_project(p)

    t1 = WorkTask(task_id="t1", project_id="p_wf", title="Task 1", status=TASK_PENDING)
    t2 = WorkTask(task_id="t2", project_id="p_wf", title="Task 2 (depends on t1)", status=TASK_PENDING, dependencies=["t1"])

    w_queue.add_task(t1)
    w_queue.add_task(t2)

    ready = w_queue.get_ready_tasks(registry)
    assert len(ready) == 1
    assert ready[0].task_id == "t1"

    blocked = w_queue.get_blocked_tasks(registry)
    assert len(blocked) == 1
    assert blocked[0].task_id == "t2"

    # Complete t1
    w_queue.mark_running("t1", "emp_01")
    w_queue.mark_completed("t1", result="Success")

    # Now t2 should be ready
    ready_after = w_queue.get_ready_tasks(registry)
    assert len(ready_after) == 1
    assert ready_after[0].task_id == "t2"


# =====================================================================
# 3. Resource Manager & Atomic Locks Tests
# =====================================================================

def test_resource_manager_reservation_and_release(temp_db, test_org, event_bus):
    rm = ResourceManager(organization=test_org, db=temp_db, event_bus=event_bus)
    emp = test_org.list_employees()[0]

    assert not rm.is_reserved(emp.employee_id)
    assert emp.availability == AVAILABILITY_AVAILABLE

    # Reserve
    reserved = rm.reserve_employee(emp.employee_id, task_id="task_100", project_id="proj_x")
    assert reserved is True
    assert rm.is_reserved(emp.employee_id)
    assert emp.availability == AVAILABILITY_BUSY
    assert emp.live_state == STATE_WORKING
    assert emp.active_tasks == 1

    # Release
    released = rm.release_employee(emp.employee_id)
    assert released is True
    assert not rm.is_reserved(emp.employee_id)
    assert emp.availability == AVAILABILITY_AVAILABLE
    assert emp.live_state == STATE_IDLE
    assert emp.active_tasks == 0


def test_double_reservation_prevention(temp_db, test_org):
    rm = ResourceManager(organization=test_org, db=temp_db)
    emp = test_org.list_employees()[0]

    first = rm.reserve_employee(emp.employee_id, task_id="task_A", project_id="proj_A")
    assert first is True

    # Second concurrent reservation attempt MUST fail
    second = rm.reserve_employee(emp.employee_id, task_id="task_B", project_id="proj_B")
    assert second is False


def test_workforce_capacity_calculation(temp_db, test_org):
    rm = ResourceManager(organization=test_org, db=temp_db)
    emps = test_org.list_employees()
    total = len(emps)

    cap1 = rm.get_workforce_capacity()
    assert cap1["total_employees"] == total
    assert cap1["available"] == total
    assert cap1["busy"] == 0
    assert cap1["utilization"] == 0.0

    # Reserve 2 employees
    rm.reserve_employee(emps[0].employee_id, "t1", "p1")
    rm.reserve_employee(emps[1].employee_id, "t2", "p2")

    cap2 = rm.get_workforce_capacity()
    assert cap2["busy"] == 2
    assert cap2["available"] == total - 2
    assert cap2["utilization"] > 0.0


# =====================================================================
# 4. Usage Tracker & Budget Enforcement Tests
# =====================================================================

def test_usage_tracker_aggregation(temp_db, event_bus):
    bm = BudgetManager(db=temp_db)
    tracker = UsageTracker(db=temp_db, event_bus=event_bus, cost_calculator=bm)

    tracker.record_usage(project_id="proj_1", employee_id="emp_a", model="gpt-4o", input_tokens=1000, output_tokens=500)
    tracker.record_usage(project_id="proj_1", employee_id="emp_b", model="gpt-4o-mini", input_tokens=2000, output_tokens=1000)
    tracker.record_usage(project_id="proj_2", employee_id="emp_a", model="mock-model", input_tokens=500, output_tokens=250)

    p1_usage = tracker.get_project_usage("proj_1")
    assert p1_usage["total_tokens"] == 4500
    assert p1_usage["total_requests"] == 2
    assert p1_usage["total_cost"] > 0.0

    total_usage = tracker.get_total_usage()
    assert total_usage["total_tokens"] == 5250
    assert total_usage["total_requests"] == 3


def test_budget_warning_and_exceeded_blocking(temp_db, event_bus):
    bm = BudgetManager(db=temp_db, event_bus=event_bus)
    events_received = []
    event_bus.subscribe(lambda e: events_received.append(e))

    bm.set_project_budget(project_id="p_budget", budget=1.00, warning_threshold=0.8)

    # Expense 1: $0.50 (50% - no warning)
    bm.record_expense("p_budget", 0.50)
    assert not any(e.event_type == EVENT_BUDGET_WARNING for e in events_received)
    assert bm.can_spend("p_budget")

    # Expense 2: $0.35 (total $0.85 -> 85% -> 80% warning emitted)
    bm.record_expense("p_budget", 0.35)
    assert any(e.event_type == EVENT_BUDGET_WARNING for e in events_received)
    assert bm.can_spend("p_budget")

    # Expense 3: $0.20 (total $1.05 -> budget exceeded)
    info = bm.record_expense("p_budget", 0.20)
    assert info["is_blocked"] is True
    assert any(e.event_type == EVENT_BUDGET_EXCEEDED for e in events_received)
    assert not bm.can_spend("p_budget")


# =====================================================================
# 5. Scheduler Engine & Multi-Project Operations Tests
# =====================================================================

def test_scheduler_single_project(temp_db, test_org):
    registry = ProjectRegistry(db=temp_db)
    p_queue = ProjectQueue(registry=registry, db=temp_db)
    w_queue = WorkQueue(db=temp_db)
    rm = ResourceManager(organization=test_org, db=temp_db)
    scheduler = SchedulerEngine(
        project_registry=registry,
        project_queue=p_queue,
        work_queue=w_queue,
        resource_manager=rm,
        db=temp_db,
    )

    proj = Project(project_id="proj_s", name="Single Proj", status=ProjectStatus.READY)
    registry.register_project(proj)

    t1 = WorkTask(task_id="ts1", project_id="proj_s", title="Task 1", required_capabilities=["python"])
    t2 = WorkTask(task_id="ts2", project_id="proj_s", title="Task 2", required_capabilities=["html"])
    w_queue.add_task(t1)
    w_queue.add_task(t2)

    # Run scheduler tick without execution
    res = scheduler.tick(execute=False)
    assert res.tasks_evaluated == 2
    assert res.tasks_scheduled == 2
    assert len(res.scheduled_assignments) == 2
    # Verify both employees were locked
    assert len(rm._reservations) == 2


def test_scheduler_multi_project_shared_workforce(temp_db, test_org):
    registry = ProjectRegistry(db=temp_db)
    p_queue = ProjectQueue(registry=registry, db=temp_db)
    w_queue = WorkQueue(db=temp_db)
    rm = ResourceManager(organization=test_org, db=temp_db)
    bm = BudgetManager(db=temp_db)
    usage = UsageTracker(db=temp_db, cost_calculator=bm)

    scheduler = SchedulerEngine(
        project_registry=registry,
        project_queue=p_queue,
        work_queue=w_queue,
        resource_manager=rm,
        budget_manager=bm,
        usage_tracker=usage,
        db=temp_db,
    )

    # 3 Projects: CRITICAL, HIGH, LOW
    p_crit = Project(project_id="p_c", name="Crit Proj", priority=ProjectPriority.CRITICAL, status=ProjectStatus.READY)
    p_high = Project(project_id="p_h", name="High Proj", priority=ProjectPriority.HIGH, status=ProjectStatus.READY)
    p_low = Project(project_id="p_l", name="Low Proj", priority=ProjectPriority.LOW, status=ProjectStatus.READY)

    registry.register_project(p_crit)
    registry.register_project(p_high)
    registry.register_project(p_low)

    w_queue.add_task(WorkTask(task_id="tc1", project_id="p_c", title="Crit Task 1", priority=10, required_capabilities=["python"]))
    w_queue.add_task(WorkTask(task_id="th1", project_id="p_h", title="High Task 1", priority=5, required_capabilities=["python"]))
    w_queue.add_task(WorkTask(task_id="tl1", project_id="p_l", title="Low Task 1", priority=1, required_capabilities=["python"]))

    # Tick with execution enabled
    res = scheduler.tick(execute=True)
    assert res.tasks_scheduled == 3
    assert res.tasks_completed == 3
    # Resources must be cleanly released after completion
    assert len(rm._reservations) == 0


def test_scheduler_failure_recovery(temp_db, test_org):
    registry = ProjectRegistry(db=temp_db)
    p_queue = ProjectQueue(registry=registry, db=temp_db)
    w_queue = WorkQueue(db=temp_db)
    rm = ResourceManager(organization=test_org, db=temp_db)

    scheduler = SchedulerEngine(
        project_registry=registry,
        project_queue=p_queue,
        work_queue=w_queue,
        resource_manager=rm,
        db=temp_db,
    )

    p = Project(project_id="p_fail", name="Fail Recovery Proj", status=ProjectStatus.READY)
    registry.register_project(p)
    w_queue.add_task(WorkTask(task_id="tf1", project_id="p_fail", title="Task that fails initially"))

    # Fail executor on first try
    fail_count = [0]
    def faulty_executor(task, emp):
        if fail_count[0] == 0:
            fail_count[0] += 1
            raise RuntimeError("Temporary worker failure")
        return {"status": "SUCCESS"}

    # Tick 1: Worker fails -> Task should be automatically requeued back to READY and employee released
    res1 = scheduler.tick(execute=True, custom_executor=faulty_executor)
    assert res1.tasks_failed == 1
    assert len(rm._reservations) == 0
    t = w_queue.get_task("tf1")
    assert t.status == TASK_READY

    # Tick 2: Re-attempt -> succeeds
    res2 = scheduler.tick(execute=True, custom_executor=faulty_executor)
    assert res2.tasks_completed == 1
    assert w_queue.get_task("tf1").status == TASK_COMPLETED


# =====================================================================
# 6. Multi-Project Simulation (5 Projects, 20 Employees, 50 Tasks)
# =====================================================================

def test_multi_project_simulation(temp_db):
    """5 active projects, 20 employees, 50 tasks with shared workforce pool."""
    # Build 20 Indonesian employee workforce
    indonesian_names = [
        ("Budi Santoso", "backend_developer", "engineering", ["python", "database", "api"]),
        ("Dewi Lestari", "frontend_developer", "engineering", ["html", "css", "javascript"]),
        ("Rian Pratama", "software_architect", "engineering", ["software_architecture", "planning"]),
        ("Eko Prasetyo", "qa_engineer", "qa", ["testing", "unit_test", "regression_testing"]),
        ("Ratna Sari", "product_manager", "product", ["project_management", "coordination"]),
        ("Panji Nugroho", "conceptor", "product", ["requirements_analysis", "acceptance_criteria"]),
        ("Maya Anggraini", "security_engineer", "engineering", ["security_audit", "vulnerability_assessment"]),
        ("Bagas Aditya", "devops_engineer", "devops", ["ci_cd", "deployment"]),
        ("Citra Dewi", "technical_writer", "documentation", ["technical_writing", "api_docs"]),
        ("Surya Pratama", "mobile_developer", "engineering", ["mobile", "flutter"]),
        ("Dian Sastro", "backend_developer", "engineering", ["python", "modular_coding"]),
        ("Reza Rahadian", "fullstack_developer", "engineering", ["python", "javascript", "api"]),
        ("Ayu Pertiwi", "business_analyst", "product", ["workflow_analysis", "metrics"]),
        ("Fajar Hidayat", "qa_engineer", "qa", ["testing", "automation"]),
        ("Gita Gutawa", "frontend_developer", "engineering", ["ui_components", "css"]),
        ("Hendra Setiawan", "backend_developer", "engineering", ["sqlite", "database"]),
        ("Indah Permata", "product_researcher", "product", ["user_research", "benchmarking"]),
        ("Joko Widodo", "support_lead", "support", ["incident_response", "coordination"]),
        ("Kartika Putri", "technical_writer", "documentation", ["documentation", "user_guides"]),
        ("Lukman Sardi", "software_architect", "engineering", ["system_design", "dependency_graph"]),
    ]

    org = Organization(name="test_org_50")
    for idx, (name, role, dept, caps) in enumerate(indonesian_names):
        emp_id = f"emp_{idx+1:02d}"
        emp = Employee(
            employee_id=emp_id,
            name=name,
            role=role,
            department=dept,
            capabilities=caps,
            status=STATUS_ACTIVE,
            availability=AVAILABILITY_AVAILABLE,
        )
        org.register_employee(emp)

    orch = OfficeOrchestrator(db=temp_db, organization=org)

    # 5 Projects with varied priorities
    projects_def = [
        ("p_saas", "PROJECT A — SaaS Landing Page", ProjectPriority.CRITICAL, 20.0),
        ("p_mobile", "PROJECT B — Mobile App", ProjectPriority.HIGH, 30.0),
        ("p_seo", "PROJECT C — SEO Campaign", ProjectPriority.NORMAL, 15.0),
        ("p_research", "PROJECT D — Product Research", ProjectPriority.NORMAL, 10.0),
        ("p_dash", "PROJECT E — Internal Dashboard", ProjectPriority.LOW, 10.0),
    ]

    for pid, name, prio, bud in projects_def:
        orch.create_project(
            project_id=pid,
            name=name,
            priority=prio,
            budget=bud,
            status=ProjectStatus.READY,
        )

    # Generate 50 tasks total (10 per project) with dependencies
    for pid, _, _, _ in projects_def:
        prev_task_id = None
        for t_idx in range(1, 11):
            t_id = f"{pid}_t{t_idx}"
            deps = [prev_task_id] if prev_task_id and t_idx % 3 != 1 else []
            caps = ["python"] if t_idx % 2 == 0 else ["html", "css"]
            orch.submit_task(
                project_id=pid,
                title=f"Subtask {t_idx} for {pid}",
                task_id=t_id,
                priority=10 - t_idx,
                dependencies=deps,
                required_capabilities=caps,
            )
            prev_task_id = t_id

    # Run orchestrator until completion
    t_start = time.perf_counter()
    summary = orch.run_until_complete(max_ticks=200)
    t_duration = time.perf_counter() - t_start

    assert summary["total_completed"] == 50
    assert summary["final_state"]["completed_tasks"] == 50
    assert summary["final_state"]["running_tasks"] == 0
    assert summary["final_state"]["queued_tasks"] == 0

    # Ensure no employees remain reserved
    cap = orch.resource_manager.get_workforce_capacity()
    assert cap["busy"] == 0
    assert cap["available"] == 20
    assert len(orch.db.list_reservations()) == 0


# =====================================================================
# 7. Deterministic Load Test Simulation (10 Projects, 50 Employees, 100 Tasks)
# =====================================================================

def test_load_simulation_100_tasks(temp_db):
    """100 tasks, 50 employees, 10 projects without state corruption."""
    org = Organization(name="load_org_100")
    for i in range(1, 51):
        emp_id = f"load_emp_{i:03d}"
        role = "backend_developer" if i % 2 == 0 else "frontend_developer"
        caps = ["python", "database"] if i % 2 == 0 else ["html", "css", "javascript"]
        org.register_employee(
            Employee(
                employee_id=emp_id,
                name=f"Karyawan {i}",
                role=role,
                department="engineering",
                capabilities=caps,
                status=STATUS_ACTIVE,
                availability=AVAILABILITY_AVAILABLE,
            )
        )

    orch = OfficeOrchestrator(db=temp_db, organization=org)

    # 10 Projects
    for p_i in range(1, 11):
        pid = f"load_p_{p_i}"
        prio = ProjectPriority.CRITICAL if p_i <= 2 else (ProjectPriority.HIGH if p_i <= 5 else ProjectPriority.NORMAL)
        orch.create_project(
            project_id=pid,
            name=f"Load Project {p_i}",
            priority=prio,
            status=ProjectStatus.READY,
            budget=100.0,
        )

    # 100 Tasks (10 per project)
    for p_i in range(1, 11):
        pid = f"load_p_{p_i}"
        for t_i in range(1, 11):
            t_id = f"{pid}_task_{t_i}"
            orch.submit_task(
                project_id=pid,
                title=f"Task {t_i} of {pid}",
                task_id=t_id,
                priority=t_i,
                required_capabilities=["python"] if t_i % 2 == 0 else ["html"],
            )

    t_start = time.perf_counter()
    summary = orch.run_until_complete(max_ticks=50)
    duration_ms = (time.perf_counter() - t_start) * 1000.0

    assert summary["total_completed"] == 100
    assert summary["final_state"]["completed_tasks"] == 100
    assert summary["final_state"]["running_tasks"] == 0
    assert summary["final_state"]["queued_tasks"] == 0

    # Ensure all 10 projects reached COMPLETED status
    completed_projects = [p for p in orch.project_registry.list_projects() if p.status == ProjectStatus.COMPLETED]
    assert len(completed_projects) == 10

    # Capacity check
    cap = orch.resource_manager.get_workforce_capacity()
    assert cap["busy"] == 0
    assert cap["available"] == 50
    assert len(orch.db.list_reservations()) == 0

    print(f"\n⚡ Load Simulation completed 100 tasks in {duration_ms:.2f}ms across {summary['ticks_run']} ticks")

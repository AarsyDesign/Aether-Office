"""Phase 6.5 Production Hardening Audit Test Suite.
Tests edge cases, crash recovery, concurrency, state machine boundaries,
budget consistency, scheduler idempotency, and LLM failure handling.
"""

import pytest
import time
import json
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

from db import Database
from events import (
    EventBus,
    Event,
    EVENT_PROJECT_CREATED,
    EVENT_PROJECT_COMPLETED,
    EVENT_PROJECT_FAILED,
    EVENT_TASK_SCHEDULED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_EMPLOYEE_RESERVED,
    EVENT_EMPLOYEE_RELEASED,
    EVENT_RESOURCE_CONFLICT,
    EVENT_BUDGET_WARNING,
    EVENT_BUDGET_EXCEEDED,
)
from workforce import (
    Organization,
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
    TASK_CANCELLED,
    TASK_BLOCKED,
)
from projects import (
    Project,
    ProjectStatus,
    ProjectPriority,
    ProjectRegistry,
    InvalidProjectStateTransition,
    validate_project_transition,
)
from office_queue import ProjectQueue, WorkQueue
from resources import ResourceManager
from usage import UsageTracker
from budget import BudgetManager
from scheduler import SchedulerEngine, ScheduleResult
from office import OfficeOrchestrator


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "aether_hardening.db")
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


# =====================================================================
# 1. Scheduler Idempotency
# =====================================================================

def test_scheduler_idempotency(temp_db, test_org):
    """Calling tick() twice in succession without state change must be idempotent:
    - Does NOT double-schedule running tasks.
    - Does NOT double-reserve employees.
    - Does NOT double-count completed tasks.
    """
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

    proj = Project(project_id="p_idem", name="Idempotency Proj", status=ProjectStatus.READY)
    registry.register_project(proj)
    w_queue.add_task(WorkTask(task_id="t_id1", project_id="p_idem", title="Idem Task 1", required_capabilities=["python"]))
    w_queue.add_task(WorkTask(task_id="t_id2", project_id="p_idem", title="Idem Task 2", required_capabilities=["python"]))

    # Tick 1 without execute: schedules both tasks, marks them running, reserves employees
    res1 = scheduler.tick(execute=False)
    assert res1.tasks_scheduled == 2
    assert len(rm._reservations) == 2

    # Tick 2 called immediately without external state change
    res2 = scheduler.tick(execute=False)
    # Tasks are already IN_PROGRESS, so ready_tasks count is 0
    assert res2.tasks_scheduled == 0
    assert res2.conflicts_detected == 0
    assert len(rm._reservations) == 2  # No duplicate reservations added

    # Now execute tick with execution enabled: completes running tasks
    # Requeue tasks for execution test
    w_queue.mark_completed("t_id1", result={"ok": True})
    w_queue.mark_completed("t_id2", result={"ok": True})
    for emp_id in list(rm._reservations.keys()):
        rm.release_employee(emp_id)

    # Tick 3: Everything completed -> 0 scheduled
    res3 = scheduler.tick(execute=True)
    assert res3.tasks_scheduled == 0
    assert res3.tasks_completed == 0
    assert len(rm._reservations) == 0


# =====================================================================
# 2. Concurrent Scheduler Execution & Distributed Locking
# =====================================================================

def test_concurrent_scheduler(temp_db, test_org):
    """When two scheduler instances attempt to tick concurrently on the same DB:
    - Distributed scheduler lock allows exactly one to proceed.
    - The second scheduler detects the lock conflict and aborts cleanly without corrupting state.
    """
    registry = ProjectRegistry(db=temp_db)
    p_queue = ProjectQueue(registry=registry, db=temp_db)
    w_queue = WorkQueue(db=temp_db)
    rm = ResourceManager(organization=test_org, db=temp_db)

    scheduler_a = SchedulerEngine(
        project_registry=registry,
        project_queue=p_queue,
        work_queue=w_queue,
        resource_manager=rm,
        db=temp_db,
    )
    scheduler_b = SchedulerEngine(
        project_registry=registry,
        project_queue=p_queue,
        work_queue=w_queue,
        resource_manager=rm,
        db=temp_db,
    )

    proj = Project(project_id="p_conc", name="Concurrent Proj", status=ProjectStatus.READY)
    registry.register_project(proj)
    w_queue.add_task(WorkTask(task_id="tc_1", project_id="p_conc", title="Conc Task", required_capabilities=["python"]))

    # Simulate scheduler_a holding the lock
    acquired = temp_db.acquire_scheduler_lock(lock_name="office_scheduler", locked_by="scheduler_a", ttl_seconds=30.0)
    assert acquired is True

    # Scheduler B tries to tick while lock is held
    res_b = scheduler_b.tick()
    assert res_b.conflicts_detected == 1
    assert res_b.tasks_scheduled == 0

    # Release lock from scheduler_a
    released = temp_db.release_scheduler_lock(lock_name="office_scheduler", locked_by="scheduler_a")
    assert released is True

    # Scheduler B can now acquire and tick successfully
    res_b2 = scheduler_b.tick()
    assert res_b2.conflicts_detected == 0
    assert res_b2.tasks_scheduled == 1


# =====================================================================
# 3. Stale Employee Reservation Recovery
# =====================================================================

def test_stale_reservation_recovery(temp_db, test_org):
    """Employee reservation with expired lease must be detected and cleanly recovered:
    - Stale reservation is purged from DB and memory.
    - Employee status restored to available and IDLE.
    - Employee can immediately be reserved for new work.
    """
    rm = ResourceManager(organization=test_org, db=temp_db)
    emp = test_org.list_employees()[0]

    # Reserve employee with 0.05 second lease
    reserved = rm.reserve_employee(
        employee_id=emp.employee_id,
        task_id="stale_task_1",
        project_id="proj_stale",
        lease_seconds=0.05,
    )
    assert reserved is True
    assert emp.availability == AVAILABILITY_BUSY

    # Wait for lease to expire
    time.sleep(0.08)

    # is_reserved should detect expired lease
    assert rm.is_reserved(emp.employee_id) is False

    # Recover stale reservations explicitly
    stale = rm.recover_stale_reservations()
    assert len(stale) == 1
    assert stale[0]["employee_id"] == emp.employee_id
    assert emp.availability == AVAILABILITY_AVAILABLE
    assert emp.live_state == STATE_IDLE

    # Employee can now be reserved without collision
    reserved_again = rm.reserve_employee(
        employee_id=emp.employee_id,
        task_id="new_task_2",
        project_id="proj_stale",
        lease_seconds=300.0,
    )
    assert reserved_again is True


# =====================================================================
# 4. Worker Crash Recovery
# =====================================================================

def test_worker_crash_recovery(temp_db, test_org):
    """Simulates a worker crashing while executing a task:
    reserve employee -> worker process killed -> task remains IN_PROGRESS -> scheduler recovery.
    - Employee reservation cleaned.
    - Task is requeued back to READY.
    - Subsequent scheduler tick reassigns and completes the task.
    """
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

    proj = Project(project_id="p_crash", name="Crash Test", status=ProjectStatus.READY)
    registry.register_project(proj)
    task = WorkTask(task_id="t_crash", project_id="p_crash", title="Crash Task", required_capabilities=["python"])
    w_queue.add_task(task)

    # Schedule task into IN_PROGRESS with short lease
    scheduler.tick(execute=False)
    assert w_queue.get_task("t_crash").status == TASK_IN_PROGRESS
    assert len(rm._reservations) == 1

    # Simulate crash: process abruptly dies, leaving reservation expired in DB
    # Force DB expiration
    past_iso = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    temp_db.conn.execute("UPDATE employee_reservations SET expires_at = ?, reserved_at = ?", (past_iso, past_iso))
    temp_db.conn.commit()

    # Clear in-memory cache to simulate new process starting
    rm._reservations.clear()

    # Run recovery
    recovered = rm.recover_stale_reservations(work_queue=w_queue)
    assert len(recovered) == 1

    # Task should be restored to READY
    assert w_queue.get_task("t_crash").status == TASK_READY

    # Next tick successfully re-executes task
    res = scheduler.tick(execute=True)
    assert res.tasks_scheduled == 1
    assert res.tasks_completed == 1
    assert w_queue.get_task("t_crash").status == TASK_COMPLETED


# =====================================================================
# 5. Task Execution Failure & Automatic Requeue
# =====================================================================

def test_task_execution_failure(temp_db, test_org):
    """When a worker execution raises an unexpected Exception:
    - Exception does NOT escape scheduler loop.
    - Employee reservation is released immediately.
    - Task is marked FAILED and automatically requeued to READY.
    - Scheduler run metrics accurately record 1 failed task.
    """
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

    proj = Project(project_id="p_fail", name="Fail Proj", status=ProjectStatus.READY)
    registry.register_project(proj)
    w_queue.add_task(WorkTask(task_id="t_err", project_id="p_fail", title="Error Task"))

    def exploding_executor(task, emp):
        raise ZeroDivisionError("Simulated computational arithmetic error in agent runtime")

    res = scheduler.tick(execute=True, custom_executor=exploding_executor)
    assert res.tasks_failed == 1
    assert res.tasks_completed == 0
    # Employee must be released
    assert len(rm._reservations) == 0
    # Task was requeued to READY
    assert w_queue.get_task("t_err").status == TASK_READY


# =====================================================================
# 6. LLM Timeout Recovery
# =====================================================================

def test_llm_timeout_recovery(temp_db, test_org):
    """Simulates LLM API timeout during agent execution:
    - Timeout is handled gracefully at the boundary.
    - Task is requeued and completes on subsequent retry.
    """
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

    proj = Project(project_id="p_to", name="Timeout Proj", status=ProjectStatus.READY)
    registry.register_project(proj)
    w_queue.add_task(WorkTask(task_id="t_to", project_id="p_to", title="LLM Call Task"))

    attempts = [0]
    def timeout_then_succeed_executor(task, emp):
        attempts[0] += 1
        if attempts[0] == 1:
            raise TimeoutError("HTTP 504: Gateway Timeout to Gemini API endpoint")
        return {"result": "LLM response successfully generated"}

    # Tick 1: times out
    res1 = scheduler.tick(execute=True, custom_executor=timeout_then_succeed_executor)
    assert res1.tasks_failed == 1
    assert len(rm._reservations) == 0
    assert w_queue.get_task("t_to").status == TASK_READY

    # Tick 2: retries and succeeds
    res2 = scheduler.tick(execute=True, custom_executor=timeout_then_succeed_executor)
    assert res2.tasks_completed == 1
    assert w_queue.get_task("t_to").status == TASK_COMPLETED


# =====================================================================
# 7. LLM Malformed Response Handling
# =====================================================================

def test_llm_malformed_response(temp_db, test_org):
    """Simulates malformed / invalid JSON / empty response from LLM:
    - Caught without crashing orchestration.
    - Task status and error reason captured.
    """
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

    proj = Project(project_id="p_mal", name="Malformed JSON Proj", status=ProjectStatus.READY)
    registry.register_project(proj)
    w_queue.add_task(WorkTask(task_id="t_mal", project_id="p_mal", title="JSON Parsing Task"))

    def malformed_json_executor(task, emp):
        raw_response = "```json\n{ invalid_json: missing_quotes "
        json.loads(raw_response)

    res = scheduler.tick(execute=True, custom_executor=malformed_json_executor)
    assert res.tasks_failed == 1
    assert len(rm._reservations) == 0
    assert w_queue.get_task("t_mal").status == TASK_READY


# =====================================================================
# 8. Budget Concurrency & Atomic Spending Updates
# =====================================================================

def test_budget_concurrency(tmp_path):
    """Multiple concurrent threads updating budget spent on shared SQLite database:
    - Atomic SQL calculation: spent = spent + ?
    - No lost updates from race conditions.
    - Budget warnings and automatic blocking triggered accurately.
    """
    db_file = str(tmp_path / "budget_race.db")
    db_init = Database(db_file)
    db_init.save_project(project_id="p_bgt", name="Budget Concurrency", budget=50.0, spent=0.0)
    db_init.save_project_budget(project_id="p_bgt", budget=50.0, spent=0.0)
    db_init.close()

    # Run 10 threads, each making 5 updates of 1.0 = 50.0 total
    num_threads = 10
    updates_per_thread = 5

    def worker_spend():
        thread_db = Database(db_file)
        try:
            for _ in range(updates_per_thread):
                thread_db.update_project_budget_spent("p_bgt", delta_spent=1.0)
        finally:
            thread_db.close()

    threads = [threading.Thread(target=worker_spend) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    verify_db = Database(db_file)
    bgt = verify_db.get_project_budget("p_bgt")
    verify_db.close()

    expected_spent = num_threads * updates_per_thread * 1.0  # 50.0
    assert bgt is not None
    assert abs(bgt["spent"] - expected_spent) < 1e-6
    assert bgt["is_blocked"] == 1


# =====================================================================
# 9. Usage Record Atomicity & Thresholds
# =====================================================================

def test_usage_atomicity(temp_db, event_bus):
    """Tests usage tracking thresholds (79%, 80%, 89%, 90%, 99%, 100%, >100%):
    - 80% threshold emits EVENT_BUDGET_WARNING
    - 90% threshold emits EVENT_BUDGET_WARNING
    - 100% threshold emits EVENT_BUDGET_EXCEEDED
    - spent > 100% blocks project from spending
    """
    bm = BudgetManager(db=temp_db, event_bus=event_bus)
    tracker = UsageTracker(db=temp_db, event_bus=event_bus, cost_calculator=bm)

    events_captured = []
    event_bus.subscribe(lambda e: events_captured.append(e))


    temp_db.save_project(project_id="p_audit", name="Threshold Test", budget=100.0, spent=0.0)
    bm.set_project_budget("p_audit", budget=100.0, warning_threshold=0.8)

    # 1. spent = 79% ($79)
    bm.record_expense("p_audit", 79.0)
    assert bm.can_spend("p_audit") is True
    assert len([e for e in events_captured if e.event_type == EVENT_BUDGET_WARNING]) == 0

    # 2. spent = 80% ($80)
    bm.record_expense("p_audit", 1.0)
    assert bm.can_spend("p_audit") is True
    assert len([e for e in events_captured if e.event_type == EVENT_BUDGET_WARNING]) == 1

    # 3. spent = 90% ($90)
    bm.record_expense("p_audit", 10.0)
    assert bm.can_spend("p_audit") is True
    assert len([e for e in events_captured if e.event_type == EVENT_BUDGET_WARNING]) >= 2

    # 4. spent = 100% ($100)
    bm.record_expense("p_audit", 10.0)
    assert len([e for e in events_captured if e.event_type == EVENT_BUDGET_EXCEEDED]) == 1

    # 5. spent > 100% ($105)
    bm.record_expense("p_audit", 5.0)
    assert bm.can_spend("p_audit") is False
    assert bm.is_blocked("p_audit") is True


# =====================================================================
# 10. State Machine Integrity & Illegal Transition Rejection
# =====================================================================

def test_invalid_state_transition(temp_db):
    """Enforces strict state machine boundaries:
    - Terminal states (COMPLETED, FAILED, CANCELLED) cannot jump back to RUNNING.
    - WorkTask invalid transitions (e.g. COMPLETED -> IN_PROGRESS) raise ValueError.
    - State is never corrupted on rejected transition.
    """
    registry = ProjectRegistry(db=temp_db)
    proj = Project(project_id="p_state", name="State Test", status=ProjectStatus.READY)
    registry.register_project(proj)

    # Valid progression: READY -> RUNNING -> COMPLETED
    registry.update_status("p_state", ProjectStatus.RUNNING)
    assert registry.get_project("p_state").status == ProjectStatus.RUNNING

    registry.complete_project("p_state")
    assert registry.get_project("p_state").status == ProjectStatus.COMPLETED

    # Illegal: COMPLETED -> RUNNING must raise InvalidProjectStateTransition
    with pytest.raises(InvalidProjectStateTransition):
        registry.update_status("p_state", ProjectStatus.RUNNING)

    # Illegal: COMPLETED -> PAUSED must raise InvalidProjectStateTransition
    with pytest.raises(InvalidProjectStateTransition):
        registry.update_status("p_state", ProjectStatus.PAUSED)

    # Verify project status remains COMPLETED
    assert registry.get_project("p_state").status == ProjectStatus.COMPLETED

    # Test WorkTask state transition validation
    wt = WorkTask(task_id="wt_01", project_id="p_state", title="State Task", status=TASK_COMPLETED)
    with pytest.raises(ValueError):
        wt.transition_to(TASK_IN_PROGRESS)

    wt_fail = WorkTask(task_id="wt_02", project_id="p_state", title="Failed Task", status=TASK_CANCELLED)
    with pytest.raises(ValueError):
        wt_fail.transition_to(TASK_IN_PROGRESS)


# =====================================================================
# 11. Process Restart Recovery Simulation
# =====================================================================

def test_process_restart_recovery(tmp_path):
    """Simulates complete process death and cold restart:
    1. Start orchestrator on disk DB.
    2. Register project and tasks.
    3. Tick scheduler so task is IN_PROGRESS and employee reserved.
    4. Terminate process (delete Python objects, close DB).
    5. Spin up entirely new OfficeOrchestrator instance pointing to same SQLite file.
    6. Verify startup auto-recovery clears stale reservations, restores employees, and requeues tasks.
    7. Finish execution smoothly.
    """
    db_file = str(tmp_path / "restart_sim.db")

    # Phase A: Initial process run
    db_a = Database(db_file)
    org_a, _ = create_default_organization()
    orch_a = OfficeOrchestrator(db=db_a, organization=org_a)

    orch_a.create_project(project_id="p_res", name="Restart Project", status=ProjectStatus.READY)
    orch_a.submit_task(project_id="p_res", title="Task A", task_id="t_res_1", required_capabilities=["python"])

    # Tick without execution -> marks running, reserves employee
    orch_a.scheduler_tick(execute=False)
    assert orch_a.work_queue.get_task("t_res_1").status == TASK_IN_PROGRESS

    # Simulate crash before completion
    db_a.close()
    del orch_a
    del db_a

    # Phase B: Cold Restart
    db_b = Database(db_file)
    org_b, _ = create_default_organization()
    orch_b = OfficeOrchestrator(db=db_b, organization=org_b)

    # Auto-recovery triggered on __init__
    # Task should be requeued back to READY
    task_recovered = orch_b.work_queue.get_task("t_res_1")
    assert task_recovered.status == TASK_READY

    # Complete execution on new orchestrator
    summary = orch_b.run_until_complete(max_ticks=5)
    assert summary["total_completed"] >= 1
    assert orch_b.project_registry.get_project("p_res").status == ProjectStatus.COMPLETED

    db_b.close()


# =====================================================================
# 12. Partial Transaction Recovery & Rollback
# =====================================================================

def test_partial_transaction_recovery(tmp_path):
    """Simulates transaction rollback during partial database updates:
    Ensures that if an operation fails midway, no half-applied mutations remain.
    """
    db_file = str(tmp_path / "rollback_test.db")
    db = Database(db_file)

    db.save_project(project_id="p_tx", name="Transaction Test", budget=100.0, spent=0.0)

    # Perform a transaction that deliberately fails
    try:
        with db.conn:
            db.conn.execute("UPDATE projects SET spent = 50.0 WHERE id = 'p_tx'")
            # Deliberate failure violating constraint
            db.conn.execute("INSERT INTO projects (id, name) VALUES ('p_tx', 'Duplicate ID Failure')")
    except Exception:
        pass  # Expected SQLite IntegrityError

    # Verify spent was rolled back to 0.0
    proj = db.get_project("p_tx")
    assert proj["spent"] == 0.0
    db.close()

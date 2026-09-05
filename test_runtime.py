"""Phase 7 Runtime Engine Test Suite.
Tests the persistent runtime, scheduler heartbeat, worker execution boundary,
artifact creation, budget & usage tracking, graceful shutdown, and cold-start recovery.
"""

import pytest
import time
import threading
from pathlib import Path

from db import Database
from events import (
    EventBus,
    Event,
    EVENT_RUNTIME_STARTED,
    EVENT_RUNTIME_STOPPED,
    EVENT_SCHEDULER_TICK_STARTED,
    EVENT_SCHEDULER_TICK_COMPLETED,
    EVENT_TASK_DISPATCHED,
    EVENT_WORKER_RESERVED,
    EVENT_WORKER_RELEASED,
    EVENT_TASK_SCHEDULED,
    EVENT_TASK_COMPLETED,
    EVENT_EMPLOYEE_RESERVED,
    EVENT_EMPLOYEE_RELEASED,
)
from workforce import (
    Organization,
    Employee,
    STATUS_ACTIVE,
    AVAILABILITY_AVAILABLE,
    STATE_IDLE,
    create_default_organization,
)
from tasks import (
    WorkTask,
    TASK_PENDING,
    TASK_READY,
    TASK_IN_PROGRESS,
    TASK_COMPLETED,
    TASK_FAILED,
)
from projects import Project, ProjectStatus, ProjectPriority, ProjectRegistry
from office_queue import ProjectQueue, WorkQueue
from resources import ResourceManager
from usage import UsageTracker
from budget import BudgetManager
from scheduler import SchedulerEngine
from office import OfficeOrchestrator
from result import AgentResult
from artifacts import Artifact, ArtifactStore, ARTIFACT_DOCUMENT
from runtime import OfficeRuntime, RuntimeConfig, TaskWorker, WorkerState


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "aether_runtime.db")
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
def sample_orchestrator(temp_db, test_org, event_bus):
    temp_db.sync_organization_to_db(test_org)
    orch = OfficeOrchestrator(
        db=temp_db,
        organization=test_org,
        event_bus=event_bus,
    )
    return orch


# =====================================================================
# 1. test_runtime_start
# =====================================================================

def test_runtime_start(sample_orchestrator, event_bus):
    """Verify runtime start sets running state, emits event, and spins heartbeat."""
    started_events = []
    event_bus.subscribe(lambda e: started_events.append(e) if e.event_type == EVENT_RUNTIME_STARTED else None)

    cfg = RuntimeConfig(heartbeat_interval=0.05)
    runtime = sample_orchestrator.get_runtime(config=cfg)

    assert not runtime.is_running
    runtime.start(in_background=True)

    try:
        assert runtime.is_running
        time.sleep(0.12)
        assert len(started_events) == 1
        assert started_events[0].event_type == EVENT_RUNTIME_STARTED
        assert runtime.ticks_count >= 1
    finally:
        runtime.stop()


# =====================================================================
# 2. test_runtime_stop
# =====================================================================

def test_runtime_stop(sample_orchestrator, event_bus):
    """Verify runtime stop gracefully terminates heartbeat loop, cleans locks, and emits event."""
    stopped_events = []
    event_bus.subscribe(lambda e: stopped_events.append(e) if e.event_type == EVENT_RUNTIME_STOPPED else None)

    cfg = RuntimeConfig(heartbeat_interval=0.05)
    runtime = sample_orchestrator.get_runtime(config=cfg)

    runtime.start(in_background=True)
    assert runtime.is_running
    time.sleep(0.08)

    runtime.stop(timeout=2.0)

    assert not runtime.is_running
    assert len(stopped_events) == 1
    assert stopped_events[0].event_type == EVENT_RUNTIME_STOPPED
    # Scheduler lock in DB should be freed
    lock_held = sample_orchestrator.db.acquire_scheduler_lock(lock_name="office_scheduler", locked_by="tester")
    assert lock_held is True
    sample_orchestrator.db.release_scheduler_lock(lock_name="office_scheduler", locked_by="tester")


# =====================================================================
# 3. test_runtime_heartbeat
# =====================================================================

def test_runtime_heartbeat(sample_orchestrator):
    """Verify runtime executes periodic heartbeat ticks and increments ticks_count."""
    cfg = RuntimeConfig(heartbeat_interval=0.04)
    runtime = sample_orchestrator.get_runtime(config=cfg)

    runtime.start(in_background=True)
    try:
        time.sleep(0.2)
        assert runtime.ticks_count >= 3
        status = runtime.status()
        assert status["is_running"] is True
        assert status["ticks_count"] >= 3
        assert status["uptime_seconds"] > 0
    finally:
        runtime.stop()


# =====================================================================
# 4. test_graceful_shutdown
# =====================================================================

def test_graceful_shutdown(sample_orchestrator, temp_db):
    """Verify graceful shutdown completes current safe work and does not leave corrupted state."""
    p = Project(project_id="p_shutdown", name="Shutdown Test", status=ProjectStatus.READY)
    sample_orchestrator.project_registry.register_project(p)
    t = WorkTask(task_id="t_shut", project_id="p_shutdown", title="Long Safe Task")
    sample_orchestrator.work_queue.add_task(t)

    # Custom executor simulating a task taking 0.1s
    def safe_exec(task, emp):
        time.sleep(0.08)
        return AgentResult(success=True, output="Finished cleanly")

    cfg = RuntimeConfig(heartbeat_interval=0.05)
    runtime = sample_orchestrator.get_runtime(config=cfg)

    # Run 1 tick in thread then stop
    th = threading.Thread(target=lambda: runtime.tick(execute=True, custom_executor=safe_exec))
    th.start()
    time.sleep(0.02)
    runtime.stop()
    th.join()

    # Task should have completed cleanly without corruption
    saved_task = sample_orchestrator.work_queue.get_task("t_shut")
    assert saved_task.status == TASK_COMPLETED
    assert len(sample_orchestrator.resource_manager._reservations) == 0


# =====================================================================
# 5. test_scheduler_continuous_execution
# =====================================================================

def test_scheduler_continuous_execution(sample_orchestrator):
    """Verify multiple queued tasks are continuously dispatched and completed across heartbeat ticks."""
    p = Project(project_id="p_continuous", name="Continuous Project", status=ProjectStatus.READY)
    sample_orchestrator.project_registry.register_project(p)

    for i in range(4):
        sample_orchestrator.work_queue.add_task(
            WorkTask(task_id=f"tc_{i}", project_id="p_continuous", title=f"Continuous Task {i}", priority=i)
        )

    cfg = RuntimeConfig(heartbeat_interval=0.03)
    runtime = sample_orchestrator.get_runtime(config=cfg)

    # Let runtime run continuously until max_ticks=8
    runtime.run(max_ticks=6)

    # All 4 tasks should be completed
    tasks = [t for t in sample_orchestrator.work_queue.list_all_tasks() if t.project_id == "p_continuous"]
    assert len(tasks) == 4
    for t in tasks:
        assert t.status == TASK_COMPLETED
    assert len(sample_orchestrator.resource_manager._reservations) == 0


# =====================================================================
# 6. test_worker_execution
# =====================================================================

def test_worker_execution(sample_orchestrator, test_org, event_bus):
    """Verify TaskWorker lifecycle: IDLE -> RESERVED -> EXECUTING -> SUCCESS -> RELEASED."""
    worker_events = []
    event_bus.subscribe(lambda e: worker_events.append(e) if e.event_type in [EVENT_WORKER_RESERVED, EVENT_WORKER_RELEASED] else None)

    worker = TaskWorker(
        worker_id="worker_test_01",
        artifact_store=sample_orchestrator.artifact_store,
        event_bus=event_bus,
    )

    emp = test_org.employees.list()[0]
    task = WorkTask(task_id="tw_01", project_id="p_worker", title="Worker Unit Task")

    assert worker.state == WorkerState.IDLE
    result = worker.execute(task=task, employee=emp)

    assert isinstance(result, AgentResult)
    assert result.success is True
    assert worker.state == WorkerState.RELEASED
    assert len(worker_events) == 2
    assert worker_events[0].event_type == EVENT_WORKER_RESERVED
    assert worker_events[1].event_type == EVENT_WORKER_RELEASED


# =====================================================================
# 7. test_worker_failure
# =====================================================================

def test_worker_failure(sample_orchestrator, test_org):
    """Verify TaskWorker failure boundary: worker failure does not crash office or leave worker locked."""
    def broken_executor(task, emp):
        raise ValueError("Critical LLM inference engine timeout")

    worker = TaskWorker(
        worker_id="worker_broken_01",
        custom_executor=broken_executor,
        artifact_store=sample_orchestrator.artifact_store,
    )

    emp = test_org.employees.list()[0]
    task = WorkTask(task_id="tw_fail", project_id="p_fail", title="Failing Task")

    res = worker.execute(task=task, employee=emp)

    assert isinstance(res, AgentResult)
    assert res.success is False
    assert "Critical LLM inference engine timeout" in str(res.error)
    assert worker.state == WorkerState.RELEASED


# =====================================================================
# 8. test_artifact_creation
# =====================================================================

def test_artifact_creation(sample_orchestrator, test_org):
    """Verify successful TaskWorker execution registers an Artifact linked to project, task, and employee."""
    store = ArtifactStore(db=sample_orchestrator.db)
    worker = TaskWorker(
        worker_id="worker_art_01",
        artifact_store=store,
    )

    emp = test_org.employees.list()[0]
    task = WorkTask(task_id="t_art", project_id="p_art_proj", title="Design Document Generation")

    res = worker.execute(task=task, employee=emp)
    assert res.success is True
    assert len(task.artifacts) == 1
    art_id = task.artifacts[0]

    art = store.get_artifact(art_id)
    assert art is not None
    assert art.task_id == "t_art"
    assert art.project_id == "p_art_proj"
    assert art.created_by == emp.employee_id
    assert art.type == ARTIFACT_DOCUMENT
    assert "worker_id" in art.metadata
    assert "timestamp" in art.metadata


# =====================================================================
# 9. test_usage_recording_after_execution
# =====================================================================

def test_usage_recording_after_execution(sample_orchestrator):
    """Verify AgentResult usage tokens are recorded in UsageTracker after scheduler tick."""
    p = Project(project_id="p_usage_test", name="Usage Project", status=ProjectStatus.READY)
    sample_orchestrator.project_registry.register_project(p)
    t = WorkTask(task_id="t_use", project_id="p_usage_test", title="Usage Task")
    sample_orchestrator.work_queue.add_task(t)

    # Initial usage should be 0
    u0 = sample_orchestrator.usage_tracker.get_project_usage("p_usage_test")
    assert u0["total_tokens"] == 0

    runtime = sample_orchestrator.get_runtime()
    res = runtime.tick(execute=True)

    assert res.tasks_completed == 1
    u1 = sample_orchestrator.usage_tracker.get_project_usage("p_usage_test")
    assert u1["total_tokens"] > 0
    assert u1["total_input_tokens"] > 0
    assert u1["total_output_tokens"] > 0


# =====================================================================
# 10. test_budget_update_after_execution
# =====================================================================

def test_budget_update_after_execution(sample_orchestrator):
    """Verify project budget spent increases based on token usage after execution."""
    p = Project(
        project_id="p_bgt_test",
        name="Budget Project",
        status=ProjectStatus.READY,
        budget=50.0,
    )
    sample_orchestrator.project_registry.register_project(p)
    sample_orchestrator.budget_manager.set_project_budget("p_bgt_test", 50.0)

    t = WorkTask(task_id="t_bgt", project_id="p_bgt_test", title="Budget Task")
    sample_orchestrator.work_queue.add_task(t)

    b0 = sample_orchestrator.budget_manager.get_project_budget("p_bgt_test")
    assert b0["spent"] == 0.0

    runtime = sample_orchestrator.get_runtime()
    res = runtime.tick(execute=True)
    assert res.tasks_completed == 1

    b1 = sample_orchestrator.budget_manager.get_project_budget("p_bgt_test")
    assert b1["spent"] > 0.0
    assert b1["remaining"] < 50.0


# =====================================================================
# 11. test_end_to_end_project_execution
# =====================================================================

def test_end_to_end_project_execution(sample_orchestrator, event_bus):
    """Integration Test:
    CREATE PROJECT -> CREATE TASK -> SCHEDULER -> RESERVE EMPLOYEE ->
    EXECUTE AGENT -> CREATE RESULT -> RECORD USAGE -> UPDATE BUDGET ->
    COMPLETE TASK -> RELEASE EMPLOYEE
    """
    events_logged = []
    target_types = {
        EVENT_TASK_SCHEDULED,
        EVENT_EMPLOYEE_RESERVED,
        EVENT_TASK_DISPATCHED,
        EVENT_WORKER_RESERVED,
        EVENT_WORKER_RELEASED,
        EVENT_TASK_COMPLETED,
        EVENT_EMPLOYEE_RELEASED,
    }
    event_bus.subscribe(lambda e: events_logged.append(e.event_type) if e.event_type in target_types else None)

    # 1. CREATE PROJECT
    p = Project(
        project_id="proj_e2e",
        name="End-to-End Enterprise Project",
        status=ProjectStatus.READY,
        priority=ProjectPriority.HIGH,
        budget=100.0,
    )
    sample_orchestrator.project_registry.register_project(p)
    sample_orchestrator.budget_manager.set_project_budget("proj_e2e", 100.0)

    # 2. CREATE TASK
    task = WorkTask(
        task_id="task_e2e_01",
        project_id="proj_e2e",
        title="Develop Backend Auth API",
        description="Implement JWT authentication and RBAC endpoints",
        priority=10,
        required_capabilities=["backend"],
    )
    sample_orchestrator.work_queue.add_task(task)

    # 3. RUNTIME SCHEDULER TICK
    runtime = sample_orchestrator.get_runtime()
    schedule_res = runtime.tick(execute=True)

    # Verify execution outcome
    assert schedule_res.tasks_scheduled == 1
    assert schedule_res.tasks_completed == 1
    assert schedule_res.tasks_failed == 0

    # Verify employee reservation and release
    assert len(sample_orchestrator.resource_manager._reservations) == 0

    # Verify Task Completion
    completed_task = sample_orchestrator.work_queue.get_task("task_e2e_01")
    assert completed_task.status == TASK_COMPLETED
    assert len(completed_task.artifacts) >= 1

    # Verify Artifact Creation
    art_id = completed_task.artifacts[0]
    art = sample_orchestrator.artifact_store.get_artifact(art_id)
    assert art is not None
    assert art.project_id == "proj_e2e"
    assert art.task_id == "task_e2e_01"

    # Verify Usage Record
    usage = sample_orchestrator.usage_tracker.get_project_usage("proj_e2e")
    assert usage["total_tokens"] > 0
    assert usage["total_requests"] >= 1

    # Verify Budget Update
    bgt = sample_orchestrator.budget_manager.get_project_budget("proj_e2e")
    assert bgt["spent"] > 0.0
    assert bgt["remaining"] < 100.0

    # Verify Event Chain
    assert EVENT_TASK_SCHEDULED in events_logged
    assert EVENT_EMPLOYEE_RESERVED in events_logged
    assert EVENT_TASK_DISPATCHED in events_logged
    assert EVENT_WORKER_RESERVED in events_logged
    assert EVENT_WORKER_RELEASED in events_logged
    assert EVENT_TASK_COMPLETED in events_logged
    assert EVENT_EMPLOYEE_RELEASED in events_logged


# =====================================================================
# 12. test_runtime_restart_recovery
# =====================================================================

def test_runtime_restart_recovery(temp_db, test_org):
    """Verify cold-start recovery on new runtime instance:
    Unfinished tasks and stale reservations left from ungraceful crash are healed.
    """
    temp_db.sync_organization_to_db(test_org)
    orch1 = OfficeOrchestrator(db=temp_db, organization=test_org)

    p = Project(project_id="p_crash", name="Crash Recovery Project", status=ProjectStatus.READY)
    orch1.project_registry.register_project(p)
    t = WorkTask(task_id="t_orphaned", project_id="p_crash", title="Orphaned In Flight Task", status=TASK_IN_PROGRESS)
    orch1.work_queue.add_task(t)

    # Reserve an employee in DB simulating a crash
    emp = test_org.employees.list()[0]
    orch1.resource_manager.reserve_employee(
        employee_id=emp.employee_id,
        project_id="p_crash",
        task_id="t_orphaned",
        lease_seconds=0.01,
    )
    time.sleep(0.02)  # Reservation is now stale

    # Simulate crash: discard orch1 without clean stop
    # New cold boot instance starts
    orch2 = OfficeOrchestrator(db=temp_db, organization=test_org)
    runtime2 = orch2.get_runtime()

    # Cold-start recovery in runtime.__init__ should have freed stale reservation
    assert len(orch2.resource_manager._reservations) == 0

    # Running tick should now pick up the recovered task and complete it
    res = runtime2.tick(execute=True)
    assert res.tasks_completed == 1
    assert orch2.work_queue.get_task("t_orphaned").status == TASK_COMPLETED

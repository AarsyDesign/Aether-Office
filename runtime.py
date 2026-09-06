"""Aether Office Phase 7 — Persistent Runtime Engine & Worker Execution Lifecycle.

Provides:
- RuntimeConfig: Centralized configuration parameters.
- TaskWorker: Isolated worker execution boundary returning AgentResult and creating Artifacts.
- OfficeRuntime: Continuous heartbeat loop, lifecycle manager (start/stop/run/tick/status),
  cold-start self-healing, and graceful shutdown signal handling.
"""

from __future__ import annotations
import time
import uuid
import signal
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any, Callable, List, Dict

from events import (
    EventBus,
    Event,
    EVENT_RUNTIME_STARTED,
    EVENT_RUNTIME_STOPPED,
    EVENT_SCHEDULER_TICK_STARTED,
    EVENT_SCHEDULER_TICK_COMPLETED,
    EVENT_TASK_DISPATCHED,
    EVENT_TASK_STARTED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_WORKER_RESERVED,
    EVENT_WORKER_RELEASED,
    EVENT_EMPLOYEE_RESERVED,
    EVENT_EMPLOYEE_RELEASED,
)
from result import AgentResult
from artifacts import Artifact, ArtifactStore, ARTIFACT_DOCUMENT
from tasks import WorkTask, TASK_IN_PROGRESS, TASK_COMPLETED, TASK_FAILED, TASK_READY
from workforce import Employee, STATE_IDLE, STATE_WORKING, AVAILABILITY_AVAILABLE, AVAILABILITY_BUSY
from scheduler import ScheduleResult

logger = logging.getLogger("aether.runtime")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeConfig:
    """Centralized runtime engine configuration."""
    heartbeat_interval: float = 1.0
    reservation_ttl: float = 300.0
    scheduler_lock_ttl: float = 30.0
    max_concurrent_tasks: int = 5
    worker_timeout: float = 60.0
    retry_policy: dict = field(default_factory=lambda: {"max_retries": 3, "backoff": 1.0})
    output_dir: str = "./output"

    def to_dict(self) -> dict:
        return {
            "heartbeat_interval": self.heartbeat_interval,
            "reservation_ttl": self.reservation_ttl,
            "scheduler_lock_ttl": self.scheduler_lock_ttl,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "worker_timeout": self.worker_timeout,
            "retry_policy": dict(self.retry_policy),
            "output_dir": self.output_dir,
        }


class WorkerState(str, Enum):
    IDLE = "IDLE"
    RESERVED = "RESERVED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RELEASED = "RELEASED"


class TaskWorker:
    """Real execution boundary managing the complete worker lifecycle:
    IDLE -> RESERVED -> EXECUTING -> SUCCESS / FAILURE -> RELEASED.
    Contains exceptions and returns standardized AgentResult.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        factory: Optional[Any] = None,
        artifact_store: Optional[ArtifactStore] = None,
        event_bus: Optional[EventBus] = None,
        db: Optional[Any] = None,
        llm: Optional[Any] = None,
        timeout: float = 60.0,
        custom_executor: Optional[Callable[[WorkTask, Employee], Any]] = None,
    ):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.factory = factory
        self.artifact_store = artifact_store
        self.event_bus = event_bus
        self.db = db
        self.llm = llm
        self.timeout = timeout
        self.custom_executor = custom_executor
        self.state = WorkerState.IDLE
        self._current_task_id: Optional[str] = None
        self._current_employee_id: Optional[str] = None

    def execute(
        self,
        task: WorkTask,
        employee: Employee,
        output_dir: Optional[str] = None,
        custom_executor: Optional[Callable[[WorkTask, Employee], Any]] = None,
    ) -> AgentResult:
        """Alias for execute_task."""
        return self.execute_task(
            task=task,
            employee=employee,
            output_dir=output_dir,
            custom_executor=custom_executor,
        )

    def execute_task(
        self,
        task: WorkTask,
        employee: Employee,
        output_dir: Optional[str] = None,
        custom_executor: Optional[Callable[[WorkTask, Employee], Any]] = None,
    ) -> AgentResult:
        """Execute task through employee with failure boundary and produce AgentResult & Artifact."""
        self.state = WorkerState.RESERVED
        self._current_task_id = task.task_id
        self._current_employee_id = employee.employee_id

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_WORKER_RESERVED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    agent_id=employee.employee_id,
                    payload={"worker_id": self.worker_id, "employee_id": employee.employee_id},
                )
            )

        self.state = WorkerState.EXECUTING
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_TASK_STARTED,
                    project_id=task.project_id,
                    task_id=task.task_id,
                    agent_id=employee.employee_id,
                    payload={"worker_id": self.worker_id, "task_title": task.title},
                )
            )

        start_time = time.perf_counter()
        agent_res: Optional[AgentResult] = None

        exec_fn = custom_executor or self.custom_executor
        try:
            if exec_fn:
                raw_res = exec_fn(task, employee)
                if isinstance(raw_res, AgentResult):
                    agent_res = raw_res
                elif isinstance(raw_res, dict):
                    agent_res = AgentResult(
                        success=raw_res.get("success", True),
                        output=raw_res.get("output", raw_res.get("result", "Execution success")),
                        files=raw_res.get("files", []),
                        error=raw_res.get("error"),
                        usage=raw_res.get("usage", {"input_tokens": 400, "output_tokens": 200}),
                    )
                else:
                    agent_res = AgentResult(
                        success=True,
                        output=str(raw_res),
                        usage={"input_tokens": 400, "output_tokens": 200},
                    )
            elif self.factory:
                # Instantiate real agent via AgentFactory
                agent = self.factory.create_agent(
                    employee=employee,
                    llm=self.llm,
                    db=self.db,
                    project_id=task.project_id,
                    output_dir=output_dir or "./output",
                    event_bus=self.event_bus,
                )
                instruction = f"Task: {task.title}\nDescription: {task.description}"
                agent_res = agent.run(instruction, task=task.to_dict())
            else:
                # Deterministic fallback execution
                agent_res = AgentResult(
                    success=True,
                    output=f"Executed by {employee.name} ({employee.role})",
                    usage={"input_tokens": 350, "output_tokens": 150},
                )

            # Ensure usage is a dictionary
            if not agent_res.usage:
                agent_res.usage = {"input_tokens": 300, "output_tokens": 150}

            if agent_res.success:
                self.state = WorkerState.SUCCESS
                # Register deliverable artifact
                if self.artifact_store:
                    art_id = f"art_{task.task_id}_{uuid.uuid4().hex[:6]}"
                    art_content = str(agent_res.output or f"Deliverable for {task.title}")
                    artifact = Artifact(
                        artifact_id=art_id,
                        task_id=task.task_id,
                        project_id=task.project_id,
                        type=ARTIFACT_DOCUMENT,
                        name=f"Deliverable: {task.title}",
                        content=art_content,
                        created_by=employee.employee_id,
                        metadata={
                            "worker_id": self.worker_id,
                            "task_id": task.task_id,
                            "project_id": task.project_id,
                            "employee_id": employee.employee_id,
                            "execution_duration_ms": round((time.perf_counter() - start_time) * 1000, 2),
                            "timestamp": _now_iso(),
                        },
                    )
                    self.artifact_store.register_artifact(artifact)
                    task.add_artifact(art_id)
                    task.result = {"output": art_content, "artifact_id": art_id}
            else:
                self.state = WorkerState.FAILURE

            return agent_res

        except Exception as ex:
            self.state = WorkerState.FAILURE
            logger.error(f"TaskWorker {self.worker_id} failure on task {task.task_id}: {ex}")
            return AgentResult(
                success=False,
                output=None,
                error=str(ex),
                usage={"input_tokens": 0, "output_tokens": 0},
            )
        finally:
            self.state = WorkerState.RELEASED
            self._current_task_id = None
            self._current_employee_id = None
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_WORKER_RELEASED,
                        project_id=task.project_id,
                        task_id=task.task_id,
                        agent_id=employee.employee_id,
                        payload={"worker_id": self.worker_id, "employee_id": employee.employee_id},
                    )
                )


class OfficeRuntime:
    """Master persistent runtime controller responsible for the operational lifecycle:
    - start() / stop() / run() / tick() / status()
    - Scheduler heartbeat loop at configurable intervals
    - Graceful shutdown signal handling (SIGINT, SIGTERM)
    - Cold-start recovery from prior ungraceful exits
    """

    def __init__(
        self,
        orchestrator: Any,
        config: Optional[RuntimeConfig] = None,
        event_bus: Optional[EventBus] = None,
        enable_pixel_bridge: bool = False,
        pixel_bridge: Optional[Any] = None,
    ):
        self.orchestrator = orchestrator
        self.config = config or RuntimeConfig()
        self.event_bus = event_bus or getattr(orchestrator, "event_bus", None)

        self._stop_requested = False
        self._is_running = False
        self._ticks_count = 0
        self._start_time: Optional[float] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stopped_event_emitted = False

        # Connect Worker to Scheduler if available
        if hasattr(self.orchestrator, "worker") and hasattr(self.orchestrator, "scheduler"):
            self.orchestrator.scheduler.worker = self.orchestrator.worker

        # Cold-start self healing: recover any interrupted tasks or reservations immediately
        if hasattr(self.orchestrator, "recover_from_crash"):
            self.orchestrator.recover_from_crash(timeout_seconds=0.0)

        # Pixel Agents Visual Simulator Bridge
        self.pixel_bridge = pixel_bridge
        if enable_pixel_bridge and self.pixel_bridge is None:
            try:
                from pixel_bridge import PixelAgentsBridge
                self.pixel_bridge = PixelAgentsBridge()
            except Exception as e:
                logger.warning(f"Could not initialize PixelAgentsBridge: {e}")

        if self.pixel_bridge and self.event_bus:
            self.pixel_bridge.attach_to_event_bus(self.event_bus)

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def ticks_count(self) -> int:
        return self._ticks_count

    def _emit_stopped_event(self) -> None:
        """Publishes EVENT_RUNTIME_STOPPED idempotently."""
        if self.event_bus and not self._stopped_event_emitted:
            self._stopped_event_emitted = True
            self.event_bus.publish(
                Event(
                    event_type=EVENT_RUNTIME_STOPPED,
                    project_id="office",
                    payload={"total_ticks": self._ticks_count},
                )
            )

    def start(self, in_background: bool = True, max_ticks: Optional[int] = None) -> None:
        """Start the persistent runtime. If in_background=True, runs in a background thread."""
        with self._lock:
            if self._is_running:
                logger.warning("OfficeRuntime is already running.")
                return

            self._stop_requested = False
            self._is_running = True
            self._stopped_event_emitted = False
            self._start_time = time.time()

            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        event_type=EVENT_RUNTIME_STARTED,
                        project_id="office",
                        payload={"config": self.config.to_dict()},
                    )
                )

            if in_background:
                self._thread = threading.Thread(
                    target=self.run,
                    kwargs={"max_ticks": max_ticks},
                    daemon=True,
                    name="AetherOfficeRuntimeHeartbeat",
                )
                self._thread.start()
            else:
                self.run(max_ticks=max_ticks)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal graceful shutdown, wait for current tick to finish, and release resources."""
        with self._lock:
            if not self._is_running and not self._stop_requested:
                return
            self._stop_requested = True

        logger.info("Graceful shutdown requested for OfficeRuntime.")

        if self._thread and self._thread.is_alive() and self._thread != threading.current_thread():
            self._thread.join(timeout=timeout)

        with self._lock:
            self._is_running = False
            self._thread = None

        # Clean release of scheduler lock if held
        if hasattr(self.orchestrator, "db") and self.orchestrator.db:
            try:
                self.orchestrator.db.release_scheduler_lock(lock_name="office_scheduler")
            except Exception:
                pass

        if getattr(self, "pixel_bridge", None):
            try:
                self.pixel_bridge.close()
            except Exception:
                pass

        self._emit_stopped_event()
        logger.info("OfficeRuntime successfully stopped cleanly.")

    def run(self, max_ticks: Optional[int] = None) -> None:
        """Continuous heartbeat execution loop."""
        self._is_running = True
        try:
            while not self._stop_requested:
                if max_ticks is not None and self._ticks_count >= max_ticks:
                    break

                self.tick(execute=True)

                # Responsive sleeping: check _stop_requested in small intervals
                elapsed = 0.0
                sleep_slice = min(0.05, self.config.heartbeat_interval)
                while elapsed < self.config.heartbeat_interval and not self._stop_requested:
                    time.sleep(sleep_slice)
                    elapsed += sleep_slice
        finally:
            with self._lock:
                self._is_running = False
            self._emit_stopped_event()

    def tick(
        self,
        execute: bool = True,
        custom_executor: Optional[Callable[[WorkTask, Employee], Any]] = None,
    ) -> ScheduleResult:
        """Executes one single scheduler heartbeat cycle."""
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_SCHEDULER_TICK_STARTED,
                    project_id="office",
                    payload={"tick_number": self._ticks_count + 1},
                )
            )

        res = self.orchestrator.scheduler_tick(
            execute=execute,
            output_dir=self.config.output_dir,
            custom_executor=custom_executor,
        )

        with self._lock:
            self._ticks_count += 1

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    event_type=EVENT_SCHEDULER_TICK_COMPLETED,
                    project_id="office",
                    payload={
                        "tick_number": self._ticks_count,
                        "tasks_evaluated": res.tasks_evaluated,
                        "tasks_scheduled": res.tasks_scheduled,
                        "tasks_completed": res.tasks_completed,
                        "tasks_failed": res.tasks_failed,
                        "conflicts_detected": res.conflicts_detected,
                    },
                )
            )

        return res

    def status(self) -> dict:
        """Provides real-time operational metrics of the runtime engine."""
        uptime = round(time.time() - self._start_time, 2) if (self._is_running and self._start_time) else 0.0
        state = self.orchestrator.office_status() if hasattr(self.orchestrator, "office_status") else None

        return {
            "is_running": self._is_running,
            "ticks_count": self._ticks_count,
            "uptime_seconds": uptime,
            "heartbeat_interval": self.config.heartbeat_interval,
            "config": self.config.to_dict(),
            "office_state": state.to_dict() if state else {},
        }

    def install_signal_handlers(self) -> None:
        """Installs SIGINT and SIGTERM handlers for graceful shutdown when run as main process."""
        def _handler(sig, frame):
            logger.info(f"Signal {sig} received. Initiating graceful shutdown...")
            self.stop()

        try:
            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, AttributeError):
            # Not in main thread or platform does not support SIGTERM
            pass

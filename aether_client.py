"""Aether Office Client SDK & Telemetry Monitor.

Use this client in Hermes Agent, Antigravity IDE, VS Code extensions, or background scripts
to stream live agent activity directly to the Aether Office visual dashboard.

Example Usage in Hermes Agent or Python scripts:
    from aether_client import AetherMonitor

    monitor = AetherMonitor("http://127.0.0.1:8000")

    # Method 1: Using context manager (auto-starts and auto-completes)
    with monitor.track(role="developer", task="Refactoring Supabase Auth", source="hermes"):
        # Real work here
        time.sleep(2)

    # Method 2: Manual notification
    monitor.notify(role="qa", task="Running test suite", status="WORKING", source="antigravity")
    monitor.notify(role="qa", task="Running test suite", status="COMPLETED", source="antigravity", details="15 tests passed")
"""

from __future__ import annotations
import json
import time
import logging
import urllib.request
import urllib.error
from contextlib import contextmanager
from typing import Optional, Dict, Any, Generator

logger = logging.getLogger("aether.client")


class AetherMonitor:
    """Client for broadcasting real AI work to Aether Office visual mission control."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", default_source: str = "hermes"):
        self.base_url = base_url.rstrip("/")
        self.default_source = default_source

    def notify(
        self,
        role: str,
        task: str,
        status: str = "WORKING",
        source: Optional[str] = None,
        details: str = "",
        project: str = "Aplikasi Kasir Pondok",
        employee_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        """Broadcast an activity update to Aether Office."""
        payload = {
            "source": source or self.default_source,
            "role": role,
            "task_title": task,
            "status": status,
            "details": details,
            "project": project,
            "employee_id": employee_id,
            "metadata": metadata or {},
        }
        url = f"{self.base_url}/api/telemetry/activity"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "AetherClient/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"Aether Office telemetry notify skipped ({e})")
            return None

    def start_activity(
        self,
        role: str,
        task: str,
        source: Optional[str] = None,
        details: str = "",
        project: str = "Aplikasi Kasir Pondok",
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        return self.notify(
            role=role,
            task=task,
            status="WORKING",
            source=source,
            details=details,
            project=project,
            metadata=metadata,
        )

    def complete_activity(
        self,
        role: str,
        task: str,
        source: Optional[str] = None,
        details: str = "",
        project: str = "Aplikasi Kasir Pondok",
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        return self.notify(
            role=role,
            task=task,
            status="COMPLETED",
            source=source,
            details=details,
            project=project,
            metadata=metadata,
        )

    def fail_activity(
        self,
        role: str,
        task: str,
        error: str = "",
        source: Optional[str] = None,
        project: str = "Aplikasi Kasir Pondok",
    ) -> Optional[dict]:
        return self.notify(
            role=role,
            task=task,
            status="FAILED",
            source=source,
            details=error,
            project=project,
        )

    @contextmanager
    def track(
        self,
        role: str,
        task: str,
        source: Optional[str] = None,
        details: str = "",
        project: str = "Aplikasi Kasir Pondok",
    ) -> Generator[None, None, None]:
        """Context manager that emits WORKING on entry and COMPLETED/FAILED on exit."""
        t0 = time.perf_counter()
        src = source or self.default_source
        self.start_activity(role=role, task=task, source=src, details=details, project=project)
        try:
            yield
            duration = round(time.perf_counter() - t0, 2)
            self.complete_activity(
                role=role,
                task=task,
                source=src,
                details=details or f"Finished in {duration}s",
                project=project,
                metadata={"duration_seconds": duration},
            )
        except Exception as err:
            self.fail_activity(role=role, task=task, error=str(err), source=src, project=project)
            raise

"""Pixel Agents Integration Bridge for Aether Office.

Connects Aether Office EventBus and Runtime with Pixel Agents (Fastify HTTP server)
so virtual employees (47+ specialized Indonesian agents) come to life in the 2D
pixel-art virtual office simulator.
"""

from __future__ import annotations
import os
import sys
import json
import time
import glob
import queue
import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("aether.pixel_bridge")

# Role to Pixel Agents tool mapping
ROLE_TOOL_MAPPING: Dict[str, Tuple[str, str]] = {
    # Engineering / Development -> Edit / Write / Bash
    "developer": ("Edit", "Writing and refactoring Python modules"),
    "backend_developer": ("Edit", "Implementing API endpoints & database logic"),
    "frontend_developer": ("Edit", "Building UI components & layouts"),
    "fullstack_developer": ("Edit", "Developing full-stack features"),
    "mobile_developer": ("Edit", "Building mobile app views"),
    "devops_engineer": ("Bash", "Managing deployment & container configs"),
    "security_engineer": ("Bash", "Auditing security vulnerabilities"),
    "data_engineer": ("Edit", "Constructing ETL pipelines"),
    # QA / Testing -> Bash / Read
    "qa": ("Bash", "Executing automated test suite"),
    "qa_engineer": ("Bash", "Running test runner and bug diagnostics"),
    # Product / Architecture -> EnterPlanMode / Write
    "pm": ("EnterPlanMode", "Analyzing requirements & task breakdown"),
    "conceptor": ("EnterPlanMode", "Formulating technical design & test specs"),
    "planner": ("EnterPlanMode", "Constructing dependency graphs & milestone gates"),
    "software_architect": ("EnterPlanMode", "Architecting system blueprint & topologies"),
    "business_analyst": ("EnterPlanMode", "Analyzing workflows & business metrics"),
    "product_researcher": ("WebSearch", "Researching market benchmarks"),
    # Design -> Edit
    "ui_designer": ("Edit", "Designing layout & color schemes"),
    "ux_designer": ("Edit", "Structuring user flows & wireframes"),
    "graphic_designer": ("Edit", "Creating visual assets & illustrations"),
    "brand_designer": ("Edit", "Polishing brand typography & guidelines"),
    "motion_designer": ("Edit", "Designing animation curves"),
    # Research -> WebSearch / Read
    "researcher": ("WebSearch", "Conducting deep technical research"),
    "data_analyst": ("Read", "Analyzing data distributions & insights"),
    "market_researcher": ("WebSearch", "Monitoring market trends"),
    "competitive_analyst": ("Read", "Benchmarking competitive feature matrix"),
    # Operations & Business -> Write
    "operations_manager": ("Write", "Optimizing operational throughput"),
    "project_coordinator": ("Write", "Coordinating inter-departmental handoffs"),
    "documentation_specialist": ("Write", "Writing project documentation & manuals"),
    "sales": ("Write", "Drafting sales proposals"),
    "account_manager": ("Write", "Communicating with client accounts"),
    "finance": ("Write", "Estimating project budget & costs"),
    "business_development": ("Write", "Outlining strategic partnerships"),
    "support_specialist": ("Write", "Responding to support inquiries"),
    "community_manager": ("Write", "Engaging community feedback"),
    "customer_support": ("Write", "Resolving customer tickets"),
}


def discover_pixel_agents_server() -> Optional[Dict[str, Any]]:
    """Auto-discover active Pixel Agents servers from ~/.pixel-agents/."""
    home = Path.home()
    servers_dir = home / ".pixel-agents" / "servers"
    
    # 1. Search servers/*.json
    if servers_dir.exists() and servers_dir.is_dir():
        json_files = sorted(servers_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
        for jf in json_files:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                port = data.get("port")
                token = data.get("token")
                if port and token:
                    # Verify health
                    if _check_server_health("127.0.0.1", port):
                        return {
                            "host": "127.0.0.1",
                            "port": port,
                            "token": token,
                            "pid": data.get("pid"),
                        }
            except Exception as e:
                logger.debug(f"Could not parse server file {jf}: {e}")

    # 2. Check legacy ~/.pixel-agents/server.json
    legacy_file = home / ".pixel-agents" / "server.json"
    if legacy_file.exists():
        try:
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
            port = data.get("port")
            token = data.get("token")
            if port and token and _check_server_health("127.0.0.1", port):
                return {
                    "host": "127.0.0.1",
                    "port": port,
                    "token": token,
                    "pid": data.get("pid"),
                }
        except Exception as e:
            logger.debug(f"Could not parse legacy server.json: {e}")

    return None


def _check_server_health(host: str, port: int, timeout: float = 1.0) -> bool:
    """Verify that the Pixel Agents HTTP server responds to /api/health."""
    url = f"http://{host}:{port}/api/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


class PixelAgentsBridge:
    """Non-blocking, resilient bridge between Aether Office and Pixel Agents."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
        provider: str = "claude",
        auto_discover: bool = True,
        cwd: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.token = token
        self.provider = provider
        self.auto_discover = auto_discover
        self.cwd = cwd or str(Path(__file__).parent.resolve())

        self._active_sessions: set[str] = set()
        self._session_tools: dict[str, str] = {}
        self._session_lock = threading.RLock()

        # Non-blocking async dispatch queue
        self._queue: queue.Queue[Optional[dict]] = queue.Queue(maxsize=1000)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._dispatch_worker,
            daemon=True,
            name="PixelAgentsBridgeWorker",
        )
        self._worker_thread.start()

        if self.auto_discover and (not self.port or not self.token):
            self.refresh_discovery()

    def refresh_discovery(self) -> bool:
        """Attempt to discover or re-discover active Pixel Agents server."""
        info = discover_pixel_agents_server()
        if info:
            self.host = self.host or info["host"]
            self.port = info["port"]
            self.token = info["token"]
            logger.info(f"PixelAgentsBridge discovered server at {self.host}:{self.port}")
            return True
        return False

    @property
    def is_connected(self) -> bool:
        if not self.host or not self.port or not self.token:
            return False
        return _check_server_health(self.host, self.port)

    # ── Non-blocking Dispatcher ──────────────────────────────────────

    def _dispatch_worker(self) -> None:
        """Background thread worker to deliver events via HTTP POST."""
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if item is None:
                self._queue.task_done()
                break

            try:
                self._send_http_request(item)
            except Exception as e:
                logger.debug(f"Error sending request: {e}")
            finally:
                self._queue.task_done()

    def _send_http_request(self, payload: dict) -> bool:
        if not self.host or not self.port or not self.token:
            if self.auto_discover:
                self.refresh_discovery()
            if not self.port or not self.token:
                return False

        url = f"http://{self.host}:{self.port}/api/hooks/{self.provider}"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            logger.debug(f"HTTP {e.code} posting hook event to Pixel Agents: {e.reason}")
            return False
        except Exception as e:
            logger.debug(f"Failed to post hook event to Pixel Agents: {e}")
            return False

    def emit_event_async(self, payload: dict) -> None:
        """Enqueue event for non-blocking asynchronous transmission."""
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            logger.warning("PixelAgentsBridge queue full; dropping event to protect runtime performance.")

    # ── Protocol Actions ─────────────────────────────────────────────

    def session_start(self, session_id: str, cwd: Optional[str] = None) -> None:
        """Stage an agent in the pixel office."""
        with self._session_lock:
            self._active_sessions.add(session_id)

        self.emit_event_async({
            "session_id": session_id,
            "hook_event_name": "SessionStart",
            "source": "startup",
            "cwd": (cwd or self.cwd).replace("\\", "/"),
        })

    def pre_tool_use(
        self,
        session_id: str,
        tool_name: str,
        tool_input: Optional[dict] = None,
        cwd: Optional[str] = None,
    ) -> None:
        """Make an agent walk to their desk and begin working/typing."""
        with self._session_lock:
            if session_id not in self._active_sessions:
                self.session_start(session_id, cwd=cwd)
            self._session_tools[session_id] = tool_name

        self.emit_event_async({
            "session_id": session_id,
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        })

    def post_tool_use(self, session_id: str) -> None:
        """Mark tool activity finished."""
        with self._session_lock:
            self._session_tools.pop(session_id, None)

        self.emit_event_async({
            "session_id": session_id,
            "hook_event_name": "PostToolUse",
        })

    def turn_stop(self, session_id: str) -> None:
        """Mark agent turn completed (agent returns to idle state at desk)."""
        self.emit_event_async({
            "session_id": session_id,
            "hook_event_name": "Stop",
        })

    def tool_failure(self, session_id: str, error_message: str = "") -> None:
        """Report tool failure."""
        with self._session_lock:
            self._session_tools.pop(session_id, None)

        self.emit_event_async({
            "session_id": session_id,
            "hook_event_name": "PostToolUseFailure",
            "error": error_message,
        })
        self.turn_stop(session_id)

    def notify_waiting(self, session_id: str, reason: str = "idle_prompt") -> None:
        """Show idle or permission speech bubble above the agent."""
        self.emit_event_async({
            "session_id": session_id,
            "hook_event_name": "Notification",
            "notification_type": reason,
        })

    def session_end(self, session_id: str, reason: str = "exit") -> None:
        """Despawn an agent from the pixel office."""
        with self._session_lock:
            self._active_sessions.discard(session_id)
            self._session_tools.pop(session_id, None)

        self.emit_event_async({
            "session_id": session_id,
            "hook_event_name": "SessionEnd",
            "reason": reason,
        })

    # ── EventBus Integration ─────────────────────────────────────────

    def attach_to_event_bus(self, event_bus: Any) -> None:
        """Subscribe to Aether Office EventBus."""
        if hasattr(event_bus, "subscribe"):
            event_bus.subscribe(self.handle_event)
            logger.info("PixelAgentsBridge successfully subscribed to EventBus.")

    def detach_from_event_bus(self, event_bus: Any) -> None:
        """Unsubscribe from Aether Office EventBus."""
        if hasattr(event_bus, "unsubscribe"):
            event_bus.unsubscribe(self.handle_event)
            logger.info("PixelAgentsBridge unsubscribed from EventBus.")

    def handle_event(self, event: Any) -> None:
        """Translate Aether Office events into Pixel Agents visual actions."""
        try:
            etype = getattr(event, "event_type", "")
            agent_id = getattr(event, "agent_id", None)
            role = getattr(event, "agent_role", None) or ""
            task_id = getattr(event, "task_id", None)
            payload = getattr(event, "payload", {}) or {}

            # Determine session identifier (prefer agent_id, fallback to task_id)
            session_id = agent_id or (f"task_{task_id}" if task_id is not None else "office_agent")

            if etype in ("employee_reserved", "task_dispatched"):
                # Employee reserved or task queued
                self.session_start(session_id)

            elif etype in ("task_started", "agent_started", "developer_unit_started", "qa_test_started"):
                tool_name, default_desc = ROLE_TOOL_MAPPING.get(role, ("Edit", "Processing task"))
                task_title = payload.get("title") or payload.get("description") or default_desc
                
                tool_input: dict[str, Any] = {}
                if tool_name in ("Edit", "Write", "Read"):
                    tool_input["file_path"] = f"{task_title[:40]}.py"
                elif tool_name == "Bash":
                    tool_input["command"] = f"pytest {task_title[:40]}"
                else:
                    tool_input["description"] = task_title[:60]

                self.pre_tool_use(session_id, tool_name=tool_name, tool_input=tool_input)

            elif etype in ("task_completed", "agent_completed", "developer_unit_completed", "qa_completed"):
                self.post_tool_use(session_id)
                self.turn_stop(session_id)

            elif etype in ("task_failed", "agent_failed", "developer_unit_failed", "qa_test_failed"):
                err_msg = payload.get("error", "Task failed")
                self.tool_failure(session_id, error_message=str(err_msg))

            elif etype in ("clarification_required", "review_requested", "agent_waiting"):
                self.notify_waiting(session_id, reason="idle_prompt")

            elif etype in ("runtime_stopped", "employee_deactivated"):
                if agent_id:
                    self.session_end(agent_id)
                else:
                    with self._session_lock:
                        sessions = list(self._active_sessions)
                    for sid in sessions:
                        self.session_end(sid)

        except Exception as e:
            logger.debug(f"Error handling EventBus event in PixelAgentsBridge: {e}")

    def close(self) -> None:
        """Shut down the background dispatcher thread."""
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        if self._worker_thread.is_alive() and threading.current_thread() != self._worker_thread:
            self._worker_thread.join(timeout=1.0)


# ── Interactive CLI & Live Demonstration ─────────────────────────────

def run_demo():
    """Run an interactive simulation demonstrating 3 Indonesian agents in Pixel Agents."""
    print("============================================================")
    print("  Aether Office -> Pixel Agents Live Office Demo")
    print("============================================================")

    bridge = PixelAgentsBridge(auto_discover=True)
    if not bridge.is_connected:
        print("[!] Pixel Agents server is not running on 127.0.0.1:3100.")
        print("[i] Starting server instruction: run `npx pixel-agents --port 3100`")
        return

    print(f"[+] Connected to Pixel Agents server on {bridge.host}:{bridge.port}")
    print("[*] Simulating office workflow for 3 Indonesian Specialists:\n")

    agents = [
        ("budi_pm", "Budi Santoso (Product Manager)", "EnterPlanMode", {"description": "Analyzing groceries cashier spec"}),
        ("eko_dev", "Eko Prasetyo (Fullstack Dev)", "Edit", {"file_path": "cashier_ui.py"}),
        ("ratna_qa", "Ratna Sari (QA Engineer)", "Bash", {"command": "pytest tests/test_cashier.py"}),
    ]

    for session_id, name, tool, tool_input in agents:
        print(f"  -> {name} enters office and starts working ({tool})...")
        bridge.session_start(session_id)
        time.sleep(0.3)
        bridge.pre_tool_use(session_id, tool_name=tool, tool_input=tool_input)
        time.sleep(0.5)

    print("\n[+] All 3 agents are now active at their desks in the pixel office!")
    print("    Check your browser at http://127.0.0.1:3100 to view them walking and typing.\n")
    print("[*] Letting them work for 5 seconds...")
    time.sleep(5)

    print("\n[*] Completing tasks:")
    for session_id, name, _, _ in agents:
        print(f"  <- {name} finished turn.")
        bridge.post_tool_use(session_id)
        bridge.turn_stop(session_id)
        time.sleep(0.4)

    print("\n[OK] Demonstration complete! Characters are now idle at their desks.")
    bridge.close()


if __name__ == "__main__":
    if "--demo" in sys.argv or len(sys.argv) == 1:
        run_demo()
    elif "--test" in sys.argv:
        info = discover_pixel_agents_server()
        if info:
            print(f"[OK] Discovered Pixel Agents server: {info}")
        else:
            print("[FAIL] Could not discover active Pixel Agents server.")

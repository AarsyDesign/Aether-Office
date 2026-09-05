"""Aether Office - Game Dashboard Server (FastAPI + SSE).

Provides a tycoon/simulation game-style visual dashboard for Aether Office.
Decoupled observer pattern: reads office state, streams live events, and provides
game controls (manual tick, auto-tick, new quest/objective creation).
"""

from __future__ import annotations

import os
import sys
import json
import time
import asyncio
import logging
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any, List

# Check if fastapi & uvicorn are installed
try:
    from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
    from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    HAS_UI_DEPS = True
except ImportError:
    HAS_UI_DEPS = False

from orchestrator import load_config
from db import Database
from workforce import create_default_organization, Organization
from office import OfficeOrchestrator
from objective_orchestrator import ObjectiveOrchestrator
from adaptive_planner import AdaptiveObjectivePlanner
from events import EventBus, Event, EVENT_OFFICE_STATE_CHANGED

logger = logging.getLogger("aether.dashboard")

# UI static assets path
UI_DIR = Path(__file__).parent / "ui"


class OfficeDashboardHub:
    """Manages the backend state and event subscribers for the web dashboard."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = load_config(config_path)
        db_path = self.config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
        
        self.event_bus = EventBus()
        self.db = Database(db_path, event_bus=self.event_bus)
        
        self.organization, _ = create_default_organization()
        self.db.sync_organization_to_db(self.organization)
        
        self.office = OfficeOrchestrator(
            db=self.db,
            organization=self.organization,
            event_bus=self.event_bus,
        )
        
        self.planner = AdaptiveObjectivePlanner(
            organization=self.organization,
            event_bus=self.event_bus,
        )
        
        self.obj_orch = ObjectiveOrchestrator(
            office_orchestrator=self.office,
            planner=self.planner,
            db=self.db,
            event_bus=self.event_bus,
            use_adaptive=True,
        )

        # Real AI Telemetry Bridge (Hermes Agent, Antigravity IDE, VS Code, Cron)
        from telemetry import TelemetryManager
        from cron_engine import CronEngine

        self.telemetry = TelemetryManager(db=self.db, event_bus=self.event_bus)
        workspace_root = str(Path(__file__).parent.parent)
        self.cron = CronEngine(
            telemetry_manager=self.telemetry,
            workspace_dir=workspace_root,
            db_path=db_path,
        )
        self.cron.start()
        
        # SSE active client queues
        self._sse_queues: List[asyncio.Queue] = []
        self.event_bus.subscribe(self._on_event)

        # Track tick count in session
        self.tick_count = 0

    def _on_event(self, event: Event) -> None:
        """Forward internal EventBus events to connected SSE web clients."""
        payload_data = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "project_id": event.project_id,
            "agent_role": event.agent_role,
            "agent_id": event.agent_id,
            "timestamp": event.timestamp,
            "payload": event.payload,
        }
        for q in list(self._sse_queues):
            try:
                q.put_nowait(payload_data)
            except Exception:
                pass

    def add_sse_listener(self, queue: asyncio.Queue) -> None:
        self._sse_queues.append(queue)

    def remove_sse_listener(self, queue: asyncio.Queue) -> None:
        if queue in self._sse_queues:
            self._sse_queues.remove(queue)

    def get_full_state(self) -> Dict[str, Any]:
        """Produce a comprehensive game state snapshot."""
        # 1. Office operational stats
        office_state = self.office.office_status()
        state_dict = office_state.to_dict()

        # 2. Departments and Employees
        departments = self.db.get_departments()
        employees = self.db.get_employees()

        # Group employees by department
        dept_map: Dict[str, List[Dict[str, Any]]] = {d["id"]: [] for d in departments}
        for emp in employees:
            dept_id = emp.get("department_id", "engineering")
            if dept_id not in dept_map:
                dept_map[dept_id] = []
            
            # Enrich employee with RPG game stats
            e_id = emp["id"]
            # Level based on ID or completed tasks
            caps = emp.get("capabilities", [])
            level = max(1, min(10, 1 + len(caps) // 2))
            
            # Active task if busy (Internal work task or External Telemetry / Cron)
            assigned_task = None
            tel_activity = self.telemetry.get_active_activity(e_id) if hasattr(self, "telemetry") else None
            if tel_activity and tel_activity.status == "WORKING":
                assigned_task = {
                    "task_id": tel_activity.activity_id,
                    "title": f"[{tel_activity.source.upper()}] {tel_activity.task_title}",
                    "status": "IN_PROGRESS",
                    "priority": 10,
                    "source": tel_activity.source,
                    "details": tel_activity.details,
                }
                emp["availability"] = "busy"
                emp["live_state"] = "WORKING"
            elif emp.get("availability") == "busy" or emp.get("live_state") == "WORKING":
                # Find current internal work task
                tasks = self.db.list_work_tasks(status="IN_PROGRESS")
                for t in tasks:
                    if t.get("assigned_employee_id") == e_id:
                        assigned_task = {
                            "task_id": t["task_id"],
                            "title": t["title"],
                            "status": t["status"],
                            "priority": t.get("priority", 0),
                            "source": "office",
                        }
                        break

            # RPG Character class mapping
            role_id = emp.get("role_id", "")
            rpg_class = role_id.replace("_", " ").title()

            dept_map[dept_id].append({
                "id": emp["id"],
                "name": emp["name"],
                "role_id": emp["role_id"],
                "rpg_class": rpg_class,
                "department_id": dept_id,
                "status": emp.get("status", "active"),
                "availability": emp.get("availability", "available"),
                "live_state": emp.get("live_state", "IDLE"),
                "level": level,
                "capabilities": caps,
                "personality": emp.get("personality", {}),
                "current_task": assigned_task,
            })

        # Build rooms data
        rooms = []
        room_visual_configs = {
            "business": {"icon": "👑", "theme": "#d97706", "label": "Business & Executive Suite", "col": 0, "row": 0},
            "product": {"icon": "💡", "theme": "#8b5cf6", "label": "Product & Strategy Lab", "col": 1, "row": 0},
            "research": {"icon": "🔬", "theme": "#0284c7", "label": "Research & Feasibility Lab", "col": 2, "row": 0},
            "engineering": {"icon": "⚡", "theme": "#2563eb", "label": "Engineering & Development Floor", "col": 3, "row": 0},
            "design": {"icon": "🎨", "theme": "#ec4899", "label": "Design & UI/UX Studio", "col": 0, "row": 1},
            "marketing": {"icon": "📈", "theme": "#10b981", "label": "Marketing & Growth War Room", "col": 1, "row": 1},
            "operations": {"icon": "📋", "theme": "#6366f1", "label": "Operations & Coordination Deck", "col": 2, "row": 1},
            "support": {"icon": "☕", "theme": "#059669", "label": "Support & Community Lounge", "col": 3, "row": 1},
        }

        for d in departments:
            d_id = d["id"]
            cfg = room_visual_configs.get(d_id, {
                "icon": "🏢", "theme": "#64748b", "label": d["name"], "col": 0, "row": 0
            })
            rooms.append({
                "id": d_id,
                "name": d["name"],
                "label": cfg["label"],
                "icon": cfg["icon"],
                "theme": cfg["theme"],
                "description": d.get("description", ""),
                "grid": {"col": cfg["col"], "row": cfg["row"]},
                "employees": dept_map.get(d_id, []),
            })

        # 3. Objectives / Quests
        all_objs = self.obj_orch.list_objectives()
        objectives_data = []
        for obj in all_objs:
            # Try to get adaptive plan milestones via orchestrator plan cache or DB
            milestones = []
            try:
                # First, look up the plan by execution_plan_id stored on the objective
                plan = None
                plan_id = getattr(obj, "execution_plan_id", None)
                if plan_id:
                    plan = self.obj_orch._plans.get(plan_id)
                if plan is None and self.obj_orch.db:
                    # Fallback: load from DB
                    from planner import ExecutionPlan
                    d = self.obj_orch.db.get_execution_plan_by_objective(obj.id)
                    if d:
                        plan = ExecutionPlan.from_dict(d)
                        self.obj_orch._plans[plan.id] = plan

                if plan and hasattr(plan, "milestones"):
                    proj_id = getattr(obj, "project_id", None) or f"proj_{obj.id}"
                    proj_tasks = {t["task_id"]: t["status"] for t in self.db.list_work_tasks(project_id=proj_id)} if self.db else {}
                    is_obj_completed = (obj.status.value if hasattr(obj.status, "value") else str(obj.status)) == "COMPLETED"

                    for m in plan.milestones:
                        m_id = getattr(m, "id", None) or getattr(m, "milestone_id", None)
                        m_title = getattr(m, "title", None) or getattr(m, "name", str(m_id))
                        m_task_ids = getattr(m, "task_ids", []) or getattr(m, "tasks", [])

                        if is_obj_completed:
                            m_status = "COMPLETED"
                        elif m_task_ids and all(proj_tasks.get(tid) == "COMPLETED" for tid in m_task_ids):
                            m_status = "COMPLETED"
                        elif m_task_ids and any(proj_tasks.get(tid) in ("IN_PROGRESS", "COMPLETED", "ASSIGNED") for tid in m_task_ids):
                            m_status = "IN_PROGRESS"
                        else:
                            m_status = "PENDING"

                        milestones.append({
                            "id": m_id,
                            "title": m_title,
                            "required_roles": getattr(m, "required_roles", []),
                            "dependencies": getattr(m, "dependencies", []),
                            "status": m_status,
                        })
            except Exception as _ms_err:
                logger.warning(f"Could not load milestones for {obj.id}: {_ms_err}")

            # Check quality report — safe call
            quality_info = None
            try:
                report = self.obj_orch.evaluate_plan_quality(obj.id)
                if report:
                    quality_info = {
                        "score": report.score,
                        "grade": report.grade,
                        "is_viable": report.is_viable,
                    }
            except Exception:
                pass

            # Safe attribute access for Phase 9 fields that may not be on older records
            domain_val = "GENERAL"
            try:
                if hasattr(obj, "domain") and obj.domain:
                    domain_val = obj.domain.value if hasattr(obj.domain, "value") else str(obj.domain)
            except Exception:
                pass

            strategy_val = "STANDARD"
            try:
                if hasattr(obj, "strategy_name") and obj.strategy_name:
                    strategy_val = obj.strategy_name
            except Exception:
                pass

            spent_val = 0.0
            try:
                proj_id = getattr(obj, "project_id", None) or f"proj_{obj.id}"
                if hasattr(self.office, "usage_tracker"):
                    usage = self.office.usage_tracker.get_project_usage(proj_id)
                    spent_val = float(usage.get("total_cost", 0.0) or 0.0)
                elif hasattr(obj, "spent"):
                    spent_val = float(obj.spent or 0.0)
            except Exception:
                pass

            budget_val = float(getattr(obj, "budget", 0.0) or 0.0)
            completed_ms = sum(1 for m in milestones if m.get("status") == "COMPLETED")

            objectives_data.append({
                "id": obj.id,
                "title": obj.title,
                "description": obj.description,
                "status": obj.status.value if hasattr(obj.status, "value") else str(obj.status),
                "priority": obj.priority.value if hasattr(obj.priority, "value") else str(obj.priority),
                "budget": budget_val,
                "spent": round(spent_val, 4),
                "domain": domain_val,
                "strategy": strategy_val,
                "completed_milestones": completed_ms,
                "total_milestones": len(milestones),
                "milestones": milestones,
                "quality": quality_info,
                "created_at": getattr(obj, "created_at", ""),
            })

        # 4. Recent Events for live ticker
        recent_events = []
        try:
            raw_evts = self.db.conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT 35"
            ).fetchall()
            for r in raw_evts:
                d = dict(r)
                recent_events.append({
                    "id": d.get("id"),
                    "event_type": d.get("event_type"),
                    "project_id": d.get("project_id"),
                    "agent_role": d.get("agent_role"),
                    "created_at": d.get("created_at"),
                    "data": d.get("data"),
                })
        except Exception as e:
            logger.warning(f"Error fetching recent events: {e}")

        # 5. Work tasks overview
        work_tasks = []
        try:
            tasks = self.db.list_work_tasks()
            for t in tasks[:30]:
                work_tasks.append({
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "status": t["status"],
                    "assigned_employee_id": t.get("assigned_employee_id"),
                    "priority": t.get("priority", 0),
                    "project_id": t.get("project_id"),
                })
        except Exception as e:
            logger.warning(f"Error fetching work tasks: {e}")

        # 6. Overall HUD stats
        def _safe_budget(o): 
            return float(getattr(o, "budget", 0.0) or 0.0)
        def _safe_spent(o):
            return float(getattr(o, "spent", 0.0) or 0.0)
        def _obj_status(o):
            s = o.status
            return s.value if hasattr(s, "value") else str(s)

        total_budget = sum(_safe_budget(o) for o in all_objs if _safe_budget(o) > 0) or 50000.0
        total_spent = state_dict.get("total_cost", 0.0) + sum(_safe_spent(o) for o in all_objs)
        remaining_funds = max(0.0, total_budget - total_spent)

        active_statuses = {"EXECUTING", "IN_PROGRESS", "PLANNED", "READY", "PLANNING", "EVALUATING"}
        hud = {
            "company_name": "AETHER OFFICE INC.",
            "ticks": self.tick_count,
            "treasury_funds": round(remaining_funds, 2),
            "total_budget": round(total_budget, 2),
            "total_spent": round(total_spent, 2),
            "active_quests": sum(1 for o in all_objs if _obj_status(o) in active_statuses),
            "completed_quests": sum(1 for o in all_objs if _obj_status(o) == "COMPLETED"),
            "total_workforce": state_dict.get("total_employees", 0),
            "busy_workforce": sum(1 for room in rooms for emp in room.get("employees", []) if emp.get("availability") == "busy" or emp.get("live_state") == "WORKING"),
            "available_workforce": sum(1 for room in rooms for emp in room.get("employees", []) if emp.get("availability") != "busy" and emp.get("live_state") != "WORKING"),
            "offline_workforce": state_dict.get("offline_employees", 0),
            "running_tasks": state_dict.get("running_tasks", 0) + (len(self.telemetry.get_active_activities()) if hasattr(self, "telemetry") else 0),
            "completed_tasks": state_dict.get("completed_tasks", 0),
            "active_crons": sum(1 for j in (self.cron.list_jobs() if hasattr(self, "cron") else []) if j["enabled"]),
            "system_health": 99.4 if state_dict.get("failed_tasks", 0) == 0 else 88.0,
            "timestamp": time.time(),
        }

        return {
            "hud": hud,
            "rooms": rooms,
            "objectives": objectives_data,
            "tasks": work_tasks,
            "recent_events": recent_events,
            "cron_jobs": self.cron.list_jobs() if hasattr(self, "cron") else [],
            "telemetry_activities": self.telemetry.get_history(25) if hasattr(self, "telemetry") else [],
        }

    def execute_scheduler_tick(self, execute_tasks: bool = True) -> Dict[str, Any]:
        """Execute one scheduler tick cycle."""
        self.tick_count += 1

        # Check for active objectives in READY, EXECUTING, or EVALUATING
        active_objs = [
            o for o in self.obj_orch.list_objectives()
            if (o.status.value if hasattr(o.status, "value") else str(o.status)) in ("READY", "EXECUTING", "EVALUATING")
        ]

        if active_objs and execute_tasks:
            for o in active_objs:
                try:
                    self.obj_orch.run_objective(o.id, auto_tick=False, max_ticks=1)
                except Exception as e:
                    logger.warning(f"Error ticking objective {o.id}: {e}")
            res = self.office.office_status()
            result_dict = res.to_dict() if hasattr(res, "to_dict") else {"status": "ok"}
        else:
            res = self.office.scheduler_tick(execute=execute_tasks)
            result_dict = res.to_dict() if hasattr(res, "to_dict") else {"status": "ok"}

        result_dict["tick_number"] = self.tick_count
        
        # Publish event
        self.event_bus.publish(
            Event(
                event_type="SCHEDULER_TICK_PROCESSED",
                project_id="office",
                payload={"tick": self.tick_count, "result": result_dict},
            )
        )
        return result_dict

    def create_objective(
        self,
        title: str,
        description: str = "",
        budget: float = 0.0,
        priority: str = "NORMAL",
        criteria: Optional[List[str]] = None,
        auto_start: bool = True,
    ) -> Dict[str, Any]:
        """Create, plan, and initiate a new business objective."""
        from projects import ProjectPriority
        prio = (
            ProjectPriority[priority.upper()]
            if isinstance(priority, str) and priority.upper() in ProjectPriority.__members__
            else ProjectPriority.NORMAL
        )
        obj = self.obj_orch.create_objective(
            title=title,
            description=description,
            budget=budget,
            priority=prio,
            acceptance_criteria=criteria,
        )
        # Immediately plan it adaptively
        plan = self.obj_orch.plan_objective(obj.id)
        report = self.obj_orch.evaluate_plan_quality(obj.id)

        # Auto-start: materialize project & tasks into work queue and perform initial tick
        if auto_start and plan and plan.is_valid:
            try:
                self.obj_orch.run_objective(obj.id, auto_tick=False, max_ticks=1)
            except Exception as e:
                logger.warning(f"Could not auto-start objective {obj.id}: {e}")

        # Refresh obj in case status changed
        refreshed_obj = self.obj_orch.get_objective(obj.id) or obj

        return {
            "id": refreshed_obj.id,
            "title": refreshed_obj.title,
            "status": refreshed_obj.status.value if hasattr(refreshed_obj.status, "value") else str(refreshed_obj.status),
            "plan_milestones": len(plan.milestones) if plan else 0,
            "quality_grade": report.grade if report else "N/A",
            "quality_score": report.score if report else 0,
        }

    def run_objective(self, objective_id: str, ticks: int = 10) -> Dict[str, Any]:
        """Run objective execution for up to N ticks."""
        from objectives import ObjectiveStatus
        obj = self.obj_orch.run_objective(objective_id, max_ticks=ticks)
        is_completed = (getattr(obj, "status", None) == ObjectiveStatus.COMPLETED) or (str(getattr(obj, "status", "")) == "COMPLETED")
        stat_val = obj.status.value if (obj and hasattr(obj.status, "value")) else str(getattr(obj, "status", "UNKNOWN"))
        msg = getattr(obj, "failure_reason", None) or f"Objective status: {stat_val}"

        return {
            "objective_id": objective_id,
            "success": is_completed,
            "status": stat_val,
            "message": msg,
        }


# Initialize FastAPI app instance
def create_app(hub: Optional[OfficeDashboardHub] = None) -> FastAPI:
    if not HAS_UI_DEPS:
        raise ImportError(
            "Dashboard requires 'fastapi' and 'uvicorn'. "
            "Please install with: pip install \"aether-office[ui]\""
        )

    if hub is None:
        hub = OfficeDashboardHub()

    app = FastAPI(
        title="Aether Office Game Dashboard",
        description="Retro Tycoon / Simulation UI for Aether Office Multi-Agent Engine",
        version="1.0.0",
    )

    # CORS for dev flexibility
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach hub to app state
    app.state.hub = hub

    # Ensure UI dir exists
    UI_DIR.mkdir(parents=True, exist_ok=True)
    custom_assets_dir = UI_DIR / "assets" / "custom"
    custom_assets_dir.mkdir(parents=True, exist_ok=True)

    # API Endpoints
    @app.get("/api/state")
    async def get_state():
        """Get full game state snapshot."""
        return hub.get_full_state()

    @app.get("/api/events/stream")
    async def events_stream(request: Request):
        """Server-Sent Events (SSE) stream for real-time visual updates."""
        queue: asyncio.Queue = asyncio.Queue()
        hub.add_sse_listener(queue)

        async def event_generator():
            try:
                # Send initial connection ping
                yield f"event: connected\ndata: {json.dumps({'status': 'online', 'time': time.time()})}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        # Wait for event or heartbeat
                        data = await asyncio.wait_for(queue.get(), timeout=2.0)
                        yield f"event: aether_event\ndata: {json.dumps(data)}\n\n"
                    except asyncio.TimeoutError:
                        # Heartbeat ping
                        yield f": ping {time.time()}\n\n"
            finally:
                hub.remove_sse_listener(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/scheduler/tick")
    async def post_tick(request: Request):
        """Trigger an operational scheduler tick."""
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        execute_tasks = body.get("execute", True)
        res = hub.execute_scheduler_tick(execute_tasks=execute_tasks)
        return {"success": True, "result": res}

    @app.post("/api/objectives")
    async def post_objective(request: Request):
        """Create and plan a new business objective from the UI."""
        data = await request.json()
        title = data.get("title")
        if not title:
            raise HTTPException(status_code=400, detail="Title is required")

        description = data.get("description", "")
        budget = float(data.get("budget", 0.0))
        priority = data.get("priority", "NORMAL")
        criteria = data.get("criteria", [])

        res = hub.create_objective(
            title=title,
            description=description,
            budget=budget,
            priority=priority,
            criteria=criteria,
        )
        return {"success": True, "objective": res}

    @app.post("/api/objectives/{objective_id}/run")
    async def post_run_objective(objective_id: str, request: Request):
        """Execute ticks for a specific objective."""
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        ticks = int(body.get("ticks", 10))
        res = hub.run_objective(objective_id, ticks=ticks)
        return {"success": True, "result": res}

    # Telemetry Ingestion Bridge Endpoints (Hermes Agent, Antigravity IDE, VS Code, Cron)
    @app.post("/api/telemetry/activity")
    async def post_telemetry_activity(request: Request):
        """Receive external AI activity signals and map to virtual office."""
        body = await request.json()
        task = body.get("task_title") or body.get("task")
        if not task:
            raise HTTPException(status_code=400, detail="'task' or 'task_title' is required")
        
        act = hub.telemetry.record_activity(
            source=body.get("source", "hermes"),
            task_title=task,
            status=body.get("status", "WORKING"),
            role=body.get("role", "developer"),
            employee_id=body.get("employee_id"),
            employee_name=body.get("employee_name"),
            project=body.get("project", "Aplikasi Kasir Pondok"),
            details=body.get("details", ""),
            metadata=body.get("metadata", {}),
        )
        return {"success": True, "activity": act.to_dict()}

    @app.get("/api/telemetry/activities")
    async def get_telemetry_activities():
        """Retrieve recent external AI activity feed."""
        return {"success": True, "activities": hub.telemetry.get_history(50)}

    @app.post("/api/telemetry/clear")
    async def post_telemetry_clear():
        """Clear active external activities."""
        hub.telemetry.clear_active()
        return {"success": True}

    # Cron Engine Endpoints
    @app.get("/api/cron/jobs")
    async def get_cron_jobs():
        """List all background cron jobs and their next scheduled run."""
        return {"success": True, "jobs": hub.cron.list_jobs()}

    @app.post("/api/cron/jobs/{job_id}/run")
    async def post_run_cron_job(job_id: str):
        """Manually trigger immediate execution of a cron job."""
        res = hub.cron.run_job_now(job_id)
        if not res:
            raise HTTPException(status_code=404, detail=f"Cron job '{job_id}' not found")
        return {"success": True, "job": res}

    @app.post("/api/cron/jobs/{job_id}/toggle")
    async def post_toggle_cron_job(job_id: str, request: Request):
        """Enable or disable a specific cron job."""
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        res = hub.cron.toggle_job(job_id, enable=body.get("enabled"))
        if not res:
            raise HTTPException(status_code=404, detail=f"Cron job '{job_id}' not found")
        return {"success": True, "job": res}

    @app.post("/api/cron/jobs")
    async def post_create_cron_job(request: Request):
        """Register a new custom cron job."""
        from cron_engine import CronJob
        data = await request.json()
        name = data.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        
        job_id = data.get("job_id") or f"cron_{uuid.uuid4().hex[:6]}"
        job = CronJob(
            job_id=job_id,
            name=name,
            description=data.get("description", ""),
            interval_seconds=int(data.get("interval_seconds", 120)),
            assigned_role=data.get("assigned_role", "devops"),
            action_type=data.get("action_type", "command"),
            action_target=data.get("action_target", "echo 'Custom cron executed'"),
        )
        hub.cron.add_job(job)
        return {"success": True, "job": job.to_dict()}

    # Serve static assets
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

    @app.get("/")
    async def index():
        index_file = UI_DIR / "index.html"
        if not index_file.exists():
            return HTMLResponse("<h1>Aether Office Dashboard: index.html not found</h1>", status_code=404)
        return FileResponse(str(index_file))

    return app


def start_dashboard(
    host: str = "127.0.0.1",
    port: int = 8000,
    auto_open: bool = True,
    config_path: str = "config.yaml",
) -> None:
    """Launch the dashboard web server."""
    if not HAS_UI_DEPS:
        print("\n" + "=" * 65)
        print("❌ DASHBOARD DEPENDENCY MISSING")
        print("   FastAPI and Uvicorn are required to launch the game dashboard.")
        print("   Please run one of the following commands in your terminal:")
        print("       pip install -e \".[ui]\"")
        print("   or directly:")
        print("       pip install fastapi uvicorn")
        print("=" * 65 + "\n")
        sys.exit(1)

    hub = OfficeDashboardHub(config_path=config_path)
    app = create_app(hub)

    url = f"http://{host}:{port}"
    print("\n" + "=" * 65)
    print("🎮 AETHER OFFICE — VIRTUAL OFFICE GAME DASHBOARD")
    print(f"   Server running at: {url}")
    print("   Press CTRL+C to stop the dashboard server.")
    print("=" * 65 + "\n")

    if auto_open:
        def _open_browser():
            time.sleep(1.0)
            webbrowser.open(url)

        import threading
        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_dashboard()

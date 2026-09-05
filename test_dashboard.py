"""Tests for Aether Office Game Dashboard (FastAPI + Observer Hub)."""

import os
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from db import Database
from events import EventBus
from workforce import create_default_organization
from office import OfficeOrchestrator
from objective_orchestrator import ObjectiveOrchestrator
from adaptive_planner import AdaptiveObjectivePlanner
from dashboard import OfficeDashboardHub, create_app, HAS_UI_DEPS


@pytest.fixture
def test_hub(tmp_path):
    """Create an isolated OfficeDashboardHub for testing."""
    db_path = str(tmp_path / "test_tasks.db")
    event_bus = EventBus()
    db = Database(db_path, event_bus=event_bus)
    org, _ = create_default_organization()
    db.sync_organization_to_db(org)

    hub = OfficeDashboardHub.__new__(OfficeDashboardHub)
    hub.config_path = "config.yaml"
    hub.config = {"project": {"data_dir": str(tmp_path)}}
    hub.event_bus = event_bus
    hub.db = db
    hub.organization = org
    hub.office = OfficeOrchestrator(db=db, organization=org, event_bus=event_bus)
    hub.planner = AdaptiveObjectivePlanner(organization=org, event_bus=event_bus)
    hub.obj_orch = ObjectiveOrchestrator(
        office_orchestrator=hub.office,
        planner=hub.planner,
        db=db,
        event_bus=event_bus,
        use_adaptive=True,
    )
    hub._sse_queues = []
    hub.event_bus.subscribe(hub._on_event)
    hub.tick_count = 0
    return hub


def test_dashboard_hub_state_structure(test_hub):
    """Verify state snapshot returns all required tycoon HUD and room elements."""
    state = test_hub.get_full_state()

    assert "hud" in state
    hud = state["hud"]
    assert hud["company_name"] == "AETHER OFFICE INC."
    assert hud["total_workforce"] > 0
    assert hud["system_health"] >= 0.0

    assert "rooms" in state
    rooms = state["rooms"]
    assert len(rooms) == 8
    dept_ids = {r["id"] for r in rooms}
    assert "engineering" in dept_ids
    assert "product" in dept_ids
    assert "business" in dept_ids
    assert "design" in dept_ids

    # Check room details
    eng_room = next(r for r in rooms if r["id"] == "engineering")
    assert len(eng_room["employees"]) > 0
    emp = eng_room["employees"][0]
    assert "id" in emp
    assert "name" in emp
    assert "rpg_class" in emp
    assert "level" in emp

    assert "objectives" in state
    assert "tasks" in state
    assert "recent_events" in state


def test_dashboard_scheduler_tick(test_hub):
    """Verify scheduler tick triggers cleanly and updates tick count."""
    assert test_hub.tick_count == 0
    result = test_hub.execute_scheduler_tick(execute_tasks=False)
    assert test_hub.tick_count == 1
    assert result["tick_number"] == 1


def test_dashboard_create_objective(test_hub):
    """Verify objective creation via hub."""
    obj_info = test_hub.create_objective(
        title="Test Campaign 1",
        description="Verify game dashboard objective creation",
        budget=1500.0,
        priority="HIGH",
        criteria=["Must be fast", "Must be reliable"],
    )

    assert obj_info["title"] == "Test Campaign 1"
    assert obj_info["status"] in ("PLANNED", "READY", "IN_PROGRESS", "DRAFT")
    assert obj_info["plan_milestones"] > 0


def test_dashboard_fastapi_endpoints(test_hub):
    """Verify FastAPI endpoints return expected responses."""
    if not HAS_UI_DEPS:
        pytest.skip("FastAPI not installed")

    app = create_app(test_hub)
    client = TestClient(app)

    # 1. GET /
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "AETHER OFFICE" in res_index.text

    # 2. GET /api/state
    res_state = client.get("/api/state")
    assert res_state.status_code == 200
    state_json = res_state.json()
    assert state_json["hud"]["company_name"] == "AETHER OFFICE INC."

    # 3. POST /api/scheduler/tick
    res_tick = client.post("/api/scheduler/tick", json={"execute": False})
    assert res_tick.status_code == 200
    tick_json = res_tick.json()
    assert tick_json["success"] is True
    assert tick_json["result"]["tick_number"] == 1

    # 4. POST /api/objectives
    res_obj = client.post("/api/objectives", json={
        "title": "API Test Quest",
        "description": "Created via FastAPI endpoint",
        "budget": 2000.0,
        "priority": "CRITICAL",
    })
    assert res_obj.status_code == 200
    obj_json = res_obj.json()
    assert obj_json["success"] is True
    assert obj_json["objective"]["title"] == "API Test Quest"

    # 5. Static files
    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200
    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200

"""Phase 3 Test Suite — Real-Time Event Streaming & Multi-Agent Foundation."""

import unittest
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from events import (
    Event,
    EventBus,
    Stream,
    format_cli_event,
    CLIProgressStreamer,
    EVENT_AGENT_REGISTERED,
    EVENT_AGENT_STATE_CHANGED,
    EVENT_AGENT_STARTED,
    EVENT_AGENT_COMPLETED,
    EVENT_AGENT_FAILED,
    EVENT_TASK_CREATED,
    EVENT_PIPELINE_STARTED,
    EVENT_PIPELINE_COMPLETED,
    EVENT_PIPELINE_FAILED,
    EVENT_DEV_UNIT_STARTED,
    EVENT_DEV_UNIT_RETRY,
    EVENT_DEV_UNIT_COMPLETED,
    EVENT_QA_TEST_STARTED,
    EVENT_QA_TEST_PASSED,
    EVENT_QA_TEST_FAILED,
)
from registry import (
    STATE_IDLE,
    STATE_THINKING,
    STATE_PLANNING,
    STATE_WORKING,
    STATE_WAITING,
    STATE_RETRYING,
    STATE_TESTING,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_BLOCKED,
    ALL_AGENT_STATES,
    validate_agent_state,
    validate_agent_transition,
    AgentManifest,
    AgentRegistry,
    Department,
    Organization,
    create_default_organization,
)
from db import Database
from agents.base import Agent
from agents.pm import PMAgent
from agents.conceptor import ConceptorAgent
from agents.planner import Planner
from agents.developer import DeveloperAgent
from agents.qa import QAAgent
from orchestrator import Orchestrator
from result import AgentResult


# =====================================================================
# 1. Event Envelope Tests
# =====================================================================

class TestEventEnvelope(unittest.TestCase):
    def test_envelope_defaults_and_uuid(self):
        evt = Event(event_type="agent_started", project_id="proj_1")
        self.assertIsNotNone(evt.event_id)
        self.assertTrue(len(evt.event_id) > 10)
        self.assertIsNotNone(evt.timestamp)
        self.assertEqual(evt.event_type, "agent_started")
        self.assertEqual(evt.project_id, "proj_1")
        self.assertEqual(evt.payload, {})
        self.assertEqual(evt.metadata, {})

    def test_envelope_to_and_from_dict(self):
        evt = Event(
            event_type=EVENT_AGENT_STATE_CHANGED,
            project_id="proj_test",
            task_id=42,
            agent_id="developer_001",
            agent_role="developer",
            status="WORKING",
            payload={"unit": "app.py", "progress": "1/5"},
            metadata={"source": "unit_test"},
        )
        d = evt.to_dict()
        self.assertEqual(d["agent_id"], "developer_001")
        self.assertEqual(d["agent_role"], "developer")
        self.assertEqual(d["status"], "WORKING")
        self.assertEqual(d["payload"]["unit"], "app.py")

        reconstructed = Event.from_dict(d)
        self.assertEqual(reconstructed.event_id, evt.event_id)
        self.assertEqual(reconstructed.timestamp, evt.timestamp)
        self.assertEqual(reconstructed.project_id, "proj_test")
        self.assertEqual(reconstructed.agent_id, "developer_001")
        self.assertEqual(reconstructed.agent_role, "developer")
        self.assertEqual(reconstructed.status, "WORKING")
        self.assertEqual(reconstructed.payload, evt.payload)
        self.assertEqual(reconstructed.metadata, evt.metadata)

    def test_envelope_identity_separated_from_role(self):
        evt1 = Event(
            event_type="test", project_id="p", agent_id="developer_001", agent_role="developer"
        )
        evt2 = Event(
            event_type="test", project_id="p", agent_id="developer_002", agent_role="developer"
        )
        self.assertNotEqual(evt1.agent_id, evt2.agent_id)
        self.assertEqual(evt1.agent_role, evt2.agent_role)


# =====================================================================
# 2. Event Bus Tests
# =====================================================================

class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_publish_and_subscribe(self):
        received = []
        handler = lambda evt: received.append(evt)

        self.bus.subscribe(handler)
        self.assertEqual(self.bus.subscriber_count, 1)

        event = Event(event_type="test_event", project_id="p1", payload={"foo": "bar"})
        self.bus.publish(event)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, "test_event")
        self.assertEqual(received[0].payload["foo"], "bar")

    def test_unsubscribe(self):
        received = []
        handler = lambda evt: received.append(evt)

        self.bus.subscribe(handler)
        self.bus.publish(Event(event_type="evt1", project_id="p1"))
        self.assertEqual(len(received), 1)

        self.bus.unsubscribe(handler)
        self.bus.publish(Event(event_type="evt2", project_id="p1"))
        self.assertEqual(len(received), 1)  # No new event received
        self.assertEqual(self.bus.subscriber_count, 0)

    def test_subscriber_exception_isolation(self):
        received_by_healthy = []

        def failing_handler(evt):
            raise RuntimeError("Subscriber crashed intentionally")

        def healthy_handler(evt):
            received_by_healthy.append(evt)

        self.bus.subscribe(failing_handler)
        self.bus.subscribe(healthy_handler)

        event = Event(event_type="test_isolation", project_id="p1")
        # Publishing must NOT raise error despite failing_handler crashing
        self.bus.publish(event)

        # Healthy handler still received event
        self.assertEqual(len(received_by_healthy), 1)
        # Error record captured
        self.assertEqual(len(self.bus.subscriber_errors), 1)
        self.assertIn("Subscriber crashed intentionally", self.bus.subscriber_errors[0]["error"])

    def test_multiple_subscribers(self):
        log_a = []
        log_b = []
        self.bus.subscribe(lambda e: log_a.append(e))
        self.bus.subscribe(lambda e: log_b.append(e))

        evt = Event(event_type="multi_test", project_id="p1")
        self.bus.publish(evt)

        self.assertEqual(len(log_a), 1)
        self.assertEqual(len(log_b), 1)


# =====================================================================
# 3. Streaming Layer Abstraction Tests
# =====================================================================

class TestStreamingAbstraction(unittest.TestCase):
    def test_stream_publish_and_iter(self):
        stream = Stream()
        stream.publish(Event(event_type="event_1", project_id="p1"))
        stream.publish(Event(event_type="event_2", project_id="p1"))

        events = list(stream.iter_events(timeout=0.05))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, "event_1")
        self.assertEqual(events[1].event_type, "event_2")

    def test_stream_close_unblocks(self):
        stream = Stream()
        stream.publish(Event(event_type="first", project_id="p1"))
        stream.close()

        # Should cleanly finish without hanging
        events = list(stream.iter_events(timeout=0.1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "first")

    def test_stream_subscribe_delegates_to_bus(self):
        bus = EventBus()
        stream = Stream(event_bus=bus)

        received = []
        stream.subscribe(lambda e: received.append(e))

        stream.publish(Event(event_type="delegated", project_id="p1"))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, "delegated")


# =====================================================================
# 4. Agent State Model Tests
# =====================================================================

class TestAgentStateModel(unittest.TestCase):
    def test_all_agent_states_recognized(self):
        expected_states = {
            "IDLE", "THINKING", "PLANNING", "WORKING", "WAITING",
            "RETRYING", "TESTING", "COMPLETED", "FAILED", "BLOCKED",
        }
        self.assertEqual(ALL_AGENT_STATES, expected_states)
        for s in expected_states:
            self.assertTrue(validate_agent_state(s))

    def test_invalid_agent_state(self):
        self.assertFalse(validate_agent_state("SLEEPING"))
        self.assertFalse(validate_agent_state("INVALID_STATE"))

    def test_valid_agent_transitions(self):
        self.assertTrue(validate_agent_transition(STATE_IDLE, STATE_THINKING))
        self.assertTrue(validate_agent_transition(STATE_IDLE, STATE_PLANNING))
        self.assertTrue(validate_agent_transition(STATE_THINKING, STATE_WORKING))
        self.assertTrue(validate_agent_transition(STATE_PLANNING, STATE_WORKING))
        self.assertTrue(validate_agent_transition(STATE_WORKING, STATE_RETRYING))
        self.assertTrue(validate_agent_transition(STATE_RETRYING, STATE_WORKING))
        self.assertTrue(validate_agent_transition(STATE_WORKING, STATE_COMPLETED))
        self.assertTrue(validate_agent_transition(STATE_WORKING, STATE_FAILED))
        self.assertTrue(validate_agent_transition(STATE_TESTING, STATE_COMPLETED))
        self.assertTrue(validate_agent_transition(STATE_TESTING, STATE_FAILED))

    def test_invalid_agent_transitions(self):
        self.assertFalse(validate_agent_transition(STATE_IDLE, STATE_RETRYING))
        self.assertFalse(validate_agent_transition(STATE_COMPLETED, STATE_RETRYING))
        self.assertFalse(validate_agent_transition("UNKNOWN", STATE_WORKING))


# =====================================================================
# 5. Agent Registry Tests
# =====================================================================

class TestAgentRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = AgentRegistry()

    def test_register_and_get(self):
        manifest = AgentManifest(
            id="developer_001",
            name="Alice",
            role="developer",
            department="engineering",
            capabilities=["python", "fastapi", "testing"],
        )
        self.registry.register(manifest)

        found = self.registry.get("developer_001")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Alice")
        self.assertEqual(found.role, "developer")
        self.assertIn("fastapi", found.capabilities)

    def test_duplicate_agent_id_rejected(self):
        m1 = AgentManifest(id="agent_1", name="A", role="developer")
        m2 = AgentManifest(id="agent_1", name="B", role="qa")
        self.registry.register(m1)

        with self.assertRaises(ValueError):
            self.registry.register(m2)

    def test_list_agents(self):
        self.registry.register(AgentManifest(id="a1", name="A", role="developer"))
        self.registry.register(AgentManifest(id="a2", name="B", role="qa"))
        self.assertEqual(len(self.registry.list()), 2)

    def test_find_by_role_supports_multiple_agents_same_role(self):
        self.registry.register(AgentManifest(id="dev_001", name="Backend Specialist", role="developer"))
        self.registry.register(AgentManifest(id="dev_002", name="Frontend Specialist", role="developer"))
        self.registry.register(AgentManifest(id="qa_001", name="Tester", role="qa"))

        devs = self.registry.find_by_role("developer")
        self.assertEqual(len(devs), 2)
        dev_ids = {d.id for d in devs}
        self.assertEqual(dev_ids, {"dev_001", "dev_002"})

    def test_find_by_department(self):
        self.registry.register(AgentManifest(id="pm_001", name="PM", role="pm", department="product"))
        self.registry.register(AgentManifest(id="dev_001", name="Dev", role="developer", department="engineering"))

        product_staff = self.registry.find_by_department("product")
        self.assertEqual(len(product_staff), 1)
        self.assertEqual(product_staff[0].id, "pm_001")

    def test_update_status(self):
        self.registry.register(AgentManifest(id="dev_001", name="Dev", role="developer", status=STATE_IDLE))
        self.assertTrue(self.registry.update_status("dev_001", STATE_WORKING))
        self.assertEqual(self.registry.get("dev_001").status, STATE_WORKING)
        self.assertFalse(self.registry.update_status("nonexistent", STATE_WORKING))

    def test_default_organization_hierarchy(self):
        org, reg = create_default_organization()
        self.assertEqual(org.name, "Aether Office")
        self.assertIsNotNone(org.get_department("engineering"))
        self.assertIsNotNone(org.get_department("product"))

        # Check 5 core specialists registered
        self.assertIsNotNone(reg.get("pm_001"))
        self.assertIsNotNone(reg.get("conceptor_001"))
        self.assertIsNotNone(reg.get("planner_001"))
        self.assertIsNotNone(reg.get("developer_001"))
        self.assertIsNotNone(reg.get("qa_001"))


# =====================================================================
# 6. Event Persistence and Current State Tests
# =====================================================================

class TestEventPersistenceAndCurrentState(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.db = Database(":memory:", event_bus=self.bus)
        self.db.create_project("proj_1", "Test Project", "brief", "/tmp/out")

    def test_event_persistence_with_envelope_fields(self):
        evt = Event(
            event_type="test_event",
            project_id="proj_1",
            agent_id="dev_001",
            agent_role="developer",
            status="WORKING",
            payload={"step": 1},
        )
        self.db.log_event("proj_1", "test_event", event=evt)

        rows = self.db.get_events("proj_1")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["event_type"], "test_event")
        self.assertEqual(r["agent_id"], "dev_001")
        self.assertEqual(r["agent_role"], "developer")
        self.assertEqual(r["status"], "WORKING")
        self.assertIn('"step": 1', r["data"])

    def test_current_state_query_without_replay(self):
        # Update agent states
        self.db.set_agent_state("developer_001", "proj_1", "developer", "WORKING", {"unit": "app.py"})
        self.db.set_agent_state("qa_001", "proj_1", "qa", "IDLE")

        # Query state directly without replaying events
        dev_state = self.db.get_agent_state("developer_001", "proj_1")
        self.assertIsNotNone(dev_state)
        self.assertEqual(dev_state["state"], "WORKING")
        self.assertEqual(dev_state["details"]["unit"], "app.py")

        qa_state = self.db.get_agent_state("qa_001", "proj_1")
        self.assertIsNotNone(qa_state)
        self.assertEqual(qa_state["state"], "IDLE")

        all_states = self.db.get_all_agent_states("proj_1")
        self.assertEqual(len(all_states), 2)

    def test_event_replay(self):
        self.db.log_event("proj_1", "event_a", agent_role="pm", data={"msg": "first"})
        self.db.log_event("proj_1", "event_b", agent_role="developer", data={"msg": "second"})

        replayed_events = []
        result = self.db.replay_events("proj_1", handler=lambda e: replayed_events.append(e))

        self.assertEqual(len(result), 2)
        self.assertEqual(len(replayed_events), 2)
        self.assertEqual(result[0].event_type, "event_a")
        self.assertEqual(result[0].payload["msg"], "first")
        self.assertEqual(result[1].event_type, "event_b")
        self.assertEqual(result[1].payload["msg"], "second")


# =====================================================================
# 7. CLI Progress Streamer Formatting Tests
# =====================================================================

class TestCLIProgressStreamer(unittest.TestCase):
    def test_cli_format_agent_states(self):
        pm_evt = Event(
            event_type=EVENT_AGENT_STATE_CHANGED,
            project_id="p1",
            agent_role="pm",
            status="THINKING",
            timestamp="2026-09-05T09:32:10Z",
        )
        line = format_cli_event(pm_evt)
        self.assertIn("09:32:10", line)
        self.assertIn("PM", line)
        self.assertIn("THINKING", line)

        dev_unit_evt = Event(
            event_type=EVENT_AGENT_STATE_CHANGED,
            project_id="p1",
            agent_role="developer",
            status="WORKING",
            payload={"unit": "app.py", "progress": "1/5"},
            timestamp="2026-09-05T09:32:27Z",
        )
        line = format_cli_event(dev_unit_evt)
        self.assertIn("09:32:27", line)
        self.assertIn("DEVELOPER", line)
        self.assertIn("app.py", line)
        self.assertIn("1/5", line)

        dev_retry_evt = Event(
            event_type=EVENT_AGENT_STATE_CHANGED,
            project_id="p1",
            agent_role="developer",
            status="RETRYING",
            payload={"unit": "services.py"},
            timestamp="2026-09-05T09:32:37Z",
        )
        line = format_cli_event(dev_retry_evt)
        self.assertIn("09:32:37", line)
        self.assertIn("DEVELOPER", line)
        self.assertIn("services.py", line)
        self.assertIn("RETRY", line)

        qa_pass_evt = Event(
            event_type=EVENT_AGENT_STATE_CHANGED,
            project_id="p1",
            agent_role="qa",
            status="COMPLETED",
            payload={"verdict": "PASS"},
            timestamp="2026-09-05T09:32:49Z",
        )
        line = format_cli_event(qa_pass_evt)
        self.assertIn("09:32:49", line)
        self.assertIn("QA", line)
        self.assertIn("PASS", line)

        complete_evt = Event(
            event_type=EVENT_PIPELINE_COMPLETED,
            project_id="p1",
        )
        self.assertEqual(format_cli_event(complete_evt), "\nPROJECT COMPLETE")

    def test_cli_streamer_integration(self):
        output_lines = []
        streamer = CLIProgressStreamer(print_fn=output_lines.append)

        events = [
            Event(event_type=EVENT_AGENT_STATE_CHANGED, project_id="p", agent_role="pm", status="THINKING", timestamp="2026-09-05T09:32:10Z"),
            Event(event_type=EVENT_AGENT_STATE_CHANGED, project_id="p", agent_role="pm", status="COMPLETED", timestamp="2026-09-05T09:32:14Z"),
            Event(event_type=EVENT_AGENT_STATE_CHANGED, project_id="p", agent_role="conceptor", status="THINKING", timestamp="2026-09-05T09:32:14Z"),
            Event(event_type=EVENT_AGENT_STATE_CHANGED, project_id="p", agent_role="conceptor", status="COMPLETED", timestamp="2026-09-05T09:32:19Z"),
            Event(event_type=EVENT_PIPELINE_COMPLETED, project_id="p"),
        ]

        for e in events:
            streamer.on_event(e)

        full_output = "\n".join(output_lines)
        self.assertIn("[AETHER OFFICE]", full_output)
        self.assertIn("PM          THINKING", full_output)
        self.assertIn("PM          COMPLETED", full_output)
        self.assertIn("CONCEPTOR   THINKING", full_output)
        self.assertIn("CONCEPTOR   COMPLETED", full_output)
        self.assertIn("PROJECT COMPLETE", full_output)


# =====================================================================
# 8. Agent Integration and State Emissions Tests
# =====================================================================

class TestAgentIntegrationAndEmissions(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.db = Database(":memory:", event_bus=self.bus)
        self.db.create_project("proj_agent", "Test", "brief", "/tmp/out")
        self.mock_llm = MagicMock()

    def test_pm_emits_generic_events_and_state(self):
        bus_events = []
        self.bus.subscribe(bus_events.append)

        pm = PMAgent(self.mock_llm, self.db, "proj_agent", "/tmp/out",
                     agent_id="pm_001", event_bus=self.bus)

        self.mock_llm.chat.return_value = {
            "project_name": "TestApp",
            "project_description": "A test app",
            "tasks": [{"title": "Task 1", "description": "Do something"}],
            "tech_stack": "Python",
            "file_structure": "app.py",
        }

        with patch.object(pm, "_write_doc", return_value=True):
            res = pm.create_project("Build a test app")

        self.assertTrue(res.success)
        self.assertEqual(pm.state, STATE_COMPLETED)

        # Verify DB state
        db_state = self.db.get_agent_state("pm_001", "proj_agent")
        self.assertEqual(db_state["state"], STATE_COMPLETED)

        # Verify event bus received state changes
        state_events = [e for e in bus_events if e.event_type == EVENT_AGENT_STATE_CHANGED]
        states_seen = [e.payload.get("state") for e in state_events]
        self.assertIn(STATE_THINKING, states_seen)
        self.assertIn(STATE_WORKING, states_seen)
        self.assertIn(STATE_COMPLETED, states_seen)

    def test_conceptor_emits_generic_events_and_state(self):
        bus_events = []
        self.bus.subscribe(bus_events.append)

        self.db.create_task("proj_agent", "Task 1")
        conceptor = ConceptorAgent(self.mock_llm, self.db, "proj_agent", "/tmp/out",
                                   agent_id="conceptor_001", event_bus=self.bus)

        self.mock_llm.chat.return_value = "# Requirements\n\n## Testing Strategy\nTest all endpoints."

        with patch.object(conceptor, "_write_doc", return_value=True):
            res = conceptor.create_requirements()

        self.assertTrue(res.success)
        self.assertEqual(conceptor.state, STATE_COMPLETED)

        db_state = self.db.get_agent_state("conceptor_001", "proj_agent")
        self.assertEqual(db_state["state"], STATE_COMPLETED)

        state_events = [e for e in bus_events if e.event_type == EVENT_AGENT_STATE_CHANGED]
        states_seen = [e.payload.get("state") for e in state_events]
        self.assertIn(STATE_THINKING, states_seen)
        self.assertIn(STATE_WORKING, states_seen)
        self.assertIn(STATE_COMPLETED, states_seen)

    def test_planner_emits_generic_events(self):
        bus_events = []
        self.bus.subscribe(bus_events.append)

        base_agent = Agent(self.mock_llm, self.db, "proj_agent", "/tmp/out",
                           agent_id="developer_001", event_bus=self.bus)
        planner = Planner(base_agent)

        self.mock_llm.chat.return_value = {
            "project_summary": "Summary",
            "tech_stack": "Python",
            "files": [{"path": "app.py", "purpose": "main", "depends_on": []}],
        }

        with patch.object(base_agent, "_write_doc", return_value=True):
            res = planner.plan()

        self.assertTrue(res.success)
        planner_events = [e for e in bus_events if e.payload.get("agent_role") == "planner"]
        planner_states = [e.payload.get("state") for e in planner_events]
        self.assertIn(STATE_PLANNING, planner_states)
        self.assertIn(STATE_COMPLETED, planner_states)

    def test_developer_emits_generic_and_unit_events(self):
        bus_events = []
        self.bus.subscribe(bus_events.append)

        dev = DeveloperAgent(self.mock_llm, self.db, "proj_agent", "/tmp/out",
                             agent_id="developer_001", event_bus=self.bus)

        # Plan response
        plan_dict = {
            "project_summary": "Test App",
            "tech_stack": "Python",
            "files": [
                {"path": "app.py", "purpose": "App", "depends_on": []},
            ],
            "generation_order": ["app.py"],
        }
        # Unit response
        unit_resp = json.dumps({
            "path": "app.py",
            "content": "def main():\n    return 42\n",
            "summary": "Main entry point",
        })

        def chat_side_effect(prompt, user_msg=None, **kwargs):
            if "Software Architect" in prompt:
                return plan_dict
            return unit_resp

        self.mock_llm.chat.side_effect = chat_side_effect

        with patch.object(dev, "_write_doc", return_value=True), \
             patch.object(dev, "_write_file", return_value=True):
            res = dev.implement()

        self.assertTrue(res.success)
        self.assertEqual(dev.state, STATE_COMPLETED)

        # Verify unit progress events in stream
        unit_events = [e for e in bus_events if e.payload.get("unit") == "app.py"]
        self.assertTrue(len(unit_events) > 0)
        self.assertEqual(unit_events[0].payload.get("progress"), "1/1")

    def test_developer_retry_state_transition(self):
        bus_events = []
        self.bus.subscribe(bus_events.append)

        dev = DeveloperAgent(self.mock_llm, self.db, "proj_agent", "/tmp/out",
                             config={"developer": {"unit_max_retries": 2}},
                             agent_id="developer_001", event_bus=self.bus)

        plan_dict = {
            "project_summary": "Test App",
            "tech_stack": "Python",
            "files": [{"path": "app.py", "purpose": "App", "depends_on": []}],
            "generation_order": ["app.py"],
        }
        syntax_err_resp = json.dumps({
            "path": "app.py",
            "content": "def broken_code(\n",
            "summary": "broken",
        })
        valid_resp = json.dumps({
            "path": "app.py",
            "content": "def fixed():\n    return True\n",
            "summary": "fixed",
        })

        responses = [plan_dict, syntax_err_resp, valid_resp]
        self.mock_llm.chat.side_effect = responses

        with patch.object(dev, "_write_doc", return_value=True), \
             patch.object(dev, "_write_file", return_value=True):
            res = dev.implement()

        self.assertTrue(res.success)
        retry_events = [e for e in bus_events if e.payload.get("state") == STATE_RETRYING]
        self.assertTrue(len(retry_events) >= 1)
        self.assertEqual(retry_events[0].payload.get("unit"), "app.py")

    def test_qa_emits_generic_events_and_verdict(self):
        bus_events = []
        self.bus.subscribe(bus_events.append)

        qa = QAAgent(self.mock_llm, self.db, "proj_agent", "/tmp/out",
                     agent_id="qa_001", event_bus=self.bus)

        self.mock_llm.chat.return_value = {
            "verdict": "PASS",
            "summary": "All tests passed cleanly",
            "criteria_results": [{"criterion": "c1", "status": "PASS", "evidence": "ok"}],
            "bugs_found": [],
            "test_commands_to_run": [],
        }

        with patch.object(qa, "_read_all_code", return_value="def main(): pass"), \
             patch.object(qa, "_write_test_report", return_value=True):
            res = qa.test()

        self.assertTrue(res.success)
        self.assertEqual(qa.state, STATE_COMPLETED)

        db_state = self.db.get_agent_state("qa_001", "proj_agent")
        self.assertEqual(db_state["state"], STATE_COMPLETED)
        self.assertEqual(db_state["details"]["verdict"], "PASS")

        qa_events = [e for e in bus_events if e.agent_role == "qa"]
        qa_states = [e.payload.get("state") for e in qa_events if e.event_type == EVENT_AGENT_STATE_CHANGED]
        self.assertIn(STATE_TESTING, qa_states)
        self.assertIn(STATE_COMPLETED, qa_states)


# =====================================================================
# 9. Orchestrator Pipeline Lifecycle Events Tests
# =====================================================================

class TestOrchestratorPipelineEvents(unittest.TestCase):
    def test_pipeline_lifecycle_events_emitted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "project": {"data_dir": tmpdir, "output_dir": tmpdir + "/out"},
                "llm": {"endpoint": "mock", "api_key": "mock", "model": "mock"},
                "qa": {"max_retries": 1},
            }

            orchestrator = Orchestrator(config, "proj_orch", tmpdir + "/out")
            bus_events = []
            orchestrator.event_bus.subscribe(bus_events.append)

            # Mock agent runs
            orchestrator.pm.create_project = MagicMock(return_value=AgentResult(success=True, output={"task_count": 1}))
            orchestrator.conceptor.create_requirements = MagicMock(return_value=AgentResult(success=True, output="Reqs"))
            orchestrator.developer.implement = MagicMock(return_value=AgentResult(success=True, files=["app.py"]))
            orchestrator.qa.test = MagicMock(return_value=AgentResult(success=True, output={"verdict": "PASS"}))

            with patch.object(orchestrator, "_write_summary"):
                res = orchestrator.run("Test brief")

            self.assertTrue(res["success"])

            # Check pipeline started and completed events were emitted
            event_types = [e.event_type for e in bus_events]
            self.assertIn("pipeline.started", event_types)
            self.assertIn(EVENT_PIPELINE_COMPLETED, event_types)

            orchestrator.db.close()


if __name__ == "__main__":
    unittest.main()

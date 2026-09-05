"""Unit tests for PixelOffice AgentEvent Bridge."""

import os
import json
import socket
import unittest
from unittest.mock import patch, MagicMock

from events import (
    Event,
    EventBus,
    EVENT_AGENT_STATE_CHANGED,
    EVENT_DEV_UNIT_STARTED,
    EVENT_QA_TEST_STARTED,
    EVENT_PIPELINE_COMPLETED,
    EVENT_PIPELINE_FAILED,
)
from pixel_bridge import (
    PixelOfficeBridge,
    map_aether_event_to_pixel,
    PIXEL_STATE_IDLE,
    PIXEL_STATE_THINKING,
    PIXEL_STATE_PLANNING,
    PIXEL_STATE_CODING,
    PIXEL_STATE_RUNNING,
    PIXEL_STATE_SUCCESS,
    PIXEL_STATE_FAILURE,
    VALID_PIXEL_STATES,
)


class TestPixelBridgeMapping(unittest.TestCase):
    def test_state_mapping_generic(self):
        ev = Event(
            event_type=EVENT_AGENT_STATE_CHANGED,
            project_id="proj_alpha",
            agent_id="developer_001",
            agent_role="developer",
            status="WORKING",
            payload={"state": "WORKING", "action": "writing_code"},
        )
        pixel_data = map_aether_event_to_pixel(ev)
        self.assertIsNotNone(pixel_data)
        self.assertEqual(pixel_data["version"], 1)
        self.assertEqual(pixel_data["provider"], "aether")
        self.assertEqual(pixel_data["sessionId"], "proj_alpha")
        self.assertEqual(pixel_data["agentId"], "developer_001")
        self.assertEqual(pixel_data["state"], PIXEL_STATE_CODING)
        self.assertIn(pixel_data["state"], VALID_PIXEL_STATES)
        self.assertEqual(pixel_data["kind"], "upsert")

    def test_dev_unit_started_maps_to_coding(self):
        ev = Event(
            event_type=EVENT_DEV_UNIT_STARTED,
            project_id="proj_beta",
            agent_id="developer_001",
            payload={"unit_id": "service.py"},
        )
        pixel_data = map_aether_event_to_pixel(ev)
        self.assertIsNotNone(pixel_data)
        self.assertEqual(pixel_data["state"], PIXEL_STATE_CODING)
        self.assertIn("service.py", pixel_data["activity"])

    def test_qa_test_started_maps_to_running(self):
        ev = Event(
            event_type=EVENT_QA_TEST_STARTED,
            project_id="proj_gamma",
            agent_id="qa_001",
            payload={"action": "running pytest"},
        )
        pixel_data = map_aether_event_to_pixel(ev)
        self.assertIsNotNone(pixel_data)
        self.assertEqual(pixel_data["state"], PIXEL_STATE_RUNNING)

    def test_pipeline_completed_maps_to_end_kind(self):
        ev = Event(
            event_type=EVENT_PIPELINE_COMPLETED,
            project_id="proj_done",
            payload={"success": True},
        )
        pixel_data = map_aether_event_to_pixel(ev)
        self.assertIsNotNone(pixel_data)
        self.assertEqual(pixel_data["state"], PIXEL_STATE_SUCCESS)
        self.assertEqual(pixel_data["kind"], "end")


class TestPixelBridgeLifecycle(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.bridge = PixelOfficeBridge(event_bus=self.bus, udp_port=19997)

    def tearDown(self):
        self.bridge.stop()

    def test_start_and_stop(self):
        self.assertFalse(self.bridge._started)
        self.bridge.start()
        self.assertTrue(self.bridge._started)
        self.assertIn(self.bridge.on_event, self.bus._subscribers)

        self.bridge.stop()
        self.assertFalse(self.bridge._started)
        self.assertNotIn(self.bridge.on_event, self.bus._subscribers)

    def test_event_bus_forwards_to_send_payload(self):
        self.bridge.start()
        with patch.object(self.bridge, "send_payload") as mock_send:
            ev = Event(
                event_type=EVENT_DEV_UNIT_STARTED,
                project_id="p1",
                agent_id="developer_001",
                payload={"unit_id": "main.py"},
            )
            self.bus.publish(ev)

            mock_send.assert_called_once()
            payload = mock_send.call_args[0][0]
            self.assertEqual(payload["agentId"], "developer_001")
            self.assertEqual(payload["state"], PIXEL_STATE_CODING)

    def test_emit_agent_state_manual(self):
        self.bridge.start()
        with patch.object(self.bridge, "send_payload") as mock_send:
            self.bridge.emit_agent_state("pm_001", "planning", activity="Task planning")
            mock_send.assert_called_once()
            payload = mock_send.call_args[0][0]
            self.assertEqual(payload["agentId"], "pm_001")
            self.assertEqual(payload["state"], "planning")
            self.assertEqual(payload["activity"], "Task planning")

    def test_udp_send_fail_open_does_not_raise(self):
        # Even if UDP port has no listener, sendto should succeed / fail silently without raising
        self.bridge.start()
        res = self.bridge.send_payload({
            "version": 1,
            "provider": "aether",
            "sessionId": "test_session",
            "agentId": "developer_001",
            "projectId": os.path.abspath("."),
            "projectLabel": "Aether Office",
            "kind": "upsert",
            "state": "coding",
            "activity": "typing",
            "occurredAt": 1234567890,
        })
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()

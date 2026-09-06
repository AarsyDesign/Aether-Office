"""Unit tests for PixelAgentsBridge in Aether Office."""

import unittest
from unittest.mock import MagicMock, patch

from events import (
    EventBus,
    Event,
    EVENT_EMPLOYEE_RESERVED,
    EVENT_TASK_STARTED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_CLARIFICATION_REQUIRED,
    EVENT_RUNTIME_STOPPED,
)
from pixel_bridge import (
    PixelAgentsBridge,
    ROLE_TOOL_MAPPING,
    discover_pixel_agents_server,
)
from runtime import OfficeRuntime, RuntimeConfig


class TestPixelAgentsBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = PixelAgentsBridge(
            host="127.0.0.1",
            port=9999,
            token="test-token",
            auto_discover=False,
            cwd="/test/workspace",
        )

    def tearDown(self):
        self.bridge.close()

    def test_role_mappings(self):
        """Verify role-to-tool mappings."""
        self.assertEqual(ROLE_TOOL_MAPPING["developer"][0], "Edit")
        self.assertEqual(ROLE_TOOL_MAPPING["qa"][0], "Bash")
        self.assertEqual(ROLE_TOOL_MAPPING["pm"][0], "EnterPlanMode")
        self.assertEqual(ROLE_TOOL_MAPPING["researcher"][0], "WebSearch")
        self.assertEqual(ROLE_TOOL_MAPPING["ui_designer"][0], "Edit")

    def test_session_lifecycle_calls(self):
        """Test that protocol methods enqueue properly and deliver to HTTP endpoint."""
        with patch.object(self.bridge, "_send_http_request") as mock_send:
            mock_send.return_value = True

            # Test pre_tool_use
            self.bridge.pre_tool_use("agent_1", tool_name="Edit", tool_input={"file_path": "main.py"})
            self.bridge._queue.join()

            self.assertTrue(mock_send.called)
            self.assertIn("agent_1", self.bridge._active_sessions)
            self.assertEqual(self.bridge._session_tools.get("agent_1"), "Edit")

            # Test post_tool_use & turn_stop
            self.bridge.post_tool_use("agent_1")
            self.bridge.turn_stop("agent_1")
            self.bridge._queue.join()

            self.assertNotIn("agent_1", self.bridge._session_tools)

    def test_event_bus_translation(self):
        """Test EventBus event translation without actual HTTP network calls."""
        with patch.object(self.bridge, "emit_event_async") as mock_emit:
            event_bus = EventBus()
            self.bridge.attach_to_event_bus(event_bus)

            # 1. Employee reserved
            event_bus.publish(
                Event(
                    event_type=EVENT_EMPLOYEE_RESERVED,
                    project_id="test_proj",
                    agent_id="dev_001",
                    agent_role="developer",
                )
            )
            mock_emit.assert_called()
            last_payload = mock_emit.call_args[0][0]
            self.assertEqual(last_payload["session_id"], "dev_001")
            self.assertEqual(last_payload["hook_event_name"], "SessionStart")

            # 2. Task started
            event_bus.publish(
                Event(
                    event_type=EVENT_TASK_STARTED,
                    project_id="test_proj",
                    task_id="t1",
                    agent_id="dev_001",
                    agent_role="developer",
                    payload={"title": "build_database"},
                )
            )
            last_payload = mock_emit.call_args[0][0]
            self.assertEqual(last_payload["hook_event_name"], "PreToolUse")
            self.assertEqual(last_payload["tool_name"], "Edit")

            # 3. Task completed
            event_bus.publish(
                Event(
                    event_type=EVENT_TASK_COMPLETED,
                    project_id="test_proj",
                    task_id="t1",
                    agent_id="dev_001",
                    agent_role="developer",
                )
            )
            last_payload = mock_emit.call_args[0][0]
            self.assertEqual(last_payload["hook_event_name"], "Stop")

            # 4. Clarification required (shows waiting notification)
            event_bus.publish(
                Event(
                    event_type=EVENT_CLARIFICATION_REQUIRED,
                    project_id="test_proj",
                    agent_id="dev_001",
                )
            )
            last_payload = mock_emit.call_args[0][0]
            self.assertEqual(last_payload["hook_event_name"], "Notification")

            self.bridge.detach_from_event_bus(event_bus)

    def test_office_runtime_integration(self):
        """Verify OfficeRuntime accepts and binds pixel_bridge."""
        mock_orch = MagicMock()
        event_bus = EventBus()
        runtime = OfficeRuntime(
            orchestrator=mock_orch,
            event_bus=event_bus,
            pixel_bridge=self.bridge,
        )

        self.assertEqual(runtime.pixel_bridge, self.bridge)
        # Verify bridge is subscribed
        self.assertIn(self.bridge.handle_event, event_bus._subscribers)

        # Stopping running runtime closes bridge
        runtime._is_running = True
        with patch.object(self.bridge, "close") as mock_close:
            runtime.stop()
            mock_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

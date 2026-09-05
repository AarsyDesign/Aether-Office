"""Unit tests for Aether Office reliability."""

from __future__ import annotations
import sys
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from result import AgentResult
from status import validate_transition, ALL_STATES, RETRYING, VALID_TRANSITIONS
from llm import (
    LLMError, LLMAuthError, LLMRateLimitError, LLMTimeoutError, LLMResponseError,
    _clean_raw, _extract_content, call_llm, call_llm_json, call_llm_with_retry, LLMClient,
)
from db import Database
from agents.developer import detect_truncation, detect_unit_truncation, validate_syntax
from agents.qa import categorize_test_error, validate_qa_response, TEST_FAIL, RUNNER_FAIL, COMMAND_NOT_FOUND, TIMEOUT, APP_CRASH
from agents.planner import topological_sort


# ─── Test: AgentResult ───

class TestAgentResult(unittest.TestCase):
    def test_success_result(self):
        r = AgentResult(success=True, output="hello", files=["a.py"])
        self.assertTrue(r.success)
        self.assertEqual(r.output, "hello")
        self.assertEqual(r.files, ["a.py"])
        self.assertIsNone(r.error)

    def test_failure_result(self):
        r = AgentResult(success=False, error="LLM timeout")
        self.assertFalse(r.success)
        self.assertEqual(r.error, "LLM timeout")

    def test_to_dict(self):
        r = AgentResult(success=True, output={"a": 1}, files=["x.py"])
        d = r.to_dict()
        self.assertIn("success", d)
        self.assertEqual(d["output_type"], "dict")
        self.assertEqual(d["files"], ["x.py"])

    def test_default_values(self):
        r = AgentResult(success=True)
        self.assertEqual(r.files, [])
        self.assertIsNone(r.error)
        self.assertIsNone(r.usage)
        self.assertEqual(r.events, [])


# ─── Test: Task State Machine ───

class TestStateMachine(unittest.TestCase):
    def test_retrying_exists(self):
        self.assertIn(RETRYING, ALL_STATES)

    def test_valid_forward_transitions(self):
        self.assertTrue(validate_transition("BACKLOG", "READY"))
        self.assertTrue(validate_transition("READY", "IN_PROGRESS"))
        self.assertTrue(validate_transition("IN_PROGRESS", "REVIEW"))
        self.assertTrue(validate_transition("REVIEW", "QA"))
        self.assertTrue(validate_transition("QA", "DONE"))

    def test_valid_retry_transitions(self):
        self.assertTrue(validate_transition("IN_PROGRESS", "RETRYING"))
        self.assertTrue(validate_transition("RETRYING", "IN_PROGRESS"))
        self.assertTrue(validate_transition("FAILED", "RETRYING"))
        self.assertTrue(validate_transition("FAILED", "IN_PROGRESS"))

    def test_valid_block_transitions(self):
        self.assertTrue(validate_transition("READY", "BLOCKED"))
        self.assertTrue(validate_transition("IN_PROGRESS", "BLOCKED"))
        self.assertTrue(validate_transition("BLOCKED", "READY"))
        self.assertTrue(validate_transition("BLOCKED", "IN_PROGRESS"))

    def test_invalid_transitions(self):
        self.assertFalse(validate_transition("BACKLOG", "DONE"))
        self.assertFalse(validate_transition("DONE", "READY"))
        self.assertFalse(validate_transition("QA", "BACKLOG"))
        self.assertFalse(validate_transition("DONE", "IN_PROGRESS"))

    def test_invalid_state(self):
        self.assertFalse(validate_transition("INVALID", "DONE"))
        self.assertFalse(validate_transition("DONE", "INVALID"))

    def test_no_transition_from_done(self):
        self.assertEqual(VALID_TRANSITIONS["DONE"], [])


# ─── Test: LLM Utilities ───

class TestLLMCleaning(unittest.TestCase):
    def test_clean_done_trailing(self):
        raw = '{"choices":[{"message":{"content":"hi"}}]}data: [DONE]'
        self.assertEqual(_clean_raw(raw), '{"choices":[{"message":{"content":"hi"}}]}')

    def test_clean_no_done(self):
        raw = '{"choices":[]}'
        self.assertEqual(_clean_raw(raw), '{"choices":[]}')

    def test_extract_content_normal(self):
        msg = {"content": "hello"}
        self.assertEqual(_extract_content(msg), "hello")

    def test_extract_content_reasoning(self):
        msg = {"content": None, "reasoning_content": "thinking..."}
        self.assertEqual(_extract_content(msg), "thinking...")

    def test_extract_content_empty(self):
        msg = {}
        self.assertEqual(_extract_content(msg), "")


# ─── Test: Truncation Detection ───

class TestTruncationDetection(unittest.TestCase):
    def test_no_truncation(self):
        output = "### FILE: a.py\n```\nprint('hi')\n```\n### CONFIG\n```json\n{}\n```"
        warnings = detect_truncation(output)
        self.assertEqual(warnings, [])

    def test_odd_code_fences(self):
        output = "### FILE: a.py\n```\nprint('hi')"
        warnings = detect_truncation(output)
        self.assertTrue(any("code fence" in w.lower() for w in warnings))

    def test_unbalanced_braces(self):
        output = '{"key": "val", "nested": {"a": 1}'
        warnings = detect_truncation(output)
        self.assertTrue(any("brace" in w.lower() for w in warnings))

    def test_abrupt_ending(self):
        output = "some code content here"
        warnings = detect_truncation(output)
        self.assertTrue(any("abrupt" in w.lower() for w in warnings))

    def test_truncated_config(self):
        output = "### CONFIG\n```json\n{\"main\": \"app.py\""
        warnings = detect_truncation(output)
        self.assertTrue(any("config" in w.lower() for w in warnings))


# ─── Test: DB ───

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_create_project(self):
        pid = self.db.create_project("p1", "Test", "brief", "/tmp")
        self.assertEqual(pid, "p1")
        p = self.db.get_project("p1")
        self.assertEqual(p["name"], "Test")

    def test_create_task(self):
        self.db.create_project("p1", "Test", "brief", "/tmp")
        tid = self.db.create_task("p1", "Task 1", "desc", "dev", 5)
        t = self.db.get_task(tid)
        self.assertEqual(t["title"], "Task 1")
        self.assertEqual(t["status"], "BACKLOG")

    def test_update_task_status(self):
        self.db.create_project("p1", "Test", "brief", "/tmp")
        tid = self.db.create_task("p1", "Task 1")
        self.db.update_task_status(tid, "READY")
        t = self.db.get_task(tid)
        self.assertEqual(t["status"], "READY")

    def test_event_logging(self):
        self.db.create_project("p1", "Test", "brief", "/tmp")
        self.db.log_event("p1", "test.event", "pm", data={"key": "val"})
        events = self.db.get_events("p1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "test.event")

    def test_audit_log(self):
        self.db.create_project("p1", "Test", "brief", "/tmp")
        self.db.audit("p1", "pm", "test_action", {"detail": 1})
        log = self.db.get_audit_log("p1")
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["action"], "test_action")


# ─── Test: QA Error Categorization ───

class TestQAErrorCategorization(unittest.TestCase):
    def test_timeout(self):
        self.assertEqual(categorize_test_error("pytest", -1, "Command timed out after 120s"), TIMEOUT)

    def test_command_not_found_127(self):
        self.assertEqual(categorize_test_error("pytest", 127, "not found"), COMMAND_NOT_FOUND)

    def test_import_error(self):
        self.assertEqual(categorize_test_error("pytest", 1, "ModuleNotFoundError: No module named 'flask'"), RUNNER_FAIL)

    def test_syntax_error(self):
        self.assertEqual(categorize_test_error("python app.py", 1, "SyntaxError: invalid syntax"), APP_CRASH)

    def test_normal_fail(self):
        self.assertEqual(categorize_test_error("pytest", 1, "FAILED test_login.py::test_auth"), TEST_FAIL)


# ─── Test: QA Response Validation ───

class TestQAValidation(unittest.TestCase):
    def test_valid_pass(self):
        data = {"verdict": "PASS", "summary": "All good", "criteria_results": [], "bugs_found": []}
        self.assertEqual(validate_qa_response(data), [])

    def test_valid_fail(self):
        data = {"verdict": "FAIL", "summary": "Has bugs", "criteria_results": [{"criterion": "x", "status": "FAIL"}], "bugs_found": []}
        self.assertEqual(validate_qa_response(data), [])

    def test_invalid_verdict(self):
        data = {"verdict": "MAYBE", "summary": "?"}
        errors = validate_qa_response(data)
        self.assertTrue(any("verdict" in e for e in errors))

    def test_missing_summary(self):
        data = {"verdict": "PASS"}
        errors = validate_qa_response(data)
        self.assertTrue(any("summary" in e for e in errors))

    def test_not_dict(self):
        errors = validate_qa_response("not a dict")
        self.assertTrue(len(errors) > 0)


# ─── Test: LLM Retry Logic ───

class TestLLMRetry(unittest.TestCase):
    @patch("llm.call_llm")
    def test_retry_on_timeout(self, mock_call):
        mock_call.side_effect = LLMTimeoutError("timeout")  # Always fail
        with self.assertRaises(LLMError):
            call_llm_with_retry("http://x", "key", "model", [{"role": "user", "content": "hi"}],
                                max_retries=2, timeout=1)
        self.assertEqual(mock_call.call_count, 2)

    @patch("llm.call_llm")
    def test_no_retry_on_auth_error(self, mock_call):
        mock_call.side_effect = LLMAuthError("bad key")
        with self.assertRaises(LLMAuthError):
            call_llm_with_retry("http://x", "key", "model", [{"role": "user", "content": "hi"}],
                                max_retries=3, timeout=1)
        self.assertEqual(mock_call.call_count, 1)

    @patch("llm.call_llm")
    def test_retry_succeeds_on_third(self, mock_call):
        mock_call.side_effect = [
            LLMTimeoutError("timeout"),
            LLMTimeoutError("timeout"),
            ("hello", None),
        ]
        result, usage = call_llm_with_retry("http://x", "key", "model", [{"role": "user", "content": "hi"}],
                                             max_retries=3, timeout=1)
        self.assertEqual(result, "hello")

    @patch("llm.call_llm_json")
    def test_retry_json_mode(self, mock_json):
        mock_json.side_effect = [
            LLMResponseError("empty"),
            ({"key": "val"}, None),
        ]
        result, usage = call_llm_with_retry("http://x", "key", "model", [{"role": "user", "content": "hi"}],
                                             json_mode=True, max_retries=2, timeout=1)
        self.assertEqual(result, {"key": "val"})


# ─── Test: LLM Client ───

class TestLLMClient(unittest.TestCase):
    @patch("llm.call_llm_with_retry")
    def test_chat_returns_str(self, mock_retry):
        mock_retry.return_value = ("hello world", None)
        client = LLMClient("http://x", "key", "model")
        result = client.chat("system", "user")
        self.assertEqual(result, "hello world")

    @patch("llm.call_llm_with_retry")
    def test_chat_json_mode(self, mock_retry):
        mock_retry.return_value = ({"key": "val"}, None)
        client = LLMClient("http://x", "key", "model")
        result = client.chat("system", "user", json_mode=True)
        self.assertEqual(result, {"key": "val"})


# ─── Test: PM Agent Validation ───

class TestPMAgent(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.create_project("p1", "Test", "brief", "/tmp")
        self.mock_llm = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_pm_validates_non_dict(self):
        from agents.pm import PMAgent
        agent = PMAgent(self.mock_llm, self.db, "p1", "/tmp")
        self.mock_llm.chat.return_value = "not a dict"
        result = agent.create_project("test brief")
        self.assertFalse(result.success)
        self.assertIn("dict", result.error)

    def test_pm_validates_missing_fields(self):
        from agents.pm import PMAgent
        agent = PMAgent(self.mock_llm, self.db, "p1", "/tmp")
        self.mock_llm.chat.return_value = {"project_name": "x"}  # Missing 'tasks'
        result = agent.create_project("test brief")
        self.assertFalse(result.success)
        self.assertIn("tasks", result.error)

    def test_pm_validates_empty_tasks(self):
        from agents.pm import PMAgent
        agent = PMAgent(self.mock_llm, self.db, "p1", "/tmp")
        self.mock_llm.chat.return_value = {"project_name": "x", "tasks": []}
        result = agent.create_project("test brief")
        self.assertFalse(result.success)
        self.assertIn("0 tasks", result.error)

    def test_pm_success(self):
        from agents.pm import PMAgent
        agent = PMAgent(self.mock_llm, self.db, "p1", "/tmp")
        self.mock_llm.chat.return_value = {
            "project_name": "Test App",
            "project_description": "A test",
            "tasks": [{"title": "Task 1", "priority": 3}],
            "tech_stack": "Python",
        }
        result = agent.create_project("test brief")
        self.assertTrue(result.success)
        tasks = self.db.get_tasks("p1")
        self.assertEqual(len(tasks), 1)


# ─── Test: Developer Truncation + Validation ───

class TestDeveloperAgent(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.create_project("p1", "Test", "brief", "/tmp/output")
        self.mock_llm = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_developer_empty_output(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/nonexistent")
        self.mock_llm.chat.return_value = "### FILE: a.py\n```\nprint('hello')\n```"
        result = agent.implement()
        self.assertTrue(result.success)

    def test_developer_truncated_output(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/nonexistent")
        self.mock_llm.chat.return_value = "### FILE: a.py\n```\nprint('hello')"
        result = agent.implement()
        # Truncated + 0 files = fail
        self.assertFalse(result.success)
        self.assertIn("truncat", result.error.lower())

    def test_developer_llm_error(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/nonexistent")
        self.mock_llm.chat.side_effect = LLMTimeoutError("timeout")
        result = agent.implement()
        self.assertFalse(result.success)
        self.assertIn("timeout", result.error)


# ─── Test: Orchestrator Failure Boundary ───

class TestOrchestrator(unittest.TestCase):
    @patch("orchestrator.LLMClient")
    def test_orchestrator_pm_failure(self, MockLLM):
        """Pipeline stops gracefully when PM fails."""
        import tempfile
        from orchestrator import Orchestrator
        config = {
            "llm": {"endpoint": "http://x", "api_key": "k", "model": "m"},
        }
        mock_llm = MockLLM.return_value
        mock_llm.chat.side_effect = LLMTimeoutError("timeout")

        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(config, "test-p1", tmpdir)
            result = orch.run("test brief")
            self.assertFalse(result["success"])
            self.assertIsNotNone(result.get("error"))
            # Check events were logged
            events = orch.db.get_events("test-p1")
            self.assertTrue(any(e["event_type"] == "pipeline.started" for e in events))


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ─── Test: Phase 2 — Developer Planner & Chunked Generation ───

class TestTopologicalSort(unittest.TestCase):
    def test_simple_order(self):
        files = [
            {"path": "a.py", "depends_on": []},
            {"path": "b.py", "depends_on": ["a.py"]},
            {"path": "c.py", "depends_on": ["b.py"]},
        ]
        order, error = topological_sort(files)
        self.assertIsNone(error)
        self.assertEqual(order, ["a.py", "b.py", "c.py"])

    def test_independent_files(self):
        files = [
            {"path": "a.py", "depends_on": []},
            {"path": "b.py", "depends_on": []},
        ]
        order, error = topological_sort(files)
        self.assertIsNone(error)
        self.assertEqual(set(order), {"a.py", "b.py"})

    def test_circular_dependency(self):
        files = [
            {"path": "a.py", "depends_on": ["b.py"]},
            {"path": "b.py", "depends_on": ["c.py"]},
            {"path": "c.py", "depends_on": ["a.py"]},
        ]
        order, error = topological_sort(files)
        self.assertIsNotNone(error)
        self.assertIn("Circular", error)

    def test_missing_dependency_external(self):
        files = [
            {"path": "a.py", "depends_on": ["external_lib"]},
            {"path": "b.py", "depends_on": ["a.py"]},
        ]
        order, error = topological_sort(files)
        self.assertIsNone(error)
        self.assertEqual(order, ["a.py", "b.py"])

    def test_diamond_dependency(self):
        files = [
            {"path": "a.py", "depends_on": []},
            {"path": "b.py", "depends_on": ["a.py"]},
            {"path": "c.py", "depends_on": ["a.py"]},
            {"path": "d.py", "depends_on": ["b.py", "c.py"]},
        ]
        order, error = topological_sort(files)
        self.assertIsNone(error)
        # a must be first, d must be last
        self.assertEqual(order[0], "a.py")
        self.assertEqual(order[-1], "d.py")


class TestUnitTruncation(unittest.TestCase):
    def test_valid_python(self):
        content = "def hello():\n    return 'world'\n"
        warnings = detect_unit_truncation(content)
        self.assertEqual(warnings, [])

    def test_empty_content(self):
        content = ""
        warnings = detect_unit_truncation(content)
        self.assertIn("Empty content", warnings)

    def test_unbalanced_brackets(self):
        content = "{\n    \"key\": {\n        \"nested\": 1\n"
        warnings = detect_unit_truncation(content)
        self.assertTrue(any("bracket" in w.lower() for w in warnings))

    def test_abrupt_ending(self):
        content = "def func():\n    return 'hello"
        warnings = detect_unit_truncation(content)
        self.assertTrue(any("abrupt" in w.lower() for w in warnings))

    def test_unclosed_fence(self):
        content = "```\ndef hello():\n    pass"
        warnings = detect_unit_truncation(content)
        self.assertTrue(any("fence" in w.lower() for w in warnings))


class TestSyntaxValidation(unittest.TestCase):
    def test_valid_python(self):
        content = "def hello():\n    return 'world'\n"
        error = validate_syntax("test.py", content)
        self.assertIsNone(error)

    def test_invalid_syntax(self):
        content = "def hello(\n    return 'world'\n"
        error = validate_syntax("test.py", content)
        self.assertIsNotNone(error)
        self.assertIn("SyntaxError", error)

    def test_non_python_skips(self):
        content = "console.log('hello')"
        error = validate_syntax("test.js", content)
        self.assertIsNone(error)


class TestDeveloperAgentChunked(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.create_project("p1", "Test", "brief", "/tmp/output")
        self.mock_llm = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_developer_chunked_calls_llm_per_file(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/nonexistent", config={})
        
        # Mock planner to return a plan
        mock_plan = AgentResult(
            success=True,
            output={
                "project_summary": "Test app",
                "tech_stack": "Python",
                "files": [
                    {"path": "a.py", "purpose": "main", "exports": ["main"], "depends_on": []},
                    {"path": "b.py", "purpose": "util", "exports": ["util"], "depends_on": ["a.py"]},
                ],
                "generation_order": ["a.py", "b.py"],
            },
            files=["docs/implementation_plan.json"]
        )
        agent.planner.plan = MagicMock(return_value=mock_plan)
        
        # Mock LLM to return valid JSON responses
        self.mock_llm.chat.side_effect = [
            '{"path": "a.py", "content": "def main():\\n    pass\\n", "summary": "main entry"}',
            '{"path": "b.py", "content": "def util():\\n    pass\\n", "summary": "util function"}',
        ]
        
        result = agent.implement()
        self.assertTrue(result.success)
        self.assertEqual(len(result.files), 2)
        self.assertEqual(self.mock_llm.chat.call_count, 2)  # Called once per file

    def test_developer_resume_skips_done(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/output", config={})
        
        # Mark a.py as already done
        agent.db.create_dev_unit("p1", "a.py", purpose="main", exports=["main"])
        agent.db.update_dev_unit_status(1, "DONE")
        
        mock_plan = AgentResult(
            success=True,
            output={
                "project_summary": "Test app",
                "tech_stack": "Python",
                "files": [
                    {"path": "a.py", "purpose": "main", "exports": ["main"], "depends_on": []},
                    {"path": "b.py", "purpose": "util", "exports": ["util"], "depends_on": ["a.py"]},
                ],
                "generation_order": ["a.py", "b.py"],
            },
            files=["docs/implementation_plan.json"]
        )
        agent.planner.plan = MagicMock(return_value=mock_plan)
        
        self.mock_llm.chat.return_value = '{"path": "b.py", "content": "def util():\\n    pass\\n", "summary": "util function"}'
        
        result = agent.implement()
        self.assertTrue(result.success)
        self.assertEqual(self.mock_llm.chat.call_count, 1)  # Only called for b.py

    def test_developer_unit_retry_on_syntax_error(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/output", config={})
        
        mock_plan = AgentResult(
            success=True,
            output={
                "project_summary": "Test app",
                "tech_stack": "Python",
                "files": [
                    {"path": "a.py", "purpose": "main", "exports": ["main"], "depends_on": []},
                ],
                "generation_order": ["a.py"],
            },
            files=["docs/implementation_plan.json"]
        )
        agent.planner.plan = MagicMock(return_value=mock_plan)
        
        # First call returns invalid syntax, second returns valid
        self.mock_llm.chat.side_effect = [
            '{"path": "a.py", "content": "def main(\\n    pass\\n", "summary": "bad syntax"}',
            '{"path": "a.py", "content": "def main():\\n    pass\\n", "summary": "fixed"}',
        ]
        
        result = agent.implement()
        self.assertTrue(result.success)
        self.assertEqual(self.mock_llm.chat.call_count, 2)  # Retried once

    def test_unit_retry_limit_exhausted(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/output", config={"developer": {"unit_max_retries": 2}})

        mock_plan = AgentResult(
            success=True,
            output={
                "project_summary": "Test app",
                "tech_stack": "Python",
                "files": [
                    {"path": "a.py", "purpose": "main", "exports": ["main"], "depends_on": []},
                ],
                "generation_order": ["a.py"],
            },
            files=["docs/implementation_plan.json"],
        )
        agent.planner.plan = MagicMock(return_value=mock_plan)

        # Both attempts fail with syntax error
        self.mock_llm.chat.side_effect = [
            '{"path": "a.py", "content": "def main(\\n", "summary": "bad 1"}',
            '{"path": "a.py", "content": "def main(\\n", "summary": "bad 2"}',
        ]

        result = agent.implement()
        self.assertFalse(result.success)
        self.assertIn("Syntax error in a.py", result.error)
        self.assertEqual(self.mock_llm.chat.call_count, 2)

    def test_context_dependency_interfaces_passed(self):
        from agents.developer import DeveloperAgent
        agent = DeveloperAgent(self.mock_llm, self.db, "p1", "/tmp/output", config={})
        plan = {
            "project_summary": "Test app",
            "tech_stack": "Python",
            "files": [
                {"path": "db.py", "purpose": "database layer", "exports": ["Database", "connect"], "depends_on": []},
                {"path": "models.py", "purpose": "data models", "exports": ["User"], "depends_on": ["db.py"]},
            ],
        }
        unit_spec = plan["files"][1]
        context = agent._build_unit_context(plan, unit_spec, ["db.py"])
        self.assertIn("db.py", context)
        self.assertIn("Database, connect", context)
        self.assertIn("database layer", context)

    def test_fix_cycle_touches_only_relevant_unit(self):
        from agents.developer import DeveloperAgent
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = DeveloperAgent(self.mock_llm, self.db, "p1", tmpdir, config={})
            # Pre-create app.py and db.py
            Path(tmpdir, "app.py").write_text("print('app')", encoding="utf-8")
            Path(tmpdir, "db.py").write_text("print('old db')", encoding="utf-8")

            mock_plan = AgentResult(
                success=True,
                output={
                    "project_summary": "Test app",
                    "tech_stack": "Python",
                    "files": [
                        {"path": "app.py", "purpose": "app entry", "exports": [], "depends_on": []},
                        {"path": "db.py", "purpose": "database", "exports": ["connect"], "depends_on": []},
                    ],
                    "generation_order": ["db.py", "app.py"],
                },
                files=["docs/implementation_plan.json"],
            )
            agent.planner.plan = MagicMock(return_value=mock_plan)
            self.mock_llm.chat.return_value = '{"path": "db.py", "content": "print(\'new db\')\\n", "summary": "fixed db"}'

            fix_context = 'QA FAIL.\nBugs:\n[{"file": "db.py", "description": "fix connect bug"}]'
            result = agent.implement(fix_context=fix_context)

            self.assertTrue(result.success)
            # Only db.py was regenerated
            self.assertEqual(self.mock_llm.chat.call_count, 1)
            self.assertEqual(Path(tmpdir, "db.py").read_text(encoding="utf-8"), "print('new db')\n")
            self.assertEqual(Path(tmpdir, "app.py").read_text(encoding="utf-8"), "print('app')")


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.create_project("p1", "Test", "brief", "/tmp/output")
        self.mock_llm = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_planner_validates_output(self):
        from agents.planner import Planner
        from agents.base import Agent
        
        class TestAgent(Agent):
            role = "test"
            system_prompt = "test"
        
        agent = TestAgent(self.mock_llm, self.db, "p1", "/tmp/output")
        planner = Planner(agent)
        
        # Invalid: not a dict
        self.mock_llm.chat.return_value = "not a dict"
        result = planner.plan()
        self.assertFalse(result.success)
        self.assertIn("dict", result.error)

    def test_planner_validates_no_files(self):
        from agents.planner import Planner
        from agents.base import Agent
        
        class TestAgent(Agent):
            role = "test"
            system_prompt = "test"
        
        agent = TestAgent(self.mock_llm, self.db, "p1", "/tmp/output")
        planner = Planner(agent)
        
        self.mock_llm.chat.return_value = {"project_summary": "x", "files": []}
        result = planner.plan()
        self.assertFalse(result.success)
        self.assertIn("0 files", result.error)

    def test_planner_validates_missing_path(self):
        from agents.planner import Planner
        from agents.base import Agent
        
        class TestAgent(Agent):
            role = "test"
            system_prompt = "test"
        
        agent = TestAgent(self.mock_llm, self.db, "p1", "/tmp/output")
        planner = Planner(agent)
        
        self.mock_llm.chat.return_value = {"project_summary": "x", "files": [{"purpose": "y"}]}
        result = planner.plan()
        self.assertFalse(result.success)
        self.assertIn("path", result.error)

    def test_planner_circular_dependency(self):
        from agents.planner import Planner
        from agents.base import Agent
        
        class TestAgent(Agent):
            role = "test"
            system_prompt = "test"
        
        agent = TestAgent(self.mock_llm, self.db, "p1", "/tmp/output")
        planner = Planner(agent)
        
        self.mock_llm.chat.return_value = {
            "project_summary": "x",
            "files": [
                {"path": "a.py", "depends_on": ["b.py"]},
                {"path": "b.py", "depends_on": ["a.py"]},
            ],
        }
        result = planner.plan()
        self.assertFalse(result.success)
        self.assertIn("Circular", result.error)


class TestDevUnitsDB(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_create_and_get_dev_unit(self):
        uid = self.db.create_dev_unit("p1", "test.py", "purpose", ["main"])
        self.assertEqual(uid, 1)
        unit = self.db.get_dev_unit(uid)
        self.assertEqual(unit["path"], "test.py")
        self.assertEqual(unit["purpose"], "purpose")
        self.assertEqual(json.loads(unit["exports"]), ["main"])
        self.assertEqual(unit["status"], "PENDING")

    def test_get_dev_units_by_status(self):
        self.db.create_dev_unit("p1", "a.py")
        self.db.create_dev_unit("p1", "b.py")
        self.db.create_dev_unit("p1", "c.py")
        self.db.update_dev_unit_status(1, "DONE")
        self.db.update_dev_unit_status(2, "FAILED", error="error")
        
        done = self.db.get_dev_units("p1", "DONE")
        failed = self.db.get_dev_units("p1", "FAILED")
        pending = self.db.get_dev_units("p1", "PENDING")
        
        self.assertEqual(len(done), 1)
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(pending), 1)

    def test_update_dev_unit_status_with_attempt(self):
        uid = self.db.create_dev_unit("p1", "test.py")
        self.db.update_dev_unit_status(uid, "RUNNING", attempt=1)
        unit = self.db.get_dev_unit(uid)
        self.assertEqual(unit["attempt"], 1)
        self.assertEqual(unit["status"], "RUNNING")


class TestIntegrationSimulation(unittest.TestCase):
    """Full integration simulation with mocked LLM."""
    
    @patch("orchestrator.LLMClient")
    def test_3_file_project_success(self, MockLLM):
        """Simulate 3-file project: planner → 3 units → QA PASS"""
        import tempfile
        from orchestrator import Orchestrator
        
        config = {
            "llm": {"endpoint": "http://x", "api_key": "k", "model": "m"},
            "developer": {"unit_max_retries": 2},
            "qa": {"max_retries": 0},
        }
        
        mock_llm = MockLLM.return_value
        
        # Sequence of LLM calls:
        # 1. PM - create project
        # 2. Conceptor - requirements
        # 3. Planner - implementation plan (3 files)
        # 4. Developer - a.py
        # 5. Developer - b.py
        # 6. Developer - c.py
        # 7. QA - test (PASS)
        
        call_sequence = [
            # PM
            {"project_name": "Test", "tasks": [{"title": "Task 1", "priority": 3}]},
            # Conceptor
            "# Requirements\nAll good\n\n## Acceptance Criteria\n1. Works",
            # Planner (JSON mode)
            {
                "project_summary": "Test app",
                "tech_stack": "Python",
                "files": [
                    {"path": "a.py", "purpose": "main", "exports": ["main"], "depends_on": []},
                    {"path": "b.py", "purpose": "util", "exports": ["util"], "depends_on": ["a.py"]},
                    {"path": "c.py", "purpose": "test", "exports": ["test"], "depends_on": ["b.py"]},
                ],
            },
            # Developer units (text mode)
            '{"path": "a.py", "content": "def main():\\n    pass\\n", "summary": "main"}',
            '{"path": "b.py", "content": "def util():\\n    pass\\n", "summary": "util"}',
            '{"path": "c.py", "content": "def test():\\n    pass\\n", "summary": "test"}',
            # QA (JSON mode)
            {
                "verdict": "PASS",
                "summary": "All good",
                "criteria_results": [],
                "bugs_found": [],
                "test_commands_to_run": [],
            },
        ]
        
        mock_llm.chat.side_effect = call_sequence
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(config, "test-3file", tmpdir)
            result = orch.run("Test project brief")
            
            self.assertTrue(result["success"])
            self.assertEqual(len(result["phases"]), 4)  # PM, Conceptor, Developer, QA
            # Verify dev units created
            units = orch.db.get_dev_units("test-3file")
            self.assertEqual(len(units), 3)
            for u in units:
                self.assertEqual(u["status"], "DONE")

    @patch("orchestrator.LLMClient")
    def test_unit_failure_stops_pipeline(self, MockLLM):
        """If one unit fails, pipeline stops gracefully."""
        import tempfile
        from orchestrator import Orchestrator
        
        config = {
            "llm": {"endpoint": "http://x", "api_key": "k", "model": "m"},
            "developer": {"unit_max_retries": 1},
            "qa": {"max_retries": 0},
        }
        
        mock_llm = MockLLM.return_value
        
        call_sequence = [
            # PM
            {"project_name": "Test", "tasks": [{"title": "Task 1", "priority": 3}]},
            # Conceptor
            "# Requirements",
            # Planner
            {
                "project_summary": "Test app",
                "tech_stack": "Python",
                "files": [
                    {"path": "a.py", "purpose": "main", "exports": ["main"], "depends_on": []},
                    {"path": "b.py", "purpose": "util", "exports": ["util"], "depends_on": ["a.py"]},
                ],
            },
            # Developer - a.py succeeds
            '{"path": "a.py", "content": "def main():\\n    pass\\n", "summary": "main"}',
            # Developer - b.py fails (syntax error)
            '{"path": "b.py", "content": "def util(\\n    pass\\n", "summary": "bad"}',
            # Retry - still fails
            '{"path": "b.py", "content": "def util(\\n    pass\\n", "summary": "bad"}',
        ]
        
        mock_llm.chat.side_effect = call_sequence
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(config, "test-fail", tmpdir)
            result = orch.run("Test project brief")
            
            self.assertFalse(result["success"])
            self.assertIn("b.py", result.get("error", ""))
            # Only a.py should be done
            units = orch.db.get_dev_units("test-fail")
            done = [u for u in units if u["status"] == "DONE"]
            self.assertEqual(len(done), 1)
            self.assertEqual(done[0]["path"], "a.py")

    @patch("orchestrator.LLMClient")
    def test_3_file_project_retry_then_success(self, MockLLM):
        """Simulate 3-file project where file 2 fails first attempt, retries, succeeds, then QA PASS."""
        import tempfile
        from orchestrator import Orchestrator

        config = {
            "llm": {"endpoint": "http://x", "api_key": "k", "model": "m"},
            "developer": {"unit_max_retries": 2},
            "qa": {"max_retries": 0},
        }

        mock_llm = MockLLM.return_value

        call_sequence = [
            # PM
            {"project_name": "Test", "tasks": [{"title": "Task 1", "priority": 3}]},
            # Conceptor
            "# Requirements\nAll good\n\n## Acceptance Criteria\n1. Works",
            # Planner
            {
                "project_summary": "Test app",
                "tech_stack": "Python",
                "files": [
                    {"path": "a.py", "purpose": "main", "exports": ["main"], "depends_on": []},
                    {"path": "b.py", "purpose": "util", "exports": ["util"], "depends_on": ["a.py"]},
                    {"path": "c.py", "purpose": "test", "exports": ["test"], "depends_on": ["b.py"]},
                ],
            },
            # Developer - a.py succeeds
            '{"path": "a.py", "content": "def main():\\n    pass\\n", "summary": "main"}',
            # Developer - b.py fails syntax error on attempt 1
            '{"path": "b.py", "content": "def util(\\n", "summary": "bad syntax"}',
            # Developer - b.py retry succeeds on attempt 2
            '{"path": "b.py", "content": "def util():\\n    pass\\n", "summary": "fixed util"}',
            # Developer - c.py succeeds
            '{"path": "c.py", "content": "def test():\\n    pass\\n", "summary": "test"}',
            # QA PASS
            {
                "verdict": "PASS",
                "summary": "All tests pass",
                "criteria_results": [],
                "bugs_found": [],
                "test_commands_to_run": [],
            },
        ]

        mock_llm.chat.side_effect = call_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            orch = Orchestrator(config, "test-retry-success", tmpdir)
            result = orch.run("Test project brief")

            self.assertTrue(result["success"])
            units = orch.db.get_dev_units("test-retry-success")
            self.assertEqual(len(units), 3)
            for u in units:
                self.assertEqual(u["status"], "DONE")
            b_unit = next(u for u in units if u["path"] == "b.py")
            self.assertEqual(b_unit["attempt"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

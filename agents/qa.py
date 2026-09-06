"""QA agent — tests implementation via LLM review + actual test commands."""

from __future__ import annotations
import json
import subprocess
import logging
from pathlib import Path
from .base import Agent
from result import AgentResult
from llm import LLMError

logger = logging.getLogger("aether.agent.qa")

# Test error categories
TEST_FAIL = "test_fail"           # Assertion failed, exit non-zero
RUNNER_FAIL = "runner_fail"       # Test runner crashed / not found
COMMAND_NOT_FOUND = "command_not_found"
TIMEOUT = "timeout"
APP_CRASH = "app_crash"
UNKNOWN = "unknown"


def categorize_test_error(cmd: str, exit_code: int, stderr: str) -> str:
    """Categorize test execution error."""
    if exit_code == -1 and "timed out" in stderr.lower():
        return TIMEOUT
    if exit_code == -1 and ("not found" in stderr.lower() or "No such file" in stderr):
        return COMMAND_NOT_FOUND
    if exit_code == -1:
        return APP_CRASH
    if exit_code == 127:
        return COMMAND_NOT_FOUND
    if exit_code != 0:
        # Check stderr for runner-specific errors
        if any(x in stderr.lower() for x in ("importerror", "modulenotfounderror", "no module named")):
            return RUNNER_FAIL
        if any(x in stderr.lower() for x in ("syntaxerror", "indentationerror", "nameerror")):
            return APP_CRASH
        return TEST_FAIL
    return TEST_FAIL


def validate_qa_response(data: dict) -> list[str]:
    """Validate QA JSON response. Returns list of errors."""
    errors = []
    if not isinstance(data, dict):
        return ["QA response is not a dict"]

    verdict = data.get("verdict")
    if verdict not in ("PASS", "FAIL"):
        errors.append(f"Invalid verdict: {verdict}")

    if "summary" not in data:
        errors.append("Missing 'summary' field")

    criteria = data.get("criteria_results")
    if criteria is not None and not isinstance(criteria, list):
        errors.append(f"criteria_results should be list, got {type(criteria).__name__}")

    bugs = data.get("bugs_found")
    if bugs is not None and not isinstance(bugs, list):
        errors.append(f"bugs_found should be list, got {type(bugs).__name__}")

    return errors


class QAAgent(Agent):
    role = "qa"
    system_prompt = """You are a Lead QA Automation & Security Engineer.
Your job is to conduct a meticulous, production-grade verification of the codebase against project requirements and acceptance criteria.

Audit & Verification Standards:
1. Syntax & Import Integrity:
   - Verify that all files have valid syntax and import paths.
   - Verify that internal cross-file imports accurately match the exported classes/functions from dependencies.
2. Completeness & Quality:
   - Flag any unfinished functions, TODOs, or placeholder implementations.
   - Verify that all core functional workflows described in the requirements are actually implemented.
3. Security & Robustness:
   - Verify SQL queries use parameterization (`?` placeholders) to prevent SQL injection.
   - Verify resource management (connections and file handles properly opened and closed via context managers).
   - Verify defensive input validation and exception handling.
4. Non-Interactive Test Commands:
   - In `test_commands_to_run`, provide ONLY automated, non-interactive checks that run and exit immediately (e.g., `python -m compileall . -q`).
   - CRITICAL: NEVER include commands that launch interactive desktop GUIs (like `python main.py` for Tkinter/PyQt apps) or wait for manual user input, as they will hang headless execution.

Output Format:
Output ONLY valid JSON with this exact structure:
{
    "verdict": "PASS" or "FAIL",
    "summary": "Detailed technical assessment of code quality, architecture compliance, and testability",
    "criteria_results": [
        {
            "criterion": "Requirement or criterion statement",
            "status": "PASS" or "FAIL",
            "evidence": "Concrete code reference or rationale",
            "severity": "critical" or "major" or "minor"
        }
    ],
    "bugs_found": [
        {
            "title": "Clear bug title",
            "description": "Technical root cause and impact",
            "file": "relative/path/to/file.ext",
            "fix_suggestion": "Precise, actionable code fix"
        }
    ],
    "test_commands_to_run": ["python -m compileall . -q"],
    "fix_instructions": "Direct architectural and code instructions for the developer if verdict is FAIL"
}

Rules:
- Be strict: PASS only if code is syntactically sound, fully implemented, secure, and meets acceptance criteria.
- Output ONLY the raw JSON object, no explanation or chatter outside JSON."""

    def test(self) -> AgentResult:
        """Run full QA cycle: LLM review + test commands."""
        self._log("agent.started", {})
        self.set_state("TESTING", {"action": "evaluating_code_and_requirements"})

        # Phase 1: Gather all context
        docs = self._read_docs()
        code_files = self._read_all_code()
        task_list = self.db.get_tasks(self.project_id)

        if code_files == "(no code files found)":
            self.set_state("FAILED", {"error": "No code files found"})
            self._log("agent.failed", {"error": "No code files found"})
            return AgentResult(success=False, error="No code files found to test")

        # Phase 2: LLM review
        try:
            review_result = self._llm_review(docs, code_files, task_list)
        except LLMError as e:
            self.set_state("FAILED", {"error": str(e)})
            self._log("agent.failed", {"error": str(e)})
            return AgentResult(success=False, error=f"QA LLM review failed: {e}")

        # Validate QA response
        if not isinstance(review_result, dict):
            self.set_state("FAILED", {"reason": "non_dict_qa_response"})
            self._log("validation_failed", {"reason": f"Expected dict, got {type(review_result).__name__}"})
            return AgentResult(success=False, error=f"QA returned {type(review_result).__name__}, expected dict")

        validation_errors = validate_qa_response(review_result)
        if validation_errors:
            self._log("validation_failed", {"errors": validation_errors})
            # If verdict missing, default to FAIL
            if "verdict" not in review_result or review_result.get("verdict") not in ("PASS", "FAIL"):
                review_result["verdict"] = "FAIL"
                review_result["summary"] = f"QA validation failed: {'; '.join(validation_errors)}"

        # Phase 3: Run test commands if available
        test_results = {}
        test_error_types = set()
        commands = review_result.get("test_commands_to_run", [])
        if commands:
            test_results = self._run_tests(commands)
            for cmd, r in test_results.items():
                if cmd == "any_failed":
                    continue
                if isinstance(r, dict) and not r.get("passed"):
                    cat = categorize_test_error(cmd, r.get("exit_code", -1), r.get("stderr", ""))
                    test_error_types.add(cat)
                    r["error_category"] = cat

        # Phase 4: Combine results
        verdict = review_result.get("verdict", "FAIL")
        if verdict == "PASS" and test_results.get("any_failed"):
            verdict = "FAIL"
            review_result["verdict"] = "FAIL"
            summary = review_result.get("summary", "")
            review_result["summary"] = f"{summary} (automated tests failed)"

        # Phase 5: Log results
        self._log("qa.completed", {
            "verdict": verdict,
            "bugs_count": len(review_result.get("bugs_found", [])),
            "criteria_count": len(review_result.get("criteria_results", [])),
            "test_error_types": list(test_error_types),
        })

        if verdict == "PASS":
            self.set_state("COMPLETED", {"verdict": "PASS"})
        else:
            self.set_state("FAILED", {
                "verdict": "FAIL",
                "bugs_count": len(review_result.get("bugs_found", [])),
            })

        # Phase 6: Update tasks
        for t in task_list:
            if t["status"] in ("REVIEW", "QA"):
                new_status = "DONE" if verdict == "PASS" else "FAILED"
                self.db.update_task_status(t["id"], new_status,
                                           result=json.dumps(review_result))

        # Phase 7: Write test report
        self._write_test_report(review_result, test_results)

        review_result["test_results"] = test_results
        return AgentResult(
            success=True,
            output=review_result,
            files=["docs/qa_report.md"],
        )

    def _llm_review(self, docs: str, code_files: str, tasks: list[dict]) -> dict:
        """LLM-based code review."""
        tasks_text = "\n".join(
            f"- {t['title']}: {t['description']} (status: {t['status']})"
            for t in tasks
        )

        user_msg = (
            f"## Requirements\n{docs}\n\n"
            f"## Tasks\n{tasks_text}\n\n"
            f"## Code\n{code_files}\n\n"
            f"Review the code against requirements. Output JSON verdict."
        )
        result = self.llm.chat(self.system_prompt, user_msg, json_mode=True)
        if isinstance(result, str):
            import re
            cleaned = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()
            fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned)
            if fence_match:
                try:
                    result = json.loads(fence_match.group(1).strip())
                except Exception:
                    pass
            if not isinstance(result, dict):
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end > start:
                    try:
                        result = json.loads(cleaned[start:end+1])
                    except Exception:
                        pass
        return result

    def _run_tests(self, commands: list[str]) -> dict:
        """Execute test commands safely and capture output."""
        self._log("test_started", {"commands": commands})
        results = {}

        # Safeguard against commands that launch blocking interactive GUI loops
        filtered_commands = []
        for cmd in commands:
            cmd_clean = cmd.strip()
            if any(cmd_clean == f"python {entry}" or cmd_clean == f"python3 {entry}" for entry in ["main.py", "app.py", "gui.py", "run.py"]):
                filtered_commands.append("python -m compileall . -q")
            else:
                filtered_commands.append(cmd)

        for cmd in filtered_commands:
            try:
                proc = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=120, cwd=str(self.output_dir),
                )
                results[cmd] = {
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[-5000:] if proc.stdout else "",
                    "stderr": proc.stderr[-2000:] if proc.stderr else "",
                    "passed": proc.returncode == 0,
                }
                if proc.returncode == 0:
                    self._log("test_passed", {"command": cmd})
                else:
                    cat = categorize_test_error(cmd, proc.returncode, proc.stderr)
                    results[cmd]["error_category"] = cat
                    self._log("test_failed", {"command": cmd, "exit_code": proc.returncode, "category": cat})

            except subprocess.TimeoutExpired:
                results[cmd] = {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Command timed out after 120s",
                    "passed": False,
                    "error_category": TIMEOUT,
                }
                self._log("test_failed", {"command": cmd, "category": TIMEOUT})
            except Exception as e:
                results[cmd] = {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "passed": False,
                    "error_category": APP_CRASH,
                }
                self._log("test_failed", {"command": cmd, "category": APP_CRASH, "error": str(e)})

        results["any_failed"] = any(
            not r["passed"] for r in results.values()
            if isinstance(r, dict) and "passed" in r
        )
        return results

    def _read_all_code(self) -> str:
        """Read all code files from project output."""
        parts = []
        code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
                      ".json", ".yaml", ".yml", ".toml", ".sql", ".sh"}

        for f in sorted(self.output_dir.rglob("*")):
            if f.is_file() and f.suffix in code_exts and "docs" not in str(f):
                try:
                    content = f.read_text(encoding="utf-8")
                    rel = f.relative_to(self.output_dir)
                    parts.append(f"### {rel}\n```\n{content}\n```")
                except (UnicodeDecodeError, PermissionError):
                    pass

        return "\n\n".join(parts) if parts else "(no code files found)"

    def _write_test_report(self, review: dict, test_results: dict):
        """Write QA report to docs."""
        report = f"# QA Report\n\n## Verdict: {review.get('verdict', 'UNKNOWN')}\n\n## Summary\n{review.get('summary', 'N/A')}\n\n"
        report += "## Criteria Results\n\n"
        for c in review.get("criteria_results", []):
            if not isinstance(c, dict):
                continue
            icon = "✅" if c.get("status") == "PASS" else "❌"
            report += f"- {icon} **{c.get('criterion', '?')}**: {c.get('status', '?')} — {c.get('evidence', '')}\n"
        if review.get("bugs_found"):
            report += "\n## Bugs Found\n\n"
            for b in review["bugs_found"]:
                if not isinstance(b, dict):
                    continue
                report += f"- **{b.get('title', '?')}** ({b.get('file', 'N/A')}): {b.get('description', '')}\n  Fix: {b.get('fix_suggestion', 'N/A')}\n"
        if test_results:
            report += "\n## Test Command Results\n\n"
            for cmd, r in test_results.items():
                if cmd == "any_failed" or not isinstance(r, dict):
                    continue
                icon = "✅" if r.get("passed") else "❌"
                cat = r.get("error_category", "")
                cat_label = f" [{cat}]" if cat else ""
                report += f"- {icon} `{cmd}` (exit {r.get('exit_code', '?')}){cat_label}\n"
                if r.get("stderr"):
                    report += f"  stderr: {r['stderr'][:500]}\n"

        self._write_doc("qa_report.md", report)

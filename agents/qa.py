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
    system_prompt = """You are a QA Engineer. Your job:
1. Review the code against acceptance criteria
2. Find bugs, missing features, edge cases
3. Output structured test results

## Input
You'll receive:
- Requirements + acceptance criteria
- Code files
- Test results (if available)

## Output Format

Output VALID JSON with this structure:
{
    "verdict": "PASS" or "FAIL",
    "summary": "overall assessment",
    "criteria_results": [
        {
            "criterion": "criterion text",
            "status": "PASS" or "FAIL",
            "evidence": "why",
            "severity": "critical" or "major" or "minor" (for failures)
        }
    ],
    "bugs_found": [
        {
            "title": "bug title",
            "description": "what's wrong",
            "file": "file path",
            "fix_suggestion": "how to fix"
        }
    ],
    "test_commands_to_run": ["command1", "command2"],
    "fix_instructions": "instructions for developer if FAIL"
}

Rules:
- Be strict — only PASS if criterion is fully met
- Each bug must have a clear fix suggestion
- test_commands_to_run should be actual runnable commands
- fix_instructions must be specific enough for developer to act on
- Output ONLY the JSON object"""

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
        return self.llm.chat(self.system_prompt, user_msg, json_mode=True)

    def _run_tests(self, commands: list[str]) -> dict:
        """Execute test commands and capture output."""
        self._log("test_started", {"commands": commands})
        results = {}

        for cmd in commands:
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

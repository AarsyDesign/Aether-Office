"""Developer agent — chunked file-by-file generation with validation."""

from __future__ import annotations
import json
import re
import ast
import logging
from pathlib import Path
from typing import Optional
from events import EventBus
from .base import Agent
from .planner import Planner
from result import AgentResult
from llm import LLMError

logger = logging.getLogger("aether.agent.developer")

UNIT_PROMPT = """You are a Principal Software Engineer. Your task is to generate the complete, production-ready implementation of ONE specific file for this project.

## Project Summary
{summary}

## Tech Stack
{tech_stack}

## Target File Specification
Path: {path}
Purpose: {purpose}

## Dependency Interfaces (Internal & External)
{dep_interfaces}

## Requirements & Acceptance Criteria (Excerpt)
{requirements}

## Instructions & Quality Standards:
1. Write COMPLETE, functional, production-quality code.
2. Absolutely NO placeholders, NO TODOs, and NO partial snippets.
3. Include all required imports, class definitions, function implementations, and robust error handling.
4. Integrate cleanly with the declared dependency interfaces above.
5. Format your output cleanly in a markdown code fence for this file (e.g. ```python ... ```) OR as a JSON object with "path" and "content" fields.
"""


def validate_syntax(filepath: str, content: str) -> str | None:
    """Validate Python syntax. Returns error message or None if valid."""
    if not filepath.endswith(".py"):
        return None
    try:
        ast.parse(content, filename=filepath)
        return None
    except SyntaxError as e:
        return f"SyntaxError in {filepath}: {e}"
    except Exception as e:
        return f"SyntaxError in {filepath}: {e}"


def detect_truncation(output: str) -> list[str]:
    """Detect truncation in full/legacy generation output."""
    warnings = []
    if not output or not output.strip():
        warnings.append("Empty output")
        return warnings

    if output.count("```") % 2 != 0:
        warnings.append("Unclosed code fence detected")

    if output.count("{") != output.count("}"):
        warnings.append("Unbalanced braces detected in output")

    stripped = output.strip()
    if not stripped.endswith(("```", "\n", "}", "]", ")", "'", '"', ";", "#")):
        warnings.append("Content appears to end abruptly")

    if "### CONFIG" in output and not stripped.endswith("```"):
        warnings.append("Incomplete CONFIG block detected")

    return warnings


def detect_unit_truncation(content: str, filepath: str = "") -> list[str]:
    """Detect actual truncation in a single file's content."""
    warnings = []
    if not content or not content.strip():
        warnings.append("Empty content")
        return warnings

    # Unclosed code fences inside content
    fence_count = content.count("```")
    if fence_count % 2 != 0:
        warnings.append("Unclosed code fence inside content")

    # If it's a Python file and ast parses cleanly, it's structurally complete
    if filepath.endswith(".py") or not filepath:
        try:
            ast.parse(content, filename=filepath or "unit.py")
            return warnings
        except SyntaxError:
            pass

    # Unclosed brackets
    opens = content.count("{") + content.count("(") + content.count("[")
    closes = content.count("}") + content.count(")") + content.count("]")
    if opens - closes > 2:
        warnings.append(f"Unbalanced brackets ({opens} open, {closes} close)")

    stripped = content.strip()
    if stripped.endswith(("(", "[", "{", "=", "+", "-", "*", "/", "\\", "def", "class", "import", "from")):
        warnings.append("Content ends abruptly on incomplete token")

    return warnings


class DeveloperAgent(Agent):
    role = "developer"

    def __init__(self, llm, db, project_id, output_dir, config: dict = None,
                 agent_id: Optional[str] = None, event_bus: Optional[EventBus] = None):
        super().__init__(llm, db, project_id, output_dir, agent_id=agent_id, event_bus=event_bus)
        self.config = config or {}
        self.unit_max_retries = self.config.get("developer", {}).get("unit_max_retries", 3)
        self.planner = Planner(self)

    def implement(self, fix_context: str = None) -> AgentResult:
        """Full chunked implementation: plan → generate each unit → validate."""
        self._log("agent.started", {"fix_mode": fix_context is not None})
        self.set_state("PLANNING", {"fix_mode": fix_context is not None})

        # Determine fix files if in fix mode
        fix_files = None
        if fix_context:
            fix_files = self._parse_fix_files(fix_context)

        # Phase 1: Plan
        print("\n[DEVELOPER] Planning implementation...")
        plan_result = self.planner.plan(fix_files=fix_files)
        if not plan_result.success:
            # Check for legacy single-response mock format containing "### FILE:"
            last_raw = getattr(self.planner, "last_raw_response", None)
            if isinstance(last_raw, str) and ("### FILE:" in last_raw or "### FILE" in last_raw):
                return self._implement_legacy(last_raw)
            self.set_state("FAILED", {"error": plan_result.error})
            return plan_result

        plan = plan_result.output
        files = plan.get("files", [])
        order = plan.get("generation_order", [f["path"] for f in files])

        print(f"[DEVELOPER] {len(order)} units identified\n")
        self._log("developer_generation_started", {"unit_count": len(order)})
        self.set_state("WORKING", {"unit_count": len(order)})

        # Phase 2: Generate each unit
        generated_files = []
        failed_unit = None

        for i, path in enumerate(order):
            # If in fix mode and this file not in fix list:
            if fix_files and path not in fix_files:
                if (self.output_dir / path).exists():
                    generated_files.append(path)
                    continue
                continue

            unit_spec = next((f for f in files if f["path"] == path), None)
            if not unit_spec:
                continue

            # Check if already generated (resume capability)
            unit_row = self.db.get_dev_unit_by_path(self.project_id, path)
            if unit_row and unit_row["status"] == "DONE":
                generated_files.append(path)
                continue

            print(f"[{i+1}/{len(order)}] {path}")
            print("      generating...")
            self.set_state("WORKING", {"unit": path, "progress": f"{i+1}/{len(order)}"})

            # Build compact context for this unit
            context = self._build_unit_context(plan, unit_spec, generated_files)

            # Generate with unit-level retry
            unit_result = self._generate_unit_with_retry(unit_spec, context)

            if unit_result.success:
                generated_files.append(path)
            else:
                failed_unit = {"path": path, "error": unit_result.error}
                break  # Stop on failure

        # Phase 3: Finalize
        if failed_unit:
            self.set_state("FAILED", {"failed_unit": failed_unit["path"], "error": failed_unit["error"]})
            self._log("developer_generation_failed", {
                "failed_unit": failed_unit["path"],
                "completed": len(generated_files),
                "total": len(order),
            })
            return AgentResult(
                success=False,
                error=f"Failed on {failed_unit['path']}: {failed_unit['error']}",
                files=generated_files,
            )

        # Mark all project tasks DONE
        task_list = self.db.get_tasks(self.project_id)
        for t in task_list:
            if t["status"] in ("READY", "IN_PROGRESS"):
                self.db.update_task_status(t["id"], "DONE")

        self.set_state("COMPLETED", {"files_written": len(generated_files)})
        self._log("developer_generation_completed", {
            "files_written": len(generated_files),
            "fix_mode": fix_context is not None,
        })
        print("\nDeveloper complete.")

        return AgentResult(
            success=True,
            output={"files_count": len(generated_files), "plan": plan},
            files=generated_files,
        )

    def _implement_legacy(self, raw: str) -> AgentResult:
        """Fallback for legacy single-response format (Phase 1/1.5 tests)."""
        self.set_state("WORKING", {"legacy_mode": True})
        trunc_warnings = detect_truncation(raw)
        pattern = r"#{2,3}\s*FILE:\s*(.+?)\s*\n```(?:\w*)\s*\n(.*?)```"
        matches = re.findall(pattern, raw, re.DOTALL)

        written_files = []
        for path_str, content in matches:
            path_str = path_str.strip()
            if self._write_file(path_str, content):
                written_files.append(path_str)

        if trunc_warnings and len(written_files) == 0:
            self.set_state("FAILED", {"error": "Truncated output detected"})
            return AgentResult(
                success=False,
                error=f"Truncated output detected: {', '.join(trunc_warnings)}",
                files=[],
            )

        if len(written_files) == 0:
            self.set_state("FAILED", {"error": "No files extracted from output"})
            return AgentResult(
                success=False,
                error="No files extracted from output",
                files=[],
            )

        self.set_state("COMPLETED", {"files_count": len(written_files)})
        return AgentResult(
            success=True,
            output={"files_count": len(written_files)},
            files=written_files,
        )

    def _generate_unit_with_retry(self, unit_spec: dict, context: str,
                                  attempt_offset: int = 0) -> AgentResult:
        """Generate a single unit with unit-level retry."""
        path = unit_spec["path"]

        # Get or create unit in DB
        unit_row = self.db.get_dev_unit_by_path(self.project_id, path)
        if unit_row:
            unit_id = unit_row["id"]
        else:
            unit_id = self.db.create_dev_unit(
                self.project_id, path,
                purpose=unit_spec.get("purpose", ""),
                exports=unit_spec.get("exports", []),
            )

        last_error = None
        for attempt in range(self.unit_max_retries):
            if attempt > 0:
                self.set_state("WORKING", {"unit": path, "attempt": attempt + 1})
            self.db.update_dev_unit_status(unit_id, "RUNNING", attempt=attempt + 1)
            self._log("developer_unit_started", {
                "path": path, "attempt": attempt + 1,
            })

            # Call LLM with adaptive feedback from previous failure if retrying
            call_context = context
            if attempt > 0 and last_error:
                call_context += (
                    f"\n\n## ⚠️ PREVIOUS ATTEMPT FIX REQUEST\n"
                    f"Your previous attempt to generate '{path}' failed with this error:\n"
                    f"--> {last_error}\n"
                    f"Please address this specific issue and output the complete, valid, non-truncated file for '{path}'."
                )

            try:
                raw = self.agent_llm_call(call_context)
            except LLMError as e:
                self.db.update_dev_unit_status(unit_id, "FAILED", error=str(e),
                                               attempt=attempt + 1)
                self._log("developer_unit_failed", {
                    "path": path, "attempt": attempt + 1, "error": str(e),
                })
                return AgentResult(success=False, error=f"LLM failed for {path}: {e}")

            # Parse response
            content, parse_error = self._parse_unit_response(raw, path)
            if parse_error:
                last_error = f"Parse failed: {parse_error}"
                if attempt < self.unit_max_retries - 1:
                    self.set_state("RETRYING", {"unit": path, "attempt": attempt + 1, "progress": "RETRY", "reason": parse_error})
                    self._log("developer_unit_retry", {
                        "path": path, "attempt": attempt + 1, "reason": parse_error,
                    })
                    print(f"      ✗ {parse_error}")
                    print(f"      retry {attempt+1}/{self.unit_max_retries}...")
                    continue
                self.db.update_dev_unit_status(unit_id, "FAILED", error=parse_error,
                                               attempt=attempt + 1)
                self._log("developer_unit_failed", {
                    "path": path, "attempt": attempt + 1, "error": parse_error,
                })
                return AgentResult(success=False, error=f"Parse failed for {path}: {parse_error}")

            # Detect truncation
            trunc_warnings = detect_unit_truncation(content, filepath=path)
            if trunc_warnings:
                last_error = f"Truncation detected: {', '.join(trunc_warnings)}"
                if attempt < self.unit_max_retries - 1:
                    self.set_state("RETRYING", {"unit": path, "attempt": attempt + 1, "progress": "RETRY", "reason": f"truncation: {trunc_warnings}"})
                    self._log("developer_unit_retry", {
                        "path": path, "attempt": attempt + 1, "reason": f"truncation: {trunc_warnings}",
                    })
                    print(f"      ✗ Truncation: {trunc_warnings}")
                    print(f"      retry {attempt+1}/{self.unit_max_retries}...")
                    continue

            # Validate syntax
            syntax_error = validate_syntax(path, content)
            if syntax_error:
                last_error = f"Syntax error: {syntax_error}"
                if attempt < self.unit_max_retries - 1:
                    self.set_state("RETRYING", {"unit": path, "attempt": attempt + 1, "progress": "RETRY", "reason": f"syntax: {syntax_error}"})
                    self._log("developer_unit_retry", {
                        "path": path, "attempt": attempt + 1, "reason": f"syntax: {syntax_error}",
                    })
                    print(f"      ✗ Syntax error: {syntax_error[:100]}")
                    print(f"      retry {attempt+1}/{self.unit_max_retries}...")
                    continue
                self.db.update_dev_unit_status(unit_id, "FAILED", error=syntax_error,
                                               attempt=attempt + 1)
                self._log("developer_unit_failed", {
                    "path": path, "attempt": attempt + 1, "error": syntax_error,
                })
                return AgentResult(success=False, error=f"Syntax error in {path}: {syntax_error}")

            # Write file to disk
            if not self._write_file(path, content):
                self.db.update_dev_unit_status(unit_id, "FAILED", error="File write failed",
                                               attempt=attempt + 1)
                self._log("developer_unit_failed", {
                    "path": path, "attempt": attempt + 1, "error": "File write failed",
                })
                return AgentResult(success=False, error=f"Failed to write {path}")

            # Success
            self.db.update_dev_unit_status(unit_id, "DONE", attempt=attempt + 1)
            self._log("developer_unit_validated", {"path": path, "attempt": attempt + 1})
            self._log("developer_unit_completed", {
                "path": path, "attempt": attempt + 1,
                "size": len(content),
            })
            print(f"      ✓ validated ({len(content)} chars)")
            return AgentResult(success=True, output={"path": path, "size": len(content)})

        # All retries exhausted
        self.db.update_dev_unit_status(unit_id, "FAILED", error="Max retries exhausted",
                                       attempt=self.unit_max_retries)
        self._log("developer_unit_failed", {
            "path": path, "attempt": self.unit_max_retries, "error": "Max retries exhausted",
        })
        return AgentResult(success=False, error=f"Max retries exhausted for {path}")

    def agent_llm_call(self, context: str) -> str:
        """Make the LLM call for unit generation."""
        prompt = UNIT_PROMPT.format(**self._format_context(context))
        resp = self.llm.chat(prompt, json_mode=False)
        return resp if isinstance(resp, str) else json.dumps(resp)

    def _format_context(self, context: str) -> dict:
        """Parse context string into format dict for UNIT_PROMPT."""
        return {
            "summary": context.split("## Project Summary\n")[1].split("\n\n")[0] if "## Project Summary" in context else "",
            "tech_stack": context.split("## Tech Stack\n")[1].split("\n\n")[0] if "## Tech Stack" in context else "",
            "path": context.split("## This File\nPath: ")[1].split("\n")[0] if "## This File\nPath:" in context else "",
            "purpose": context.split("Purpose: ")[1].split("\n")[0] if "Purpose: " in context else "",
            "dep_interfaces": context.split("## Dependency Interfaces\n")[1].split("\n\n## ")[0] if "## Dependency Interfaces" in context else "(none)",
            "requirements": context.split("## Requirements (relevant excerpt)\n")[1] if "## Requirements (relevant excerpt)" in context else "",
        }

    def _build_unit_context(self, plan: dict, unit_spec: dict,
                            completed_files: list[str]) -> str:
        """Build compact context for a single unit generation."""
        sections = []

        # Project summary
        sections.append(f"## Project Summary\n{plan.get('project_summary', '')}")

        # Tech stack
        sections.append(f"## Tech Stack\n{plan.get('tech_stack', '')}")

        # This file spec
        sections.append(f"## This File\nPath: {unit_spec['path']}\nPurpose: {unit_spec.get('purpose', '')}")

        # Dependency interfaces
        dep_interfaces = self._get_dep_interfaces(plan, unit_spec, completed_files)
        sections.append(f"## Dependency Interfaces\n{dep_interfaces}")

        # Requirements excerpt
        docs = self._read_docs()
        if len(docs) > 3000:
            docs = docs[:3000] + "\n...(truncated)"
        sections.append(f"## Requirements (relevant excerpt)\n{docs}")

        return "\n\n".join(sections)

    def _get_dep_interfaces(self, plan: dict, unit_spec: dict,
                            completed_files: list[str]) -> str:
        """Get public interfaces from dependency files."""
        files = plan.get("files", [])
        path_to_file = {f["path"]: f for f in files}
        deps = unit_spec.get("depends_on", [])

        if not deps:
            return "(no dependencies)"

        lines = []
        for dep_path in deps:
            dep_spec = path_to_file.get(dep_path)
            if dep_spec:
                exports = dep_spec.get("exports", [])
                purpose = dep_spec.get("purpose", "")
                lines.append(f"{dep_path}")
                lines.append(f"  purpose: {purpose}")
                if exports:
                    lines.append(f"  exports: {', '.join(exports)}")
            else:
                lines.append(f"{dep_path} (external)")

        return "\n".join(lines)

    def _parse_unit_response(self, raw: str, expected_path: str) -> tuple[str | None, str | None]:
        """Parse LLM response into file content. Returns (content, error)."""
        if not isinstance(raw, str):
            return None, f"Expected str, got {type(raw).__name__}"

        # Strip reasoning tags (e.g. <think>...</think> from reasoning models)
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # 1. Try structured JSON first
        content = self._try_parse_json(cleaned, expected_path)
        if content is not None:
            return content, None

        # 2. Try fenced code block
        content = self._try_parse_fenced(cleaned, expected_path)
        if content is not None:
            return content, None

        # 3. Fallback: check if cleaned string is direct valid code
        stripped = cleaned.strip()
        if stripped:
            if expected_path.endswith(".py"):
                try:
                    ast.parse(stripped, filename=expected_path)
                    return stripped, None
                except SyntaxError:
                    pass
            if any(stripped.startswith(kw) for kw in ("import ", "from ", "def ", "class ", "#!/", "# ", "/*", "//", "package ", "const ", "function ")):
                return stripped, None

        return None, "Could not parse response as JSON or code fence"

    def _try_parse_json(self, raw: str, expected_path: str) -> str | None:
        """Try to parse as structured JSON response."""
        raw = raw.strip()
        # Strip markdown fences around json if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"(\{.*\})", raw, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                except json.JSONDecodeError:
                    return None
            else:
                return None

        if not isinstance(data, dict):
            return None

        path = data.get("path", "")
        content = data.get("content", "")

        if not content:
            return None

        if path and path != expected_path:
            logger.warning(f"Path mismatch: expected {expected_path}, got {path}")

        return content

    def _try_parse_fenced(self, raw: str, expected_path: str) -> str | None:
        """Try to extract content from fenced code block (both closed and unclosed)."""
        # 1. Closed code fences
        pattern = r"```(?:\w*)\s*\n(.*?)```"
        matches = re.findall(pattern, raw, re.DOTALL)
        if matches:
            content = max(matches, key=len).strip()
            if content:
                return content

        # 2. Unclosed code fence (truncated before ending backticks)
        unclosed_pattern = r"```(?:\w*)\s*\n(.*)$"
        unclosed = re.search(unclosed_pattern, raw, re.DOTALL)
        if unclosed:
            content = unclosed.group(1).strip()
            if content:
                return content

        return None

    def _parse_fix_files(self, fix_context: str) -> list[str] | None:
        """Extract file paths from QA fix context."""
        files = []
        patterns = [
            r'"file":\s*"([^"]+)"',
            r'`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)`',
            r'([a-zA-Z0-9_\-./]+\.(?:py|js|ts|jsx|tsx|html|css|json|yaml|yml|sql))',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, fix_context)
            files.extend(matches)

        seen = set()
        unique = []
        for f in files:
            clean = f.strip().strip("'\"`")
            if clean and clean not in seen and not clean.startswith("docs/"):
                seen.add(clean)
                unique.append(clean)

        return unique if unique else None

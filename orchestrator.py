"""Orchestrator — runs PM → Conceptor → Developer(Chunked) → QA pipeline."""

from __future__ import annotations
import json
import time
import yaml
import logging
import traceback
from pathlib import Path
from llm import LLMClient, LLMError
from db import Database
from result import AgentResult
from events import EventBus, Stream, Event, EVENT_PIPELINE_STARTED, EVENT_PIPELINE_COMPLETED, EVENT_PIPELINE_FAILED
from registry import create_default_organization, AgentRegistry
from agents import PMAgent, ConceptorAgent, DeveloperAgent, QAAgent
from factory import AgentFactory


logger = logging.getLogger("aether.orchestrator")


def load_config(path: str = "config.yaml") -> dict:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    if path == "config.yaml" and Path("config.example.yaml").exists():
        with open("config.example.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Orchestrator:
    """Runs the full AI dev team pipeline with failure isolation."""

    def __init__(self, config: dict, project_id: str, output_dir: str):
        self.config = config
        self.project_id = project_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Init Event System & Organization Registry
        self.event_bus = EventBus()
        self.stream = Stream(self.event_bus)
        self.org, self.registry = create_default_organization()
        self.event_bus.subscribe(self._sync_agent_registry)

        # Init DB
        db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
        self.db = Database(db_path, event_bus=self.event_bus)

        # Init LLM (Router)
        llm_cfg = config.get("llm", {})
        self.llm = LLMClient(
            endpoint=llm_cfg["endpoint"],
            api_key=llm_cfg["api_key"],
            model=llm_cfg.get("model", "default"),
            temperature=llm_cfg.get("temperature", 0.7),
            max_tokens=llm_cfg.get("max_tokens", 4096),
            max_retries=llm_cfg.get("max_retries", 3),
            timeout=llm_cfg.get("timeout", 300),
            models=llm_cfg.get("models"),
        )

        self.factory = AgentFactory(organization=self.org)

        # Init agents with role-routed LLM clients from the router
        # When self.llm is mocked in unit tests, preserve the original mock
        is_real_client = type(self.llm).__name__ == "LLMClient" and not hasattr(self.llm, "_mock_return_value")
        pm_llm = self.llm.for_role("pm") if is_real_client else self.llm
        conceptor_llm = self.llm.for_role("conceptor") if is_real_client else self.llm
        dev_llm = self.llm.for_role("developer") if is_real_client else self.llm
        qa_llm = self.llm.for_role("qa") if is_real_client else self.llm

        self.pm = PMAgent(pm_llm, self.db, project_id, str(output_dir),
                          agent_id="pm_001", event_bus=self.event_bus)
        self.conceptor = ConceptorAgent(conceptor_llm, self.db, project_id, str(output_dir),
                                        agent_id="conceptor_001", event_bus=self.event_bus)
        self.developer = DeveloperAgent(dev_llm, self.db, project_id, str(output_dir), config,
                                        agent_id="developer_001", event_bus=self.event_bus)
        self.qa = QAAgent(qa_llm, self.db, project_id, str(output_dir),
                          agent_id="qa_001", event_bus=self.event_bus)

        self.max_retries = config.get("qa", {}).get("max_retries", 3)


    def _sync_agent_registry(self, evt: Event):
        """Synchronize live agent states into AgentRegistry."""
        if evt.event_type == "agent_state_changed" and evt.agent_id and evt.status:
            self.registry.update_status(evt.agent_id, evt.status)

    def run(self, brief: str) -> dict:
        """Execute full pipeline. Returns result dict. Never crashes without logging."""
        start = time.time()
        result = {"phases": [], "success": False, "error": None}

        # Create project
        try:
            self.db.create_project(
                self.project_id, name="project", brief=brief,
                output_dir=str(self.output_dir),
            )
            self.db.log_event(self.project_id, "pipeline.started",
                              data={"brief_length": len(brief)})
        except Exception as e:
            result["error"] = f"Failed to create project: {e}"
            logger.exception("Pipeline init failed")
            return result

        # Phase 1: PM
        pm_result = self._run_phase("pm", "📋 Phase 1: Project Manager", self._phase_pm, brief)
        result["phases"].append(pm_result)
        if not pm_result.get("success"):
            result["error"] = f"PM failed: {pm_result.get('error', 'unknown')}"
            self._finalize(result, start, success=False)
            return result

        # Phase 2: Conceptor
        conceptor_result = self._run_phase("conceptor", "📝 Phase 2: Conceptor", self._phase_conceptor)
        result["phases"].append(conceptor_result)
        if not conceptor_result.get("success"):
            result["error"] = f"Conceptor failed: {conceptor_result.get('error', 'unknown')}"
            self._finalize(result, start, success=False)
            return result

        # Phase 3: Developer (chunked)
        dev_result = self._run_phase("developer", "💻 Phase 3: Developer", self._phase_developer)
        result["phases"].append(dev_result)
        if not dev_result.get("success"):
            result["error"] = f"Developer failed: {dev_result.get('error', 'unknown')}"
            self._finalize(result, start, success=False)
            return result

        # Phase 4: QA (with retry loop)
        qa_passed = False
        retries = 0
        while not qa_passed and retries <= self.max_retries:
            qa_result = self._run_phase("qa", f"🔍 Phase 4: QA (attempt {retries+1}/{self.max_retries+1})", self._phase_qa)
            result["phases"].append(qa_result)

            if not qa_result.get("success"):
                result["error"] = f"QA crashed: {qa_result.get('error', 'unknown')}"
                break

            verdict = qa_result.get("verdict", "FAIL")
            if verdict == "PASS":
                qa_passed = True
            else:
                retries += 1
                if retries <= self.max_retries:
                    # Build fix context from QA output
                    qa_output = qa_result.get("qa_output", {})
                    fix_context = (
                        f"QA FAIL #{retries}.\n"
                        f"Bugs:\n{json.dumps(qa_output.get('bugs_found', []), indent=2)}\n\n"
                        f"Fix instructions:\n{qa_output.get('fix_instructions', 'Fix all bugs')}"
                    )
                    fix_result = self._run_phase(
                        "developer", f"🔧 Developer fix (attempt {retries})",
                        self._phase_fix, fix_context,
                    )
                    result["phases"].append(fix_result)
                    if not fix_result.get("success"):
                        result["error"] = f"Developer fix failed: {fix_result.get('error', 'unknown')}"
                        break

        self._finalize(result, start, success=qa_passed)
        return result

    def _run_phase(self, agent_role: str, label: str, fn, *args) -> dict:
        """Run a single phase with error boundary."""
        print(f"\n{label}...")
        try:
            agent_result: AgentResult = fn(*args)
        except Exception as e:
            logger.exception(f"Phase {agent_role} crashed")
            self.db.log_event(self.project_id, "agent.failed", agent_role,
                              data={"error": str(e), "traceback": traceback.format_exc()})
            print(f"   💥 CRASHED: {e}")
            return {"agent": agent_role, "success": False, "error": str(e), "status": "crashed"}

        # Log events from result
        for evt in agent_result.events:
            self.db.log_event(self.project_id, evt.get("type", "unknown"), agent_role, data=evt)

        phase_data = {"agent": agent_role, "success": agent_result.success}

        if agent_result.success:
            phase_data["status"] = "done"
            if agent_result.files:
                phase_data["files"] = len(agent_result.files)
            if isinstance(agent_result.output, dict):
                phase_data["qa_output"] = agent_result.output
                phase_data["verdict"] = agent_result.output.get("verdict")
        else:
            phase_data["status"] = "failed"
            phase_data["error"] = agent_result.error
            self.db.log_event(self.project_id, "agent.failed", agent_role,
                              data={"error": agent_result.error})

        return phase_data

    # --- Phase implementations ---

    def _phase_pm(self, brief: str) -> AgentResult:
        result = self.pm.create_project(brief)
        if result.success:
            output = result.output or {}
            print(f"   ✅ {output.get('task_count', '?')} tasks created")
        else:
            print(f"   ❌ FAILED: {result.error}")
        return result

    def _phase_conceptor(self) -> AgentResult:
        result = self.conceptor.create_requirements()
        if result.success:
            print(f"   ✅ Requirements: {len(result.output or '')} chars")
        else:
            print(f"   ❌ FAILED: {result.error}")
        return result

    def _phase_developer(self) -> AgentResult:
        result = self.developer.implement()
        if result.success:
            print(f"   ✅ {len(result.files)} files generated")
        else:
            print(f"   ❌ FAILED: {result.error}")
        return result

    def _phase_qa(self) -> AgentResult:
        result = self.qa.test()
        if result.success and result.output:
            output = result.output if isinstance(result.output, dict) else {}
            verdict = output.get("verdict", "?")
            bugs = len(output.get("bugs_found", []))
            print(f"   {'✅' if verdict == 'PASS' else '❌'} Verdict: {verdict}, Bugs: {bugs}")
        elif not result.success:
            print(f"   ❌ FAILED: {result.error}")
        return result

    def _phase_fix(self, fix_context: str) -> AgentResult:
        return self.developer.implement(fix_context=fix_context)

    # --- Finalize ---

    def _finalize(self, result: dict, start: float, success: bool):
        elapsed = time.time() - start
        result["success"] = success
        result["elapsed_seconds"] = round(elapsed, 1)

        if success:
            self.db.update_project_status(self.project_id, "DONE")
            self.db.log_event(self.project_id, EVENT_PIPELINE_COMPLETED,
                              data={"elapsed": elapsed}, status="COMPLETED")
            print(f"\n{'='*50}")
            print(f"✅ PIPELINE COMPLETE — {result['elapsed_seconds']}s")
        else:
            self.db.update_project_status(self.project_id, "FAILED")
            self.db.log_event(self.project_id, EVENT_PIPELINE_FAILED,
                              data={"error": result.get("error"), "elapsed": elapsed}, status="FAILED")
            print(f"\n{'='*50}")
            print(f"❌ PIPELINE FAILED — {result['elapsed_seconds']}s")
            if result.get("error"):
                print(f"   Reason: {result['error']}")

        self._write_summary(result)
        print(f"   Output: {self.output_dir}")
        try:
            self.stream.close()
        except Exception:
            pass

    def _write_summary(self, result: dict):
        status = "✅ SUCCESS" if result["success"] else "❌ FAILED"
        lines = [
            "# Pipeline Summary\n",
            f"**Status:** {status}",
            f"**Time:** {result['elapsed_seconds']}s",
        ]
        if result.get("error"):
            lines.append(f"**Error:** {result['error']}")
        lines.append("\n## Phases\n")
        for p in result.get("phases", []):
            icon = "✅" if p.get("success") else "❌"
            line = f"- {icon} **{p.get('agent', '?')}**: {p.get('status', '?')}"
            if "files" in p:
                line += f" ({p['files']} files)"
            if "error" in p:
                line += f" — {p['error']}"
            lines.append(line)

        (self.output_dir / "docs").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "docs" / "summary.md").write_text("\n".join(lines), encoding="utf-8")

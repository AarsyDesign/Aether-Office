"""Phase 9 Comprehensive Test Suite: Adaptive Planning & Intelligence.

Validates:
- Objective classification across 6 domains (Software, Research, Marketing, Content, Analysis, General)
- Strategy selection and decomposition for all domains
- ObjectiveComplexity detection (SIMPLE, STANDARD, COMPLEX)
- Ambiguity detection and ClarificationRequest generation
- Plan quality evaluation (PlanQualityReport, score, issues, recommendations)
- Risk analysis (7 risk types)
- Workforce-aware and budget-aware planning
- Deadline analysis and critical path computation
- Plan optimization (dependency pruning, parallelization, cost tier adjustment)
- LLM planner assistance schema validation and deterministic fallback
- Intermediate milestone quality gating and revision handling
- Full end-to-end pipeline execution with existing OfficeRuntime and SchedulerEngine
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta

from objectives import Objective, ObjectiveStatus, AcceptanceCriterion, CriterionType
from analysis import (
    ObjectiveType,
    ObjectiveComplexity,
    RiskType,
    ClarificationRequest,
    RiskAssessment,
    ObjectiveAnalysis,
    ObjectiveAnalyzer,
    RiskAnalyzer,
)
from strategies import (
    PlanningStrategy,
    SoftwarePlanningStrategy,
    ResearchPlanningStrategy,
    MarketingPlanningStrategy,
    ContentPlanningStrategy,
    AnalysisPlanningStrategy,
    GeneralPlanningStrategy,
    get_strategy_for_type,
)
from plan_evaluator import PlanQualityEvaluator, PlanQualityReport, PlanOptimizer
from milestone_gate import MilestoneGate, MilestoneGateStatus, MilestoneGateEvaluator
from adaptive_planner import AdaptiveObjectivePlanner, LLMPlannerAssistant
from planner import ExecutionPlan, Milestone, PlanValidator, ObjectivePlanner, LegacyObjectivePlanner
from workforce import Organization, Department, Role, Employee, create_default_organization
from office import OfficeOrchestrator
from objective_orchestrator import ObjectiveOrchestrator
from events import EventBus, Event
from db import Database


@pytest.fixture
def mock_org():
    """Builds a verified Organization with the full role catalog and active workforce."""
    org, _ = create_default_organization()
    return org


def test_objective_classification():
    """Verify classification of objectives across 6 domain types."""
    analyzer = ObjectiveAnalyzer()

    # 1. SOFTWARE
    obj_sw = Objective("obj_1", "Bangun aplikasi mobile Flutter e-commerce", description="Fitur katalog, keranjang belanja, dan pembayaran payment gateway.")
    assert analyzer.classify_objective_type(obj_sw) == ObjectiveType.SOFTWARE

    # 2. RESEARCH
    obj_res = Objective("obj_2", "Riset 20 kompetitor AI di Asia Tenggara", description="Lakukan studi perbandingan fitur, harga, dan arsitektur model.")
    assert analyzer.classify_objective_type(obj_res) == ObjectiveType.RESEARCH

    # 3. MARKETING
    obj_mkt = Objective("obj_3", "Buat campaign pemasaran produk SaaS", description="Strategi kampanye peluncuran, iklan sosial media, dan email outreach.")
    assert analyzer.classify_objective_type(obj_mkt) == ObjectiveType.MARKETING

    # 4. CONTENT
    obj_cnt = Objective("obj_4", "Buat katalog produk e-commerce dan artikel blog", description="Penulisan konten deskripsi 100 produk dan materi promosi.")
    assert analyzer.classify_objective_type(obj_cnt) == ObjectiveType.CONTENT

    # 5. ANALYSIS
    obj_anl = Objective("obj_5", "Analisis penjualan dan tren performa finansial bulan ini", description="Evaluasi metrik churn rate, revenue growth, dan statistik transaksi.")
    assert analyzer.classify_objective_type(obj_anl) == ObjectiveType.ANALYSIS

    # 6. GENERAL
    obj_gen = Objective("obj_6", "Koordinasikan pertemuan akbar tahunan kantor", description="Rencanakan rundown acara dan koordinasi logistik.")
    assert analyzer.classify_objective_type(obj_gen) == ObjectiveType.GENERAL


def test_strategy_selection():
    """Verify that get_strategy_for_type returns the correct concrete strategy instance."""
    assert isinstance(get_strategy_for_type(ObjectiveType.SOFTWARE), SoftwarePlanningStrategy)
    assert isinstance(get_strategy_for_type(ObjectiveType.RESEARCH), ResearchPlanningStrategy)
    assert isinstance(get_strategy_for_type(ObjectiveType.MARKETING), MarketingPlanningStrategy)
    assert isinstance(get_strategy_for_type(ObjectiveType.CONTENT), ContentPlanningStrategy)
    assert isinstance(get_strategy_for_type(ObjectiveType.ANALYSIS), AnalysisPlanningStrategy)
    assert isinstance(get_strategy_for_type(ObjectiveType.GENERAL), GeneralPlanningStrategy)


def test_software_strategy(mock_org):
    """Verify SoftwarePlanningStrategy decomposition into Discovery -> Design -> Implementation -> Testing -> Deployment."""
    strat = SoftwarePlanningStrategy()
    obj = Objective("obj_sw", "Bangun REST API backend pembayaran", description="Backend service microservice.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)

    plan = strat.plan(obj, analysis, organization=mock_org)
    assert len(plan.milestones) == 5
    assert len(plan.tasks) >= 5

    # Check DAG validity
    is_valid, err = PlanValidator.validate_plan(plan, organization=mock_org)
    assert is_valid, f"Plan validation failed: {err}"


def test_research_strategy(mock_org):
    """Verify ResearchPlanningStrategy decomposition: Scope -> Data Collection -> Analysis -> Synthesis -> Report."""
    strat = ResearchPlanningStrategy()
    obj = Objective("obj_res", "Riset mendalam perbandingan framework LLM", description="Studi literatur dan benchmark.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)

    plan = strat.plan(obj, analysis, organization=mock_org)
    assert len(plan.milestones) == 5
    assert len(plan.tasks) >= 5

    is_valid, err = PlanValidator.validate_plan(plan, organization=mock_org)
    assert is_valid, f"Research plan invalid: {err}"


def test_marketing_strategy(mock_org):
    """Verify MarketingPlanningStrategy decomposition: Research -> Strategy -> Content -> Distribution -> Measurement."""
    strat = MarketingPlanningStrategy()
    obj = Objective("obj_mkt", "Kampanye pemasaran digital produk baru", description="Peluncuran brand SaaS.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)

    plan = strat.plan(obj, analysis, organization=mock_org)
    assert len(plan.milestones) == 5
    assert len(plan.tasks) >= 5
    is_valid, err = PlanValidator.validate_plan(plan, organization=mock_org)
    assert is_valid, f"Marketing plan invalid: {err}"


def test_content_strategy(mock_org):
    """Verify ContentPlanningStrategy decomposition: Brief -> Research -> Production -> Review -> Publishing."""
    strat = ContentPlanningStrategy()
    obj = Objective("obj_cnt", "Produksi 10 artikel dokumentasi panduan teknis", description="Panduan pengguna.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)

    plan = strat.plan(obj, analysis, organization=mock_org)
    assert len(plan.milestones) == 5
    assert len(plan.tasks) >= 5
    is_valid, err = PlanValidator.validate_plan(plan, organization=mock_org)
    assert is_valid, f"Content plan invalid: {err}"


def test_analysis_strategy(mock_org):
    """Verify AnalysisPlanningStrategy decomposition: Data Collection -> Processing -> Analysis -> Validation -> Recommendation."""
    strat = AnalysisPlanningStrategy()
    obj = Objective("obj_anl", "Analisis statistik churn pelanggan Q3", description="Eksplorasi dataset churn.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)

    plan = strat.plan(obj, analysis, organization=mock_org)
    assert len(plan.milestones) == 5
    assert len(plan.tasks) >= 5
    is_valid, err = PlanValidator.validate_plan(plan, organization=mock_org)
    assert is_valid, f"Analysis plan invalid: {err}"


def test_general_strategy(mock_org):
    """Verify GeneralPlanningStrategy conservative decomposition for arbitrary goals."""
    strat = GeneralPlanningStrategy()
    obj = Objective("obj_gen", "Peremajaan inventaris perlengkapan ruang rapat", description="Pengecekan fasilitas.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)

    plan = strat.plan(obj, analysis, organization=mock_org)
    assert len(plan.milestones) == 4
    assert len(plan.tasks) >= 4
    is_valid, err = PlanValidator.validate_plan(plan, organization=mock_org)
    assert is_valid, f"General plan invalid: {err}"


def test_complexity_detection():
    """Verify complexity classification (SIMPLE, STANDARD, COMPLEX) based on text, scope, and budget."""
    analyzer = ObjectiveAnalyzer()

    # Simple: short title and concise description
    obj_simple = Objective("obj_s", "Perbaiki typo pada halaman login", description="Koreksi teks tombol.")
    assert analyzer.determine_complexity(obj_simple) == ObjectiveComplexity.SIMPLE

    # Standard: moderate description
    obj_std = Objective("obj_m", "Kembangkan modul autentikasi Google OAuth", description="Integrasi login dengan provider Google OAuth 2.0 dan manajemen session.")
    assert analyzer.determine_complexity(obj_std) == ObjectiveComplexity.STANDARD

    # Complex: large description with multiple enterprise keywords and high budget
    obj_cplx = Objective(
        "obj_c",
        "Bangun arsitektur microservices core banking enterprise",
        description="Pengembangan sistem enterprise berskala besar, integrasi multi-channel payment gateway, kepatuhan audit keamanan, migrasi database heterogen berkapasitas tinggi, dan toleransi fault terdistribusi secara menyeluruh dengan high availability.",
        budget=15000.0,
    )
    assert analyzer.determine_complexity(obj_cplx) == ObjectiveComplexity.COMPLEX


def test_ambiguity_detection():
    """Verify detection of ambiguous/underspecified objectives with subjective adjectives."""
    analyzer = ObjectiveAnalyzer()

    # Highly ambiguous: 3 words, subjective adjective, no description
    obj_vague = Objective("obj_v", "Buat website yang bagus", description="")
    ambiguity = analyzer.assess_ambiguity(obj_vague)
    assert ambiguity >= 0.50

    # Concrete objective: clear scope and details
    obj_clear = Objective(
        "obj_c",
        "Implementasi REST API autentikasi JWT pengguna",
        description="Endpoint POST /login dan POST /register menggunakan hash bcrypt dengan database PostgreSQL.",
    )
    assert analyzer.assess_ambiguity(obj_clear) < 0.40


def test_clarification_request():
    """Verify ClarificationRequest generation for ambiguous objectives and planner blocking gate."""
    analyzer = ObjectiveAnalyzer()
    obj_vague = Objective("obj_v", "Buat aplikasi keren", description="")
    analysis = analyzer.analyze(obj_vague)

    assert analysis.needs_clarification is True
    assert len(analysis.clarifications) > 0
    blocking = [c for c in analysis.clarifications if c.blocking]
    assert len(blocking) > 0
    assert any("target" in c.question.lower() or "lingkup" in c.question.lower() or "kriteria" in c.question.lower() for c in blocking)

    # Adaptive planner should reject planning until clarified
    planner = AdaptiveObjectivePlanner(analyzer=analyzer)
    plan = planner.plan(obj_vague)
    assert plan.is_valid is False
    assert plan.metadata.get("needs_clarification") is True
    assert "memerlukan klarifikasi" in plan.validation_error


def test_plan_quality(mock_org):
    """Verify PlanQualityEvaluator scoring, issue detection, and recommendations."""
    strat = SoftwarePlanningStrategy()
    obj = Objective("obj_sw", "Bangun portal web inventory", description="Sistem inventory barang.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)
    plan = strat.plan(obj, analysis, organization=mock_org)

    report = PlanQualityEvaluator.evaluate(plan, obj, organization=mock_org)
    assert isinstance(report, PlanQualityReport)
    assert 0 <= report.score <= 100
    assert report.grade in ("A+", "A", "B", "C", "D", "F")
    assert report.is_viable is True
    assert isinstance(report.issues, list)
    assert isinstance(report.warnings, list)
    assert isinstance(report.recommendations, list)


def test_risk_analysis(mock_org):
    """Verify RiskAnalyzer identifies specific risk types."""
    # Test high complexity and ambiguous requirement risks
    obj_risky = Objective(
        "obj_risk",
        "Sistem cerdas canggih enterprise",
        description="Pengembangan sistem enterprise berskala besar, integrasi multi-channel, kepatuhan audit keamanan, migrasi database heterogen berkapasitas tinggi.",
        budget=10.0,  # Intentionally low budget for risk detection
    )
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj_risky)

    detected_types = {r.risk_type for r in analysis.risks}
    assert RiskType.HIGH_COMPLEXITY in detected_types or RiskType.AMBIGUOUS_REQUIREMENT in detected_types or RiskType.BUDGET_RISK in detected_types


def test_workforce_aware_planning():
    """Verify planning awareness when organization lacks required capabilities."""
    empty_org = Organization()  # Org with no employees or capabilities
    obj = Objective("obj_sw", "Bangun REST API backend", description="Backend service.")
    planner = AdaptiveObjectivePlanner(organization=empty_org)
    plan = planner.plan(obj)

    # Quality check should reflect capability shortage
    quality = plan.metadata.get("quality_report", {})
    warnings = quality.get("warnings", [])
    issues = quality.get("issues", [])
    combined = " ".join(warnings + issues)
    assert "kemampuan" in combined.lower() or "kapabilitas" in combined.lower() or "tidak tersedia" in combined.lower()


def test_budget_aware_planning(mock_org):
    """Verify budget risk detection and model tier adjustment when plan exceeds budget."""
    # Strict budget: $0.001
    obj_budget = Objective("obj_b", "Bangun arsitektur microservices enterprise", description="Sistem terdistribusi.", budget=0.001)
    planner = AdaptiveObjectivePlanner(organization=mock_org, enable_optimization=True)
    plan = planner.plan(obj_budget)

    quality = plan.metadata.get("quality_report", {})
    warnings = quality.get("warnings", [])
    issues = quality.get("issues", [])
    assert any("anggaran" in w.lower() or "budget" in w.lower() for w in (warnings + issues)) or not plan.is_valid or len(plan.metadata.get("optimizations", [])) > 0


def test_deadline_analysis(mock_org):
    """Verify deadline risk assessment when estimated duration exceeds deadline."""
    # Set impossible deadline: 1 hour in the future
    deadline_iso = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    obj_urgent = Objective(
        "obj_urg",
        "Bangun aplikasi mobile enterprise",
        description="Proyek besar dengan durasi panjang.",
        deadline=deadline_iso,
    )
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj_urgent)

    deadline_risks = [r for r in analysis.risks if r.risk_type == RiskType.DEADLINE_RISK]
    assert len(deadline_risks) > 0
    assert "tenggat waktu" in deadline_risks[0].description.lower() or "deadline" in deadline_risks[0].description.lower() or "ketat" in deadline_risks[0].description.lower()


def test_plan_optimization(mock_org):
    """Verify PlanOptimizer detects critical path, marks parallelizable tasks, and removes duplicate dependencies."""
    strat = SoftwarePlanningStrategy()
    obj = Objective("obj_opt", "Pengembangan sistem billing SaaS", description="Sistem billing.")
    analyzer = ObjectiveAnalyzer(organization=mock_org)
    analysis = analyzer.analyze(obj)
    plan = strat.plan(obj, analysis, organization=mock_org)

    # Intentionally add a redundant dependency to test pruning
    t0 = plan.tasks[0]["task_id"]
    t1 = plan.tasks[1]["task_id"]
    plan.dependencies[t1] = [t0, t0]  # duplicate entry

    opt_plan, modified, notes = PlanOptimizer.optimize_plan(plan, obj, organization=mock_org)
    assert modified is True
    # Duplicate removed
    assert len(opt_plan.dependencies[t1]) == 1
    # Critical path should be identified
    assert "critical_path" in opt_plan.metadata
    assert len(opt_plan.metadata["critical_path"]) > 0


def test_llm_planner_fallback(mock_org):
    """Verify that if LLM assistant fails/raises an error, planner falls back to deterministic strategy safely."""
    def broken_llm(prompt):
        raise RuntimeError("LLM API timeout error 503")

    assistant = LLMPlannerAssistant(llm_client=broken_llm)
    planner = AdaptiveObjectivePlanner(
        organization=mock_org,
        llm_assistant=assistant,
    )
    obj = Objective("obj_fb", "Riset 15 framework web Python", description="Analisis perbandingan performa.")
    plan = planner.plan(obj)

    # Should successfully fall back to ResearchPlanningStrategy
    assert plan.is_valid is True
    assert plan.metadata.get("strategy") in ("research_inquiry", "research_investigation", "Research & Investigation Strategy")
    assert plan.metadata.get("used_llm_assist") is False


def test_invalid_llm_plan(mock_org):
    """Verify that an invalid LLM output (cyclic DAG) is rejected by PlanValidator and falls back to deterministic plan."""
    # LLM produces a cyclic dependency: task_a -> task_b -> task_a
    cyclic_llm_output = {
        "id": "plan_cyclic",
        "objective_id": "obj_cyc",
        "milestones": [{"milestone_id": "m1", "name": "M1", "tasks": ["t_a", "t_b"]}],
        "tasks": [
            {"task_id": "t_a", "title": "Task A", "milestone_id": "m1", "required_capabilities": ["coding"]},
            {"task_id": "t_b", "title": "Task B", "milestone_id": "m1", "required_capabilities": ["coding"]},
        ],
        "dependencies": {
            "t_a": ["t_b"],
            "t_b": ["t_a"],  # Cycle!
        },
        "estimated_cost": 10.0,
        "required_skills": ["coding"],
    }

    def bad_llm(prompt):
        return cyclic_llm_output

    assistant = LLMPlannerAssistant(llm_client=bad_llm)
    planner = AdaptiveObjectivePlanner(
        organization=mock_org,
        llm_assistant=assistant,
    )
    obj = Objective("obj_cyc", "Bangun fitur analitik dashboard", description="Dashboard reporting.")
    plan = planner.plan(obj)

    # Rejection should occur and fallback strategy used
    assert plan.is_valid is True
    assert plan.id != "plan_cyclic"
    assert plan.metadata.get("used_llm_assist") is False


def test_milestone_gating():
    """Verify intermediate MilestoneGate evaluation: PASS, NEEDS_REVISION, and revision task injection."""
    evaluator = MilestoneGateEvaluator()

    # 1. Test Passing Gate
    gate = MilestoneGate(milestone_id="m_res", name="Research Phase")
    tasks_done = [{"task_id": "t1", "status": "COMPLETED", "result": {"output": "Laporan riset selesai"}}]
    status, feedback, _, _ = evaluator.evaluate_gate(gate, tasks=tasks_done, artifacts=[])
    assert status == MilestoneGateStatus.PASSED
    assert "selesai sempurna" in feedback

    # 2. Test Failing Gate when criteria unfulfilled
    gate_strict = MilestoneGate(
        milestone_id="m_strict",
        name="Strict Phase",
        max_revisions=2,
    )
    gate_strict.gating_criteria.add_criterion(
        AcceptanceCriterion("Keyword Check", CriterionType.TEXT, target_value="disetujui")
    )
    status_fail, fb_fail, _, rev_tasks = evaluator.evaluate_gate(gate_strict, tasks=tasks_done, artifacts=[])
    assert status_fail == MilestoneGateStatus.NEEDS_REVISION
    assert len(rev_tasks) == 1
    assert rev_tasks[0]["milestone_id"] == "m_strict"
    assert gate_strict.revision_count == 1


def test_adaptive_planner_end_to_end(mock_org, tmp_path):
    """End-to-End Integration Test:
    CREATE OBJECTIVE -> ANALYZE -> CLASSIFY -> SELECT STRATEGY ->
    GENERATE PLAN -> VALIDATE -> QUALITY CHECK -> OPTIMIZE ->
    EXECUTION PLAN -> OFFICE RUNTIME SCHEDULER -> OUTCOME
    """
    db_path = str(tmp_path / "test_aether.db")
    db = Database(db_path)
    db.sync_organization_to_db(mock_org)
    event_bus = EventBus()

    # Track published events
    captured_events = []
    event_bus.subscribe(lambda e: captured_events.append(e.event_type))

    # Initialize Office Orchestrator with our mock org
    office_orch = OfficeOrchestrator(
        db=db,
        organization=mock_org,
        event_bus=event_bus,
    )

    # Initialize Objective Orchestrator with Adaptive Planner
    adaptive_planner = AdaptiveObjectivePlanner(
        organization=office_orch.organization,
        event_bus=event_bus,
    )
    obj_orch = ObjectiveOrchestrator(
        office_orchestrator=office_orch,
        planner=adaptive_planner,
        db=db,
        event_bus=event_bus,
    )

    # 1. Create Objective
    obj = obj_orch.create_objective(
        title="Bangun landing page portal edukasi",
        description="Landing page interaktif untuk pendaftaran kursus online dengan integrasi backend dan testing.",
        budget=500.0,
    )
    assert obj.status == ObjectiveStatus.CREATED

    # 2. Analyze Objective
    analysis = obj_orch.analyze_objective(obj.id)
    assert analysis.objective_type == ObjectiveType.SOFTWARE
    assert analysis.confidence >= 0.70

    # 3. Plan Objective (Strategy Selection -> Plan Generation -> Validation -> Quality Check -> Optimization)
    plan = obj_orch.plan_objective(obj.id)
    assert plan.is_valid is True
    assert obj.status == ObjectiveStatus.READY
    assert plan.metadata.get("strategy") in ("software_engineering", "Software Engineering Strategy")
    assert plan.metadata.get("quality_score") is not None
    assert plan.metadata.get("quality_score") is not None

    # 4. Evaluate Plan Quality
    report = obj_orch.evaluate_plan_quality(obj.id)
    assert report is not None
    assert report.is_viable is True

    # 5. Execute Plan in Office Runtime via Scheduler Tick
    executed_obj = obj_orch.run_objective(obj.id, auto_tick=True, max_ticks=30)
    assert executed_obj.status == ObjectiveStatus.COMPLETED
    assert executed_obj.result is not None

    # 6. Verify Phase 9 Event Flow
    assert "objective_analysis_started" in captured_events
    assert "objective_analyzed" in captured_events
    assert "planning_strategy_selected" in captured_events
    assert "plan_generated" in captured_events
    assert "plan_validated" in captured_events
    assert "plan_quality_evaluated" in captured_events
    assert "objective_completed" in captured_events

    db.close()

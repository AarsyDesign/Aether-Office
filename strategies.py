"""Domain-Specific Planning Strategies for Phase 9 Adaptive Planning.

Defines the PlanningStrategy interface and concrete strategies for Software,
Research, Marketing, Content, Data Analysis, and General objectives.
"""

from __future__ import annotations
import uuid
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from objectives import Objective
from analysis import ObjectiveType, ObjectiveComplexity, ObjectiveAnalysis
from planner import ExecutionPlan, Milestone
from workforce import Organization


class PlanningStrategy(ABC):
    """Abstract interface for domain-specific planning strategies."""

    strategy_name: str = "base"
    objective_type: ObjectiveType = ObjectiveType.GENERAL

    @abstractmethod
    def plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
        organization: Optional[Organization] = None,
    ) -> ExecutionPlan:
        """Decomposes an objective into a domain-tailored ExecutionPlan."""
        pass


class SoftwarePlanningStrategy(PlanningStrategy):
    """5-phase software engineering decomposition:
    Discovery -> Design -> Implementation -> Testing -> Deployment.
    """
    strategy_name = "software_engineering"
    objective_type = ObjectiveType.SOFTWARE

    def plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
        organization: Optional[Organization] = None,
    ) -> ExecutionPlan:
        plan_id = f"plan_sw_{objective.id}_{int(time.time())}"
        proj_id = objective.project_id or objective.id
        milestones: list[Milestone] = []
        tasks: list[dict] = []
        dependencies: dict[str, list[str]] = {}
        all_skills: set[str] = set()

        is_complex = analysis.complexity == ObjectiveComplexity.COMPLEX
        is_simple = analysis.complexity == ObjectiveComplexity.SIMPLE

        # --- Milestone 1: Discovery & Scoping ---
        m1_id = f"m1_{objective.id}_discovery"
        t1_id = f"{objective.id}_t1_scope"
        t1 = {
            "task_id": t1_id,
            "project_id": proj_id,
            "milestone_id": m1_id,
            "title": f"Analisis Kebutuhan & Spesifikasi: {objective.title}",
            "description": f"Spesifikasi teknis, batasan sistem, dan kriteria penerimaan untuk {objective.title}.",
            "priority": 10,
            "preferred_role": "conceptor",
            "required_capabilities": ["requirements_analysis", "acceptance_criteria"],
            "model_tier": "standard",
        }
        tasks.append(t1)
        dependencies[t1_id] = []
        all_skills.update(t1["required_capabilities"])

        m1_tasks = [t1_id]
        if is_complex:
            t1b_id = f"{objective.id}_t1b_feasibility"
            t1b = {
                "task_id": t1b_id,
                "project_id": proj_id,
                "milestone_id": m1_id,
                "title": f"Studi Kelayakan Teknis & Integrasi: {objective.title}",
                "description": "Evaluasi dependensi pihak ketiga, protokol API, dan arsitektur integrasi data.",
                "priority": 9,
                "preferred_role": "conceptor",
                "required_capabilities": ["technical_design", "requirements_analysis"],
                "model_tier": "standard",
            }
            tasks.append(t1b)
            dependencies[t1b_id] = [t1_id]
            all_skills.update(t1b["required_capabilities"])
            m1_tasks.append(t1b_id)

        milestones.append(Milestone(m1_id, "Discovery & Scoping", "Perumusan spesifikasi teknis dan batasan sistem", m1_tasks, order=1))

        # --- Milestone 2: Architecture & Design ---
        m2_id = f"m2_{objective.id}_design"
        t2_id = f"{objective.id}_t2_arch"
        prev_dep = m1_tasks[-1]
        t2 = {
            "task_id": t2_id,
            "project_id": proj_id,
            "milestone_id": m2_id,
            "title": f"Perancangan Arsitektur & Struktur Data: {objective.title}",
            "description": "Desain skema data, diagram alur, dan antarmuka komponen.",
            "priority": 8,
            "preferred_role": "planner",
            "required_capabilities": ["software_architecture", "implementation_planning"],
            "model_tier": "strong",
        }
        tasks.append(t2)
        dependencies[t2_id] = [prev_dep]
        all_skills.update(t2["required_capabilities"])

        milestones.append(Milestone(m2_id, "Desain & Arsitektur", "Desain modular arsitektur sistem dan cetak biru data", [t2_id], order=2))

        # --- Milestone 3: Implementation ---
        m3_id = f"m3_{objective.id}_impl"
        m3_tasks = []
        t3_id = f"{objective.id}_t3_backend"
        t3 = {
            "task_id": t3_id,
            "project_id": proj_id,
            "milestone_id": m3_id,
            "title": f"Implementasi Modul Inti & Logika Bisnis: {objective.title}",
            "description": "Penulisan kode Python backend, handler fungsional, dan modul layanan.",
            "priority": 7,
            "preferred_role": "developer",
            "required_capabilities": ["python", "modular_coding", "debugging"],
            "model_tier": "strong",
        }
        tasks.append(t3)
        dependencies[t3_id] = [t2_id]
        all_skills.update(t3["required_capabilities"])
        m3_tasks.append(t3_id)

        if not is_simple:
            t3b_id = f"{objective.id}_t3b_integration"
            t3b = {
                "task_id": t3b_id,
                "project_id": proj_id,
                "milestone_id": m3_id,
                "title": f"Konstruksi Antarmuka & Integrasi API: {objective.title}",
                "description": "Pengembangan antarmuka visual, konektor API, dan penanganan status respons.",
                "priority": 6,
                "preferred_role": "developer",
                "required_capabilities": ["python", "modular_coding"],
                "model_tier": "standard",
            }
            tasks.append(t3b)
            dependencies[t3b_id] = [t3_id]
            all_skills.update(t3b["required_capabilities"])
            m3_tasks.append(t3b_id)

        milestones.append(Milestone(m3_id, "Implementasi Modul", "Pengembangan modul perangkat lunak dan penulisan kode sumber", m3_tasks, order=3))

        # --- Milestone 4: Testing & QA ---
        m4_id = f"m4_{objective.id}_qa"
        t4_id = f"{objective.id}_t4_test"
        t4 = {
            "task_id": t4_id,
            "project_id": proj_id,
            "milestone_id": m4_id,
            "title": f"Pengujian Otomatis & Validasi Kualitas: {objective.title}",
            "description": "Eksekusi pengujian fungsionalitas, uji regresi, dan validasi kriteria penerimaan.",
            "priority": 5,
            "preferred_role": "qa",
            "required_capabilities": ["automated_testing", "code_review", "bug_diagnosis"],
            "model_tier": "standard",
        }
        tasks.append(t4)
        dependencies[t4_id] = [m3_tasks[-1]]
        all_skills.update(t4["required_capabilities"])

        milestones.append(Milestone(m4_id, "Testing & QA", "Verifikasi kualitas kode dan pengujian menyeluruh", [t4_id], order=4))

        # --- Milestone 5: Deployment & Delivery ---
        m5_id = f"m5_{objective.id}_deploy"
        t5_id = f"{objective.id}_t5_release"
        t5 = {
            "task_id": t5_id,
            "project_id": proj_id,
            "milestone_id": m5_id,
            "title": f"Packaging & Deliverable Release: {objective.title}",
            "description": "Kompilasi dokumentasi rilis, packaging artefak, dan kesiapan operasional.",
            "priority": 4,
            "preferred_role": "developer",
            "required_capabilities": ["syntax_validation", "unit_generation"],
            "model_tier": "cheap",
        }
        tasks.append(t5)
        dependencies[t5_id] = [t4_id]
        all_skills.update(t5["required_capabilities"])

        milestones.append(Milestone(m5_id, "Packaging & Release", "Persiapan rilis dan finalisasi artefak siap guna", [t5_id], order=5))

        cost = round(len(tasks) * 0.003, 4)
        return ExecutionPlan(
            id=plan_id,
            objective_id=objective.id,
            milestones=milestones,
            tasks=tasks,
            dependencies=dependencies,
            estimated_cost=cost,
            required_skills=sorted(list(all_skills)),
            metadata={
                "strategy": self.strategy_name,
                "domain": self.objective_type.value,
                "complexity": analysis.complexity.value,
            },
        )


class ResearchPlanningStrategy(PlanningStrategy):
    """5-phase research decomposition:
    Scope -> Data Collection -> Analysis -> Synthesis -> Report.
    """
    strategy_name = "research_inquiry"
    objective_type = ObjectiveType.RESEARCH

    def plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
        organization: Optional[Organization] = None,
    ) -> ExecutionPlan:
        plan_id = f"plan_res_{objective.id}_{int(time.time())}"
        proj_id = objective.project_id or objective.id
        milestones: list[Milestone] = []
        tasks: list[dict] = []
        dependencies: dict[str, list[str]] = {}
        all_skills: set[str] = set()

        # Phase 1: Scope & Hypothesis
        t1_id = f"{objective.id}_res1_scope"
        t1 = {
            "task_id": t1_id,
            "project_id": proj_id,
            "milestone_id": "m1_scope",
            "title": f"Perumusan Hipotesis & Batasan Riset: {objective.title}",
            "description": "Definisi pertanyaan kunci riset, parameter investigasi, dan tolok ukur validasi.",
            "priority": 10,
            "preferred_role": "conceptor",
            "required_capabilities": ["requirements_analysis", "acceptance_criteria"],
            "model_tier": "strong",
        }
        tasks.append(t1)
        dependencies[t1_id] = []
        all_skills.update(t1["required_capabilities"])
        milestones.append(Milestone("m1_scope", "Lingkup & Hipotesis", "Definisi parameter dan batasan riset", [t1_id], order=1))

        # Phase 2: Data Collection
        t2_id = f"{objective.id}_res2_data"
        t2 = {
            "task_id": t2_id,
            "project_id": proj_id,
            "milestone_id": "m2_collect",
            "title": f"Pengumpulan Data & Pemetaan Sumber: {objective.title}",
            "description": "Inventarisasi data primer/sekunder, riset kompetitor, dan kompilasi fakta.",
            "priority": 8,
            "preferred_role": "conceptor",
            "required_capabilities": ["user_stories", "technical_design"],
            "model_tier": "standard",
        }
        tasks.append(t2)
        dependencies[t2_id] = [t1_id]
        all_skills.update(t2["required_capabilities"])
        milestones.append(Milestone("m2_collect", "Pengumpulan Data", "Pengumpulan fakta dan studi literatur/lapangan", [t2_id], order=2))

        # Phase 3: Qualitative / Quantitative Analysis
        t3_id = f"{objective.id}_res3_analysis"
        t3 = {
            "task_id": t3_id,
            "project_id": proj_id,
            "milestone_id": "m3_analysis",
            "title": f"Analisis Pola & Komparasi Kritis: {objective.title}",
            "description": "Ekstraksi pola data, komparasi kekuatan/kelemahan kompetitor, dan benchmarking.",
            "priority": 7,
            "preferred_role": "planner",
            "required_capabilities": ["software_architecture", "implementation_planning"],
            "model_tier": "strong",
        }
        tasks.append(t3)
        dependencies[t3_id] = [t2_id]
        all_skills.update(t3["required_capabilities"])
        milestones.append(Milestone("m3_analysis", "Analisis Data", "Pemrosesan komparatif dan analisis kritis", [t3_id], order=3))

        # Phase 4: Synthesis & Insights
        t4_id = f"{objective.id}_res4_synthesis"
        t4 = {
            "task_id": t4_id,
            "project_id": proj_id,
            "milestone_id": "m4_synthesis",
            "title": f"Sintesis Temuan & Perumusan Solusi: {objective.title}",
            "description": "Penyusunan temuan inti, visualisasi kesimpulan, dan rekomendasi langkah lanjut.",
            "priority": 6,
            "preferred_role": "planner",
            "required_capabilities": ["dependency_graph", "topological_sort"],
            "model_tier": "standard",
        }
        tasks.append(t4)
        dependencies[t4_id] = [t3_id]
        all_skills.update(t4["required_capabilities"])
        milestones.append(Milestone("m4_synthesis", "Sintesis Temuan", "Formulasi wawasan strategis dan kesimpulan", [t4_id], order=4))

        # Phase 5: Final Report & Presentation
        t5_id = f"{objective.id}_res5_report"
        t5 = {
            "task_id": t5_id,
            "project_id": proj_id,
            "milestone_id": "m5_report",
            "title": f"Penyusunan Laporan Riset Lengkap: {objective.title}",
            "description": "Kompilasi dokumen laporan akhir riset beserta ringkasan eksekutif.",
            "priority": 5,
            "preferred_role": "qa",
            "required_capabilities": ["code_review", "automated_testing"],
            "model_tier": "cheap",
        }
        tasks.append(t5)
        dependencies[t5_id] = [t4_id]
        all_skills.update(t5["required_capabilities"])
        milestones.append(Milestone("m5_report", "Laporan Riset Akhir", "Kompilasi deliverable laporan riset komprehensif", [t5_id], order=5))

        cost = round(len(tasks) * 0.0028, 4)
        return ExecutionPlan(
            id=plan_id,
            objective_id=objective.id,
            milestones=milestones,
            tasks=tasks,
            dependencies=dependencies,
            estimated_cost=cost,
            required_skills=sorted(list(all_skills)),
            metadata={
                "strategy": self.strategy_name,
                "domain": self.objective_type.value,
                "complexity": analysis.complexity.value,
            },
        )


class MarketingPlanningStrategy(PlanningStrategy):
    """5-phase marketing campaign decomposition:
    Research -> Strategy -> Content -> Distribution -> Measurement.
    """
    strategy_name = "marketing_campaign"
    objective_type = ObjectiveType.MARKETING

    def plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
        organization: Optional[Organization] = None,
    ) -> ExecutionPlan:
        plan_id = f"plan_mkt_{objective.id}_{int(time.time())}"
        proj_id = objective.project_id or objective.id
        milestones: list[Milestone] = []
        tasks: list[dict] = []
        dependencies: dict[str, list[str]] = {}
        all_skills: set[str] = set()

        # 1. Market Research & Persona
        t1_id = f"{objective.id}_mkt1_persona"
        t1 = {
            "task_id": t1_id,
            "project_id": proj_id,
            "milestone_id": "m1_research",
            "title": f"Riset Persona & Audiens Sasaran: {objective.title}",
            "description": "Identifikasi segmen pasar, pain points pelanggan, dan profil persona pembeli.",
            "priority": 10,
            "preferred_role": "conceptor",
            "required_capabilities": ["requirements_analysis", "user_stories"],
            "model_tier": "standard",
        }
        tasks.append(t1)
        dependencies[t1_id] = []
        all_skills.update(t1["required_capabilities"])
        milestones.append(Milestone("m1_research", "Riset Audiens & Persona", "Pemetaan segmen audiens dan kebutuhan pasar", [t1_id], order=1))

        # 2. Campaign Strategy & Messaging
        t2_id = f"{objective.id}_mkt2_strategy"
        t2 = {
            "task_id": t2_id,
            "project_id": proj_id,
            "milestone_id": "m2_strategy",
            "title": f"Penyusunan Strategi & Pesan Kunci: {objective.title}",
            "description": "Value proposition, positioning statement, dan rencana narasi kampanye.",
            "priority": 9,
            "preferred_role": "pm",
            "required_capabilities": ["planning", "prioritization"],
            "model_tier": "strong",
        }
        tasks.append(t2)
        dependencies[t2_id] = [t1_id]
        all_skills.update(t2["required_capabilities"])
        milestones.append(Milestone("m2_strategy", "Strategi & Pesan", "Penetapan positioning dan strategi kampanye", [t2_id], order=2))

        # 3. Creative Content Production
        t3_id = f"{objective.id}_mkt3_creative"
        t3 = {
            "task_id": t3_id,
            "project_id": proj_id,
            "milestone_id": "m3_content",
            "title": f"Produksi Naskah & Aset Visual Pemasaran: {objective.title}",
            "description": "Pembuatan copywriting iklan, materi landing page, dan call-to-action promosi.",
            "priority": 7,
            "preferred_role": "conceptor",
            "required_capabilities": ["technical_design", "acceptance_criteria"],
            "model_tier": "standard",
        }
        tasks.append(t3)
        dependencies[t3_id] = [t2_id]
        all_skills.update(t3["required_capabilities"])
        milestones.append(Milestone("m3_content", "Produksi Konten", "Pembuatan naskah iklan dan materi promosi", [t3_id], order=3))

        # 4. Distribution Channel Setup
        t4_id = f"{objective.id}_mkt4_channels"
        t4 = {
            "task_id": t4_id,
            "project_id": proj_id,
            "milestone_id": "m4_distribution",
            "title": f"Rencana Saluran Distribusi & Jadwal Rilis: {objective.title}",
            "description": "Pemetaan channel media sosial, email outreach, dan kalender editorial kampanye.",
            "priority": 6,
            "preferred_role": "pm",
            "required_capabilities": ["task_breakdown", "handoff"],
            "model_tier": "cheap",
        }
        tasks.append(t4)
        dependencies[t4_id] = [t3_id]
        all_skills.update(t4["required_capabilities"])
        milestones.append(Milestone("m4_distribution", "Distribusi Saluran", "Perencanaan channel publikasi dan jadwal rilis", [t4_id], order=4))

        # 5. Performance Measurement & KPIs
        t5_id = f"{objective.id}_mkt5_kpi"
        t5 = {
            "task_id": t5_id,
            "project_id": proj_id,
            "milestone_id": "m5_metrics",
            "title": f"Metrik Keberhasilan & Panduan Evaluasi: {objective.title}",
            "description": "Perumusan target konversi, CAC/LTV benchmark, dan kerangka pelacakan hasil.",
            "priority": 5,
            "preferred_role": "qa",
            "required_capabilities": ["automated_testing", "code_review"],
            "model_tier": "standard",
        }
        tasks.append(t5)
        dependencies[t5_id] = [t4_id]
        all_skills.update(t5["required_capabilities"])
        milestones.append(Milestone("m5_metrics", "Pengukuran Kinerja", "Penetapan KPI kampanye dan kerangka analisis", [t5_id], order=5))

        cost = round(len(tasks) * 0.0027, 4)
        return ExecutionPlan(
            id=plan_id,
            objective_id=objective.id,
            milestones=milestones,
            tasks=tasks,
            dependencies=dependencies,
            estimated_cost=cost,
            required_skills=sorted(list(all_skills)),
            metadata={
                "strategy": self.strategy_name,
                "domain": self.objective_type.value,
                "complexity": analysis.complexity.value,
            },
        )


class ContentPlanningStrategy(PlanningStrategy):
    """5-phase content publishing decomposition:
    Brief -> Research -> Drafting -> Review -> Publishing.
    """
    strategy_name = "content_publishing"
    objective_type = ObjectiveType.CONTENT

    def plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
        organization: Optional[Organization] = None,
    ) -> ExecutionPlan:
        plan_id = f"plan_cnt_{objective.id}_{int(time.time())}"
        proj_id = objective.project_id or objective.id
        milestones: list[Milestone] = []
        tasks: list[dict] = []
        dependencies: dict[str, list[str]] = {}
        all_skills: set[str] = set()

        # 1. Brief & Editorial Goals
        t1_id = f"{objective.id}_cnt1_brief"
        t1 = {
            "task_id": t1_id,
            "project_id": proj_id,
            "milestone_id": "m1_brief",
            "title": f"Penyusunan Editorial Brief & Sasaran Pembaca: {objective.title}",
            "description": "Target pesan, tone of voice, gaya penulisan, dan poin kunci naskah.",
            "priority": 10,
            "preferred_role": "pm",
            "required_capabilities": ["task_breakdown", "prioritization"],
            "model_tier": "standard",
        }
        tasks.append(t1)
        dependencies[t1_id] = []
        all_skills.update(t1["required_capabilities"])
        milestones.append(Milestone("m1_brief", "Editorial Brief", "Perumusan panduan gaya dan sasaran naskah", [t1_id], order=1))

        # 2. Outline & Subtopics
        t2_id = f"{objective.id}_cnt2_outline"
        t2 = {
            "task_id": t2_id,
            "project_id": proj_id,
            "milestone_id": "m2_outline",
            "title": f"Riset Materi & Struktur Kerangka Naskah: {objective.title}",
            "description": "Pengumpulan referensi, struktur bab/sub-topik, dan alur penjelasan logis.",
            "priority": 8,
            "preferred_role": "conceptor",
            "required_capabilities": ["requirements_analysis", "technical_design"],
            "model_tier": "standard",
        }
        tasks.append(t2)
        dependencies[t2_id] = [t1_id]
        all_skills.update(t2["required_capabilities"])
        milestones.append(Milestone("m2_outline", "Kerangka Naskah", "Penyusunan outline terstruktur dan studi referensi", [t2_id], order=2))

        # 3. Content Drafting / Production
        t3_id = f"{objective.id}_cnt3_draft"
        t3 = {
            "task_id": t3_id,
            "project_id": proj_id,
            "milestone_id": "m3_draft",
            "title": f"Penulisan Draft Lengkap Konten: {objective.title}",
            "description": "Penyusunan naskah komprehensif, artikel, atau dokumen materi publikasi.",
            "priority": 7,
            "preferred_role": "conceptor",
            "required_capabilities": ["user_stories", "acceptance_criteria"],
            "model_tier": "strong",
        }
        tasks.append(t3)
        dependencies[t3_id] = [t2_id]
        all_skills.update(t3["required_capabilities"])
        milestones.append(Milestone("m3_draft", "Penulisan Naskah", "Produksi draft konten utama secara lengkap", [t3_id], order=3))

        # 4. Review & Editorial Quality
        t4_id = f"{objective.id}_cnt4_review"
        t4 = {
            "task_id": t4_id,
            "project_id": proj_id,
            "milestone_id": "m4_review",
            "title": f"Penyuntingan & Verifikasi Kualitas Gaya: {objective.title}",
            "description": "Proofreading naskah, cek akurasi data, konsistensi istilah, dan perbaikan editorial.",
            "priority": 6,
            "preferred_role": "qa",
            "required_capabilities": ["code_review", "bug_diagnosis"],
            "model_tier": "standard",
        }
        tasks.append(t4)
        dependencies[t4_id] = [t3_id]
        all_skills.update(t4["required_capabilities"])
        milestones.append(Milestone("m4_review", "Penyuntingan Editorial", "Pemeriksaan akurasi bahasa dan kelayakan kualitas", [t4_id], order=4))

        # 5. Packaging & Deliverable Publication
        t5_id = f"{objective.id}_cnt5_publish"
        t5 = {
            "task_id": t5_id,
            "project_id": proj_id,
            "milestone_id": "m5_publish",
            "title": f"Packaging Format Akhir & Publikasi: {objective.title}",
            "description": "Format Markdown/PDF/Docx deliverable dan pengarsipan artefak deliverable.",
            "priority": 5,
            "preferred_role": "developer",
            "required_capabilities": ["modular_coding", "syntax_validation"],
            "model_tier": "cheap",
        }
        tasks.append(t5)
        dependencies[t5_id] = [t4_id]
        all_skills.update(t5["required_capabilities"])
        milestones.append(Milestone("m5_publish", "Packaging & Publikasi", "Ekspor deliverable ke format akhir publikasi", [t5_id], order=5))

        cost = round(len(tasks) * 0.0025, 4)
        return ExecutionPlan(
            id=plan_id,
            objective_id=objective.id,
            milestones=milestones,
            tasks=tasks,
            dependencies=dependencies,
            estimated_cost=cost,
            required_skills=sorted(list(all_skills)),
            metadata={
                "strategy": self.strategy_name,
                "domain": self.objective_type.value,
                "complexity": analysis.complexity.value,
            },
        )


class AnalysisPlanningStrategy(PlanningStrategy):
    """5-phase data analytics decomposition:
    Data Collection -> Processing -> Modeling/Querying -> Validation -> Recommendations.
    """
    strategy_name = "data_analytics"
    objective_type = ObjectiveType.ANALYSIS

    def plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
        organization: Optional[Organization] = None,
    ) -> ExecutionPlan:
        plan_id = f"plan_anl_{objective.id}_{int(time.time())}"
        proj_id = objective.project_id or objective.id
        milestones: list[Milestone] = []
        tasks: list[dict] = []
        dependencies: dict[str, list[str]] = {}
        all_skills: set[str] = set()

        # 1. Ingestion / Sourcing
        t1_id = f"{objective.id}_anl1_source"
        t1 = {
            "task_id": t1_id,
            "project_id": proj_id,
            "milestone_id": "m1_source",
            "title": f"Inventarisasi Sumber & Ekstraksi Data: {objective.title}",
            "description": "Pengumpulan data masukan, ekstraksi tabel transaksi, dan validasi skema input.",
            "priority": 10,
            "preferred_role": "developer",
            "required_capabilities": ["python", "modular_coding"],
            "model_tier": "standard",
        }
        tasks.append(t1)
        dependencies[t1_id] = []
        all_skills.update(t1["required_capabilities"])
        milestones.append(Milestone("m1_source", "Ekstraksi Data", "Pengumpulan dan inventarisasi data mentah", [t1_id], order=1))

        # 2. Cleaning & Processing
        t2_id = f"{objective.id}_anl2_clean"
        t2 = {
            "task_id": t2_id,
            "project_id": proj_id,
            "milestone_id": "m2_process",
            "title": f"Pembersihan Data & Transformasi Normalisasi: {objective.title}",
            "description": "Penanganan missing values, deteksi anomali, agregasi data, dan standarisasi format.",
            "priority": 8,
            "preferred_role": "developer",
            "required_capabilities": ["python", "debugging"],
            "model_tier": "standard",
        }
        tasks.append(t2)
        dependencies[t2_id] = [t1_id]
        all_skills.update(t2["required_capabilities"])
        milestones.append(Milestone("m2_process", "Pembersihan Data", "Normalisasi dan penyaringan dataset analitik", [t2_id], order=2))

        # 3. Modeling / Statistical Analysis
        t3_id = f"{objective.id}_anl3_model"
        t3 = {
            "task_id": t3_id,
            "project_id": proj_id,
            "milestone_id": "m3_analysis",
            "title": f"Pemodelan Analitik & Kalkulasi Tren: {objective.title}",
            "description": "Kalkulasi metrik kunci, korelasi statistik, pengujian hipotesis, dan identifikasi pola.",
            "priority": 7,
            "preferred_role": "planner",
            "required_capabilities": ["software_architecture", "topological_sort"],
            "model_tier": "strong",
        }
        tasks.append(t3)
        dependencies[t3_id] = [t2_id]
        all_skills.update(t3["required_capabilities"])
        milestones.append(Milestone("m3_analysis", "Kalkulasi Analitik", "Pemodelan komparatif dan kalkulasi statistik", [t3_id], order=3))

        # 4. Result Validation & Quality Check
        t4_id = f"{objective.id}_anl4_validate"
        t4 = {
            "task_id": t4_id,
            "project_id": proj_id,
            "milestone_id": "m4_validate",
            "title": f"Validasi Silang & Rekonsiliasi Hasil: {objective.title}",
            "description": "Pemeriksaan kebenaran matematis metrik, sanity check angka, dan verifikasi kriteria.",
            "priority": 6,
            "preferred_role": "qa",
            "required_capabilities": ["automated_testing", "code_review"],
            "model_tier": "standard",
        }
        tasks.append(t4)
        dependencies[t4_id] = [t3_id]
        all_skills.update(t4["required_capabilities"])
        milestones.append(Milestone("m4_validate", "Validasi Hasil", "Uji silang akurasi data dan rekonsiliasi angka", [t4_id], order=4))

        # 5. Strategic Insights & Action Plan
        t5_id = f"{objective.id}_anl5_report"
        t5 = {
            "task_id": t5_id,
            "project_id": proj_id,
            "milestone_id": "m5_report",
            "title": f"Perumusan Insight Strategis & Dashboard Summary: {objective.title}",
            "description": "Penyusunan laporan eksekutif, visualisasi kesimpulan, dan rekomendasi actionable.",
            "priority": 5,
            "preferred_role": "pm",
            "required_capabilities": ["planning", "handoff"],
            "model_tier": "strong",
        }
        tasks.append(t5)
        dependencies[t5_id] = [t4_id]
        all_skills.update(t5["required_capabilities"])
        milestones.append(Milestone("m5_report", "Rekomendasi Strategis", "Penyusunan wawasan bisnis dan laporan tindakan", [t5_id], order=5))

        cost = round(len(tasks) * 0.003, 4)
        return ExecutionPlan(
            id=plan_id,
            objective_id=objective.id,
            milestones=milestones,
            tasks=tasks,
            dependencies=dependencies,
            estimated_cost=cost,
            required_skills=sorted(list(all_skills)),
            metadata={
                "strategy": self.strategy_name,
                "domain": self.objective_type.value,
                "complexity": analysis.complexity.value,
            },
        )


class GeneralPlanningStrategy(PlanningStrategy):
    """Conservative 4-phase fallback strategy for arbitrary objectives:
    Scoping -> Planning -> Execution -> Review.
    """
    strategy_name = "general_purpose"
    objective_type = ObjectiveType.GENERAL

    def plan(
        self,
        objective: Objective,
        analysis: ObjectiveAnalysis,
        organization: Optional[Organization] = None,
    ) -> ExecutionPlan:
        plan_id = f"plan_gen_{objective.id}_{int(time.time())}"
        proj_id = objective.project_id or objective.id
        milestones: list[Milestone] = []
        tasks: list[dict] = []
        dependencies: dict[str, list[str]] = {}
        all_skills: set[str] = set()

        # Milestone 1: Scoping
        t1_id = f"{objective.id}_gen1_scope"
        t1 = {
            "task_id": t1_id,
            "project_id": proj_id,
            "milestone_id": "m1_scope",
            "title": f"Definisi Sasaran & Kebutuhan Kunci: {objective.title}",
            "description": f"Penyusunan ruang lingkup dan batasan deliverable untuk {objective.title}.",
            "priority": 10,
            "preferred_role": "conceptor",
            "required_capabilities": ["requirements_analysis", "acceptance_criteria"],
            "model_tier": "standard",
        }
        tasks.append(t1)
        dependencies[t1_id] = []
        all_skills.update(t1["required_capabilities"])
        milestones.append(Milestone("m1_scope", "Definisi Sasaran", "Perumusan batasan dan kebutuhan objektif", [t1_id], order=1))

        # Milestone 2: Planning & Setup
        t2_id = f"{objective.id}_gen2_plan"
        t2 = {
            "task_id": t2_id,
            "project_id": proj_id,
            "milestone_id": "m2_setup",
            "title": f"Perencanaan Alur Kerja & Sumber Daya: {objective.title}",
            "description": "Penyusunan jadwal, alokasi tugas teknis, dan rancangan keluaran.",
            "priority": 8,
            "preferred_role": "planner",
            "required_capabilities": ["software_architecture", "implementation_planning"],
            "model_tier": "standard",
        }
        tasks.append(t2)
        dependencies[t2_id] = [t1_id]
        all_skills.update(t2["required_capabilities"])
        milestones.append(Milestone("m2_setup", "Perencanaan Alur", "Perancangan langkah teknis dan spesifikasi", [t2_id], order=2))

        # Milestone 3: Execution
        t3_id = f"{objective.id}_gen3_exec"
        t3 = {
            "task_id": t3_id,
            "project_id": proj_id,
            "milestone_id": "m3_exec",
            "title": f"Eksekusi & Konstruksi Deliverable: {objective.title}",
            "description": "Pengembangan komponen inti dan penyusunan deliverable utama objektif.",
            "priority": 6,
            "preferred_role": "developer",
            "required_capabilities": ["python", "modular_coding", "debugging"],
            "model_tier": "strong",
        }
        tasks.append(t3)
        dependencies[t3_id] = [t2_id]
        all_skills.update(t3["required_capabilities"])
        milestones.append(Milestone("m3_exec", "Eksekusi Utama", "Konstruksi dan pengerjaan deliverable inti", [t3_id], order=3))

        # Milestone 4: Review & Finalization
        t4_id = f"{objective.id}_gen4_review"
        t4 = {
            "task_id": t4_id,
            "project_id": proj_id,
            "milestone_id": "m4_review",
            "title": f"Tinjauan Kualitas & Verifikasi Penerimaan: {objective.title}",
            "description": "Pemeriksaan deliverable terhadap kriteria penerimaan dan penyusunan catatan akhir.",
            "priority": 5,
            "preferred_role": "qa",
            "required_capabilities": ["automated_testing", "code_review"],
            "model_tier": "standard",
        }
        tasks.append(t4)
        dependencies[t4_id] = [t3_id]
        all_skills.update(t4["required_capabilities"])
        milestones.append(Milestone("m4_review", "Evaluasi Akhir", "Pemeriksaan pemenuhan kriteria deliverable", [t4_id], order=4))

        cost = round(len(tasks) * 0.0025, 4)
        return ExecutionPlan(
            id=plan_id,
            objective_id=objective.id,
            milestones=milestones,
            tasks=tasks,
            dependencies=dependencies,
            estimated_cost=cost,
            required_skills=sorted(list(all_skills)),
            metadata={
                "strategy": self.strategy_name,
                "domain": self.objective_type.value,
                "complexity": analysis.complexity.value,
            },
        )


def get_strategy_for_type(obj_type: ObjectiveType) -> PlanningStrategy:
    """Factory helper returning appropriate strategy instance for objective domain."""
    strategy_map = {
        ObjectiveType.SOFTWARE: SoftwarePlanningStrategy(),
        ObjectiveType.RESEARCH: ResearchPlanningStrategy(),
        ObjectiveType.MARKETING: MarketingPlanningStrategy(),
        ObjectiveType.CONTENT: ContentPlanningStrategy(),
        ObjectiveType.ANALYSIS: AnalysisPlanningStrategy(),
        ObjectiveType.GENERAL: GeneralPlanningStrategy(),
    }
    return strategy_map.get(obj_type, GeneralPlanningStrategy())

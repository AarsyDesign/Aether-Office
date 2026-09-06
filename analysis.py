"""Objective Analysis & Intelligence for Phase 9 Adaptive Planning.

Provides domain classification, complexity determination, ambiguity detection,
and risk assessment to inform adaptive planning strategies.
"""

from __future__ import annotations
import uuid
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from objectives import Objective
from workforce import Organization, STATUS_ACTIVE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ObjectiveType(str, Enum):
    """Domain classification for business objectives."""
    SOFTWARE = "SOFTWARE"
    RESEARCH = "RESEARCH"
    MARKETING = "MARKETING"
    CONTENT = "CONTENT"
    ANALYSIS = "ANALYSIS"
    GENERAL = "GENERAL"


class ObjectiveComplexity(str, Enum):
    """Complexity tiers defining decomposition depth."""
    SIMPLE = "SIMPLE"        # ~3-5 tasks
    STANDARD = "STANDARD"    # ~5-15 tasks
    COMPLEX = "COMPLEX"      # 15+ tasks


class RiskType(str, Enum):
    """Identified operational and strategic risk vectors."""
    HIGH_COMPLEXITY = "HIGH_COMPLEXITY"
    DEEP_DEPENDENCY = "DEEP_DEPENDENCY"
    SKILL_SHORTAGE = "SKILL_SHORTAGE"
    BUDGET_RISK = "BUDGET_RISK"
    DEADLINE_RISK = "DEADLINE_RISK"
    SINGLE_POINT_OF_FAILURE = "SINGLE_POINT_OF_FAILURE"
    AMBIGUOUS_REQUIREMENT = "AMBIGUOUS_REQUIREMENT"


@dataclass
class ClarificationRequest:
    """A blocking or non-blocking inquiry required to resolve ambiguity."""
    question: str
    reason: str
    blocking: bool = True
    priority: str = "HIGH"

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "reason": self.reason,
            "blocking": self.blocking,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ClarificationRequest:
        return cls(
            question=d["question"],
            reason=d["reason"],
            blocking=bool(d.get("blocking", True)),
            priority=d.get("priority", "HIGH"),
        )


@dataclass
class RiskAssessment:
    """Identified risk evaluation and suggested mitigation."""
    risk_type: RiskType
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    description: str
    mitigation: str = ""

    def to_dict(self) -> dict:
        return {
            "risk_type": self.risk_type.value if isinstance(self.risk_type, RiskType) else str(self.risk_type),
            "severity": self.severity,
            "description": self.description,
            "mitigation": self.mitigation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RiskAssessment:
        return cls(
            risk_type=RiskType(d["risk_type"]),
            severity=d.get("severity", "MEDIUM"),
            description=d.get("description", ""),
            mitigation=d.get("mitigation", ""),
        )


@dataclass
class ObjectiveAnalysis:
    """Consolidated intelligence report for an Objective."""
    objective_id: str
    objective_type: ObjectiveType
    complexity: ObjectiveComplexity
    ambiguity_score: float = 0.0  # 0.0 (crystal clear) to 1.0 (completely ambiguous)
    needs_clarification: bool = False
    clarifications: list[ClarificationRequest] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    estimated_deliverables: list[str] = field(default_factory=list)
    estimated_duration: float = 0.0  # In estimated execution hours or ticks
    estimated_cost: float = 0.0      # In USD
    risks: list[RiskAssessment] = field(default_factory=list)
    confidence: float = 1.0          # 0.0 to 1.0 (>=0.80 HIGH, 0.60-0.79 MEDIUM, <0.60 LOW)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    @property
    def ambiguity(self) -> float:
        return self.ambiguity_score

    @ambiguity.setter
    def ambiguity(self, val: float) -> None:
        self.ambiguity_score = val

    @property
    def confidence_level(self) -> str:
        if self.confidence >= 0.80:
            return "HIGH CONFIDENCE"
        if self.confidence >= 0.60:
            return "MEDIUM CONFIDENCE"
        return "LOW CONFIDENCE"

    def to_dict(self) -> dict:
        return {
            "objective_id": self.objective_id,
            "objective_type": self.objective_type.value,
            "complexity": self.complexity.value,
            "ambiguity": self.ambiguity_score,
            "ambiguity_score": self.ambiguity_score,
            "needs_clarification": self.needs_clarification,
            "clarifications": [c.to_dict() for c in self.clarifications],
            "required_capabilities": list(self.required_capabilities),
            "estimated_deliverables": list(self.estimated_deliverables),
            "estimated_duration": self.estimated_duration,
            "estimated_cost": self.estimated_cost,
            "risks": [r.to_dict() for r in self.risks],
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


class RiskAnalyzer:
    """Evaluates multi-dimensional risk vectors across workforce, budget, and scope."""

    @classmethod
    def analyze_risks(
        cls,
        objective: Objective,
        objective_type: ObjectiveType,
        complexity: ObjectiveComplexity,
        required_capabilities: list[str],
        estimated_cost: float,
        organization: Optional[Organization] = None,
        ambiguity_score: float = 0.0,
        estimated_duration: float = 24.0,
    ) -> list[RiskAssessment]:
        risks: list[RiskAssessment] = []

        # 1. Ambiguity Risk
        if ambiguity_score >= 0.40:
            risks.append(
                RiskAssessment(
                    risk_type=RiskType.AMBIGUOUS_REQUIREMENT,
                    severity="HIGH" if ambiguity_score >= 0.65 else "MEDIUM",
                    description=f"Objective memiliki skor ambiguitas tinggi ({ambiguity_score:.2f}). Kebutuhan belum cukup spesifik.",
                    mitigation="Ajukan klarifikasi kepada pemangku kepentingan sebelum mengeksekusi implementasi.",
                )
            )

        # 2. Complexity Risk
        if complexity == ObjectiveComplexity.COMPLEX:
            risks.append(
                RiskAssessment(
                    risk_type=RiskType.HIGH_COMPLEXITY,
                    severity="HIGH",
                    description="Kompleksitas tinggi membutuhkan koordinasi multi-fase dan banyak dependensi antar-tugas.",
                    mitigation="Bagi pekerjaan ke dalam milestone gating bertahap dan tinjau kemajuan berkala.",
                )
            )

        # 3. Budget Risk
        if objective.budget > 0:
            if estimated_cost > objective.budget:
                risks.append(
                    RiskAssessment(
                        risk_type=RiskType.BUDGET_RISK,
                        severity="CRITICAL",
                        description=(
                            f"Estimasi biaya (${estimated_cost:.2f}) melampaui batas anggaran "
                            f"yang dialokasikan (${objective.budget:.2f})."
                        ),
                        mitigation="Terapkan model hemat biaya (leaner models) atau pangkas tugas sekunder yang tidak esensial.",
                    )
                )
            elif estimated_cost >= (objective.budget * 0.85):
                risks.append(
                    RiskAssessment(
                        risk_type=RiskType.BUDGET_RISK,
                        severity="MEDIUM",
                        description=f"Estimasi biaya mendekati batas anggaran (${estimated_cost:.2f} / ${objective.budget:.2f}).",
                        mitigation="Pantau pemakaian token pada setiap detak penjadwalan.",
                    )
                )

        # 4. Deadline Risk
        if objective.deadline:
            try:
                # Basic deadline sanity check
                target_dt = datetime.fromisoformat(objective.deadline.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                remaining_hours = (target_dt - now_dt).total_seconds() / 3600.0
                if remaining_hours <= 0:
                    risks.append(
                        RiskAssessment(
                            risk_type=RiskType.DEADLINE_RISK,
                            severity="CRITICAL",
                            description="Tenggat waktu objektif telah kedaluwarsa atau kurang dari waktu yang dibutuhkan.",
                            mitigation="Perbarui tanggal tenggat waktu atau tingkatkan prioritas ke CRITICAL.",
                        )
                    )
                elif remaining_hours < 24.0 or remaining_hours < estimated_duration:
                    risks.append(
                        RiskAssessment(
                            risk_type=RiskType.DEADLINE_RISK,
                            severity="HIGH",
                            description=f"Sisa waktu sangat ketat ({remaining_hours:.1f} jam) dibandingkan estimasi pekerjaan.",
                            mitigation="Paralelkan tugas-tugas non-dependen dan fokuskan deliverable utama.",
                        )
                    )
            except Exception:
                pass

        # 5. Workforce & Capability Risks
        if organization:
            active_emps = [e for e in organization.employees.list() if e.status == STATUS_ACTIVE]
            available_caps: dict[str, int] = {}
            for emp in active_emps:
                for c in emp.capabilities:
                    c_low = c.lower()
                    available_caps[c_low] = available_caps.get(c_low, 0) + 1

            for req in required_capabilities:
                req_low = req.lower()
                matching_count = sum(count for cap, count in available_caps.items() if req_low in cap or cap in req_low)
                if matching_count == 0:
                    risks.append(
                        RiskAssessment(
                            risk_type=RiskType.SKILL_SHORTAGE,
                            severity="HIGH",
                            description=f"Keahlian '{req}' tidak dimiliki oleh personel aktif dalam workforce pool.",
                            mitigation=f"Lakukan hiring atau delegasikan ke role generalis dengan model penalaran kuat.",
                        )
                    )
                elif matching_count == 1:
                    risks.append(
                        RiskAssessment(
                            risk_type=RiskType.SINGLE_POINT_OF_FAILURE,
                            severity="LOW",
                            description=f"Hanya terdapat 1 karyawan aktif yang memiliki keahlian '{req}'.",
                            mitigation="Pastikan beban kerja personel tersebut tidak mengalami overload.",
                        )
                    )

        return risks


class ObjectiveAnalyzer:
    """Performs deep structural, domain, and risk analysis on an Objective."""

    # Weighted intent patterns per objective type
    TYPE_PATTERNS = {
        ObjectiveType.SOFTWARE: [
            (r"\b(aplikasi|software|sistem|fitur|backend|frontend|api|oauth|database|endpoint|kode|saas|service|login|auth|dashboard)\b", 3),
            (r"\b(landing page|website|portal|bot|mobile|ios|android|fullstack|refactor|debug|web app|web)\b", 2),
            (r"\b(build|develop|coding|test runner|framework)\b", 1),
        ],
        ObjectiveType.RESEARCH: [
            (r"\b(riset|penelitian|kompetitor|survey|studi|investigasi|benchmark|eksplorasi|perbandingan)\b", 3),
            (r"\b(market research|analisis pasar|tren industri|feasibility|kajian|literature)\b", 3),
            (r"\b(data sekunder|sumber data|studi kasus|komparasi)\b", 2),
        ],
        ObjectiveType.MARKETING: [
            (r"\b(marketing|pemasaran|campaign|kampanye|promosi|ads|iklan|leads|lead gen)\b", 3),
            (r"\b(branding|brand|penjualan|sales funnel|distribusi|akuisisi|growth)\b", 2),
            (r"\b(sosmed|social media|cta|conversion|konversi)\b", 2),
        ],
        ObjectiveType.CONTENT: [
            (r"\b(konten|artikel|blog|copywriting|tulisan|naskah|copy|postingan|katalog)\b", 3),
            (r"\b(newsletter|buku panduan|ebook|press release|caption|skrip)\b", 3),
            (r"\b(editing|proofreading|publikasi|draft)\b", 2),
        ],
        ObjectiveType.ANALYSIS: [
            (r"\b(analisis|analitik|metrik|kpi|reporting|laporan keuangan|churn|revenue|omset)\b", 3),
            (r"\b(tren penjualan|evaluasi data|statistik|korelasi|prediksi|dashboard bi)\b", 3),
            (r"\b(data cleaning|insight|rekomendasi strategis)\b", 2),
        ],
    }

    VAGUE_WORDS = {
        "bagus", "keren", "hebat", "cepat", "sesuatu", "modern", "oke", "mantap", "canggih",
        "lengkap", "terbaik", "good", "cool", "nice", "awesome", "simple",
    }

    def __init__(self, organization: Optional[Organization] = None):
        self.organization = organization

    def classify_type(self, title: Any, description: str = "") -> tuple[ObjectiveType, float]:
        """Classifies objective domain using weighted pattern scoring.
        Accepts either an Objective instance or (title, description) strings.
        Returns (ObjectiveType, confidence_score).
        """
        if isinstance(title, Objective) or (not isinstance(title, str) and hasattr(title, "title")):
            obj = title
            t_str = str(obj.title)
            description = str(getattr(obj, "description", "") or "")
        else:
            t_str = str(title or "")

        t_clean = t_str.strip().lower()
        d_clean = description.strip().lower()
        scores: dict[ObjectiveType, int] = {t: 0 for t in ObjectiveType}

        for obj_type, pattern_list in self.TYPE_PATTERNS.items():
            for pattern, weight in pattern_list:
                # Title matches have 2x multiplier since title conveys core intent
                t_matches = re.findall(pattern, t_clean)
                scores[obj_type] += len(t_matches) * weight * 2
                d_matches = re.findall(pattern, d_clean)
                scores[obj_type] += len(d_matches) * weight

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_type, top_score = sorted_scores[0]

        if top_score == 0:
            return ObjectiveType.GENERAL, 0.65

        total_score = sum(scores.values())
        confidence = min(0.95, round(top_score / max(1, total_score) * 0.7 + 0.3, 2))
        return top_type, confidence

    def classify_objective_type(self, title: Any, description: str = "") -> ObjectiveType:
        """Convenience alias returning only the classified ObjectiveType."""
        return self.classify_type(title, description)[0]

    def determine_complexity(
        self,
        title: Any,
        description: str = "",
        budget: float = 0.0,
        criteria_count: int = 0,
    ) -> ObjectiveComplexity:
        """Determines complexity tier based on scope, words, budget, and criteria count.
        Accepts either an Objective instance or explicit parameter fields.
        """
        if isinstance(title, Objective) or (not isinstance(title, str) and hasattr(title, "title")):
            obj = title
            t_str = str(obj.title)
            description = str(getattr(obj, "description", "") or "")
            budget = float(getattr(obj, "budget", 0.0) or 0.0)
            crit = getattr(obj, "acceptance_criteria", None)
            criteria_count = len(crit) if crit else 0
        else:
            t_str = str(title or "")

        text = f"{t_str} {description}".lower()
        words = len(text.split())

        # Indicators of high complexity
        complex_indicators = [
            "integrasi", "multi-tier", "enterprise", "arsitektur kompleks", "end-to-end",
            "fullstack", "microservices", "migrasi data", "distributed", "skala besar",
            "global", "keamanan tingkat tinggi", "oauth2", "20 kompetitor", "heterogen",
            "berskala besar", "multi-channel", "audit keamanan",
        ]
        complex_matches = sum(1 for ind in complex_indicators if ind in text)

        if complex_matches >= 2 or words > 80 or budget >= 250.0 or criteria_count >= 5:
            return ObjectiveComplexity.COMPLEX
        if complex_matches >= 1 or words > 25 or budget >= 75.0 or criteria_count >= 2:
            return ObjectiveComplexity.STANDARD
        return ObjectiveComplexity.SIMPLE

    def detect_ambiguity(
        self,
        title: Any,
        description: str = "",
        criteria_count: int = 0,
    ) -> tuple[float, list[ClarificationRequest]]:
        """Evaluates whether the objective specification is too ambiguous or vague.
        Accepts either an Objective instance or raw text fields.
        Returns (ambiguity_score [0.0-1.0], list of ClarificationRequests).
        """
        if isinstance(title, Objective) or (not isinstance(title, str) and hasattr(title, "title")):
            obj = title
            t_str = str(obj.title)
            description = str(getattr(obj, "description", "") or "")
            crit = getattr(obj, "acceptance_criteria", None)
            criteria_count = len(crit) if crit else 0
        else:
            t_str = str(title or "")

        title_clean = t_str.strip().lower()
        desc_clean = description.strip().lower()
        words = title_clean.split()
        requests: list[ClarificationRequest] = []

        ambiguity_score = 0.0

        vague_found = [w for w in words if w in self.VAGUE_WORDS]

        # Check 1: Extremely short or vague title without detailed description
        if len(words) <= 4 and len(desc_clean) < 20:
            if vague_found or len(desc_clean) == 0:
                ambiguity_score += 0.35
                requests.append(
                    ClarificationRequest(
                        question="Apa ruang lingkup spesifik dan siapa target pengguna dari objektif ini?",
                        reason="Judul sangat ringkas tanpa deskripsi rincian yang memadai.",
                        blocking=True,
                        priority="HIGH",
                    )
                )
            else:
                ambiguity_score += 0.15
                requests.append(
                    ClarificationRequest(
                        question="Dapatkah dielaborasi ruang lingkup spesifik dan target pengguna dari objektif ini?",
                        reason="Deskripsi singkat, elaborasi tambahan akan meningkatkan ketepatan luaran.",
                        blocking=False,
                        priority="LOW",
                    )
                )

        # Check 2: Heavy reliance on subjective/vague descriptors
        if vague_found:
            ambiguity_score += 0.25 * min(2, len(vague_found))
            requests.append(
                ClarificationRequest(
                    question=f"Dapatkah parameter atau kriteria keberhasilan '{', '.join(vague_found)}' didefinisikan secara spesifik?",
                    reason="Kata sifat subjektif memerlukan definisi kriteria penerimaan yang terukur.",
                    blocking=True,
                    priority="HIGH",
                )
            )

        # Check 3: Lack of acceptance criteria
        if criteria_count == 0:
            ambiguity_score += 0.20
            requests.append(
                ClarificationRequest(
                    question="Apakah ada kriteria penerimaan (acceptance criteria) atau format deliverable yang diwajibkan?",
                    reason="Kriteria penerimaan diperlukan agar evaluator dapat memvalidasi luaran akhir secara objektif.",
                    blocking=False,
                    priority="MEDIUM",
                )
            )

        ambiguity_score = min(1.0, round(ambiguity_score, 2))
        return ambiguity_score, requests

    def assess_ambiguity(
        self,
        title_or_obj: Any,
        description: str = "",
        criteria_count: int = 0,
    ) -> float:
        """Helper alias returning only the ambiguity score [0.0 - 1.0]."""
        return self.detect_ambiguity(title_or_obj, description, criteria_count)[0]

    def analyze(self, objective: Objective) -> ObjectiveAnalysis:
        """Runs comprehensive multi-dimensional intelligence analysis on the Objective."""
        crit_count = len(objective.acceptance_criteria) if objective.acceptance_criteria else 0

        # 1. Classify domain & type
        obj_type, type_confidence = self.classify_type(objective.title, objective.description)

        # 2. Complexity determination
        complexity = self.determine_complexity(
            title=objective.title,
            description=objective.description,
            budget=objective.budget,
            criteria_count=crit_count,
        )

        # 3. Ambiguity & Clarifications
        ambiguity_score, clarifications = self.detect_ambiguity(
            title=objective.title,
            description=objective.description,
            criteria_count=crit_count,
        )
        needs_clarification = ambiguity_score >= 0.50 or any(c.blocking for c in clarifications)

        # 4. Capability & Deliverable estimations per domain & complexity
        caps, deliverables = self._estimate_capabilities_and_deliverables(obj_type, complexity)

        # 5. Cost and duration estimation
        multiplier = 1.0
        if complexity == ObjectiveComplexity.SIMPLE:
            multiplier = 0.8
            est_duration = 2.0
            task_estimate = 4
        elif complexity == ObjectiveComplexity.STANDARD:
            multiplier = 1.5
            est_duration = 6.0
            task_estimate = 8
        else:
            multiplier = 3.0
            est_duration = 16.0
            task_estimate = 16

        estimated_cost = round(task_estimate * 0.0035 * multiplier, 4)

        # 6. Risk Assessment
        risks = RiskAnalyzer.analyze_risks(
            objective=objective,
            objective_type=obj_type,
            complexity=complexity,
            required_capabilities=caps,
            estimated_cost=estimated_cost,
            organization=self.organization,
            ambiguity_score=ambiguity_score,
            estimated_duration=est_duration,
        )

        # 7. Confidence Score (0.0 to 1.0)
        # Drops with ambiguity and unmitigated high risks
        confidence = type_confidence
        if ambiguity_score > 0.3:
            confidence -= (ambiguity_score * 0.35)
        critical_risks = sum(1 for r in risks if r.severity in ("HIGH", "CRITICAL"))
        if critical_risks > 0:
            confidence -= (critical_risks * 0.1)
        confidence = max(0.20, min(0.99, round(confidence, 2)))

        return ObjectiveAnalysis(
            objective_id=objective.id,
            objective_type=obj_type,
            complexity=complexity,
            ambiguity_score=ambiguity_score,
            needs_clarification=needs_clarification,
            clarifications=clarifications,
            required_capabilities=caps,
            estimated_deliverables=deliverables,
            estimated_duration=est_duration,
            estimated_cost=estimated_cost,
            risks=risks,
            confidence=confidence,
            metadata={
                "task_estimate": task_estimate,
                "domain_confidence": type_confidence,
            },
        )

    def _estimate_capabilities_and_deliverables(
        self,
        obj_type: ObjectiveType,
        complexity: ObjectiveComplexity,
    ) -> tuple[list[str], list[str]]:
        """Derives estimated skill capabilities and deliverables for domain & complexity."""
        if obj_type == ObjectiveType.SOFTWARE:
            caps = ["requirements_analysis", "software_architecture", "python", "modular_coding", "debugging", "automated_testing"]
            deliverables = ["Dokumen Spesifikasi Teknis", "Cetak Biru Arsitektur", "Source Code & Modul", "Laporan Hasil Pengujian QA"]
        elif obj_type == ObjectiveType.RESEARCH:
            caps = ["requirements_analysis", "task_breakdown", "planning", "code_review"]
            deliverables = ["Dokumen Ruang Lingkup Riset", "Kompilasi Data & Sumber", "Laporan Analisis & Sintesis Komprehensif"]
        elif obj_type == ObjectiveType.MARKETING:
            caps = ["requirements_analysis", "planning", "user_stories", "prioritization"]
            deliverables = ["Riset Target Audiens", "Strategi & Rencana Kampanye", "Aset Konten & Materi Distribusi"]
        elif obj_type == ObjectiveType.CONTENT:
            caps = ["requirements_analysis", "user_stories", "code_review"]
            deliverables = ["Brief & Kerangka Konten", "Draft Naskah Deliverable", "Dokumen Konten Terverifikasi & Final"]
        elif obj_type == ObjectiveType.ANALYSIS:
            caps = ["requirements_analysis", "software_architecture", "python", "debugging"]
            deliverables = ["Dataset Hasil Pemrosesan", "Model/Query Analisis", "Laporan Insight & Rekomendasi"]
        else:  # GENERAL
            caps = ["planning", "task_breakdown", "python", "automated_testing"]
            deliverables = ["Dokumen Perencanaan Sasaran", "Deliverable Utama Objektif", "Laporan Evaluasi & Review Akhir"]

        return caps, deliverables

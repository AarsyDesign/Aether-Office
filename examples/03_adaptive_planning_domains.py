"""Example 03: Multi-Domain Adaptive Planning Showcase

Shows how Aether Office dynamically adapts its planning strategy, milestone
breakdown, and task composition across 4 different domains:
1. Software Engineering
2. Market Research
3. Digital Marketing Campaign
4. Ambiguous Objective (triggers Clarification Gate)
"""

import sys

# Reconfigure stdout for UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from workforce import create_default_organization
from objectives import Objective
from adaptive_planner import AdaptiveObjectivePlanner


def main():
    print("=" * 75)
    print("🧠 AETHER OFFICE — EXAMPLE 03: MULTI-DOMAIN ADAPTIVE PLANNING SHOWCASE")
    print("=" * 75)

    org, _ = create_default_organization()
    planner = AdaptiveObjectivePlanner(organization=org)

    sample_objectives = [
        Objective(
            id="obj_sw",
            title="Bangun API microservices otentikasi JWT",
            description="Layanan backend login, register, refresh token, dan audit log dengan PostgreSQL.",
        ),
        Objective(
            id="obj_res",
            title="Riset 20 kompetitor AI Agent di pasar global",
            description="Studi literatur dan perbandingan fitur, struktur harga, latensi, dan target pasar.",
        ),
        Objective(
            id="obj_mkt",
            title="Kampanye pemasaran digital produk SaaS",
            description="Strategi peluncuran media sosial, optimasi conversion funnel, dan distribusi iklan berbayar.",
        ),
        Objective(
            id="obj_vague",
            title="Buat aplikasi yang bagus",
            description="",  # Intentionally ambiguous
        ),
    ]

    for idx, obj in enumerate(sample_objectives, 1):
        print(f"\n[{idx}] Objektif: '{obj.title}'")
        analysis = planner.analyze(obj)
        print(f"    Domain Terdeteksi: {analysis.objective_type.value}")
        print(f"    Kompleksitas     : {analysis.complexity.value}")
        print(f"    Skor Ambiguitas  : {analysis.ambiguity_score:.2f}")

        plan = planner.plan(obj)
        if not plan.is_valid and plan.metadata.get("needs_clarification"):
            print("    ⚠️  GERBANG KLARIFIKASI AKTIF: Objektif terlalu umum/ambigu.")
            for c in plan.metadata.get("clarifications", []):
                print(f"       Pertanyaan : {c.get('question')}")
                print(f"       Alasan     : {c.get('reason')}")
        else:
            print(f"    Strategi         : {plan.metadata.get('strategy')}")
            print(f"    Milestone Terbentuk ({len(plan.milestones)} tahap):")
            for m in plan.milestones:
                print(f"       • Milestone {m.order}: {m.name}")

    print("\n" + "=" * 75)
    print("✅ Sistem berhasil menyesuaikan strategi tanpa intervensi manual!")
    print("=" * 75)


if __name__ == "__main__":
    main()

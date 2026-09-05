"""Example 01: Quickstart Objective Planning

Demonstrates how Aether Office takes a high-level user objective, analyzes
its domain and complexity, generates an adaptive execution plan, audits plan
quality, and computes the critical path.
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
    print("=" * 70)
    print("🚀 AETHER OFFICE — EXAMPLE 01: QUICKSTART OBJECTIVE PLANNING")
    print("=" * 70)

    # 1. Initialize Workforce Organization (37 Indonesian employees & 8 departments)
    org, _ = create_default_organization()
    print(f"\n🏢 Organisasi dimuat: {org.name}")
    print(f"   Jumlah Departemen : {len(org.list_departments())}")
    print(f"   Jumlah Karyawan   : {len(org.employees.list())}")

    # 2. Initialize Adaptive Objective Planner
    planner = AdaptiveObjectivePlanner(organization=org)

    # 3. Create a High-Level Objective
    objective = Objective(
        id="obj_demo_01",
        title="Bangun portal web e-commerce untuk produk UMKM lokal",
        description="Portal katalog produk dan checkout pembayaran dengan integrasi payment gateway dan testing end-to-end.",
        budget=250.0,
    )
    print(f"\n📋 Objektif Diterima:")
    print(f"   Judul     : {objective.title}")
    print(f"   Deskripsi : {objective.description}")
    print(f"   Anggaran  : ${objective.budget:.2f}")

    # 4. Analyze the Objective
    print("\n🔍 Menganalisis karakteristik objektif...")
    analysis = planner.analyze(objective)
    print(f"   • Tipe Domain    : {analysis.objective_type.value}")
    print(f"   • Kompleksitas   : {analysis.complexity.value}")
    print(f"   • Skor Ambiguitas: {analysis.ambiguity_score:.2f} ({'Perlu Klarifikasi' if analysis.needs_clarification else 'Jelas & Spesifik'})")
    print(f"   • Keyakinan      : {analysis.confidence:.2f} ({analysis.confidence_level})")
    print(f"   • Estimasi Durasi: {analysis.estimated_duration:.1f} jam")
    print(f"   • Estimasi Biaya : ${analysis.estimated_cost:.4f}")

    # 5. Formulate Adaptive Execution Plan
    print("\n⚡ Merumuskan Rencana Eksekusi Adaptif...")
    plan = planner.plan(objective)
    print(f"   • Plan ID        : {plan.id}")
    print(f"   • Validasi Plan  : {'✅ Lolos (Valid DAG)' if plan.is_valid else '❌ Gagal'}")
    print(f"   • Strategi       : {plan.metadata.get('strategy')}")
    print(f"   • Skor Kualitas  : {plan.metadata.get('quality_score')} / 100 (Grade {plan.metadata.get('quality_grade')})")

    # 6. Display Milestones & Tasks
    print("\n📌 Rencana Milestone & Tugas:")
    for m in plan.milestones:
        print(f"\n   [Milestone {m.order}] {m.name} ({m.milestone_id})")
        print(f"   Deskripsi: {m.description}")
        m_tasks = [t for t in plan.tasks if t.get("milestone_id") == m.milestone_id]
        for t in m_tasks:
            role = t.get("preferred_role", "general")
            tier = t.get("model_tier", "standard")
            print(f"     → Task: {t.get('title')} [{role.upper()}] (Model: {tier})")

    # 7. Critical Path & Optimizations
    crit_path = plan.metadata.get("critical_path", [])
    if crit_path:
        print(f"\n🎯 Jalur Kritis ({len(crit_path)} tugas):")
        print("     " + " -> ".join(crit_path))

    print("\n" + "=" * 70)
    print("✅ Selesai! Rencana eksekusi siap dikirim ke Office Scheduler.")
    print("=" * 70)


if __name__ == "__main__":
    main()

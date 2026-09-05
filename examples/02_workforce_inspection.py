"""Example 02: Workforce & Skill Matching Inspection

Demonstrates the 8 departments, 37 roles, and Indonesian employee roster
in Aether Office, and shows how TaskMatcher assigns the most qualified employee.
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
from matcher import TaskMatcher
from tasks import WorkTask


def main():
    print("=" * 70)
    print("🏢 AETHER OFFICE — EXAMPLE 02: WORKFORCE & SKILL MATCHING")
    print("=" * 70)

    org, _ = create_default_organization()

    # 1. Inspect Departments
    print("\n📂 Daftar Departemen Kantor:")
    for dept in org.list_departments():
        roles_in_dept = [r for r in org.roles.list() if r.department == dept.department_id]
        print(f"   • {dept.name:<25} ({len(roles_in_dept)} roles) — {dept.description}")

    # 2. Inspect Sample Employees
    print("\n👥 Sampel Karyawan Aktif:")
    for emp in org.employees.list():
        caps = ", ".join(emp.capabilities[:3])
        print(f"   • {emp.name:<22} | Role: {emp.role:<15} | Keahlian: {caps}...")

    # 3. Demonstrate Task Matching
    print("\n🎯 Simulasi Pencocokan Karyawan (TaskMatcher):")
    sample_task = WorkTask(
        task_id="task_qa_01",
        project_id="proj_demo",
        title="Audit Keamanan dan Automated Testing API",
        description="Pengujian penetrasi API dan penulisan integration test suites.",
        preferred_role="qa",
        required_capabilities=["automated_testing", "code_review"],
    )

    ranked = TaskMatcher.rank_candidates(sample_task, org.employees.list())
    if ranked:
        assigned_emp, match_score = ranked[0]
        print(f"   Task Title        : {sample_task.title}")
        print(f"   Preferred Role    : {sample_task.preferred_role}")
        print(f"   Required Skills   : {', '.join(sample_task.required_capabilities)}")
        print(f"   Hasil Match       : {assigned_emp.name} (ID: {assigned_emp.employee_id})")
        print(f"   Role Karyawan     : {assigned_emp.role}")
        print(f"   Skor Kesesuaian   : {match_score}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

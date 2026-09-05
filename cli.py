"""CLI entry point for AI Dev Team."""

import sys
import argparse
import hashlib
import time
from pathlib import Path

# Reconfigure stdout for UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import Orchestrator, load_config
from events import CLIProgressStreamer


def main():
    parser = argparse.ArgumentParser(description="AI Development Team — automated software development")
    sub = parser.add_subparsers(dest="command", help="Command")

    # run command
    run_parser = sub.add_parser("run", help="Run the full pipeline")
    run_parser.add_argument("brief", help="Path to project brief file (or - for stdin)")
    run_parser.add_argument("--config", default="config.yaml", help="Config file path")
    run_parser.add_argument("--name", default=None, help="Project name (auto-generated if not set)")
    run_parser.add_argument("--output", default=None, help="Output directory (default: projects/<name>)")
    run_parser.add_argument("--mock", "--demo", dest="mock", action="store_true", help="Jalankan dalam mode simulasi offline tanpa server LLM")

    # status command
    status_parser = sub.add_parser("status", help="Show project status")
    status_parser.add_argument("project_id", nargs="?", default=None, help="Project ID")
    status_parser.add_argument("--project", dest="project_flag", default=None, help="Project ID alias")

    # events command
    events_parser = sub.add_parser("events", help="Show project events")
    events_parser.add_argument("project_id", help="Project ID")

    # replay command
    replay_parser = sub.add_parser("replay", help="Replay project events")
    replay_parser.add_argument("project_id", help="Project ID")

    # list command
    sub.add_parser("list", help="List all projects")

    # departments command (Phase 4)
    sub.add_parser("departments", help="List all workforce departments")

    # roles command (Phase 4)
    roles_parser = sub.add_parser("roles", help="List workforce roles")
    roles_parser.add_argument("--department", default=None, help="Filter roles by department")

    # employees command (Phase 4)
    employees_parser = sub.add_parser("employees", help="List workforce employees")
    employees_parser.add_argument("--role", default=None, help="Filter employees by role")
    employees_parser.add_argument("--department", default=None, help="Filter employees by department")
    employees_parser.add_argument("--status", default=None, help="Filter employees by status (active/inactive)")

    # hire command (Phase 4)
    hire_parser = sub.add_parser("hire", help="Hire a new AI employee")
    hire_parser.add_argument("--role", required=True, help="Role identifier")
    hire_parser.add_argument("--name", required=True, help="Employee display name")
    hire_parser.add_argument("--department", default=None, help="Department (optional, inferred from role)")
    hire_parser.add_argument("--capabilities", default="", help="Comma-separated capability list")

    # fire command (Phase 4)
    fire_parser = sub.add_parser("fire", help="Deactivate an AI employee")
    fire_parser.add_argument("employee_id", help="Employee ID to deactivate")

    # teams command (Phase 5)
    teams_parser = sub.add_parser("teams", help="List project teams")
    teams_parser.add_argument("--project", default=None, help="Filter by project ID")

    # team command (Phase 5)
    team_parser = sub.add_parser("team", help="View team details")
    team_parser.add_argument("team_id", help="Team ID")

    # tasks command (Phase 5)
    tasks_parser = sub.add_parser("tasks", help="List collaborative work tasks")
    tasks_parser.add_argument("--project", default=None, help="Filter by project ID")
    tasks_parser.add_argument("--status", default=None, help="Filter by task status")

    # task command (Phase 5)
    task_parser = sub.add_parser("task", help="View work task details")
    task_parser.add_argument("task_id", help="Task ID")

    # artifacts command (Phase 5)
    artifacts_parser = sub.add_parser("artifacts", help="List deliverables and artifacts")
    artifacts_parser.add_argument("--project", default=None, help="Filter by project ID")
    artifacts_parser.add_argument("--task", default=None, help="Filter by task ID")

    # reviews command (Phase 5)
    reviews_parser = sub.add_parser("reviews", help="List peer reviews")
    reviews_parser.add_argument("--project", default=None, help="Filter by project ID")
    reviews_parser.add_argument("--task", default=None, help="Filter by task ID")

    # workflow command (Phase 5)
    workflow_parser = sub.add_parser("workflow", help="View workflow status for project")
    workflow_parser.add_argument("project_id", help="Project ID")

    # workflow-run command (Phase 5)
    workflow_run_parser = sub.add_parser("workflow-run", help="Execute collaborative workflow")
    workflow_run_parser.add_argument("project_id", help="Project ID")
    workflow_run_parser.add_argument("--brief", required=True, help="Project brief or objective")
    workflow_run_parser.add_argument("--config", default="config.yaml", help="Config file path")
    workflow_run_parser.add_argument("--team-name", default=None, help="Custom team name")

    # Phase 6: Multi-Project & Autonomous Operations commands
    # projects command
    projects_parser = sub.add_parser("projects", help="Daftar semua proyek aktif dan riwayat kantor")
    projects_parser.add_argument("--status", default=None, help="Filter berdasarkan status proyek")

    # project command
    project_parser = sub.add_parser("project", help="Lihat rincian proyek kantor")
    project_parser.add_argument("project_id", help="ID Proyek")

    # queue command
    sub.add_parser("queue", help="Pantau antrean proyek dan antrean tugas global")

    # schedule command
    sub.add_parser("schedule", help="Pantau jadwal tugas dan penugasan karyawan")

    # resources command
    sub.add_parser("resources", help="Pantau kapasitas workforce dan status reservasi karyawan")

    # usage command
    usage_parser = sub.add_parser("usage", help="Laporan penggunaan token dan model LLM")
    usage_parser.add_argument("--project", default=None, help="Filter per ID Proyek")

    # costs command
    costs_parser = sub.add_parser("costs", help="Estimasi biaya komputasi dan anggaran proyek")
    costs_parser.add_argument("--project", default=None, help="Filter per ID Proyek")

    # office command (Phase 6 & 7)
    office_parser = sub.add_parser("office", help="Dashboard operasional dan kontrol runtime engine Aether Office")
    office_parser.add_argument("action", nargs="?", default="status", choices=["status", "start", "stop", "tick"], help="Aksi: status (default), start, stop, tick")
    office_parser.add_argument("--heartbeat", type=float, default=None, help="Interval detak jantung dalam detik (default: 5.0)")
    office_parser.add_argument("--no-execute", action="store_true", help="Jangan jalankan worker saat tick")
    office_parser.add_argument("--max-ticks", type=int, default=None, help="Batas jumlah tick sebelum berhenti")

    # scheduler-tick command
    tick_parser = sub.add_parser("scheduler-tick", help="Jalankan satu siklus penjadwalan deterministik")
    tick_parser.add_argument("--execute", action="store_true", help="Eksekusi tugas yang dijadwalkan secara langsung")

    # project-pause command
    pause_parser = sub.add_parser("project-pause", help="Jeda operasional proyek")
    pause_parser.add_argument("project_id", help="ID Proyek")
    pause_parser.add_argument("--reason", default="Dijeda oleh pengguna via CLI", help="Alasan jeda proyek")

    # project-resume command
    resume_parser = sub.add_parser("project-resume", help="Lanjutkan kembali operasional proyek yang dijeda")
    resume_parser.add_argument("project_id", help="ID Proyek")

    # Phase 8 & 9: Objective-to-Outcome Engine commands
    obj_parser = sub.add_parser("objective", help="Manajemen dan orkestrasi objektif bisnis Aether Office")
    obj_parser.add_argument("action", choices=["create", "list", "show", "run", "status", "cancel", "analyze", "plan", "risks", "plan-quality"], help="Aksi: create, list, show, run, status, cancel, analyze, plan, risks, plan-quality")
    obj_parser.add_argument("target", nargs="?", default=None, help="Judul objektif (untuk create) atau ID Objektif (untuk show/run/status/cancel/analyze/plan/risks/plan-quality)")
    obj_parser.add_argument("--description", default="", help="Deskripsi lengkap objektif")
    obj_parser.add_argument("--budget", type=float, default=0.0, help="Alokasi anggaran maksimal ($)")
    obj_parser.add_argument("--deadline", default=None, help="Tenggat waktu objektif (ISO string)")
    obj_parser.add_argument("--priority", default="NORMAL", choices=["CRITICAL", "HIGH", "NORMAL", "LOW"], help="Prioritas objektif")
    obj_parser.add_argument("--criteria", default="", help="Kriteria penerimaan dipisahkan koma")
    obj_parser.add_argument("--max-revisions", type=int, default=3, help="Maksimum percobaan revisi jika kriteria belum terpenuhi")
    obj_parser.add_argument("--ticks", type=int, default=30, help="Maksimum detak scheduler saat eksekusi")
    obj_parser.add_argument("--reason", default="Dibatalkan pengguna via CLI", help="Alasan pembatalan objektif")

    # dashboard / ui command
    dash_parser = sub.add_parser("dashboard", aliases=["ui"], help="Buka visual game dashboard interaktif Aether Office di browser")
    dash_parser.add_argument("--host", default="127.0.0.1", help="Host server dashboard (default: 127.0.0.1)")
    dash_parser.add_argument("--port", type=int, default=8000, help="Port server dashboard (default: 8000)")
    dash_parser.add_argument("--no-browser", "--no-open", dest="no_browser", action="store_true", help="Jangan buka browser secara otomatis")
    dash_parser.add_argument("--config", default="config.yaml", help="Path file konfigurasi")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "events":
        cmd_events(args)
    elif args.command == "replay":
        cmd_replay(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "departments":
        cmd_departments(args)
    elif args.command == "roles":
        cmd_roles(args)
    elif args.command == "employees":
        cmd_employees(args)
    elif args.command == "hire":
        cmd_hire(args)
    elif args.command == "fire":
        cmd_fire(args)
    elif args.command == "teams":
        cmd_teams(args)
    elif args.command == "team":
        cmd_team(args)
    elif args.command == "tasks":
        cmd_tasks(args)
    elif args.command == "task":
        cmd_task(args)
    elif args.command == "artifacts":
        cmd_artifacts(args)
    elif args.command == "reviews":
        cmd_reviews(args)
    elif args.command == "workflow":
        cmd_workflow(args)
    elif args.command == "workflow-run":
        cmd_workflow_run(args)
    elif args.command == "projects":
        cmd_projects(args)
    elif args.command == "project":
        cmd_project(args)
    elif args.command == "queue":
        cmd_queue(args)
    elif args.command == "schedule":
        cmd_schedule(args)
    elif args.command == "resources":
        cmd_resources(args)
    elif args.command == "usage":
        cmd_usage(args)
    elif args.command == "costs":
        cmd_costs(args)
    elif args.command == "office":
        cmd_office(args)
    elif args.command == "scheduler-tick":
        cmd_scheduler_tick(args)
    elif args.command == "project-pause":
        cmd_project_pause(args)
    elif args.command == "project-resume":
        cmd_project_resume(args)
    elif args.command == "objective":
        cmd_objective(args)
    elif args.command in ("dashboard", "ui"):
        cmd_dashboard(args)
    else:
        parser.print_help()


def cmd_dashboard(args):
    """Launch the interactive game dashboard."""
    try:
        import fastapi
        import uvicorn
    except ImportError:
        # Auto-fallback: check if local .venv exists with installed dependencies
        from pathlib import Path
        venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists() and sys.executable.lower() != str(venv_python.resolve()).lower():
            import subprocess
            res = subprocess.run([str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:])
            sys.exit(res.returncode)

        print("\n" + "=" * 65)
        print("❌ DASHBOARD DEPENDENCY MISSING")
        print("   FastAPI dan Uvicorn dibutuhkan untuk menjalankan game dashboard.")
        print("   Silakan jalankan perintah instalasi berikut di terminal:")
        print("       .\\.venv\\Scripts\\python.exe -m pip install fastapi uvicorn")
        print("   atau jalankan langsung menggunakan virtual environment:")
        print("       .\\.venv\\Scripts\\python.exe cli.py dashboard")
        print("=" * 65 + "\n")
        sys.exit(1)

    from dashboard import start_dashboard
    start_dashboard(
        host=args.host,
        port=args.port,
        auto_open=not args.no_browser,
        config_path=args.config,
    )




def cmd_run(args):
    """Run the full pipeline."""
    # Read brief
    if args.brief == "-":
        brief = sys.stdin.read()
    else:
        brief_path = Path(args.brief)
        if not brief_path.exists():
            print(f"❌ Brief file not found: {args.brief}")
            sys.exit(1)
        brief = brief_path.read_text(encoding="utf-8")

    # Generate project ID
    if args.name:
        project_name = args.name
    else:
        words = brief.strip().split()[:3]
        project_name = "-".join(w.lower().strip(".,!?") for w in words)

    project_id = f"{project_name}-{int(time.time())}"

    # Output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        config = load_config(args.config)
        output_dir = Path(config.get("project", {}).get("output_dir", "./projects")) / project_id

    print(f"🚀 AI Dev Team — Starting pipeline")
    print(f"   Project: {project_name}")
    print(f"   ID: {project_id}")
    print(f"   Output: {output_dir}")
    print(f"   Brief: {len(brief)} chars")

    if getattr(args, "mock", False):
        import os
        os.environ["AETHER_MOCK_LLM"] = "1"
        print("   ⚡ Mode Simulasi Offline / Mock Aktif (Tanpa koneksi LLM eksternal)")

    # Load config and run
    config = load_config(args.config)
    orchestrator = Orchestrator(config, project_id, output_dir)

    # Attach CLI real-time progress streamer to event bus
    streamer = CLIProgressStreamer()
    orchestrator.event_bus.subscribe(streamer.on_event)

    # Attach PixelOffice bridge (UDP 9997 & HTTP 3003)
    try:
        from pixel_bridge import PixelOfficeBridge
        pixel_bridge = PixelOfficeBridge(event_bus=orchestrator.event_bus)
        pixel_bridge.start()
    except Exception:
        pass

    try:
        result = orchestrator.run(brief)
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"💥 PIPELINE CRASHED: {e}")
        print(f"   Output: {output_dir}")
        sys.exit(1)

    # Print result
    print(f"\n   Output: {output_dir}")
    print(f"   Docs: {output_dir / 'docs'}")
    sys.exit(0 if result["success"] else 1)


def cmd_status(args):
    """Show project status."""
    from db import Database
    config = load_config()
    db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
    db = Database(db_path)

    project_id = args.project_id or getattr(args, "project_flag", None)
    if not project_id:
        print("❌ Project ID wajib diisi. Contoh: python cli.py status <project_id> atau --project <project_id>")
        return

    project = db.get_project(project_id)
    if not project:
        print(f"❌ Project not found: {project_id}")
        return

    tasks = db.get_tasks(project_id)
    print(f"\n📋 Project: {project['name']}")
    print(f"   Status: {project['status']}")
    print(f"   Created: {project['created_at']}")

    # Show live agent states
    agent_states = db.get_all_agent_states(args.project_id)
    if agent_states:
        print(f"\n   Agents ({len(agent_states)}):")
        for a in agent_states:
            print(f"   🤖 {a['agent_id']:<15} {a['agent_role']:<12} [{a['state']}]")

    print(f"\n   Tasks ({len(tasks)}):")
    for t in tasks:
        status_icon = {
            "BACKLOG": "⬜", "READY": "🟡", "IN_PROGRESS": "🔵",
            "BLOCKED": "🔴", "REVIEW": "🟣", "QA": "🔍",
            "DONE": "✅", "FAILED": "❌",
        }.get(t["status"], "❓")
        print(f"   {status_icon} [{t['id']}] {t['title']} — {t['status']}")
    db.close()


def cmd_events(args):
    """Show project events."""
    from db import Database
    config = load_config()
    db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
    db = Database(db_path)

    events = db.get_events(args.project_id)
    print(f"\n📜 Events ({len(events)}):")
    for e in events:
        agent_id_str = f" / {e['agent_id']}" if e.get("agent_id") else ""
        status_str = f" [{e['status']}]" if e.get("status") else ""
        print(f"   [{e['created_at']}] {e['event_type']} ({e['agent_role'] or 'system'}{agent_id_str}){status_str}")
        if e["data"] and e["data"] != "{}":
            print(f"      {e['data']}")
    db.close()


def cmd_replay(args):
    """Replay events for a project through CLI streamer."""
    from db import Database
    config = load_config()
    db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
    db = Database(db_path)

    project = db.get_project(args.project_id)
    if not project:
        print(f"❌ Project not found: {args.project_id}")
        db.close()
        return

    print(f"🔄 Replaying events for project: {args.project_id}")
    streamer = CLIProgressStreamer()
    replayed = db.replay_events(args.project_id, handler=streamer.on_event)
    print(f"\nTotal replayed events: {len(replayed)}")
    db.close()


def cmd_list(args=None):
    """List all projects."""
    from db import Database
    config = load_config()
    db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
    db = Database(db_path)

    rows = db.conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    if not rows:
        print("No projects found.")
        return

    print(f"\n📁 Projects ({len(rows)}):")
    for r in rows:
        status_icon = "✅" if r["status"] == "DONE" else "❌" if r["status"] == "FAILED" else "🔵"
        print(f"   {status_icon} {r['id']} — {r['name']} ({r['status']})")
    db.close()


def _get_workforce_db():
    from db import Database
    from workforce import create_default_organization, seed_full_workforce
    config = load_config()
    db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
    db = Database(db_path)
    # Seed default organization into DB if empty or missing roles
    org, _ = create_default_organization()
    seed_full_workforce(org)
    db.sync_organization_to_db(org)
    return db


def cmd_departments(args=None):
    """List all workforce departments."""
    db = _get_workforce_db()
    depts = db.get_departments()
    print(f"\n🏢 DIVISI & DEPARTEMEN KANTOR AETHER OFFICE ({len(depts)}):")
    for d in depts:
        emps = db.get_employees(department_id=d["id"])
        print(f"   • {d['id']:<15} {d['name']:<20} ({len(emps)} karyawan) — {d.get('description', '')}")
    db.close()


def cmd_roles(args):
    """List workforce roles."""
    db = _get_workforce_db()
    roles = db.get_roles(department_id=args.department)
    dept_label = f" di divisi '{args.department}'" if args.department else ""
    print(f"\n💼 KATALOG POSISI & JABATAN KERJA ({len(roles)}){dept_label}:")
    for r in roles:
        caps = ", ".join(r.get("capabilities", [])) or "tidak ada"
        print(f"   • {r['id']:<24} [Divisi: {r['department_id']:<12}] {r['name']}")
        print(f"     Tugas & Tanggung Jawab: {r.get('description', '')}")
        print(f"     Keahlian Utama: {caps}")
    db.close()


def cmd_employees(args):
    """List workforce employees."""
    db = _get_workforce_db()
    emps = db.get_employees(role_id=args.role, department_id=args.department, status=args.status)
    filter_label = []
    if args.role:
        filter_label.append(f"posisi={args.role}")
    if args.department:
        filter_label.append(f"divisi={args.department}")
    if args.status:
        filter_label.append(f"status={args.status}")
    label_str = f" ({', '.join(filter_label)})" if filter_label else ""

    print(f"\n👥 DAFTAR KARYAWAN KANTOR AETHER OFFICE ({len(emps)}){label_str}:")
    for e in emps:
        status_icon = "🟢" if e["status"] == "active" else "🔴"
        avail_map = {"available": "Tersedia", "busy": "Sedang Bertugas", "offline": "Offline"}
        avail_str = f"[{avail_map.get(e.get('availability', 'available'), e.get('availability'))}]"
        caps = ", ".join(e.get("capabilities", [])) or "-"
        personality = e.get("personality", {})
        traits = ", ".join(personality.get("traits", [])) or "-"
        comm = personality.get("communication_style", "concise")

        print(f"   {status_icon} {e['id']:<18} {e['name']:<24} Posisi: {e['role_id']:<20} Divisi: {e['department_id']:<12} {avail_str}")
        print(f"      Keahlian: {caps}")
        print(f"      Karakter: {traits} | Gaya Komunikasi: {comm}")
    db.close()


def cmd_hire(args):
    """Hire a new employee."""
    db = _get_workforce_db()
    role_obj = db.get_role(args.role)
    dept = args.department or (role_obj["department_id"] if role_obj else "engineering")

    existing = db.get_employees(role_id=args.role)
    idx = len(existing) + 1
    emp_id = f"{args.role}_{idx:03d}"
    while db.get_employee(emp_id):
        idx += 1
        emp_id = f"{args.role}_{idx:03d}"

    caps = [c.strip() for c in args.capabilities.split(",") if c.strip()] if args.capabilities else (role_obj.get("capabilities", []) if role_obj else [])

    db.save_employee(
        employee_id=emp_id,
        name=args.name,
        role_id=args.role,
        department_id=dept,
        capabilities=caps,
        status="active",
        availability="available",
    )
    print(f"\n🎉 Selamat Bergabung di Aether Office! Karyawan Baru Berhasil Direkrut:")
    print(f"   ID Karyawan : {emp_id}")
    print(f"   Nama Lengkap: {args.name}")
    print(f"   Posisi      : {args.role}")
    print(f"   Divisi      : {dept}")
    print(f"   Keahlian    : {', '.join(caps) if caps else '-'}")
    db.close()


def cmd_fire(args):
    """Deactivate an employee."""
    db = _get_workforce_db()
    emp = db.get_employee(args.employee_id)
    if not emp:
        print(f"❌ Karyawan tidak ditemukan: {args.employee_id}")
        db.close()
        return

    db.update_employee_status(args.employee_id, status="inactive", availability="offline", live_state="BLOCKED")
    print(f"\n👋 Karyawan Telah Dinonaktifkan:")
    print(f"   ID Karyawan : {args.employee_id}")
    print(f"   Nama Lengkap: {emp['name']}")
    print(f"   Status      : Nonaktif (Offline)")
    db.close()


# =====================================================================
# Phase 5: Team Collaboration & Delegation CLI Commands
# =====================================================================

def cmd_teams(args):
    """List project teams."""
    db = _get_workforce_db()
    teams = db.list_teams(project_id=args.project)
    print(f"\n🤝 DAFTAR TIM PROYEK AETHER OFFICE ({len(teams)}):")
    if not teams:
        print("   (Belum ada tim proyek yang dibentuk)")
    for t in teams:
        lead_name = t.get("lead_employee_id") or "Belum Ditentukan"
        emp = db.get_employee(lead_name)
        if emp:
            lead_name = f"{emp['name']} ({lead_name})"
        status_icon = "🟢" if t.get("status") == "active" else "🏁"
        print(f"   {status_icon} {t['id']:<18} {t['name']:<25} Status: {t.get('status', 'active'):<10} Ketua: {lead_name}")
        print(f"      Anggota: {len(t.get('members', []))} personil | Sasaran: {t.get('objective', '-')[:60]}")
    db.close()


def cmd_team(args):
    """View team details and members."""
    db = _get_workforce_db()
    team = db.get_team(args.team_id)
    if not team:
        print(f"❌ Tim tidak ditemukan: {args.team_id}")
        db.close()
        return

    lead_emp = db.get_employee(team.get("lead_employee_id") or "")
    lead_str = f"{lead_emp['name']} — {lead_emp['role']}" if lead_emp else (team.get("lead_employee_id") or "-")

    print(f"\n=======================================================")
    print(f"👥 TIM: {team['name']}")
    print(f"   ID Tim      : {team['id']}")
    print(f"   Proyek      : {team['project_id']}")
    print(f"   Status      : {team['status'].upper()}")
    print(f"   Ketua Tim   : {lead_str}")
    print(f"   Sasaran     : {team.get('objective', '-')}")
    print(f"-------------------------------------------------------")
    print(f"📋 DAFTAR ANGGOTA ({len(team.get('members', []))} Personil):")
    for m in team.get("members", []):
        emp = db.get_employee(m["employee_id"])
        if emp:
            status_icon = "🟢" if emp.get("status") == "active" else "🔴"
            print(f"   {status_icon} {emp['name']:<22} Posisi: {emp['role']:<20} [{emp.get('availability', 'available').upper()}]")
            caps = ", ".join(emp.get("capabilities", []))
            print(f"      Keahlian: {caps}")
        else:
            print(f"   • {m['employee_id']} (Role: {m.get('role', '-')})")
    print(f"=======================================================\n")
    db.close()


def cmd_tasks(args):
    """List collaborative work tasks."""
    db = _get_workforce_db()
    tasks = db.list_work_tasks(project_id=args.project, status=args.status)
    proj_label = f" Proyek '{args.project}'" if args.project else ""
    print(f"\n📋 DAFTAR PENUGASAN KERJA (WORK TASKS){proj_label} ({len(tasks)}):")
    if not tasks:
        print("   (Tidak ada tugas yang cocok)")

    for t in tasks:
        status_icons = {
            "COMPLETED": "✅",
            "IN_PROGRESS": "⚡",
            "WAITING_REVIEW": "🔍",
            "ASSIGNED": "📌",
            "READY": "⏳",
            "PENDING": "⏱️",
            "BLOCKED": "🚫",
            "FAILED": "❌",
            "CANCELLED": "⚪",
        }
        icon = status_icons.get(t.get("status"), "•")
        assigned = t.get("assigned_employee_id") or "Belum Diassign"
        emp = db.get_employee(assigned)
        if emp:
            assigned = f"{emp['name']} ({assigned})"
        deps = f" [Prasyarat: {', '.join(t.get('dependencies', []))}]" if t.get("dependencies") else ""
        print(f"   {icon} {t['task_id']:<20} {t['status']:<15} {t['title']:<35}")
        print(f"      Petugas: {assigned:<30} Prioritas: {t.get('priority', 0)}{deps}")
    db.close()


def cmd_task(args):
    """View work task details."""
    db = _get_workforce_db()
    t = db.get_work_task(args.task_id)
    if not t:
        print(f"❌ Tugas tidak ditemukan: {args.task_id}")
        db.close()
        return

    assigned = t.get("assigned_employee_id") or "-"
    emp = db.get_employee(assigned)
    if emp:
        assigned = f"{emp['name']} ({emp['role']})"

    print(f"\n=======================================================")
    print(f"📌 TUGAS KERJA: {t['title']}")
    print(f"   ID Tugas    : {t['task_id']}")
    print(f"   Proyek      : {t['project_id']}")
    print(f"   Status      : {t['status']}")
    print(f"   Prioritas   : {t.get('priority', 0)}")
    print(f"   Petugas     : {assigned}")
    print(f"   Deskripsi   : {t.get('description', '-')}")
    print(f"   Keahlian    : {', '.join(t.get('required_capabilities', [])) or '-'}")
    print(f"   Prasyarat   : {', '.join(t.get('dependencies', [])) or 'Tidak ada'}")
    print(f"   Artifacts   : {', '.join(t.get('artifacts', [])) or 'Belum ada'}")
    if t.get("result"):
        print(f"   Hasil/Output: {str(t.get('result'))[:150]}...")
    print(f"=======================================================\n")
    db.close()


def cmd_artifacts(args):
    """List deliverables and artifacts."""
    db = _get_workforce_db()
    arts = db.list_artifacts(project_id=args.project, task_id=args.task)
    print(f"\n📦 DAFTAR HASIL KERJA & ARTIFACT ({len(arts)}):")
    if not arts:
        print("   (Belum ada artifact yang tersimpan)")
    for a in arts:
        creator = a.get("created_by") or "-"
        emp = db.get_employee(creator)
        if emp:
            creator = f"{emp['name']}"
        print(f"   📄 {a['artifact_id']:<25} v{a.get('version', 1)} [{a.get('type', 'doc').upper()}] {a.get('name', '')}")
        print(f"      Dibuat Oleh: {creator:<20} Tugas: {a.get('task_id', '-')}")
        if a.get("content"):
            preview = a["content"].replace("\n", " ")[:90]
            print(f"      Pratinjau  : \"{preview}...\"")
    db.close()


def cmd_reviews(args):
    """List peer reviews."""
    db = _get_workforce_db()
    revs = db.list_reviews(project_id=args.project, task_id=args.task)
    print(f"\n🔍 DAFTAR EVALUASI & PEER REVIEW ({len(revs)}):")
    if not revs:
        print("   (Belum ada review yang tercatat)")
    for r in revs:
        status_badge = "✅ DISETUJUI" if r.get("status") == "APPROVED" else "🔄 PERBAIKAN" if r.get("status") == "CHANGES_REQUESTED" else "❌ DITOLAK" if r.get("status") == "REJECTED" else "⏳ MENUNGGU"
        reviewer = r.get("reviewer_employee_id") or "-"
        rev_emp = db.get_employee(reviewer)
        if rev_emp:
            reviewer = rev_emp["name"]
        print(f"   • {r['review_id']:<20} {status_badge:<16} Skor: {r.get('score', 0.0):.1f} Reviewer: {reviewer}")
        print(f"      Artifact : {r.get('artifact_id', '-')} (Tugas: {r.get('task_id', '-')})")
        if r.get("feedback"):
            print(f"      Catatan  : {r['feedback']}")
    db.close()


def cmd_workflow(args):
    """View workflow status for a project."""
    db = _get_workforce_db()
    proj = db.get_project(args.project_id)
    if not proj:
        print(f"❌ Proyek tidak ditemukan: {args.project_id}")
        db.close()
        return

    teams = db.list_teams(project_id=args.project_id)
    tasks = db.list_work_tasks(project_id=args.project_id)
    arts = db.list_artifacts(project_id=args.project_id)

    print(f"\n=======================================================")
    print(f"🏢 WORKFLOW PROYEK: {proj['name']} ({args.project_id})")
    print(f"   Status Global : {proj.get('status', 'ACTIVE')}")
    print(f"   Brief/Sasaran : {proj.get('brief', '-')[:120]}")
    print(f"   Tim Dibentuk  : {len(teams)} tim")
    print(f"   Total Tugas   : {len(tasks)} tugas")
    print(f"   Total Artifact: {len(arts)} deliverable")
    print(f"=======================================================\n")
    db.close()


def cmd_workflow_run(args):
    """Execute collaborative workflow from brief."""
    from workflow import WorkOrchestrator
    from workforce import create_default_organization
    from llm import LLMClient
    from events import EventBus, CLIProgressStreamer

    config = load_config(args.config)
    llm_cfg = config["llm"]
    llm = LLMClient(
        endpoint=llm_cfg["endpoint"],
        api_key=llm_cfg["api_key"],
        model=llm_cfg["model"],
        temperature=llm_cfg.get("temperature", 0.7),
        max_tokens=llm_cfg.get("max_tokens", 4096),
        max_retries=llm_cfg.get("max_retries", 3),
        timeout=llm_cfg.get("timeout", 300),
    )

    db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
    event_bus = EventBus()
    streamer = CLIProgressStreamer()
    event_bus.subscribe(streamer.on_event)

    from db import Database
    db = Database(db_path, event_bus=event_bus)
    org, _ = create_default_organization()
    db.sync_organization_to_db(org)

    output_dir = config.get("project", {}).get("output_dir", "./projects") + f"/{args.project_id}"

    # Create project entry
    db.create_project(args.project_id, name=args.project_id, brief=args.brief, output_dir=output_dir)

    print(f"\n🚀 MEMULAI WORKFLOW KOLABORASI AETHER OFFICE: {args.project_id}")
    print(f"   Brief Proyek : {args.brief}\n")

    orch = WorkOrchestrator(
        project_id=args.project_id,
        org=org,
        db=db,
        llm=llm,
        output_dir=output_dir,
        event_bus=event_bus,
    )

    result = orch.run_workflow(brief=args.brief, team_name=args.team_name)

    if result.get("success"):
        print(f"\n🎉 WORKFLOW SELESAI DENGAN SUKSES!")
        print(f"   Tim Terlibat  : {result.get('team', {}).get('name')}")
        print(f"   Tugas Selesai : {len(result.get('tasks', []))} tugas")
        print(f"   Artifact Siap : {len(result.get('artifacts', []))} deliverable")
    else:
        print(f"\n💥 WORKFLOW GAGAL ATAU TERHAMBAT:")
        print(f"   State Akhir   : {result.get('workflow_state')}")
        print(f"   Kendala/Error : {result.get('error')}")

    db.close()


# =====================================================================
# Phase 6: Multi-Project & Autonomous Operations Handlers
# =====================================================================

def _get_office_orchestrator():
    from db import Database
    from workforce import create_default_organization
    from office import OfficeOrchestrator
    config = load_config()
    db_path = config.get("project", {}).get("data_dir", "./data") + "/tasks.db"
    db = Database(db_path)
    org, _ = create_default_organization()
    db.sync_organization_to_db(org)
    return OfficeOrchestrator(db=db, organization=org)


def cmd_projects(args):
    """List all projects across the office."""
    orch = _get_office_orchestrator()
    projs = orch.project_registry.list_projects()
    if args.status:
        projs = [p for p in projs if p.status.value.upper() == args.status.upper()]

    status_badge = {
        "RUNNING": "●",
        "READY": "●",
        "PAUSED": "⏸",
        "BLOCKED": "⛔",
        "COMPLETED": "✓",
        "FAILED": "✗",
        "PLANNED": "○",
        "CANCELLED": "✕",
    }

    print(f"\n📁 AETHER OFFICE — DAFTAR PROYEK ({len(projs)}):")
    print("─" * 78)
    if not projs:
        print("   (Belum ada proyek yang terdaftar)")
    for p in projs:
        icon = status_badge.get(p.status.value, "●")
        dl_str = p.deadline if p.deadline else "-"
        budget_str = f"${p.budget:.2f} (terpakai: ${p.spent:.2f})" if p.budget > 0 else f"${p.spent:.2f}"
        print(f"  {icon} {p.name:<26} [{p.status.value:<9}] Prioritas: {p.priority.value:<8} Deadline: {dl_str:<12}")
        print(f"    ID: {p.project_id} | Anggaran: {budget_str}")
        if p.description:
            print(f"    Deskripsi: {p.description[:70]}")
    orch.db.close()


def cmd_project(args):
    """View detailed project information."""
    orch = _get_office_orchestrator()
    p = orch.project_registry.get_project(args.project_id)
    if not p:
        print(f"❌ Proyek tidak ditemukan: {args.project_id}")
        orch.db.close()
        return

    b_info = orch.budget_manager.get_project_budget(args.project_id)
    usage = orch.usage_tracker.get_project_usage(args.project_id)
    tasks = [t for t in orch.work_queue.list_all_tasks() if t.project_id == args.project_id]

    print(f"\n📋 RINCIAN PROYEK: {p.name}")
    print("─" * 60)
    print(f"   ID Proyek       : {p.project_id}")
    print(f"   Status          : {p.status.value}")
    print(f"   Prioritas       : {p.priority.value} (Bobot: {p.priority.weight})")
    print(f"   Deadline        : {p.deadline or '-'}")
    print(f"   Owner / Lead    : {p.owner_employee_id or '-'}")
    print(f"   Tim Terkait     : {p.team_id or '-'}")
    print(f"   Dibuat Pada     : {p.created_at}")
    print(f"   Mulai Berjalan  : {p.started_at or '-'}")
    print(f"   Selesai Pada    : {p.completed_at or '-'}")
    print(f"   Deskripsi       : {p.description or '-'}")
    print(f"\n💰 KEUANGAN & PENGGUNAAN TOKEN:")
    print(f"   Alokasi Budget  : ${b_info.get('budget', 0.0):.2f}")
    print(f"   Biaya Terpakai  : ${b_info.get('spent', 0.0):.4f}")
    rem = b_info.get('remaining', 0.0)
    print(f"   Sisa Anggaran   : {'Tak Terbatas' if rem == float('inf') else f'${rem:.4f}'}")
    print(f"   Status Anggaran : {'TERBLOKIR (Budget Habis)' if b_info.get('is_blocked') else 'Aman'}")
    print(f"   Total Token     : {usage.get('total_tokens', 0):,} (Input: {usage.get('total_input_tokens', 0):,}, Output: {usage.get('total_output_tokens', 0):,})")

    print(f"\n📝 DAFTAR TUGAS PROYEK ({len(tasks)}):")
    for t in tasks:
        emp_str = f"[{t.assigned_employee_id}]" if t.assigned_employee_id else "[Belum Ditugaskan]"
        print(f"   • [{t.status:<11}] {t.task_id:<12} {t.title:<30} {emp_str}")
    orch.db.close()


def cmd_queue(args):
    """View project queue and multi-project work queue."""
    orch = _get_office_orchestrator()
    ranked_projects = orch.project_queue.get_ranked_projects(active_only=False)
    ready_tasks = orch.work_queue.get_ready_tasks(orch.project_registry, orch.project_queue)
    running_tasks = orch.work_queue.get_running_tasks()
    blocked_tasks = orch.work_queue.get_blocked_tasks(orch.project_registry)

    print("\n🚦 AETHER OFFICE — ANTREAN OPERASIONAL")
    print("─" * 60)
    print(f"\n1. Antrean Proyek ({len(ranked_projects)}):")
    for p, score in ranked_projects:
        entry = orch.project_queue._entries.get(p.project_id, {})
        starv = entry.get("starvation_counter", 0)
        print(f"   • {p.name:<24} [Skor: {score:>5.1f}] [Status: {p.status.value:<8}] [Prioritas: {p.priority.value:<8}] (Starvation: {starv} tick)")

    print(f"\n2. Tugas Siap Eksekusi (Ready Tasks: {len(ready_tasks)}):")
    for t in ready_tasks[:10]:
        print(f"   • {t.task_id:<14} [P:{t.priority}] {t.title:<32} Proyek: {t.project_id}")
    if len(ready_tasks) > 10:
        print(f"     ... dan {len(ready_tasks) - 10} tugas lainnya")

    print(f"\n3. Tugas Sedang Berjalan (Running Tasks: {len(running_tasks)}):")
    for t in running_tasks:
        print(f"   • {t.task_id:<14} Petugas: {t.assigned_employee_id:<18} {t.title}")

    print(f"\n4. Tugas Terblokir / Menunggu Prasyarat (Blocked Tasks: {len(blocked_tasks)}):")
    for t in blocked_tasks[:5]:
        deps = ", ".join(t.dependencies) if t.dependencies else "proyek non-aktif"
        print(f"   • {t.task_id:<14} {t.title:<30} (Menunggu: {deps})")
    orch.db.close()


def cmd_schedule(args):
    """Display scheduling assignments and reservations."""
    orch = _get_office_orchestrator()
    reservations = orch.db.list_reservations()
    ready_tasks = orch.work_queue.get_ready_tasks(orch.project_registry, orch.project_queue)
    history = orch.db.list_scheduler_runs(limit=5)

    print("\n📅 AETHER OFFICE — JADWAL & ALOKASI TUGAS")
    print("─" * 60)
    print(f"\n1. Reservasi Karyawan Aktif ({len(reservations)}):")
    if not reservations:
        print("   (Tidak ada reservasi aktif saat ini)")
    for r in reservations:
        emp = orch.resource_manager.get_employee(r["employee_id"])
        emp_name = emp.name if emp else r["employee_id"]
        print(f"   • {r['employee_id']:<18} ({emp_name:<20}) → Tugas: {r['task_id']:<12} Proyek: {r['project_id']}")

    print(f"\n2. Tugas Antrean Prioritas Tertinggi ({len(ready_tasks)}):")
    for t in ready_tasks[:5]:
        req_caps = ", ".join(t.required_capabilities) or "umum"
        print(f"   • {t.task_id:<14} Prioritas: {t.priority:<2} Keahlian: {req_caps:<20} Judul: {t.title}")

    print(f"\n3. Riwayat Penjadwalan Terbaru (5 Terakhir):")
    for run in history:
        print(f"   • Tick #{run['tick_number']:<4} Dievaluasi: {run['tasks_evaluated']:<3} Terjadwal: {run['tasks_scheduled']:<3} Konflik: {run['conflicts_detected']:<2} Durasi: {run['duration_ms']:.2f}ms")
    orch.db.close()


def cmd_resources(args):
    """Workforce Capacity and Reservation Status."""
    orch = _get_office_orchestrator()
    cap = orch.resource_manager.get_workforce_capacity()
    reservations = orch.db.list_reservations()

    print("\n👥 AETHER OFFICE — KAPASITAS WORKFORCE")
    print("─" * 60)
    print(f"   Total Karyawan     : {cap['total_employees']}")
    print(f"   Tersedia (Ready)   : {cap['available']}")
    print(f"   Bertugas (Busy)    : {cap['busy']}")
    print(f"   Offline / Non-aktif: {cap['offline']}")
    print(f"   Tugas Berjalan     : {cap['running_tasks']}")
    print(f"   Tingkat Utilisasi  : {cap['utilization'] * 100:.1f}%\n")

    print(f"🔒 Status Reservasi Karyawan ({len(reservations)}):")
    if not reservations:
        print("   (Seluruh karyawan yang aktif saat ini berstatus Tersedia)")
    for r in reservations:
        print(f"   • {r['employee_id']:<18} dikunci untuk Tugas: {r['task_id']} (Proyek: {r['project_id']}) sejak {r['reserved_at']}")
    orch.db.close()


def cmd_usage(args):
    """Token Usage Report."""
    orch = _get_office_orchestrator()
    if args.project:
        usage = orch.usage_tracker.get_project_usage(args.project)
        records = orch.db.list_usage_records(project_id=args.project)
        print(f"\n📊 PENGGUNAAN TOKEN — PROYEK: {args.project}")
    else:
        usage = orch.usage_tracker.get_total_usage()
        records = orch.db.list_usage_records()
        print("\n📊 PENGGUNAAN TOKEN — SELURUH KANTOR AETHER OFFICE")

    print("─" * 60)
    print(f"   Total Permintaan (Requests) : {usage.get('total_requests', 0):,}")
    print(f"   Total Input Tokens          : {usage.get('total_input_tokens', 0):,}")
    print(f"   Total Output Tokens         : {usage.get('total_output_tokens', 0):,}")
    print(f"   Total Keseluruhan Tokens    : {usage.get('total_tokens', 0):,}")
    print(f"   Estimasi Total Biaya        : ${usage.get('total_cost', 0.0):.4f}")

    if records:
        print(f"\n📝 Catatan Transaksi Terbaru (Maksimal 10):")
        for rec in records[-10:]:
            print(f"   • Proyek: {rec['project_id']:<18} Petugas: {rec.get('employee_id','-'):<16} Model: {rec.get('model','-'):<14} Tokens: {rec.get('total_tokens',0):<6} Biaya: ${rec.get('estimated_cost',0.0):.5f}")
    orch.db.close()


def cmd_costs(args):
    """Computational Costs & Project Budget Management."""
    orch = _get_office_orchestrator()
    projs = orch.project_registry.list_projects()
    total_usage = orch.usage_tracker.get_total_usage()

    print("\n💵 AETHER OFFICE — KEUANGAN & BIAYA KOMPUTASI")
    print("─" * 65)
    print(f"   Total Estimasi Biaya Seluruh Kantor : ${total_usage.get('total_cost', 0.0):.4f}")
    print("\n📊 Rincian Anggaran Per Proyek:")
    for p in projs:
        b_info = orch.budget_manager.get_project_budget(p.project_id)
        budget = b_info.get("budget", 0.0)
        spent = b_info.get("spent", 0.0)
        remaining = b_info.get("remaining", 0.0)
        blocked_str = "⛔ TERBLOKIR" if b_info.get("is_blocked") else "Aman"

        rem_display = f"${remaining:.4f}" if remaining != float("inf") else "Tak Terbatas"
        pct_display = f"({(spent / budget) * 100:.1f}%)" if budget > 0 else ""
        print(f"   • {p.name:<26} Anggaran: ${budget:.2f} | Terpakai: ${spent:.4f} {pct_display:<8} | Sisa: {rem_display:<12} [{blocked_str}]")
    orch.db.close()


def cmd_office(args):
    """Master operational dashboard and runtime control for Aether Office."""
    action = getattr(args, "action", "status") or "status"
    orch = _get_office_orchestrator()
    runtime = orch.get_runtime()

    if action == "status":
        state = orch.office_status()
        rt_status = runtime.status()

        print("\n" + "=" * 55)
        print("           AETHER OFFICE — OPERATIONAL STATE")
        print("=" * 55)
        print(f"  Status Runtime : {'🟢 AKTIF' if rt_status['is_running'] else '⚪ STANDBY / SIAP'}")
        print(f"  Detak Jantung  : {rt_status['heartbeat_interval']} detik")
        print(f"  Total Tick     : {rt_status['ticks_count']}")

        print("\n📁 Projects")
        projs = orch.project_registry.list_projects()
        if not projs:
            print("  (Tidak ada proyek aktif)")
        for p in projs[:8]:
            status_dot = "●"
            print(f"  {status_dot} {p.name:<26} {p.status.value}")
        if len(projs) > 8:
            print(f"  ... dan {len(projs) - 8} proyek lainnya")

        print("\n👥 Workforce")
        print(f"  Total      : {state.total_employees}")
        print(f"  Available  : {state.available_employees}")
        print(f"  Busy       : {state.busy_employees}")
        print(f"  Offline    : {state.offline_employees}")

        print("\n📝 Tasks")
        print(f"  Running    : {state.running_tasks}")
        print(f"  Queued     : {state.queued_tasks}")
        print(f"  Blocked    : {state.blocked_projects}")

        print("\n📊 Usage")
        print(f"  Tokens     : {state.total_token_usage:,}")
        print(f"  Estimated  : ${state.total_cost:.2f}")
        print("\n" + "=" * 55 + "\n")
        orch.db.close()

    elif action == "start":
        from runtime import RuntimeConfig
        heartbeat = getattr(args, "heartbeat", None) or 5.0
        cfg = RuntimeConfig(heartbeat_interval=heartbeat)
        rt = orch.get_runtime(config=cfg)
        rt.install_signal_handlers()
        print("\n🚀 MEMULAI AETHER OFFICE RUNTIME ENGINE...")
        print(f"   Heartbeat Interval : {heartbeat} detik")
        print("   Tekan Ctrl+C untuk menghentikan secara aman (graceful shutdown).\n")
        max_ticks = getattr(args, "max_ticks", None)
        try:
            rt.run(max_ticks=max_ticks)
        except KeyboardInterrupt:
            rt.stop()
        print("\n🛑 Runtime Engine telah dihentikan secara aman.")
        orch.db.close()

    elif action == "stop":
        print("\n🛑 MENGIRIMKAN SINYAL PENGHENTIAN RUNTIME ENGINE...")
        if hasattr(orch, "db") and orch.db:
            orch.db.release_scheduler_lock(lock_name="office_scheduler")
        print("   Kunci scheduler dibebaskan. Runtime yang berjalan akan berhenti secara aman.")
        orch.db.close()

    elif action == "tick":
        no_exec = getattr(args, "no_execute", False)
        print("\n⚙️ MENJALANKAN SATU SIKLUS DETAK JANTUNG RUNTIME ENGINE...")
        res = runtime.tick(execute=not no_exec)
        print(f"   Tick Nomor          : #{res.tick_number}")
        print(f"   Tugas Dievaluasi    : {res.tasks_evaluated}")
        print(f"   Tugas Terjadwal     : {res.tasks_scheduled}")
        print(f"   Tugas Diselesaikan  : {res.tasks_completed}")
        print(f"   Tugas Gagal/Requeue : {res.tasks_failed}")
        print(f"   Konflik Terdeteksi  : {res.conflicts_detected}")
        print(f"   Waktu Eksekusi      : {res.duration_ms:.2f} ms")
        if res.scheduled_assignments:
            print(f"\n📋 Penugasan Dibuat:")
            for a in res.scheduled_assignments:
                print(f"   • Petugas {a['employee_name']} ({a['employee_id']}) → Tugas {a['task_id']} [Skor: {a['match_score']}] (Proyek: {a['project_id']})")
        orch.db.close()


def cmd_scheduler_tick(args):
    """Trigger a single scheduling tick."""
    orch = _get_office_orchestrator()
    print("\n⚙️ MENJALANKAN SIKLUS PENJADWALAN SCHEDULER ENGINE...")
    res = orch.scheduler_tick(execute=args.execute)
    print(f"   Tick Nomor          : #{res.tick_number}")
    print(f"   Tugas Dievaluasi    : {res.tasks_evaluated}")
    print(f"   Tugas Terjadwal     : {res.tasks_scheduled}")
    print(f"   Tugas Diselesaikan  : {res.tasks_completed}")
    print(f"   Tugas Gagal/Requeue : {res.tasks_failed}")
    print(f"   Konflik Terdeteksi  : {res.conflicts_detected}")
    print(f"   Waktu Eksekusi      : {res.duration_ms:.2f} ms")

    if res.scheduled_assignments:
        print(f"\n📋 Penugasan Dibuat:")
        for a in res.scheduled_assignments:
            print(f"   • Petugas {a['employee_name']} ({a['employee_id']}) → Tugas {a['task_id']} [Skor Kecocokan: {a['match_score']}] (Proyek: {a['project_id']})")
    orch.db.close()


def cmd_project_pause(args):
    """Pause an active project."""
    orch = _get_office_orchestrator()
    try:
        p = orch.pause_project(args.project_id, reason=args.reason)
        print(f"\n⏸️ Proyek '{p.name}' ({p.project_id}) berhasil DIJEDA.")
        print(f"   Alasan : {args.reason}")
    except Exception as e:
        print(f"❌ Gagal menjeda proyek: {e}")
    orch.db.close()


def cmd_project_resume(args):
    """Resume a paused project."""
    orch = _get_office_orchestrator()
    try:
        p = orch.resume_project(args.project_id)
        print(f"\n▶️ Proyek '{p.name}' ({p.project_id}) berhasil DILANJUTKAN kembali ke antrean aktif.")
    except Exception as e:
        print(f"❌ Gagal melanjutkan proyek: {e}")
    orch.db.close()


def cmd_objective(args):
    """Handler for Phase 8 business objective commands."""
    orch = _get_office_orchestrator()
    obj_orch = orch.get_objective_orchestrator()
    action = args.action

    if action == "create":
        title = args.target
        if not title:
            print("❌ Judul objektif wajib diisi. Contoh: python cli.py objective create 'Buat landing page SaaS'")
            orch.db.close()
            return
        crit_list = [c.strip() for c in args.criteria.split(",") if c.strip()] if args.criteria else None
        from projects import ProjectPriority
        prio = ProjectPriority(args.priority.upper())
        obj = obj_orch.create_objective(
            title=title,
            description=args.description,
            budget=args.budget,
            deadline=args.deadline,
            priority=prio,
            acceptance_criteria=crit_list,
            max_revisions=args.max_revisions,
        )
        print(f"\n🎯 OBJEKTIF BERHASIL DIBUAT:")
        print(f"   ID        : {obj.id}")
        print(f"   Judul     : {obj.title}")
        print(f"   Status    : {obj.status.value}")
        print(f"   Prioritas : {obj.priority.value}")
        print(f"   Anggaran  : ${obj.budget:.2f}")
        print(f"   Kriteria  : {len(obj.acceptance_criteria.criteria)} item terdaftar")
        orch.db.close()

    elif action == "list":
        objs = obj_orch.list_objectives()
        print(f"\n📋 DAFTAR OBJEKTIF BISNIS AETHER OFFICE ({len(objs)}):")
        print("─" * 72)
        if not objs:
            print("   (Belum ada objektif yang didaftarkan)")
        for o in objs:
            b_str = f"${o.budget:.2f}" if o.budget > 0 else "Fleksibel"
            rev_str = f" [Revisi: {o.revision_count}/{o.max_revisions}]" if o.revision_count > 0 else ""
            print(f"   • [{o.status.value:<10}] {o.id:<14} {o.title:<28} Budget: {b_str}{rev_str}")
        orch.db.close()

    elif action in ("show", "status"):
        obj_id = args.target
        if not obj_id:
            print("❌ ID Objektif wajib diisi. Contoh: python cli.py objective show <id>")
            orch.db.close()
            return
        obj = obj_orch.get_objective(obj_id)
        if not obj:
            print(f"❌ Objektif dengan ID '{obj_id}' tidak ditemukan.")
            orch.db.close()
            return
        print(f"\n🎯 RINCIAN OBJEKTIF: {obj.title}")
        print("─" * 65)
        print(f"   ID             : {obj.id}")
        print(f"   Status         : {obj.status.value}")
        print(f"   Prioritas      : {obj.priority.value}")
        print(f"   Alokasi Budget : ${obj.budget:.2f}")
        print(f"   Tenggat Waktu  : {obj.deadline or '-'}")
        print(f"   Proyek Terkait : {obj.project_id or '-'}")
        print(f"   Rencana ID     : {obj.execution_plan_id or '-'}")
        print(f"   Siklus Revisi  : {obj.revision_count} / {obj.max_revisions}")
        print(f"   Dibuat Pada    : {obj.created_at}")
        print(f"   Mulai/Selesai  : {obj.started_at or '-'} / {obj.completed_at or '-'}")
        if obj.failure_reason:
            print(f"   Kendala/Error  : {obj.failure_reason}")
        print(f"\n📋 Kriteria Penerimaan ({len(obj.acceptance_criteria.criteria)}):")
        for c in obj.acceptance_criteria.criteria:
            req_str = "[Wajib]" if c.required else "[Opsional]"
            print(f"   • {req_str:<9} {c.name:<30} ({c.criterion_type.value})")

        evals = orch.db.list_objective_evaluations(obj.id) if orch.db else []
        if evals:
            print(f"\n🔍 Riwayat Evaluasi Deliverable ({len(evals)}):")
            for ev in evals:
                print(f"   • [{ev['verdict']:<14}] {ev['feedback']}")

        orch.db.close()

    elif action == "run":
        obj_id = args.target
        if not obj_id:
            print("❌ ID Objektif wajib diisi. Contoh: python cli.py objective run <id>")
            orch.db.close()
            return
        print(f"\n🚀 MENJALANKAN PIPELINE OBJECTIVE-TO-OUTCOME ({obj_id})...")
        obj = obj_orch.run_objective(obj_id, auto_tick=True, max_ticks=args.ticks)
        print(f"\n🏁 HASIL AKHIR OBJEKTIF:")
        print(f"   ID        : {obj.id}")
        print(f"   Status    : {obj.status.value}")
        print(f"   Revisi    : {obj.revision_count} kali")
        if obj.status.value == "COMPLETED":
            print(f"   ✅ Objektif berhasil diselesaikan dan lolos evaluasi penerimaan!")
            if obj.result.get("feedback"):
                print(f"   Ulasan    : {obj.result['feedback']}")
        elif obj.status.value == "FAILED":
            print(f"   ❌ Objektif gagal mencapai kriteria penerimaan.")
            print(f"   Alasan    : {obj.failure_reason or obj.result.get('feedback')}")
        orch.db.close()

    elif action == "cancel":
        obj_id = args.target
        if not obj_id:
            print("❌ ID Objektif wajib diisi. Contoh: python cli.py objective cancel <id>")
            orch.db.close()
            return
        obj = obj_orch.cancel_objective(obj_id, reason=args.reason)
        print(f"\n🛑 Objektif '{obj.id}' telah DIBATALKAN.")
        print(f"   Alasan: {args.reason}")
        orch.db.close()

    elif action == "analyze":
        obj_id = args.target
        if not obj_id:
            print("❌ ID Objektif wajib diisi. Contoh: python cli.py objective analyze <id>")
            orch.db.close()
            return
        obj = obj_orch.get_objective(obj_id)
        if not obj:
            print(f"❌ Objektif dengan ID '{obj_id}' tidak ditemukan.")
            orch.db.close()
            return
        print(f"\n🔍 MENGANALISIS OBJEKTIF: {obj.title} ({obj.id})...")
        analysis = obj_orch.analyze_objective(obj.id)
        print(f"\n📊 HASIL ANALISIS OBJEKTIF:")
        print("─" * 60)
        print(f"   Klasifikasi Domain : {analysis.objective_type.value}")
        print(f"   Kompleksitas       : {analysis.complexity.value}")
        print(f"   Tingkat Ambiguitas : {analysis.ambiguity:.2f} ({'Tinggi (Perlu Klarifikasi)' if analysis.needs_clarification else 'Cukup Jelas'})")
        print(f"   Keyakinan Planner  : {analysis.confidence:.2f} ({analysis.confidence_level})")
        print(f"   Estimasi Durasi    : {analysis.estimated_duration}")
        print(f"   Estimasi Biaya     : ${analysis.estimated_cost:.2f}")
        print(f"   Kemampuan Butuh    : {', '.join(analysis.required_capabilities) if analysis.required_capabilities else '-'}")
        print(f"   Deliverable        : {', '.join(analysis.estimated_deliverables) if analysis.estimated_deliverables else '-'}")
        if analysis.clarifications:
            print(f"\n❓ PERTANYAAN KLARIFIKASI ({len(analysis.clarifications)}):")
            for c in analysis.clarifications:
                blk = "[BLOCKING]" if c.blocking else "[NON-BLOCKING]"
                print(f"   • {blk} {c.question}")
                print(f"     Alasan: {c.reason} (Prioritas: {c.priority})")
        if analysis.risks:
            print(f"\n⚠️  FAKTOR RISIKO TERDETEKSI ({len(analysis.risks)}):")
            for r in analysis.risks:
                print(f"   • [{r.severity.upper()}] {r.risk_type.value}: {r.description}")
        orch.db.close()

    elif action == "plan":
        obj_id = args.target
        if not obj_id:
            print("❌ ID Objektif wajib diisi. Contoh: python cli.py objective plan <id>")
            orch.db.close()
            return
        obj = obj_orch.get_objective(obj_id)
        if not obj:
            print(f"❌ Objektif dengan ID '{obj_id}' tidak ditemukan.")
            orch.db.close()
            return
        print(f"\n📐 MENYUSUN RENCANA EKSEKUSI ADAPTIF: {obj.title} ({obj.id})...")
        plan = obj_orch.plan_objective(obj.id)
        print(f"\n📋 RENCANA EKSEKUSI:")
        print("─" * 60)
        print(f"   Plan ID          : {plan.id}")
        print(f"   Strategi Domain  : {plan.metadata.get('strategy', '-')}")
        print(f"   Status Validasi  : {'✅ Lolos Validasi' if plan.is_valid else '❌ Gagal Validasi'}")
        if plan.validation_error:
            print(f"   Kendala Rencana  : {plan.validation_error}")
        print(f"   Estimasi Biaya   : ${plan.estimated_cost:.2f}")
        print(f"   Total Milestones : {len(plan.milestones)}")
        print(f"   Total Tugas      : {len(plan.tasks)}")
        if plan.metadata.get("quality_score") is not None:
            print(f"   Skor Kualitas    : {plan.metadata.get('quality_score')}/100 (Grade: {plan.metadata.get('quality_grade')})")
        if plan.metadata.get("optimizations"):
            print(f"\n⚡ Optimasi Rencana ({len(plan.metadata['optimizations'])}):")
            for opt in plan.metadata["optimizations"]:
                print(f"   • {opt}")
        print(f"\n📌 Rincian Milestones & Tugas:")
        for m in plan.milestones:
            print(f"   🏁 [{m.milestone_id}] {m.name}")
            for t_id in m.tasks:
                t_match = next((t for t in plan.tasks if t['task_id'] == t_id), None)
                if t_match:
                    role_str = f"[{t_match.get('preferred_role', 'agent')}]"
                    print(f"      - {t_id:<14} {role_str:<18} {t_match.get('title', '')}")
        orch.db.close()

    elif action == "risks":
        obj_id = args.target
        if not obj_id:
            print("❌ ID Objektif wajib diisi. Contoh: python cli.py objective risks <id>")
            orch.db.close()
            return
        obj = obj_orch.get_objective(obj_id)
        if not obj:
            print(f"❌ Objektif dengan ID '{obj_id}' tidak ditemukan.")
            orch.db.close()
            return
        analysis = obj_orch.analyze_objective(obj.id)
        print(f"\n🛡️  ANALISIS RISIKO OBJEKTIF: {obj.title} ({obj.id})")
        print("─" * 60)
        if not analysis.risks:
            print("   ✅ Tidak ditemukan risiko kritis pada objektif ini.")
        else:
            for r in analysis.risks:
                print(f"   • [{r.severity.upper()}] {r.risk_type.value}")
                print(f"     Deskripsi : {r.description}")
                if r.mitigation:
                    print(f"     Mitigasi  : {r.mitigation}")
        orch.db.close()

    elif action == "plan-quality":
        obj_id = args.target
        if not obj_id:
            print("❌ ID Objektif wajib diisi. Contoh: python cli.py objective plan-quality <id>")
            orch.db.close()
            return
        obj = obj_orch.get_objective(obj_id)
        if not obj:
            print(f"❌ Objektif dengan ID '{obj_id}' tidak ditemukan.")
            orch.db.close()
            return
        report = obj_orch.evaluate_plan_quality(obj.id)
        if not report:
            # Generate plan first if none exists
            obj_orch.plan_objective(obj.id)
            report = obj_orch.evaluate_plan_quality(obj.id)
        if not report:
            print(f"❌ Rencana eksekusi untuk objektif '{obj_id}' belum dapat dievaluasi kualitasnya.")
            orch.db.close()
            return
        print(f"\n🏆 EVALUASI KUALITAS RENCANA: {obj.title} ({obj.id})")
        print("─" * 60)
        print(f"   Skor Kelayakan : {report.score} / 100")
        print(f"   Predikat (Grade): {report.grade}")
        print(f"   Status Rencana : {'Lolos (Viable)' if report.is_viable else 'Tidak Layak (Non-Viable)'}")
        if report.issues:
            print(f"\n❌ Isu Kritis ({len(report.issues)}):")
            for iss in report.issues:
                print(f"   • {iss}")
        if report.warnings:
            print(f"\n⚠️  Peringatan ({len(report.warnings)}):")
            for w in report.warnings:
                print(f"   • {w}")
        if report.recommendations:
            print(f"\n💡 Rekomendasi Perbaikan ({len(report.recommendations)}):")
            for rec in report.recommendations:
                print(f"   • {rec}")
        orch.db.close()


if __name__ == "__main__":
    main()



"""SQLite database for tasks and events."""

import sqlite3
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Callable, Any, List, Dict
from status import validate_transition, ALL_STATES
from events import Event, EventBus, EVENT_AGENT_STATE_CHANGED

logger = logging.getLogger("aether.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str, event_bus: Optional[EventBus] = None):
        self.db_path = db_path
        self.event_bus = event_bus
        if ":memory:" not in db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        if ":memory:" not in db_path:
            try:
                self.conn.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                brief TEXT,
                status TEXT DEFAULT 'ACTIVE',
                output_dir TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'BACKLOG',
                assigned_to TEXT,
                priority INTEGER DEFAULT 0,
                parent_id INTEGER,
                dependencies TEXT DEFAULT '[]',
                result TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                agent_role TEXT,
                task_id INTEGER,
                data TEXT DEFAULT '{}',
                created_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                agent_role TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT DEFAULT '{}',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dev_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                attempt INTEGER DEFAULT 0,
                error TEXT,
                exports TEXT DEFAULT '[]',
                purpose TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS agent_states (
                agent_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                agent_role TEXT NOT NULL,
                state TEXT NOT NULL,
                details TEXT DEFAULT '{}',
                updated_at TEXT,
                PRIMARY KEY (agent_id, project_id)
            );

            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                default_model TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS departments (
                id TEXT PRIMARY KEY,
                organization_id TEXT DEFAULT 'aether_office',
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                default_model TEXT DEFAULT '{}',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                department_id TEXT NOT NULL,
                description TEXT DEFAULT '',
                capabilities TEXT DEFAULT '[]',
                default_model TEXT DEFAULT '{}',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS employees (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role_id TEXT NOT NULL,
                department_id TEXT NOT NULL,
                capabilities TEXT DEFAULT '[]',
                personality TEXT DEFAULT '{}',
                model TEXT DEFAULT '{}',
                status TEXT DEFAULT 'active',
                availability TEXT DEFAULT 'available',
                live_state TEXT DEFAULT 'IDLE',
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS capabilities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS employee_capabilities (
                employee_id TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                PRIMARY KEY (employee_id, capability_id),
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            );

            -- Phase 5: Teams, WorkTasks, Artifacts, Reviews, Discussions
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                objective TEXT DEFAULT '',
                lead_employee_id TEXT,
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS team_members (
                team_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                role TEXT DEFAULT '',
                joined_at TEXT,
                PRIMARY KEY (team_id, employee_id)
            );

            CREATE TABLE IF NOT EXISTS work_tasks (
                task_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                parent_task_id TEXT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'PENDING',
                priority INTEGER DEFAULT 0,
                assigned_employee_id TEXT,
                assigned_team_id TEXT,
                required_capabilities TEXT DEFAULT '[]',
                preferred_role TEXT,
                dependencies TEXT DEFAULT '[]',
                artifacts TEXT DEFAULT '[]',
                result TEXT,
                created_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS task_dependencies (
                task_id TEXT NOT NULL,
                depends_on_task_id TEXT NOT NULL,
                PRIMARY KEY (task_id, depends_on_task_id)
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                type TEXT DEFAULT 'document',
                name TEXT NOT NULL,
                path TEXT,
                content TEXT DEFAULT '',
                created_by TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                metadata TEXT DEFAULT '{}',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS handoffs (
                handoff_id TEXT PRIMARY KEY,
                from_employee_id TEXT NOT NULL,
                to_employee_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                artifact_ids TEXT DEFAULT '[]',
                message TEXT DEFAULT '',
                status TEXT DEFAULT 'CREATED',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                reviewer_employee_id TEXT NOT NULL,
                author_employee_id TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                score REAL DEFAULT 0.0,
                feedback TEXT DEFAULT '',
                required_changes TEXT DEFAULT '[]',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS discussions (
                discussion_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                task_id TEXT,
                topic TEXT NOT NULL,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS discussion_messages (
                message_id TEXT PRIMARY KEY,
                discussion_id TEXT NOT NULL,
                sender_employee_id TEXT NOT NULL,
                recipient_employee_id TEXT,
                task_id TEXT,
                message_type TEXT DEFAULT 'QUESTION',
                content TEXT DEFAULT '',
                created_at TEXT
            );

            -- Phase 6: Autonomous Office Operations & Multi-Project Scheduling
            CREATE TABLE IF NOT EXISTS project_queue (
                project_id TEXT PRIMARY KEY,
                priority_weight REAL DEFAULT 0.0,
                waiting_duration INTEGER DEFAULT 0,
                starvation_counter INTEGER DEFAULT 0,
                status TEXT DEFAULT 'WAITING',
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS employee_reservations (
                employee_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                reserved_at TEXT NOT NULL,
                expires_at TEXT
            );

            CREATE TABLE IF NOT EXISTS usage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT DEFAULT 'aether_office',
                project_id TEXT NOT NULL,
                task_id TEXT,
                employee_id TEXT,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                requests INTEGER DEFAULT 1,
                estimated_cost REAL DEFAULT 0.0,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS project_budgets (
                project_id TEXT PRIMARY KEY,
                budget REAL DEFAULT 0.0,
                spent REAL DEFAULT 0.0,
                warning_threshold REAL DEFAULT 0.8,
                is_blocked INTEGER DEFAULT 0,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS scheduler_runs (
                run_id TEXT PRIMARY KEY,
                tick_number INTEGER DEFAULT 0,
                tasks_evaluated INTEGER DEFAULT 0,
                tasks_scheduled INTEGER DEFAULT 0,
                conflicts_detected INTEGER DEFAULT 0,
                duration_ms REAL DEFAULT 0.0,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS scheduler_locks (
                lock_name TEXT PRIMARY KEY,
                locked_by TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            -- Phase 8: Objective-to-Outcome Engine
            CREATE TABLE IF NOT EXISTS objectives (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'CREATED',
                priority TEXT DEFAULT 'NORMAL',
                deadline TEXT,
                budget REAL DEFAULT 0.0,
                acceptance_criteria TEXT DEFAULT '[]',
                project_id TEXT,
                execution_plan_id TEXT,
                revision_count INTEGER DEFAULT 0,
                max_revisions INTEGER DEFAULT 3,
                result TEXT DEFAULT '{}',
                failure_reason TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                started_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS execution_plans (
                id TEXT PRIMARY KEY,
                objective_id TEXT NOT NULL,
                milestones TEXT DEFAULT '[]',
                tasks TEXT DEFAULT '[]',
                dependencies TEXT DEFAULT '{}',
                estimated_cost REAL DEFAULT 0.0,
                required_skills TEXT DEFAULT '[]',
                is_valid INTEGER DEFAULT 1,
                validation_error TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                FOREIGN KEY (objective_id) REFERENCES objectives(id)
            );

            CREATE TABLE IF NOT EXISTS objective_evaluations (
                id TEXT PRIMARY KEY,
                objective_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                criteria_results TEXT DEFAULT '[]',
                feedback TEXT DEFAULT '',
                revision_requested INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                FOREIGN KEY (objective_id) REFERENCES objectives(id)
            );

            -- Phase 9: Adaptive Planning & Intelligence
            CREATE TABLE IF NOT EXISTS objective_analyses (
                id TEXT PRIMARY KEY,
                objective_id TEXT NOT NULL,
                objective_type TEXT NOT NULL,
                complexity TEXT NOT NULL,
                ambiguity_score REAL DEFAULT 0.0,
                needs_clarification INTEGER DEFAULT 0,
                clarifications TEXT DEFAULT '[]',
                required_capabilities TEXT DEFAULT '[]',
                estimated_deliverables TEXT DEFAULT '[]',
                estimated_duration REAL DEFAULT 0.0,
                estimated_cost REAL DEFAULT 0.0,
                risks TEXT DEFAULT '[]',
                confidence REAL DEFAULT 1.0,
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                FOREIGN KEY (objective_id) REFERENCES objectives(id)
            );

            CREATE TABLE IF NOT EXISTS plan_quality_reports (
                id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                objective_id TEXT NOT NULL,
                score REAL DEFAULT 0.0,
                completeness_score REAL DEFAULT 0.0,
                dependency_score REAL DEFAULT 0.0,
                capability_score REAL DEFAULT 0.0,
                budget_score REAL DEFAULT 0.0,
                criteria_coverage_score REAL DEFAULT 0.0,
                issues TEXT DEFAULT '[]',
                warnings TEXT DEFAULT '[]',
                recommendations TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at TEXT,
                FOREIGN KEY (plan_id) REFERENCES execution_plans(id)
            );
        """)
        self.conn.commit()

        # Schema migrations for backward-compatibility with existing events tables
        for col, col_type in [("event_id", "TEXT"), ("agent_id", "TEXT"), ("status", "TEXT")]:
            try:
                self.conn.execute(f"ALTER TABLE events ADD COLUMN {col} {col_type};")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

        # Phase 6 migrations for projects table
        project_cols = [
            ("description", "TEXT DEFAULT ''"),
            ("priority", "TEXT DEFAULT 'NORMAL'"),
            ("deadline", "TEXT"),
            ("owner_employee_id", "TEXT"),
            ("team_id", "TEXT"),
            ("budget", "REAL DEFAULT 0.0"),
            ("spent", "REAL DEFAULT 0.0"),
            ("started_at", "TEXT"),
            ("completed_at", "TEXT"),
            ("metadata", "TEXT DEFAULT '{}'"),
        ]
        for col, col_def in project_cols:
            try:
                self.conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {col_def};")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    # --- Projects ---

    def create_project(self, project_id: str, name: str, brief: str, output_dir: str) -> str:
        now = _now()
        self.conn.execute("DELETE FROM dev_units WHERE project_id=?", (project_id,))
        self.conn.execute("DELETE FROM tasks WHERE project_id=?", (project_id,))
        self.conn.execute("DELETE FROM events WHERE project_id=?", (project_id,))
        self.conn.execute("DELETE FROM agent_states WHERE project_id=?", (project_id,))
        self.conn.execute(
            "INSERT OR REPLACE INTO projects (id, name, brief, output_dir, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (project_id, name, brief, output_dir, now, now),
        )
        self.conn.commit()
        return project_id

    def get_project(self, project_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def update_project_status(self, project_id: str, status: str):
        self.conn.execute(
            "UPDATE projects SET status=?, updated_at=? WHERE id=?",
            (status, _now(), project_id),
        )
        self.conn.commit()

    # --- Tasks ---

    def create_task(self, project_id: str, title: str, description: str = "",
                    assigned_to: str = "", priority: int = 0,
                    dependencies: list[int] = None) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO tasks (project_id, title, description, assigned_to, priority, dependencies, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (project_id, title, description, assigned_to, priority,
             json.dumps(dependencies or []), now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_task_status(self, task_id: int, status: str, result: str = None, force: bool = False):
        """Update task status with transition validation."""
        current_row = self.conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if current_row:
            current = current_row["status"]
            if not force and not validate_transition(current, status):
                logger.warning(f"Invalid transition: {current} -> {status} (task {task_id})")
                self.log_event(
                    self.get_task(task_id)["project_id"] if self.get_task(task_id) else "?",
                    "invalid_transition", data={"task_id": task_id, "from": current, "to": status},
                )
                # Still allow it — don't block, but log the violation
        now = _now()
        if result:
            self.conn.execute(
                "UPDATE tasks SET status=?, result=?, updated_at=? WHERE id=?",
                (status, result, now, task_id),
            )
        else:
            self.conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                (status, now, task_id),
            )
        self.conn.commit()

    def get_tasks(self, project_id: str, status: str = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE project_id=? AND status=? ORDER BY priority DESC, id",
                (project_id, status),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE project_id=? ORDER BY priority DESC, id",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_task(self, task_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    # --- Events ---

    def log_event(self, project_id: str, event_type: str, agent_role: str = None,
                  task_id: int = None, data: dict = None, agent_id: str = None,
                  status: str = None, event: Optional[Event] = None) -> Event:
        """Log event to SQLite and dispatch to EventBus if attached."""
        if event is not None:
            evt = event
            now = evt.timestamp
            p_id = evt.project_id
            e_type = evt.event_type
            a_role = evt.agent_role
            t_id = evt.task_id
            payload = evt.payload
            a_id = evt.agent_id
            e_status = evt.status
            e_id = evt.event_id
        else:
            now = _now()
            p_id = project_id
            e_type = event_type
            a_role = agent_role
            t_id = task_id
            payload = data or {}
            a_id = agent_id or (f"{agent_role}_001" if agent_role else None)
            e_status = status
            evt = Event(
                event_type=e_type,
                project_id=p_id,
                task_id=t_id,
                agent_id=a_id,
                agent_role=a_role,
                status=e_status,
                payload=payload,
                timestamp=now,
            )
            e_id = evt.event_id

        self.conn.execute(
            "INSERT INTO events (project_id, event_type, agent_role, task_id, data, created_at, event_id, agent_id, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (p_id, e_type, a_role, t_id, json.dumps(payload), now, e_id, a_id, e_status),
        )
        self.conn.commit()

        if self.event_bus:
            self.event_bus.publish(evt)

        return evt

    def get_events(self, project_id: str, event_type: str = None) -> list[dict]:
        if event_type:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE project_id=? AND event_type=? ORDER BY id",
                (project_id, event_type),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def replay_events(self, project_id: str, since_id: Optional[int] = None,
                      handler: Optional[Callable[[Event], None]] = None) -> list[Event]:
        """Replay events for a project from SQLite storage, optionally invoking handler."""
        if since_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE project_id=? AND id > ? ORDER BY id",
                (project_id, since_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()

        replayed: list[Event] = []
        for r in rows:
            d = dict(r)
            raw_data = d.get("data") or "{}"
            try:
                payload = json.loads(raw_data)
            except Exception:
                payload = {"raw": raw_data}
            evt = Event(
                event_id=d.get("event_id") or f"legacy_{d['id']}",
                timestamp=d.get("created_at") or _now(),
                project_id=d.get("project_id", ""),
                task_id=d.get("task_id"),
                agent_id=d.get("agent_id") or (f"{d.get('agent_role')}_001" if d.get("agent_role") else None),
                agent_role=d.get("agent_role"),
                event_type=d.get("event_type", "unknown"),
                status=d.get("status"),
                payload=payload,
                metadata={"db_id": d["id"]},
            )
            replayed.append(evt)
            if handler:
                try:
                    handler(evt)
                except Exception as e:
                    logger.error(f"Error in replay handler: {e}")
        return replayed

    # --- Agent States ---

    def set_agent_state(self, agent_id: str, project_id: str, agent_role: str,
                        state: str, details: dict = None) -> dict:
        """Set current live state of an agent in a project."""
        now = _now()
        payload_str = json.dumps(details or {})
        self.conn.execute(
            "INSERT OR REPLACE INTO agent_states (agent_id, project_id, agent_role, state, details, updated_at) VALUES (?,?,?,?,?,?)",
            (agent_id, project_id, agent_role, state, payload_str, now),
        )
        self.conn.commit()
        return {
            "agent_id": agent_id,
            "project_id": project_id,
            "agent_role": agent_role,
            "state": state,
            "details": details or {},
            "updated_at": now,
        }

    def get_agent_state(self, agent_id: str, project_id: str = None) -> Optional[dict]:
        """Directly get the current state of an agent without replaying historical events."""
        if project_id:
            row = self.conn.execute(
                "SELECT * FROM agent_states WHERE agent_id=? AND project_id=?",
                (agent_id, project_id),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM agent_states WHERE agent_id=? ORDER BY updated_at DESC LIMIT 1",
                (agent_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["details"] = json.loads(d.get("details") or "{}")
        except Exception:
            d["details"] = {}
        return d

    def get_all_agent_states(self, project_id: str) -> list[dict]:
        """Get all agent current states for a project."""
        rows = self.conn.execute(
            "SELECT * FROM agent_states WHERE project_id=? ORDER BY agent_id",
            (project_id,),
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.get("details") or "{}")
            except Exception:
                d["details"] = {}
            results.append(d)
        return results

    # --- Audit ---

    def audit(self, project_id: str, agent_role: str, action: str, details: dict = None):
        self.conn.execute(
            "INSERT INTO audit_log (project_id, agent_role, action, details, created_at) VALUES (?,?,?,?,?)",
            (project_id, agent_role, action, json.dumps(details or {}), _now()),
        )
        self.conn.commit()

    def get_audit_log(self, project_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM audit_log WHERE project_id=? ORDER BY id",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()

    # --- Dev Units (Phase 2) ---

    def create_dev_unit(self, project_id: str, path: str, purpose: str = "",
                        exports: list[str] = None) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO dev_units (project_id, path, purpose, exports, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (project_id, path, purpose, json.dumps(exports or []), now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_dev_units(self, project_id: str, status: str = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM dev_units WHERE project_id=? AND status=? ORDER BY id",
                (project_id, status),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM dev_units WHERE project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_dev_unit(self, unit_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM dev_units WHERE id=?", (unit_id,)).fetchone()
        return dict(row) if row else None

    def get_dev_unit_by_path(self, project_id: str, path: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM dev_units WHERE project_id=? AND path=?",
            (project_id, path),
        ).fetchone()
        return dict(row) if row else None

    def update_dev_unit_status(self, unit_id: int, status: str, error: str = None,
                               attempt: int = None):
        now = _now()
        if attempt is not None:
            self.conn.execute(
                "UPDATE dev_units SET status=?, error=?, attempt=?, updated_at=? WHERE id=?",
                (status, error, attempt, now, unit_id),
            )
        else:
            self.conn.execute(
                "UPDATE dev_units SET status=?, error=?, updated_at=? WHERE id=?",
                (status, error, now, unit_id),
            )
        self.conn.commit()

    # --- Workforce & Organization (Phase 4) ---

    def save_organization(self, name: str, default_model: dict = None, metadata: dict = None, org_id: str = "aether_office"):
        now = _now()
        self.conn.execute(
            """INSERT INTO organizations (id, name, default_model, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   default_model=excluded.default_model,
                   metadata=excluded.metadata,
                   updated_at=excluded.updated_at""",
            (org_id, name, json.dumps(default_model or {}), json.dumps(metadata or {}), now, now),
        )
        self.conn.commit()

    def get_organization(self, org_id: str = "aether_office") -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["default_model"] = json.loads(d.get("default_model") or "{}")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    def save_department(self, dept_id: str, name: str, description: str = "", default_model: dict = None, org_id: str = "aether_office"):
        now = _now()
        self.conn.execute(
            """INSERT INTO departments (id, organization_id, name, description, default_model, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   description=excluded.description,
                   default_model=excluded.default_model""",
            (dept_id, org_id, name, description, json.dumps(default_model or {}), now),
        )
        self.conn.commit()

    def get_departments(self, org_id: Optional[str] = None) -> list[dict]:
        if org_id:
            rows = self.conn.execute("SELECT * FROM departments WHERE organization_id=? ORDER BY id", (org_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM departments ORDER BY id").fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["default_model"] = json.loads(d.get("default_model") or "{}")
            res.append(d)
        return res

    def get_department(self, dept_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM departments WHERE id=?", (dept_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["default_model"] = json.loads(d.get("default_model") or "{}")
        return d

    def save_role(self, role_id: str, name: str, department_id: str, description: str = "", capabilities: list = None, default_model: dict = None):
        now = _now()
        self.conn.execute(
            """INSERT INTO roles (id, name, department_id, description, capabilities, default_model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   department_id=excluded.department_id,
                   description=excluded.description,
                   capabilities=excluded.capabilities,
                   default_model=excluded.default_model""",
            (role_id, name, department_id, description, json.dumps(capabilities or []), json.dumps(default_model or {}), now),
        )
        self.conn.commit()

    def get_roles(self, department_id: Optional[str] = None) -> list[dict]:
        if department_id:
            rows = self.conn.execute("SELECT * FROM roles WHERE department_id=? ORDER BY id", (department_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM roles ORDER BY id").fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["capabilities"] = json.loads(d.get("capabilities") or "[]")
            d["default_model"] = json.loads(d.get("default_model") or "{}")
            res.append(d)
        return res

    def get_role(self, role_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["capabilities"] = json.loads(d.get("capabilities") or "[]")
        d["default_model"] = json.loads(d.get("default_model") or "{}")
        return d

    def save_employee(self, employee_id: str, name: str, role_id: str, department_id: str,
                      capabilities: list = None, personality: dict = None, model: dict = None,
                      status: str = "active", availability: str = "available",
                      live_state: str = "IDLE", metadata: dict = None):
        now = _now()
        caps = capabilities or []
        self.conn.execute(
            """INSERT INTO employees (id, name, role_id, department_id, capabilities, personality, model, status, availability, live_state, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   role_id=excluded.role_id,
                   department_id=excluded.department_id,
                   capabilities=excluded.capabilities,
                   personality=excluded.personality,
                   model=excluded.model,
                   status=excluded.status,
                   availability=excluded.availability,
                   live_state=excluded.live_state,
                   metadata=excluded.metadata,
                   updated_at=excluded.updated_at""",
            (
                employee_id, name, role_id, department_id,
                json.dumps(caps),
                json.dumps(personality or {}),
                json.dumps(model or {}),
                status, availability, live_state,
                json.dumps(metadata or {}),
                now, now,
            ),
        )

        # Sync employee_capabilities table
        self.conn.execute("DELETE FROM employee_capabilities WHERE employee_id=?", (employee_id,))
        for cap in caps:
            # Ensure capability exists in capabilities table
            self.conn.execute(
                "INSERT OR IGNORE INTO capabilities (id, name, category) VALUES (?, ?, ?)",
                (cap, cap.replace("_", " ").title(), department_id),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO employee_capabilities (employee_id, capability_id) VALUES (?, ?)",
                (employee_id, cap),
            )

        self.conn.commit()

    def get_employee(self, employee_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["capabilities"] = json.loads(d.get("capabilities") or "[]")
        d["personality"] = json.loads(d.get("personality") or "{}")
        d["model"] = json.loads(d.get("model") or "{}")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    def get_employees(self, role_id: Optional[str] = None, department_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM employees WHERE 1=1"
        params = []
        if role_id:
            query += " AND role_id=?"
            params.append(role_id)
        if department_id:
            query += " AND department_id=?"
            params.append(department_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY id"

        rows = self.conn.execute(query, tuple(params)).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["capabilities"] = json.loads(d.get("capabilities") or "[]")
            d["personality"] = json.loads(d.get("personality") or "{}")
            d["model"] = json.loads(d.get("model") or "{}")
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            res.append(d)
        return res

    def update_employee_status(self, employee_id: str, status: Optional[str] = None,
                               availability: Optional[str] = None, live_state: Optional[str] = None):
        now = _now()
        updates = []
        params = []
        if status is not None:
            updates.append("status=?")
            params.append(status)
        if availability is not None:
            updates.append("availability=?")
            params.append(availability)
        if live_state is not None:
            updates.append("live_state=?")
            params.append(live_state)

        if not updates:
            return

        updates.append("updated_at=?")
        params.append(now)
        params.append(employee_id)

        sql = f"UPDATE employees SET {', '.join(updates)} WHERE id=?"
        self.conn.execute(sql, tuple(params))
        self.conn.commit()

    def sync_organization_to_db(self, org):
        """Persist entire Organization in-memory graph to SQLite database."""
        self.save_organization(
            name=org.name,
            default_model=getattr(org, "default_model", {}),
        )
        for dept in org.list_departments():
            self.save_department(
                dept_id=dept.department_id,
                name=dept.name,
                description=dept.description,
                default_model=dept.default_model,
            )
        for role in org.list_roles():
            self.save_role(
                role_id=role.role_id,
                name=role.name,
                department_id=role.department,
                description=role.description,
                capabilities=role.capabilities,
                default_model=role.default_model,
            )
        for emp in org.list_employees():
            self.save_employee(
                employee_id=emp.employee_id,
                name=emp.name,
                role_id=emp.role,
                department_id=emp.department,
                capabilities=emp.capabilities,
                personality=emp.personality,
                model=emp.model,
                status=emp.status,
                availability=emp.availability,
                live_state=emp.live_state,
                metadata=emp.metadata,
            )

    # =========================================================================
    # Phase 5: Teams, WorkTasks, Artifacts, Handoffs, Reviews, Discussions
    # =========================================================================

    # --- Teams ---

    def save_team(
        self,
        team_id: str,
        project_id: str,
        name: str,
        objective: str = "",
        lead_employee_id: Optional[str] = None,
        status: str = "active",
        metadata: Optional[dict] = None,
    ) -> None:
        now = _now()
        meta_str = json.dumps(metadata or {})
        self.conn.execute("""
            INSERT INTO teams (id, project_id, name, objective, lead_employee_id, status, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                objective = excluded.objective,
                lead_employee_id = excluded.lead_employee_id,
                status = excluded.status,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at;
        """, (team_id, project_id, name, objective, lead_employee_id, status, meta_str, now, now))
        self.conn.commit()

    def get_team(self, team_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
        d["members"] = self.get_team_members(team_id)
        return d

    def list_teams(self, project_id: Optional[str] = None) -> list[dict]:
        if project_id:
            rows = self.conn.execute("SELECT * FROM teams WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM teams ORDER BY created_at DESC").fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
            d["members"] = self.get_team_members(d["id"])
            res.append(d)
        return res

    def add_team_member(self, team_id: str, employee_id: str, role: str = "") -> None:
        now = _now()
        self.conn.execute("""
            INSERT OR REPLACE INTO team_members (team_id, employee_id, role, joined_at)
            VALUES (?, ?, ?, ?)
        """, (team_id, employee_id, role, now))
        self.conn.commit()

    def remove_team_member(self, team_id: str, employee_id: str) -> None:
        self.conn.execute("DELETE FROM team_members WHERE team_id = ? AND employee_id = ?", (team_id, employee_id))
        self.conn.commit()

    def get_team_members(self, team_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM team_members WHERE team_id = ?", (team_id,)).fetchall()
        return [dict(r) for r in rows]

    # --- Work Tasks ---

    def save_work_task(
        self,
        task_id: str,
        project_id: str,
        title: str,
        description: str = "",
        status: str = "PENDING",
        priority: int = 0,
        parent_task_id: Optional[str] = None,
        assigned_employee_id: Optional[str] = None,
        assigned_team_id: Optional[str] = None,
        required_capabilities: Optional[list[str]] = None,
        preferred_role: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
        artifacts: Optional[list[str]] = None,
        result: Optional[Any] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        now = _now()
        caps_str = json.dumps(required_capabilities or [])
        deps_str = json.dumps(dependencies or [])
        arts_str = json.dumps(artifacts or [])
        res_str = json.dumps(result) if result is not None else None
        meta_str = json.dumps(metadata or {})

        self.conn.execute("""
            INSERT INTO work_tasks (
                task_id, project_id, parent_task_id, title, description, status, priority,
                assigned_employee_id, assigned_team_id, required_capabilities, preferred_role,
                dependencies, artifacts, result, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                status = excluded.status,
                priority = excluded.priority,
                assigned_employee_id = excluded.assigned_employee_id,
                assigned_team_id = excluded.assigned_team_id,
                required_capabilities = excluded.required_capabilities,
                preferred_role = excluded.preferred_role,
                dependencies = excluded.dependencies,
                artifacts = excluded.artifacts,
                result = excluded.result,
                metadata = excluded.metadata;
        """, (
            task_id, project_id, parent_task_id, title, description, status, priority,
            assigned_employee_id, assigned_team_id, caps_str, preferred_role,
            deps_str, arts_str, res_str, now, meta_str
        ))

        # Update task_dependencies table
        self.conn.execute("DELETE FROM task_dependencies WHERE task_id = ?", (task_id,))
        for dep in (dependencies or []):
            self.conn.execute("INSERT OR IGNORE INTO task_dependencies (task_id, depends_on_task_id) VALUES (?, ?)", (task_id, dep))

        self.conn.commit()

    def get_work_task(self, task_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM work_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["required_capabilities"] = json.loads(d["required_capabilities"]) if d["required_capabilities"] else []
        d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else []
        d["artifacts"] = json.loads(d["artifacts"]) if d["artifacts"] else []
        d["result"] = json.loads(d["result"]) if d["result"] else None
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
        return d

    def list_work_tasks(self, project_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM work_tasks WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY priority DESC, created_at ASC"

        rows = self.conn.execute(query, params).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["required_capabilities"] = json.loads(d["required_capabilities"]) if d["required_capabilities"] else []
            d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else []
            d["artifacts"] = json.loads(d["artifacts"]) if d["artifacts"] else []
            d["result"] = json.loads(d["result"]) if d["result"] else None
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
            res.append(d)
        return res

    def update_work_task_status(
        self,
        task_id: str,
        status: str,
        result: Optional[Any] = None,
        completed_at: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> None:
        now = _now()
        res_str = json.dumps(result) if result is not None else None
        updates = ["status = ?"]
        params = [status]

        if result is not None:
            updates.append("result = ?")
            params.append(res_str)
        if started_at:
            updates.append("started_at = ?")
            params.append(started_at)
        if completed_at:
            updates.append("completed_at = ?")
            params.append(completed_at)
        elif status in ("COMPLETED", "FAILED", "CANCELLED"):
            updates.append("completed_at = ?")
            params.append(now)

        params.append(task_id)
        sql = f"UPDATE work_tasks SET {', '.join(updates)} WHERE task_id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()

    # --- Artifacts ---

    def save_artifact(
        self,
        artifact_id: str,
        task_id: str,
        project_id: str,
        type: str = "document",
        name: str = "",
        path: Optional[str] = None,
        content: str = "",
        created_by: str = "",
        version: int = 1,
        metadata: Optional[dict] = None,
    ) -> None:
        now = _now()
        meta_str = json.dumps(metadata or {})
        self.conn.execute("""
            INSERT INTO artifacts (
                artifact_id, task_id, project_id, type, name, path, content, created_by, version, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                name = excluded.name,
                path = excluded.path,
                content = excluded.content,
                version = excluded.version,
                metadata = excluded.metadata;
        """, (artifact_id, task_id, project_id, type, name, path, content, created_by, version, meta_str, now))
        self.conn.commit()

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
        return d

    def list_artifacts(self, project_id: Optional[str] = None, task_id: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM artifacts WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        query += " ORDER BY created_at ASC"

        rows = self.conn.execute(query, params).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
            res.append(d)
        return res

    # --- Handoffs ---

    def save_handoff(
        self,
        handoff_id: str,
        from_employee_id: str,
        to_employee_id: str,
        task_id: str,
        project_id: str,
        artifact_ids: Optional[list[str]] = None,
        message: str = "",
        status: str = "CREATED",
    ) -> None:
        now = _now()
        arts_str = json.dumps(artifact_ids or [])
        self.conn.execute("""
            INSERT INTO handoffs (
                handoff_id, from_employee_id, to_employee_id, task_id, project_id, artifact_ids, message, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(handoff_id) DO UPDATE SET
                status = excluded.status,
                message = excluded.message,
                artifact_ids = excluded.artifact_ids,
                updated_at = excluded.updated_at;
        """, (handoff_id, from_employee_id, to_employee_id, task_id, project_id, arts_str, message, status, now, now))
        self.conn.commit()

    def get_handoff(self, handoff_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?", (handoff_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["artifact_ids"] = json.loads(d["artifact_ids"]) if d["artifact_ids"] else []
        return d

    def list_handoffs(self, project_id: Optional[str] = None, to_employee_id: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM handoffs WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if to_employee_id:
            query += " AND to_employee_id = ?"
            params.append(to_employee_id)
        query += " ORDER BY created_at DESC"

        rows = self.conn.execute(query, params).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["artifact_ids"] = json.loads(d["artifact_ids"]) if d["artifact_ids"] else []
            res.append(d)
        return res

    def update_handoff_status(self, handoff_id: str, status: str) -> None:
        now = _now()
        self.conn.execute("UPDATE handoffs SET status = ?, updated_at = ? WHERE handoff_id = ?", (status, now, handoff_id))
        self.conn.commit()

    # --- Reviews ---

    def save_review(
        self,
        review_id: str,
        artifact_id: str,
        task_id: str,
        reviewer_employee_id: str,
        author_employee_id: str,
        status: str = "PENDING",
        score: float = 0.0,
        feedback: str = "",
        required_changes: Optional[list[str]] = None,
    ) -> None:
        now = _now()
        changes_str = json.dumps(required_changes or [])
        self.conn.execute("""
            INSERT INTO reviews (
                review_id, artifact_id, task_id, reviewer_employee_id, author_employee_id,
                status, score, feedback, required_changes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                status = excluded.status,
                score = excluded.score,
                feedback = excluded.feedback,
                required_changes = excluded.required_changes,
                updated_at = excluded.updated_at;
        """, (review_id, artifact_id, task_id, reviewer_employee_id, author_employee_id, status, score, feedback, changes_str, now, now))
        self.conn.commit()

    def get_review(self, review_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM reviews WHERE review_id = ?", (review_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["required_changes"] = json.loads(d["required_changes"]) if d["required_changes"] else []
        return d

    def list_reviews(self, project_id: Optional[str] = None, artifact_id: Optional[str] = None, task_id: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM reviews WHERE 1=1"
        params = []
        if artifact_id:
            query += " AND artifact_id = ?"
            params.append(artifact_id)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        query += " ORDER BY created_at DESC"

        rows = self.conn.execute(query, params).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["required_changes"] = json.loads(d["required_changes"]) if d["required_changes"] else []
            res.append(d)
        return res

    def update_review(
        self,
        review_id: str,
        status: str,
        score: Optional[float] = None,
        feedback: Optional[str] = None,
        required_changes: Optional[list[str]] = None,
    ) -> None:
        now = _now()
        updates = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if score is not None:
            updates.append("score = ?")
            params.append(score)
        if feedback is not None:
            updates.append("feedback = ?")
            params.append(feedback)
        if required_changes is not None:
            updates.append("required_changes = ?")
            params.append(json.dumps(required_changes))

        params.append(review_id)
        sql = f"UPDATE reviews SET {', '.join(updates)} WHERE review_id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()

    # --- Discussions ---

    def save_discussion(
        self,
        discussion_id: str,
        project_id: str,
        topic: str,
        task_id: Optional[str] = None,
        status: str = "OPEN",
    ) -> None:
        now = _now()
        self.conn.execute("""
            INSERT INTO discussions (discussion_id, project_id, task_id, topic, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discussion_id) DO UPDATE SET
                topic = excluded.topic,
                status = excluded.status,
                updated_at = excluded.updated_at;
        """, (discussion_id, project_id, task_id, topic, status, now, now))
        self.conn.commit()

    def get_discussion(self, discussion_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM discussions WHERE discussion_id = ?", (discussion_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["messages"] = self.get_discussion_messages(discussion_id)
        return d

    def list_discussions(self, project_id: Optional[str] = None) -> list[dict]:
        if project_id:
            rows = self.conn.execute("SELECT * FROM discussions WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM discussions ORDER BY created_at DESC").fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["messages"] = self.get_discussion_messages(d["discussion_id"])
            res.append(d)
        return res

    def save_discussion_message(
        self,
        message_id: str,
        discussion_id: str,
        sender_employee_id: str,
        content: str,
        recipient_employee_id: Optional[str] = None,
        task_id: Optional[str] = None,
        message_type: str = "QUESTION",
    ) -> None:
        now = _now()
        self.conn.execute("""
            INSERT OR REPLACE INTO discussion_messages (
                message_id, discussion_id, sender_employee_id, recipient_employee_id, task_id, message_type, content, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (message_id, discussion_id, sender_employee_id, recipient_employee_id, task_id, message_type, content, now))
        self.conn.commit()

    def get_discussion_messages(self, discussion_id: str) -> list[dict]:
        rows = self.conn.execute("""
            SELECT * FROM discussion_messages WHERE discussion_id = ? ORDER BY created_at ASC
        """, (discussion_id,)).fetchall()
        return [dict(r) for r in rows]

    # =========================================================================
    # Phase 6: Multi-Project Operations, Scheduling, Resources, Budget & Usage
    # =========================================================================

    # --- Phase 6 Projects ---

    def save_project(
        self,
        project_id: str,
        name: str,
        description: str = "",
        brief: str = "",
        status: str = "PLANNED",
        priority: str = "NORMAL",
        deadline: Optional[str] = None,
        owner_employee_id: Optional[str] = None,
        team_id: Optional[str] = None,
        budget: float = 0.0,
        spent: float = 0.0,
        output_dir: Optional[str] = None,
        metadata: Optional[dict] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        """Create or update a Project record with full Phase 6 fields without clearing existing project tasks."""
        now = _now()
        meta_str = json.dumps(metadata or {})
        self.conn.execute("""
            INSERT INTO projects (
                id, name, description, brief, status, priority, deadline,
                owner_employee_id, team_id, budget, spent, output_dir,
                metadata, created_at, updated_at, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                brief = CASE WHEN excluded.brief != '' THEN excluded.brief ELSE projects.brief END,
                status = excluded.status,
                priority = excluded.priority,
                deadline = excluded.deadline,
                owner_employee_id = excluded.owner_employee_id,
                team_id = excluded.team_id,
                budget = excluded.budget,
                spent = excluded.spent,
                output_dir = CASE WHEN excluded.output_dir IS NOT NULL THEN excluded.output_dir ELSE projects.output_dir END,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at,
                started_at = CASE WHEN excluded.started_at IS NOT NULL THEN excluded.started_at ELSE projects.started_at END,
                completed_at = CASE WHEN excluded.completed_at IS NOT NULL THEN excluded.completed_at ELSE projects.completed_at END;
        """, (
            project_id, name, description, brief, status, priority, deadline,
            owner_employee_id, team_id, budget, spent, output_dir,
            meta_str, now, now, started_at, completed_at
        ))
        self.conn.commit()

    def list_projects(self, status: Optional[str] = None) -> list[dict]:
        """List all projects, optionally filtered by status."""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if "metadata" in d and d["metadata"]:
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except Exception:
                    pass
            result.append(d)
        return result

    def update_project(self, project_id: str, **kwargs) -> None:
        """Update arbitrary project columns dynamically."""
        if not kwargs:
            return
        now = _now()
        kwargs["updated_at"] = now
        updates = []
        params = []
        for k, v in kwargs.items():
            updates.append(f"{k} = ?")
            if k == "metadata" and isinstance(v, dict):
                params.append(json.dumps(v))
            else:
                params.append(v)
        params.append(project_id)
        sql = f"UPDATE projects SET {', '.join(updates)} WHERE id = ?"
        self.conn.execute(sql, params)
        self.conn.commit()

    # --- Project Queue ---

    def save_project_queue_entry(
        self,
        project_id: str,
        priority_weight: float = 0.0,
        waiting_duration: int = 0,
        starvation_counter: int = 0,
        status: str = "WAITING",
    ) -> None:
        now = _now()
        self.conn.execute("""
            INSERT INTO project_queue (
                project_id, priority_weight, waiting_duration, starvation_counter, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                priority_weight = excluded.priority_weight,
                waiting_duration = excluded.waiting_duration,
                starvation_counter = excluded.starvation_counter,
                status = excluded.status,
                updated_at = excluded.updated_at;
        """, (project_id, priority_weight, waiting_duration, starvation_counter, status, now))
        self.conn.commit()

    def get_project_queue_entry(self, project_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM project_queue WHERE project_id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_project_queue_entries(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM project_queue ORDER BY priority_weight DESC, starvation_counter DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_project_queue_entry(self, project_id: str) -> None:
        self.conn.execute("DELETE FROM project_queue WHERE project_id = ?", (project_id,))
        self.conn.commit()

    # --- Employee Reservations (Atomic Resource Locks) ---

    def reserve_employee(
        self,
        employee_id: str,
        task_id: str,
        project_id: str,
        expires_at: Optional[str] = None,
        lease_seconds: float = 300.0,
    ) -> bool:
        """Atomically acquire an exclusive reservation lock on an employee.
        Supports lease TTL to prevent deadlocks from crashed workers.
        Returns True if reservation was successful, False if already reserved.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        if not expires_at and lease_seconds:
            expires_at = (now + timedelta(seconds=lease_seconds)).isoformat()

        try:
            # Check for stale expired lease and auto-evict if expired
            existing = self.conn.execute(
                "SELECT * FROM employee_reservations WHERE employee_id = ?", (employee_id,)
            ).fetchone()
            if existing and existing["expires_at"]:
                if existing["expires_at"] < now_iso:
                    self.conn.execute(
                        "DELETE FROM employee_reservations WHERE employee_id = ?", (employee_id,)
                    )

            self.conn.execute("""
                INSERT INTO employee_reservations (
                    employee_id, task_id, project_id, reserved_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (employee_id, task_id, project_id, now_iso, expires_at))
            # Also update employee record availability to busy
            self.conn.execute(
                "UPDATE employees SET availability = 'busy', live_state = 'WORKING', updated_at = ? WHERE id = ?",
                (now_iso, employee_id),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def release_employee(self, employee_id: str) -> bool:
        """Release reservation lock for an employee. Returns True if released."""
        now = _now()
        cur = self.conn.execute(
            "DELETE FROM employee_reservations WHERE employee_id = ?", (employee_id,)
        )
        released = cur.rowcount > 0
        if released:
            self.conn.execute(
                "UPDATE employees SET availability = 'available', live_state = 'IDLE', updated_at = ? WHERE id = ?",
                (now, employee_id),
            )
        self.conn.commit()
        return released

    def get_reservation(self, employee_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM employee_reservations WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        return dict(row) if row else None

    def is_employee_reserved(self, employee_id: str) -> bool:
        res = self.get_reservation(employee_id)
        if not res:
            return False
        exp = res.get("expires_at")
        if exp and exp < _now():
            return False
        return True

    def list_reservations(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM employee_reservations ORDER BY reserved_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stale_reservations(self, timeout_seconds: Optional[float] = None) -> list[dict]:
        """Find reservations whose lease has expired or exceeds timeout_seconds.
        If timeout_seconds <= 0, returns all reservations (for cold process restart recovery).
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        if timeout_seconds is not None:
            if timeout_seconds <= 0:
                rows = self.conn.execute("SELECT * FROM employee_reservations").fetchall()
            else:
                cutoff = (now - timedelta(seconds=timeout_seconds)).isoformat()
                rows = self.conn.execute(
                    "SELECT * FROM employee_reservations WHERE (expires_at IS NOT NULL AND expires_at < ?) OR reserved_at <= ?",
                    (now_iso, cutoff),
                ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM employee_reservations WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now_iso,),
            ).fetchall()
        return [dict(r) for r in rows]


    def clean_stale_reservations(self, timeout_seconds: Optional[float] = None) -> list[dict]:
        """Atomically clean up expired employee reservations and restore availability.
        Returns list of cleaned reservations.
        """
        now_iso = _now()
        stale = self.get_stale_reservations(timeout_seconds)
        if stale:
            for s in stale:
                emp_id = s["employee_id"]
                self.conn.execute("DELETE FROM employee_reservations WHERE employee_id = ?", (emp_id,))
                self.conn.execute(
                    "UPDATE employees SET availability = 'available', live_state = 'IDLE', updated_at = ? WHERE id = ?",
                    (now_iso, emp_id),
                )
            self.conn.commit()
        return stale


    # --- Usage Records & Tracking ---

    def save_usage_record(
        self,
        project_id: str,
        task_id: Optional[str] = None,
        employee_id: Optional[str] = None,
        model: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        requests: int = 1,
        estimated_cost: float = 0.0,
        organization_id: str = "aether_office",
    ) -> int:
        now = _now()
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens
        cur = self.conn.execute("""
            INSERT INTO usage_records (
                organization_id, project_id, task_id, employee_id, model,
                input_tokens, output_tokens, total_tokens, requests, estimated_cost, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            organization_id, project_id, task_id, employee_id, model,
            input_tokens, output_tokens, total_tokens, requests, estimated_cost, now
        ))
        record_id = cur.lastrowid
        # Update project spent and project_budgets spent
        if estimated_cost > 0.0:
            self.update_project_budget_spent(project_id, estimated_cost)
        self.conn.commit()
        return record_id

    def list_usage_records(
        self,
        project_id: Optional[str] = None,
        employee_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> list[dict]:
        query = "SELECT * FROM usage_records WHERE 1=1"
        params = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        query += " ORDER BY created_at ASC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_project_usage_summary(self, project_id: str) -> dict:
        row = self.conn.execute("""
            SELECT 
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(requests), 0) as total_requests,
                COALESCE(SUM(estimated_cost), 0.0) as total_cost
            FROM usage_records WHERE project_id = ?
        """, (project_id,)).fetchone()
        return dict(row) if row else {
            "total_input_tokens": 0, "total_output_tokens": 0,
            "total_tokens": 0, "total_requests": 0, "total_cost": 0.0
        }

    def get_office_usage_summary(self) -> dict:
        row = self.conn.execute("""
            SELECT 
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(requests), 0) as total_requests,
                COALESCE(SUM(estimated_cost), 0.0) as total_cost
            FROM usage_records
        """).fetchone()
        return dict(row) if row else {
            "total_input_tokens": 0, "total_output_tokens": 0,
            "total_tokens": 0, "total_requests": 0, "total_cost": 0.0
        }

    # --- Project Budgets ---

    def save_project_budget(
        self,
        project_id: str,
        budget: float,
        spent: float = 0.0,
        warning_threshold: float = 0.8,
        is_blocked: int = 0,
    ) -> None:
        now = _now()
        self.conn.execute("""
            INSERT INTO project_budgets (
                project_id, budget, spent, warning_threshold, is_blocked, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                budget = excluded.budget,
                spent = excluded.spent,
                warning_threshold = excluded.warning_threshold,
                is_blocked = excluded.is_blocked,
                updated_at = excluded.updated_at;
        """, (project_id, budget, spent, warning_threshold, is_blocked, now))
        # Keep projects table budget/spent in sync
        self.conn.execute("""
            UPDATE projects SET budget = ?, spent = ?, updated_at = ? WHERE id = ?
        """, (budget, spent, now, project_id))
        self.conn.commit()

    def get_project_budget(self, project_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM project_budgets WHERE project_id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_project_budget_spent(self, project_id: str, delta_spent: float) -> dict:
        now = _now()
        cur_budget = self.get_project_budget(project_id)
        if not cur_budget:
            # Check if project has a budget set in projects table
            proj = self.get_project(project_id)
            init_budget = float(proj.get("budget", 0.0)) if proj and proj.get("budget") else 0.0
            init_spent = float(proj.get("spent", 0.0)) if proj and proj.get("spent") else 0.0
            self.save_project_budget(project_id, budget=init_budget, spent=init_spent)

        # Atomic SQL calculation: spent = spent + delta_spent
        self.conn.execute("""
            UPDATE project_budgets
            SET spent = spent + ?,
                is_blocked = CASE
                    WHEN budget > 0.0 AND (spent + ?) >= budget THEN 1
                    ELSE is_blocked
                END,
                updated_at = ?
            WHERE project_id = ?
        """, (delta_spent, delta_spent, now, project_id))

        self.conn.execute("""
            UPDATE projects
            SET spent = (SELECT spent FROM project_budgets WHERE project_id = ?),
                updated_at = ?
            WHERE id = ?
        """, (project_id, now, project_id))
        self.conn.commit()

        updated = self.get_project_budget(project_id)
        return dict(updated) if updated else {"spent": 0.0, "budget": 0.0, "is_blocked": 0}

    # --- Scheduler Runs ---

    def save_scheduler_run(
        self,
        run_id: str,
        tick_number: int,
        tasks_evaluated: int,
        tasks_scheduled: int,
        conflicts_detected: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        now = _now()
        self.conn.execute("""
            INSERT OR REPLACE INTO scheduler_runs (
                run_id, tick_number, tasks_evaluated, tasks_scheduled,
                conflicts_detected, duration_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (run_id, tick_number, tasks_evaluated, tasks_scheduled, conflicts_detected, duration_ms, now))
        self.conn.commit()

    def list_scheduler_runs(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute("""
            SELECT * FROM scheduler_runs ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    # --- Distributed / Process Scheduler Locks ---

    def acquire_scheduler_lock(
        self, lock_name: str = "office_scheduler", locked_by: str = "scheduler", ttl_seconds: float = 30.0
    ) -> bool:
        """Acquire an atomic scheduler lock with TTL.
        Returns True if acquired, False if already held by another active runner.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        try:
            row = self.conn.execute(
                "SELECT * FROM scheduler_locks WHERE lock_name = ?", (lock_name,)
            ).fetchone()
            if row:
                if row["expires_at"] < now_iso:
                    # Previous lock expired/crashed, overwrite atomically
                    self.conn.execute("""
                        UPDATE scheduler_locks
                        SET locked_by = ?, acquired_at = ?, expires_at = ?
                        WHERE lock_name = ?
                    """, (locked_by, now_iso, expires_at, lock_name))
                    self.conn.commit()
                    return True
                else:
                    return False
            else:
                self.conn.execute("""
                    INSERT INTO scheduler_locks (lock_name, locked_by, acquired_at, expires_at)
                    VALUES (?, ?, ?, ?)
                """, (lock_name, locked_by, now_iso, expires_at))
                self.conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def release_scheduler_lock(
        self, lock_name: str = "office_scheduler", locked_by: Optional[str] = None
    ) -> bool:
        """Release scheduler lock."""
        if locked_by:
            cur = self.conn.execute(
                "DELETE FROM scheduler_locks WHERE lock_name = ? AND locked_by = ?",
                (lock_name, locked_by),
            )
        else:
            cur = self.conn.execute(
                "DELETE FROM scheduler_locks WHERE lock_name = ?", (lock_name,)
            )
        self.conn.commit()
        return cur.rowcount > 0

    # --- Phase 8: Objective-to-Outcome Engine Persistence ---

    def save_objective(
        self,
        objective_id: str,
        title: str,
        description: str = "",
        status: str = "CREATED",
        priority: str = "NORMAL",
        deadline: Optional[str] = None,
        budget: float = 0.0,
        acceptance_criteria: Optional[list] = None,
        project_id: Optional[str] = None,
        execution_plan_id: Optional[str] = None,
        revision_count: int = 0,
        max_revisions: int = 3,
        result: Optional[dict] = None,
        failure_reason: Optional[str] = None,
        metadata: Optional[dict] = None,
        created_at: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        """Insert or update an Objective record."""
        now = _now()
        criteria_json = json.dumps(acceptance_criteria if acceptance_criteria is not None else [])
        result_json = json.dumps(result if result is not None else {})
        meta_json = json.dumps(metadata if metadata is not None else {})
        c_at = created_at or now

        self.conn.execute("""
            INSERT INTO objectives (
                id, title, description, status, priority, deadline, budget,
                acceptance_criteria, project_id, execution_plan_id, revision_count,
                max_revisions, result, failure_reason, metadata, created_at, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                status = excluded.status,
                priority = excluded.priority,
                deadline = excluded.deadline,
                budget = excluded.budget,
                acceptance_criteria = excluded.acceptance_criteria,
                project_id = excluded.project_id,
                execution_plan_id = excluded.execution_plan_id,
                revision_count = excluded.revision_count,
                max_revisions = excluded.max_revisions,
                result = excluded.result,
                failure_reason = excluded.failure_reason,
                metadata = excluded.metadata,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at
        """, (
            objective_id, title, description, status, priority, deadline, budget,
            criteria_json, project_id, execution_plan_id, revision_count,
            max_revisions, result_json, failure_reason, meta_json, c_at, started_at, completed_at
        ))
        self.conn.commit()

    def get_objective(self, objective_id: str) -> Optional[dict]:
        """Fetch an Objective by ID."""
        row = self.conn.execute("SELECT * FROM objectives WHERE id = ?", (objective_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["acceptance_criteria"] = json.loads(d.get("acceptance_criteria") or "[]")
        d["result"] = json.loads(d.get("result") or "{}")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    def list_objectives(self, status: Optional[str] = None) -> list[dict]:
        """List all Objectives, optionally filtered by status."""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM objectives WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM objectives ORDER BY created_at DESC"
            ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["acceptance_criteria"] = json.loads(d.get("acceptance_criteria") or "[]")
            d["result"] = json.loads(d.get("result") or "{}")
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            results.append(d)
        return results

    def update_objective_status(
        self,
        objective_id: str,
        status: str,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        failure_reason: Optional[str] = None,
        result: Optional[dict] = None,
        revision_count: Optional[int] = None,
    ) -> bool:
        """Update Objective status and related fields."""
        fields = ["status = ?"]
        params = [status]

        if started_at is not None:
            fields.append("started_at = ?")
            params.append(started_at)
        if completed_at is not None:
            fields.append("completed_at = ?")
            params.append(completed_at)
        if failure_reason is not None:
            fields.append("failure_reason = ?")
            params.append(failure_reason)
        if result is not None:
            fields.append("result = ?")
            params.append(json.dumps(result))
        if revision_count is not None:
            fields.append("revision_count = ?")
            params.append(revision_count)

        params.append(objective_id)
        cur = self.conn.execute(
            f"UPDATE objectives SET {', '.join(fields)} WHERE id = ?", params
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_objective(self, objective_id: str) -> bool:
        """Delete an Objective and its related plans/evaluations."""
        self.conn.execute("DELETE FROM objective_evaluations WHERE objective_id = ?", (objective_id,))
        self.conn.execute("DELETE FROM execution_plans WHERE objective_id = ?", (objective_id,))
        cur = self.conn.execute("DELETE FROM objectives WHERE id = ?", (objective_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def save_execution_plan(
        self,
        plan_id: str,
        objective_id: str,
        milestones: Optional[list] = None,
        tasks: Optional[list] = None,
        dependencies: Optional[dict] = None,
        estimated_cost: float = 0.0,
        required_skills: Optional[list] = None,
        is_valid: bool = True,
        validation_error: Optional[str] = None,
        metadata: Optional[dict] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Insert or update an ExecutionPlan record."""
        now = _now()
        m_json = json.dumps(milestones if milestones is not None else [])
        t_json = json.dumps(tasks if tasks is not None else [])
        d_json = json.dumps(dependencies if dependencies is not None else {})
        s_json = json.dumps(required_skills if required_skills is not None else [])
        meta_json = json.dumps(metadata if metadata is not None else {})
        c_at = created_at or now

        self.conn.execute("""
            INSERT INTO execution_plans (
                id, objective_id, milestones, tasks, dependencies, estimated_cost,
                required_skills, is_valid, validation_error, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                milestones = excluded.milestones,
                tasks = excluded.tasks,
                dependencies = excluded.dependencies,
                estimated_cost = excluded.estimated_cost,
                required_skills = excluded.required_skills,
                is_valid = excluded.is_valid,
                validation_error = excluded.validation_error,
                metadata = excluded.metadata
        """, (
            plan_id, objective_id, m_json, t_json, d_json, estimated_cost,
            s_json, 1 if is_valid else 0, validation_error, meta_json, c_at
        ))
        self.conn.commit()

    def get_execution_plan(self, plan_id: str) -> Optional[dict]:
        """Fetch ExecutionPlan by plan ID."""
        row = self.conn.execute("SELECT * FROM execution_plans WHERE id = ?", (plan_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["milestones"] = json.loads(d.get("milestones") or "[]")
        d["tasks"] = json.loads(d.get("tasks") or "[]")
        d["dependencies"] = json.loads(d.get("dependencies") or "{}")
        d["required_skills"] = json.loads(d.get("required_skills") or "[]")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        d["is_valid"] = bool(d.get("is_valid", 1))
        return d

    def get_execution_plan_by_objective(self, objective_id: str) -> Optional[dict]:
        """Fetch ExecutionPlan by objective ID."""
        row = self.conn.execute(
            "SELECT * FROM execution_plans WHERE objective_id = ? ORDER BY created_at DESC LIMIT 1",
            (objective_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["milestones"] = json.loads(d.get("milestones") or "[]")
        d["tasks"] = json.loads(d.get("tasks") or "[]")
        d["dependencies"] = json.loads(d.get("dependencies") or "{}")
        d["required_skills"] = json.loads(d.get("required_skills") or "[]")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        d["is_valid"] = bool(d.get("is_valid", 1))
        return d

    def save_objective_evaluation(
        self,
        evaluation_id: str,
        objective_id: str,
        verdict: str,
        criteria_results: Optional[list] = None,
        feedback: str = "",
        revision_requested: bool = False,
        metadata: Optional[dict] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Insert an ObjectiveEvaluation record."""
        now = _now()
        cr_json = json.dumps(criteria_results if criteria_results is not None else [])
        meta_json = json.dumps(metadata if metadata is not None else {})
        c_at = created_at or now

        self.conn.execute("""
            INSERT INTO objective_evaluations (
                id, objective_id, verdict, criteria_results, feedback,
                revision_requested, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            evaluation_id, objective_id, verdict, cr_json, feedback,
            1 if revision_requested else 0, meta_json, c_at
        ))
        self.conn.commit()

    def list_objective_evaluations(self, objective_id: str) -> list[dict]:
        """List all evaluations for an objective."""
        rows = self.conn.execute(
            "SELECT * FROM objective_evaluations WHERE objective_id = ? ORDER BY created_at ASC",
            (objective_id,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["criteria_results"] = json.loads(d.get("criteria_results") or "[]")
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            d["revision_requested"] = bool(d.get("revision_requested", 0))
            results.append(d)
        return results

    # --- Phase 9: Adaptive Planning & Intelligence Methods ---

    def save_objective_analysis(
        self,
        analysis_id: Any,
        objective_id: Optional[str] = None,
        objective_type: Optional[str] = None,
        complexity: Optional[str] = None,
        ambiguity_score: float = 0.0,
        needs_clarification: bool = False,
        clarifications: Optional[list] = None,
        required_capabilities: Optional[list] = None,
        estimated_deliverables: Optional[list] = None,
        estimated_duration: float = 0.0,
        estimated_cost: float = 0.0,
        risks: Optional[list] = None,
        confidence: float = 1.0,
        metadata: Optional[dict] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Insert or replace an ObjectiveAnalysis record."""
        now = _now()
        if isinstance(analysis_id, dict):
            d = analysis_id
            analysis_id = d.get("analysis_id") or f"oa_{d.get('objective_id', 'unknown')}_{int(time.time())}"
            objective_id = d.get("objective_id", "")
            objective_type = d.get("objective_type", "GENERAL")
            complexity = d.get("complexity", "STANDARD")
            ambiguity_score = float(d.get("ambiguity_score", 0.0) or 0.0)
            needs_clarification = bool(d.get("needs_clarification", False))
            clarifications = d.get("clarifications")
            required_capabilities = d.get("required_capabilities")
            estimated_deliverables = d.get("estimated_deliverables")
            estimated_duration = float(d.get("estimated_duration", 0.0) or 0.0)
            estimated_cost = float(d.get("estimated_cost", 0.0) or 0.0)
            risks = d.get("risks")
            confidence = float(d.get("confidence", 1.0) or 1.0)
            metadata = d.get("metadata")
            created_at = d.get("created_at")

        clar_json = json.dumps(clarifications if clarifications is not None else [])
        caps_json = json.dumps(required_capabilities if required_capabilities is not None else [])
        deliv_json = json.dumps(estimated_deliverables if estimated_deliverables is not None else [])
        risks_json = json.dumps(risks if risks is not None else [])
        meta_json = json.dumps(metadata if metadata is not None else {})
        c_at = created_at or now

        self.conn.execute("""
            INSERT OR REPLACE INTO objective_analyses (
                id, objective_id, objective_type, complexity, ambiguity_score,
                needs_clarification, clarifications, required_capabilities,
                estimated_deliverables, estimated_duration, estimated_cost,
                risks, confidence, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            analysis_id, objective_id, objective_type, complexity, ambiguity_score,
            1 if needs_clarification else 0, clar_json, caps_json, deliv_json,
            estimated_duration, estimated_cost, risks_json, confidence, meta_json, c_at
        ))
        self.conn.commit()

    def get_objective_analysis(self, objective_id: str) -> Optional[dict]:
        """Fetch latest ObjectiveAnalysis by objective ID."""
        row = self.conn.execute(
            "SELECT * FROM objective_analyses WHERE objective_id = ? ORDER BY created_at DESC LIMIT 1",
            (objective_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["clarifications"] = json.loads(d.get("clarifications") or "[]")
        d["required_capabilities"] = json.loads(d.get("required_capabilities") or "[]")
        d["estimated_deliverables"] = json.loads(d.get("estimated_deliverables") or "[]")
        d["risks"] = json.loads(d.get("risks") or "[]")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        d["needs_clarification"] = bool(d.get("needs_clarification", 0))
        return d

    def save_plan_quality_report(
        self,
        report_id: str,
        plan_id: str,
        objective_id: str,
        score: float,
        completeness_score: float = 0.0,
        dependency_score: float = 0.0,
        capability_score: float = 0.0,
        budget_score: float = 0.0,
        criteria_coverage_score: float = 0.0,
        issues: Optional[list] = None,
        warnings: Optional[list] = None,
        recommendations: Optional[list] = None,
        metadata: Optional[dict] = None,
        created_at: Optional[str] = None,
        grade: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Insert or replace a PlanQualityReport record."""
        now = _now()
        iss_json = json.dumps(issues if issues is not None else [])
        warn_json = json.dumps(warnings if warnings is not None else [])
        rec_json = json.dumps(recommendations if recommendations is not None else [])
        meta_json = json.dumps(metadata if metadata is not None else {})
        c_at = created_at or now

        self.conn.execute("""
            INSERT OR REPLACE INTO plan_quality_reports (
                id, plan_id, objective_id, score, completeness_score,
                dependency_score, capability_score, budget_score,
                criteria_coverage_score, issues, warnings, recommendations,
                metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id, plan_id, objective_id, score, completeness_score,
            dependency_score, capability_score, budget_score, criteria_coverage_score,
            iss_json, warn_json, rec_json, meta_json, c_at
        ))
        self.conn.commit()

    def get_plan_quality_report(self, plan_id: str) -> Optional[dict]:
        """Fetch PlanQualityReport by plan ID."""
        row = self.conn.execute(
            "SELECT * FROM plan_quality_reports WHERE plan_id = ? ORDER BY created_at DESC LIMIT 1",
            (plan_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["issues"] = json.loads(d.get("issues") or "[]")
        d["warnings"] = json.loads(d.get("warnings") or "[]")
        d["recommendations"] = json.loads(d.get("recommendations") or "[]")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d





"""Phase 4 Test Suite — AI Office Organization & Workforce."""

from __future__ import annotations
import unittest
import json
from unittest.mock import MagicMock

from workforce import (
    Role,
    RoleCatalog,
    get_seed_roles,
    Department,
    DepartmentRegistry,
    Employee,
    AgentManifest,
    EmployeeRegistry,
    Organization,
    create_default_organization,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    AVAILABILITY_AVAILABLE,
    AVAILABILITY_BUSY,
    AVAILABILITY_OFFLINE,
    STATE_IDLE,
    STATE_WORKING,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_BLOCKED,
)
from prompt_builder import PromptBuilder
from model_resolver import resolve_model_config
from agents.base import Agent
from agents.pm import PMAgent
from agents.conceptor import ConceptorAgent
from agents.planner import Planner as PlannerAgent
from agents.developer import DeveloperAgent
from agents.qa import QAAgent
from agents.generic import GenericAgent
from factory import AgentFactory
from matcher import TaskMatcher
from events import (
    Event,
    EventBus,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_DEACTIVATED,
    EVENT_ROLE_REGISTERED,
    EVENT_DEPARTMENT_REGISTERED,
    EVENT_AGENT_STATE_CHANGED,
)
from db import Database
from llm import LLMClient, LLMError


# =====================================================================
# 1. Employee Schema & Identity Tests
# =====================================================================

class TestEmployeeSchema(unittest.TestCase):
    def test_employee_creation_and_defaults(self):
        emp = Employee(
            employee_id="dev_001",
            name="Bagas Aditya",
            role="backend_developer",
            department="engineering",
            capabilities=["python", "sqlite", "api"],
        )
        self.assertEqual(emp.employee_id, "dev_001")
        self.assertEqual(emp.id, "dev_001")  # backward-compatibility property
        self.assertEqual(emp.name, "Bagas Aditya")
        self.assertEqual(emp.role, "backend_developer")
        self.assertEqual(emp.department, "engineering")
        self.assertEqual(emp.status, STATUS_ACTIVE)
        self.assertEqual(emp.availability, AVAILABILITY_AVAILABLE)
        self.assertEqual(emp.live_state, STATE_IDLE)
        self.assertTrue(emp.is_active)
        self.assertIn("python", emp.capabilities)

    def test_employee_dict_serialization_deserialization(self):
        emp = Employee(
            employee_id="copy_001",
            name="Laras Wulandari",
            role="copywriter",
            department="marketing",
            capabilities=["copywriting", "seo"],
            personality={"traits": ["kreatif", "lugasi"], "communication_style": "ekspresif"},
            model={"provider": "openai-compatible", "model": "claude-3-5-sonnet"},
        )
        d = emp.to_dict()
        self.assertEqual(d["employee_id"], "copy_001")
        self.assertEqual(d["id"], "copy_001")
        self.assertEqual(d["name"], "Laras Wulandari")
        self.assertEqual(d["model"]["model"], "claude-3-5-sonnet")

        reconstructed = Employee.from_dict(d)
        self.assertEqual(reconstructed.employee_id, "copy_001")
        self.assertEqual(reconstructed.role, "copywriter")
        self.assertEqual(reconstructed.personality["communication_style"], "ekspresif")
        self.assertEqual(reconstructed.capabilities, ["copywriting", "seo"])


    def test_agent_manifest_backward_compatibility(self):
        manifest = AgentManifest(
            id="agent_99",
            name="Legacy Agent",
            role="developer",
            capabilities=["python"],
            model="gpt-4o",
            status=STATE_IDLE,
        )
        self.assertEqual(manifest.id, "agent_99")
        self.assertEqual(manifest.employee_id, "agent_99")
        self.assertEqual(manifest.status, STATE_IDLE)

        d = manifest.to_dict()
        self.assertEqual(d["id"], "agent_99")
        self.assertEqual(d["model"], "gpt-4o")

        from_d = AgentManifest.from_dict(d)
        self.assertEqual(from_d.id, "agent_99")
        self.assertEqual(from_d.name, "Legacy Agent")


# =====================================================================
# 2. Role & Role Catalog Tests
# =====================================================================

class TestRoleCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = RoleCatalog()

    def test_register_and_get_role(self):
        role = Role(
            role_id="devops_engineer",
            name="DevOps Engineer",
            department="engineering",
            description="Manages deployment and cloud infrastructure",
            capabilities=["docker", "ci_cd", "kubernetes"],
        )
        self.catalog.register(role)

        found = self.catalog.get("devops_engineer")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "DevOps Engineer")
        self.assertEqual(found.department, "engineering")
        self.assertIn("docker", found.capabilities)

    def test_seed_roles_population(self):
        seed = get_seed_roles()
        self.assertTrue(len(seed) >= 30, f"Expected at least 30 seed roles, got {len(seed)}")

        # Verify representation across all 8 requested domains
        depts = {r.department for r in seed}
        expected_depts = {
            "product",
            "engineering",
            "design",
            "marketing",
            "research",
            "operations",
            "business",
            "support",
        }
        self.assertTrue(expected_depts.issubset(depts), f"Missing departments in seed: {expected_depts - depts}")

    def test_find_by_department(self):
        for r in get_seed_roles():
            self.catalog.register(r)

        eng_roles = self.catalog.find_by_department("engineering")
        self.assertTrue(len(eng_roles) >= 8)
        eng_ids = {r.role_id for r in eng_roles}
        self.assertIn("backend_developer", eng_ids)
        self.assertIn("qa_engineer", eng_ids)
        self.assertIn("software_architect", eng_ids)


# =====================================================================
# 3. Department Registry Tests
# =====================================================================

class TestDepartmentRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = DepartmentRegistry()

    def test_register_and_get_department(self):
        dept = Department(name="Design", description="Visual design and UI/UX", department_id="design")
        self.registry.register(dept)

        found = self.registry.get("design")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Design")
        self.assertEqual(found.description, "Visual design and UI/UX")

    def test_dict_like_access_and_containment(self):
        dept = Department(name="marketing", description="Growth and brand")
        self.registry.register(dept)

        self.assertIn("marketing", self.registry)
        self.assertEqual(self.registry["marketing"].name, "marketing")
        self.assertEqual(len(self.registry), 1)


# =====================================================================
# 4. Employee Registry Tests
# =====================================================================

class TestEmployeeRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = EmployeeRegistry()

    def test_register_and_get_employee(self):
        emp = Employee(employee_id="emp_01", name="Andi Wijaya", role="backend_developer", department="engineering")
        self.registry.register(emp)

        found = self.registry.get("emp_01")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Andi Wijaya")

    def test_duplicate_employee_id_rejected(self):
        e1 = Employee(employee_id="emp_01", name="Andi Wijaya", role="developer")
        e2 = Employee(employee_id="emp_01", name="Bambang", role="qa")
        self.registry.register(e1)

        with self.assertRaises(ValueError):
            self.registry.register(e2)


    def test_lookups_by_role_dept_and_capability(self):
        e1 = Employee(employee_id="e1", name="E1", role="developer", department="engineering", capabilities=["python", "fastapi"])
        e2 = Employee(employee_id="e2", name="E2", role="developer", department="engineering", capabilities=["javascript", "react"])
        e3 = Employee(employee_id="e3", name="E3", role="copywriter", department="marketing", capabilities=["copywriting", "python"])
        self.registry.register(e1)
        self.registry.register(e2)
        self.registry.register(e3)

        # by role
        devs = self.registry.find_by_role("developer")
        self.assertEqual(len(devs), 2)

        # by department
        mkt = self.registry.find_by_department("marketing")
        self.assertEqual(len(mkt), 1)
        self.assertEqual(mkt[0].employee_id, "e3")

        # by capability
        python_users = self.registry.find_by_capability("python")
        self.assertEqual(len(python_users), 2)
        py_ids = {u.employee_id for u in python_users}
        self.assertEqual(py_ids, {"e1", "e3"})

    def test_update_status(self):
        emp = Employee(employee_id="e1", name="E1", role="developer")
        self.registry.register(emp)

        self.assertTrue(self.registry.update_status("e1", STATE_WORKING))
        self.assertEqual(self.registry.get("e1").live_state, STATE_WORKING)
        self.assertEqual(self.registry.get("e1").availability, AVAILABILITY_BUSY)

        self.registry.update_status("e1", STATE_COMPLETED)
        self.assertEqual(self.registry.get("e1").availability, AVAILABILITY_AVAILABLE)


# =====================================================================
# 5. Modular Prompt Composition Tests
# =====================================================================

class TestPromptBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = PromptBuilder()

    def test_prompt_composition_all_sections(self):
        emp = Employee(
            employee_id="dev_002",
            name="Bagas Aditya",
            role="backend_developer",
            department="engineering",
            capabilities=["python", "sqlite", "fastapi"],
            personality={
                "traits": ["analytical", "systematic", "detail_oriented"],
                "communication_style": "concise",
                "decision_style": "evidence_based",
            },
        )
        role = Role(
            role_id="backend_developer",
            name="Backend Developer",
            department="engineering",
            description="Constructs resilient API microservices and database engines",
            capabilities=["python", "database"],
        )

        prompt = self.builder.build(
            employee=emp,
            role=role,
            task={"title": "Build Auth API", "description": "Create JWT auth endpoint with SQLite", "required_capabilities": ["python", "fastapi"]},
            context="User needs user registration with password hashing.",
            policies=["All functions must have type annotations."],
        )

        # Verify all sections are present
        self.assertIn("=== BASE INSTRUCTIONS ===", prompt)
        self.assertIn("=== ROLE & IDENTITY ===", prompt)
        self.assertIn("Bagas Aditya", prompt)

        self.assertIn("Backend Developer", prompt)
        self.assertIn("=== CAPABILITIES & DOMAIN SKILLS ===", prompt)
        self.assertIn("python, sqlite, fastapi", prompt)
        self.assertIn("=== PERSONALITY & STYLE ===", prompt)
        self.assertIn("analytical, systematic, detail_oriented", prompt)
        self.assertIn("concise", prompt)
        self.assertIn("=== TASK CONTEXT ===", prompt)
        self.assertIn("Build Auth API", prompt)
        self.assertIn("Create JWT auth endpoint with SQLite", prompt)
        self.assertIn("=== ORGANIZATION POLICIES & STANDARDS ===", prompt)
        self.assertIn("All functions must have type annotations.", prompt)


# =====================================================================
# 6. Model Inheritance Hierarchy Tests
# =====================================================================

class TestModelResolver(unittest.TestCase):
    def test_model_inheritance_hierarchy(self):
        # Global config
        global_cfg = {"llm": {"provider": "openai-compatible", "model": "default-global-model", "temperature": 0.7}}

        # Org default overrides model
        org = Organization(name="Aether Office")
        org.default_model = {"model": "org-model", "temperature": 0.6}

        # Dept default overrides temperature
        dept = Department(name="engineering", default_model={"temperature": 0.2})

        # Role default has max_tokens
        role = Role(role_id="dev", name="Dev", department="engineering", default_model={"max_tokens": 2048})

        # Employee specifies exact model
        emp = Employee(employee_id="dev_01", name="Dev", role="dev", model={"model": "gpt-4o-custom"})

        resolved = resolve_model_config(
            employee=emp,
            role=role,
            department=dept,
            organization=org,
            global_config=global_cfg,
        )

        # Employee model wins
        self.assertEqual(resolved["model"], "gpt-4o-custom")
        # Dept temperature wins over org and global
        self.assertEqual(resolved["temperature"], 0.2)
        # Role max_tokens inherited
        self.assertEqual(resolved["max_tokens"], 2048)
        # Provider inherited from global
        self.assertEqual(resolved["provider"], "openai-compatible")

    def test_router_role_model_mapping(self):
        global_cfg = {
            "llm": {
                "endpoint": "http://router:20128/v1",
                "api_key": "sk-router",
                "model": "gratisan",
                "models": {
                    "developer": "qwen2.5-coder",
                    "qa": "mistral-small",
                }
            }
        }
        role_dev = Role(role_id="developer", name="Dev", department="engineering")
        resolved = resolve_model_config(role=role_dev, global_config=global_cfg)
        self.assertEqual(resolved["model"], "qwen2.5-coder")
        self.assertEqual(resolved["endpoint"], "http://router:20128/v1")


# =====================================================================
# 7. Agent Factory & Generic Agent Tests
# =====================================================================

class TestAgentFactory(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.db = Database(":memory:", event_bus=self.bus)
        self.llm = MagicMock(spec=LLMClient)
        self.org, _ = create_default_organization()
        self.factory = AgentFactory(organization=self.org)

    def test_specialized_agent_mappings(self):
        pm_emp = self.org.get_employee("pm_001")
        dev_emp = self.org.get_employee("developer_001")
        qa_emp = self.org.get_employee("qa_001")

        pm_agent = self.factory.create_agent(pm_emp, self.llm, self.db, "p1", "/tmp")
        dev_agent = self.factory.create_agent(dev_emp, self.llm, self.db, "p1", "/tmp", config={})
        qa_agent = self.factory.create_agent(qa_emp, self.llm, self.db, "p1", "/tmp")

        self.assertIsInstance(pm_agent, PMAgent)
        self.assertIsInstance(dev_agent, DeveloperAgent)
        self.assertIsInstance(qa_agent, QAAgent)

    def test_generic_agent_fallback_for_custom_roles(self):
        designer_emp = self.org.hire(
            name="Dewi Anjani",
            role="ui_designer",
            capabilities=["ui_design", "css", "layout"],
        )

        agent = self.factory.create_agent(designer_emp, self.llm, self.db, "p1", "/tmp")
        self.assertIsInstance(agent, GenericAgent)
        self.assertEqual(agent.role, "ui_designer")
        self.assertEqual(agent.agent_id, designer_emp.employee_id)

    def test_generic_agent_execution_with_mock_llm(self):
        self.llm.chat.return_value = "UI Design Specification:\n1. Header with logo\n2. Responsive grid"

        copywriter = self.org.hire(name="Laras Wulandari", role="copywriter", capabilities=["copywriting"])
        agent = self.factory.create_agent(copywriter, self.llm, self.db, "p1", "/tmp")

        result = agent.run(context="Write landing page outline", task={"title": "Landing Page"})
        self.assertTrue(result.success)
        self.assertIn("UI Design Specification", result.output)
        self.assertEqual(agent.state, STATE_COMPLETED)


# =====================================================================
# 8. Hiring & Deactivation Lifecycle Tests
# =====================================================================

class TestHiringAndDeactivation(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.org = Organization(name="Aether Office", event_bus=self.bus)
        self.events_received: list[Event] = []
        self.bus.subscribe(self.events_received.append)

    def test_hire_and_auto_id_assignment(self):
        emp1 = self.org.hire(name="Bagas Aditya", role="backend_developer")
        emp2 = self.org.hire(name="Bayu Setiawan", role="backend_developer")

        self.assertEqual(emp1.employee_id, "backend_developer_001")
        self.assertEqual(emp2.employee_id, "backend_developer_002")
        self.assertEqual(emp1.status, STATUS_ACTIVE)
        self.assertEqual(emp1.availability, AVAILABILITY_AVAILABLE)

        # Verify hire event emitted
        hire_events = [e for e in self.events_received if e.event_type == EVENT_EMPLOYEE_HIRED]
        self.assertEqual(len(hire_events), 2)
        self.assertEqual(hire_events[0].agent_id, "backend_developer_001")

    def test_fire_employee_lifecycle(self):
        emp = self.org.hire(name="Cahyo Utomo", role="qa_engineer")
        emp_id = emp.employee_id

        self.assertTrue(self.org.fire(emp_id))

        updated = self.org.get_employee(emp_id)
        self.assertEqual(updated.status, STATUS_INACTIVE)
        self.assertEqual(updated.availability, AVAILABILITY_OFFLINE)

        # Verify deactivation event
        deact_events = [e for e in self.events_received if e.event_type == EVENT_EMPLOYEE_DEACTIVATED]
        self.assertEqual(len(deact_events), 1)
        self.assertEqual(deact_events[0].agent_id, emp_id)


# =====================================================================
# 9. Deterministic Task Matcher Tests
# =====================================================================

class TestTaskMatcher(unittest.TestCase):
    def setUp(self):
        self.c1 = Employee(employee_id="c1", name="Bagas Aditya", role="backend_developer", department="engineering", capabilities=["python", "sqlite", "api"])
        self.c2 = Employee(employee_id="c2", name="Bella Safitri", role="backend_developer", department="engineering", capabilities=["python", "fastapi", "docker"])
        self.c3 = Employee(employee_id="c3", name="Citra Dewi", role="frontend_developer", department="engineering", capabilities=["react", "javascript"])
        self.c4 = Employee(employee_id="c4", name="Diana Putri", role="backend_developer", department="engineering", capabilities=["python", "sqlite"], status=STATUS_INACTIVE)
        self.c5 = Employee(employee_id="c5", name="Evan Santoso", role="backend_developer", department="engineering", capabilities=["python", "sqlite"], availability=AVAILABILITY_BUSY)

        self.candidates = [self.c1, self.c2, self.c3, self.c4, self.c5]

    def test_inactive_and_busy_candidates_disqualified(self):
        task = {"role": "backend_developer", "required_capabilities": ["python"]}
        self.assertEqual(TaskMatcher.score_candidate(self.c4, task), -1)
        self.assertEqual(TaskMatcher.score_candidate(self.c5, task), -1)

    def test_role_and_capability_scoring(self):
        # Task requires role=backend_developer (+20) and capabilities: python (+10), sqlite (+10)
        # Total for c1: 20 (role) + 5 (dept) + 20 (caps) = 45
        # Total for c2: 20 (role) + 5 (dept) + 10 (caps: python only) = 35
        # Total for c3: 0 (role) + 5 (dept) + 0 (caps) = 5
        task = {
            "role": "backend_developer",
            "department": "engineering",
            "required_capabilities": ["python", "sqlite"],
        }
        score_c1 = TaskMatcher.score_candidate(self.c1, task)
        score_c2 = TaskMatcher.score_candidate(self.c2, task)
        score_c3 = TaskMatcher.score_candidate(self.c3, task)

        self.assertEqual(score_c1, 45)
        self.assertEqual(score_c2, 35)
        self.assertEqual(score_c3, 5)

        best = TaskMatcher.find_best_employee(task, self.candidates)
        self.assertIsNotNone(best)
        self.assertEqual(best.employee_id, "c1")


# =====================================================================
# 10. Organization State & Analytics Tests
# =====================================================================

class TestOrganizationStateAndAnalytics(unittest.TestCase):
    def test_employee_counts_and_department_stats(self):
        org, _ = create_default_organization()

        # By default, 5 core employees
        self.assertEqual(org.get_employee_count(), 5)
        self.assertEqual(len(org.get_active_employees()), 5)

        # Hire 2 marketing employees
        org.hire(name="Laras Wulandari", role="copywriter", department="marketing")
        org.hire(name="Surya Pratama", role="seo_specialist", department="marketing")

        self.assertEqual(org.get_employee_count(), 7)

        stats = org.get_department_stats()
        self.assertIn("engineering", stats)
        self.assertIn("product", stats)
        self.assertIn("marketing", stats)
        self.assertEqual(stats["engineering"]["total_active"], 3)
        self.assertEqual(stats["marketing"]["total_active"], 2)


# =====================================================================
# 11. Database Workforce Persistence Tests
# =====================================================================

class TestDatabaseWorkforcePersistence(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_department_and_role_persistence(self):
        self.db.save_department(dept_id="design", name="Design", description="UI & UX")
        depts = self.db.get_departments()
        self.assertEqual(len(depts), 1)
        self.assertEqual(depts[0]["id"], "design")

        self.db.save_role(
            role_id="ui_designer",
            name="UI Designer",
            department_id="design",
            description="Creates user interfaces",
            capabilities=["ui_design", "css"],
        )
        role = self.db.get_role("ui_designer")
        self.assertIsNotNone(role)
        self.assertEqual(role["name"], "UI Designer")
        self.assertIn("ui_design", role["capabilities"])

    def test_employee_persistence_and_status_update(self):
        self.db.save_employee(
            employee_id="dev_007",
            name="Joko Susilo",
            role_id="backend_developer",
            department_id="engineering",
            capabilities=["python", "security"],
            status="active",
            availability="available",
        )

        emp = self.db.get_employee("dev_007")
        self.assertIsNotNone(emp)
        self.assertEqual(emp["name"], "Joko Susilo")
        self.assertEqual(emp["status"], "active")
        self.assertIn("security", emp["capabilities"])

        # Update status
        self.db.update_employee_status("dev_007", status="inactive", availability="offline")
        updated = self.db.get_employee("dev_007")
        self.assertEqual(updated["status"], "inactive")
        self.assertEqual(updated["availability"], "offline")


    def test_sync_organization_to_db(self):
        org, _ = create_default_organization()
        self.db.sync_organization_to_db(org)

        db_depts = self.db.get_departments()
        self.assertTrue(len(db_depts) >= 8)

        db_emps = self.db.get_employees()
        self.assertEqual(len(db_emps), 5)


# =====================================================================
# 12. Full Integration Simulation (>= 3 departments, >= 5 roles, >= 10 employees)
# =====================================================================

class TestWorkforceIntegrationSimulation(unittest.TestCase):
    """Rigorous integration simulation testing dynamic scaling of workforce."""

    def setUp(self):
        self.bus = EventBus()
        self.db = Database(":memory:", event_bus=self.bus)
        self.org = Organization(name="Aether Scale Test", event_bus=self.bus)
        self.factory = AgentFactory(organization=self.org)
        self.llm = MagicMock(spec=LLMClient)

        self.events_collected: list[Event] = []
        self.bus.subscribe(self.events_collected.append)

    def test_full_workforce_simulation_with_10_employees(self):
        # 1. Register 3 Departments
        eng = Department(name="Engineering", department_id="engineering")
        prod = Department(name="Product", department_id="product")
        mkt = Department(name="Marketing", department_id="marketing")
        self.org.register_department(eng)
        self.org.register_department(prod)
        self.org.register_department(mkt)

        # 2. Register 5 Roles
        r_backend = Role(role_id="backend_developer", name="Backend Developer", department="engineering", capabilities=["python", "api", "sqlite"])
        r_frontend = Role(role_id="frontend_developer", name="Frontend Developer", department="engineering", capabilities=["react", "typescript", "css"])
        r_copy = Role(role_id="copywriter", name="Copywriter", department="marketing", capabilities=["copywriting", "creative_writing"])
        r_seo = Role(role_id="seo_specialist", name="SEO Specialist", department="marketing", capabilities=["seo", "keyword_research"])
        r_pm = Role(role_id="product_manager", name="Product Manager", department="product", capabilities=["task_breakdown", "scoping"])

        for r in [r_backend, r_frontend, r_copy, r_seo, r_pm]:
            self.org.register_role(r)

        # 3. Hire 10 Employees
        # Two backend developers with different personalities and capabilities
        e1 = self.org.hire(name="Bagas Aditya", role="backend_developer", capabilities=["python", "api", "sqlite", "fastapi"], personality={"traits": ["analytical"], "communication_style": "concise"})
        e2 = self.org.hire(name="Bayu Setiawan", role="backend_developer", capabilities=["python", "django", "postgresql"], personality={"traits": ["methodical"], "communication_style": "verbose"})

        # Two frontend developers
        e3 = self.org.hire(name="Citra Dewi", role="frontend_developer", capabilities=["react", "typescript", "tailwind"], personality={"traits": ["creative"]})
        e4 = self.org.hire(name="Dimas Prasetya", role="frontend_developer", capabilities=["vue", "javascript", "html"], personality={"traits": ["practical"]})

        # Two copywriters with same role, different skills and personality
        e5 = self.org.hire(name="Laras Wulandari", role="copywriter", capabilities=["copywriting", "messaging", "viral_hooks"], personality={"traits": ["witty"], "communication_style": "punchy"})
        e6 = self.org.hire(name="Maya Anggraini", role="copywriter", capabilities=["copywriting", "technical_writing", "newsletters"], personality={"traits": ["structured"], "communication_style": "academic"})

        # Two SEO specialists
        e7 = self.org.hire(name="Surya Pratama", role="seo_specialist", capabilities=["seo", "keyword_research", "analytics"])
        e8 = self.org.hire(name="Tiara Kusuma", role="seo_specialist", capabilities=["seo", "site_audit", "speed_optimization"])

        # Two product managers
        e9 = self.org.hire(name="Panji Nugroho", role="product_manager", capabilities=["task_breakdown", "scoping", "user_stories"])
        e10 = self.org.hire(name="Putri Rahayu", role="product_manager", capabilities=["task_breakdown", "roadmapping", "agile"])

        # Verify workforce counts
        self.assertEqual(self.org.get_employee_count(), 10)
        self.assertEqual(len(self.org.get_active_employees()), 10)

        # 4. Verify Same-Role Employees are Independently Usable
        self.assertNotEqual(e5.employee_id, e6.employee_id)
        self.assertEqual(e5.role, e6.role)
        self.assertNotEqual(e5.capabilities, e6.capabilities)

        # 5. Test Deterministic Task Matching to Best Employee
        # Task A: Requires FastAPI and SQLite backend dev -> Should match Bagas Aditya (e1), NOT Bayu Setiawan (e2)
        task_api = {
            "title": "Build Fast SQLite Backend",
            "role": "backend_developer",
            "department": "engineering",
            "required_capabilities": ["fastapi", "sqlite"],
        }
        best_backend = TaskMatcher.find_best_employee(task_api, self.org.list_employees())
        self.assertEqual(best_backend.employee_id, e1.employee_id)

        # Task B: Requires Viral hooks copywriting -> Should match Laras Wulandari (e5), NOT Maya Anggraini (e6)
        task_copy = {
            "title": "Launch Twitter Campaign",
            "role": "copywriter",
            "department": "marketing",
            "required_capabilities": ["viral_hooks"],
        }
        best_copy = TaskMatcher.find_best_employee(task_copy, self.org.list_employees())
        self.assertEqual(best_copy.employee_id, e5.employee_id)

        # 6. Instantiate Agents via AgentFactory and Execute Tasks
        self.llm.chat.return_value = "API endpoints constructed with FastAPI and SQLite."

        agent_bagas = self.factory.create_agent(best_backend, self.llm, self.db, "sim_project", "/tmp")
        result_bagas = agent_bagas.run("Implement user endpoints", task=task_api)
        self.assertTrue(result_bagas.success)
        self.assertIn("API endpoints", result_bagas.output)

        # 7. Verify Events Emitted on EventBus
        state_events = [e for e in self.events_collected if e.event_type == EVENT_AGENT_STATE_CHANGED]
        self.assertTrue(len(state_events) >= 2)
        self.assertEqual(state_events[-1].agent_id, e1.employee_id)
        self.assertEqual(state_events[-1].status, STATE_COMPLETED)

        # 8. Verify SQLite Persistence of the Entire Workforce
        self.db.sync_organization_to_db(self.org)
        stored_emps = self.db.get_employees()
        self.assertEqual(len(stored_emps), 10)

        stored_depts = self.db.get_departments()
        self.assertEqual(len(stored_depts), 3)

        stored_roles = self.db.get_roles()
        self.assertEqual(len(stored_roles), 5)


if __name__ == "__main__":
    unittest.main()

"""Core Workforce Model — Organizations, Departments, Roles, Employees, and Registries."""

from __future__ import annotations
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from events import (
    Event,
    EventBus,
    EVENT_EMPLOYEE_HIRED,
    EVENT_EMPLOYEE_DEACTIVATED,
    EVENT_ROLE_REGISTERED,
    EVENT_DEPARTMENT_REGISTERED,
)

# Standard Agent States from Phase 3
STATE_IDLE = "IDLE"
STATE_THINKING = "THINKING"
STATE_PLANNING = "PLANNING"
STATE_WORKING = "WORKING"
STATE_WAITING = "WAITING"
STATE_RETRYING = "RETRYING"
STATE_TESTING = "TESTING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"
STATE_BLOCKED = "BLOCKED"

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"

AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_BUSY = "busy"
AVAILABILITY_OFFLINE = "offline"


# =====================================================================
# 1. Role & Role Catalog
# =====================================================================

@dataclass
class Role:
    """Role definition within an organization."""
    role_id: str
    name: str
    department: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    default_model: Optional[dict] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "department": self.department,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "default_model": dict(self.default_model) if self.default_model else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Role:
        return cls(
            role_id=d["role_id"],
            name=d.get("name", d["role_id"]),
            department=d.get("department", "engineering"),
            description=d.get("description", ""),
            capabilities=d.get("capabilities", []) or [],
            default_model=d.get("default_model"),
            metadata=d.get("metadata", {}) or {},
        )


class RoleCatalog:
    """Registry and catalog for managing roles across the organization."""

    def __init__(self):
        self._roles: dict[str, Role] = {}
        self._lock = threading.Lock()

    def register(self, role: Role) -> Role:
        """Register a new role in the catalog. Replaces or adds."""
        if not isinstance(role, Role):
            raise TypeError(f"Expected Role, got {type(role).__name__}")
        with self._lock:
            self._roles[role.role_id] = role
            return role

    def get(self, role_id: str) -> Optional[Role]:
        """Lookup a role by role_id."""
        with self._lock:
            return self._roles.get(role_id)

    def list(self) -> list[Role]:
        """List all registered roles."""
        with self._lock:
            return list(self._roles.values())

    def find_by_department(self, department: str) -> list[Role]:
        """List all roles belonging to a department."""
        with self._lock:
            return [r for r in self._roles.values() if r.department == department]

    def clear(self) -> None:
        with self._lock:
            self._roles.clear()


def get_seed_roles() -> list[Role]:
    """Provide the default seed catalog across 8 organization departments."""
    return [
        # Product
        Role(
            role_id="product_manager",
            name="Product Manager",
            department="product",
            description="Defines project scope, user stories, task breakdown, and acceptance standards",
            capabilities=["task_breakdown", "planning", "prioritization", "scoping"],
        ),
        Role(
            role_id="product_researcher",
            name="Product Researcher",
            department="product",
            description="Investigates user needs, product benchmarks, and feature viability",
            capabilities=["user_research", "market_analysis", "benchmarking"],
        ),
        Role(
            role_id="conceptor",
            name="Conceptor Analyst",
            department="product",
            description="Translates high-level tasks into detailed functional requirements and test specs",
            capabilities=["requirements_analysis", "acceptance_criteria", "technical_design"],
        ),
        Role(
            role_id="business_analyst",
            name="Business Analyst",
            department="product",
            description="Analyzes workflows, business metrics, and functional feasibility",
            capabilities=["workflow_analysis", "metrics", "feasibility"],
        ),

        # Engineering
        Role(
            role_id="software_architect",
            name="Software Architect & Planner",
            department="engineering",
            description="Designs system architecture, component dependency graphs, and technical blueprints",
            capabilities=["software_architecture", "dependency_graph", "topological_sort", "implementation_planning"],
        ),
        Role(
            role_id="backend_developer",
            name="Backend Developer",
            department="engineering",
            description="Builds backend logic, APIs, database layers, and services",
            capabilities=["python", "api", "database", "sqlite", "modular_coding"],
        ),
        Role(
            role_id="frontend_developer",
            name="Frontend Developer",
            department="engineering",
            description="Builds user interfaces, web components, and frontend logic",
            capabilities=["html", "css", "javascript", "ui_components"],
        ),
        Role(
            role_id="fullstack_developer",
            name="Full-Stack Developer",
            department="engineering",
            description="Develops end-to-end applications across backend and frontend",
            capabilities=["python", "modular_coding", "syntax_validation", "debugging", "unit_generation"],
        ),
        Role(
            role_id="mobile_developer",
            name="Mobile Developer",
            department="engineering",
            description="Builds mobile applications for Android and iOS platforms",
            capabilities=["mobile", "flutter", "native_ui"],
        ),
        Role(
            role_id="qa_engineer",
            name="QA Engineer",
            department="engineering",
            description="Conducts automated testing, syntax review, bug diagnostics, and verification",
            capabilities=["automated_testing", "code_review", "bug_diagnosis", "test_runner"],
        ),
        Role(
            role_id="devops_engineer",
            name="DevOps Engineer",
            department="engineering",
            description="Manages deployment pipelines, containers, and environment configurations",
            capabilities=["docker", "ci_cd", "cloud", "scripting"],
        ),
        Role(
            role_id="security_engineer",
            name="Security Engineer",
            department="engineering",
            description="Conducts security audits, vulnerability scanning, and hardening",
            capabilities=["security_audit", "vulnerability_scan", "auth_review"],
        ),
        Role(
            role_id="data_engineer",
            name="Data Engineer",
            department="engineering",
            description="Builds data transformation pipelines and storage schemas",
            capabilities=["sql", "etl", "data_modeling"],
        ),

        # Design
        Role(
            role_id="ui_designer",
            name="UI Designer",
            department="design",
            description="Crafts user interfaces, design systems, visual hierarchy, and component specs",
            capabilities=["ui_design", "design_systems", "layout", "color_theory"],
        ),
        Role(
            role_id="ux_designer",
            name="UX Designer",
            department="design",
            description="Designs user journeys, wireframes, and usability flows",
            capabilities=["ux_research", "wireframing", "user_flows"],
        ),
        Role(
            role_id="graphic_designer",
            name="Graphic Designer",
            department="design",
            description="Produces visual marketing assets, illustrations, and icons",
            capabilities=["graphic_design", "illustration", "branding"],
        ),
        Role(
            role_id="brand_designer",
            name="Brand Designer",
            department="design",
            description="Develops brand identity, typography guidelines, and tone guidelines",
            capabilities=["branding", "typography", "style_guides"],
        ),
        Role(
            role_id="motion_designer",
            name="Motion Designer",
            department="design",
            description="Creates interactive animations and transition specifications",
            capabilities=["animation", "motion_graphics", "transitions"],
        ),

        # Marketing
        Role(
            role_id="marketing_strategist",
            name="Marketing Strategist",
            department="marketing",
            description="Develops go-to-market strategies, campaign roadmaps, and audience targeting",
            capabilities=["campaign_strategy", "audience_targeting", "gtm"],
        ),
        Role(
            role_id="copywriter",
            name="Copywriter",
            department="marketing",
            description="Writes engaging persuasive copy, landing page headlines, and value propositions",
            capabilities=["copywriting", "creative_writing", "messaging"],
        ),
        Role(
            role_id="seo_specialist",
            name="SEO Specialist",
            department="marketing",
            description="Optimizes content for search visibility, keywords, and technical indexing",
            capabilities=["seo", "keyword_research", "content_optimization"],
        ),
        Role(
            role_id="social_media_manager",
            name="Social Media Manager",
            department="marketing",
            description="Crafts social media posts, threads, and community engagement updates",
            capabilities=["social_media", "community_updates", "viral_hooking"],
        ),
        Role(
            role_id="content_strategist",
            name="Content Strategist",
            department="marketing",
            description="Plans editorial calendars and informational content funnels",
            capabilities=["content_planning", "editorial_calendar", "content_funnels"],
        ),
        Role(
            role_id="email_marketer",
            name="Email Marketer",
            department="marketing",
            description="Designs email drip campaigns, newsletters, and conversion sequences",
            capabilities=["email_copy", "newsletters", "conversion_optimization"],
        ),

        # Research
        Role(
            role_id="researcher",
            name="General Researcher",
            department="research",
            description="Performs deep-dive literature, technological, and documentation research",
            capabilities=["deep_research", "information_synthesis", "technical_writing"],
        ),
        Role(
            role_id="data_analyst",
            name="Data Analyst",
            department="research",
            description="Performs statistical data analysis, charting, and insight extraction",
            capabilities=["data_analysis", "statistics", "visualization"],
        ),
        Role(
            role_id="market_researcher",
            name="Market Researcher",
            department="research",
            description="Conducts competitor analysis, industry trends, and pricing research",
            capabilities=["market_research", "competitor_intel", "pricing_research"],
        ),
        Role(
            role_id="competitive_analyst",
            name="Competitive Analyst",
            department="research",
            description="Monitors and benchmarks market competitors and feature matrices",
            capabilities=["competitor_intel", "feature_matrix", "swot"],
        ),

        # Operations
        Role(
            role_id="operations_manager",
            name="Operations Manager",
            department="operations",
            description="Monitors workflow throughput, operational dependencies, and resource allocation",
            capabilities=["workflow_optimization", "resource_allocation", "process_management"],
        ),
        Role(
            role_id="project_coordinator",
            name="Project Coordinator",
            department="operations",
            description="Facilitates handoffs between departments and tracks milestone deliveries",
            capabilities=["handoff_coordination", "tracking", "reporting"],
        ),
        Role(
            role_id="documentation_specialist",
            name="Documentation Specialist",
            department="operations",
            description="Writes, organizes, and maintains comprehensive project documentation and manuals",
            capabilities=["documentation", "markdown", "knowledge_base"],
        ),

        # Business
        Role(
            role_id="sales",
            name="Sales Specialist",
            department="business",
            description="Formulates pitch decks, sales proposals, and client outreach communications",
            capabilities=["sales_pitch", "proposals", "negotiation"],
        ),
        Role(
            role_id="account_manager",
            name="Account Manager",
            department="business",
            description="Manages client relationships, requirements retention, and delivery feedback",
            capabilities=["client_communication", "relationship_management"],
        ),
        Role(
            role_id="finance",
            name="Finance Specialist",
            department="business",
            description="Analyzes costs, revenue projections, and resource budgets",
            capabilities=["budgeting", "cost_analysis", "forecasting"],
        ),
        Role(
            role_id="business_development",
            name="Business Development",
            department="business",
            description="Identifies strategic partnerships, expansion avenues, and market opportunities",
            capabilities=["partnership_strategy", "growth", "networking"],
        ),

        # Support
        Role(
            role_id="customer_support",
            name="Customer Support Specialist",
            department="support",
            description="Provides empathetic, solution-oriented answers to user inquiries and issues",
            capabilities=["customer_support", "troubleshooting", "empathetic_communication"],
        ),
        Role(
            role_id="community_manager",
            name="Community Manager",
            department="support",
            description="Engages user communities, answers community queries, and collects feedback",
            capabilities=["community_engagement", "moderation", "feedback_collection"],
        ),
    ]


# =====================================================================
# 2. Department & Department Registry
# =====================================================================

@dataclass
class Department:
    """Department container within an organization."""
    name: str = ""
    description: str = ""
    department_id: str = ""
    default_model: Optional[dict] = None
    agent_ids: list[str] = field(default_factory=list)  # Backward-compatible with Phase 3

    def __post_init__(self):
        if not self.department_id and self.name:
            self.department_id = self.name.lower()
        if not self.name and self.department_id:
            self.name = self.department_id.title()

    @property
    def employee_ids(self) -> list[str]:
        return self.agent_ids

    def to_dict(self) -> dict:
        return {
            "department_id": self.department_id,
            "name": self.name,
            "description": self.description,
            "default_model": dict(self.default_model) if self.default_model else None,
            "agent_ids": list(self.agent_ids),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Department:
        dept_id = d.get("department_id") or d.get("id") or d.get("name", "engineering").lower()
        name = d.get("name", dept_id.title())
        return cls(
            department_id=dept_id,
            name=name,
            description=d.get("description", ""),
            default_model=d.get("default_model"),
            agent_ids=d.get("agent_ids", []) or d.get("employee_ids", []) or [],
        )


class DepartmentRegistry:
    """Registry for managing departments with dict-like compatibility."""

    def __init__(self):
        self._departments: dict[str, Department] = {}
        self._lock = threading.Lock()

    def register(self, dept: Department) -> Department:
        if not isinstance(dept, Department):
            raise TypeError(f"Expected Department, got {type(dept).__name__}")
        with self._lock:
            self._departments[dept.department_id] = dept
            self._departments[dept.name] = dept
            return dept

    def get(self, department_id: str, default: Any = None) -> Optional[Department]:
        with self._lock:
            return self._departments.get(department_id, self._departments.get(department_id.lower(), default))

    def list(self) -> list[Department]:
        with self._lock:
            # deduplicate by department_id
            seen = set()
            res = []
            for d in self._departments.values():
                if d.department_id not in seen:
                    seen.add(d.department_id)
                    res.append(d)
            return res

    def clear(self) -> None:
        with self._lock:
            self._departments.clear()

    # Dict-like compatibility
    def __getitem__(self, key: str) -> Department:
        item = self.get(key)
        if item is None:
            raise KeyError(key)
        return item

    def __setitem__(self, key: str, value: Department) -> None:
        self.register(value)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __iter__(self):
        return iter(d.department_id for d in self.list())

    def __len__(self) -> int:
        return len(self.list())

    def values(self):
        return self.list()

    def items(self):
        return [(d.department_id, d) for d in self.list()]


ALL_AGENT_STATES = {
    STATE_IDLE,
    STATE_THINKING,
    STATE_PLANNING,
    STATE_WORKING,
    STATE_WAITING,
    STATE_RETRYING,
    STATE_TESTING,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_BLOCKED,
}


# =====================================================================
# 3. Employee Profile & Registry
# =====================================================================

class Employee:
    """Generic Employee profile representing an autonomous AI worker."""

    def __init__(
        self,
        employee_id: Optional[str] = None,
        name: str = "",
        role: str = "developer",
        department: str = "engineering",
        capabilities: Optional[list[str]] = None,
        personality: Optional[dict] = None,
        model: Optional[Any] = None,
        status: Optional[str] = None,
        availability: str = AVAILABILITY_AVAILABLE,
        live_state: str = STATE_IDLE,
        metadata: Optional[dict] = None,
        id: Optional[str] = None,
        active_tasks: int = 0,
        queued_tasks: int = 0,
        completed_tasks: int = 0,
    ):
        self.employee_id = employee_id or id or ""
        self.name = name or self.employee_id
        self.role = role
        self.department = department
        self.capabilities = list(capabilities) if capabilities else []
        self.personality = dict(personality) if personality else {
            "traits": ["analytical", "systematic"],
            "communication_style": "concise",
            "decision_style": "evidence_based",
        }
        if isinstance(model, dict):
            self.model = model
        elif isinstance(model, str):
            self.model = {"provider": "openai-compatible", "model": model}
        else:
            self.model = {"provider": "openai-compatible", "model": None}

        self.status = status or STATUS_ACTIVE
        self.availability = availability
        self.live_state = live_state
        self.metadata = dict(metadata) if metadata else {}
        self.active_tasks = active_tasks
        self.queued_tasks = queued_tasks
        self.completed_tasks = completed_tasks

    @property
    def id(self) -> str:
        """Alias for backward-compatibility with Phase 3 AgentManifest.id."""
        return self.employee_id

    @id.setter
    def id(self, val: str):
        self.employee_id = val

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE or (self.status in ALL_AGENT_STATES and self.status != STATE_BLOCKED)

    @property
    def workload(self) -> int:
        """Returns the current workload (active + queued tasks)."""
        return self.active_tasks + self.queued_tasks

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "id": self.employee_id,  # Compatibility
            "name": self.name,
            "role": self.role,
            "department": self.department,
            "capabilities": list(self.capabilities),
            "personality": dict(self.personality),
            "model": dict(self.model),
            "status": self.status,
            "availability": self.availability,
            "live_state": self.live_state,
            "metadata": dict(self.metadata),
            "active_tasks": self.active_tasks,
            "queued_tasks": self.queued_tasks,
            "completed_tasks": self.completed_tasks,
            "workload": self.workload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Employee:
        emp_id = d.get("employee_id") or d.get("id")
        if not emp_id:
            raise ValueError("Employee dictionary must contain 'employee_id' or 'id'")
        return cls(
            employee_id=emp_id,
            name=d.get("name", emp_id),
            role=d.get("role", "developer"),
            department=d.get("department", "engineering"),
            capabilities=d.get("capabilities", []) or [],
            personality=d.get("personality", {}) or {
                "traits": ["analytical", "systematic"],
                "communication_style": "concise",
            },
            model=d.get("model", {}) if isinstance(d.get("model"), dict) else {
                "provider": "openai-compatible",
                "model": d.get("model"),
            },
            status=d.get("status", STATUS_ACTIVE),
            availability=d.get("availability", AVAILABILITY_AVAILABLE),
            live_state=d.get("live_state", STATE_IDLE),
            metadata=d.get("metadata", {}) or {},
            active_tasks=d.get("active_tasks", 0),
            queued_tasks=d.get("queued_tasks", 0),
            completed_tasks=d.get("completed_tasks", 0),
        )


class AgentManifest(Employee):
    """Phase 3 backward-compatible wrapper around Employee."""

    def __init__(
        self,
        id: str,
        name: str,
        role: str,
        department: str = "engineering",
        capabilities: Optional[list[str]] = None,
        model: Optional[str] = None,
        status: str = STATE_IDLE,
        metadata: Optional[dict] = None,
    ):
        super().__init__(
            id=id,
            name=name,
            role=role,
            department=department,
            capabilities=capabilities,
            model={"provider": "openai-compatible", "model": model} if model else None,
            status=status,
            live_state=status,
            metadata=metadata,
        )

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["model"] = self.model.get("model") if isinstance(self.model, dict) else self.model
        return d

    @classmethod
    def from_dict(cls, d: dict) -> AgentManifest:
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            role=d.get("role", "base"),
            department=d.get("department", "engineering"),
            capabilities=d.get("capabilities", []) or [],
            model=d.get("model") if isinstance(d.get("model"), str) else (d.get("model", {}) or {}).get("model"),
            status=d.get("status", STATE_IDLE),
            metadata=d.get("metadata", {}) or {},
        )


class EmployeeRegistry:
    """Thread-safe registry for employee indexing and state tracking."""

    def __init__(self):
        self._employees: dict[str, Employee] = {}
        self._lock = threading.Lock()

    def register(self, employee: Employee) -> Employee:
        """Register an employee. Rejects duplicate IDs."""
        if not isinstance(employee, (Employee, AgentManifest)):
            raise TypeError(f"Expected Employee or AgentManifest, got {type(employee).__name__}")
        with self._lock:
            if employee.employee_id in self._employees:
                raise ValueError(f"Employee with ID '{employee.employee_id}' already registered")
            self._employees[employee.employee_id] = employee
            return employee

    def get(self, employee_id: str) -> Optional[Employee]:
        """Look up an employee by ID."""
        with self._lock:
            return self._employees.get(employee_id)

    def list(self) -> list[Employee]:
        """List all registered employees."""
        with self._lock:
            return list(self._employees.values())

    def find_by_role(self, role: str) -> list[Employee]:
        """Find all employees matching a given role."""
        with self._lock:
            return [e for e in self._employees.values() if e.role == role]

    def find_by_department(self, department: str) -> list[Employee]:
        """Find all employees in a specific department."""
        with self._lock:
            return [e for e in self._employees.values() if e.department == department]

    def find_by_capability(self, capability: str) -> list[Employee]:
        """Find all employees possessing a specific capability."""
        with self._lock:
            return [e for e in self._employees.values() if capability in e.capabilities]

    def update_status(self, employee_id: str, status: str) -> bool:
        """Update live status of a registered employee."""
        with self._lock:
            emp = self._employees.get(employee_id)
            if emp:
                emp.live_state = status
                # If this is an AgentManifest or had a Phase 3 agent state in status, update status as well
                if isinstance(emp, AgentManifest) or emp.status in ALL_AGENT_STATES:
                    emp.status = status
                # If status is an execution state, update availability
                if status in (STATE_WORKING, STATE_PLANNING, STATE_TESTING, STATE_THINKING):
                    emp.availability = AVAILABILITY_BUSY
                elif status in (STATE_IDLE, STATE_COMPLETED):
                    emp.availability = AVAILABILITY_AVAILABLE
                return True
            return False

    def clear(self) -> None:
        """Clear registry for test isolation."""
        with self._lock:
            self._employees.clear()



# =====================================================================
# 4. Organization Container
# =====================================================================

class Organization:
    """High-level organization container coordinating departments, roles, and employees."""

    def __init__(self, name: str = "Aether Office", event_bus: Optional[EventBus] = None):
        self.name = name
        self.event_bus = event_bus
        self.departments = DepartmentRegistry()
        self.roles = RoleCatalog()
        self.employees = EmployeeRegistry()
        self.default_model: dict = {
            "provider": "openai-compatible",
            "model": None,
            "temperature": 0.7,
            "max_tokens": 4096,
        }

    # Department operations
    def register_department(self, dept: Department) -> Department:
        self.departments.register(dept)
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=EVENT_DEPARTMENT_REGISTERED,
                project_id="",
                payload=dept.to_dict(),
            ))
        return dept

    def add_department(self, dept: Department) -> Department:
        """Alias for register_department for Phase 3 backward-compatibility."""
        return self.register_department(dept)


    def get_department(self, department_id: str) -> Optional[Department]:
        return self.departments.get(department_id)

    def list_departments(self) -> list[Department]:
        return self.departments.list()

    # Role operations
    def register_role(self, role: Role) -> Role:
        self.roles.register(role)
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=EVENT_ROLE_REGISTERED,
                project_id="",
                agent_role=role.role_id,
                payload=role.to_dict(),
            ))
        return role

    def get_role(self, role_id: str) -> Optional[Role]:
        return self.roles.get(role_id)

    def list_roles(self) -> list[Role]:
        return self.roles.list()

    # Employee operations (Hiring / Firing)
    def hire(
        self,
        name: str,
        role: str,
        department: Optional[str] = None,
        capabilities: Optional[list[str]] = None,
        personality: Optional[dict] = None,
        model: Optional[dict] = None,
        employee_id: Optional[str] = None,
    ) -> Employee:
        """Hire a new employee into the organization."""
        # Derive department from role if not specified
        if not department:
            role_obj = self.roles.get(role)
            department = role_obj.department if role_obj else "engineering"

        # Generate unique employee ID if not provided
        if not employee_id:
            existing = self.employees.find_by_role(role)
            idx = len(existing) + 1
            employee_id = f"{role}_{idx:03d}"
            # Ensure unique in case of gaps
            while self.employees.get(employee_id):
                idx += 1
                employee_id = f"{role}_{idx:03d}"

        # If capabilities not provided, inherit default capabilities from role
        if capabilities is None:
            role_obj = self.roles.get(role)
            capabilities = list(role_obj.capabilities) if role_obj else []

        emp = Employee(
            employee_id=employee_id,
            name=name,
            role=role,
            department=department,
            capabilities=capabilities,
            personality=personality or {
                "traits": ["analytical", "systematic"],
                "communication_style": "concise",
                "decision_style": "evidence_based",
            },
            model=model or {"provider": "openai-compatible", "model": None},
            status=STATUS_ACTIVE,
            availability=AVAILABILITY_AVAILABLE,
        )

        self.employees.register(emp)

        # Attach to department
        dept_obj = self.departments.get(department)
        if dept_obj and employee_id not in dept_obj.agent_ids:
            dept_obj.agent_ids.append(employee_id)

        # Emit event
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=EVENT_EMPLOYEE_HIRED,
                project_id="",
                agent_id=emp.employee_id,
                agent_role=emp.role,
                status=emp.status,
                payload=emp.to_dict(),
            ))

        return emp

    def hire_employee(self, employee: Employee) -> Employee:
        """Register an already instantiated Employee directly into the workforce."""
        emp = self.employees.register(employee)
        dept_obj = self.departments.get(employee.department)
        if dept_obj and employee.employee_id not in dept_obj.agent_ids:
            dept_obj.agent_ids.append(employee.employee_id)
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=EVENT_EMPLOYEE_HIRED,
                project_id="",
                agent_id=emp.employee_id,
                agent_role=emp.role,
                status=emp.status,
                payload=emp.to_dict(),
            ))
        return emp

    def list_employees(self) -> list[Employee]:
        """List all active and registered employees in the organization."""
        return self.employees.list()


    def register_employee(self, emp: Employee) -> Employee:
        """Register an existing Employee instance into the organization."""
        self.employees.register(emp)
        dept_obj = self.departments.get(emp.department)
        if dept_obj and emp.employee_id not in dept_obj.agent_ids:
            dept_obj.agent_ids.append(emp.employee_id)
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=EVENT_EMPLOYEE_HIRED,
                project_id="",
                agent_id=emp.employee_id,
                agent_role=emp.role,
                status=emp.status,
                payload=emp.to_dict(),
            ))
        return emp

    def fire(self, employee_id: str) -> bool:
        """Deactivate / fire an employee."""
        emp = self.employees.get(employee_id)
        if not emp:
            return False

        emp.status = STATUS_INACTIVE
        emp.availability = AVAILABILITY_OFFLINE
        emp.live_state = STATE_BLOCKED

        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=EVENT_EMPLOYEE_DEACTIVATED,
                project_id="",
                agent_id=emp.employee_id,
                agent_role=emp.role,
                status=emp.status,
                payload={"employee_id": employee_id, "status": emp.status},
            ))

        return True

    def get_employee(self, employee_id: str) -> Optional[Employee]:
        return self.employees.get(employee_id)

    def list_employees(self) -> list[Employee]:
        return self.employees.list()

    def find_by_role(self, role: str) -> list[Employee]:
        return self.employees.find_by_role(role)

    def find_by_department(self, department: str) -> list[Employee]:
        return self.employees.find_by_department(department)

    def find_by_capability(self, capability: str) -> list[Employee]:
        return self.employees.find_by_capability(capability)

    # Organization State & Analytics
    def get_employee_count(self, active_only: bool = False) -> int:
        all_emps = self.employees.list()
        if active_only:
            return sum(1 for e in all_emps if e.status == STATUS_ACTIVE)
        return len(all_emps)

    def get_active_employees(self) -> list[Employee]:
        return [e for e in self.employees.list() if e.status == STATUS_ACTIVE]

    def get_department_stats(self) -> dict:
        """Return breakdown of employees and roles per department."""
        stats = {}
        for dept in self.departments.list():
            dept_id = dept.department_id
            emps = [e for e in self.employees.find_by_department(dept_id) if e.status == STATUS_ACTIVE]
            role_breakdown = {}
            for e in emps:
                role_breakdown[e.role] = role_breakdown.get(e.role, 0) + 1
            stats[dept_id] = {
                "name": dept.name,
                "total_active": len(emps),
                "roles": role_breakdown,
            }
        return stats


# =====================================================================
# 5. Default Factory Constructor
# =====================================================================

def create_default_organization(event_bus: Optional[EventBus] = None) -> tuple[Organization, EmployeeRegistry]:
    """Create default Aether Office organization with seed roles and default specialists."""
    org = Organization(name="Aether Office", event_bus=event_bus)

    # 1. Register Standard Departments
    standard_depts = [
        Department(department_id="engineering", name="Engineering", description="Software development, architecture, QA, infrastructure"),
        Department(department_id="product", name="Product", description="Product planning, requirements, user experience"),
        Department(department_id="design", name="Design", description="UI/UX design, visual identity, design systems"),
        Department(department_id="marketing", name="Marketing", description="Growth, copy, content, and communications"),
        Department(department_id="research", name="Research", description="Data analytics, market research, and feasibility"),
        Department(department_id="operations", name="Operations", description="Project coordination and documentation"),
        Department(department_id="business", name="Business", description="Sales, business development, and finance"),
        Department(department_id="support", name="Support", description="Customer support and community management"),
    ]
    for d in standard_depts:
        org.register_department(d)

    # 2. Register Seed Roles
    for r in get_seed_roles():
        org.register_role(r)

    # 3. Hire Core 5 Specialists (Indonesian Office Team)
    core_team = [
        {
            "employee_id": "pm_001",
            "name": "Budi Santoso",
            "role": "pm",
            "department": "product",
            "capabilities": ["task_breakdown", "planning", "handoff", "prioritization"],
            "personality": {
                "traits": ["terstruktur", "tegas", "solutif", "gotong_royong"],
                "communication_style": "jelas_dan_terarah",
                "decision_style": "musyawarah_mufakat",
            },
        },
        {
            "employee_id": "conceptor_001",
            "name": "Dewi Lestari",
            "role": "conceptor",
            "department": "product",
            "capabilities": ["requirements_analysis", "acceptance_criteria", "user_stories", "technical_design"],
            "personality": {
                "traits": ["teliti", "analitis", "ramah", "tanggap"],
                "communication_style": "terstruktur_dan_santun",
                "decision_style": "berbasis_fakta",
            },
        },
        {
            "employee_id": "planner_001",
            "name": "Rian Pratama",
            "role": "planner",
            "department": "engineering",
            "capabilities": ["software_architecture", "dependency_graph", "topological_sort", "implementation_planning"],
            "personality": {
                "traits": ["sistematis", "visioner", "cermat"],
                "communication_style": "ringkas_dan_lugas",
                "decision_style": "prinsip_dasar",
            },
        },
        {
            "employee_id": "developer_001",
            "name": "Eko Prasetyo",
            "role": "developer",
            "department": "engineering",
            "capabilities": ["python", "modular_coding", "syntax_validation", "debugging", "unit_generation"],
            "personality": {
                "traits": ["pragmatis", "ulet", "teliti", "cekatan"],
                "communication_style": "teknis_dan_lugas",
                "decision_style": "test_driven",
            },
        },
        {
            "employee_id": "qa_001",
            "name": "Ratna Sari",
            "role": "qa",
            "department": "engineering",
            "capabilities": ["automated_testing", "code_review", "bug_diagnosis", "test_runner"],
            "personality": {
                "traits": ["kritis", "teliti", "disiplin", "pantang_menyerah"],
                "communication_style": "tegas_dan_presisi",
                "decision_style": "verifikasi_ketat",
            },
        },
    ]


    for member in core_team:
        org.hire(
            employee_id=member["employee_id"],
            name=member["name"],
            role=member["role"],
            department=member["department"],
            capabilities=member["capabilities"],
            personality=member.get("personality"),
        )

    return org, org.employees


def seed_full_workforce(org: Organization) -> Organization:
    """Populate all 37 specialized roles with authentic Indonesian specialists if not already hired."""
    # Mapping for all 37 specialized Indonesian employees
    indonesian_specialists = [
        # Engineering
        ("pm_001", "Budi Santoso", "pm", "product", ["task_breakdown", "planning", "handoff", "prioritization"]),
        ("conceptor_001", "Dewi Lestari", "conceptor", "product", ["requirements_analysis", "acceptance_criteria", "user_stories", "technical_design"]),
        ("planner_001", "Rian Pratama", "planner", "engineering", ["software_architecture", "dependency_graph", "topological_sort", "implementation_planning"]),
        ("developer_001", "Eko Prasetyo", "developer", "engineering", ["python", "modular_coding", "syntax_validation", "debugging", "unit_generation"]),
        ("qa_001", "Ratna Sari", "qa", "engineering", ["automated_testing", "code_review", "bug_diagnosis", "test_runner"]),
        ("architect_001", "Arya Kusuma", "architect", "engineering", ["system_design", "scalability", "microservices", "api_design"]),
        ("backend_001", "Agus Hermawan", "backend_developer", "engineering", ["python", "api", "database", "sqlite", "modular_coding"]),
        ("frontend_001", "Fajar Nugraha", "frontend_developer", "engineering", ["html", "css", "javascript", "ui_components"]),
        ("fullstack_001", "Dimas Setiawan", "fullstack_developer", "engineering", ["python", "modular_coding", "syntax_validation", "debugging", "unit_generation"]),
        ("mobile_001", "Bayu Pratama", "mobile_developer", "engineering", ["mobile", "flutter", "native_ui"]),
        ("qa_eng_001", "Fitri Handayani", "qa_engineer", "engineering", ["automated_testing", "code_review", "bug_diagnosis", "test_runner"]),
        ("devops_001", "Hendra Gunawan", "devops_engineer", "engineering", ["docker", "ci_cd", "cloud", "scripting"]),
        ("security_001", "Teguh Wibowo", "security_engineer", "engineering", ["security_audit", "vulnerability_scan", "auth_review"]),
        ("data_eng_001", "Rizky Ramadhan", "data_engineer", "engineering", ["sql", "etl", "data_modeling"]),
        
        # Design
        ("ui_001", "Maya Indah", "ui_designer", "design", ["ui_design", "design_systems", "layout", "color_theory"]),
        ("ux_001", "Siti Rahma", "ux_designer", "design", ["ux_research", "wireframing", "user_flows"]),
        ("graphic_001", "Nadia Safitri", "graphic_designer", "design", ["graphic_design", "illustration", "branding"]),
        ("brand_001", "Dian Sastro", "brand_designer", "design", ["branding", "typography", "style_guides"]),
        ("motion_001", "Yoga Pratama", "motion_designer", "design", ["animation", "motion_graphics", "transitions"]),
        
        # Marketing
        ("mkt_strat_001", "Indra Wijaya", "marketing_strategist", "marketing", ["campaign_strategy", "audience_targeting", "gtm"]),
        ("copy_001", "Laras Wulandari", "copywriter", "marketing", ["copywriting", "creative_writing", "messaging"]),
        ("seo_001", "Surya Saputra", "seo_specialist", "marketing", ["seo", "keyword_research", "content_optimization"]),
        ("socmed_001", "Annisa Putri", "social_media_manager", "marketing", ["social_media", "community_updates", "viral_hooking"]),
        ("content_001", "Mega Utami", "content_strategist", "marketing", ["content_planning", "editorial_calendar", "content_funnels"]),
        ("email_001", "Gita Gutawa", "email_marketer", "marketing", ["email_copy", "newsletters", "conversion_optimization"]),
        
        # Research
        ("research_001", "Bambang Pamungkas", "researcher", "research", ["deep_research", "information_synthesis", "technical_writing"]),
        ("data_anl_001", "Wahyu Hidayat", "data_analyst", "research", ["data_analysis", "statistics", "visualization"]),
        ("mkt_res_001", "Putri Melati", "market_researcher", "research", ["market_research", "competitor_intel", "pricing_research"]),
        ("comp_anl_001", "Arief Budiman", "competitive_analyst", "research", ["competitor_intel", "feature_matrix", "swot"]),
        
        # Operations
        ("ops_mgr_001", "Tri Haryanto", "operations_manager", "operations", ["workflow_optimization", "resource_allocation", "process_management"]),
        ("proj_coord_001", "Wulan Guritno", "project_coordinator", "operations", ["handoff_coordination", "tracking", "reporting"]),
        ("docs_001", "Intan Permata", "documentation_specialist", "operations", ["documentation", "markdown", "knowledge_base"]),
        
        # Business
        ("sales_001", "Doni Salman", "sales", "business", ["sales_pitch", "proposals", "negotiation"]),
        ("acc_mgr_001", "Reza Rahadian", "account_manager", "business", ["client_communication", "relationship_management"]),
        ("finance_001", "Sri Mulyani", "finance", "business", ["budgeting", "cost_estimation", "roi_analysis"]),
        
        # Support
        ("support_001", "Lukman Sardi", "support_specialist", "support", ["ticket_resolution", "customer_guidance", "troubleshooting"]),
        ("comm_mgr_001", "Chicco Jerikho", "community_manager", "support", ["community_moderation", "event_hosting", "feedback_collection"]),
    ]

    for emp_id, name, role_id, dept_id, caps in indonesian_specialists:
        if not org.get_employee(emp_id):
            # Check if role exists in catalog
            if not org.roles.get(role_id):
                org.register_role(Role(role_id=role_id, name=role_id.replace("_", " ").title(), department=dept_id, capabilities=caps))
            org.hire(
                employee_id=emp_id,
                name=name,
                role=role_id,
                department=dept_id,
                capabilities=caps,
                personality={
                    "traits": ["profesional", "kolaboratif", "tangkas", "gotong_royong"],
                    "communication_style": "terstruktur_dan_santun",
                    "decision_style": "musyawarah_mufakat",
                },
            )
    return org


"""Comprehensive Test Suite for Phase 5: Dynamic Team Collaboration & Task Delegation."""

from __future__ import annotations
import unittest
from unittest.mock import MagicMock
import tempfile
import shutil

from workforce import (
    Organization,
    Department,
    Role,
    Employee,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    AVAILABILITY_AVAILABLE,
    AVAILABILITY_BUSY,
    AVAILABILITY_OFFLINE,
)
from matcher import TaskMatcher
from factory import AgentFactory
from events import (
    EventBus,
    Event,
    EVENT_TEAM_CREATED,
    EVENT_TEAM_MEMBER_ADDED,
    EVENT_TEAM_MEMBER_REMOVED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_STARTED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_BLOCKED,
    EVENT_TASK_DECOMPOSED,
    EVENT_ARTIFACT_CREATED,
    EVENT_ARTIFACT_HANDOFF,
    EVENT_REVIEW_REQUESTED,
    EVENT_REVIEW_COMPLETED,
    EVENT_DISCUSSION_MESSAGE,
    EVENT_WORKFLOW_COMPLETED,
    EVENT_EMPLOYEE_REASSIGNED,
)
from db import Database
from team import ProjectTeam, TeamBuilder, TEAM_ACTIVE, TEAM_COMPLETED
from tasks import (
    WorkTask,
    TaskDecomposer,
    validate_work_task_transition,
    CircularDependencyError,
    DependencyError,
    TASK_PENDING,
    TASK_READY,
    TASK_ASSIGNED,
    TASK_IN_PROGRESS,
    TASK_WAITING_REVIEW,
    TASK_BLOCKED,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_CANCELLED,
)
from artifacts import Artifact, ArtifactStore, ARTIFACT_DOCUMENT, ARTIFACT_CODE
from handoff import Handoff, HandoffManager, HANDOFF_CREATED, HANDOFF_RECEIVED, HANDOFF_ACCEPTED
from reviews import Review, ReviewRouter, REVIEW_PENDING, REVIEW_APPROVED, REVIEW_CHANGES_REQUESTED, REVIEW_REJECTED
from discussion import Discussion, DiscussionMessage, MSG_QUESTION, MSG_DECISION, MSG_ANSWER
from delegation import DelegationEngine, EXECUTION_ERROR, NO_EMPLOYEE_AVAILABLE
from workflow import WorkOrchestrator, WORKFLOW_PROJECT_COMPLETE, WORKFLOW_BLOCKED


class TestProjectTeam(unittest.TestCase):
    """Unit tests for ProjectTeam model and lifecycle."""

    def setUp(self):
        self.bus = EventBus()
        self.events = []
        self.bus.subscribe(lambda e: self.events.append(e))
        self.team = ProjectTeam(
            team_id="team_alpha",
            project_id="proj_001",
            name="Alpha Team",
            objective="Develop MVP",
            event_bus=self.bus,
        )

    def test_team_creation_and_defaults(self):
        self.assertEqual(self.team.team_id, "team_alpha")
        self.assertEqual(self.team.status, TEAM_ACTIVE)
        self.assertEqual(len(self.team.employee_ids), 0)
        self.assertIsNone(self.team.lead_employee_id)

    def test_add_and_remove_employee(self):
        self.assertTrue(self.team.add_employee("emp_budi", role="pm"))
        self.assertIn("emp_budi", self.team.employee_ids)
        # Adding duplicate should return False
        self.assertFalse(self.team.add_employee("emp_budi"))

        added_events = [e for e in self.events if e.event_type == EVENT_TEAM_MEMBER_ADDED]
        self.assertEqual(len(added_events), 1)
        self.assertEqual(added_events[0].agent_id, "emp_budi")

        # Remove employee
        self.assertTrue(self.team.remove_employee("emp_budi"))
        self.assertNotIn("emp_budi", self.team.employee_ids)
        removed_events = [e for e in self.events if e.event_type == EVENT_TEAM_MEMBER_REMOVED]
        self.assertEqual(len(removed_events), 1)

    def test_set_lead_and_close(self):
        self.team.add_employee("emp_rian")
        self.team.add_employee("emp_dewi")
        self.team.set_lead("emp_rian")
        self.assertEqual(self.team.lead_employee_id, "emp_rian")

        self.team.close(status=TEAM_COMPLETED)
        self.assertEqual(self.team.status, TEAM_COMPLETED)


class TestWorkTaskAndStateMachine(unittest.TestCase):
    """Unit tests for WorkTask state transitions and dependency validation."""

    def test_valid_state_transitions(self):
        task = WorkTask(task_id="t1", project_id="p1", title="Init Project")
        self.assertEqual(task.status, TASK_PENDING)

        # PENDING -> READY
        self.assertTrue(task.transition_to(TASK_READY))
        self.assertEqual(task.status, TASK_READY)

        # READY -> ASSIGNED
        self.assertTrue(task.transition_to(TASK_ASSIGNED))
        self.assertEqual(task.status, TASK_ASSIGNED)

        # ASSIGNED -> IN_PROGRESS
        self.assertTrue(task.transition_to(TASK_IN_PROGRESS))
        self.assertIsNotNone(task.started_at)

        # IN_PROGRESS -> WAITING_REVIEW
        self.assertTrue(task.transition_to(TASK_WAITING_REVIEW))

        # WAITING_REVIEW -> COMPLETED
        self.assertTrue(task.transition_to(TASK_COMPLETED))
        self.assertIsNotNone(task.completed_at)

    def test_invalid_state_transition_raises(self):
        task = WorkTask(task_id="t2", project_id="p1", title="Invalid Transition Test")
        # Cannot jump from PENDING directly to COMPLETED
        with self.assertRaises(ValueError):
            task.transition_to(TASK_COMPLETED)

    def test_topological_sort_and_dependencies(self):
        t1 = WorkTask(task_id="t1", project_id="p", title="Task 1", dependencies=[])
        t2 = WorkTask(task_id="t2", project_id="p", title="Task 2", dependencies=["t1"])
        t3 = WorkTask(task_id="t3", project_id="p", title="Task 3", dependencies=["t2"])

        sorted_tasks = TaskDecomposer.topological_sort([t3, t1, t2])
        self.assertEqual([t.task_id for t in sorted_tasks], ["t1", "t2", "t3"])

    def test_circular_dependency_detection(self):
        t1 = WorkTask(task_id="t1", project_id="p", title="Task 1", dependencies=["t2"])
        t2 = WorkTask(task_id="t2", project_id="p", title="Task 2", dependencies=["t1"])

        with self.assertRaises(CircularDependencyError):
            TaskDecomposer.topological_sort([t1, t2])

    def test_self_dependency_raises(self):
        t1 = WorkTask(task_id="t1", project_id="p", title="Self Dep Task")
        with self.assertRaises(CircularDependencyError):
            t1.add_dependency("t1")


class TestTaskMatcherWorkload(unittest.TestCase):
    """Tests for TaskMatcher incorporating workload penalty and availability."""

    def setUp(self):
        self.emp1 = Employee(
            employee_id="emp_eko",
            name="Eko Prasetyo",
            role="developer",
            department="engineering",
            capabilities=["python", "fastapi"],
            active_tasks=0,
        )
        self.emp2 = Employee(
            employee_id="emp_bayu",
            name="Bayu Setiawan",
            role="developer",
            department="engineering",
            capabilities=["python", "fastapi"],
            active_tasks=3,  # Heavily loaded
        )

    def test_workload_penalty_ranks_free_employee_higher(self):
        task = {"role": "developer", "required_capabilities": ["python", "fastapi"]}
        score1 = TaskMatcher.score_candidate(self.emp1, task)
        score2 = TaskMatcher.score_candidate(self.emp2, task)

        # emp2 has penalty of 3 * 2 = 6 points
        self.assertEqual(score1 - score2, 6)

        best = TaskMatcher.find_best_employee(task, [self.emp2, self.emp1])
        self.assertEqual(best.employee_id, "emp_eko")

    def test_unavailable_and_inactive_rejection(self):
        busy_emp = Employee(
            employee_id="busy",
            role="developer",
            availability=AVAILABILITY_BUSY,
        )
        inactive_emp = Employee(
            employee_id="inactive",
            role="developer",
            status=STATUS_INACTIVE,
        )
        task = {"role": "developer"}
        self.assertEqual(TaskMatcher.score_candidate(busy_emp, task), -1)
        self.assertEqual(TaskMatcher.score_candidate(inactive_emp, task), -1)


class TestArtifactAndVersioning(unittest.TestCase):
    """Unit tests for Artifact model and ArtifactStore."""

    def test_artifact_versioning(self):
        art_v1 = Artifact(
            artifact_id="doc_001",
            task_id="task_01",
            project_id="proj_01",
            type=ARTIFACT_DOCUMENT,
            name="Architecture Spec",
            content="Version 1 content",
            created_by="emp_rian",
        )
        self.assertEqual(art_v1.version, 1)

        art_v2 = art_v1.create_new_version("Version 2 revised content", updated_by="emp_budi")
        self.assertEqual(art_v2.version, 2)
        self.assertEqual(art_v2.created_by, "emp_budi")
        self.assertIn("version_history", art_v2.metadata)
        self.assertEqual(len(art_v2.metadata["version_history"]), 1)
        self.assertEqual(art_v2.metadata["version_history"][0]["version"], 1)

    def test_artifact_store(self):
        bus = EventBus()
        events = []
        bus.subscribe(lambda e: events.append(e))
        store = ArtifactStore(event_bus=bus)

        art = Artifact(artifact_id="art_1", task_id="t1", project_id="p1", name="Test Art")
        store.register_artifact(art)

        self.assertEqual(store.get_artifact("art_1").name, "Test Art")
        created_events = [e for e in events if e.event_type == EVENT_ARTIFACT_CREATED]
        self.assertEqual(len(created_events), 1)


class TestHandoffSystem(unittest.TestCase):
    """Unit tests for Handoff lifecycle and context packaging."""

    def test_handoff_lifecycle(self):
        bus = EventBus()
        events = []
        bus.subscribe(lambda e: events.append(e))

        handoff = Handoff(
            handoff_id="h1",
            from_employee_id="emp_maya",
            to_employee_id="emp_citra",
            task_id="t_ui",
            project_id="p_marketing",
            artifact_ids=["art_copy_01"],
            message="Please build UI based on copy.",
            event_bus=bus,
        )

        self.assertEqual(handoff.status, HANDOFF_CREATED)
        self.assertTrue(handoff.receive())
        self.assertEqual(handoff.status, HANDOFF_RECEIVED)
        self.assertTrue(handoff.accept())
        self.assertEqual(handoff.status, HANDOFF_ACCEPTED)

        handoff_events = [e for e in events if e.event_type == EVENT_ARTIFACT_HANDOFF]
        self.assertEqual(len(handoff_events), 1)

    def test_handoff_rejection(self):
        handoff = Handoff(
            handoff_id="h2",
            from_employee_id="emp_maya",
            to_employee_id="emp_citra",
            task_id="t_ui",
            project_id="p1",
        )
        handoff.receive()
        self.assertTrue(handoff.reject("Missing CTA copy details"))
        self.assertEqual(handoff.status, "REJECTED")
        self.assertEqual(handoff.metadata["rejection_reason"], "Missing CTA copy details")


class TestPeerReviewSystem(unittest.TestCase):
    """Unit tests for Review model and ReviewRouter."""

    def test_review_approval_flow(self):
        bus = EventBus()
        events = []
        bus.subscribe(lambda e: events.append(e))

        review = Review(
            review_id="rev_01",
            artifact_id="art_backend",
            task_id="task_api",
            reviewer_employee_id="emp_ratna",
            author_employee_id="emp_eko",
            event_bus=bus,
        )
        self.assertEqual(review.status, REVIEW_PENDING)
        self.assertTrue(review.approve(score=1.0, feedback="Code meets all unit test standards."))
        self.assertEqual(review.status, REVIEW_APPROVED)

        completed_events = [e for e in events if e.event_type == EVENT_REVIEW_COMPLETED]
        self.assertEqual(len(completed_events), 1)

    def test_review_request_changes(self):
        review = Review(
            review_id="rev_02",
            artifact_id="art_copy",
            task_id="task_copy",
            reviewer_employee_id="emp_budi",
            author_employee_id="emp_laras",
        )
        self.assertTrue(review.request_changes("Needs stronger value prop", ["Add social proof bullets"]))
        self.assertEqual(review.status, REVIEW_CHANGES_REQUESTED)
        self.assertEqual(review.required_changes, ["Add social proof bullets"])

    def test_review_router_pairing(self):
        dev = Employee(employee_id="dev1", role="backend_developer")
        qa = Employee(employee_id="qa1", role="qa_engineer", capabilities=["automated_testing", "code_review"])
        copy = Employee(employee_id="copy1", role="copywriter")

        # Developer artifact should route to QA Engineer
        reviewer = ReviewRouter.select_reviewer(dev, [dev, qa, copy])
        self.assertEqual(reviewer.employee_id, "qa1")


class TestDiscussionSystem(unittest.TestCase):
    """Unit tests for Discussion and DiscussionMessage."""

    def test_structured_discussion(self):
        bus = EventBus()
        events = []
        bus.subscribe(lambda e: events.append(e))

        disc = Discussion(
            discussion_id="disc_01",
            project_id="proj_01",
            topic="Database Architecture Decision",
            event_bus=bus,
        )
        msg1 = disc.add_message(
            sender_employee_id="emp_eko",
            content="Should we use SQLite with WAL mode?",
            message_type=MSG_QUESTION,
        )
        self.assertEqual(msg1.message_type, MSG_QUESTION)
        self.assertEqual(len(disc.messages), 1)

        msg2 = disc.add_message(
            sender_employee_id="emp_rian",
            content="Yes, SQLite with WAL mode provides robust concurrency.",
            message_type=MSG_DECISION,
        )
        self.assertEqual(msg2.message_type, MSG_DECISION)
        self.assertEqual(len(disc.messages), 2)

        disc.resolve()
        self.assertEqual(disc.status, "RESOLVED")

        msg_events = [e for e in events if e.event_type == EVENT_DISCUSSION_MESSAGE]
        self.assertEqual(len(msg_events), 2)


class TestDelegationAndReassignment(unittest.TestCase):
    """Tests for DelegationEngine task execution and auto-reassignment on failure."""

    def setUp(self):
        self.org = Organization(name="Test Org")
        self.emp1 = Employee(
            employee_id="emp_1",
            name="Eko",
            role="developer",
            capabilities=["python"],
        )
        self.emp2 = Employee(
            employee_id="emp_2",
            name="Bagas",
            role="developer",
            capabilities=["python"],
        )
        self.org.register_employee(self.emp1)
        self.org.register_employee(self.emp2)

        self.bus = EventBus()
        self.events = []
        self.bus.subscribe(lambda e: self.events.append(e))

        self.factory = AgentFactory(self.org)
        self.artifact_store = ArtifactStore(event_bus=self.bus)

    def test_reassignment_when_first_employee_fails(self):
        mock_llm = MagicMock()
        # First call fails, second call succeeds
        mock_agent_instance = MagicMock()
        mock_res_fail = MagicMock(success=False, error="Simulated agent crash")
        mock_res_success = MagicMock(success=True, output="Resolved by second agent", error=None)

        task = WorkTask(
            task_id="t_code",
            project_id="p_test",
            title="Write Code",
            preferred_role="developer",
            required_capabilities=["python"],
        )

        engine = DelegationEngine(
            org=self.org,
            factory=self.factory,
            llm=mock_llm,
            db=MagicMock(),
            artifact_store=self.artifact_store,
            event_bus=self.bus,
        )

        # Mock factory create_agent to return fail first, then success
        call_count = [0]
        def mock_create(*args, **kwargs):
            call_count[0] += 1
            agent = MagicMock()
            if call_count[0] == 1:
                agent.run.return_value = mock_res_fail
            else:
                agent.run.return_value = mock_res_success
            return agent

        self.factory.create_agent = mock_create

        res = engine.execute_task(
            task=task,
            team_candidates=[self.emp1, self.emp2],
            output_dir="/tmp",
            enable_review=False,
        )

        self.assertTrue(res["success"])
        reassigned_events = [e for e in self.events if e.event_type == EVENT_EMPLOYEE_REASSIGNED]
        self.assertIn(reassigned_events[0].payload["previous_employee_id"], ["emp_1", "emp_2"])
        self.assertNotEqual(reassigned_events[0].payload["previous_employee_id"], res["employee_id"])


class TestEndToEndCollaborationSimulation(unittest.TestCase):
    """End-to-end integration simulation of Phase 5 Collaborative Workflow.
    Simulates: 'Create SaaS Landing Page' with >= 6 distinct Indonesian employees.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = f"{self.temp_dir}/tasks.db"
        self.bus = EventBus()
        self.events = []
        self.bus.subscribe(lambda e: self.events.append(e))
        self.db = Database(self.db_path, event_bus=self.bus)

        # Build Organization with 6+ distinct Indonesian employees across roles
        self.org = Organization(name="Aether Office Indonesia")

        r_pm = Role("product_manager", "Product Manager", "product", capabilities=["task_breakdown", "scoping"])
        r_copy = Role("copywriter", "Copywriter", "marketing", capabilities=["copywriting", "messaging"])
        r_front = Role("frontend_developer", "Frontend Developer", "engineering", capabilities=["react", "typescript", "tailwind"])
        r_back = Role("backend_developer", "Backend Developer", "engineering", capabilities=["python", "fastapi", "sqlite"])
        r_seo = Role("seo_specialist", "SEO Specialist", "marketing", capabilities=["seo", "keyword_research"])
        r_qa = Role("qa_engineer", "QA Engineer", "engineering", capabilities=["automated_testing", "code_review"])

        for r in [r_pm, r_copy, r_front, r_back, r_seo, r_qa]:
            self.org.register_role(r)

        # 6 Indonesian Employees
        self.e_panji = self.org.hire("Panji Nugroho", "product_manager", capabilities=["task_breakdown", "scoping"])
        self.e_maya = self.org.hire("Maya Anggraini", "copywriter", capabilities=["copywriting", "messaging"])
        self.e_citra = self.org.hire("Citra Dewi", "frontend_developer", capabilities=["react", "typescript", "tailwind"])
        self.e_bagas = self.org.hire("Bagas Aditya", "backend_developer", capabilities=["python", "fastapi", "sqlite"])
        self.e_surya = self.org.hire("Surya Pratama", "seo_specialist", capabilities=["seo", "keyword_research"])
        self.e_ratna = self.org.hire("Ratna Sari", "qa_engineer", capabilities=["automated_testing", "code_review"])

        self.db.sync_organization_to_db(self.org)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_saas_landing_page_simulation(self):
        """Execute full SaaS landing page workflow without hardcoded employee assignments."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "Deliverable successfully produced with all requirements met."

        orchestrator = WorkOrchestrator(
            project_id="proj_saas_launch",
            org=self.org,
            db=self.db,
            llm=mock_llm,
            output_dir=f"{self.temp_dir}/output",
            event_bus=self.bus,
        )

        brief = (
            "Create modern SaaS landing page for an AI accounting tool. "
            "Requires research, landing copy, frontend UI design, backend lead API, SEO tags, and QA review."
        )

        result = orchestrator.run_workflow(
            brief=brief,
            team_name="Tim Peluncuran SaaS",
            enable_reviews=True,
        )

        # 1. Verify Workflow Succeeded
        self.assertTrue(result["success"])
        self.assertEqual(result["workflow_state"], WORKFLOW_PROJECT_COMPLETE)

        # 2. Verify Dynamic Team Formation
        team = result["team"]
        self.assertIsNotNone(team)
        self.assertEqual(team["name"], "Tim Peluncuran SaaS")
        # Team must have pulled candidates covering required roles (PM, copy, front, back, seo, qa)
        self.assertTrue(len(team["employee_ids"]) >= 6)
        self.assertEqual(team["status"], "completed")

        # 3. Verify Tasks Execution
        tasks = result["tasks"]
        self.assertEqual(len(tasks), 6)
        for t in tasks:
            self.assertEqual(t["status"], TASK_COMPLETED)
            self.assertIsNotNone(t["assigned_employee_id"])
            self.assertTrue(len(t["artifacts"]) >= 1)

        # 4. Verify Multiple Distinct Employees Participated
        assigned_employees = {t["assigned_employee_id"] for t in tasks}
        self.assertTrue(len(assigned_employees) >= 4, f"Expected at least 4 unique employees, got {assigned_employees}")

        # 5. Verify Artifacts & Handoffs
        artifacts = result["artifacts"]
        self.assertEqual(len(artifacts), 6)
        stored_artifacts = self.db.list_artifacts(project_id="proj_saas_launch")
        self.assertEqual(len(stored_artifacts), 6)

        stored_handoffs = self.db.list_handoffs(project_id="proj_saas_launch")
        self.assertTrue(len(stored_handoffs) >= 4)

        # 6. Verify Peer Reviews Conducted
        stored_reviews = self.db.list_reviews(project_id="proj_saas_launch")
        self.assertTrue(len(stored_reviews) >= 4)
        for rev in stored_reviews:
            self.assertEqual(rev["status"], REVIEW_APPROVED)

        # 7. Verify Events Emitted to EventBus
        event_types = {e.event_type for e in self.events}
        expected_events = {
            EVENT_TEAM_CREATED,
            EVENT_TASK_DECOMPOSED,
            EVENT_TASK_ASSIGNED,
            EVENT_TASK_STARTED,
            EVENT_TASK_COMPLETED,
            EVENT_ARTIFACT_CREATED,
            EVENT_ARTIFACT_HANDOFF,
            EVENT_REVIEW_REQUESTED,
            EVENT_REVIEW_COMPLETED,
            EVENT_WORKFLOW_COMPLETED,
        }
        for exp in expected_events:
            self.assertIn(exp, event_types, f"Missing expected event: {exp}")

        # 8. Verify SQLite Persistence of Teams and WorkTasks
        db_teams = self.db.list_teams(project_id="proj_saas_launch")
        self.assertEqual(len(db_teams), 1)

        db_tasks = self.db.list_work_tasks(project_id="proj_saas_launch")
        self.assertEqual(len(db_tasks), 6)


if __name__ == "__main__":
    unittest.main()

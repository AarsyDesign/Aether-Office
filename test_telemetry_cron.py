"""Unit and integration tests for Telemetry & Cron Engine in Aether Office."""
import unittest
from telemetry import TelemetryManager, ROLE_TO_EMPLOYEE_HINT
from cron_engine import CronEngine
from aether_client import AetherMonitor

class TestTelemetryManager(unittest.TestCase):
    def setUp(self):
        self.mgr = TelemetryManager(db=None)

    def test_role_mapping(self):
        emp_id, name = self.mgr.resolve_employee(role="developer")
        self.assertEqual(emp_id, "developer_001")
        self.assertEqual(name, "Eko Prasetyo")

        emp_id, name = self.mgr.resolve_employee(role="qa")
        self.assertEqual(emp_id, "qa_001")
        self.assertEqual(name, "Ratna Sari")

        emp_id, name = self.mgr.resolve_employee(role="devops")
        self.assertEqual(emp_id, "planner_001")

        emp_id, name = self.mgr.resolve_employee(role="pm")
        self.assertEqual(emp_id, "pm_001")

    def test_record_and_query_activity(self):
        act = self.mgr.record_activity(
            source="hermes",
            role="developer",
            task_title="Refactor POS Checkout",
            status="WORKING",
            project="Kasir Test"
        )
        self.assertIsNotNone(act.activity_id)
        self.assertEqual(act.employee_id, "developer_001")

        active = self.mgr.get_active_activities()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["task_title"], "Refactor POS Checkout")

        # Complete activity
        self.mgr.update_activity(act.activity_id, status="COMPLETED", details="All POS checkout tests pass")
        self.assertEqual(len(self.mgr.get_active_activities()), 0)
        
        hist = self.mgr.get_history(10)
        self.assertGreaterEqual(len(hist), 1)
        self.assertEqual(hist[0]["status"], "COMPLETED")

class TestCronEngine(unittest.TestCase):
    def setUp(self):
        self.telemetry = TelemetryManager(db=None)
        self.engine = CronEngine(telemetry_manager=self.telemetry)

    def test_default_jobs_exist(self):
        jobs = self.engine.list_jobs()
        self.assertGreaterEqual(len(jobs), 3)
        job_ids = [j["job_id"] for j in jobs]
        self.assertIn("cron_git_audit", job_ids)
        self.assertIn("cron_db_health", job_ids)

    def test_run_job_now(self):
        job_dict = self.engine.run_job_now("cron_git_audit")
        self.assertIsNotNone(job_dict)
        self.assertTrue(job_dict["last_output"].startswith("Git"))

    def test_toggle_job(self):
        job_dict = self.engine.toggle_job("cron_git_audit")
        self.assertFalse(job_dict["enabled"])
        job_dict = self.engine.toggle_job("cron_git_audit")
        self.assertTrue(job_dict["enabled"])

class TestAetherClientSDK(unittest.TestCase):
    def test_client_context_manager_offline_graceful(self):
        # Client targeting offline port should not throw errors or break user work
        client = AetherMonitor(base_url="http://127.0.0.1:9999", default_source="test_runner")
        with client.track(task="Self test", role="qa"):
            x = 1 + 1
            self.assertEqual(x, 2)

if __name__ == "__main__":
    unittest.main()

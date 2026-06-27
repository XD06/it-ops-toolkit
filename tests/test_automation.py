import unittest
from unittest.mock import patch

from it_ops_toolkit.automation import AutomationError, run_flush_dns_cache
from it_ops_toolkit.tasks import new_task_run


class AutomationTests(unittest.TestCase):
    def test_flush_dns_dry_run_returns_plan(self) -> None:
        task = new_task_run(task_type="automation")

        summary = run_flush_dns_cache(task=task, dry_run=True, confirm=False)

        self.assertEqual(summary["scenario"], "flush_dns")
        self.assertEqual(summary["risk_level"], "low_change")
        self.assertTrue(summary["dry_run"])
        self.assertFalse(summary["executed"])
        self.assertEqual(summary["result"]["status"], "planned")

    def test_flush_dns_requires_confirm_without_dry_run(self) -> None:
        task = new_task_run(task_type="automation")

        with self.assertRaises(AutomationError):
            run_flush_dns_cache(task=task, dry_run=False, confirm=False)

    def test_flush_dns_rejects_dry_run_and_confirm_together(self) -> None:
        task = new_task_run(task_type="automation")

        with self.assertRaises(AutomationError):
            run_flush_dns_cache(task=task, dry_run=True, confirm=True)

    def test_flush_dns_confirm_executes_adapter(self) -> None:
        task = new_task_run(task_type="automation")

        with patch(
            "it_ops_toolkit.automation.flush_dns_cache",
            return_value={
                "action": "flush_dns_cache",
                "target": "localhost",
                "status": "success",
                "dry_run": False,
                "executed": True,
                "return_code": 0,
                "duration_ms": 12,
                "error": None,
            },
        ) as adapter:
            summary = run_flush_dns_cache(task=task, dry_run=False, confirm=True)

        adapter.assert_called_once_with(dry_run=False, timeout_seconds=15)
        self.assertEqual(summary["title"], "本机 DNS 缓存已清理")
        self.assertTrue(summary["executed"])


if __name__ == "__main__":
    unittest.main()

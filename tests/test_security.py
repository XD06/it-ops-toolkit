import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig
from it_ops_toolkit.models import Asset
from it_ops_toolkit.security import run_security_check
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run


class SecurityTests(unittest.TestCase):
    def test_detects_risky_open_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            asset = Asset(
                id="asset-192-168-1-10",
                ip="192.168.1.10",
                open_ports=[3389],
                first_seen=now,
                last_seen=now,
            )
            task = new_task_run(task_type="security_check")
            store.save_asset(asset)
            store.save_task_run(task)

            findings = run_security_check(
                config=OpsConfig.model_validate(DEFAULT_CONFIG),
                task=task,
                store=store,
            )

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity.value, "high")


if __name__ == "__main__":
    unittest.main()


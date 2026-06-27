import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig
from it_ops_toolkit.models import Asset, ProbeResult, ProbeStatus, Target
from it_ops_toolkit.security import _find_certificate_risks, run_security_check
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

    def test_detects_expiring_certificate_result(self) -> None:
        task = new_task_run(task_type="security_check")
        result = ProbeResult(
            id="probe-tls-cert-example-com-443",
            task_id=task.id,
            probe_type="tls_cert",
            target=Target(type="service", value="example.com:443"),
            status=ProbeStatus.success,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            observations={"days_remaining": 7},
        )

        findings = _find_certificate_risks(
            task=task,
            result=result,
            warning_days=30,
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity.value, "medium")
        self.assertEqual(findings[0].title, "TLS 证书即将过期")


if __name__ == "__main__":
    unittest.main()

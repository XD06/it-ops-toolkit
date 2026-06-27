import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig
from it_ops_toolkit.health_matrix import HealthMatrixError, run_health_tcp_matrix
from it_ops_toolkit.models import ProbeResult, ProbeStatus, Target
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run


class HealthMatrixTests(unittest.TestCase):
    def test_run_health_tcp_matrix_reads_csv_and_records_results(self) -> None:
        config = OpsConfig.model_validate(DEFAULT_CONFIG)
        now = datetime.now(UTC)

        def fake_check_tcp_port(
            *,
            task_id: str,
            target: str,
            port: int,
            timeout_ms: int,
        ) -> ProbeResult:
            return ProbeResult(
                id=f"probe-tcp-{target}-{port}",
                task_id=task_id,
                probe_type="tcp",
                target=Target(type="ip", value=target),
                status=ProbeStatus.success if target == "192.168.1.10" else ProbeStatus.failed,
                started_at=now,
                ended_at=now,
                observations={"port": port, "open": target == "192.168.1.10"},
            )

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text(
                "name,host,port\nprinter,192.168.1.10,9100\nnas,192.168.1.20,445\n",
                encoding="utf-8",
            )
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="health_matrix")

            with patch("it_ops_toolkit.health_matrix.check_tcp_port", fake_check_tcp_port):
                summary = run_health_tcp_matrix(
                    config=config,
                    task=task,
                    store=store,
                    csv_path=csv_path,
                )

            self.assertEqual(summary["target_count"], 2)
            self.assertEqual(summary["success_count"], 1)
            self.assertEqual(summary["failed_count"], 1)
            self.assertEqual(summary["entries"][0]["name"], "printer")
            self.assertEqual(len(store.list_probe_results_for_task(task.id)), 2)

    def test_run_health_tcp_matrix_requires_host_and_port_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text("name,host\nprinter,192.168.1.10\n", encoding="utf-8")

            with self.assertRaises(HealthMatrixError):
                run_health_tcp_matrix(
                    config=OpsConfig.model_validate(DEFAULT_CONFIG),
                    task=new_task_run(task_type="health_matrix"),
                    store=SQLiteStore(Path(tmp) / "ops.sqlite"),
                    csv_path=csv_path,
                )


if __name__ == "__main__":
    unittest.main()

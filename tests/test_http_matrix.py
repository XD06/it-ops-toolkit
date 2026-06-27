import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig
from it_ops_toolkit.health_matrix_http import (
    HealthHttpMatrixError,
    run_health_http_matrix,
)
from it_ops_toolkit.models import ProbeResult, ProbeStatus, Target
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run


class HealthHttpMatrixTests(unittest.TestCase):
    def test_run_health_http_matrix_reads_csv_and_records_results(self) -> None:
        config = OpsConfig.model_validate(DEFAULT_CONFIG)
        now = datetime.now(UTC)

        def fake_check_http_url(
            *,
            task_id: str,
            url: str,
            timeout_ms: int,
            method: str = "GET",
        ) -> ProbeResult:
            return ProbeResult(
                id=f"probe-http-{url}",
                task_id=task_id,
                probe_type="http",
                target=Target(type="url", value=url),
                status=ProbeStatus.success if url.startswith("https://ok") else ProbeStatus.failed,
                started_at=now,
                ended_at=now,
                observations={"url": url, "method": method, "ok": url.startswith("https://ok")},
            )

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text(
                "name,url,method\nportal,https://ok.example.local,HEAD\nlegacy,http://fail.example.local,GET\n",
                encoding="utf-8",
            )
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="health_matrix")

            with patch("it_ops_toolkit.health_matrix_http.check_http_url", fake_check_http_url):
                summary = run_health_http_matrix(
                    config=config,
                    task=task,
                    store=store,
                    csv_path=csv_path,
                )

            self.assertEqual(summary["target_count"], 2)
            self.assertEqual(summary["success_count"], 1)
            self.assertEqual(summary["failed_count"], 1)
            self.assertEqual(summary["entries"][0]["name"], "portal")
            self.assertEqual(summary["entries"][0]["method"], "HEAD")
            self.assertEqual(len(store.list_probe_results_for_task(task.id)), 2)

    def test_run_health_http_matrix_requires_url_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text("name,host\nportal,example.local\n", encoding="utf-8")

            with self.assertRaises(HealthHttpMatrixError):
                run_health_http_matrix(
                    config=OpsConfig.model_validate(DEFAULT_CONFIG),
                    task=new_task_run(task_type="health_matrix"),
                    store=SQLiteStore(Path(tmp) / "ops.sqlite"),
                    csv_path=csv_path,
                )

    def test_run_health_http_matrix_rejects_non_read_only_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text("name,url,method\nportal,https://example.local,POST\n", encoding="utf-8")

            with self.assertRaises(HealthHttpMatrixError):
                run_health_http_matrix(
                    config=OpsConfig.model_validate(DEFAULT_CONFIG),
                    task=new_task_run(task_type="health_matrix"),
                    store=SQLiteStore(Path(tmp) / "ops.sqlite"),
                    csv_path=csv_path,
                )


if __name__ == "__main__":
    unittest.main()

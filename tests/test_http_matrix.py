import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig
from it_ops_toolkit.health_matrix_http import (
    HealthHttpMatrixError,
    parse_expected_status,
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
            ok = url.startswith("https://ok")
            return ProbeResult(
                id=f"probe-http-{url}",
                task_id=task_id,
                probe_type="http",
                target=Target(type="url", value=url),
                status=ProbeStatus.success if ok else ProbeStatus.failed,
                started_at=now,
                ended_at=now,
                observations={
                    "url": url,
                    "method": method,
                    "status_code": 200 if ok else None,
                    "ok": ok,
                },
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
            self.assertEqual(summary["entries"][0]["http_status_code"], 200)
            self.assertEqual(len(store.list_probe_results_for_task(task.id)), 2)

    def test_run_health_http_matrix_checks_expected_status(self) -> None:
        config = OpsConfig.model_validate(DEFAULT_CONFIG)
        now = datetime.now(UTC)

        def fake_check_http_url(
            *,
            task_id: str,
            url: str,
            timeout_ms: int,
            method: str = "GET",
        ) -> ProbeResult:
            if url.endswith("/portal"):
                status_code = 200
                status = ProbeStatus.success
            elif url.endswith("/redirect"):
                status_code = 301
                status = ProbeStatus.success
            else:
                status_code = 503
                status = ProbeStatus.failed
            return ProbeResult(
                id=f"probe-http-{url}",
                task_id=task_id,
                probe_type="http",
                target=Target(type="url", value=url),
                status=status,
                started_at=now,
                ended_at=now,
                observations={
                    "url": url,
                    "method": method,
                    "status_code": status_code,
                    "ok": 200 <= status_code < 400,
                },
            )

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text(
                "name,url,method,expected_status,owner,description\n"
                "portal,https://ok.example.local/portal,GET,200,alice,门户\n"
                "redirect,https://ok.example.local/redirect,GET,301-302,bob,跳转\n"
                "down,https://fail.example.local/down,GET,200-299,carol,故障\n",
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

            entries = summary["entries"]
            self.assertEqual(len(entries), 3)

            self.assertEqual(entries[0]["http_status_code"], 200)
            self.assertTrue(entries[0]["status_match"])
            self.assertEqual(entries[0]["owner"], "alice")
            self.assertEqual(entries[0]["description"], "门户")

            self.assertEqual(entries[1]["http_status_code"], 301)
            self.assertTrue(entries[1]["status_match"])

            self.assertEqual(entries[2]["http_status_code"], 503)
            self.assertFalse(entries[2]["status_match"])

            self.assertEqual(summary["mismatch_count"], 1)

    def test_run_health_http_matrix_without_expected_status_skips_match(self) -> None:
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
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={
                    "url": url,
                    "method": method,
                    "status_code": 200,
                    "ok": True,
                },
            )

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text(
                "name,url\nportal,https://ok.example.local\n",
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

            self.assertEqual(summary["mismatch_count"], 0)
            self.assertEqual(summary["entries"][0]["expected_status"], "")
            self.assertTrue(summary["entries"][0]["status_match"])

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

    def test_run_health_http_matrix_rejects_invalid_expected_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "targets.csv"
            csv_path.write_text(
                "name,url,expected_status\nportal,https://example.local,abc\n",
                encoding="utf-8",
            )

            with self.assertRaises(HealthHttpMatrixError):
                run_health_http_matrix(
                    config=OpsConfig.model_validate(DEFAULT_CONFIG),
                    task=new_task_run(task_type="health_matrix"),
                    store=SQLiteStore(Path(tmp) / "ops.sqlite"),
                    csv_path=csv_path,
                )


class ParseExpectedStatusTests(unittest.TestCase):
    def test_single_code(self) -> None:
        self.assertEqual(parse_expected_status("200"), [(200, 200)])

    def test_range(self) -> None:
        self.assertEqual(parse_expected_status("200-299"), [(200, 299)])

    def test_multiple_values(self) -> None:
        self.assertEqual(
            parse_expected_status("200,301,302"),
            [(200, 200), (301, 301), (302, 302)],
        )

    def test_mixed_range_and_code(self) -> None:
        self.assertEqual(
            parse_expected_status("200-299,404"),
            [(200, 299), (404, 404)],
        )

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(parse_expected_status(""))

    def test_invalid_value_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_expected_status("abc")

    def test_invalid_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_expected_status("300-200")


if __name__ == "__main__":
    unittest.main()

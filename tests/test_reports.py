import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.models import Asset, ProbeResult, ProbeStatus, Target, TaskStatus
from it_ops_toolkit.reports import generate_report
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import finish_task_run, new_task_run


class ReportTests(unittest.TestCase):
    def test_generate_markdown_report_for_asset_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="asset_scan")
            now = datetime.now(UTC)
            asset = Asset(
                id="asset-127-0-0-1",
                ip="127.0.0.1",
                open_ports=[445],
                first_seen=now,
                last_seen=now,
            )
            result = ProbeResult(
                id="probe-ping-127.0.0.1",
                task_id=task.id,
                probe_type="ping",
                target=Target(type="ip", value="127.0.0.1"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"reachable": True},
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": [asset.ip],
                    "result_refs": [result.id],
                }
            )

            store.save_task_run(task)
            store.save_asset(asset)
            store.save_probe_result(result)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )

            report_path = Path(report.path)
            self.assertTrue(report_path.exists())
            self.assertIn("资产结果", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


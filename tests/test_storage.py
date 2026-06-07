import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.models import Asset, ProbeResult, ProbeStatus, Target, TaskStatus
from it_ops_toolkit.storage import SQLiteStore, TaskRecordNotFound
from it_ops_toolkit.tasks import new_task_run


class StorageTests(unittest.TestCase):
    def test_save_list_and_get_task_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="health_check", status=TaskStatus.success)

            store.save_task_run(task)

            tasks = store.list_task_runs()
            loaded = store.get_task_run(task.id)

            self.assertEqual(len(tasks), 1)
            self.assertEqual(loaded.id, task.id)
            self.assertEqual(loaded.task_type, "health_check")
            self.assertEqual(loaded.status, TaskStatus.success)

    def test_missing_task_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")

            with self.assertRaises(TaskRecordNotFound):
                store.get_task_run("task-missing")

    def test_save_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            asset = Asset(
                id="asset-192-168-1-10",
                ip="192.168.1.10",
                open_ports=[80, 443],
                first_seen=now,
                last_seen=now,
            )

            store.save_asset(asset)
            assets = store.list_assets()

            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].ip, "192.168.1.10")
            self.assertEqual(assets[0].open_ports, [80, 443])

    def test_save_probe_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            result = ProbeResult(
                id="probe-ping-192.168.1.10",
                task_id="task-1",
                probe_type="ping",
                target=Target(type="ip", value="192.168.1.10"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"reachable": True},
                evidence={"summary": "ok"},
            )

            store.save_probe_result(result)
            results = store.list_probe_results_for_task("task-1")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, ProbeStatus.success)
            self.assertEqual(results[0].observations["reachable"], True)


if __name__ == "__main__":
    unittest.main()

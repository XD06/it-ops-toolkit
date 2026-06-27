import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.models import (
    Asset,
    LocalInterface,
    LocalSnapshot,
    ProbeResult,
    ProbeStatus,
    Target,
    TaskStatus,
)
from it_ops_toolkit.storage import SQLiteStore, TaskRecordNotFound
from it_ops_toolkit.tasks import new_task_run


class StorageTests(unittest.TestCase):
    def test_save_list_and_get_task_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="health_check", status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "summary": {
                        "scenario": "printer",
                        "scenario_label": "打印机可达性诊断",
                        "title": "打印机可达，但常见打印端口不可达",
                        "ports": [9100, 515, 631],
                    }
                }
            )

            store.save_task_run(task)

            tasks = store.list_task_runs()
            loaded = store.get_task_run(task.id)

            self.assertEqual(len(tasks), 1)
            self.assertEqual(loaded.id, task.id)
            self.assertEqual(loaded.task_type, "health_check")
            self.assertEqual(loaded.status, TaskStatus.success)
            self.assertEqual(loaded.summary["scenario"], "printer")
            self.assertEqual(loaded.summary["ports"], [9100, 515, 631])

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
                hostname="pc-10",
                asset_type="workstation",
                open_ports=[80, 443],
                first_seen=now,
                last_seen=now,
                owner="Alice",
                description="财务电脑",
                tags=["finance", "windows"],
            )

            store.save_asset(asset)
            assets = store.list_assets()

            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].ip, "192.168.1.10")
            self.assertEqual(assets[0].open_ports, [80, 443])
            self.assertEqual(assets[0].owner, "Alice")
            self.assertEqual(assets[0].description, "财务电脑")
            self.assertEqual(assets[0].tags, ["finance", "windows"])

    def test_save_asset_preserves_existing_notes_when_scan_updates_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            store.save_asset(
                Asset(
                    id="asset-192-168-1-10",
                    ip="192.168.1.10",
                    open_ports=[80],
                    first_seen=now,
                    last_seen=now,
                    owner="Alice",
                    description="财务电脑",
                    tags=["finance"],
                )
            )

            store.save_asset(
                Asset(
                    id="asset-192-168-1-10",
                    ip="192.168.1.10",
                    open_ports=[80, 443],
                    first_seen=now,
                    last_seen=now,
                    source="scan_profile:office_lan",
                )
            )

            asset = store.get_asset_by_ip("192.168.1.10")
            self.assertIsNotNone(asset)
            assert asset is not None
            self.assertEqual(asset.open_ports, [80, 443])
            self.assertEqual(asset.owner, "Alice")
            self.assertEqual(asset.description, "财务电脑")
            self.assertEqual(asset.tags, ["finance"])

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

    def test_save_tls_certificate_probe_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            result = ProbeResult(
                id="probe-tls-cert-example-com-443",
                task_id="task-1",
                probe_type="tls_cert",
                target=Target(type="service", value="example.com:443"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"days_remaining": 90},
            )

            store.save_probe_result(result)
            results = store.list_probe_results_for_task("task-1")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].probe_type, "tls_cert")
            self.assertEqual(results[0].observations["days_remaining"], 90)

    def test_save_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="ops_collect")
            now = datetime.now(UTC)
            snapshot = LocalSnapshot(
                id="local-1",
                task_id=task.id,
                collected_at=now,
                hostname="pc-01",
                os_name="Windows-11",
                platform="Windows",
                interfaces=[
                    LocalInterface(
                        name="Ethernet",
                        status="Up",
                        ipv4_addresses=["192.168.1.20"],
                        default_gateways=["192.168.1.1"],
                        dns_servers=["192.168.1.1"],
                    )
                ],
                default_routes=[{"next_hop": "192.168.1.1"}],
                dns_servers=["192.168.1.1"],
            )

            store.save_local_snapshot(snapshot)
            loaded = store.list_local_snapshots_for_task(task.id)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].hostname, "pc-01")
            self.assertEqual(loaded[0].interfaces[0].name, "Ethernet")


if __name__ == "__main__":
    unittest.main()

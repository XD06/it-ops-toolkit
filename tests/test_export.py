import tempfile
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig
from it_ops_toolkit.export import export_bundle
from it_ops_toolkit.models import (
    Asset,
    LocalInterface,
    LocalSnapshot,
    ProbeResult,
    ProbeStatus,
    Target,
    TaskStatus,
)
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import finish_task_run, new_task_run


class ExportTests(unittest.TestCase):
    def test_export_bundle_contains_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            task = new_task_run(task_type="health_check")
            task = finish_task_run(task, status=TaskStatus.success)
            result = ProbeResult(
                id="probe-dns-localhost",
                task_id=task.id,
                probe_type="dns",
                target=Target(type="hostname", value="localhost"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"addresses": ["127.0.0.1"]},
            )
            asset = Asset(
                id="asset-127-0-0-1",
                ip="127.0.0.1",
                first_seen=now,
                last_seen=now,
            )
            snapshot = LocalSnapshot(
                id="local-1",
                task_id=task.id,
                collected_at=now,
                hostname="pc-01",
                os_name="Windows-11",
                platform="Windows",
                interfaces=[
                    LocalInterface(name="Ethernet", ipv4_addresses=["127.0.0.1"])
                ],
            )
            store.save_task_run(task)
            store.save_probe_result(result)
            store.save_asset(asset)
            store.save_local_snapshot(snapshot)

            bundle = export_bundle(
                config=OpsConfig.model_validate(DEFAULT_CONFIG),
                store=store,
                output_path=Path(tmp) / "bundle.zip",
            )

            self.assertTrue(bundle.exists())
            with zipfile.ZipFile(bundle) as archive:
                names = set(archive.namelist())

            self.assertIn("summary.md", names)
            self.assertIn("config-summary.json", names)
            self.assertIn("tasks.json", names)
            self.assertIn("assets.json", names)
            self.assertIn("findings.json", names)
            self.assertIn("local-snapshots.json", names)
            self.assertIn("probe-results.json", names)


if __name__ == "__main__":
    unittest.main()

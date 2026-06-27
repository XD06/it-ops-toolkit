import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from it_ops_toolkit.assets import (
    AssetExportError,
    AssetImportError,
    AssetScanError,
    export_assets,
    expand_scan_hosts,
    import_asset_notes,
    run_asset_diff,
    run_asset_scan,
)
from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig, ScanProfile
from it_ops_toolkit.models import Asset, ProbeResult, ProbeStatus, Target
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run


class AssetScanTests(unittest.TestCase):
    def test_expand_scan_hosts(self) -> None:
        profile = ScanProfile(subnets=["192.168.1.0/30"])

        hosts = expand_scan_hosts(profile)

        self.assertEqual(hosts, ["192.168.1.1", "192.168.1.2"])

    def test_invalid_subnet_raises(self) -> None:
        profile = ScanProfile(subnets=["not-a-subnet"])

        with self.assertRaises(AssetScanError):
            expand_scan_hosts(profile)

    def test_tcp_without_ping_discovers_tcp_open_host(self) -> None:
        config = OpsConfig.model_validate(
            {
                **DEFAULT_CONFIG,
                "scan_profiles": {
                    "test_lan": {
                        "subnets": ["192.168.50.0/30"],
                        "ping": {"enabled": True, "timeout_ms": 1, "retries": 0},
                        "tcp_ports": [445],
                    }
                },
            }
        )

        def fake_ping_host(
            *,
            task_id: str,
            target: str,
            timeout_ms: int,
            retries: int,
        ) -> ProbeResult:
            now = datetime.now(UTC)
            return ProbeResult(
                id=f"probe-ping-{target}",
                task_id=task_id,
                probe_type="ping",
                target=Target(type="ip", value=target),
                status=ProbeStatus.failed,
                started_at=now,
                ended_at=now,
                observations={"reachable": False},
            )

        def fake_check_tcp_port(
            *,
            task_id: str,
            target: str,
            port: int,
            timeout_ms: int,
        ) -> ProbeResult:
            now = datetime.now(UTC)
            is_open = target == "192.168.50.1"
            return ProbeResult(
                id=f"probe-tcp-{target}-{port}",
                task_id=task_id,
                probe_type="tcp",
                target=Target(type="ip", value=target),
                status=ProbeStatus.success if is_open else ProbeStatus.failed,
                started_at=now,
                ended_at=now,
                observations={"port": port, "open": is_open},
            )

        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="asset_scan")
            with patch("it_ops_toolkit.assets.ping_host", fake_ping_host), patch(
                "it_ops_toolkit.assets.check_tcp_port",
                fake_check_tcp_port,
            ), patch("it_ops_toolkit.assets._safe_reverse_dns", return_value=None):
                assets, results = run_asset_scan(
                    config=config,
                    profile_name="test_lan",
                    task=task,
                    store=store,
                    tcp_without_ping=True,
                )

            self.assertEqual([asset.ip for asset in assets], ["192.168.50.1"])
            self.assertEqual(assets[0].open_ports, [445])
            self.assertEqual(len(results), 4)
            self.assertEqual(store.list_assets()[0].ip, "192.168.50.1")

    def test_default_scan_does_not_tcp_scan_ping_failed_hosts(self) -> None:
        config = OpsConfig.model_validate(
            {
                **DEFAULT_CONFIG,
                "scan_profiles": {
                    "test_lan": {
                        "subnets": ["192.168.60.0/30"],
                        "ping": {"enabled": True, "timeout_ms": 1, "retries": 0},
                        "tcp_ports": [445],
                    }
                },
            }
        )

        def fake_ping_host(
            *,
            task_id: str,
            target: str,
            timeout_ms: int,
            retries: int,
        ) -> ProbeResult:
            now = datetime.now(UTC)
            return ProbeResult(
                id=f"probe-ping-{target}",
                task_id=task_id,
                probe_type="ping",
                target=Target(type="ip", value=target),
                status=ProbeStatus.failed,
                started_at=now,
                ended_at=now,
                observations={"reachable": False},
            )

        def fail_if_called(*args: object, **kwargs: object) -> ProbeResult:
            raise AssertionError("TCP scan should not run for ping-failed hosts")

        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="asset_scan")
            with patch("it_ops_toolkit.assets.ping_host", fake_ping_host), patch(
                "it_ops_toolkit.assets.check_tcp_port",
                fail_if_called,
            ):
                assets, results = run_asset_scan(
                    config=config,
                    profile_name="test_lan",
                    task=task,
                    store=store,
                )

            self.assertEqual(assets, [])
            self.assertEqual(len(results), 2)

    def test_asset_diff_detects_new_missing_and_new_ports(self) -> None:
        config = OpsConfig.model_validate(
            {
                **DEFAULT_CONFIG,
                "scan_profiles": {
                    "test_lan": {
                        "subnets": ["192.168.70.0/30"],
                        "ping": {"enabled": True, "timeout_ms": 1, "retries": 0},
                        "tcp_ports": [80, 443],
                    }
                },
            }
        )
        now = datetime.now(UTC)

        def fake_ping_host(
            *,
            task_id: str,
            target: str,
            timeout_ms: int,
            retries: int,
        ) -> ProbeResult:
            return ProbeResult(
                id=f"probe-ping-{target}",
                task_id=task_id,
                probe_type="ping",
                target=Target(type="ip", value=target),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"reachable": target == "192.168.70.1"},
            )

        def fake_check_tcp_port(
            *,
            task_id: str,
            target: str,
            port: int,
            timeout_ms: int,
        ) -> ProbeResult:
            is_open = target == "192.168.70.1"
            return ProbeResult(
                id=f"probe-tcp-{target}-{port}",
                task_id=task_id,
                probe_type="tcp",
                target=Target(type="ip", value=target),
                status=ProbeStatus.success if is_open else ProbeStatus.failed,
                started_at=now,
                ended_at=now,
                observations={"port": port, "open": is_open},
            )

        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.save_asset(
                Asset(
                    id="asset-192-168-70-1",
                    ip="192.168.70.1",
                    open_ports=[80],
                    first_seen=now,
                    last_seen=now,
                    source="scan_profile:test_lan",
                )
            )
            store.save_asset(
                Asset(
                    id="asset-192-168-70-2",
                    ip="192.168.70.2",
                    open_ports=[22],
                    first_seen=now,
                    last_seen=now,
                    source="scan_profile:test_lan",
                )
            )
            task = new_task_run(task_type="asset_diff")

            with patch("it_ops_toolkit.assets.ping_host", fake_ping_host), patch(
                "it_ops_toolkit.assets.check_tcp_port",
                fake_check_tcp_port,
            ), patch("it_ops_toolkit.assets._safe_reverse_dns", return_value=None):
                assets, results, findings, summary = run_asset_diff(
                    config=config,
                    profile_name="test_lan",
                    task=task,
                    store=store,
                )

            self.assertEqual([asset.ip for asset in assets], ["192.168.70.1"])
            self.assertEqual(len(results), 4)
            self.assertEqual(summary["new_assets"], [])
            self.assertEqual(summary["disappeared_assets"], ["192.168.70.2"])
            self.assertEqual(summary["newly_open_ports"], {"192.168.70.1": [443]})
            self.assertEqual(summary["newly_open_port_count"], 1)
            self.assertEqual([finding.title for finding in findings], [
                "发现历史资产未出现在本次扫描",
                "发现新增开放端口",
            ])
            self.assertEqual(len(store.list_findings_for_task(task.id)), 2)

    def test_asset_diff_detects_new_asset(self) -> None:
        config = OpsConfig.model_validate(
            {
                **DEFAULT_CONFIG,
                "scan_profiles": {
                    "test_lan": {
                        "subnets": ["192.168.80.0/30"],
                        "ping": {"enabled": True, "timeout_ms": 1, "retries": 0},
                        "tcp_ports": [],
                    }
                },
            }
        )
        now = datetime.now(UTC)

        def fake_ping_host(
            *,
            task_id: str,
            target: str,
            timeout_ms: int,
            retries: int,
        ) -> ProbeResult:
            return ProbeResult(
                id=f"probe-ping-{target}",
                task_id=task_id,
                probe_type="ping",
                target=Target(type="ip", value=target),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"reachable": target == "192.168.80.1"},
            )

        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="asset_diff")

            with patch("it_ops_toolkit.assets.ping_host", fake_ping_host), patch(
                "it_ops_toolkit.assets._safe_reverse_dns", return_value=None
            ):
                _, _, findings, summary = run_asset_diff(
                    config=config,
                    profile_name="test_lan",
                    task=task,
                    store=store,
                )

            self.assertEqual(summary["new_assets"], ["192.168.80.1"])
            self.assertEqual(summary["new_asset_count"], 1)
            self.assertEqual(findings[0].title, "发现新增资产")

    def test_import_asset_notes_updates_existing_assets_and_reports_skips(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            store.save_asset(
                Asset(
                    id="asset-192-168-1-10",
                    ip="192.168.1.10",
                    hostname="old-name",
                    open_ports=[80],
                    first_seen=now,
                    last_seen=now,
                )
            )
            csv_path = Path(tmp) / "asset-notes.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ip,hostname,owner,asset_type,description,tags",
                        "192.168.1.10,pc-10,Alice,workstation,财务电脑,\"finance,windows\"",
                        "192.168.1.99,unknown,Bob,printer,不存在资产,printer",
                        ",missing-ip,Bob,printer,缺少 IP,printer",
                    ]
                ),
                encoding="utf-8",
            )

            summary = import_asset_notes(store=store, csv_path=csv_path)
            asset = store.get_asset_by_ip("192.168.1.10")

            self.assertIsNotNone(asset)
            assert asset is not None
            self.assertEqual(asset.hostname, "pc-10")
            self.assertEqual(asset.owner, "Alice")
            self.assertEqual(asset.asset_type, "workstation")
            self.assertEqual(asset.description, "财务电脑")
            self.assertEqual(asset.tags, ["finance", "windows"])
            self.assertEqual(asset.open_ports, [80])
            self.assertEqual(summary["updated_count"], 1)
            self.assertEqual(summary["skipped_count"], 1)
            self.assertEqual(summary["error_count"], 1)
            self.assertEqual(summary["skipped_rows"][0]["reason"], "asset_not_found")
            self.assertEqual(summary["error_rows"][0]["reason"], "missing_ip")

    def test_import_asset_notes_requires_ip_column(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            csv_path = Path(tmp) / "asset-notes.csv"
            csv_path.write_text("hostname,owner\npc-10,Alice\n", encoding="utf-8")

            with self.assertRaises(AssetImportError):
                import_asset_notes(store=store, csv_path=csv_path)

    def test_export_assets_csv_and_json(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            now = datetime.now(UTC)
            store.save_asset(
                Asset(
                    id="asset-192-168-1-20",
                    ip="192.168.1.20",
                    hostname="pc-20",
                    open_ports=[445, 3389],
                    first_seen=now,
                    last_seen=now,
                    source="test",
                )
            )

            csv_path = export_assets(
                store=store,
                output_path=Path(tmp) / "assets.csv",
                export_format="csv",
            )
            json_path = export_assets(
                store=store,
                output_path=Path(tmp) / "assets.json",
                export_format="JSON",
            )

            csv_text = csv_path.read_text(encoding="utf-8-sig")
            json_payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertIn("ip,hostname", csv_text)
            self.assertIn("192.168.1.20", csv_text)
            self.assertEqual(json_payload[0]["ip"], "192.168.1.20")

    def test_export_assets_rejects_unsupported_format(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")

            with self.assertRaises(AssetExportError):
                export_assets(
                    store=store,
                    output_path=Path(tmp) / "assets.xlsx",
                    export_format="xlsx",
                )


if __name__ == "__main__":
    unittest.main()

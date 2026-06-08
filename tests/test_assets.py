import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from it_ops_toolkit.assets import AssetScanError, expand_scan_hosts, run_asset_scan
from it_ops_toolkit.config import DEFAULT_CONFIG, OpsConfig, ScanProfile
from it_ops_toolkit.models import ProbeResult, ProbeStatus, Target
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


if __name__ == "__main__":
    unittest.main()

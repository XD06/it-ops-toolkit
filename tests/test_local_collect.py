import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from it_ops_toolkit.local_collect import (
    CommandOutput,
    _parse_windows_network_json,
    _redact_proxy_value,
    collect_local_snapshot,
)
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run


WINDOWS_NETWORK_PAYLOAD = json.dumps(
    {
        "ip_configurations": [
            {
                "interface_alias": "Ethernet",
                "interface_description": "Intel Ethernet",
                "interface_index": 12,
                "net_adapter_status": "Up",
                "net_profile_name": "Office LAN",
                "ipv4_addresses": ["192.168.1.20"],
                "ipv6_addresses": ["fe80::1"],
                "ipv4_default_gateways": ["192.168.1.1"],
                "dns_servers": ["192.168.1.1", "8.8.8.8"],
            }
        ],
        "default_routes": [
            {
                "interface_alias": "Ethernet",
                "destination_prefix": "0.0.0.0/0",
                "next_hop": "192.168.1.1",
                "route_metric": 25,
                "interface_index": 12,
            }
        ],
        "dns_client_servers": [
            {
                "interface_alias": "Ethernet",
                "address_family": 2,
                "server_addresses": ["192.168.1.1", "8.8.8.8"],
            }
        ],
    }
)


class LocalCollectTests(unittest.TestCase):
    def test_parse_windows_network_json(self) -> None:
        interfaces, routes, dns_servers = _parse_windows_network_json(
            WINDOWS_NETWORK_PAYLOAD
        )

        self.assertEqual(len(interfaces), 1)
        self.assertEqual(interfaces[0].name, "Ethernet")
        self.assertEqual(interfaces[0].ipv4_addresses, ["192.168.1.20"])
        self.assertEqual(routes[0]["next_hop"], "192.168.1.1")
        self.assertEqual(dns_servers, ["192.168.1.1", "8.8.8.8"])

    def test_redact_proxy_credentials(self) -> None:
        redacted = _redact_proxy_value("http://user:secret@proxy.local:8080")

        self.assertEqual(redacted, "http://proxy.local:8080")

    def test_collect_local_snapshot_saves_windows_result(self) -> None:
        def fake_runner(args: list[str], timeout: int) -> CommandOutput:
            if args[0] == "netsh":
                return CommandOutput(args, 0, "Direct access (no proxy server).", "")
            return CommandOutput(args, 0, WINDOWS_NETWORK_PAYLOAD, "")

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="ops_collect")
            with patch(
                "it_ops_toolkit.local_collect.platform_module.system",
                return_value="Windows",
            ), patch.dict(
                os.environ,
                {"HTTP_PROXY": "http://user:secret@proxy.local:8080"},
                clear=True,
            ):
                snapshot = collect_local_snapshot(
                    task=task,
                    store=store,
                    command_runner=fake_runner,
                )

            loaded = store.list_local_snapshots_for_task(task.id)

            self.assertEqual(snapshot.hostname, loaded[0].hostname)
            self.assertEqual(loaded[0].interfaces[0].name, "Ethernet")
            self.assertEqual(loaded[0].dns_servers, ["192.168.1.1", "8.8.8.8"])
            self.assertEqual(
                loaded[0].proxy["environment"]["HTTP_PROXY"],
                "http://proxy.local:8080",
            )


if __name__ == "__main__":
    unittest.main()

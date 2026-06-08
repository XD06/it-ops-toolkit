import unittest

from it_ops_toolkit.health import _host_and_port_for_tcp, _host_for_network_check
from it_ops_toolkit.models import ProbeStatus
from it_ops_toolkit.probes import resolve_hostname


class HealthTests(unittest.TestCase):
    def test_host_for_network_check_extracts_url_hostname(self) -> None:
        self.assertEqual(
            _host_for_network_check("https://intranet.example.local/path"),
            "intranet.example.local",
        )

    def test_dns_probe_resolves_localhost(self) -> None:
        result = resolve_hostname(
            task_id="task-test",
            hostname="localhost",
            timeout_ms=1000,
        )

        self.assertEqual(result.status, ProbeStatus.success)
        self.assertTrue(result.observations["addresses"])

    def test_tcp_target_uses_configured_port(self) -> None:
        host, port = _host_and_port_for_tcp("192.168.1.10", 3389)

        self.assertEqual(host, "192.168.1.10")
        self.assertEqual(port, 3389)

    def test_tcp_target_infers_https_port(self) -> None:
        host, port = _host_and_port_for_tcp("https://intranet.example.local", None)

        self.assertEqual(host, "intranet.example.local")
        self.assertEqual(port, 443)


if __name__ == "__main__":
    unittest.main()

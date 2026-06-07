import unittest

from it_ops_toolkit.health import _host_for_network_check
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


if __name__ == "__main__":
    unittest.main()


import unittest

from typer.testing import CliRunner

from it_ops_toolkit.cli import app


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_diagnose_help_lists_dns_and_printer(self) -> None:
        result = self.runner.invoke(app, ["diagnose", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("dns", result.output)
        self.assertIn("printer", result.output)
        self.assertIn("slow-network", result.output)

    def test_dns_diagnosis_help_shows_readable_options(self) -> None:
        result = self.runner.invoke(app, ["diagnose", "dns", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--name", result.output)
        self.assertIn("--expected-ip", result.output)
        self.assertIn("--tcp-port", result.output)

    def test_slow_network_diagnosis_help_shows_target_options(self) -> None:
        result = self.runner.invoke(app, ["diagnose", "slow-network", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--external-ip", result.output)
        self.assertIn("--dns-name", result.output)
        self.assertIn("--http-url", result.output)

    def test_printer_diagnosis_help_shows_port_option(self) -> None:
        result = self.runner.invoke(app, ["diagnose", "printer", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--target", result.output)
        self.assertIn("--ports", result.output)
        self.assertIn("9100,515,631", result.output)

    def test_certificate_check_help_shows_target_and_warning_options(self) -> None:
        result = self.runner.invoke(app, ["security", "cert-check", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--target", result.output)
        self.assertIn("--warning-days", result.output)

    def test_asset_diff_help_shows_profile_and_tcp_without_ping(self) -> None:
        result = self.runner.invoke(app, ["asset", "diff", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--profile", result.output)
        self.assertIn("--tcp-without-ping", result.output)

    def test_asset_import_notes_help_shows_file_option(self) -> None:
        result = self.runner.invoke(app, ["asset", "import-notes", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--file", result.output)

    def test_flush_dns_help_shows_dry_run_and_confirm(self) -> None:
        result = self.runner.invoke(app, ["automate", "flush-dns", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--dry-run", result.output)
        self.assertIn("--confirm", result.output)

    def test_health_tcp_matrix_help_shows_file_option(self) -> None:
        result = self.runner.invoke(app, ["health", "tcp-matrix", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--file", result.output)

    def test_health_http_matrix_help_shows_file_option(self) -> None:
        result = self.runner.invoke(app, ["health", "http-matrix", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--file", result.output)


if __name__ == "__main__":
    unittest.main()

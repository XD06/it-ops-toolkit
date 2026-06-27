import unittest

from it_ops_toolkit.probes.dns import _parse_nslookup_output, _has_nslookup_error


class NslookupParseWindowsTests(unittest.TestCase):
    def test_parses_windows_success_output(self) -> None:
        output = (
            "Server:  dns.google\r\n"
            "Address:  8.8.8.8\r\n"
            "\r\n"
            "Name:    www.baidu.com\r\n"
            "Addresses:  110.242.68.4\r\n"
            "          110.242.68.3\r\n"
        )

        result = _parse_nslookup_output(output)

        self.assertEqual(result["server_name"], "dns.google")
        self.assertEqual(result["server_address"], "8.8.8.8")
        self.assertIn("110.242.68.4", result["addresses"])
        self.assertIn("110.242.68.3", result["addresses"])

    def test_parses_windows_single_address(self) -> None:
        output = (
            "Server:  192.168.1.1\r\n"
            "Address:  192.168.1.1\r\n"
            "\r\n"
            "Name:    app.example.local\r\n"
            "Address:  192.168.1.50\r\n"
        )

        result = _parse_nslookup_output(output)

        self.assertEqual(result["server_name"], "192.168.1.1")
        self.assertEqual(result["server_address"], "192.168.1.1")
        self.assertIn("192.168.1.50", result["addresses"])
        self.assertNotIn("192.168.1.1", result["addresses"])

    def test_parses_windows_nxdomain_error(self) -> None:
        output = (
            "Server:  8.8.8.8\r\n"
            "Address:  8.8.8.8\r\n"
            "\r\n"
            "*** Can't find missing.example.local: No answer\r\n"
        )

        result = _parse_nslookup_output(output)
        self.assertEqual(result["addresses"], [])
        self.assertTrue(_has_nslookup_error(output, 0))


class NslookupParseLinuxTests(unittest.TestCase):
    def test_parses_linux_success_output(self) -> None:
        output = (
            "Server:\t\t8.8.8.8\n"
            "Address:\t8.8.8.8#53\n"
            "\n"
            "Non-authoritative answer:\n"
            "Name:\twww.baidu.com\n"
            "Address: 110.242.68.4\n"
            "Name:\twww.baidu.com\n"
            "Address: 110.242.68.3\n"
        )

        result = _parse_nslookup_output(output)

        self.assertEqual(result["server_name"], "8.8.8.8")
        self.assertEqual(result["server_address"], "8.8.8.8")
        self.assertIn("110.242.68.4", result["addresses"])
        self.assertIn("110.242.68.3", result["addresses"])

    def test_parses_linux_single_address(self) -> None:
        output = (
            "Server:\t\t192.168.1.1\n"
            "Address:\t192.168.1.1#53\n"
            "\n"
            "Name:\tapp.example.local\n"
            "Address: 192.168.1.50\n"
        )

        result = _parse_nslookup_output(output)

        self.assertIn("192.168.1.50", result["addresses"])
        self.assertNotIn("192.168.1.1", result["addresses"])

    def test_parses_linux_nxdomain_error(self) -> None:
        output = (
            "Server:\t\t8.8.8.8\n"
            "Address:\t8.8.8.8#53\n"
            "\n"
            "** server can't find missing.example.local: NXDOMAIN\n"
        )

        result = _parse_nslookup_output(output)
        self.assertEqual(result["addresses"], [])
        self.assertTrue(_has_nslookup_error(output, 1))


class NslookupParseEdgeCaseTests(unittest.TestCase):
    def test_returns_empty_for_empty_output(self) -> None:
        result = _parse_nslookup_output("")
        self.assertEqual(result["addresses"], [])
        self.assertEqual(result["server_name"], "")

    def test_returns_empty_for_whitespace_only(self) -> None:
        result = _parse_nslookup_output("  \n  \t  ")
        self.assertEqual(result["addresses"], [])

    def test_deduplicates_addresses(self) -> None:
        output = (
            "Server:\t\t8.8.8.8\n"
            "Address:\t8.8.8.8#53\n"
            "\n"
            "Non-authoritative answer:\n"
            "Name:\texample.com\n"
            "Address: 1.2.3.4\n"
            "Name:\texample.com\n"
            "Address: 1.2.3.4\n"
        )

        result = _parse_nslookup_output(output)
        self.assertEqual(len(result["addresses"]), 1)
        self.assertEqual(result["addresses"][0], "1.2.3.4")


if __name__ == "__main__":
    unittest.main()

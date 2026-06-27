import unittest

from it_ops_toolkit.probes.ping import _parse_ping_stats


class PingStatsWindowsTests(unittest.TestCase):
    def test_parses_windows_success_output(self) -> None:
        output = (
            "Pinging 223.5.5.5 with 32 bytes of data:\n"
            "Reply from 223.5.5.5: bytes=32 time=12ms TTL=115\n"
            "Reply from 223.5.5.5: bytes=32 time=15ms TTL=115\n"
            "Reply from 223.5.5.5: bytes=32 time=11ms TTL=115\n"
            "Reply from 223.5.5.5: bytes=32 time=13ms TTL=115\n"
            "\n"
            "Ping statistics for 223.5.5.5:\n"
            "    Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),\n"
            "Approximate round trip times in milli-seconds:\n"
            "    Minimum = 11ms, Maximum = 15ms, Average = 12ms\n"
        )

        stats = _parse_ping_stats(output)

        self.assertIsNotNone(stats)
        assert stats is not None  # for type checker
        self.assertEqual(stats["packets_sent"], 4)
        self.assertEqual(stats["packets_received"], 4)
        self.assertEqual(stats["packets_lost"], 0)
        self.assertEqual(stats["packet_loss_percent"], 0.0)
        self.assertEqual(stats["min_rtt_ms"], 11.0)
        self.assertEqual(stats["avg_rtt_ms"], 12.0)
        self.assertEqual(stats["max_rtt_ms"], 15.0)

    def test_parses_windows_partial_loss_output(self) -> None:
        output = (
            "Pinging 192.168.1.10 with 32 bytes of data:\n"
            "Reply from 192.168.1.10: bytes=32 time=2ms TTL=64\n"
            "Request timed out.\n"
            "Reply from 192.168.1.10: bytes=32 time=3ms TTL=64\n"
            "Request timed out.\n"
            "\n"
            "Ping statistics for 192.168.1.10:\n"
            "    Packets: Sent = 4, Received = 2, Lost = 2 (50% loss),\n"
            "Approximate round trip times in milli-seconds:\n"
            "    Minimum = 2ms, Maximum = 3ms, Average = 2ms\n"
        )

        stats = _parse_ping_stats(output)

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["packets_sent"], 4)
        self.assertEqual(stats["packets_received"], 2)
        self.assertEqual(stats["packets_lost"], 2)
        self.assertEqual(stats["packet_loss_percent"], 50.0)
        self.assertEqual(stats["avg_rtt_ms"], 2.0)

    def test_parses_windows_total_loss_output(self) -> None:
        output = (
            "Pinging 10.0.0.99 with 32 bytes of data:\n"
            "Request timed out.\n"
            "Request timed out.\n"
            "\n"
            "Ping statistics for 10.0.0.99:\n"
            "    Packets: Sent = 2, Received = 0, Lost = 2 (100% loss),\n"
        )

        stats = _parse_ping_stats(output)

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["packets_sent"], 2)
        self.assertEqual(stats["packets_received"], 0)
        self.assertEqual(stats["packet_loss_percent"], 100.0)
        # No RTT stats when all packets lost
        self.assertNotIn("avg_rtt_ms", stats)


class PingStatsLinuxTests(unittest.TestCase):
    def test_parses_linux_success_output(self) -> None:
        output = (
            "PING 223.5.5.5 (223.5.5.5) 56(84) bytes of data.\n"
            "64 bytes from 223.5.5.5: icmp_seq=1 ttl=115 time=12.1 ms\n"
            "64 bytes from 223.5.5.5: icmp_seq=2 ttl=115 time=15.2 ms\n"
            "64 bytes from 223.5.5.5: icmp_seq=3 ttl=115 time=11.0 ms\n"
            "64 bytes from 223.5.5.5: icmp_seq=4 ttl=115 time=13.5 ms\n"
            "\n"
            "--- 223.5.5.5 ping statistics ---\n"
            "4 packets transmitted, 4 received, 0% packet loss, time 3005ms\n"
            "rtt min/avg/max/mdev = 11.000/12.950/15.200/1.525 ms\n"
        )

        stats = _parse_ping_stats(output)

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["packets_sent"], 4)
        self.assertEqual(stats["packets_received"], 4)
        self.assertEqual(stats["packets_lost"], 0)
        self.assertEqual(stats["packet_loss_percent"], 0.0)
        self.assertEqual(stats["min_rtt_ms"], 11.0)
        self.assertEqual(stats["avg_rtt_ms"], 12.95)
        self.assertEqual(stats["max_rtt_ms"], 15.2)

    def test_parses_linux_partial_loss_output(self) -> None:
        output = (
            "PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.\n"
            "64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=1.23 ms\n"
            "64 bytes from 10.0.0.1: icmp_seq=3 ttl=64 time=1.45 ms\n"
            "\n"
            "--- 10.0.0.1 ping statistics ---\n"
            "4 packets transmitted, 2 received, 50% packet loss, time 3014ms\n"
            "rtt min/avg/max/mdev = 1.230/1.340/1.450/0.110 ms\n"
        )

        stats = _parse_ping_stats(output)

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["packets_sent"], 4)
        self.assertEqual(stats["packets_received"], 2)
        self.assertEqual(stats["packets_lost"], 2)
        self.assertEqual(stats["packet_loss_percent"], 50.0)
        self.assertEqual(stats["avg_rtt_ms"], 1.34)

    def test_parses_linux_total_loss_output(self) -> None:
        output = (
            "PING 10.0.0.99 (10.0.0.99) 56(84) bytes of data.\n"
            "\n"
            "--- 10.0.0.99 ping statistics ---\n"
            "4 packets transmitted, 0 received, 100% packet loss, time 3072ms\n"
        )

        stats = _parse_ping_stats(output)

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["packets_sent"], 4)
        self.assertEqual(stats["packets_received"], 0)
        self.assertEqual(stats["packet_loss_percent"], 100.0)
        self.assertNotIn("avg_rtt_ms", stats)

    def test_parses_linux_old_round_trip_format(self) -> None:
        output = (
            "PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.\n"
            "64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=1.2 ms\n"
            "\n"
            "--- 10.0.0.1 ping statistics ---\n"
            "1 packets transmitted, 1 received, 0% packet loss, time 0ms\n"
            "round-trip min/avg/max = 1.200/1.200/1.200 ms\n"
        )

        stats = _parse_ping_stats(output)

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["avg_rtt_ms"], 1.2)
        self.assertEqual(stats["min_rtt_ms"], 1.2)
        self.assertEqual(stats["max_rtt_ms"], 1.2)


class PingStatsEdgeCaseTests(unittest.TestCase):
    def test_returns_none_for_empty_output(self) -> None:
        self.assertIsNone(_parse_ping_stats(""))

    def test_returns_none_for_non_ping_output(self) -> None:
        self.assertIsNone(_parse_ping_stats("hello world\nfoo bar"))

    def test_returns_none_for_whitespace_only(self) -> None:
        self.assertIsNone(_parse_ping_stats("   \n  \t  "))


if __name__ == "__main__":
    unittest.main()

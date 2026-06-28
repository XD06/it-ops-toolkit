"""Phase 8 拓扑模块测试。

测试覆盖：
- ARP 表解析（Windows / Linux 格式）。
- OUI 厂商识别。
- Traceroute 输出解析（Windows / Linux 格式）。
- 设备类型推断。
- 资产对比（reconcile）。
- 未知设备检测。
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from it_ops_toolkit.models import (
    ArpEntry,
    Asset,
    TraceRouteHop,
    TraceRouteResult,
)
from it_ops_toolkit.probes.arp import (
    _parse_linux_arp,
    _parse_linux_ip_neigh,
    _parse_windows_arp,
    infer_device_type,
    lookup_vendor,
)
from it_ops_toolkit.probes.traceroute import (
    _check_reached,
    _parse_linux_traceroute,
    _parse_windows_tracert,
)
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.topology import detect_unknown_devices, reconcile_arp_with_assets


class OuiLookupTests(unittest.TestCase):
    """测试 OUI 厂商识别。"""

    def test_lookup_known_vendor(self) -> None:
        self.assertEqual(lookup_vendor("b8:27:eb:12:34:56"), "Raspberry Pi Foundation")
        self.assertEqual(lookup_vendor("00:1b:54:aa:bb:cc"), "Cisco Systems")
        self.assertEqual(lookup_vendor("00:15:c5:11:22:33"), "Dell Inc.")

    def test_lookup_unknown_vendor(self) -> None:
        self.assertIsNone(lookup_vendor("aa:bb:cc:dd:ee:ff"))
        self.assertIsNone(lookup_vendor(""))
        self.assertIsNone(lookup_vendor("invalid"))

    def test_lookup_case_insensitive(self) -> None:
        # MAC 前缀大小写不敏感
        self.assertEqual(lookup_vendor("B8:27:EB:12:34:56"), "Raspberry Pi Foundation")
        self.assertEqual(lookup_vendor("00:1B:54:AA:BB:CC"), "Cisco Systems")


class DeviceTypeInferTests(unittest.TestCase):
    """测试设备类型推断。"""

    def test_infer_printer(self) -> None:
        self.assertEqual(
            infer_device_type("Hewlett-Packard", "00:1e:0b:12:34:56"), "printer"
        )
        self.assertEqual(
            infer_device_type("Brother Industries", "00:80:77:aa:bb:cc"), "printer"
        )

    def test_infer_network_device(self) -> None:
        self.assertEqual(
            infer_device_type("Cisco Systems", "00:1b:54:aa:bb:cc"), "network_device"
        )
        self.assertEqual(
            infer_device_type("MikroTik", "00:0c:42:aa:bb:cc"), "network_device"
        )

    def test_infer_unknown(self) -> None:
        self.assertEqual(infer_device_type(None, "aa:bb:cc:dd:ee:ff"), "unknown")
        self.assertEqual(infer_device_type("UnknownVendor", "aa:bb:cc:dd:ee:ff"), "unknown")

    def test_infer_server(self) -> None:
        self.assertEqual(infer_device_type("Dell Inc.", "00:15:c5:aa:bb:cc"), "server")

    def test_infer_iot(self) -> None:
        self.assertEqual(
            infer_device_type("Raspberry Pi Foundation", "b8:27:eb:12:34:56"), "iot"
        )


class ArpParseWindowsTests(unittest.TestCase):
    """测试 Windows ARP 表解析。"""

    def test_parse_windows_arp_basic(self) -> None:
        output = """Interface: 192.168.1.100 --- 0xa
  Internet Address      Physical Address    Type
  192.168.1.1           aa-bb-cc-dd-ee-ff   dynamic
  192.168.1.10          11-22-33-44-55-66   static
  192.168.1.50          b8-27-eb-12-34-56   dynamic
"""
        entries = _parse_windows_arp(output)
        self.assertEqual(len(entries), 3)

        # 第一条
        self.assertEqual(entries[0].ip, "192.168.1.1")
        self.assertEqual(entries[0].mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(entries[0].interface, "192.168.1.100")
        self.assertEqual(entries[0].state, "dynamic")

        # 第二条
        self.assertEqual(entries[1].state, "static")

        # Raspberry Pi 应识别厂商
        self.assertEqual(entries[2].vendor, "Raspberry Pi Foundation")
        self.assertEqual(entries[2].device_type, "iot")

    def test_parse_windows_arp_empty(self) -> None:
        entries = _parse_windows_arp("")
        self.assertEqual(len(entries), 0)

    def test_parse_windows_arp_mac_format(self) -> None:
        """Windows ARP 表中 MAC 用 - 分隔，应转换为 : 并小写。"""
        output = "  10.0.0.1           AA-BB-CC-DD-EE-FF   dynamic\n"
        entries = _parse_windows_arp(output)
        self.assertEqual(entries[0].mac, "aa:bb:cc:dd:ee:ff")


class ArpParseLinuxTests(unittest.TestCase):
    """测试 Linux ARP 表解析。"""

    def test_parse_ip_neigh(self) -> None:
        output = """192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
192.168.1.10 dev eth0 lladdr b8:27:eb:12:34:56 STALE
192.168.1.20 dev wlan0 lladdr 00:1b:54:aa:bb:cc REACHABLE
"""
        entries = _parse_linux_ip_neigh(output)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].ip, "192.168.1.1")
        self.assertEqual(entries[0].interface, "eth0")
        self.assertEqual(entries[0].state, "reachable")
        self.assertEqual(entries[1].vendor, "Raspberry Pi Foundation")
        self.assertEqual(entries[2].vendor, "Cisco Systems")

    def test_parse_ip_neigh_no_mac_skipped(self) -> None:
        """没有 MAC 地址的条目应被跳过。"""
        output = "192.168.1.20 dev eth0 FAILED\n"
        entries = _parse_linux_ip_neigh(output)
        self.assertEqual(len(entries), 0)

    def test_parse_arp_n(self) -> None:
        output = """Address                  HWtype  HWaddress           Flags Mask  Iface
192.168.1.1              ether   aa:bb:cc:dd:ee:ff   C           eth0
192.168.1.10             ether   b8:27:eb:12:34:56   C           eth0
"""
        entries = _parse_linux_arp(output)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].ip, "192.168.1.1")
        self.assertEqual(entries[0].interface, "eth0")
        self.assertEqual(entries[1].vendor, "Raspberry Pi Foundation")


class TracerouteParseWindowsTests(unittest.TestCase):
    """测试 Windows tracert 输出解析。"""

    def test_parse_windows_tracert(self) -> None:
        output = """Tracing route to 8.8.8.8 over a maximum of 15 hops

  1     1 ms     1 ms     1 ms  192.168.1.1
  2     5 ms     4 ms     5 ms  10.0.0.1
  3     *        *        *     Request timed out.
  4    12 ms    11 ms    12 ms  8.8.8.8

Trace complete.
"""
        hops = _parse_windows_tracert(output)
        self.assertEqual(len(hops), 4)

        self.assertEqual(hops[0].hop, 1)
        self.assertEqual(hops[0].ip, "192.168.1.1")
        self.assertEqual(len(hops[0].rtt_ms), 3)
        self.assertFalse(hops[0].timeout)

        self.assertEqual(hops[1].hop, 2)
        self.assertEqual(hops[1].ip, "10.0.0.1")

        self.assertTrue(hops[2].timeout)
        self.assertIsNone(hops[2].ip)

        self.assertEqual(hops[3].hop, 4)
        self.assertEqual(hops[3].ip, "8.8.8.8")

    def test_parse_windows_tracert_empty(self) -> None:
        hops = _parse_windows_tracert("")
        self.assertEqual(len(hops), 0)


class TracerouteParseLinuxTests(unittest.TestCase):
    """测试 Linux traceroute 输出解析。"""

    def test_parse_linux_traceroute(self) -> None:
        output = """traceroute to 8.8.8.8 (8.8.8.8), 15 hops max, 60 byte packets
 1  192.168.1.1 (192.168.1.1)  1.234 ms  1.456 ms  1.789 ms
 2  10.0.0.1 (10.0.0.1)  5.123 ms  5.456 ms  5.789 ms
 3  * * *
 4  8.8.8.8 (8.8.8.8)  12.345 ms  12.678 ms  12.901 ms
"""
        hops = _parse_linux_traceroute(output)
        self.assertEqual(len(hops), 4)

        self.assertEqual(hops[0].hop, 1)
        self.assertEqual(hops[0].ip, "192.168.1.1")
        self.assertEqual(len(hops[0].rtt_ms), 3)
        self.assertAlmostEqual(hops[0].rtt_ms[0], 1.234, places=3)

        self.assertTrue(hops[2].timeout)

        self.assertEqual(hops[3].ip, "8.8.8.8")

    def test_check_reached_ip_match(self) -> None:
        hops = [
            TraceRouteHop(hop=1, ip="192.168.1.1", rtt_ms=[1.0]),
            TraceRouteHop(hop=2, ip="8.8.8.8", rtt_ms=[5.0]),
        ]
        self.assertTrue(_check_reached(hops, "8.8.8.8"))

    def test_check_not_reached_timeout(self) -> None:
        hops = [
            TraceRouteHop(hop=1, ip="192.168.1.1", rtt_ms=[1.0]),
            TraceRouteHop(hop=2, timeout=True),
        ]
        self.assertFalse(_check_reached(hops, "8.8.8.8"))

    def test_check_not_reached_empty(self) -> None:
        self.assertFalse(_check_reached([], "8.8.8.8"))


class ReconcileTests(unittest.TestCase):
    """测试 ARP 表与资产库对比。"""

    def _make_asset(self, ip: str, hostname: str | None = None) -> Asset:
        now = datetime.now(UTC)
        return Asset(
            id=f"asset-{ip}",
            ip=ip,
            hostname=hostname,
            open_ports=[],
            first_seen=now,
            last_seen=now,
        )

    def test_reconcile_finds_new_and_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")

            # 资产库有 192.168.1.1 和 192.168.1.10
            store.save_asset(self._make_asset("192.168.1.1", "gateway"))
            store.save_asset(self._make_asset("192.168.1.10", "server"))

            # ARP 表有 192.168.1.1（匹配）和 192.168.1.50（新设备）
            arp_entries = [
                ArpEntry(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff", vendor="Cisco Systems"),
                ArpEntry(ip="192.168.1.50", mac="11:22:33:44:55:66", vendor=None),
            ]

            result = reconcile_arp_with_assets(arp_entries=arp_entries, store=store)

            self.assertEqual(len(result.matched), 1)
            self.assertEqual(result.matched[0]["ip"], "192.168.1.1")
            self.assertEqual(len(result.new_devices), 1)
            self.assertEqual(result.new_devices[0].ip, "192.168.1.50")
            self.assertEqual(len(result.offline_devices), 1)
            self.assertEqual(result.offline_devices[0].ip, "192.168.1.10")
            self.assertEqual(len(result.unknown_vendors), 1)
            self.assertEqual(result.unknown_vendors[0].ip, "192.168.1.50")


class DetectUnknownDevicesTests(unittest.TestCase):
    """测试未知设备检测。"""

    def _make_asset(self, ip: str) -> Asset:
        now = datetime.now(UTC)
        return Asset(
            id=f"asset-{ip}",
            ip=ip,
            open_ports=[],
            first_seen=now,
            last_seen=now,
        )

    def test_detect_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.save_asset(self._make_asset("192.168.1.1"))

            arp_entries = [
                ArpEntry(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff"),  # 已知
                ArpEntry(ip="192.168.1.99", mac="99:88:77:66:55:44"),  # 未知
                ArpEntry(ip="10.0.0.5", mac="11:22:33:44:55:66"),  # 未知
            ]

            unknown = detect_unknown_devices(arp_entries=arp_entries, store=store)
            self.assertEqual(len(unknown), 2)
            ips = {e.ip for e in unknown}
            self.assertIn("192.168.1.99", ips)
            self.assertIn("10.0.0.5", ips)

    def test_detect_no_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.save_asset(self._make_asset("192.168.1.1"))

            arp_entries = [
                ArpEntry(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff"),
            ]

            unknown = detect_unknown_devices(arp_entries=arp_entries, store=store)
            self.assertEqual(len(unknown), 0)


class CollectArpTableMockTests(unittest.TestCase):
    """测试 collect_arp_table 在 mock 环境下的行为。"""

    @patch("it_ops_toolkit.probes.arp.platform.system", return_value="Windows")
    @patch("it_ops_toolkit.probes.arp.subprocess.run")
    def test_collect_windows(self, mock_run, mock_system) -> None:
        mock_run.return_value.stdout = (
            "Interface: 192.168.1.100 --- 0xa\n"
            "  Internet Address      Physical Address    Type\n"
            "  192.168.1.1           b8-27-eb-12-34-56   dynamic\n"
        )

        from it_ops_toolkit.probes.arp import collect_arp_table

        entries = collect_arp_table()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].ip, "192.168.1.1")
        self.assertEqual(entries[0].mac, "b8:27:eb:12:34:56")
        self.assertEqual(entries[0].vendor, "Raspberry Pi Foundation")

    @patch("it_ops_toolkit.probes.arp.platform.system", return_value="Linux")
    @patch("it_ops_toolkit.probes.arp.subprocess.run")
    def test_collect_linux(self, mock_run, mock_system) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "192.168.1.1 dev eth0 lladdr b8:27:eb:12:34:56 REACHABLE\n"
        )

        from it_ops_toolkit.probes.arp import collect_arp_table

        entries = collect_arp_table()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].ip, "192.168.1.1")
        self.assertEqual(entries[0].interface, "eth0")


class RunTracerouteMockTests(unittest.TestCase):
    """测试 run_traceroute 在 mock 环境下的行为。"""

    @patch("it_ops_toolkit.probes.traceroute.platform.system", return_value="Windows")
    @patch("it_ops_toolkit.probes.traceroute.subprocess.run")
    def test_run_traceroute_windows(self, mock_run, mock_system) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "Tracing route to 8.8.8.8 over a maximum of 15 hops\n\n"
            "  1     1 ms     1 ms     1 ms  192.168.1.1\n"
            "  2    12 ms    11 ms    12 ms  8.8.8.8\n\n"
            "Trace complete.\n"
        )

        from it_ops_toolkit.probes.traceroute import run_traceroute

        result = run_traceroute(target="8.8.8.8", max_hops=15)
        self.assertEqual(result.target, "8.8.8.8")
        self.assertEqual(len(result.hops), 2)
        self.assertTrue(result.reached)


class TopologyViewModelTests(unittest.TestCase):
    """测试拓扑数据模型。"""

    def test_arp_entry_model(self) -> None:
        entry = ArpEntry(
            ip="192.168.1.1",
            mac="aa:bb:cc:dd:ee:ff",
            interface="eth0",
            state="dynamic",
            vendor="Cisco Systems",
            device_type="network_device",
        )
        self.assertEqual(entry.ip, "192.168.1.1")
        self.assertEqual(entry.vendor, "Cisco Systems")

    def test_arp_entry_defaults(self) -> None:
        entry = ArpEntry(ip="10.0.0.1", mac="aa:bb:cc:dd:ee:ff")
        self.assertEqual(entry.interface, "")
        self.assertEqual(entry.state, "dynamic")
        self.assertIsNone(entry.vendor)

    def test_trace_route_hop_timeout(self) -> None:
        hop = TraceRouteHop(hop=3, timeout=True)
        self.assertTrue(hop.timeout)
        self.assertIsNone(hop.ip)
        self.assertEqual(hop.rtt_ms, [])

    def test_trace_route_result(self) -> None:
        result = TraceRouteResult(
            target="8.8.8.8",
            source="192.168.1.100",
            hops=[TraceRouteHop(hop=1, ip="192.168.1.1", rtt_ms=[1.5])],
            total_hops=1,
            reached=False,
        )
        self.assertEqual(result.target, "8.8.8.8")
        self.assertEqual(result.total_hops, 1)
        self.assertFalse(result.reached)


if __name__ == "__main__":
    unittest.main()

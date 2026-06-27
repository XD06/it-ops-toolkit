import unittest
from datetime import UTC, datetime

from it_ops_toolkit.diagnosis import (
    classify_dns_diagnosis,
    classify_internet_diagnosis,
    classify_intranet_diagnosis,
    classify_printer_diagnosis,
    classify_rdp_diagnosis,
    classify_slow_network_diagnosis,
    normalize_ports,
    parse_host_port_target,
    parse_ports,
    parse_service_url,
)
from it_ops_toolkit.models import ProbeResult, ProbeStatus, Target


class DiagnosisTests(unittest.TestCase):
    def test_classifies_dns_issue_when_ping_ok_but_dns_fails(self) -> None:
        results = [
            _result("ping", "223.5.5.5", ProbeStatus.success),
            _result("dns", "www.baidu.com", ProbeStatus.failed),
            _result("http", "https://www.baidu.com", ProbeStatus.failed),
        ]

        summary = classify_internet_diagnosis(results)

        self.assertEqual(summary.title, "外部 IP 可达，但 DNS 解析异常")

    def test_classifies_success_when_all_checks_pass(self) -> None:
        results = [
            _result("ping", "223.5.5.5", ProbeStatus.success),
            _result("dns", "www.baidu.com", ProbeStatus.success),
            _result("http", "https://www.baidu.com", ProbeStatus.success),
        ]

        summary = classify_internet_diagnosis(results)

        self.assertEqual(summary.title, "基础互联网连通性正常")

    def test_classifies_dns_lookup_failure(self) -> None:
        results = [
            _result("dns", "missing.example.local", ProbeStatus.failed),
        ]

        summary = classify_dns_diagnosis(results)

        self.assertEqual(summary.title, "DNS 解析失败")

    def test_classifies_dns_expected_ip_mismatch(self) -> None:
        results = [
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"addresses": ["192.168.1.10"]},
            ),
        ]

        summary = classify_dns_diagnosis(results, expected_ip="192.168.1.20")

        self.assertEqual(summary.title, "DNS 解析结果不符合预期")

    def test_classifies_dns_tcp_issue(self) -> None:
        results = [
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"addresses": ["192.168.1.10"]},
            ),
            _result(
                "tcp",
                "192.168.1.10:443",
                ProbeStatus.failed,
                observations={"port": 443, "open": False},
            ),
        ]

        summary = classify_dns_diagnosis(results, expected_ip="192.168.1.10", tcp_port=443)

        self.assertEqual(summary.title, "DNS 解析正常，但目标端口不可达")

    def test_classifies_dns_success(self) -> None:
        results = [
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"addresses": ["192.168.1.10"]},
            ),
            _result(
                "tcp",
                "192.168.1.10:443",
                ProbeStatus.success,
                observations={"port": 443, "open": True},
            ),
        ]

        summary = classify_dns_diagnosis(results, expected_ip="192.168.1.10", tcp_port=443)

        self.assertEqual(summary.title, "DNS 基础检查正常")

    def test_classifies_dns_server_mismatch(self) -> None:
        results = [
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"addresses": ["192.168.1.10"]},
            ),
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"dns_server": "8.8.8.8", "addresses": ["203.0.113.50"]},
            ),
        ]

        summary = classify_dns_diagnosis(
            results,
            dns_servers=["8.8.8.8"],
        )

        self.assertEqual(summary.title, "多 DNS 服务器解析结果不一致")

    def test_classifies_dns_server_all_match(self) -> None:
        results = [
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"addresses": ["192.168.1.10"]},
            ),
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"dns_server": "8.8.8.8", "addresses": ["192.168.1.10"]},
            ),
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"dns_server": "114.114.114.114", "addresses": ["192.168.1.10"]},
            ),
        ]

        summary = classify_dns_diagnosis(
            results,
            dns_servers=["8.8.8.8", "114.114.114.114"],
        )

        self.assertEqual(summary.title, "DNS 基础检查正常")

    def test_classifies_dns_server_partial_failure(self) -> None:
        results = [
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"addresses": ["192.168.1.10"]},
            ),
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"dns_server": "8.8.8.8", "addresses": ["192.168.1.10"]},
            ),
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.failed,
                observations={"dns_server": "10.0.0.53", "addresses": []},
            ),
        ]

        summary = classify_dns_diagnosis(
            results,
            dns_servers=["8.8.8.8", "10.0.0.53"],
        )

        self.assertIn("部分 DNS 服务器解析失败", summary.title)
        self.assertIn("10.0.0.53", summary.title)

    def test_classifies_dns_server_all_failed(self) -> None:
        results = [
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.success,
                observations={"addresses": ["192.168.1.10"]},
            ),
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.failed,
                observations={"dns_server": "8.8.8.8", "addresses": []},
            ),
            _result(
                "dns",
                "app.example.local",
                ProbeStatus.failed,
                observations={"dns_server": "10.0.0.53", "addresses": []},
            ),
        ]

        summary = classify_dns_diagnosis(
            results,
            dns_servers=["8.8.8.8", "10.0.0.53"],
        )

        self.assertEqual(summary.title, "所有指定 DNS 服务器解析均失败")

    def test_classifies_slow_dns_latency(self) -> None:
        results = [
            _result("ping", "223.5.5.5", ProbeStatus.success, duration_ms=40),
            _result("dns", "www.baidu.com", ProbeStatus.success, duration_ms=650),
            _result("http", "https://www.baidu.com", ProbeStatus.success, duration_ms=300),
        ]

        summary = classify_slow_network_diagnosis(results)

        self.assertEqual(summary.title, "DNS 解析耗时偏高")

    def test_classifies_slow_http_latency(self) -> None:
        results = [
            _result("ping", "223.5.5.5", ProbeStatus.success, duration_ms=40),
            _result("dns", "www.baidu.com", ProbeStatus.success, duration_ms=80),
            _result("http", "https://www.baidu.com", ProbeStatus.success, duration_ms=1500),
        ]

        summary = classify_slow_network_diagnosis(results)

        self.assertEqual(summary.title, "HTTP/HTTPS 响应耗时偏高")

    def test_classifies_high_packet_loss(self) -> None:
        results = [
            _result(
                "ping",
                "223.5.5.5",
                ProbeStatus.success,
                duration_ms=40,
                observations={"packet_loss_percent": 50.0, "avg_rtt_ms": 30.0},
            ),
            _result("dns", "www.baidu.com", ProbeStatus.success, duration_ms=80),
            _result("http", "https://www.baidu.com", ProbeStatus.success, duration_ms=300),
        ]

        summary = classify_slow_network_diagnosis(results)

        self.assertEqual(summary.title, "基础链路丢包率偏高")

    def test_classifies_high_rtt_latency(self) -> None:
        results = [
            _result(
                "ping",
                "223.5.5.5",
                ProbeStatus.success,
                duration_ms=600,
                observations={"avg_rtt_ms": 350.0, "packet_loss_percent": 0.0},
            ),
            _result("dns", "www.baidu.com", ProbeStatus.success, duration_ms=80),
            _result("http", "https://www.baidu.com", ProbeStatus.success, duration_ms=400),
        ]

        summary = classify_slow_network_diagnosis(results)

        self.assertEqual(summary.title, "基础网络延迟偏高")

    def test_slow_network_normal_with_rtt_observations(self) -> None:
        results = [
            _result(
                "ping",
                "223.5.5.5",
                ProbeStatus.success,
                duration_ms=35,
                observations={"avg_rtt_ms": 15.0, "packet_loss_percent": 0.0},
            ),
            _result("dns", "www.baidu.com", ProbeStatus.success, duration_ms=80),
            _result("http", "https://www.baidu.com", ProbeStatus.success, duration_ms=300),
        ]

        summary = classify_slow_network_diagnosis(results)

        self.assertEqual(summary.title, "基础延迟检查正常")

    def test_parse_service_url_uses_default_https_port(self) -> None:
        parsed = parse_service_url("https://intranet.example.local/path")

        self.assertEqual(parsed["host"], "intranet.example.local")
        self.assertEqual(parsed["port"], 443)

    def test_classifies_intranet_tcp_issue(self) -> None:
        results = [
            _result("dns", "intranet.example.local", ProbeStatus.success),
            _result("ping", "intranet.example.local", ProbeStatus.success),
            _result("tcp", "intranet.example.local", ProbeStatus.failed),
            _result("http", "https://intranet.example.local", ProbeStatus.failed),
        ]

        summary = classify_intranet_diagnosis(results)

        self.assertEqual(summary.title, "目标主机可达，但业务端口不可达")

    def test_parse_rdp_target_supports_host_port(self) -> None:
        parsed = parse_host_port_target("pc-01.example.local:3390", default_port=3389)

        self.assertEqual(parsed["host"], "pc-01.example.local")
        self.assertEqual(parsed["port"], 3390)

    def test_classifies_rdp_port_reachable_when_ping_fails(self) -> None:
        results = [
            _result("dns", "pc-01.example.local", ProbeStatus.success),
            _result("ping", "pc-01.example.local", ProbeStatus.failed),
            _result("tcp", "pc-01.example.local", ProbeStatus.success),
        ]

        summary = classify_rdp_diagnosis(results)

        self.assertEqual(summary.title, "RDP 端口可达，但 Ping 不通")

    def test_classifies_rdp_tcp_issue(self) -> None:
        results = [
            _result("ping", "192.168.1.50", ProbeStatus.success),
            _result("tcp", "192.168.1.50", ProbeStatus.failed),
        ]

        summary = classify_rdp_diagnosis(results)

        self.assertEqual(summary.title, "目标主机可达，但 RDP 端口不可达")

    def test_parse_ports_supports_csv_and_deduplicates(self) -> None:
        ports = parse_ports("9100, 515, 631, 9100")

        self.assertEqual(ports, [9100, 515, 631])

    def test_normalize_ports_rejects_empty_list(self) -> None:
        with self.assertRaises(ValueError):
            normalize_ports([])

    def test_classifies_printer_dns_issue(self) -> None:
        results = [
            _result("dns", "printer-01.example.local", ProbeStatus.failed),
            _result("ping", "printer-01.example.local", ProbeStatus.failed),
            _result("tcp", "printer-01.example.local:9100", ProbeStatus.failed),
        ]

        summary = classify_printer_diagnosis(results)

        self.assertEqual(summary.title, "打印机名称解析异常")

    def test_classifies_printer_port_issue(self) -> None:
        results = [
            _result("ping", "192.168.1.80", ProbeStatus.success),
            _result("tcp", "192.168.1.80:9100", ProbeStatus.failed),
            _result("tcp", "192.168.1.80:515", ProbeStatus.failed),
            _result("tcp", "192.168.1.80:631", ProbeStatus.failed),
        ]

        summary = classify_printer_diagnosis(results)

        self.assertEqual(summary.title, "打印机可达，但常见打印端口不可达")

    def test_classifies_printer_success_when_any_port_open(self) -> None:
        results = [
            _result("ping", "192.168.1.80", ProbeStatus.success),
            _result("tcp", "192.168.1.80:9100", ProbeStatus.failed),
            _result("tcp", "192.168.1.80:515", ProbeStatus.success),
            _result("tcp", "192.168.1.80:631", ProbeStatus.failed),
        ]

        summary = classify_printer_diagnosis(results)

        self.assertEqual(summary.title, "至少一个打印端口可达")


def _result(
    probe_type: str,
    target: str,
    status: ProbeStatus,
    observations: dict[str, object] | None = None,
    duration_ms: int | None = None,
) -> ProbeResult:
    now = datetime.now(UTC)
    target_type = "url" if target.startswith("http") else "hostname"
    return ProbeResult(
        id=f"probe-{probe_type}-{target}",
        task_id="task-test",
        probe_type=probe_type,
        target=Target(type=target_type, value=target),
        status=status,
        started_at=now,
        ended_at=now,
        duration_ms=duration_ms,
        observations=observations or {},
    )


if __name__ == "__main__":
    unittest.main()

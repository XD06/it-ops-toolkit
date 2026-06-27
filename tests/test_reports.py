import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.models import (
    Asset,
    LocalInterface,
    LocalSnapshot,
    ProbeResult,
    ProbeStatus,
    Target,
    TaskStatus,
)
from it_ops_toolkit.reports import generate_report
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import finish_task_run, new_task_run


class ReportTests(unittest.TestCase):
    def test_generate_markdown_report_for_asset_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="asset_scan")
            now = datetime.now(UTC)
            asset = Asset(
                id="asset-127-0-0-1",
                ip="127.0.0.1",
                open_ports=[445],
                first_seen=now,
                last_seen=now,
            )
            result = ProbeResult(
                id="probe-ping-127.0.0.1",
                task_id=task.id,
                probe_type="ping",
                target=Target(type="ip", value="127.0.0.1"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"reachable": True},
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": [asset.ip],
                    "result_refs": [result.id],
                }
            )

            store.save_task_run(task)
            store.save_asset(asset)
            store.save_probe_result(result)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )

            report_path = Path(report.path)
            self.assertTrue(report_path.exists())
            self.assertIn("资产结果", report_path.read_text(encoding="utf-8"))

    def test_generate_markdown_report_for_diagnosis_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="diagnosis")
            now = datetime.now(UTC)
            result = ProbeResult(
                id="probe-tcp-192.168.1.80-9100",
                task_id=task.id,
                probe_type="tcp",
                target=Target(type="service", value="192.168.1.80:9100"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"port": 9100, "reachable": True},
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": ["192.168.1.80", "9100", "515", "631"],
                    "result_refs": [result.id],
                    "summary": {
                        "scenario": "printer",
                        "scenario_label": "打印机可达性诊断",
                        "title": "至少一个打印端口可达",
                        "likely_area": "基础网络路径和打印服务端口正常",
                        "recommendation": "继续检查驱动和队列。",
                        "ports": [9100, 515, 631],
                    },
                }
            )

            store.save_task_run(task)
            store.save_probe_result(result)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )

            report_path = Path(report.path)
            text = report_path.read_text(encoding="utf-8")
            self.assertEqual(report.report_type, "diagnosis")
            self.assertEqual(report.title, "打印机可达性诊断报告")
            self.assertEqual(report.summary, "至少一个打印端口可达；可能范围：基础网络路径和打印服务端口正常")
            self.assertIn("# 打印机可达性诊断报告", text)
            self.assertIn("执行摘要", text)
            self.assertIn("至少一个打印端口可达", text)
            self.assertIn("诊断步骤", text)
            self.assertIn("| 1 | TCP 端口 | 192.168.1.80:9100 | 正常 |", text)
            self.assertIn("打印端口检查", text)
            self.assertIn("检查端口：9100,515,631", text)
            self.assertIn("可达端口：9100", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))
            self.assertEqual(
                payload["printer_port_summary"],
                {
                    "checked_ports": [9100, 515, 631],
                    "reachable_ports": [9100],
                },
            )
            self.assertEqual(
                payload["diagnosis_steps"],
                [
                    {
                        "step": 1,
                        "check": "TCP 端口",
                        "target": "192.168.1.80:9100",
                        "status": "正常",
                        "probe_type": "tcp",
                        "result_id": "probe-tcp-192.168.1.80-9100",
                    }
                ],
            )

    def test_generate_report_for_dns_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="diagnosis")
            now = datetime.now(UTC)
            dns_result = ProbeResult(
                id="probe-dns-app.example.local",
                task_id=task.id,
                probe_type="dns",
                target=Target(type="hostname", value="app.example.local"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"addresses": ["192.168.1.10"]},
            )
            tcp_result = ProbeResult(
                id="probe-tcp-192.168.1.10-443",
                task_id=task.id,
                probe_type="tcp",
                target=Target(type="ip", value="192.168.1.10"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={"port": 443, "open": True},
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": ["app.example.local", "192.168.1.10", "443"],
                    "result_refs": [dns_result.id, tcp_result.id],
                    "summary": {
                        "scenario": "dns",
                        "scenario_label": "DNS 解析诊断",
                        "title": "DNS 基础检查正常",
                        "likely_area": "未发现解析失败、解析结果偏差或目标端口基础异常",
                        "recommendation": "继续检查应用或客户端环境。",
                        "expected_ip": "192.168.1.10",
                        "tcp_port": 443,
                    },
                }
            )

            store.save_task_run(task)
            store.save_probe_result(dns_result)
            store.save_probe_result(tcp_result)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )
            text = Path(report.path).read_text(encoding="utf-8")

            self.assertEqual(report.title, "DNS 解析诊断报告")
            self.assertIn("DNS 解析结果", text)
            self.assertIn("解析地址：192.168.1.10", text)
            self.assertIn("期望 IP：192.168.1.10", text)
            self.assertIn("期望命中：是", text)
            self.assertIn("TCP 检查端口：443", text)
            self.assertIn("TCP 可达地址：192.168.1.10", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))

            self.assertEqual(payload["diagnosis_steps"][0]["check"], "DNS 解析")
            self.assertEqual(payload["diagnosis_steps"][0]["status"], "正常")
            self.assertEqual(payload["diagnosis_steps"][1]["check"], "TCP 端口")
            self.assertEqual(payload["diagnosis_steps"][1]["target"], "192.168.1.10")
            self.assertEqual(
                payload["dns_resolution_summary"],
                {
                    "name": "app.example.local",
                    "resolved_addresses": ["192.168.1.10"],
                    "expected_ip": "192.168.1.10",
                    "expected_ip_matched": True,
                    "tcp_port": 443,
                    "tcp_reachable_addresses": ["192.168.1.10"],
                },
            )

    def test_generate_report_for_certificate_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="security_check")
            now = datetime.now(UTC)
            result = ProbeResult(
                id="probe-tls-cert-example-com-443",
                task_id=task.id,
                probe_type="tls_cert",
                target=Target(type="service", value="example.com:443"),
                status=ProbeStatus.success,
                started_at=now,
                ended_at=now,
                observations={
                    "days_remaining": 7,
                    "expires_at": "2026-06-30T00:00:00+00:00",
                },
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": ["example.com:443"],
                    "result_refs": [result.id],
                    "summary": {
                        "scenario": "cert_check",
                        "scenario_label": "证书过期检查",
                        "title": "TLS 证书即将过期",
                        "target": "example.com:443",
                        "days_remaining": 7,
                        "warning_days": 30,
                    },
                }
            )

            store.save_task_run(task)
            store.save_probe_result(result)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )
            text = Path(report.path).read_text(encoding="utf-8")

            self.assertEqual(report.title, "证书过期检查报告")
            self.assertIn("证书检查结果", text)
            self.assertIn("剩余天数：7", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))

            self.assertEqual(
                payload["certificate_summary"],
                {
                    "target": "example.com:443",
                    "status": "success",
                    "days_remaining": 7,
                    "expires_at": "2026-06-30T00:00:00+00:00",
                    "warning_days": 30,
                },
            )

    def test_generate_report_for_asset_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="asset_diff")
            now = datetime.now(UTC)
            asset = Asset(
                id="asset-192-168-1-20",
                ip="192.168.1.20",
                open_ports=[80, 443],
                first_seen=now,
                last_seen=now,
                source="scan_profile:office_lan",
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": [asset.ip],
                    "summary": {
                        "scenario": "asset_diff",
                        "scenario_label": "资产变化对比",
                        "title": "资产变化检查发现变化",
                        "likely_area": "资产接入、设备在线状态或服务端口发生变化",
                        "recommendation": "复核变化。",
                        "profile": "office_lan",
                        "scanned_asset_count": 1,
                        "new_assets": ["192.168.1.20"],
                        "disappeared_assets": ["192.168.1.30"],
                        "newly_open_ports": {"192.168.1.20": [443]},
                        "new_asset_count": 1,
                        "disappeared_asset_count": 1,
                        "newly_open_port_count": 1,
                    },
                }
            )

            store.save_task_run(task)
            store.save_asset(asset)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )
            text = Path(report.path).read_text(encoding="utf-8")

            self.assertEqual(report.title, "资产变化对比报告")
            self.assertEqual(report.report_type, "asset")
            self.assertIn("资产变化", text)
            self.assertIn("新增资产：192.168.1.20", text)
            self.assertIn("未出现资产：192.168.1.30", text)
            self.assertIn("| 192.168.1.20 | 443 |", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))
            self.assertEqual(
                payload["asset_diff_summary"],
                {
                    "profile": "office_lan",
                    "scanned_asset_count": 1,
                    "new_assets": ["192.168.1.20"],
                    "disappeared_assets": ["192.168.1.30"],
                    "newly_open_ports": {"192.168.1.20": [443]},
                    "new_asset_count": 1,
                    "disappeared_asset_count": 1,
                    "newly_open_port_count": 1,
                },
            )

    def test_generate_report_for_asset_import_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="asset_import_notes")
            now = datetime.now(UTC)
            asset = Asset(
                id="asset-192-168-1-20",
                ip="192.168.1.20",
                hostname="pc-20",
                owner="Alice",
                asset_type="workstation",
                description="财务电脑",
                tags=["finance"],
                open_ports=[445],
                first_seen=now,
                last_seen=now,
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": [asset.ip],
                    "summary": {
                        "scenario": "asset_import_notes",
                        "scenario_label": "资产备注导入",
                        "title": "资产备注导入完成，但存在跳过行",
                        "likely_area": "资产元数据维护",
                        "recommendation": "复核跳过行。",
                        "source_file": str(Path(tmp) / "asset-notes.csv"),
                        "updated_assets": [asset.ip],
                        "updated_count": 1,
                        "skipped_rows": [
                            {
                                "row": 3,
                                "ip": "192.168.1.99",
                                "reason": "asset_not_found",
                            }
                        ],
                        "skipped_count": 1,
                        "error_rows": [],
                        "error_count": 0,
                    },
                }
            )

            store.save_task_run(task)
            store.save_asset(asset)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )
            text = Path(report.path).read_text(encoding="utf-8")

            self.assertEqual(report.title, "资产备注导入报告")
            self.assertEqual(report.summary, "更新资产 1 台，跳过行 1 行，错误行 0 行")
            self.assertIn("资产备注导入", text)
            self.assertIn("已更新 IP：192.168.1.20", text)
            self.assertIn("| 3 | 192.168.1.99 | skipped | asset_not_found |", text)
            self.assertIn("Alice", text)
            self.assertIn("finance", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))
            self.assertEqual(payload["asset_import_summary"]["updated_count"], 1)
            self.assertEqual(payload["asset_import_summary"]["skipped_count"], 1)
            self.assertEqual(payload["assets"][0]["owner"], "Alice")
            self.assertEqual(payload["assets"][0]["tags"], ["finance"])

    def test_generate_report_for_flush_dns_automation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="automation")
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": ["localhost"],
                    "result_refs": ["automation-flush-dns"],
                    "summary": {
                        "scenario": "flush_dns",
                        "scenario_label": "清理本机 DNS 缓存",
                        "title": "清理本机 DNS 缓存计划已生成",
                        "likely_area": "本机 DNS 缓存",
                        "recommendation": "如确认要执行低风险变更，请重新运行并显式添加 --confirm。",
                        "action": "flush_dns_cache",
                        "target": "localhost",
                        "dry_run": True,
                        "confirmed": False,
                        "executed": False,
                        "risk_level": "low_change",
                        "result": {
                            "status": "planned",
                            "return_code": None,
                            "duration_ms": 0,
                            "error": None,
                        },
                    },
                }
            )
            store.save_task_run(task)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )
            text = Path(report.path).read_text(encoding="utf-8")

            self.assertEqual(report.title, "清理本机 DNS 缓存报告")
            self.assertEqual(report.report_type, "ops")
            self.assertIn("自动化动作", text)
            self.assertIn("Dry-run：是", text)
            self.assertIn("结果：planned", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))
            self.assertEqual(payload["automation_summary"]["scenario"], "flush_dns")
            self.assertEqual(payload["automation_summary"]["status"], "planned")
            self.assertFalse(payload["automation_summary"]["executed"])

    def test_generate_report_for_health_tcp_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="health_matrix")
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "summary": {
                        "scenario": "health_tcp_matrix",
                        "scenario_label": "批量 TCP 端口测试",
                        "title": "批量 TCP 端口测试发现异常",
                        "likely_area": "目标端口可达性",
                        "recommendation": "复核失败目标的网络路径、服务监听和防火墙策略。",
                        "source_file": str(Path(tmp) / "targets.csv"),
                        "target_count": 2,
                        "result_count": 2,
                        "success_count": 1,
                        "failed_count": 1,
                        "entries": [
                            {
                                "row": 2,
                                "name": "printer",
                                "host": "192.168.1.10",
                                "port": 9100,
                                "status": "success",
                                "error": "",
                                "duration_ms": 12,
                            },
                            {
                                "row": 3,
                                "name": "nas",
                                "host": "192.168.1.20",
                                "port": 445,
                                "status": "failed",
                                "error": "TCP connection failed",
                                "duration_ms": 8,
                            },
                        ],
                        "result_ids": ["probe-tcp-192.168.1.10-9100"],
                    }
                }
            )
            store.save_task_run(task)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )
            text = Path(report.path).read_text(encoding="utf-8")

            self.assertEqual(report.title, "批量 TCP 端口测试报告")
            self.assertIn("批量 TCP 端口测试", text)
            self.assertIn("| 2 | printer | 192.168.1.10 | 9100 | success | 12 |", text)
            self.assertIn("| 3 | nas | 192.168.1.20 | 445 | failed | 8 | TCP connection failed |", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))
            self.assertEqual(payload["health_matrix_summary"]["target_count"], 2)
            self.assertEqual(payload["health_matrix_summary"]["success_count"], 1)
            self.assertEqual(payload["health_matrix_summary"]["result_ids"], ["probe-tcp-192.168.1.10-9100"])

    def test_generate_report_for_health_http_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="health_matrix")
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "summary": {
                        "scenario": "health_http_matrix",
                        "scenario_label": "批量 HTTP 端口测试",
                        "title": "批量 HTTP 端口测试正常",
                        "likely_area": "目标 HTTP/HTTPS 可达性",
                        "recommendation": "保持巡检节奏。",
                        "source_file": str(Path(tmp) / "targets.csv"),
                        "target_count": 1,
                        "result_count": 1,
                        "success_count": 1,
                        "failed_count": 0,
                        "entries": [
                            {
                                "row": 2,
                                "name": "portal",
                                "url": "https://ok.example.local",
                                "method": "GET",
                                "status": "success",
                                "error": "",
                                "duration_ms": 20,
                            }
                        ],
                        "result_ids": ["probe-http-https-ok-example-local"],
                    }
                }
            )
            store.save_task_run(task)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )
            text = Path(report.path).read_text(encoding="utf-8")

            self.assertEqual(report.title, "批量 HTTP 端口测试报告")
            self.assertIn("批量 HTTP 端口测试", text)
            self.assertIn("https://ok.example.local", text)

            json_report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="json",
            )
            payload = json.loads(Path(json_report.path).read_text(encoding="utf-8"))
            self.assertEqual(payload["health_matrix_summary"]["target_count"], 1)
            self.assertEqual(payload["health_matrix_summary"]["success_count"], 1)
            self.assertEqual(payload["health_matrix_summary"]["result_ids"], ["probe-http-https-ok-example-local"])

    def test_generate_markdown_report_for_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="ops_collect")
            now = datetime.now(UTC)
            snapshot = LocalSnapshot(
                id="local-1",
                task_id=task.id,
                collected_at=now,
                hostname="pc-01",
                os_name="Windows-11",
                platform="Windows",
                interfaces=[
                    LocalInterface(
                        name="Ethernet",
                        status="Up",
                        ipv4_addresses=["192.168.1.20"],
                        default_gateways=["192.168.1.1"],
                        dns_servers=["192.168.1.1"],
                    )
                ],
                default_routes=[{"next_hop": "192.168.1.1"}],
                dns_servers=["192.168.1.1"],
            )
            task = finish_task_run(task, status=TaskStatus.success)
            task = task.model_copy(
                update={
                    "target_refs": [snapshot.hostname],
                    "result_refs": [snapshot.id],
                }
            )

            store.save_task_run(task)
            store.save_local_snapshot(snapshot)

            report = generate_report(
                store=store,
                source_task_id=task.id,
                output_dir=Path(tmp) / "reports",
                report_format="markdown",
            )

            report_path = Path(report.path)
            text = report_path.read_text(encoding="utf-8")
            self.assertTrue(report_path.exists())
            self.assertIn("本机信息", text)
            self.assertIn("Ethernet", text)


if __name__ == "__main__":
    unittest.main()

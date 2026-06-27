from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import Asset, Finding, LocalSnapshot, ProbeResult, Report, TaskRun
from .storage import SQLiteStore, TaskRecordNotFound


class ReportError(RuntimeError):
    pass


def generate_report(
    *,
    store: SQLiteStore,
    source_task_id: str,
    output_dir: Path,
    report_format: str,
) -> Report:
    try:
        source_task = store.get_task_run(source_task_id)
    except TaskRecordNotFound as exc:
        raise ReportError(f"source task not found: {source_task_id}") from exc

    if report_format not in {"markdown", "csv", "json"}:
        raise ReportError(f"unsupported report format: {report_format}")

    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = f"report-{uuid4().hex[:12]}"
    report_type = _report_type_for_task(source_task)
    path = output_dir / f"{report_id}.{_extension_for_format(report_format)}"
    probe_results = store.list_probe_results_for_task(source_task.id)
    findings = store.list_findings_for_task(source_task.id)
    local_snapshots = store.list_local_snapshots_for_task(source_task.id)
    assets = _assets_for_task(store, source_task)

    if report_format == "markdown":
        path.write_text(
            _render_markdown(source_task, probe_results, assets, findings, local_snapshots),
            encoding="utf-8",
        )
    elif report_format == "csv":
        _write_csv(path, probe_results, assets, findings, local_snapshots)
    elif report_format == "json":
        path.write_text(
            _render_json(source_task, probe_results, assets, findings, local_snapshots),
            encoding="utf-8",
        )

    report = Report(
        id=report_id,
        source_task_id=source_task.id,
        report_type=report_type,
        title=_report_title_for_task(source_task),
        format=report_format,
        path=str(path),
        summary=_report_summary_for_task(
            source_task,
            probe_results=probe_results,
            findings=findings,
            local_snapshots=local_snapshots,
            assets=assets,
        ),
        generated_at=datetime.now(UTC),
    )
    store.save_report(report)
    return report


def _report_type_for_task(task: TaskRun) -> str:
    if task.task_type == "asset_scan":
        return "asset"
    if task.task_type == "asset_diff":
        return "asset"
    if task.task_type == "asset_import_notes":
        return "asset"
    if task.task_type == "health_check":
        return "health"
    if task.task_type == "health_matrix":
        return "health"
    if task.task_type == "security_check":
        return "security"
    if task.task_type == "ops_collect":
        return "ops"
    if task.task_type == "automation":
        return "ops"
    if task.task_type == "diagnosis":
        return "diagnosis"
    return "generic"


def _report_title_for_task(task: TaskRun) -> str:
    if task.task_type == "asset_scan":
        return "资产扫描报告"
    if task.task_type == "asset_diff":
        return "资产变化对比报告"
    if task.task_type == "asset_import_notes":
        return "资产备注导入报告"
    if task.task_type == "health_check":
        return "巡检报告"
    if task.task_type == "health_matrix":
        scenario = str(task.summary.get("scenario", "")).strip()
        if scenario == "health_http_matrix":
            return "批量 HTTP 端口测试报告"
        return "批量 TCP 端口测试报告"
    if task.task_type == "security_check":
        if task.summary.get("scenario") == "cert_check":
            return "证书过期检查报告"
        return "安全检查报告"
    if task.task_type == "ops_collect":
        return "本机运维信息采集报告"
    if task.task_type == "automation":
        if task.summary.get("scenario") == "flush_dns":
            return "清理本机 DNS 缓存报告"
        return "自动化动作报告"
    if task.task_type == "diagnosis":
        scenario = _diagnosis_scenario_name(task)
        return f"{scenario}报告"
    return f"{task.task_type} 报告"


def _diagnosis_scenario_name(task: TaskRun) -> str:
    scenario_label = str(task.summary.get("scenario_label", "")).strip()
    if scenario_label:
        return scenario_label

    scenario = str(task.summary.get("scenario", "")).strip()
    if scenario == "internet":
        return "互联网连通性诊断"
    if scenario == "intranet":
        return "内网系统访问诊断"
    if scenario == "printer":
        return "打印机可达性诊断"
    if scenario == "rdp":
        return "远程桌面连接诊断"
    if scenario == "slow_network":
        return "网络慢基础诊断"
    if scenario == "dns":
        return "DNS 解析诊断"

    targets = task.target_refs
    summary_title = str(task.summary.get("title", "")).strip()

    if len(targets) >= 3 and any(target.startswith("http://") or target.startswith("https://") for target in targets):
        return "互联网连通性诊断"
    if len(targets) == 1 and (targets[0].startswith("http://") or targets[0].startswith("https://")):
        return "内网系统访问诊断"
    if "RDP" in summary_title:
        return "远程桌面连接诊断"
    if "打印" in summary_title:
        return "打印机可达性诊断"
    return "诊断"


def _report_summary_for_task(
    task: TaskRun,
    *,
    probe_results: list[ProbeResult],
    findings: list[Finding],
    local_snapshots: list[LocalSnapshot],
    assets: list[Asset],
) -> str:
    if task.task_type == "diagnosis" and task.summary:
        title = str(task.summary.get("title", "")).strip()
        likely_area = str(task.summary.get("likely_area", "")).strip()
        if likely_area:
            return f"{title}；可能范围：{likely_area}"
        return title
    if task.task_type == "asset_scan":
        return f"发现资产 {len(assets)} 台，探测结果 {len(probe_results)} 条"
    if task.task_type == "asset_diff":
        return (
            f"新增资产 {task.summary.get('new_asset_count', 0)} 台，"
            f"未出现资产 {task.summary.get('disappeared_asset_count', 0)} 台，"
            f"新增开放端口 {task.summary.get('newly_open_port_count', 0)} 个"
        )
    if task.task_type == "asset_import_notes":
        return (
            f"更新资产 {task.summary.get('updated_count', 0)} 台，"
            f"跳过行 {task.summary.get('skipped_count', 0)} 行，"
            f"错误行 {task.summary.get('error_count', 0)} 行"
        )
    if task.task_type == "health_check":
        return f"巡检完成，探测结果 {len(probe_results)} 条"
    if task.task_type == "health_matrix" and task.summary:
        return (
            f"目标 {task.summary.get('target_count', 0)} 个，"
            f"成功 {task.summary.get('success_count', 0)} 个，"
            f"失败 {task.summary.get('failed_count', 0)} 个"
        )
    if task.task_type == "security_check":
        return f"安全发现 {len(findings)} 条"
    if task.task_type == "ops_collect":
        return f"采集本机信息快照 {len(local_snapshots)} 份"
    if task.task_type == "automation" and task.summary:
        return str(task.summary.get("title", "自动化动作完成"))
    return (
        f"探测结果 {len(probe_results)} 条，"
        f"风险发现 {len(findings)} 条，"
        f"本机快照 {len(local_snapshots)} 份"
    )


def _extension_for_format(report_format: str) -> str:
    return {"markdown": "md", "csv": "csv", "json": "json"}[report_format]


def _assets_for_task(store: SQLiteStore, task: TaskRun) -> list[Asset]:
    assets: list[Asset] = []
    if task.task_type not in {
        "asset_scan",
        "asset_diff",
        "asset_import_notes",
        "health_matrix",
    }:
        return assets
    for target_ref in task.target_refs:
        asset = store.get_asset_by_ip(target_ref)
        if asset:
            assets.append(asset)
    return assets


def _render_markdown(
    task: TaskRun,
    probe_results: list[ProbeResult],
    assets: list[Asset],
    findings: list[Finding],
    local_snapshots: list[LocalSnapshot],
) -> str:
    lines = [
        f"# {_report_title_for_task(task)}",
        "",
        "## 任务信息",
        "",
        f"- 任务 ID：`{task.id}`",
        f"- 任务类型：`{task.task_type}`",
        f"- 状态：`{task.status.value}`",
        f"- 风险等级：`{task.risk_level.value}`",
        f"- 开始时间：`{task.started_at.isoformat()}`",
        f"- 结束时间：`{task.ended_at.isoformat() if task.ended_at else ''}`",
        "",
    ]

    if task.summary:
        lines.extend(
            [
                "## 执行摘要",
                "",
                f"- 标题：{task.summary.get('title', '')}",
                f"- 可能范围：{task.summary.get('likely_area', '')}",
                f"- 建议：{task.summary.get('recommendation', '')}",
                "",
            ]
        )
        lines.extend(_render_diagnosis_steps(task, probe_results))
        lines.extend(_render_diagnosis_details(task, probe_results))
        lines.extend(_render_asset_diff_details(task))
        lines.extend(_render_asset_import_details(task))
        lines.extend(_render_automation_details(task))
        lines.extend(_render_health_matrix_details(task))

    if local_snapshots:
        lines.extend(
            [
                "## 本机信息",
                "",
                "| 主机名 | 系统 | 网卡数 | 默认路由数 | DNS | 采集时间 |",
                "|---|---|---:|---:|---|---|",
            ]
        )
        for snapshot in local_snapshots:
            lines.append(
                "| "
                + " | ".join(
                    [
                        snapshot.hostname,
                        snapshot.os_name,
                        str(len(snapshot.interfaces)),
                        str(len(snapshot.default_routes)),
                        ",".join(snapshot.dns_servers),
                        snapshot.collected_at.isoformat(),
                    ]
                )
                + " |"
            )
        lines.append("")

        lines.extend(
            [
                "## 网卡摘要",
                "",
                "| 名称 | 状态 | IPv4 | 网关 | DNS |",
                "|---|---|---|---|---|",
            ]
        )
        for snapshot in local_snapshots:
            for interface in snapshot.interfaces:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            interface.name,
                            interface.status or "",
                            ",".join(interface.ipv4_addresses),
                            ",".join(interface.default_gateways),
                            ",".join(interface.dns_servers),
                        ]
                    )
                    + " |"
                )
        lines.append("")

    if assets:
        lines.extend(
            [
                "## 资产结果",
                "",
                "| IP | 主机名 | 类型 | 负责人 | 标签 | 状态 | 开放端口 | 最后发现 |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for asset in assets:
            lines.append(
                "| "
                + " | ".join(
                    [
                        asset.ip,
                        asset.hostname or "",
                        asset.asset_type or "",
                        asset.owner or "",
                        ",".join(asset.tags),
                        asset.status,
                        ",".join(str(port) for port in asset.open_ports),
                        asset.last_seen.isoformat(),
                    ]
                )
                + " |"
            )
        lines.append("")

    if findings:
        lines.extend(
            [
                "## 风险发现",
                "",
                "| 等级 | 标题 | 描述 | 建议 |",
                "|---|---|---|---|",
            ]
        )
        for finding in findings:
            lines.append(
                "| "
                + " | ".join(
                    [
                        finding.severity.value,
                        finding.title,
                        finding.description,
                        finding.recommendation,
                    ]
                )
                + " |"
            )
        lines.append("")

    cert_summary = _certificate_check_summary_payload(task, probe_results)
    if cert_summary:
        lines.extend(
            [
                "## 证书检查结果",
                "",
                f"- 目标：{cert_summary['target']}",
                f"- 剩余天数：{cert_summary['days_remaining']}",
                f"- 过期时间：{cert_summary['expires_at'] or ''}",
                "",
            ]
        )

    lines.extend(
        [
            "## 探测结果",
            "",
            "| 类型 | 目标 | 状态 | 耗时 ms | 观察值 | 错误 |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for result in probe_results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.probe_type,
                    result.target.value,
                    result.status.value,
                    str(result.duration_ms or ""),
                    _compact_json(result.observations),
                    result.error.message if result.error else "",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_diagnosis_details(task: TaskRun, probe_results: list[ProbeResult]) -> list[str]:
    dns_summary = _dns_resolution_summary_payload(task, probe_results)
    if dns_summary:
        lines = [
            "## DNS 解析结果",
            "",
            f"- 解析地址：{','.join(str(address) for address in dns_summary['resolved_addresses']) if dns_summary['resolved_addresses'] else '无'}",
            f"- 期望 IP：{dns_summary['expected_ip'] or '未指定'}",
            f"- 期望命中：{_expected_ip_match_label(dns_summary)}",
        ]
        if dns_summary["tcp_port"]:
            lines.append(f"- TCP 检查端口：{dns_summary['tcp_port']}")
            lines.append(
                f"- TCP 可达地址：{','.join(str(address) for address in dns_summary['tcp_reachable_addresses']) if dns_summary['tcp_reachable_addresses'] else '无'}"
            )
        lines.append("")
        return lines

    printer_summary = _printer_port_summary_payload(task, probe_results)
    if not printer_summary:
        return []

    lines = [
        "## 打印端口检查",
        "",
        f"- 检查端口：{','.join(str(port) for port in printer_summary['checked_ports'])}",
        f"- 可达端口：{','.join(str(port) for port in printer_summary['reachable_ports']) if printer_summary['reachable_ports'] else '无'}",
        "",
    ]
    return lines


def _render_diagnosis_steps(task: TaskRun, probe_results: list[ProbeResult]) -> list[str]:
    steps = _diagnosis_steps_payload(task, probe_results)
    if not steps:
        return []

    lines = [
        "## 诊断步骤",
        "",
        "| 步骤 | 检查 | 目标 | 结果 |",
        "|---:|---|---|---|",
    ]
    for step in steps:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(step["step"]),
                    str(step["check"]),
                    str(step["target"]),
                    str(step["status"]),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def _probe_label(result: ProbeResult) -> str:
    if result.probe_type == "dns":
        return "DNS 解析"
    if result.probe_type == "ping":
        return "Ping 连通性"
    if result.probe_type == "tcp":
        return "TCP 端口"
    if result.probe_type == "http":
        return "HTTP/HTTPS 访问"
    return result.probe_type


def _probe_status_label(result: ProbeResult) -> str:
    labels = {
        "success": "正常",
        "failed": "异常",
        "timeout": "超时",
        "skipped": "跳过",
    }
    return labels.get(result.status.value, result.status.value)


def _expected_ip_match_label(dns_summary: dict[str, object]) -> str:
    if not dns_summary["expected_ip"]:
        return "未检查"
    return "是" if dns_summary["expected_ip_matched"] else "否"


def _write_csv(
    path: Path,
    probe_results: list[ProbeResult],
    assets: list[Asset],
    findings: list[Finding],
    local_snapshots: list[LocalSnapshot],
) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        if local_snapshots:
            writer.writerow(
                [
                    "snapshot_id",
                    "hostname",
                    "os_name",
                    "interface_name",
                    "status",
                    "ipv4_addresses",
                    "default_gateways",
                    "dns_servers",
                    "collected_at",
                ]
            )
            for snapshot in local_snapshots:
                if not snapshot.interfaces:
                    writer.writerow(
                        [
                            snapshot.id,
                            snapshot.hostname,
                            snapshot.os_name,
                            "",
                            "",
                            "",
                            "",
                            ",".join(snapshot.dns_servers),
                            snapshot.collected_at.isoformat(),
                        ]
                    )
                for interface in snapshot.interfaces:
                    writer.writerow(
                        [
                            snapshot.id,
                            snapshot.hostname,
                            snapshot.os_name,
                            interface.name,
                            interface.status or "",
                            ",".join(interface.ipv4_addresses),
                            ",".join(interface.default_gateways),
                            ",".join(interface.dns_servers),
                            snapshot.collected_at.isoformat(),
                        ]
                    )
            return

        if assets:
            writer.writerow(
                [
                    "ip",
                    "hostname",
                    "asset_type",
                    "owner",
                    "description",
                    "tags",
                    "status",
                    "open_ports",
                    "last_seen",
                ]
            )
            for asset in assets:
                writer.writerow(
                    [
                        asset.ip,
                        asset.hostname or "",
                        asset.asset_type or "",
                        asset.owner or "",
                        asset.description or "",
                        ",".join(asset.tags),
                        asset.status,
                        ",".join(str(port) for port in asset.open_ports),
                        asset.last_seen.isoformat(),
                    ]
                )
            return

        if findings:
            writer.writerow(["severity", "title", "description", "recommendation"])
            for finding in findings:
                writer.writerow(
                    [
                        finding.severity.value,
                        finding.title,
                        finding.description,
                        finding.recommendation,
                    ]
                )
            return

        writer.writerow(["probe_type", "target", "status", "duration_ms", "observations", "error"])
        for result in probe_results:
            writer.writerow(
                [
                    result.probe_type,
                    result.target.value,
                    result.status.value,
                    result.duration_ms or "",
                    _compact_json(result.observations),
                    result.error.message if result.error else "",
                ]
            )


def _render_json(
    task: TaskRun,
    probe_results: list[ProbeResult],
    assets: list[Asset],
    findings: list[Finding],
    local_snapshots: list[LocalSnapshot],
) -> str:
    payload = {
        "task": task.model_dump(mode="json"),
        "assets": [asset.model_dump(mode="json") for asset in assets],
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "local_snapshots": [
            snapshot.model_dump(mode="json") for snapshot in local_snapshots
        ],
        "diagnosis_steps": _diagnosis_steps_payload(task, probe_results),
        "dns_resolution_summary": _dns_resolution_summary_payload(task, probe_results),
        "printer_port_summary": _printer_port_summary_payload(task, probe_results),
        "certificate_summary": _certificate_check_summary_payload(task, probe_results),
        "asset_diff_summary": _asset_diff_summary_payload(task),
        "asset_import_summary": _asset_import_summary_payload(task),
        "automation_summary": _automation_summary_payload(task),
        "health_matrix_summary": _health_matrix_summary_payload(task),
        "probe_results": [result.model_dump(mode="json") for result in probe_results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _diagnosis_steps_payload(
    task: TaskRun,
    probe_results: list[ProbeResult],
) -> list[dict[str, object]]:
    if task.task_type != "diagnosis":
        return []
    return [
        {
            "step": index,
            "check": _probe_label(result),
            "target": result.target.value,
            "status": _probe_status_label(result),
            "probe_type": result.probe_type,
            "result_id": result.id,
        }
        for index, result in enumerate(probe_results, start=1)
    ]


def _printer_port_summary_payload(
    task: TaskRun,
    probe_results: list[ProbeResult],
) -> dict[str, list[int]] | None:
    if task.task_type != "diagnosis" or task.summary.get("scenario") != "printer":
        return None

    checked_ports = [int(port) for port in task.summary.get("ports", [])]
    reachable_ports: list[int] = []
    for result in probe_results:
        if result.probe_type != "tcp" or result.status.value != "success":
            continue
        port = result.observations.get("port")
        if port is None and ":" in result.target.value:
            raw_port = result.target.value.rsplit(":", 1)[-1]
            port = int(raw_port) if raw_port.isdigit() else None
        if port is None:
            continue
        port_value = int(port)
        if port_value not in reachable_ports:
            reachable_ports.append(port_value)

    return {
        "checked_ports": checked_ports,
        "reachable_ports": reachable_ports,
    }


def _dns_resolution_summary_payload(
    task: TaskRun,
    probe_results: list[ProbeResult],
) -> dict[str, object] | None:
    if task.task_type != "diagnosis" or task.summary.get("scenario") != "dns":
        return None

    dns_result = next((result for result in probe_results if result.probe_type == "dns"), None)
    resolved_addresses = []
    if dns_result:
        addresses = dns_result.observations.get("addresses", [])
        if isinstance(addresses, list):
            resolved_addresses = [str(address) for address in addresses]

    expected_ip = task.summary.get("expected_ip")
    tcp_port = task.summary.get("tcp_port")
    tcp_reachable_addresses: list[str] = []
    for result in probe_results:
        if result.probe_type != "tcp" or result.status.value != "success":
            continue
        if result.target.value not in tcp_reachable_addresses:
            tcp_reachable_addresses.append(result.target.value)

    return {
        "name": task.target_refs[0] if task.target_refs else "",
        "resolved_addresses": resolved_addresses,
        "expected_ip": expected_ip,
        "expected_ip_matched": bool(expected_ip and str(expected_ip) in resolved_addresses),
        "tcp_port": tcp_port,
        "tcp_reachable_addresses": tcp_reachable_addresses,
    }


def _certificate_check_summary_payload(
    task: TaskRun,
    probe_results: list[ProbeResult],
) -> dict[str, object] | None:
    if task.task_type != "security_check" or task.summary.get("scenario") != "cert_check":
        return None
    result = next((item for item in probe_results if item.probe_type == "tls_cert"), None)
    if result is None:
        return None
    return {
        "target": result.target.value,
        "status": result.status.value,
        "days_remaining": result.observations.get("days_remaining"),
        "expires_at": result.observations.get("expires_at"),
        "warning_days": task.summary.get("warning_days"),
    }


def _render_asset_diff_details(task: TaskRun) -> list[str]:
    summary = _asset_diff_summary_payload(task)
    if not summary:
        return []

    newly_open_ports = summary["newly_open_ports"]
    lines = [
        "## 资产变化",
        "",
        f"- 扫描配置：{summary['profile']}",
        f"- 新增资产：{','.join(summary['new_assets']) if summary['new_assets'] else '无'}",
        f"- 未出现资产：{','.join(summary['disappeared_assets']) if summary['disappeared_assets'] else '无'}",
        f"- 新增开放端口数量：{summary['newly_open_port_count']}",
        "",
    ]
    if newly_open_ports:
        lines.extend(
            [
                "| IP | 新增开放端口 |",
                "|---|---|",
            ]
        )
        for ip, ports in newly_open_ports.items():
            lines.append(f"| {ip} | {','.join(str(port) for port in ports)} |")
        lines.append("")
    return lines


def _asset_diff_summary_payload(task: TaskRun) -> dict[str, object] | None:
    if task.task_type != "asset_diff" or task.summary.get("scenario") != "asset_diff":
        return None

    newly_open_ports = task.summary.get("newly_open_ports", {})
    normalized_ports: dict[str, list[int]] = {}
    if isinstance(newly_open_ports, dict):
        for ip, ports in newly_open_ports.items():
            if isinstance(ports, list):
                normalized_ports[str(ip)] = [int(port) for port in ports]

    return {
        "profile": task.summary.get("profile", ""),
        "scanned_asset_count": int(task.summary.get("scanned_asset_count", 0)),
        "new_assets": [str(ip) for ip in task.summary.get("new_assets", [])],
        "disappeared_assets": [
            str(ip) for ip in task.summary.get("disappeared_assets", [])
        ],
        "newly_open_ports": normalized_ports,
        "new_asset_count": int(task.summary.get("new_asset_count", 0)),
        "disappeared_asset_count": int(task.summary.get("disappeared_asset_count", 0)),
        "newly_open_port_count": int(task.summary.get("newly_open_port_count", 0)),
    }


def _render_asset_import_details(task: TaskRun) -> list[str]:
    summary = _asset_import_summary_payload(task)
    if not summary:
        return []

    lines = [
        "## 资产备注导入",
        "",
        f"- 来源文件：{summary['source_file']}",
        f"- 更新资产：{summary['updated_count']}",
        f"- 跳过行：{summary['skipped_count']}",
        f"- 错误行：{summary['error_count']}",
        "",
    ]
    if summary["updated_assets"]:
        lines.append(f"- 已更新 IP：{','.join(summary['updated_assets'])}")
        lines.append("")
    if summary["skipped_rows"] or summary["error_rows"]:
        lines.extend(
            [
                "| 行号 | IP | 类型 | 原因 |",
                "|---:|---|---|---|",
            ]
        )
        for row in summary["skipped_rows"]:
            lines.append(
                f"| {row.get('row', '')} | {row.get('ip', '')} | skipped | {row.get('reason', '')} |"
            )
        for row in summary["error_rows"]:
            lines.append(
                f"| {row.get('row', '')} | {row.get('ip', '')} | error | {row.get('reason', '')} |"
            )
        lines.append("")
    return lines


def _asset_import_summary_payload(task: TaskRun) -> dict[str, object] | None:
    if (
        task.task_type != "asset_import_notes"
        or task.summary.get("scenario") != "asset_import_notes"
    ):
        return None

    return {
        "source_file": str(task.summary.get("source_file", "")),
        "updated_assets": [str(ip) for ip in task.summary.get("updated_assets", [])],
        "updated_count": int(task.summary.get("updated_count", 0)),
        "skipped_rows": list(task.summary.get("skipped_rows", [])),
        "skipped_count": int(task.summary.get("skipped_count", 0)),
        "error_rows": list(task.summary.get("error_rows", [])),
        "error_count": int(task.summary.get("error_count", 0)),
    }


def _render_automation_details(task: TaskRun) -> list[str]:
    summary = _automation_summary_payload(task)
    if not summary:
        return []

    lines = [
        "## 自动化动作",
        "",
        f"- 动作：{summary['action']}",
        f"- 目标：{summary['target']}",
        f"- 风险等级：{summary['risk_level']}",
        f"- Dry-run：{'是' if summary['dry_run'] else '否'}",
        f"- 已执行：{'是' if summary['executed'] else '否'}",
        f"- 结果：{summary['status']}",
        "",
    ]
    if summary["error"]:
        lines.extend([f"- 错误：{summary['error']}", ""])
    return lines


def _automation_summary_payload(task: TaskRun) -> dict[str, object] | None:
    if task.task_type != "automation":
        return None

    result = task.summary.get("result", {})
    if not isinstance(result, dict):
        result = {}

    return {
        "scenario": task.summary.get("scenario", ""),
        "action": task.summary.get("action", ""),
        "target": task.summary.get("target", ""),
        "risk_level": task.summary.get("risk_level", ""),
        "dry_run": bool(task.summary.get("dry_run", False)),
        "confirmed": bool(task.summary.get("confirmed", False)),
        "executed": bool(task.summary.get("executed", False)),
        "status": result.get("status", ""),
        "return_code": result.get("return_code"),
        "duration_ms": result.get("duration_ms"),
        "error": result.get("error"),
    }


def _render_health_matrix_details(task: TaskRun) -> list[str]:
    summary = _health_matrix_summary_payload(task)
    if not summary:
        return []

    scenario = str(summary.get("scenario", ""))
    if scenario == "health_http_matrix":
        return _render_http_matrix_details(summary)
    return _render_tcp_matrix_details(summary)


def _render_tcp_matrix_details(summary: dict[str, object]) -> list[str]:
    lines = [
        "## 批量 TCP 端口测试",
        "",
        f"- 来源文件：{summary['source_file']}",
        f"- 目标数量：{summary['target_count']}",
        f"- 成功数量：{summary['success_count']}",
        f"- 失败数量：{summary['failed_count']}",
        "",
        "| 行号 | 名称 | 主机 | 端口 | 状态 | 耗时 ms | 错误 |",
        "|---:|---|---|---:|---|---:|---|",
    ]
    for entry in summary["entries"]:
        target_label = entry.get("host", entry.get("url", ""))
        port_label = entry.get("port", "")
        lines.append(
            f"| {entry['row']} | {entry['name']} | {target_label} | {port_label} | {entry['status']} | {entry['duration_ms'] if entry['duration_ms'] is not None else ''} | {entry['error']} |"
        )
    lines.append("")
    return lines


def _render_http_matrix_details(summary: dict[str, object]) -> list[str]:
    mismatch_count = int(summary.get("mismatch_count", 0))
    lines = [
        "## 批量 HTTP 端口测试",
        "",
        f"- 来源文件：{summary['source_file']}",
        f"- 目标数量：{summary['target_count']}",
        f"- 成功数量：{summary['success_count']}",
        f"- 失败数量：{summary['failed_count']}",
    ]
    if mismatch_count:
        lines.append(f"- 状态码不匹配：{mismatch_count}")
    lines.extend(
        [
            "",
            "| 行号 | 名称 | URL | 方法 | 状态 | HTTP 状态码 | 期望状态码 | 匹配 | 耗时 ms | 错误 |",
            "|---:|---|---|---|---|---:|---|---|---:|---|",
        ]
    )
    for entry in summary["entries"]:
        http_status = entry.get("http_status_code")
        http_status_label = str(http_status) if http_status is not None else ""
        expected_label = entry.get("expected_status", "")
        match_label = _http_status_match_label(entry)
        lines.append(
            f"| {entry['row']} | {entry['name']} | {entry['url']} | {entry['method']} | {entry['status']} | {http_status_label} | {expected_label} | {match_label} | {entry['duration_ms'] if entry['duration_ms'] is not None else ''} | {entry['error']} |"
        )
    lines.append("")
    return lines


def _http_status_match_label(entry: dict[str, object]) -> str:
    if not entry.get("expected_status"):
        return "未检查"
    return "是" if entry.get("status_match") else "否"


def _health_matrix_summary_payload(task: TaskRun) -> dict[str, object] | None:
    if task.task_type != "health_matrix" or task.summary.get("scenario") not in {
        "health_tcp_matrix",
        "health_http_matrix",
    }:
        return None
    return {
        "scenario": str(task.summary.get("scenario", "")),
        "source_file": str(task.summary.get("source_file", "")),
        "target_count": int(task.summary.get("target_count", 0)),
        "result_count": int(task.summary.get("result_count", 0)),
        "result_ids": [str(result_id) for result_id in task.summary.get("result_ids", [])],
        "success_count": int(task.summary.get("success_count", 0)),
        "failed_count": int(task.summary.get("failed_count", 0)),
        "mismatch_count": int(task.summary.get("mismatch_count", 0)),
        "entries": list(task.summary.get("entries", [])),
    }

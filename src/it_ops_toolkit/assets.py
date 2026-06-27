from __future__ import annotations

import csv
import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path

from .config import OpsConfig, ScanProfile
from .models import Asset, Finding, ProbeResult, ProbeStatus, Severity, TaskRun
from .probes import check_tcp_port, ping_host
from .storage import SQLiteStore

MAX_SCAN_HOSTS = 1024


class AssetScanError(RuntimeError):
    pass


class AssetExportError(RuntimeError):
    pass


class AssetImportError(RuntimeError):
    pass


def run_asset_scan(
    *,
    config: OpsConfig,
    profile_name: str,
    task: TaskRun,
    store: SQLiteStore,
    tcp_without_ping: bool = False,
) -> tuple[list[Asset], list[ProbeResult]]:
    profile = _get_scan_profile(config, profile_name)
    hosts = expand_scan_hosts(profile)
    if len(hosts) > MAX_SCAN_HOSTS:
        raise AssetScanError(
            f"scan profile expands to {len(hosts)} hosts; limit is {MAX_SCAN_HOSTS}"
        )

    ping_results = _run_ping_checks(config, profile, task, hosts)
    active_hosts = [
        result.target.value
        for result in ping_results
        if result.status == ProbeStatus.success and result.observations.get("reachable")
    ]
    tcp_hosts = hosts if tcp_without_ping else active_hosts
    tcp_results = _run_tcp_checks(config, profile, task, tcp_hosts)
    results = [*ping_results, *tcp_results]

    open_ports_by_host: dict[str, list[int]] = {host: [] for host in active_hosts}
    for result in tcp_results:
        if result.status == ProbeStatus.success:
            port = result.observations.get("port")
            if isinstance(port, int):
                open_ports_by_host.setdefault(result.target.value, []).append(port)

    active_host_set = set(active_hosts)
    asset_hosts = [
        host for host in hosts if host in active_host_set or host in open_ports_by_host
    ]

    now = datetime.now(UTC)
    assets = [
        Asset(
            id=f"asset-{host.replace('.', '-')}",
            ip=host,
            hostname=_safe_reverse_dns(host),
            open_ports=sorted(open_ports_by_host.get(host, [])),
            first_seen=now,
            last_seen=now,
            status="active",
            source=f"scan_profile:{profile_name}",
        )
        for host in asset_hosts
    ]

    for result in results:
        store.save_probe_result(result)
    for asset in assets:
        store.save_asset(asset)

    return assets, results


def run_asset_diff(
    *,
    config: OpsConfig,
    profile_name: str,
    task: TaskRun,
    store: SQLiteStore,
    tcp_without_ping: bool = False,
) -> tuple[list[Asset], list[ProbeResult], list[Finding], dict[str, object]]:
    before_assets = {asset.ip: asset for asset in store.list_assets()}
    scanned_assets, results = run_asset_scan(
        config=config,
        profile_name=profile_name,
        task=task,
        store=store,
        tcp_without_ping=tcp_without_ping,
    )
    scanned_by_ip = {asset.ip: asset for asset in scanned_assets}

    new_assets = sorted(ip for ip in scanned_by_ip if ip not in before_assets)
    disappeared_assets = sorted(
        ip
        for ip, asset in before_assets.items()
        if _asset_in_profile(asset, profile_name) and ip not in scanned_by_ip
    )
    newly_open_ports = _newly_open_ports(before_assets, scanned_by_ip)

    findings = _asset_diff_findings(
        task=task,
        new_assets=new_assets,
        disappeared_assets=disappeared_assets,
        newly_open_ports=newly_open_ports,
    )
    for finding in findings:
        store.save_finding(finding)

    summary = _asset_diff_summary(
        profile_name=profile_name,
        scanned_assets=scanned_assets,
        results=results,
        new_assets=new_assets,
        disappeared_assets=disappeared_assets,
        newly_open_ports=newly_open_ports,
    )
    return scanned_assets, results, findings, summary


def import_asset_notes(
    *,
    store: SQLiteStore,
    csv_path: Path,
) -> dict[str, object]:
    if not csv_path.exists():
        raise AssetImportError(f"asset notes file not found: {csv_path}")

    updated_assets: list[str] = []
    skipped_rows: list[dict[str, object]] = []
    error_rows: list[dict[str, object]] = []

    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        if "ip" not in fieldnames:
            raise AssetImportError("asset notes CSV must include an 'ip' column")
        allowed_columns = {
            "ip",
            "hostname",
            "owner",
            "asset_type",
            "description",
            "tags",
        }
        unsupported_columns = sorted(fieldnames - allowed_columns)
        if unsupported_columns:
            raise AssetImportError(
                "unsupported asset notes CSV columns: "
                + ", ".join(unsupported_columns)
            )
        for row_number, row in enumerate(reader, start=2):
            ip = _clean_csv_value(row.get("ip"))
            if not ip:
                error_rows.append(
                    {
                        "row": row_number,
                        "reason": "missing_ip",
                    }
                )
                continue
            if None in row:
                error_rows.append(
                    {
                        "row": row_number,
                        "ip": ip,
                        "reason": "too_many_columns",
                    }
                )
                continue

            asset = store.get_asset_by_ip(ip)
            if asset is None:
                skipped_rows.append(
                    {
                        "row": row_number,
                        "ip": ip,
                        "reason": "asset_not_found",
                    }
                )
                continue

            updated_asset = asset.model_copy(
                update={
                    "hostname": _clean_csv_value(row.get("hostname")) or asset.hostname,
                    "owner": _clean_csv_value(row.get("owner")),
                    "asset_type": _clean_csv_value(row.get("asset_type"))
                    or asset.asset_type,
                    "description": _clean_csv_value(row.get("description")),
                    "tags": _parse_tags(row.get("tags")),
                }
            )
            store.save_asset(updated_asset)
            updated_assets.append(ip)

    return {
        "scenario": "asset_import_notes",
        "scenario_label": "资产备注导入",
        "title": _asset_import_title(updated_assets, skipped_rows, error_rows),
        "likely_area": "资产元数据维护",
        "recommendation": "复核跳过和错误行；确认负责人、用途和标签符合当前资产台账。",
        "source_file": str(csv_path),
        "updated_assets": updated_assets,
        "updated_count": len(updated_assets),
        "skipped_rows": skipped_rows,
        "skipped_count": len(skipped_rows),
        "error_rows": error_rows,
        "error_count": len(error_rows),
    }


def export_assets(
    *,
    store: SQLiteStore,
    output_path: Path,
    export_format: str = "csv",
) -> Path:
    export_format = export_format.lower()
    if export_format not in {"csv", "json"}:
        raise AssetExportError(f"unsupported asset export format: {export_format}")

    assets = store.list_assets()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "csv":
        _write_assets_csv(output_path, assets)
    elif export_format == "json":
        output_path.write_text(
            json.dumps(
                [asset.model_dump(mode="json") for asset in assets],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return output_path


def default_asset_export_path(base_dir: Path, export_format: str) -> Path:
    export_format = export_format.lower()
    if export_format not in {"csv", "json"}:
        raise AssetExportError(f"unsupported asset export format: {export_format}")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return base_dir / f"assets-{stamp}.{export_format}"


def _asset_in_profile(asset: Asset, profile_name: str) -> bool:
    return asset.source == f"scan_profile:{profile_name}"


def _newly_open_ports(
    before_assets: dict[str, Asset],
    scanned_assets: dict[str, Asset],
) -> dict[str, list[int]]:
    changes: dict[str, list[int]] = {}
    for ip, asset in scanned_assets.items():
        before = before_assets.get(ip)
        if before is None:
            continue
        previous_ports = set(before.open_ports)
        current_ports = set(asset.open_ports)
        added_ports = sorted(current_ports - previous_ports)
        if added_ports:
            changes[ip] = added_ports
    return changes


def _asset_diff_findings(
    *,
    task: TaskRun,
    new_assets: list[str],
    disappeared_assets: list[str],
    newly_open_ports: dict[str, list[int]],
) -> list[Finding]:
    findings: list[Finding] = []
    if new_assets:
        findings.append(
            Finding(
                id=f"finding-{task.id}-new-assets",
                task_id=task.id,
                category="configuration",
                severity=Severity.medium,
                title="发现新增资产",
                description=f"本次扫描发现 {len(new_assets)} 个历史资产库中不存在的 IP。",
                evidence_refs=new_assets,
                recommendation="确认这些设备是否为授权接入，并补充负责人、用途和资产类型。",
            )
        )
    if disappeared_assets:
        findings.append(
            Finding(
                id=f"finding-{task.id}-missing-assets",
                task_id=task.id,
                category="availability",
                severity=Severity.low,
                title="发现历史资产未出现在本次扫描",
                description=f"有 {len(disappeared_assets)} 个历史资产本次未被发现。",
                evidence_refs=disappeared_assets,
                recommendation="确认设备是否下线、改 IP、禁 Ping，或是否存在网络链路问题。",
            )
        )
    if newly_open_ports:
        evidence_refs = [
            f"{ip}:{port}"
            for ip, ports in newly_open_ports.items()
            for port in ports
        ]
        findings.append(
            Finding(
                id=f"finding-{task.id}-new-open-ports",
                task_id=task.id,
                category="security",
                severity=Severity.medium,
                title="发现新增开放端口",
                description=f"有 {len(evidence_refs)} 个端口相比历史资产记录新增开放。",
                evidence_refs=evidence_refs,
                recommendation="确认新增端口是否符合业务预期；不需要的服务应关闭或限制访问范围。",
            )
        )
    return findings


def _asset_diff_summary(
    *,
    profile_name: str,
    scanned_assets: list[Asset],
    results: list[ProbeResult],
    new_assets: list[str],
    disappeared_assets: list[str],
    newly_open_ports: dict[str, list[int]],
) -> dict[str, object]:
    new_port_count = sum(len(ports) for ports in newly_open_ports.values())
    changed = bool(new_assets or disappeared_assets or newly_open_ports)
    title = "资产变化检查发现变化" if changed else "资产变化检查未发现明显变化"
    likely_area = "资产接入、设备在线状态或服务端口发生变化" if changed else "本次扫描与历史资产记录基本一致"
    recommendation = (
        "复核新增设备、未出现设备和新增开放端口，确认是否符合预期。"
        if changed
        else "保持现有资产盘点节奏，定期重新执行变化检查。"
    )
    return {
        "scenario": "asset_diff",
        "scenario_label": "资产变化对比",
        "title": title,
        "likely_area": likely_area,
        "recommendation": recommendation,
        "profile": profile_name,
        "scanned_asset_count": len(scanned_assets),
        "probe_result_count": len(results),
        "new_assets": new_assets,
        "disappeared_assets": disappeared_assets,
        "newly_open_ports": newly_open_ports,
        "new_asset_count": len(new_assets),
        "disappeared_asset_count": len(disappeared_assets),
        "newly_open_port_count": new_port_count,
    }


def _asset_import_title(
    updated_assets: list[str],
    skipped_rows: list[dict[str, object]],
    error_rows: list[dict[str, object]],
) -> str:
    if error_rows:
        return "资产备注导入完成，但存在错误行"
    if skipped_rows:
        return "资产备注导入完成，但存在跳过行"
    return "资产备注导入完成"


def _clean_csv_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_tags(value: str | None) -> list[str]:
    cleaned = _clean_csv_value(value)
    if not cleaned:
        return []
    normalized = cleaned.replace("，", ",").replace(";", ",")
    tags: list[str] = []
    for item in normalized.split(","):
        tag = item.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def expand_scan_hosts(profile: ScanProfile) -> list[str]:
    hosts: list[str] = []
    for subnet in profile.subnets:
        try:
            network = ip_network(subnet, strict=False)
        except ValueError as exc:
            raise AssetScanError(f"invalid subnet: {subnet}") from exc
        hosts.extend(str(host) for host in network.hosts())
    return hosts


def _get_scan_profile(config: OpsConfig, profile_name: str) -> ScanProfile:
    try:
        return config.scan_profiles[profile_name]
    except KeyError as exc:
        raise AssetScanError(f"scan profile not found: {profile_name}") from exc


def _run_ping_checks(
    config: OpsConfig,
    profile: ScanProfile,
    task: TaskRun,
    hosts: list[str],
) -> list[ProbeResult]:
    if not profile.ping.enabled:
        return []

    workers = min(config.probe_defaults.concurrency, max(len(hosts), 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                ping_host,
                task_id=task.id,
                target=host,
                timeout_ms=profile.ping.timeout_ms,
                retries=profile.ping.retries,
            )
            for host in hosts
        ]
        return [future.result() for future in as_completed(futures)]


def _run_tcp_checks(
    config: OpsConfig,
    profile: ScanProfile,
    task: TaskRun,
    hosts: list[str],
) -> list[ProbeResult]:
    if not hosts or not profile.tcp_ports:
        return []

    timeout_ms = config.probe_defaults.timeout_ms
    jobs = [(host, port) for host in hosts for port in profile.tcp_ports]
    workers = min(config.probe_defaults.concurrency, max(len(jobs), 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                check_tcp_port,
                task_id=task.id,
                target=host,
                port=port,
                timeout_ms=timeout_ms,
            )
            for host, port in jobs
        ]
        return [future.result() for future in as_completed(futures)]


def _write_assets_csv(path: Path, assets: list[Asset]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "ip",
                "hostname",
                "mac",
                "vendor",
                "os_hint",
                "asset_type",
                "owner",
                "description",
                "tags",
                "open_ports",
                "status",
                "first_seen",
                "last_seen",
                "source",
            ]
        )
        for asset in assets:
            writer.writerow(
                [
                    asset.ip,
                    asset.hostname or "",
                    asset.mac or "",
                    asset.vendor or "",
                    asset.os_hint or "",
                    asset.asset_type or "",
                    asset.owner or "",
                    asset.description or "",
                    ",".join(asset.tags),
                    ",".join(str(port) for port in asset.open_ports),
                    asset.status,
                    asset.first_seen.isoformat(),
                    asset.last_seen.isoformat(),
                    asset.source,
                ]
            )


def _safe_reverse_dns(host: str) -> str | None:
    try:
        return socket.gethostbyaddr(host)[0]
    except OSError:
        return None

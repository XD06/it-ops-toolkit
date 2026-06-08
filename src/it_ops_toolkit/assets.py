from __future__ import annotations

import csv
import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path

from .config import OpsConfig, ScanProfile
from .models import Asset, ProbeResult, ProbeStatus, TaskRun
from .probes import check_tcp_port, ping_host
from .storage import SQLiteStore

MAX_SCAN_HOSTS = 1024


class AssetScanError(RuntimeError):
    pass


class AssetExportError(RuntimeError):
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

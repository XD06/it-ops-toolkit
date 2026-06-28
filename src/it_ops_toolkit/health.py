from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from .config import HealthTarget, OpsConfig
from .models import ProbeResult, TaskRun
from .probes import check_http_url, check_tcp_port, ping_host, resolve_hostname
from .storage import SQLiteStore


# 进度回调类型：(描述, 当前序号, 总数) -> None
ProgressCallback = Callable[[str, int, int], None]


class HealthCheckError(RuntimeError):
    pass


def run_health_check(
    *,
    config: OpsConfig,
    profile_name: str,
    task: TaskRun,
    store: SQLiteStore,
    progress_callback: ProgressCallback | None = None,
) -> list[ProbeResult]:
    try:
        profile = config.health_profiles[profile_name]
    except KeyError as exc:
        raise HealthCheckError(f"health profile not found: {profile_name}") from exc

    # 预计算总检查数
    total = sum(len(target.checks) for target in profile.targets)
    results: list[ProbeResult] = []
    index = 0
    for target in profile.targets:
        for check in target.checks:
            index += 1
            if progress_callback:
                desc = f"{check} -> {target.value}"
                progress_callback(desc, index, total)
            result = _run_target_check(config, task, target, check)
            if result:
                store.save_probe_result(result)
                results.append(result)
    return results


def _run_target_check(
    config: OpsConfig,
    task: TaskRun,
    target: HealthTarget,
    check: str,
) -> ProbeResult | None:
    timeout_ms = config.probe_defaults.timeout_ms
    value = str(target.value)

    if check == "ping":
        return ping_host(
            task_id=task.id,
            target=_host_for_network_check(value),
            timeout_ms=timeout_ms,
            retries=config.probe_defaults.retries,
        )
    if check == "dns":
        return resolve_hostname(
            task_id=task.id,
            hostname=_host_for_network_check(value),
            timeout_ms=timeout_ms,
        )
    if check == "http":
        if not value.startswith(("http://", "https://")):
            raise HealthCheckError(f"HTTP check requires URL target: {value}")
        return check_http_url(
            task_id=task.id,
            url=value,
            timeout_ms=timeout_ms,
        )
    if check == "tcp":
        host, port = _host_and_port_for_tcp(value, target.port)
        return check_tcp_port(
            task_id=task.id,
            target=host,
            port=port,
            timeout_ms=timeout_ms,
        )
    raise HealthCheckError(f"unsupported check type: {check}")


def _host_for_network_check(value: str) -> str:
    parsed = urlparse(value)
    if parsed.hostname:
        return parsed.hostname
    return value


def _host_and_port_for_tcp(value: str, configured_port: int | None) -> tuple[str, int]:
    parsed = urlparse(value)
    if parsed.hostname:
        port = configured_port or parsed.port
        if port is None:
            if parsed.scheme == "https":
                port = 443
            elif parsed.scheme == "http":
                port = 80
        if port is None:
            raise HealthCheckError(f"TCP check requires port: {value}")
        return parsed.hostname, port

    if configured_port is None:
        raise HealthCheckError(f"TCP check requires port: {value}")
    return value, configured_port

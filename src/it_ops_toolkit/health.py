from __future__ import annotations

from urllib.parse import urlparse

from .config import HealthTarget, OpsConfig
from .models import ProbeResult, TaskRun
from .probes import check_http_url, ping_host, resolve_hostname
from .storage import SQLiteStore


class HealthCheckError(RuntimeError):
    pass


def run_health_check(
    *,
    config: OpsConfig,
    profile_name: str,
    task: TaskRun,
    store: SQLiteStore,
) -> list[ProbeResult]:
    try:
        profile = config.health_profiles[profile_name]
    except KeyError as exc:
        raise HealthCheckError(f"health profile not found: {profile_name}") from exc

    results: list[ProbeResult] = []
    for target in profile.targets:
        for check in target.checks:
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
        raise HealthCheckError("TCP health checks require port support; not implemented yet")
    raise HealthCheckError(f"unsupported check type: {check}")


def _host_for_network_check(value: str) -> str:
    parsed = urlparse(value)
    if parsed.hostname:
        return parsed.hostname
    return value


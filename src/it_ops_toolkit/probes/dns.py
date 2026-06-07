from __future__ import annotations

import socket
from datetime import UTC, datetime
from time import monotonic

from it_ops_toolkit.models import ErrorInfo, ProbeResult, ProbeStatus, Target


def resolve_hostname(
    *,
    task_id: str,
    hostname: str,
    timeout_ms: int,
) -> ProbeResult:
    started = datetime.now(UTC)
    start = monotonic()
    original_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_ms / 1000)
    try:
        records = socket.getaddrinfo(hostname, None)
        addresses = sorted({record[4][0] for record in records})
        return ProbeResult(
            id=f"probe-dns-{hostname}",
            task_id=task_id,
            probe_type="dns",
            target=Target(type="hostname", value=hostname),
            status=ProbeStatus.success,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=int((monotonic() - start) * 1000),
            observations={"hostname": hostname, "addresses": addresses},
            evidence={"summary": f"{hostname} resolved to {', '.join(addresses)}"},
        )
    except socket.timeout as exc:
        return _failed_result(
            task_id=task_id,
            hostname=hostname,
            started=started,
            start=start,
            status=ProbeStatus.timeout,
            code="timeout",
            message="DNS lookup timed out",
            detail=str(exc),
        )
    except OSError as exc:
        return _failed_result(
            task_id=task_id,
            hostname=hostname,
            started=started,
            start=start,
            status=ProbeStatus.failed,
            code="dns_failed",
            message="DNS lookup failed",
            detail=str(exc),
        )
    finally:
        socket.setdefaulttimeout(original_timeout)


def _failed_result(
    *,
    task_id: str,
    hostname: str,
    started: datetime,
    start: float,
    status: ProbeStatus,
    code: str,
    message: str,
    detail: str,
) -> ProbeResult:
    return ProbeResult(
        id=f"probe-dns-{hostname}",
        task_id=task_id,
        probe_type="dns",
        target=Target(type="hostname", value=hostname),
        status=status,
        started_at=started,
        ended_at=datetime.now(UTC),
        duration_ms=int((monotonic() - start) * 1000),
        observations={"hostname": hostname},
        error=ErrorInfo(
            code=code,
            message=message,
            detail=detail,
            retryable=True,
        ),
        evidence={},
    )


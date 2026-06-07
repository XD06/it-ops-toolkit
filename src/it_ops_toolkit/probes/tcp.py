from __future__ import annotations

import socket
from datetime import UTC, datetime
from time import monotonic

from it_ops_toolkit.models import ErrorInfo, ProbeResult, ProbeStatus, Target


def check_tcp_port(
    *,
    task_id: str,
    target: str,
    port: int,
    timeout_ms: int,
) -> ProbeResult:
    started = datetime.now(UTC)
    start = monotonic()
    try:
        with socket.create_connection((target, port), timeout=timeout_ms / 1000):
            duration_ms = int((monotonic() - start) * 1000)
            return ProbeResult(
                id=f"probe-tcp-{target}-{port}",
                task_id=task_id,
                probe_type="tcp",
                target=Target(type="ip", value=target),
                status=ProbeStatus.success,
                started_at=started,
                ended_at=datetime.now(UTC),
                duration_ms=duration_ms,
                observations={"port": port, "open": True},
                evidence={"summary": f"TCP {port} connected"},
            )
    except TimeoutError as exc:
        return _failed_result(
            task_id=task_id,
            target=target,
            port=port,
            started=started,
            start=start,
            status=ProbeStatus.timeout,
            code="timeout",
            message="TCP connection timed out",
            detail=str(exc),
            retryable=True,
        )
    except OSError as exc:
        return _failed_result(
            task_id=task_id,
            target=target,
            port=port,
            started=started,
            start=start,
            status=ProbeStatus.failed,
            code="connection_failed",
            message="TCP connection failed",
            detail=str(exc),
            retryable=True,
        )


def _failed_result(
    *,
    task_id: str,
    target: str,
    port: int,
    started: datetime,
    start: float,
    status: ProbeStatus,
    code: str,
    message: str,
    detail: str,
    retryable: bool,
) -> ProbeResult:
    return ProbeResult(
        id=f"probe-tcp-{target}-{port}",
        task_id=task_id,
        probe_type="tcp",
        target=Target(type="ip", value=target),
        status=status,
        started_at=started,
        ended_at=datetime.now(UTC),
        duration_ms=int((monotonic() - start) * 1000),
        observations={"port": port, "open": False},
        error=ErrorInfo(
            code=code,
            message=message,
            detail=detail,
            retryable=retryable,
        ),
        evidence={},
    )


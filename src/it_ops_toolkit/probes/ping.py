from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime
from time import monotonic

from it_ops_toolkit.models import ErrorInfo, ProbeResult, ProbeStatus, Target


def ping_host(
    *,
    task_id: str,
    target: str,
    timeout_ms: int,
    retries: int,
) -> ProbeResult:
    started = datetime.now(UTC)
    start = monotonic()
    command = _ping_command(target, timeout_ms=timeout_ms, retries=retries)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max((timeout_ms / 1000) * max(retries, 1) + 1, 1),
            check=False,
        )
        duration_ms = int((monotonic() - start) * 1000)
        success = completed.returncode == 0
        return ProbeResult(
            id=f"probe-ping-{target}",
            task_id=task_id,
            probe_type="ping",
            target=Target(type="ip", value=target),
            status=ProbeStatus.success if success else ProbeStatus.failed,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=duration_ms,
            observations={
                "reachable": success,
                "return_code": completed.returncode,
            },
            error=None
            if success
            else ErrorInfo(
                code="ping_failed",
                message="Ping failed",
                detail=_trim_output(completed.stderr or completed.stdout),
                retryable=True,
            ),
            evidence={"summary": _trim_output(completed.stdout)},
        )
    except subprocess.TimeoutExpired as exc:
        return ProbeResult(
            id=f"probe-ping-{target}",
            task_id=task_id,
            probe_type="ping",
            target=Target(type="ip", value=target),
            status=ProbeStatus.timeout,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=int((monotonic() - start) * 1000),
            observations={"reachable": False},
            error=ErrorInfo(
                code="timeout",
                message="Ping timed out",
                detail=str(exc),
                retryable=True,
            ),
            evidence={},
        )


def _ping_command(target: str, *, timeout_ms: int, retries: int) -> list[str]:
    count = max(retries, 1)
    if platform.system().lower() == "windows":
        return ["ping", "-n", str(count), "-w", str(timeout_ms), target]
    timeout_seconds = max(int(timeout_ms / 1000), 1)
    return ["ping", "-c", str(count), "-W", str(timeout_seconds), target]


def _trim_output(output: str, *, limit: int = 500) -> str:
    output = output.strip()
    if len(output) <= limit:
        return output
    return output[:limit] + "..."


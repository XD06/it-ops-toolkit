from __future__ import annotations

import platform
import re
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
        raw_output = completed.stdout or ""
        stats = _parse_ping_stats(raw_output)
        success = completed.returncode == 0

        observations: dict[str, object] = {
            "reachable": success,
            "return_code": completed.returncode,
        }
        if stats is not None:
            observations.update(stats)

        return ProbeResult(
            id=f"probe-ping-{target}",
            task_id=task_id,
            probe_type="ping",
            target=Target(type="ip", value=target),
            status=ProbeStatus.success if success else ProbeStatus.failed,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=duration_ms,
            observations=observations,
            error=None
            if success
            else ErrorInfo(
                code="ping_failed",
                message="Ping failed",
                detail=_trim_output(completed.stderr or completed.stdout),
                retryable=True,
            ),
            evidence={"summary": _trim_output(raw_output)},
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


def _parse_ping_stats(output: str) -> dict[str, object] | None:
    """Parse ping output to extract packet loss and RTT statistics.

    Supports both Windows and Linux/macOS ping output formats.
    Returns None if no statistics can be extracted.
    """
    if not output or not output.strip():
        return None

    windows_stats = _parse_windows_ping_stats(output)
    if windows_stats:
        return windows_stats

    linux_stats = _parse_linux_ping_stats(output)
    if linux_stats:
        return linux_stats

    return None


def _parse_windows_ping_stats(output: str) -> dict[str, object] | None:
    stats: dict[str, object] = {}

    # Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)
    packet_match = re.search(
        r"Sent\s*=\s*(\d+).*?Received\s*=\s*(\d+).*?Lost\s*=\s*(\d+)\s*\((\d+)%\s*loss\)",
        output,
        re.IGNORECASE,
    )
    if packet_match:
        stats["packets_sent"] = int(packet_match.group(1))
        stats["packets_received"] = int(packet_match.group(2))
        stats["packets_lost"] = int(packet_match.group(3))
        stats["packet_loss_percent"] = float(packet_match.group(4))

    # Minimum = 11ms, Maximum = 15ms, Average = 12ms
    rtt_match = re.search(
        r"Minimum\s*=\s*(\d+)\s*ms.*?Maximum\s*=\s*(\d+)\s*ms.*?Average\s*=\s*(\d+)\s*ms",
        output,
        re.IGNORECASE,
    )
    if rtt_match:
        stats["min_rtt_ms"] = float(rtt_match.group(1))
        stats["max_rtt_ms"] = float(rtt_match.group(2))
        stats["avg_rtt_ms"] = float(rtt_match.group(3))

    if not stats:
        return None
    return stats


def _parse_linux_ping_stats(output: str) -> dict[str, object] | None:
    stats: dict[str, object] = {}

    # 4 packets transmitted, 4 received, 0% packet loss
    packet_match = re.search(
        r"(\d+)\s+packets\s+transmitted.*?(\d+)\s+received.*?(?:(\d+(?:\.\d+)?)%\s+packet\s+loss)?",
        output,
        re.IGNORECASE,
    )
    if packet_match:
        sent = int(packet_match.group(1))
        received = int(packet_match.group(2))
        loss_str = packet_match.group(3)
        loss_percent = float(loss_str) if loss_str else _calc_loss_percent(sent, received)

        stats["packets_sent"] = sent
        stats["packets_received"] = received
        stats["packets_lost"] = sent - received
        stats["packet_loss_percent"] = loss_percent

    # rtt min/avg/max/mdev = 11.000/12.950/15.200/1.525 ms
    # Also handle older format: round-trip min/avg/max = 11.0/12.9/15.2 ms
    rtt_match = re.search(
        r"(?:rtt|round-trip)\s+min/avg/max(?:/mdev)?\s*=\s*"
        r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)(?:/\d+(?:\.\d+)?)?\s*ms",
        output,
        re.IGNORECASE,
    )
    if rtt_match:
        stats["min_rtt_ms"] = float(rtt_match.group(1))
        stats["avg_rtt_ms"] = float(rtt_match.group(2))
        stats["max_rtt_ms"] = float(rtt_match.group(3))

    if not stats:
        return None
    return stats


def _calc_loss_percent(sent: int, received: int) -> float:
    if sent <= 0:
        return 0.0
    return round((sent - received) / sent * 100, 1)


def _trim_output(output: str, *, limit: int = 500) -> str:
    output = output.strip()
    if len(output) <= limit:
        return output
    return output[:limit] + "..."

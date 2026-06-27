from __future__ import annotations

import socket
import ssl
from datetime import UTC, datetime
from time import monotonic

from it_ops_toolkit.models import ErrorInfo, ProbeResult, ProbeStatus, Target


def check_tls_certificate(
    *,
    task_id: str,
    hostname: str,
    port: int = 443,
    timeout_ms: int,
) -> ProbeResult:
    started = datetime.now(UTC)
    start = monotonic()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout_ms / 1000) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls:
                cert = tls.getpeercert()
        not_after_raw = str(cert.get("notAfter", ""))
        expires_at = _parse_not_after(not_after_raw)
        now = datetime.now(UTC)
        days_remaining = (expires_at - now).days
        return ProbeResult(
            id=f"probe-tls-cert-{hostname}-{port}",
            task_id=task_id,
            probe_type="tls_cert",
            target=Target(type="service", value=f"{hostname}:{port}"),
            status=ProbeStatus.success,
            started_at=started,
            ended_at=now,
            duration_ms=int((monotonic() - start) * 1000),
            observations={
                "hostname": hostname,
                "port": port,
                "subject": cert.get("subject", ()),
                "issuer": cert.get("issuer", ()),
                "not_after": not_after_raw,
                "expires_at": expires_at.isoformat(),
                "days_remaining": days_remaining,
            },
            evidence={"summary": f"TLS certificate expires in {days_remaining} days"},
        )
    except (OSError, ssl.SSLError, ValueError) as exc:
        return ProbeResult(
            id=f"probe-tls-cert-{hostname}-{port}",
            task_id=task_id,
            probe_type="tls_cert",
            target=Target(type="service", value=f"{hostname}:{port}"),
            status=ProbeStatus.failed,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=int((monotonic() - start) * 1000),
            observations={"hostname": hostname, "port": port},
            error=ErrorInfo(
                code="tls_certificate_failed",
                message="TLS certificate check failed",
                detail=str(exc),
                retryable=True,
            ),
            evidence={},
        )


def _parse_not_after(value: str) -> datetime:
    if not value:
        raise ValueError("certificate notAfter is missing")
    parsed = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z")
    return parsed.replace(tzinfo=UTC)

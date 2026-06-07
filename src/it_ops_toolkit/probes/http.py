from __future__ import annotations

import ssl
from datetime import UTC, datetime
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from it_ops_toolkit.models import ErrorInfo, ProbeResult, ProbeStatus, Target


def check_http_url(
    *,
    task_id: str,
    url: str,
    timeout_ms: int,
) -> ProbeResult:
    started = datetime.now(UTC)
    start = monotonic()
    request = Request(url, method="GET", headers={"User-Agent": "it-ops-toolkit/0.1"})
    try:
        with urlopen(request, timeout=timeout_ms / 1000) as response:
            status_code = response.getcode()
            return ProbeResult(
                id=f"probe-http-{_safe_id(url)}",
                task_id=task_id,
                probe_type="http",
                target=Target(type="url", value=url),
                status=ProbeStatus.success,
                started_at=started,
                ended_at=datetime.now(UTC),
                duration_ms=int((monotonic() - start) * 1000),
                observations={
                    "url": url,
                    "status_code": status_code,
                    "final_url": response.geturl(),
                    "ok": 200 <= status_code < 400,
                },
                evidence={"summary": f"HTTP {status_code}"},
            )
    except HTTPError as exc:
        return _failed_result(
            task_id=task_id,
            url=url,
            started=started,
            start=start,
            code="http_error",
            message="HTTP request returned error status",
            detail=f"HTTP {exc.code}",
        )
    except (URLError, TimeoutError, ssl.SSLError) as exc:
        return _failed_result(
            task_id=task_id,
            url=url,
            started=started,
            start=start,
            code="http_failed",
            message="HTTP request failed",
            detail=str(exc),
        )


def _failed_result(
    *,
    task_id: str,
    url: str,
    started: datetime,
    start: float,
    code: str,
    message: str,
    detail: str,
) -> ProbeResult:
    return ProbeResult(
        id=f"probe-http-{_safe_id(url)}",
        task_id=task_id,
        probe_type="http",
        target=Target(type="url", value=url),
        status=ProbeStatus.failed,
        started_at=started,
        ended_at=datetime.now(UTC),
        duration_ms=int((monotonic() - start) * 1000),
        observations={"url": url, "ok": False},
        error=ErrorInfo(
            code=code,
            message=message,
            detail=detail,
            retryable=True,
        ),
        evidence={},
    )


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-").lower()


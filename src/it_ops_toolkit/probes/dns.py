from __future__ import annotations

import re
import socket
import subprocess
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


def resolve_with_server(
    *,
    task_id: str,
    hostname: str,
    dns_server: str,
    timeout_ms: int,
) -> ProbeResult:
    """Resolve a hostname using a specific DNS server via nslookup.

    This is useful for comparing results from multiple DNS servers
    (e.g. internal DNS vs public DNS).
    """
    started = datetime.now(UTC)
    start = monotonic()
    command = ["nslookup", hostname, dns_server]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(timeout_ms / 1000, 2),
            check=False,
        )
        duration_ms = int((monotonic() - start) * 1000)
        raw_output = completed.stdout or ""
        parsed = _parse_nslookup_output(raw_output)

        addresses = parsed.get("addresses", [])
        server_name = parsed.get("server_name", dns_server)
        server_address = parsed.get("server_address", dns_server)

        # nslookup returns non-zero on some errors but not all;
        # check for explicit error markers in output
        has_error = _has_nslookup_error(raw_output, completed.returncode)

        if has_error or not addresses:
            error_detail = _nslookup_error_detail(raw_output, completed.stderr or "")
            return ProbeResult(
                id=f"probe-dns-{hostname}-{dns_server}",
                task_id=task_id,
                probe_type="dns",
                target=Target(type="hostname", value=hostname),
                status=ProbeStatus.failed,
                started_at=started,
                ended_at=datetime.now(UTC),
                duration_ms=duration_ms,
                observations={
                    "hostname": hostname,
                    "dns_server": dns_server,
                    "server_name": server_name,
                    "server_address": server_address,
                    "addresses": [],
                },
                error=ErrorInfo(
                    code="dns_lookup_failed",
                    message=f"DNS lookup via {dns_server} failed",
                    detail=error_detail,
                    retryable=True,
                ),
                evidence={"summary": _trim_output(raw_output)},
            )

        return ProbeResult(
            id=f"probe-dns-{hostname}-{dns_server}",
            task_id=task_id,
            probe_type="dns",
            target=Target(type="hostname", value=hostname),
            status=ProbeStatus.success,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=duration_ms,
            observations={
                "hostname": hostname,
                "dns_server": dns_server,
                "server_name": server_name,
                "server_address": server_address,
                "addresses": sorted(addresses),
            },
            evidence={"summary": _trim_output(raw_output)},
        )
    except subprocess.TimeoutExpired as exc:
        return ProbeResult(
            id=f"probe-dns-{hostname}-{dns_server}",
            task_id=task_id,
            probe_type="dns",
            target=Target(type="hostname", value=hostname),
            status=ProbeStatus.timeout,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=int((monotonic() - start) * 1000),
            observations={
                "hostname": hostname,
                "dns_server": dns_server,
                "addresses": [],
            },
            error=ErrorInfo(
                code="timeout",
                message=f"DNS lookup via {dns_server} timed out",
                detail=str(exc),
                retryable=True,
            ),
            evidence={},
        )
    except OSError as exc:
        return ProbeResult(
            id=f"probe-dns-{hostname}-{dns_server}",
            task_id=task_id,
            probe_type="dns",
            target=Target(type="hostname", value=hostname),
            status=ProbeStatus.failed,
            started_at=started,
            ended_at=datetime.now(UTC),
            duration_ms=int((monotonic() - start) * 1000),
            observations={
                "hostname": hostname,
                "dns_server": dns_server,
                "addresses": [],
            },
            error=ErrorInfo(
                code="nslookup_not_found",
                message="nslookup command not found",
                detail=str(exc),
                retryable=True,
            ),
            evidence={},
        )


def _parse_nslookup_output(output: str) -> dict[str, object]:
    """Parse nslookup output to extract DNS server info and resolved addresses.

    Supports both Windows and Linux nslookup output formats.
    """
    result: dict[str, object] = {
        "server_name": "",
        "server_address": "",
        "addresses": [],
    }

    if not output or not output.strip():
        return result

    # Server:  dns.google  (or)  Server:		8.8.8.8
    # Address:  8.8.8.8  (or)  Address:	8.8.8.8#53
    server_match = re.search(
        r"Server:\s*(\S+).*?Address:\s*([^\s#]+)",
        output,
        re.IGNORECASE | re.DOTALL,
    )
    if server_match:
        result["server_name"] = server_match.group(1)
        result["server_address"] = server_match.group(2)

    # Extract resolved addresses
    # Windows format:
    #   Name:    www.baidu.com
    #   Addresses:  110.242.68.4
    #               110.242.68.3
    #
    # Linux format:
    #   Name:	www.baidu.com
    #   Address: 110.242.68.4
    #   Name:	www.baidu.com
    #   Address: 110.242.68.3

    addresses: list[str] = []

    # Windows format:
    #   Addresses:  110.242.68.4
    #               110.242.68.3
    # The first address is on the same line, followed by continuation lines
    win_match = re.search(
        r"Addresses:\s*(.+?)(?=\n\s*\n|\n\S|\Z)",
        output,
        re.IGNORECASE | re.DOTALL,
    )
    if win_match:
        block = win_match.group(1)
        for token in re.findall(r"\S+", block):
            if _is_ip_address(token) and token != result.get("server_address"):
                addresses.append(token)

    # Linux format: individual "Address: <ip>" lines after Name section
    if not addresses:
        for match in re.finditer(r"^Address:\s*(\S+)", output, re.IGNORECASE | re.MULTILINE):
            ip = match.group(1)
            # Skip the server's own address line
            if _is_ip_address(ip) and ip != result.get("server_address"):
                addresses.append(ip)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for addr in addresses:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)

    result["addresses"] = unique
    return result


def _has_nslookup_error(output: str, return_code: int) -> bool:
    """Check if nslookup output indicates an error."""
    if return_code != 0:
        return True
    lower = output.lower()
    if "can't find" in lower:
        return True
    if "nxdomain" in lower:
        return True
    if "no answer" in lower and "non-authoritative" not in lower:
        return True
    if "** server can't find" in lower:
        return True
    return False


def _nslookup_error_detail(stdout: str, stderr: str) -> str:
    """Extract error detail from nslookup output."""
    detail = stderr.strip() or stdout.strip()
    if not detail:
        return "Unknown nslookup error"
    # Try to find the specific error line
    for line in detail.splitlines():
        lower = line.lower()
        if "can't find" in lower or "nxdomain" in lower or "no answer" in lower or "error" in lower:
            return line.strip()
    return detail[:300]


def _is_ip_address(value: str) -> bool:
    """Check if a string looks like an IPv4 or IPv6 address."""
    try:
        socket.inet_aton(value)
        return True
    except OSError:
        pass
    if ":" in value and all(
        part == "" or all(c in "0123456789abcdefABCDEF" for c in part)
        for part in value.split(":")
    ):
        return True
    return False


def _trim_output(output: str, *, limit: int = 500) -> str:
    output = output.strip()
    if len(output) <= limit:
        return output
    return output[:limit] + "..."


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

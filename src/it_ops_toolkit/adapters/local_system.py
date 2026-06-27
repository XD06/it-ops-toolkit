from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime
from time import monotonic
from typing import Any


def flush_dns_cache(
    *,
    dry_run: bool,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    command = _flush_dns_command()
    started_at = datetime.now(UTC)
    start = monotonic()

    if dry_run:
        return {
            "action": "flush_dns_cache",
            "target": "localhost",
            "status": "planned",
            "dry_run": True,
            "executed": False,
            "command": command,
            "started_at": started_at.isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_ms": int((monotonic() - start) * 1000),
            "return_code": None,
            "stdout": "",
            "stderr": "",
            "error": None,
        }

    if command is None:
        return {
            "action": "flush_dns_cache",
            "target": "localhost",
            "status": "failed",
            "dry_run": False,
            "executed": False,
            "command": None,
            "started_at": started_at.isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_ms": int((monotonic() - start) * 1000),
            "return_code": None,
            "stdout": "",
            "stderr": "",
            "error": "flush DNS cache is currently supported only on Windows",
        }

    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "action": "flush_dns_cache",
            "target": "localhost",
            "status": "timeout",
            "dry_run": False,
            "executed": True,
            "command": command,
            "started_at": started_at.isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_ms": int((monotonic() - start) * 1000),
            "return_code": None,
            "stdout": _trim_output(exc.stdout or ""),
            "stderr": _trim_output(exc.stderr or ""),
            "error": "flush DNS cache timed out",
        }

    success = completed.returncode == 0
    return {
        "action": "flush_dns_cache",
        "target": "localhost",
        "status": "success" if success else "failed",
        "dry_run": False,
        "executed": True,
        "command": command,
        "started_at": started_at.isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "duration_ms": int((monotonic() - start) * 1000),
        "return_code": completed.returncode,
        "stdout": _trim_output(completed.stdout),
        "stderr": _trim_output(completed.stderr),
        "error": None if success else "flush DNS cache command failed",
    }


def _flush_dns_command() -> list[str] | None:
    if platform.system().lower() != "windows":
        return None
    return ["ipconfig", "/flushdns"]


def _trim_output(value: str, *, limit: int = 500) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."

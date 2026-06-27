from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import OpsConfig
from .models import ProbeResult, TaskRun
from .probes import check_http_url
from .storage import SQLiteStore


class HealthHttpMatrixError(RuntimeError):
    pass


def run_health_http_matrix(
    *,
    config: OpsConfig,
    task: TaskRun,
    store: SQLiteStore,
    csv_path: Path,
) -> dict[str, Any]:
    rows = _read_targets(csv_path)
    results: list[ProbeResult] = []
    entries: list[dict[str, Any]] = []

    for row in rows:
        entry = {
            "row": row["row"],
            "name": row["name"],
            "url": row["url"],
            "method": row["method"],
        }
        try:
            result = check_http_url(
                task_id=task.id,
                url=row["url"],
                timeout_ms=config.probe_defaults.timeout_ms,
                method=row["method"],
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            entry.update(
                {
                    "status": "error",
                    "error": str(exc),
                    "duration_ms": None,
                }
            )
            entries.append(entry)
            continue

        store.save_probe_result(result)
        results.append(result)
        entry.update(
            {
                "status": result.status.value,
                "error": result.error.message if result.error else "",
                "duration_ms": result.duration_ms,
            }
        )
        entries.append(entry)

    summary = {
        "scenario": "health_http_matrix",
        "scenario_label": "批量 HTTP 端口测试",
        "title": _matrix_title(entries),
        "likely_area": "目标 HTTP/HTTPS 可达性",
        "recommendation": "复核失败 URL 的网络路径、服务状态和证书/代理情况。",
        "source_file": str(csv_path),
        "target_count": len(rows),
        "result_count": len(results),
        "entries": entries,
        "result_ids": [result.id for result in results],
        "success_count": sum(1 for entry in entries if entry["status"] == "success"),
        "failed_count": sum(
            1 for entry in entries if entry["status"] not in {"success"}
        ),
    }
    return summary


def _read_targets(csv_path: Path) -> list[dict[str, Any]]:
    if not csv_path.exists():
        raise HealthHttpMatrixError(f"http matrix file not found: {csv_path}")

    targets: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        required = {"url"}
        missing = sorted(required - fieldnames)
        if missing:
            raise HealthHttpMatrixError(
                "http matrix CSV must include columns: url"
            )
        for row_number, row in enumerate(reader, start=2):
            url = _clean(row.get("url"))
            if not url:
                raise HealthHttpMatrixError(f"row {row_number} requires url")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            method = (_clean(row.get("method")) or "GET").upper()
            if method not in {"GET", "HEAD"}:
                raise HealthHttpMatrixError(
                    f"row {row_number} has unsupported method for read-only check: {method}"
                )
            targets.append(
                {
                    "row": row_number,
                    "name": _clean(row.get("name")) or url,
                    "url": url,
                    "method": method,
                }
            )
    return targets


def _matrix_title(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "批量 HTTP 端口测试未包含目标"
    if any(entry["status"] != "success" for entry in entries):
        return "批量 HTTP 端口测试发现异常"
    return "批量 HTTP 端口测试正常"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None

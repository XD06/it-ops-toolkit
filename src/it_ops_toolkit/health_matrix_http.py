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
        entry: dict[str, Any] = {
            "row": row["row"],
            "name": row["name"],
            "url": row["url"],
            "method": row["method"],
            "owner": row["owner"],
            "description": row["description"],
            "expected_status": row["expected_status_raw"],
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
                    "http_status_code": None,
                    "status_match": _status_matches(None, row["expected_status"]),
                    "error": str(exc),
                    "duration_ms": None,
                }
            )
            entries.append(entry)
            continue

        store.save_probe_result(result)
        results.append(result)
        http_status_code = result.observations.get("status_code")
        if http_status_code is not None:
            http_status_code = int(http_status_code)
        entry.update(
            {
                "status": result.status.value,
                "http_status_code": http_status_code,
                "status_match": _status_matches(http_status_code, row["expected_status"]),
                "error": result.error.message if result.error else "",
                "duration_ms": result.duration_ms,
            }
        )
        entries.append(entry)

    mismatch_count = sum(
        1
        for entry in entries
        if entry.get("expected_status") and not entry.get("status_match", True)
    )
    summary = {
        "scenario": "health_http_matrix",
        "scenario_label": "批量 HTTP 端口测试",
        "title": _matrix_title(entries),
        "likely_area": "目标 HTTP/HTTPS 可达性",
        "recommendation": "复核失败 URL 的网络路径、服务状态、状态码预期和证书/代理情况。",
        "source_file": str(csv_path),
        "target_count": len(rows),
        "result_count": len(results),
        "entries": entries,
        "result_ids": [result.id for result in results],
        "success_count": sum(1 for entry in entries if entry["status"] == "success"),
        "failed_count": sum(
            1 for entry in entries if entry["status"] not in {"success"}
        ),
        "mismatch_count": mismatch_count,
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
            expected_status_raw = _clean(row.get("expected_status")) or ""
            if expected_status_raw:
                try:
                    expected_status = parse_expected_status(expected_status_raw)
                except ValueError as exc:
                    raise HealthHttpMatrixError(
                        f"row {row_number} has invalid expected_status: {expected_status_raw}"
                    ) from exc
            else:
                expected_status = None
            targets.append(
                {
                    "row": row_number,
                    "name": _clean(row.get("name")) or url,
                    "url": url,
                    "method": method,
                    "owner": _clean(row.get("owner")) or "",
                    "description": _clean(row.get("description")) or "",
                    "expected_status_raw": expected_status_raw,
                    "expected_status": expected_status,
                }
            )
    return targets


def parse_expected_status(value: str) -> list[tuple[int, int]] | None:
    """解析期望状态码配置，返回范围列表。

    支持格式：
    - 单个状态码：``200``
    - 范围：``200-299``
    - 多个值：``200,301,302``
    - 范围与单个值混合：``200-299,404``

    留空时返回 ``None``，表示不检查。
    """
    value = value.strip()
    if not value:
        return None
    ranges: list[tuple[int, int]] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low_text, high_text = part.split("-", 1)
            low = int(low_text.strip())
            high = int(high_text.strip())
            if low > high:
                raise ValueError(f"invalid range: {part}")
            ranges.append((low, high))
        else:
            ranges.append((int(part), int(part)))
    if not ranges:
        raise ValueError("empty expected_status")
    return ranges


def _status_matches(
    status_code: int | None,
    expected: list[tuple[int, int]] | None,
) -> bool:
    if expected is None:
        return True
    if status_code is None:
        return False
    return any(low <= status_code <= high for low, high in expected)


def _matrix_title(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "批量 HTTP 端口测试未包含目标"
    has_mismatch = any(
        entry.get("expected_status") and not entry.get("status_match", True)
        for entry in entries
    )
    if has_mismatch:
        return "批量 HTTP 端口测试发现状态码不匹配"
    if any(entry["status"] != "success" for entry in entries):
        return "批量 HTTP 端口测试发现异常"
    return "批量 HTTP 端口测试正常"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None

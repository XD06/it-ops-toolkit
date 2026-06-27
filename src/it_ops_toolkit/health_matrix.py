from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .config import OpsConfig
from .models import ProbeResult, TaskRun
from .probes import check_tcp_port
from .storage import SQLiteStore


class HealthMatrixError(RuntimeError):
    pass


def run_health_tcp_matrix(
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
            "host": row["host"],
            "port": row["port"],
        }
        try:
            result = check_tcp_port(
                task_id=task.id,
                target=row["host"],
                port=row["port"],
                timeout_ms=config.probe_defaults.timeout_ms,
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
        "scenario": "health_tcp_matrix",
        "scenario_label": "批量 TCP 端口测试",
        "title": _matrix_title(entries),
        "likely_area": "目标端口可达性",
        "recommendation": "复核失败目标的网络路径、服务监听和防火墙策略。",
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
        raise HealthMatrixError(f"tcp matrix file not found: {csv_path}")

    targets: list[dict[str, Any]] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        required = {"host", "port"}
        missing = sorted(required - fieldnames)
        if missing:
            raise HealthMatrixError(
                "tcp matrix CSV must include columns: " + ", ".join(sorted(required))
            )
        for row_number, row in enumerate(reader, start=2):
            host = _clean(row.get("host"))
            port_text = _clean(row.get("port"))
            if not host or not port_text:
                raise HealthMatrixError(f"row {row_number} requires host and port")
            try:
                port = int(port_text)
            except ValueError as exc:
                raise HealthMatrixError(f"row {row_number} has invalid port: {port_text}") from exc
            if port < 1 or port > 65535:
                raise HealthMatrixError(f"row {row_number} has invalid port: {port}")
            targets.append(
                {
                    "row": row_number,
                    "name": _clean(row.get("name")) or host,
                    "host": host,
                    "port": port,
                }
            )
    return targets


def _matrix_title(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "批量 TCP 端口测试未包含目标"
    if any(entry["status"] != "success" for entry in entries):
        return "批量 TCP 端口测试发现异常"
    return "批量 TCP 端口测试正常"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None

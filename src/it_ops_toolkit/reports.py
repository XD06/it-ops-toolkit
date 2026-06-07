from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import Asset, ProbeResult, Report, TaskRun
from .storage import SQLiteStore, TaskRecordNotFound


class ReportError(RuntimeError):
    pass


def generate_report(
    *,
    store: SQLiteStore,
    source_task_id: str,
    output_dir: Path,
    report_format: str,
) -> Report:
    try:
        source_task = store.get_task_run(source_task_id)
    except TaskRecordNotFound as exc:
        raise ReportError(f"source task not found: {source_task_id}") from exc

    if report_format not in {"markdown", "csv", "json"}:
        raise ReportError(f"unsupported report format: {report_format}")

    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = f"report-{uuid4().hex[:12]}"
    report_type = _report_type_for_task(source_task)
    path = output_dir / f"{report_id}.{_extension_for_format(report_format)}"
    probe_results = store.list_probe_results_for_task(source_task.id)
    assets = _assets_for_task(store, source_task)

    if report_format == "markdown":
        path.write_text(
            _render_markdown(source_task, probe_results, assets),
            encoding="utf-8",
        )
    elif report_format == "csv":
        _write_csv(path, source_task, probe_results, assets)
    elif report_format == "json":
        path.write_text(
            _render_json(source_task, probe_results, assets),
            encoding="utf-8",
        )

    report = Report(
        id=report_id,
        source_task_id=source_task.id,
        report_type=report_type,
        title=f"{source_task.task_type} report",
        format=report_format,
        path=str(path),
        summary=f"{source_task.task_type}: {len(probe_results)} probe results",
        generated_at=datetime.now(UTC),
    )
    store.save_report(report)
    return report


def _report_type_for_task(task: TaskRun) -> str:
    if task.task_type == "asset_scan":
        return "asset"
    if task.task_type == "health_check":
        return "health"
    return "generic"


def _extension_for_format(report_format: str) -> str:
    return {"markdown": "md", "csv": "csv", "json": "json"}[report_format]


def _assets_for_task(store: SQLiteStore, task: TaskRun) -> list[Asset]:
    assets: list[Asset] = []
    if task.task_type != "asset_scan":
        return assets
    for target_ref in task.target_refs:
        asset = store.get_asset_by_ip(target_ref)
        if asset:
            assets.append(asset)
    return assets


def _render_markdown(
    task: TaskRun,
    probe_results: list[ProbeResult],
    assets: list[Asset],
) -> str:
    lines = [
        f"# {task.task_type} 报告",
        "",
        "## 任务信息",
        "",
        f"- 任务 ID：`{task.id}`",
        f"- 任务类型：`{task.task_type}`",
        f"- 状态：`{task.status.value}`",
        f"- 风险等级：`{task.risk_level.value}`",
        f"- 开始时间：`{task.started_at.isoformat()}`",
        f"- 结束时间：`{task.ended_at.isoformat() if task.ended_at else ''}`",
        "",
    ]

    if assets:
        lines.extend(
            [
                "## 资产结果",
                "",
                "| IP | 主机名 | 状态 | 开放端口 | 最后发现 |",
                "|---|---|---|---|---|",
            ]
        )
        for asset in assets:
            lines.append(
                "| "
                + " | ".join(
                    [
                        asset.ip,
                        asset.hostname or "",
                        asset.status,
                        ",".join(str(port) for port in asset.open_ports),
                        asset.last_seen.isoformat(),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## 探测结果",
            "",
            "| 类型 | 目标 | 状态 | 耗时 ms | 观察值 | 错误 |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for result in probe_results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.probe_type,
                    result.target.value,
                    result.status.value,
                    str(result.duration_ms or ""),
                    _compact_json(result.observations),
                    result.error.message if result.error else "",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _write_csv(
    path: Path,
    task: TaskRun,
    probe_results: list[ProbeResult],
    assets: list[Asset],
) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        if assets:
            writer.writerow(["ip", "hostname", "status", "open_ports", "last_seen"])
            for asset in assets:
                writer.writerow(
                    [
                        asset.ip,
                        asset.hostname or "",
                        asset.status,
                        ",".join(str(port) for port in asset.open_ports),
                        asset.last_seen.isoformat(),
                    ]
                )
            return

        writer.writerow(["probe_type", "target", "status", "duration_ms", "observations", "error"])
        for result in probe_results:
            writer.writerow(
                [
                    result.probe_type,
                    result.target.value,
                    result.status.value,
                    result.duration_ms or "",
                    _compact_json(result.observations),
                    result.error.message if result.error else "",
                ]
            )


def _render_json(
    task: TaskRun,
    probe_results: list[ProbeResult],
    assets: list[Asset],
) -> str:
    payload = {
        "task": task.model_dump(mode="json"),
        "assets": [asset.model_dump(mode="json") for asset in assets],
        "probe_results": [result.model_dump(mode="json") for result in probe_results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


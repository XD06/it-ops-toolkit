from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .config import OpsConfig
from .models import Asset, ProbeResult, TaskRun
from .storage import SQLiteStore


class ExportError(RuntimeError):
    pass


def export_bundle(
    *,
    config: OpsConfig,
    store: SQLiteStore,
    output_path: Path,
    task_id: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tasks = _tasks_for_bundle(store, task_id=task_id)
    task_ids = {task.id for task in tasks}
    probe_results = _probe_results_for_bundle(store, task_ids=task_ids)
    findings = _findings_for_bundle(store, task_ids=task_ids)
    local_snapshots = _local_snapshots_for_bundle(store, task_ids=task_ids)
    assets = store.list_assets()

    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "diagnostic-bundle"
        root.mkdir(parents=True, exist_ok=True)

        _write_json(root / "config-summary.json", _config_summary(config))
        _write_json(root / "tasks.json", [task.model_dump(mode="json") for task in tasks])
        _write_json(root / "assets.json", [asset.model_dump(mode="json") for asset in assets])
        _write_json(
            root / "probe-results.json",
            [result.model_dump(mode="json") for result in probe_results],
        )
        _write_json(root / "findings.json", [finding.model_dump(mode="json") for finding in findings])
        _write_json(
            root / "local-snapshots.json",
            [snapshot.model_dump(mode="json") for snapshot in local_snapshots],
        )
        (root / "summary.md").write_text(
            _render_summary(
                tasks=tasks,
                assets=assets,
                probe_results=probe_results,
                findings=findings,
                local_snapshots=local_snapshots,
            ),
            encoding="utf-8",
        )

        with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in root.rglob("*"):
                if file.is_file():
                    archive.write(file, file.relative_to(root))

    return output_path


def default_bundle_path(base_dir: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return base_dir / f"diagnostic-bundle-{stamp}.zip"


def _tasks_for_bundle(store: SQLiteStore, *, task_id: str | None) -> list[TaskRun]:
    if task_id:
        return [store.get_task_run(task_id)]
    return store.list_task_runs(limit=200)


def _probe_results_for_bundle(store: SQLiteStore, *, task_ids: set[str]) -> list[ProbeResult]:
    if not task_ids:
        return []
    results: list[ProbeResult] = []
    for task_id in task_ids:
        results.extend(store.list_probe_results_for_task(task_id))
    return results


def _findings_for_bundle(store: SQLiteStore, *, task_ids: set[str]):
    if not task_ids:
        return []
    findings = []
    for task_id in task_ids:
        findings.extend(store.list_findings_for_task(task_id))
    return findings


def _local_snapshots_for_bundle(store: SQLiteStore, *, task_ids: set[str]):
    if not task_ids:
        return []
    snapshots = []
    for task_id in task_ids:
        snapshots.extend(store.list_local_snapshots_for_task(task_id))
    return snapshots


def _config_summary(config: OpsConfig) -> dict[str, object]:
    return {
        "app": config.app.model_dump(mode="json"),
        "scan_profiles": sorted(config.scan_profiles.keys()),
        "health_profiles": sorted(config.health_profiles.keys()),
        "probe_defaults": config.probe_defaults.model_dump(mode="json"),
        "reports": {
            "formats": config.reports.formats,
        },
        "storage": {
            "type": config.storage.type,
        },
    }


def _render_summary(
    *,
    tasks: list[TaskRun],
    assets: list[Asset],
    probe_results: list[ProbeResult],
    findings: list,
    local_snapshots: list,
) -> str:
    success_count = sum(1 for result in probe_results if result.status == "success")
    failed_count = len(probe_results) - success_count
    lines = [
            "# 诊断包摘要",
            "",
            f"- 生成时间：`{datetime.now(UTC).isoformat()}`",
            f"- 任务数量：{len(tasks)}",
            f"- 资产数量：{len(assets)}",
            f"- 探测结果数量：{len(probe_results)}",
            f"- 风险发现数量：{len(findings)}",
            f"- 本机信息快照数量：{len(local_snapshots)}",
            f"- 成功探测：{success_count}",
            f"- 异常或超时探测：{failed_count}",
            "",
    ]

    summarized_tasks = [task for task in tasks if task.summary]
    if summarized_tasks:
        lines.extend(
            [
                "## 任务摘要",
                "",
                "| 任务 ID | 类型 | 结论 | 可能范围 |",
                "|---|---|---|---|",
            ]
        )
        for task in summarized_tasks:
            lines.append(
                "| "
                + " | ".join(
                    [
                        task.id,
                        task.task_type,
                        str(task.summary.get("title", "")),
                        str(task.summary.get("likely_area", "")),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## 文件说明",
            "",
            "- `config-summary.json`：脱敏后的配置摘要。",
            "- `tasks.json`：任务记录。",
            "- `assets.json`：资产记录。",
            "- `probe-results.json`：探测结果。",
            "- `findings.json`：风险发现。",
            "- `local-snapshots.json`：本机系统与网络采集快照。",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

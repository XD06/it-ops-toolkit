"""Web Console FastAPI 应用定义。

架构规则：
- Web 只调用 SQLiteStore（数据层）和已有的应用服务函数。
- Web 不直接调用 Adapter（ping、dns、tcp、http 探针）。
- Web 只读展示 CLI 产生的历史结果，不承载业务判断逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from .. import __version__
from ..models import Asset, Finding, ProbeResult, Report, TaskRun
from ..storage import SQLiteStore, TaskRecordNotFound
from ..tasks import get_task, list_tasks
from .dashboard import render_dashboard

app = FastAPI(
    title="IT Ops Toolkit Web Console",
    version=__version__,
    description="中小企业 IT 运维工具箱 — Web 可视化层（只读展示历史结果）",
)

# 全局 store 实例，由 CLI 启动时注入或测试时直接设置。
_store: SQLiteStore | None = None


def set_store(store: SQLiteStore) -> None:
    """注入 SQLiteStore 实例。"""
    global _store
    _store = store


def get_store() -> SQLiteStore:
    """获取当前 store 实例，未设置时使用默认路径。"""
    global _store
    if _store is None:
        _store = SQLiteStore(Path("data/ops.sqlite"))
    return _store


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    """渲染 HTML 仪表盘首页。"""
    store = get_store()
    return render_dashboard(store=store)


# ---------------------------------------------------------------------------
# API 路由 — 概览
# ---------------------------------------------------------------------------


@app.get("/api/overview", summary="仪表盘概览统计")
def api_overview() -> dict[str, Any]:
    """返回资产数、任务数、报告数等概览统计。"""
    store = get_store()
    assets = store.list_assets()
    tasks = store.list_task_runs(limit=500)
    reports = store.list_reports(limit=500)
    findings = store.list_all_findings()

    # 按任务类型统计
    task_type_counts: dict[str, int] = {}
    for task in tasks:
        task_type_counts[task.task_type] = task_type_counts.get(task.task_type, 0) + 1

    # 按严重程度统计发现
    severity_counts: dict[str, int] = {}
    for finding in findings:
        severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1

    return {
        "assets_count": len(assets),
        "tasks_count": len(tasks),
        "reports_count": len(reports),
        "findings_count": len(findings),
        "task_type_counts": task_type_counts,
        "severity_counts": severity_counts,
        "version": __version__,
    }


# ---------------------------------------------------------------------------
# API 路由 — 资产
# ---------------------------------------------------------------------------


@app.get("/api/assets", summary="资产列表")
def api_list_assets() -> list[dict[str, Any]]:
    """返回所有资产记录。"""
    store = get_store()
    assets = store.list_assets()
    return [_asset_to_dict(a) for a in assets]


@app.get("/api/assets/{ip}", summary="资产详情")
def api_get_asset(ip: str) -> dict[str, Any]:
    """按 IP 查询单个资产详情。"""
    store = get_store()
    asset = store.get_asset_by_ip(ip)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"asset not found: {ip}")
    return _asset_to_dict(asset)


def _asset_to_dict(asset: Asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "ip": asset.ip,
        "hostname": asset.hostname,
        "mac": asset.mac,
        "vendor": asset.vendor,
        "os_hint": asset.os_hint,
        "asset_type": asset.asset_type,
        "open_ports": asset.open_ports,
        "first_seen": asset.first_seen,
        "last_seen": asset.last_seen,
        "status": asset.status,
        "source": asset.source,
        "owner": asset.owner,
        "description": asset.description,
        "tags": asset.tags,
    }


# ---------------------------------------------------------------------------
# API 路由 — 任务
# ---------------------------------------------------------------------------


@app.get("/api/tasks", summary="任务历史列表")
def api_list_tasks(
    limit: int = Query(default=20, ge=1, le=500),
) -> list[dict[str, Any]]:
    """返回最近的任务执行记录。"""
    store = get_store()
    tasks = list_tasks(store, limit=limit)
    return [_task_to_dict(t) for t in tasks]


@app.get("/api/tasks/{task_id}", summary="任务详情")
def api_get_task(task_id: str) -> dict[str, Any]:
    """查询单个任务的详细信息。"""
    store = get_store()
    try:
        task = get_task(store, task_id)
    except TaskRecordNotFound:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    return _task_to_dict(task)


@app.get("/api/tasks/{task_id}/results", summary="任务探测结果")
def api_get_task_results(task_id: str) -> list[dict[str, Any]]:
    """返回指定任务的所有探测结果。"""
    store = get_store()
    # 先检查任务是否存在
    try:
        get_task(store, task_id)
    except TaskRecordNotFound:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    results = store.list_probe_results_for_task(task_id)
    return [_result_to_dict(r) for r in results]


@app.get("/api/tasks/{task_id}/findings", summary="任务发现项")
def api_get_task_findings(task_id: str) -> list[dict[str, Any]]:
    """返回指定任务的所有发现项。"""
    store = get_store()
    try:
        get_task(store, task_id)
    except TaskRecordNotFound:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    findings = store.list_findings_for_task(task_id)
    return [_finding_to_dict(f) for f in findings]


@app.get("/api/tasks/{task_id}/snapshots", summary="任务本机快照")
def api_get_task_snapshots(task_id: str) -> list[dict[str, Any]]:
    """返回指定任务的本机信息快照。"""
    store = get_store()
    try:
        get_task(store, task_id)
    except TaskRecordNotFound:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    snapshots = store.list_local_snapshots_for_task(task_id)
    return [_snapshot_to_dict(s) for s in snapshots]


def _task_to_dict(task: TaskRun) -> dict[str, Any]:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "requested_by": task.requested_by,
        "source": task.source,
        "status": task.status.value,
        "risk_level": task.risk_level.value,
        "started_at": task.started_at,
        "ended_at": task.ended_at,
        "target_refs": task.target_refs,
        "result_refs": task.result_refs,
        "log_refs": task.log_refs,
        "summary": task.summary,
    }


def _result_to_dict(result: ProbeResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "task_id": result.task_id,
        "request_id": result.request_id,
        "probe_type": result.probe_type,
        "target": result.target.model_dump(mode="json"),
        "status": result.status.value,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "duration_ms": result.duration_ms,
        "observations": result.observations,
        "error": result.error.model_dump(mode="json") if result.error else None,
        "evidence": result.evidence,
    }


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "task_id": finding.task_id,
        "category": finding.category,
        "severity": finding.severity,
        "title": finding.title,
        "description": finding.description,
        "evidence_refs": finding.evidence_refs,
        "recommendation": finding.recommendation,
        "requires_human_review": finding.requires_human_review,
    }


def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "task_id": snapshot.task_id,
        "collected_at": snapshot.collected_at,
        "hostname": snapshot.hostname,
        "fqdn": snapshot.fqdn,
        "username": snapshot.username,
        "os_name": snapshot.os_name,
        "platform": snapshot.platform,
        "interfaces": [i.model_dump(mode="json") for i in snapshot.interfaces],
        "default_routes": snapshot.default_routes,
        "dns_servers": snapshot.dns_servers,
        "proxy": snapshot.proxy,
        "observations": snapshot.observations,
    }


# ---------------------------------------------------------------------------
# API 路由 — 报告
# ---------------------------------------------------------------------------


@app.get("/api/reports", summary="报告列表")
def api_list_reports(
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """返回报告记录列表。"""
    store = get_store()
    reports = store.list_reports(limit=limit)
    return [_report_to_dict(r) for r in reports]


@app.get("/api/reports/{report_id}", summary="报告详情")
def api_get_report(report_id: str) -> dict[str, Any]:
    """查询单个报告详情。"""
    store = get_store()
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"report not found: {report_id}")
    return _report_to_dict(report)


@app.get("/api/reports/{report_id}/content", summary="报告文件内容")
def api_get_report_content(report_id: str) -> JSONResponse:
    """读取报告文件内容并返回。"""
    store = get_store()
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"report not found: {report_id}")
    report_path = Path(report.path)
    if not report_path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="report path is not absolute; cannot resolve",
        )
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"report file not found: {report.path}")
    try:
        content = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"failed to read report: {exc}")
    return JSONResponse(
        content={
            "id": report.id,
            "title": report.title,
            "format": report.format,
            "path": report.path,
            "content": content,
        }
    )


def _report_to_dict(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "source_task_id": report.source_task_id,
        "report_type": report.report_type,
        "title": report.title,
        "format": report.format,
        "path": report.path,
        "summary": report.summary,
        "generated_at": report.generated_at,
    }


# ---------------------------------------------------------------------------
# API 路由 — 健康检查
# ---------------------------------------------------------------------------


@app.get("/api/health", summary="Web Console 健康检查")
def api_health() -> dict[str, str]:
    """返回 Web Console 自身健康状态。"""
    return {"status": "ok", "version": __version__}

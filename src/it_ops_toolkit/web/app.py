"""Web Console FastAPI 应用定义。

架构规则：
- Web 只调用 SQLiteStore（数据层）和已有的领域服务函数。
- Web 不直接调用 Adapter（ping、dns、tcp、http 探针）。
- Web 展示 CLI 产生的历史结果，也可通过领域服务触发只读巡检和扫描。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .. import __version__
from ..assets import AssetScanError, run_asset_scan
from ..config import OpsConfig
from ..health import HealthCheckError, run_health_check
from ..models import Asset, Finding, ProbeResult, Report, TaskRun, TaskStatus
from ..storage import SQLiteStore, TaskRecordNotFound
from ..tasks import finish_task_run, get_task, list_tasks, new_task_run
from .dashboard import render_dashboard

app = FastAPI(
    title="IT Ops Toolkit Web Console",
    version=__version__,
    description="中小企业 IT 运维工具箱 — Web 可视化层",
)

# 全局实例，由 CLI 启动时注入或测试时直接设置。
_store: SQLiteStore | None = None
_config: OpsConfig | None = None


def set_store(store: SQLiteStore) -> None:
    """注入 SQLiteStore 实例。"""
    global _store
    _store = store


def set_config(config: OpsConfig | None) -> None:
    """注入 OpsConfig 实例。传入 None 可清除配置。"""
    global _config
    _config = config


def get_store() -> SQLiteStore:
    """获取当前 store 实例，未设置时使用默认路径。"""
    global _store
    if _store is None:
        _store = SQLiteStore(Path("data/ops.sqlite"))
    return _store


def get_config() -> OpsConfig:
    """获取当前配置实例，未设置时抛出异常。"""
    global _config
    if _config is None:
        raise HTTPException(
            status_code=503,
            detail="configuration not available; start web console via 'ops web run'",
        )
    return _config


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class TriggerHealthCheckRequest(BaseModel):
    profile_name: str


class TriggerAssetScanRequest(BaseModel):
    profile_name: str
    tcp_without_ping: bool = False


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> str:
    """渲染 HTML 仪表盘首页。"""
    store = get_store()
    config_available = _config is not None
    return render_dashboard(store=store, config_available=config_available)


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
        "config_available": _config is not None,
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
    task_type: str | None = Query(default=None, description="按任务类型筛选"),
    status: str | None = Query(default=None, description="按任务状态筛选"),
) -> list[dict[str, Any]]:
    """返回最近的任务执行记录，支持按类型和状态筛选。"""
    store = get_store()
    tasks = list_tasks(store, limit=limit)
    if task_type:
        tasks = [t for t in tasks if t.task_type == task_type]
    if status:
        tasks = [t for t in tasks if t.status.value == status]
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


# ---------------------------------------------------------------------------
# API 路由 — 任务触发（通过领域服务，不直接调用 Adapter）
# ---------------------------------------------------------------------------


@app.post("/api/tasks/trigger/health-check", summary="触发巡检任务")
def api_trigger_health_check(req: TriggerHealthCheckRequest) -> dict[str, Any]:
    """通过领域服务触发一次巡检任务。"""
    config = get_config()
    store = get_store()

    if req.profile_name not in config.health_profiles:
        raise HTTPException(
            status_code=400,
            detail=f"health profile not found: {req.profile_name}",
        )

    task = new_task_run(task_type="health_check", requested_by="web")
    task = task.model_copy(update={"source": "web"})
    store.save_task_run(task)

    try:
        results = run_health_check(
            config=config,
            profile_name=req.profile_name,
            task=task,
            store=store,
        )
    except HealthCheckError as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"health check failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={
            "result_refs": [r.id for r in results],
            "target_refs": [r.target.value for r in results],
        }
    )
    store.save_task_run(task)
    return _task_to_dict(task)


@app.post("/api/tasks/trigger/asset-scan", summary="触发资产扫描任务")
def api_trigger_asset_scan(req: TriggerAssetScanRequest) -> dict[str, Any]:
    """通过领域服务触发一次资产扫描任务。"""
    config = get_config()
    store = get_store()

    if req.profile_name not in config.scan_profiles:
        raise HTTPException(
            status_code=400,
            detail=f"scan profile not found: {req.profile_name}",
        )

    task = new_task_run(task_type="asset_scan", requested_by="web")
    task = task.model_copy(update={"source": "web"})
    store.save_task_run(task)

    try:
        assets, results = run_asset_scan(
            config=config,
            profile_name=req.profile_name,
            task=task,
            store=store,
            tcp_without_ping=req.tcp_without_ping,
        )
    except AssetScanError as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"asset scan failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={
            "result_refs": [r.id for r in results],
            "target_refs": [a.ip for a in assets],
        }
    )
    store.save_task_run(task)
    return _task_to_dict(task)


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
# API 路由 — 配置查看
# ---------------------------------------------------------------------------


@app.get("/api/config", summary="查看当前配置")
def api_get_config() -> dict[str, Any]:
    """返回当前配置的只读视图（不包含敏感信息）。"""
    config = get_config()
    return _config_to_dict(config)


@app.get("/api/config/health-profiles", summary="查看巡检配置")
def api_get_health_profiles() -> list[dict[str, Any]]:
    """返回所有巡检配置。"""
    config = get_config()
    return [
        {
            "name": name,
            "description": profile.description,
            "targets": [
                {
                    "name": t.name,
                    "type": t.type,
                    "value": str(t.value),
                    "checks": t.checks,
                    "port": t.port,
                }
                for t in profile.targets
            ],
        }
        for name, profile in config.health_profiles.items()
    ]


@app.get("/api/config/scan-profiles", summary="查看扫描配置")
def api_get_scan_profiles() -> list[dict[str, Any]]:
    """返回所有资产扫描配置。"""
    config = get_config()
    return [
        {
            "name": name,
            "description": profile.description,
            "subnets": profile.subnets,
            "ping": {
                "enabled": profile.ping.enabled,
                "timeout_ms": profile.ping.timeout_ms,
                "retries": profile.ping.retries,
            },
            "tcp_ports": profile.tcp_ports,
        }
        for name, profile in config.scan_profiles.items()
    ]


def _config_to_dict(config: OpsConfig) -> dict[str, Any]:
    return {
        "app": {
            "name": config.app.name,
            "environment": config.app.environment,
        },
        "scan_profiles": list(config.scan_profiles.keys()),
        "health_profiles": list(config.health_profiles.keys()),
        "probe_defaults": {
            "timeout_ms": config.probe_defaults.timeout_ms,
            "retries": config.probe_defaults.retries,
            "concurrency": config.probe_defaults.concurrency,
        },
        "reports": {
            "output_dir": str(config.reports.output_dir),
            "formats": config.reports.formats,
        },
        "storage": {
            "type": config.storage.type,
            "path": str(config.storage.path),
        },
        "security": {
            "risky_ports": config.security.risky_ports,
        },
    }


# ---------------------------------------------------------------------------
# API 路由 — 健康检查
# ---------------------------------------------------------------------------


@app.get("/api/health", summary="Web Console 健康检查")
def api_health() -> dict[str, str]:
    """返回 Web Console 自身健康状态。"""
    return {"status": "ok", "version": __version__}

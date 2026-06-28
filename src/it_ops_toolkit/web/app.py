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
from ..models import Asset, Finding, ProbeResult, Report, RiskLevel, TaskRun, TaskStatus
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


# ---------------------------------------------------------------------------
# API 路由 — 历史趋势（Phase 6）
# ---------------------------------------------------------------------------


@app.get("/api/trends/targets", summary="可用趋势目标列表")
def api_trend_targets(
    probe_type: str | None = Query(default=None, description="按探针类型筛选"),
) -> list[dict[str, Any]]:
    """列出有历史数据的目标，用于趋势查询的目标选择。"""
    from ..trend import list_available_targets

    store = get_store()
    return list_available_targets(store=store, probe_type=probe_type)


@app.get("/api/trends/probe", summary="探针趋势详情")
def api_trend_probe(
    probe_type: str = Query(..., description="探针类型"),
    target: str | None = Query(default=None, description="目标筛选"),
    metric: str | None = Query(default=None, description="指定指标"),
    days: int = Query(default=7, ge=1, le=365, description="查询天数范围"),
    granularity: str = Query(default="daily", description="聚合粒度：daily / hourly"),
) -> dict[str, Any]:
    """返回探针的趋势数据，包含时间序列聚合和状态分布。"""
    from ..trend import TrendError, get_trend

    store = get_store()
    try:
        return get_trend(
            store=store,
            probe_type=probe_type,
            target=target,
            metric=metric,
            days=days,
            granularity=granularity,
        )
    except TrendError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/trends/summary", summary="趋势摘要")
def api_trend_summary(
    probe_type: str = Query(..., description="探针类型"),
    target: str | None = Query(default=None, description="目标筛选"),
    days: int = Query(default=7, ge=1, le=365, description="查询天数范围"),
) -> dict[str, Any]:
    """返回趋势摘要，适合 AI 消费或快速概览。"""
    from ..trend import TrendError, get_trend_summary

    store = get_store()
    try:
        return get_trend_summary(
            store=store,
            probe_type=probe_type,
            target=target,
            days=days,
        )
    except TrendError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# API 路由 — AI 运维助手（Phase 7）
# ---------------------------------------------------------------------------


@app.get("/api/ai/summarize/{task_id}", summary="AI 任务摘要")
def api_ai_summarize(
    task_id: str,
    prompt: str | None = Query(default=None, description="自定义提示词"),
) -> dict[str, Any]:
    """对指定任务生成 AI 摘要。"""
    from ..ai_copilot import AIAdapterError, summarize_task

    config = get_config()
    store = get_store()
    try:
        output = summarize_task(task_id=task_id, store=store, config=config, prompt=prompt)
        return output.model_dump(mode="json")
    except AIAdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ai/explain/{task_id}", summary="AI 异常解释")
def api_ai_explain(
    task_id: str,
    question: str | None = Query(default=None, description="自然语言提问"),
) -> dict[str, Any]:
    """解释指定任务中的异常。"""
    from ..ai_copilot import AIAdapterError, explain_anomaly

    config = get_config()
    store = get_store()
    try:
        output = explain_anomaly(task_id=task_id, store=store, config=config, question=question)
        return output.model_dump(mode="json")
    except AIAdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ai/weekly", summary="AI 周报摘要")
def api_ai_weekly(
    days: int = Query(default=7, ge=1, le=90, description="汇总天数"),
    prompt: str | None = Query(default=None, description="自定义提示词"),
) -> dict[str, Any]:
    """生成 AI 周报摘要。"""
    from ..ai_copilot import AIAdapterError, summarize_recent

    config = get_config()
    store = get_store()
    try:
        output = summarize_recent(store=store, config=config, days=days, prompt=prompt)
        return output.model_dump(mode="json")
    except AIAdapterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ai/logs", summary="AI 调用日志")
def api_ai_logs(
    task_id: str | None = Query(default=None, description="按任务 ID 筛选"),
    limit: int = Query(default=50, ge=1, le=500, description="最多返回条数"),
) -> list[dict[str, Any]]:
    """查询 AI 调用审计日志。"""
    store = get_store()
    logs = store.list_ai_call_logs(task_id=task_id, limit=limit)
    return [log.model_dump(mode="json") for log in logs]


# ---------------------------------------------------------------------------
# Phase 8：网络拓扑与资产关系
# ---------------------------------------------------------------------------


@app.get("/api/topology", summary="网络拓扑视图")
def api_topology(
    traceroute_target: str | None = Query(default=None, description="可选：traceroute 目标"),
    max_hops: int = Query(default=15, ge=1, le=30, description="traceroute 最大跳数"),
    reconcile: bool = Query(default=True, description="是否与资产库对比"),
) -> dict[str, Any]:
    """获取本机视角的网络拓扑。

    包含本机接口、默认网关、ARP 表、可选 traceroute 和资产对比。
    """
    from ..topology import get_topology

    store = get_store() if reconcile else None
    view = get_topology(
        store=store,
        traceroute_target=traceroute_target,
        max_hops=max_hops,
    )
    return view.model_dump(mode="json")


@app.get("/api/topology/arp", summary="ARP 表")
def api_topology_arp() -> list[dict[str, Any]]:
    """采集本机 ARP 表。"""
    from ..probes.arp import collect_arp_table

    entries = collect_arp_table()
    return [e.model_dump(mode="json") for e in entries]


@app.get("/api/topology/unknown", summary="未知设备检测")
def api_topology_unknown() -> list[dict[str, Any]]:
    """检测 ARP 表中不在资产库的未知设备。"""
    from ..probes.arp import collect_arp_table
    from ..topology import detect_unknown_devices

    store = get_store()
    arp_entries = collect_arp_table()
    unknown = detect_unknown_devices(arp_entries=arp_entries, store=store)
    return [e.model_dump(mode="json") for e in unknown]


@app.get("/api/topology/traceroute/{target}", summary="路由追踪")
def api_topology_traceroute(
    target: str,
    max_hops: int = Query(default=15, ge=1, le=30, description="最大跳数"),
) -> dict[str, Any]:
    """对指定目标执行路由追踪。"""
    from ..probes.traceroute import TraceRouteError, run_traceroute

    try:
        result = run_traceroute(target=target, max_hops=max_hops)
    except TraceRouteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# SNMP 探针
# ---------------------------------------------------------------------------


@app.get("/api/snmp/{target}", summary="SNMP 设备信息采集")
def api_snmp_info(
    target: str,
    community: str = Query(default="public", description="SNMP community 字符串"),
    port: int = Query(default=161, ge=1, le=65535, description="SNMP UDP 端口"),
    timeout_ms: int = Query(default=3000, ge=500, le=10000, description="超时时间（毫秒）"),
) -> dict[str, Any]:
    """通过 SNMP v2c 采集设备基础信息（sysDescr、sysName、接口列表等）。"""
    from ..probes.snmp import SnmpError, collect_snmp_info

    store = get_store()
    task = new_task_run(task_type="snmp_probe", source="web")
    store.save_task_run(task)

    result = collect_snmp_info(
        task_id=task.id,
        target=target,
        community=community,
        port=port,
        timeout_ms=timeout_ms,
    )
    store.save_probe_result(result)

    task = finish_task_run(
        task,
        status=TaskStatus.success if result.status == "success" else TaskStatus.failed,
    )
    store.save_task_run(task)

    return result.model_dump(mode="json")


@app.get("/api/snmp/{target}/get", summary="SNMP GET 单个 OID")
def api_snmp_get(
    target: str,
    oid: str = Query(..., description="要查询的 OID"),
    community: str = Query(default="public", description="SNMP community 字符串"),
    port: int = Query(default=161, ge=1, le=65535, description="SNMP UDP 端口"),
    timeout_ms: int = Query(default=3000, ge=500, le=10000, description="超时时间（毫秒）"),
) -> dict[str, Any]:
    """通过 SNMP v2c GET 查询单个 OID 的值。"""
    from ..probes.snmp import SnmpError, snmp_get

    try:
        resp_oid, value = snmp_get(
            target=target,
            oid=oid,
            community=community,
            port=port,
            timeout_ms=timeout_ms,
        )
    except SnmpError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"oid": resp_oid, "value": value}


# ---------------------------------------------------------------------------
# Phase 9：受控 Agent 工作流
# ---------------------------------------------------------------------------


@app.get("/api/workflows", summary="可用工作流列表")
def api_workflows_list() -> list[dict[str, Any]]:
    """列出所有可用工作流定义。"""
    from ..agent_workflow import get_builtin_workflows

    workflows = get_builtin_workflows()
    return [wf.model_dump(mode="json") for wf in workflows]


class WorkflowRunRequest(BaseModel):
    """工作流执行请求体。"""

    confirm: bool = False
    context: dict[str, Any] | None = None


@app.post("/api/workflows/{name}/run", summary="执行工作流")
def api_workflows_run(
    name: str,
    request: WorkflowRunRequest,
) -> dict[str, Any]:
    """执行指定工作流。"""
    from ..agent_workflow import (
        WorkflowError,
        execute_workflow,
        get_workflow_by_name,
    )

    config = get_config()
    store = get_store()

    try:
        wf = get_workflow_by_name(name)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    execution = execute_workflow(
        workflow=wf,
        store=store,
        config=config,
        trigger="web",
        context=request.context,
        auto_approve_low_risk=request.confirm,
    )
    return execution.model_dump(mode="json")


@app.get("/api/workflows/executions", summary="工作流执行历史")
def api_workflows_executions(
    workflow_name: str | None = Query(default=None, description="按工作流名称筛选"),
    status: str | None = Query(default=None, description="按状态筛选"),
    limit: int = Query(default=50, ge=1, le=500, description="最多返回条数"),
) -> list[dict[str, Any]]:
    """查询工作流执行历史。"""
    store = get_store()
    executions = store.list_workflow_executions(
        limit=limit,
        workflow_name=workflow_name,
        status=status,
    )
    return [e.model_dump(mode="json") for e in executions]


@app.get("/api/workflows/executions/{execution_id}", summary="工作流执行详情")
def api_workflows_execution_detail(
    execution_id: str,
) -> dict[str, Any]:
    """查看工作流执行详情。"""
    store = get_store()
    execution = store.get_workflow_execution(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=404,
            detail=f"workflow execution not found: {execution_id}",
        )
    return execution.model_dump(mode="json")


# ---------------------------------------------------------------------------
# 操作中心 — 通过 Web 触发领域服务
# ---------------------------------------------------------------------------


class DiagnoseRequest(BaseModel):
    """诊断触发请求体。"""

    scenario: str  # internet / intranet / rdp / printer / dns / slow_network
    target: str | None = None  # intranet=URL, rdp/printer=host[:port], dns=域名
    expected_ip: str | None = None
    tcp_port: int | None = None
    dns_servers: list[str] | None = None
    timeout_ms: int = 1000
    retries: int = 1


@app.post("/api/ops/diagnose", summary="触发诊断任务")
def api_ops_diagnose(req: DiagnoseRequest) -> dict[str, Any]:
    """通过领域服务触发一次诊断任务。

    支持 6 种场景：internet / intranet / rdp / printer / dns / slow_network
    """
    config = get_config()
    store = get_store()

    scenario = req.scenario.strip().lower()
    valid_scenarios = {"internet", "intranet", "rdp", "printer", "dns", "slow_network"}
    if scenario not in valid_scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"invalid scenario: {scenario}. supported: {sorted(valid_scenarios)}",
        )

    if scenario in {"intranet", "rdp", "printer", "dns"} and not req.target:
        raise HTTPException(
            status_code=400,
            detail=f"scenario '{scenario}' requires 'target' parameter",
        )

    timeout = req.timeout_ms or config.probe_defaults.timeout_ms
    retries = req.retries if req.retries is not None else config.probe_defaults.retries

    from ..diagnosis import (
        run_dns_diagnosis,
        run_internet_diagnosis,
        run_intranet_diagnosis,
        run_printer_diagnosis,
        run_rdp_diagnosis,
        run_slow_network_diagnosis,
    )

    task = new_task_run(task_type="diagnosis", requested_by="web")
    task = task.model_copy(update={"source": "web", "risk_level": RiskLevel.read_only})
    store.save_task_run(task)

    try:
        if scenario == "internet":
            results, summary = run_internet_diagnosis(
                task=task, store=store, timeout_ms=timeout, retries=retries,
            )
        elif scenario == "slow_network":
            results, summary = run_slow_network_diagnosis(
                task=task, store=store, timeout_ms=timeout, retries=retries,
            )
        elif scenario == "intranet":
            results, summary = run_intranet_diagnosis(
                task=task, store=store, url=req.target, timeout_ms=timeout, retries=retries,
            )
        elif scenario == "rdp":
            results, summary = run_rdp_diagnosis(
                task=task, store=store, target=req.target, timeout_ms=timeout, retries=retries,
            )
        elif scenario == "printer":
            results, summary = run_printer_diagnosis(
                task=task, store=store, target=req.target, timeout_ms=timeout, retries=retries,
            )
        elif scenario == "dns":
            results, summary = run_dns_diagnosis(
                task=task, store=store, name=req.target,
                expected_ip=req.expected_ip, tcp_port=req.tcp_port,
                dns_servers=req.dns_servers, timeout_ms=timeout,
            )
    except ValueError as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"diagnosis failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={
            "result_refs": [r.id for r in results],
            "target_refs": [r.target.value for r in results],
            "summary": {
                "scenario": scenario,
                "title": summary.title,
                "likely_area": summary.likely_area,
                "recommendation": summary.recommendation,
            },
        }
    )
    store.save_task_run(task)
    return _task_to_dict(task)


@app.post("/api/ops/security-check", summary="触发安全检查")
def api_ops_security_check() -> dict[str, Any]:
    """基于已发现资产执行安全检查。"""
    config = get_config()
    store = get_store()

    from ..security import run_security_check

    task = new_task_run(task_type="security_check", requested_by="web")
    task = task.model_copy(update={"source": "web", "risk_level": RiskLevel.read_only})
    store.save_task_run(task)

    try:
        findings = run_security_check(config=config, task=task, store=store)
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"security check failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={
            "result_refs": [f.id for f in findings],
            "summary": {"findings_count": len(findings)},
        }
    )
    store.save_task_run(task)
    return _task_to_dict(task)


class CertCheckRequest(BaseModel):
    """证书检查请求体。"""

    hostname: str
    port: int = 443
    warning_days: int = 30


@app.post("/api/ops/cert-check", summary="触发证书检查")
def api_ops_cert_check(req: CertCheckRequest) -> dict[str, Any]:
    """检查 TLS 证书过期风险。"""
    store = get_store()

    from ..security import run_certificate_check

    task = new_task_run(task_type="security_check", requested_by="web")
    task = task.model_copy(update={"source": "web", "risk_level": RiskLevel.read_only})
    store.save_task_run(task)

    try:
        result, findings = run_certificate_check(
            task=task, store=store, hostname=req.hostname,
            port=req.port, warning_days=req.warning_days,
        )
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"cert check failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={
            "result_refs": [result.id] + [f.id for f in findings],
            "target_refs": [req.hostname],
        }
    )
    store.save_task_run(task)
    return _task_to_dict(task)


class ReportGenerateRequest(BaseModel):
    """报告生成请求体。"""

    source_task_id: str
    report_format: str = "markdown"  # markdown / csv / json


@app.post("/api/ops/report-generate", summary="触发报告生成")
def api_ops_report_generate(req: ReportGenerateRequest) -> dict[str, Any]:
    """基于指定任务生成报告。"""
    config = get_config()
    store = get_store()

    from ..reports import ReportError, generate_report

    task = new_task_run(task_type="report_generate", requested_by="web")
    task = task.model_copy(update={"source": "web", "risk_level": RiskLevel.read_only})
    store.save_task_run(task)

    try:
        report = generate_report(
            store=store,
            source_task_id=req.source_task_id,
            output_dir=config.reports.output_dir,
            report_format=req.report_format,
        )
    except ReportError as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"report generation failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={"summary": {"report_id": report.id, "report_path": report.path}}
    )
    store.save_task_run(task)
    return _task_to_dict(task)


class AssetDiffRequest(BaseModel):
    """资产对比请求体。"""

    profile_name: str
    tcp_without_ping: bool = False


@app.post("/api/ops/asset-diff", summary="触发资产变化对比")
def api_ops_asset_diff(req: AssetDiffRequest) -> dict[str, Any]:
    """执行资产变化对比。"""
    config = get_config()
    store = get_store()

    if req.profile_name not in config.scan_profiles:
        raise HTTPException(
            status_code=400,
            detail=f"scan profile not found: {req.profile_name}",
        )

    from ..assets import AssetScanError, run_asset_diff

    task = new_task_run(task_type="asset_diff", requested_by="web")
    task = task.model_copy(update={"source": "web", "risk_level": RiskLevel.read_only})
    store.save_task_run(task)

    try:
        assets, results, findings, summary = run_asset_diff(
            config=config, profile_name=req.profile_name,
            task=task, store=store, tcp_without_ping=req.tcp_without_ping,
        )
    except AssetScanError as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"asset diff failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={
            "result_refs": [r.id for r in results] + [f.id for f in findings],
            "target_refs": [a.ip for a in assets],
            "summary": summary,
        }
    )
    store.save_task_run(task)
    return _task_to_dict(task)


class FlushDnsRequest(BaseModel):
    """清理 DNS 缓存请求体。"""

    dry_run: bool = True
    confirm: bool = False


@app.post("/api/ops/flush-dns", summary="触发清理本机 DNS 缓存")
def api_ops_flush_dns(req: FlushDnsRequest) -> dict[str, Any]:
    """清理本机 DNS 缓存（低风险变更操作）。

    - dry_run=true：只生成计划，不执行
    - confirm=true：实际执行清理
    """
    store = get_store()

    from ..automation import AutomationError, run_flush_dns_cache

    task = new_task_run(task_type="automation", requested_by="web")
    task = task.model_copy(update={"source": "web", "risk_level": RiskLevel.low_change})
    store.save_task_run(task)

    try:
        result = run_flush_dns_cache(
            task=task, dry_run=req.dry_run, confirm=req.confirm,
        )
    except AutomationError as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"flush-dns failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(update={"summary": result})
    store.save_task_run(task)
    return _task_to_dict(task)


@app.post("/api/ops/collect-local", summary="触发本机信息采集")
def api_ops_collect_local() -> dict[str, Any]:
    """采集本机系统和网络排障上下文。"""
    store = get_store()

    from ..local_collect import collect_local_snapshot

    task = new_task_run(task_type="ops_collect", requested_by="web")
    task = task.model_copy(update={"source": "web", "risk_level": RiskLevel.read_only})
    store.save_task_run(task)

    try:
        snapshot = collect_local_snapshot(task=task, store=store)
    except Exception as exc:
        task = finish_task_run(task, status=TaskStatus.failed)
        store.save_task_run(task)
        raise HTTPException(status_code=500, detail=f"collect local info failed: {exc}") from exc

    task = finish_task_run(task, status=TaskStatus.success)
    task = task.model_copy(
        update={"summary": {"hostname": snapshot.hostname, "os": snapshot.os_name}}
    )
    store.save_task_run(task)
    return _task_to_dict(task)


# ---------------------------------------------------------------------------
# 调度管理 — 定时任务 CRUD + 告警事件
# ---------------------------------------------------------------------------


class ScheduleCreateRequest(BaseModel):
    """创建定时任务请求体。"""

    name: str
    task_type: str  # health_check / security_check / asset_scan
    profile: str = "default"
    cron: str
    enabled: bool = True
    alert_on: list[str] = ["warning", "critical"]


@app.get("/api/schedules", summary="定时任务列表")
def api_schedules_list() -> list[dict[str, Any]]:
    """列出所有定时任务。"""
    store = get_store()
    tasks = store.list_scheduled_tasks()
    return [t.model_dump(mode="json") for t in tasks]


@app.post("/api/schedules", summary="添加定时任务")
def api_schedules_add(req: ScheduleCreateRequest) -> dict[str, Any]:
    """添加一个新的定时任务。"""
    from ..scheduler import CronExpression, SchedulerError, create_scheduled_task

    # 验证 cron 表达式
    try:
        CronExpression(req.cron)
    except SchedulerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    valid_types = {"health_check", "security_check", "asset_scan"}
    if req.task_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"invalid task_type: {req.task_type}. supported: {sorted(valid_types)}",
        )

    store = get_store()

    # 检查名称是否重复
    task_id = f"schedule-{req.name}"
    if store.get_scheduled_task(task_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"schedule task with name '{req.name}' already exists",
        )

    task = create_scheduled_task(
        name=req.name,
        task_type=req.task_type,
        profile=req.profile,
        cron=req.cron,
        enabled=req.enabled,
        alert_on=req.alert_on,
    )
    store.save_scheduled_task(task)
    return task.model_dump(mode="json")


@app.delete("/api/schedules/{task_id}", summary="删除定时任务")
def api_schedules_delete(task_id: str) -> dict[str, Any]:
    """删除指定定时任务。"""
    store = get_store()
    task = store.get_scheduled_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"schedule task not found: {task_id}",
        )
    store.delete_scheduled_task(task_id)
    return {"deleted": True, "task_id": task_id}


@app.post("/api/schedules/{task_id}/enable", summary="启用定时任务")
def api_schedules_enable(task_id: str) -> dict[str, Any]:
    """启用指定定时任务。"""
    store = get_store()
    task = store.get_scheduled_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"schedule task not found: {task_id}",
        )

    from ..scheduler import CronExpression

    updated = task.model_copy(update={"enabled": True})
    if updated.next_run is None:
        cron = CronExpression(updated.cron)
        from datetime import UTC, datetime
        updated = updated.model_copy(
            update={"next_run": cron.next_run_after(datetime.now(UTC))}
        )
    store.save_scheduled_task(updated)
    return updated.model_dump(mode="json")


@app.post("/api/schedules/{task_id}/disable", summary="禁用定时任务")
def api_schedules_disable(task_id: str) -> dict[str, Any]:
    """禁用指定定时任务。"""
    store = get_store()
    task = store.get_scheduled_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"schedule task not found: {task_id}",
        )

    updated = task.model_copy(update={"enabled": False})
    store.save_scheduled_task(updated)
    return updated.model_dump(mode="json")


@app.post("/api/schedules/{task_id}/run-now", summary="立即执行定时任务")
def api_schedules_run_now(task_id: str) -> dict[str, Any]:
    """立即执行一次定时任务（不等调度时间）。"""
    config = get_config()
    store = get_store()

    from ..scheduler import SchedulerEngine

    engine = SchedulerEngine(config=config, store=store)
    task = engine.run_task_now(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"schedule task not found: {task_id}",
        )
    return task.model_dump(mode="json")


@app.get("/api/alerts", summary="告警事件列表")
def api_alerts_list(
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """列出告警事件，支持按状态筛选。"""
    store = get_store()
    events = store.list_alert_events(status=status, limit=limit)
    return [e.model_dump(mode="json") for e in events]


@app.post("/api/alerts/{event_id}/acknowledge", summary="确认告警事件")
def api_alerts_acknowledge(event_id: str) -> dict[str, Any]:
    """确认（标记已处理）告警事件。"""
    store = get_store()
    event = store.get_alert_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"alert event not found: {event_id}",
        )

    from datetime import UTC, datetime

    updated = event.model_copy(
        update={
            "acknowledged": True,
            "acknowledged_at": datetime.now(UTC),
        }
    )
    store.save_alert_event(updated)
    return updated.model_dump(mode="json")

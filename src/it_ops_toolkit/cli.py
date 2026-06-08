from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .assets import AssetScanError, run_asset_scan
from .config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    OpsConfig,
    create_default_config_file,
    load_config,
)
from .local_collect import collect_local_snapshot
from .diagnosis import (
    DEFAULT_DNS_NAME,
    DEFAULT_EXTERNAL_IP,
    DEFAULT_HTTP_URL,
    run_intranet_diagnosis,
    run_internet_diagnosis,
)
from .export import ExportError, default_bundle_path, export_bundle
from .health import HealthCheckError, run_health_check
from .models import TaskStatus
from .reports import ReportError, generate_report
from .security import run_security_check
from .storage import SQLiteStore, TaskRecordNotFound
from .tasks import finish_task_run, get_task, list_tasks, new_task_run

console = Console()

app = typer.Typer(
    name="ops",
    help="中小企业 IT 运维工具箱。",
    no_args_is_help=True,
    invoke_without_command=True,
)
config_app = typer.Typer(help="配置管理。")
asset_app = typer.Typer(help="资产发现。")
health_app = typer.Typer(help="网络与服务巡检。")
diagnose_app = typer.Typer(help="场景化故障诊断。")
collect_app = typer.Typer(help="本机运维信息采集。")
export_app = typer.Typer(help="诊断包导出。")
report_app = typer.Typer(help="报告输出。")
security_app = typer.Typer(help="轻量安全检查。")
task_app = typer.Typer(help="任务记录。")
app.add_typer(config_app, name="config")
app.add_typer(asset_app, name="asset")
app.add_typer(health_app, name="health")
app.add_typer(diagnose_app, name="diagnose")
app.add_typer(collect_app, name="collect")
app.add_typer(export_app, name="export")
app.add_typer(report_app, name="report")
app.add_typer(security_app, name="security")
app.add_typer(task_app, name="task")


def main() -> None:
    app()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", help="显示版本信息。"),
    ] = False,
) -> None:
    if version:
        console.print(f"it-ops-toolkit {__version__}")
        raise typer.Exit()


@config_app.command("init")
def config_init(
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="配置文件输出路径。"),
    ] = DEFAULT_CONFIG_PATH,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="覆盖已有配置文件。"),
    ] = False,
) -> None:
    """生成默认配置文件。"""
    try:
        created_path = create_default_config_file(path, force=force)
    except ConfigError as exc:
        console.print(f"[red]配置初始化失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]配置文件已生成：[/green]{created_path}")


@config_app.command("validate")
def config_validate(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="要校验的配置文件。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """校验配置文件。"""
    try:
        loaded = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]配置校验失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]配置校验通过：[/green]{config}")
    console.print(f"扫描配置数量：{len(loaded.scan_profiles)}")
    console.print(f"巡检配置数量：{len(loaded.health_profiles)}")


@asset_app.command("scan")
def asset_scan(
    profile: Annotated[
        str,
        typer.Option("--profile", "-p", help="扫描配置名称。"),
    ] = "office_lan",
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    tcp_without_ping: Annotated[
        bool,
        typer.Option(
            "--tcp-without-ping",
            help="即使 Ping 不通也尝试配置的 TCP 端口，可能明显增加耗时。",
        ),
    ] = False,
) -> None:
    """执行基础资产发现。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="asset_scan")
        store.save_task_run(task)
        assets, results = run_asset_scan(
            config=loaded,
            profile_name=profile,
            task=task,
            store=store,
            tcp_without_ping=tcp_without_ping,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "result_refs": [result.id for result in results],
                "target_refs": [asset.ip for asset in assets],
            }
        )
        store.save_task_run(task)
    except (ConfigError, AssetScanError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]资产扫描失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]资产扫描完成：[/green]{task.id}")
    console.print(f"发现在线资产：{len(assets)}")
    console.print(f"探测结果数量：{len(results)}")
    console.print(f"Ping 不通仍扫 TCP：{'是' if tcp_without_ping else '否'}")


@asset_app.command("list")
def asset_list(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看已发现资产。"""
    try:
        store = _store_from_config(config)
        assets = store.list_assets()
    except ConfigError as exc:
        console.print(f"[red]读取资产失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="资产列表")
    table.add_column("IP")
    table.add_column("主机名")
    table.add_column("状态")
    table.add_column("开放端口")
    table.add_column("最后发现")

    for asset in assets:
        table.add_row(
            asset.ip,
            asset.hostname or "",
            asset.status,
            ",".join(str(port) for port in asset.open_ports),
            asset.last_seen.isoformat(),
        )

    console.print(table)


@asset_app.command("show")
def asset_show(
    ip: Annotated[str, typer.Argument(help="资产 IP。")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看单个资产详情。"""
    try:
        store = _store_from_config(config)
        asset = store.get_asset_by_ip(ip)
    except ConfigError as exc:
        console.print(f"[red]读取资产失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    if asset is None:
        console.print(f"[red]资产不存在：[/red]{ip}")
        raise typer.Exit(code=1)

    console.print(f"[bold]IP：[/bold]{asset.ip}")
    console.print(f"[bold]主机名：[/bold]{asset.hostname or ''}")
    console.print(f"[bold]MAC：[/bold]{asset.mac or ''}")
    console.print(f"[bold]厂商：[/bold]{asset.vendor or ''}")
    console.print(f"[bold]系统线索：[/bold]{asset.os_hint or ''}")
    console.print(f"[bold]设备类型：[/bold]{asset.asset_type or ''}")
    console.print(f"[bold]开放端口：[/bold]{','.join(str(port) for port in asset.open_ports)}")
    console.print(f"[bold]状态：[/bold]{asset.status}")
    console.print(f"[bold]首次发现：[/bold]{asset.first_seen.isoformat()}")
    console.print(f"[bold]最后发现：[/bold]{asset.last_seen.isoformat()}")
    console.print(f"[bold]来源：[/bold]{asset.source}")


@health_app.command("check")
def health_check(
    profile: Annotated[
        str,
        typer.Option("--profile", "-p", help="巡检配置名称。"),
    ] = "daily_basic",
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """执行网络与服务巡检。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="health_check")
        store.save_task_run(task)
        results = run_health_check(
            config=loaded,
            profile_name=profile,
            task=task,
            store=store,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "result_refs": [result.id for result in results],
                "target_refs": [result.target.value for result in results],
            }
        )
        store.save_task_run(task)
    except (ConfigError, HealthCheckError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]巡检失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    success_count = sum(1 for result in results if result.status == "success")
    console.print(f"[green]巡检完成：[/green]{task.id}")
    console.print(f"成功检查：{success_count}")
    console.print(f"总检查数：{len(results)}")


@diagnose_app.command("internet")
def diagnose_internet(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    external_ip: Annotated[
        str,
        typer.Option("--external-ip", help="用于测试外部 IP 连通性的地址。"),
    ] = DEFAULT_EXTERNAL_IP,
    dns_name: Annotated[
        str,
        typer.Option("--dns-name", help="用于测试 DNS 解析的域名。"),
    ] = DEFAULT_DNS_NAME,
    http_url: Annotated[
        str,
        typer.Option("--http-url", help="用于测试 HTTP/HTTPS 访问的 URL。"),
    ] = DEFAULT_HTTP_URL,
) -> None:
    """诊断本机基础互联网连通性。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="diagnosis")
        store.save_task_run(task)
        results, summary = run_internet_diagnosis(
            task=task,
            store=store,
            external_ip=external_ip,
            dns_name=dns_name,
            http_url=http_url,
            timeout_ms=loaded.probe_defaults.timeout_ms,
            retries=loaded.probe_defaults.retries,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [external_ip, dns_name, http_url],
                "result_refs": [result.id for result in results],
            }
        )
        store.save_task_run(task)
    except ConfigError as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]诊断失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="互联网连通性诊断")
    table.add_column("检查")
    table.add_column("目标")
    table.add_column("状态")
    table.add_column("耗时 ms")
    table.add_column("错误")
    for result in results:
        table.add_row(
            result.probe_type,
            result.target.value,
            result.status.value,
            str(result.duration_ms or ""),
            result.error.message if result.error else "",
        )

    console.print(table)
    console.print(f"[bold]结论：[/bold]{summary.title}")
    console.print(f"[bold]可能范围：[/bold]{summary.likely_area}")
    console.print(f"[bold]建议：[/bold]{summary.recommendation}")
    console.print(f"[bold]任务 ID：[/bold]{task.id}")


@diagnose_app.command("intranet")
def diagnose_intranet(
    url: Annotated[
        str,
        typer.Option("--url", "-u", help="打不开的内网系统 URL。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """诊断内网系统基础访问链路。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="diagnosis")
        store.save_task_run(task)
        results, summary = run_intranet_diagnosis(
            task=task,
            store=store,
            url=url,
            timeout_ms=loaded.probe_defaults.timeout_ms,
            retries=loaded.probe_defaults.retries,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [url],
                "result_refs": [result.id for result in results],
            }
        )
        store.save_task_run(task)
    except (ConfigError, ValueError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]诊断失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="内网系统访问诊断")
    table.add_column("检查")
    table.add_column("目标")
    table.add_column("状态")
    table.add_column("耗时 ms")
    table.add_column("错误")
    for result in results:
        table.add_row(
            result.probe_type,
            result.target.value,
            result.status.value,
            str(result.duration_ms or ""),
            result.error.message if result.error else "",
        )

    console.print(table)
    console.print(f"[bold]结论：[/bold]{summary.title}")
    console.print(f"[bold]可能范围：[/bold]{summary.likely_area}")
    console.print(f"[bold]建议：[/bold]{summary.recommendation}")
    console.print(f"[bold]任务 ID：[/bold]{task.id}")


@collect_app.command("local")
def collect_local(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """采集本机系统与网络排障上下文。"""
    try:
        _, store = _load_config_and_store(config)
        task = new_task_run(task_type="ops_collect")
        store.save_task_run(task)
        snapshot = collect_local_snapshot(task=task, store=store)
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [snapshot.hostname],
                "result_refs": [snapshot.id],
            }
        )
        store.save_task_run(task)
    except ConfigError as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]本机信息采集失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="本机运维信息")
    table.add_column("项目")
    table.add_column("值")
    table.add_row("主机名", snapshot.hostname)
    table.add_row("FQDN", snapshot.fqdn or "")
    table.add_row("系统", snapshot.os_name)
    table.add_row("网卡数量", str(len(snapshot.interfaces)))
    table.add_row("默认路由", str(len(snapshot.default_routes)))
    table.add_row("DNS", ", ".join(snapshot.dns_servers))
    table.add_row("任务 ID", task.id)
    console.print(table)

    interface_table = Table(title="网卡摘要")
    interface_table.add_column("名称")
    interface_table.add_column("状态")
    interface_table.add_column("IPv4")
    interface_table.add_column("网关")
    for interface in snapshot.interfaces:
        interface_table.add_row(
            interface.name,
            interface.status or "",
            ", ".join(interface.ipv4_addresses),
            ", ".join(interface.default_gateways),
        )
    console.print(interface_table)


@report_app.command("generate")
def report_generate(
    task_id: Annotated[
        str,
        typer.Option("--task", "-t", help="来源任务 ID。"),
    ],
    report_format: Annotated[
        str,
        typer.Option("--format", "-f", help="报告格式：markdown、csv、json。"),
    ] = "markdown",
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """基于任务生成报告。"""
    try:
        loaded, store = _load_config_and_store(config)
        report_task = new_task_run(task_type="report_generate")
        store.save_task_run(report_task)
        output_dir = loaded.reports.output_dir
        if not output_dir.is_absolute():
            output_dir = config.resolve().parent / output_dir
        report = generate_report(
            store=store,
            source_task_id=task_id,
            output_dir=output_dir.resolve(),
            report_format=report_format,
        )
        report_task = finish_task_run(report_task, status=TaskStatus.success)
        report_task = report_task.model_copy(
            update={
                "target_refs": [task_id],
                "result_refs": [report.id],
            }
        )
        store.save_task_run(report_task)
    except (ConfigError, ReportError) as exc:
        if "report_task" in locals():
            failed_task = finish_task_run(report_task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]报告生成失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]报告已生成：[/green]{report.path}")
    console.print(f"报告 ID：{report.id}")


@export_app.command("bundle")
def export_diagnostic_bundle(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    task_id: Annotated[
        str | None,
        typer.Option("--task", "-t", help="只导出指定任务。"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="输出 zip 路径。"),
    ] = None,
) -> None:
    """导出诊断包。"""
    try:
        loaded, store = _load_config_and_store(config)
        output_path = output
        if output_path is None:
            output_path = default_bundle_path(config.resolve().parent / "bundles")
        elif not output_path.is_absolute():
            output_path = config.resolve().parent / output_path
        bundle = export_bundle(
            config=loaded,
            store=store,
            output_path=output_path.resolve(),
            task_id=task_id,
        )
    except (ConfigError, ExportError, TaskRecordNotFound) as exc:
        console.print(f"[red]导出诊断包失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]诊断包已生成：[/green]{bundle}")


@security_app.command("check")
def security_check(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """基于已发现资产执行轻量安全检查。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="security_check")
        store.save_task_run(task)
        findings = run_security_check(config=loaded, task=task, store=store)
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "result_refs": [finding.id for finding in findings],
            }
        )
        store.save_task_run(task)
    except ConfigError as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]安全检查失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="安全发现")
    table.add_column("等级")
    table.add_column("标题")
    table.add_column("建议")

    for finding in findings:
        table.add_row(
            finding.severity.value,
            finding.title,
            finding.recommendation,
        )

    console.print(table)
    console.print(f"[bold]发现数量：[/bold]{len(findings)}")
    console.print(f"[bold]任务 ID：[/bold]{task.id}")


@task_app.command("list")
def task_list(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=1, max=200, help="最大返回数量。"),
    ] = 20,
) -> None:
    """查看任务历史。"""
    try:
        store = _store_from_config(config)
        tasks = list_tasks(store, limit=limit)
    except ConfigError as exc:
        console.print(f"[red]读取任务失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="任务历史")
    table.add_column("ID")
    table.add_column("类型")
    table.add_column("状态")
    table.add_column("风险")
    table.add_column("开始时间")
    table.add_column("结束时间")

    for task in tasks:
        table.add_row(
            task.id,
            task.task_type,
            task.status.value,
            task.risk_level.value,
            task.started_at.isoformat(),
            task.ended_at.isoformat() if task.ended_at else "",
        )

    console.print(table)


@task_app.command("show")
def task_show(
    task_id: Annotated[str, typer.Argument(help="任务 ID。")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看任务详情。"""
    try:
        store = _store_from_config(config)
        task = get_task(store, task_id)
    except ConfigError as exc:
        console.print(f"[red]读取任务失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc
    except TaskRecordNotFound as exc:
        console.print(f"[red]任务不存在：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]任务 ID：[/bold]{task.id}")
    console.print(f"[bold]类型：[/bold]{task.task_type}")
    console.print(f"[bold]状态：[/bold]{task.status.value}")
    console.print(f"[bold]风险：[/bold]{task.risk_level.value}")
    console.print(f"[bold]来源：[/bold]{task.source}")
    console.print(f"[bold]执行人：[/bold]{task.requested_by}")
    console.print(f"[bold]开始时间：[/bold]{task.started_at.isoformat()}")
    console.print(f"[bold]结束时间：[/bold]{task.ended_at.isoformat() if task.ended_at else ''}")
    console.print(f"[bold]目标引用：[/bold]{task.target_refs}")
    console.print(f"[bold]结果引用：[/bold]{task.result_refs}")
    console.print(f"[bold]日志引用：[/bold]{task.log_refs}")

    snapshots = store.list_local_snapshots_for_task(task.id)
    if snapshots:
        snapshot_table = Table(title="本机信息快照")
        snapshot_table.add_column("ID")
        snapshot_table.add_column("主机名")
        snapshot_table.add_column("系统")
        snapshot_table.add_column("网卡数")
        snapshot_table.add_column("采集时间")
        for snapshot in snapshots:
            snapshot_table.add_row(
                snapshot.id,
                snapshot.hostname,
                snapshot.os_name,
                str(len(snapshot.interfaces)),
                snapshot.collected_at.isoformat(),
            )
        console.print(snapshot_table)

    results = store.list_probe_results_for_task(task.id)
    if not results:
        return

    table = Table(title="探测结果")
    table.add_column("类型")
    table.add_column("目标")
    table.add_column("状态")
    table.add_column("耗时 ms")
    table.add_column("错误")

    for result in results:
        table.add_row(
            result.probe_type,
            result.target.value,
            result.status.value,
            str(result.duration_ms or ""),
            result.error.message if result.error else "",
        )

    console.print(table)


def _store_from_config(config_path: Path) -> SQLiteStore:
    loaded, store = _load_config_and_store(config_path)
    return store


def _load_config_and_store(config_path: Path) -> tuple[OpsConfig, SQLiteStore]:
    loaded = load_config(config_path)
    storage_path = loaded.storage.path
    if not storage_path.is_absolute():
        storage_path = config_path.resolve().parent / storage_path
    return loaded, SQLiteStore(storage_path.resolve())

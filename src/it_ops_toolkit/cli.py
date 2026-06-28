from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from . import __version__
from .automation import AutomationError, run_flush_dns_cache
from .assets import (
    AssetExportError,
    AssetImportError,
    AssetScanError,
    default_asset_export_path,
    export_assets,
    import_asset_notes,
    run_asset_diff,
    run_asset_scan,
)
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
    DEFAULT_PRINTER_PORTS,
    DEFAULT_RDP_PORT,
    parse_ports,
    run_dns_diagnosis,
    run_intranet_diagnosis,
    run_internet_diagnosis,
    run_printer_diagnosis,
    run_rdp_diagnosis,
    run_slow_network_diagnosis,
)
from .export import ExportError, default_bundle_path, export_bundle
from .health import HealthCheckError, run_health_check
from .health_matrix import HealthMatrixError, run_health_tcp_matrix
from .health_matrix_http import HealthHttpMatrixError, run_health_http_matrix
from .models import AIOutput, RiskLevel, TaskStatus
from .reports import ReportError, generate_report
from .security import CERT_EXPIRING_SOON_DAYS, run_certificate_check, run_security_check
from .storage import SQLiteStore, TaskRecordNotFound
from .tasks import finish_task_run, get_task, list_tasks, new_task_run
from .alert_engine import (
    AlertEngineError,
    acknowledge_alert as acknowledge_alert_event,
    evaluate_results,
    load_rules_from_config,
)
from .notify import NotificationCenter
from .scheduler import (
    CronExpression,
    SchedulerEngine,
    SchedulerError,
    create_scheduled_task,
)
from .trend import (
    TrendError,
    get_trend,
    get_trend_summary,
    list_available_targets,
)
from .ai_copilot import (
    AIAdapterError,
    explain_anomaly,
    summarize_recent,
    summarize_task,
)

console = Console()


def _make_progress() -> Progress:
    """创建统一的 Rich Progress 实例。"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )

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
automate_app = typer.Typer(help="低风险自动化动作。")
task_app = typer.Typer(help="任务记录。")
web_app = typer.Typer(help="Web Console。")
schedule_app = typer.Typer(help="定时任务调度。")
alert_app = typer.Typer(help="告警管理。")
trend_app = typer.Typer(help="历史趋势分析。")
ai_app = typer.Typer(help="AI 运维助手。")
topology_app = typer.Typer(help="网络拓扑与资产关系。")
probe_app = typer.Typer(help="网络探测（traceroute 等）。")
workflow_app = typer.Typer(help="受控 Agent 工作流。")
app.add_typer(config_app, name="config")
app.add_typer(asset_app, name="asset")
app.add_typer(health_app, name="health")
app.add_typer(diagnose_app, name="diagnose")
app.add_typer(collect_app, name="collect")
app.add_typer(export_app, name="export")
app.add_typer(report_app, name="report")
app.add_typer(security_app, name="security")
app.add_typer(automate_app, name="automate")
app.add_typer(task_app, name="task")
app.add_typer(web_app, name="web")
app.add_typer(schedule_app, name="schedule")
app.add_typer(alert_app, name="alert")
app.add_typer(trend_app, name="trend")
app.add_typer(ai_app, name="ai")
app.add_typer(topology_app, name="topology")
app.add_typer(probe_app, name="probe")
app.add_typer(workflow_app, name="workflow")


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
        progress = _make_progress()
        with progress:
            ptask = progress.add_task("资产扫描", total=None)
            def _cb(desc: str, current: int, total: int) -> None:
                progress.update(ptask, description=desc, completed=current, total=total)
            assets, results = run_asset_scan(
                config=loaded,
                profile_name=profile,
                task=task,
                store=store,
                tcp_without_ping=tcp_without_ping,
                progress_callback=_cb,
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


@asset_app.command("diff")
def asset_diff(
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
    """执行资产变化对比。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="asset_diff")
        store.save_task_run(task)
        assets, results, findings, summary = run_asset_diff(
            config=loaded,
            profile_name=profile,
            task=task,
            store=store,
            tcp_without_ping=tcp_without_ping,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "result_refs": [
                    *(result.id for result in results),
                    *(finding.id for finding in findings),
                ],
                "target_refs": [asset.ip for asset in assets],
                "summary": summary,
            }
        )
        store.save_task_run(task)
    except (ConfigError, AssetScanError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]资产变化对比失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]资产变化对比完成：[/green]{task.id}")
    console.print(f"扫描到资产：{summary['scanned_asset_count']}")
    console.print(f"新增资产：{summary['new_asset_count']}")
    console.print(f"未出现资产：{summary['disappeared_asset_count']}")
    console.print(f"新增开放端口：{summary['newly_open_port_count']}")
    console.print(f"变化发现：{len(findings)}")
    console.print(f"Ping 不通仍扫 TCP：{'是' if tcp_without_ping else '否'}")


@asset_app.command("import-notes")
def asset_import_notes(
    file: Annotated[
        Path,
        typer.Option("--file", "-f", help="资产备注 CSV 文件路径。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """从 CSV 导入资产负责人、用途、类型和标签。"""
    try:
        _, store = _load_config_and_store(config)
        csv_path = file if file.is_absolute() else config.resolve().parent / file
        task = new_task_run(task_type="asset_import_notes")
        store.save_task_run(task)
        summary = import_asset_notes(store=store, csv_path=csv_path.resolve())
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": list(summary["updated_assets"]),
                "result_refs": [str(csv_path.resolve())],
                "summary": summary,
            }
        )
        store.save_task_run(task)
    except (ConfigError, AssetImportError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]资产备注导入失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]资产备注导入完成：[/green]{task.id}")
    console.print(f"更新资产：{summary['updated_count']}")
    console.print(f"跳过行：{summary['skipped_count']}")
    console.print(f"错误行：{summary['error_count']}")


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
    table.add_column("负责人")
    table.add_column("类型")
    table.add_column("开放端口")
    table.add_column("最后发现")

    for asset in assets:
        table.add_row(
            asset.ip,
            asset.hostname or "",
            asset.status,
            asset.owner or "",
            asset.asset_type or "",
            ",".join(str(port) for port in asset.open_ports),
            asset.last_seen.isoformat(),
        )

    console.print(table)


@asset_app.command("export")
def asset_export(
    export_format: Annotated[
        str,
        typer.Option("--format", "-f", help="导出格式：csv、json。"),
    ] = "csv",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="输出文件路径。"),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """导出当前资产清单。"""
    try:
        loaded, store = _load_config_and_store(config)
        output_path = output
        if output_path is None:
            output_dir = loaded.reports.output_dir
            if not output_dir.is_absolute():
                output_dir = config.resolve().parent / output_dir
            output_path = default_asset_export_path(output_dir.resolve(), export_format)
        elif not output_path.is_absolute():
            output_path = config.resolve().parent / output_path

        asset_count = len(store.list_assets())
        exported = export_assets(
            store=store,
            output_path=output_path.resolve(),
            export_format=export_format,
        )
    except (ConfigError, AssetExportError) as exc:
        console.print(f"[red]资产导出失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]资产清单已导出：[/green]{exported}")
    console.print(f"资产数量：{asset_count}")


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
    console.print(f"[bold]负责人：[/bold]{asset.owner or ''}")
    console.print(f"[bold]描述：[/bold]{asset.description or ''}")
    console.print(f"[bold]标签：[/bold]{','.join(asset.tags)}")
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
        progress = _make_progress()
        with progress:
            ptask = progress.add_task("巡检中", total=None)
            def _cb(desc: str, current: int, total: int) -> None:
                progress.update(ptask, description=desc, completed=current, total=total)
            results = run_health_check(
                config=loaded,
                profile_name=profile,
                task=task,
                store=store,
                progress_callback=_cb,
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


@health_app.command("tcp-matrix")
def health_tcp_matrix(
    file: Annotated[
        Path,
        typer.Option("--file", "-f", help="TCP matrix CSV 文件。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """批量执行 TCP 端口可达性测试。"""
    try:
        loaded, store = _load_config_and_store(config)
        csv_path = file if file.is_absolute() else config.resolve().parent / file
        task = new_task_run(task_type="health_matrix")
        store.save_task_run(task)
        progress = _make_progress()
        with progress:
            ptask = progress.add_task("TCP matrix", total=None)
            def _cb(desc: str, current: int, total: int) -> None:
                progress.update(ptask, description=desc, completed=current, total=total)
            summary = run_health_tcp_matrix(
                config=loaded,
                task=task,
                store=store,
                csv_path=csv_path.resolve(),
                progress_callback=_cb,
            )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [
                    f"{entry['host']}:{entry['port']}" for entry in summary["entries"]
                ],
                "result_refs": list(summary["result_ids"]),
                "summary": summary,
            }
        )
        store.save_task_run(task)
    except (ConfigError, HealthMatrixError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]批量 TCP 测试失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]批量 TCP 测试完成：[/green]{task.id}")
    console.print(f"目标数量：{summary['target_count']}")
    console.print(f"成功数量：{summary['success_count']}")
    console.print(f"失败数量：{summary['failed_count']}")


@health_app.command("http-matrix")
def health_http_matrix(
    file: Annotated[
        Path,
        typer.Option("--file", "-f", help="HTTP matrix CSV 文件。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """批量执行 HTTP/HTTPS 可达性测试。"""
    try:
        loaded, store = _load_config_and_store(config)
        csv_path = file if file.is_absolute() else config.resolve().parent / file
        task = new_task_run(task_type="health_matrix")
        store.save_task_run(task)
        progress = _make_progress()
        with progress:
            ptask = progress.add_task("HTTP matrix", total=None)
            def _cb(desc: str, current: int, total: int) -> None:
                progress.update(ptask, description=desc, completed=current, total=total)
            summary = run_health_http_matrix(
                config=loaded,
                task=task,
                store=store,
                csv_path=csv_path.resolve(),
                progress_callback=_cb,
            )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [entry["url"] for entry in summary["entries"]],
                "result_refs": list(summary["result_ids"]),
                "summary": summary,
            }
        )
        store.save_task_run(task)
    except (ConfigError, HealthHttpMatrixError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]批量 HTTP 测试失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]批量 HTTP 测试完成：[/green]{task.id}")
    console.print(f"目标数量：{summary['target_count']}")
    console.print(f"成功数量：{summary['success_count']}")
    console.print(f"失败数量：{summary['failed_count']}")
    mismatch_count = summary.get("mismatch_count", 0)
    if mismatch_count:
        console.print(f"[yellow]状态码不匹配：[/yellow]{mismatch_count}")


@diagnose_app.callback(invoke_without_command=True)
def diagnose_guide(
    ctx: typer.Context,
) -> None:
    """场景化故障诊断 — 交互式引导。

    不指定子命令时，进入交互式诊断引导菜单。
    """
    if ctx.invoked_subcommand is not None:
        return

    console.print("[bold cyan]=== 交互式诊断引导 ===[/bold cyan]")
    console.print("请选择诊断场景：")
    console.print()

    scenarios = [
        ("internet", "互联网连通性诊断", "上不了网 / 外网不通"),
        ("slow-network", "网络慢诊断", "网络延迟高 / 速度慢"),
        ("intranet", "内网系统诊断", "内网系统打不开"),
        ("rdp", "远程桌面诊断", "RDP 连不上"),
        ("printer", "打印机诊断", "打印机不可达"),
        ("dns", "DNS 诊断", "DNS 解析异常"),
    ]

    for i, (key, label, desc) in enumerate(scenarios, 1):
        console.print(f"  [cyan]{i}[/cyan]. {label} [dim]— {desc}[/dim]")

    console.print()
    choice = IntPrompt.ask(
        "选择场景编号",
        choices=[str(i) for i in range(1, len(scenarios) + 1)],
        default="1",
        console=console,
    )

    scenario_key = scenarios[choice - 1][0]
    config_path = Prompt.ask(
        "配置文件路径",
        default=str(DEFAULT_CONFIG_PATH),
        console=console,
    )

    # 根据场景收集额外参数
    extra_args: list[str] = []

    if scenario_key == "internet":
        ext_ip = Prompt.ask("外部 IP（用于 Ping 测试）", default=DEFAULT_EXTERNAL_IP, console=console)
        dns_name = Prompt.ask("DNS 测试域名", default=DEFAULT_DNS_NAME, console=console)
        http_url = Prompt.ask("HTTP 测试 URL", default=DEFAULT_HTTP_URL, console=console)
        extra_args = ["--external-ip", ext_ip, "--dns-name", dns_name, "--http-url", http_url]

    elif scenario_key == "slow-network":
        ext_ip = Prompt.ask("外部 IP", default=DEFAULT_EXTERNAL_IP, console=console)
        dns_name = Prompt.ask("DNS 测试域名", default=DEFAULT_DNS_NAME, console=console)
        http_url = Prompt.ask("HTTP 测试 URL", default=DEFAULT_HTTP_URL, console=console)
        extra_args = ["--external-ip", ext_ip, "--dns-name", dns_name, "--http-url", http_url]

    elif scenario_key == "intranet":
        url = Prompt.ask("内网系统 URL", default="https://intranet.example.local", console=console)
        extra_args = ["--url", url]

    elif scenario_key == "rdp":
        target = Prompt.ask("目标地址（IP 或主机名）", default="192.168.1.50", console=console)
        port = IntPrompt.ask("RDP 端口", default=DEFAULT_RDP_PORT, console=console)
        extra_args = ["--target", target, "--port", str(port)]

    elif scenario_key == "printer":
        target = Prompt.ask("打印机地址（IP 或主机名）", default="printer-01.example.local", console=console)
        ports = Prompt.ask(
            "打印机端口（逗号分隔）",
            default=",".join(str(p) for p in DEFAULT_PRINTER_PORTS),
            console=console,
        )
        extra_args = ["--target", target, "--ports", ports]

    elif scenario_key == "dns":
        name = Prompt.ask("要解析的域名", default=DEFAULT_DNS_NAME, console=console)
        expected_ip = Prompt.ask("期望 IP（可留空）", default="", console=console)
        tcp_port = IntPrompt.ask("TCP 端口验证（0 跳过）", default=0, console=console)
        dns_servers = Prompt.ask("DNS 服务器（逗号分隔，可留空）", default="", console=console)
        extra_args = ["--name", name]
        if expected_ip:
            extra_args += ["--expected-ip", expected_ip]
        if tcp_port > 0:
            extra_args += ["--tcp-port", str(tcp_port)]
        if dns_servers:
            extra_args += ["--dns-servers", dns_servers]

    console.print()
    console.print(f"[dim]即将执行：ops diagnose {scenario_key} --config {config_path} {' '.join(extra_args)}[/dim]")
    if not Confirm.ask("确认执行", default=True, console=console):
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit()

    # 通过 Click 重新调度到子命令
    cmd = ctx.command.commands[scenario_key]
    args = ["--config", config_path, *extra_args]
    sub_ctx = cmd.make_context(scenario_key, args, parent=ctx)
    cmd.invoke(sub_ctx)


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
                "summary": {
                    "scenario": "internet",
                    "scenario_label": "互联网连通性诊断",
                    "title": summary.title,
                    "likely_area": summary.likely_area,
                    "recommendation": summary.recommendation,
                },
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


@diagnose_app.command("slow-network")
def diagnose_slow_network(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    external_ip: Annotated[
        str,
        typer.Option("--external-ip", help="用于测试基础网络延迟的地址。"),
    ] = DEFAULT_EXTERNAL_IP,
    dns_name: Annotated[
        str,
        typer.Option("--dns-name", help="用于测试 DNS 解析耗时的域名。"),
    ] = DEFAULT_DNS_NAME,
    http_url: Annotated[
        str,
        typer.Option("--http-url", help="用于测试 HTTP/HTTPS 响应耗时的 URL。"),
    ] = DEFAULT_HTTP_URL,
) -> None:
    """诊断网络慢的基础链路耗时。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="diagnosis")
        store.save_task_run(task)
        results, summary = run_slow_network_diagnosis(
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
                "summary": {
                    "scenario": "slow_network",
                    "scenario_label": "网络慢基础诊断",
                    "title": summary.title,
                    "likely_area": summary.likely_area,
                    "recommendation": summary.recommendation,
                },
            }
        )
        store.save_task_run(task)
    except ConfigError as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]诊断失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="网络慢基础诊断")
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
                "summary": {
                    "scenario": "intranet",
                    "scenario_label": "内网系统访问诊断",
                    "title": summary.title,
                    "likely_area": summary.likely_area,
                    "recommendation": summary.recommendation,
                },
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


@diagnose_app.command("printer")
def diagnose_printer(
    target: Annotated[
        str,
        typer.Option("--target", "-t", help="打印机目标 IP、主机名或 host:port。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    ports: Annotated[
        str,
        typer.Option("--ports", help="要检查的打印 TCP 端口列表，例如 9100,515,631。"),
    ] = ",".join(str(port) for port in DEFAULT_PRINTER_PORTS),
) -> None:
    """诊断打印机基础可达性。"""
    try:
        loaded, store = _load_config_and_store(config)
        parsed_ports = parse_ports(ports)
        task = new_task_run(task_type="diagnosis")
        store.save_task_run(task)
        results, summary = run_printer_diagnosis(
            task=task,
            store=store,
            target=target,
            ports=parsed_ports,
            timeout_ms=loaded.probe_defaults.timeout_ms,
            retries=loaded.probe_defaults.retries,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [target, *(str(port) for port in parsed_ports)],
                "result_refs": [result.id for result in results],
                "summary": {
                    "scenario": "printer",
                    "scenario_label": "打印机可达性诊断",
                    "title": summary.title,
                    "likely_area": summary.likely_area,
                    "recommendation": summary.recommendation,
                    "ports": parsed_ports,
                },
            }
        )
        store.save_task_run(task)
    except (ConfigError, ValueError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]诊断失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="打印机可达性诊断")
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
    console.print(f"[bold]检查端口：[/bold]{','.join(str(port) for port in parsed_ports)}")
    console.print(f"[bold]任务 ID：[/bold]{task.id}")


@diagnose_app.command("dns")
def diagnose_dns(
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="要诊断的域名或主机名。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    expected_ip: Annotated[
        str | None,
        typer.Option("--expected-ip", help="期望解析结果包含的 IP。"),
    ] = None,
    tcp_port: Annotated[
        int | None,
        typer.Option("--tcp-port", min=1, max=65535, help="对解析出的地址执行 TCP 端口检查。"),
    ] = None,
    dns_servers: Annotated[
        str | None,
        typer.Option("--dns-servers", help="要对比的 DNS 服务器列表，逗号分隔，例如 8.8.8.8,114.114.114.114。"),
    ] = None,
) -> None:
    """诊断 DNS 解析结果和可选目标端口，支持多 DNS 服务器对比。"""
    try:
        loaded, store = _load_config_and_store(config)
        parsed_servers = _parse_dns_servers(dns_servers)
        task = new_task_run(task_type="diagnosis")
        store.save_task_run(task)
        results, summary = run_dns_diagnosis(
            task=task,
            store=store,
            name=name,
            expected_ip=expected_ip,
            tcp_port=tcp_port,
            dns_servers=parsed_servers,
            timeout_ms=loaded.probe_defaults.timeout_ms,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [ref for ref in [name, expected_ip, str(tcp_port) if tcp_port else None] if ref],
                "result_refs": [result.id for result in results],
                "summary": {
                    "scenario": "dns",
                    "scenario_label": "DNS 解析诊断",
                    "title": summary.title,
                    "likely_area": summary.likely_area,
                    "recommendation": summary.recommendation,
                    "expected_ip": expected_ip,
                    "tcp_port": tcp_port,
                    "dns_servers": parsed_servers or [],
                },
            }
        )
        store.save_task_run(task)
    except (ConfigError, ValueError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]诊断失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="DNS 解析诊断")
    table.add_column("检查")
    table.add_column("目标")
    table.add_column("状态")
    table.add_column("耗时 ms")
    table.add_column("观察值")
    table.add_column("错误")
    for result in results:
        table.add_row(
            result.probe_type,
            result.target.value,
            result.status.value,
            str(result.duration_ms or ""),
            _result_observation_summary(result),
            result.error.message if result.error else "",
        )

    console.print(table)
    console.print(f"[bold]结论：[/bold]{summary.title}")
    console.print(f"[bold]可能范围：[/bold]{summary.likely_area}")
    console.print(f"[bold]建议：[/bold]{summary.recommendation}")
    console.print(f"[bold]任务 ID：[/bold]{task.id}")


@diagnose_app.command("rdp")
def diagnose_rdp(
    target: Annotated[
        str,
        typer.Option("--target", "-t", help="远程桌面目标 IP、主机名或 host:port。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    port: Annotated[
        int,
        typer.Option("--port", "-p", min=1, max=65535, help="RDP TCP 端口。"),
    ] = DEFAULT_RDP_PORT,
) -> None:
    """诊断远程桌面基础连接链路。"""
    try:
        loaded, store = _load_config_and_store(config)
        task = new_task_run(task_type="diagnosis")
        store.save_task_run(task)
        results, summary = run_rdp_diagnosis(
            task=task,
            store=store,
            target=target,
            port=port,
            timeout_ms=loaded.probe_defaults.timeout_ms,
            retries=loaded.probe_defaults.retries,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [target],
                "result_refs": [result.id for result in results],
                "summary": {
                    "scenario": "rdp",
                    "scenario_label": "远程桌面连接诊断",
                    "title": summary.title,
                    "likely_area": summary.likely_area,
                    "recommendation": summary.recommendation,
                },
            }
        )
        store.save_task_run(task)
    except (ConfigError, ValueError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]诊断失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="远程桌面连接诊断")
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


@security_app.command("cert-check")
def security_cert_check(
    target: Annotated[
        str,
        typer.Option("--target", "-t", help="HTTPS 主机名、host:port 或 https:// URL。"),
    ],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    warning_days: Annotated[
        int,
        typer.Option("--warning-days", min=1, help="证书剩余天数小于等于该值时提示风险。"),
    ] = CERT_EXPIRING_SOON_DAYS,
) -> None:
    """只读检查 TLS 证书过期风险。"""
    try:
        loaded, store = _load_config_and_store(config)
        host, port = _parse_tls_target(target)
        task = new_task_run(task_type="security_check")
        store.save_task_run(task)
        result, findings = run_certificate_check(
            task=task,
            store=store,
            hostname=host,
            port=port,
            warning_days=warning_days,
            timeout_ms=loaded.probe_defaults.timeout_ms,
        )
        task = finish_task_run(task, status=TaskStatus.success)
        task = task.model_copy(
            update={
                "target_refs": [f"{host}:{port}"],
                "result_refs": [result.id, *(finding.id for finding in findings)],
                "summary": {
                    "scenario": "cert_check",
                    "scenario_label": "证书过期检查",
                    "title": _certificate_summary_title(result, findings),
                    "target": f"{host}:{port}",
                    "days_remaining": result.observations.get("days_remaining"),
                    "warning_days": warning_days,
                },
            }
        )
        store.save_task_run(task)
    except (ConfigError, ValueError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]证书检查失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="证书过期检查")
    table.add_column("目标")
    table.add_column("状态")
    table.add_column("剩余天数")
    table.add_column("错误")
    table.add_row(
        result.target.value,
        result.status.value,
        str(result.observations.get("days_remaining", "")),
        result.error.message if result.error else "",
    )
    console.print(table)

    finding_table = Table(title="证书风险")
    finding_table.add_column("等级")
    finding_table.add_column("标题")
    finding_table.add_column("建议")
    for finding in findings:
        finding_table.add_row(
            finding.severity.value,
            finding.title,
            finding.recommendation,
        )
    console.print(finding_table)
    console.print(f"[bold]发现数量：[/bold]{len(findings)}")
    console.print(f"[bold]任务 ID：[/bold]{task.id}")


@automate_app.command("flush-dns")
def automate_flush_dns(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="只生成计划，不执行清理动作。"),
    ] = False,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="确认执行本机 DNS 缓存清理。"),
    ] = False,
) -> None:
    """清理本机 DNS 缓存，默认只执行 dry-run。"""
    try:
        _, store = _load_config_and_store(config)
        effective_dry_run = dry_run or not confirm
        task = new_task_run(task_type="automation", risk_level=RiskLevel.low_change)
        store.save_task_run(task)
        summary = run_flush_dns_cache(
            task=task,
            dry_run=effective_dry_run,
            confirm=confirm,
        )
        result_status = summary["result"]["status"]
        task_status = (
            TaskStatus.success
            if result_status in {"planned", "success"}
            else TaskStatus.failed
        )
        task = finish_task_run(task, status=task_status)
        task = task.model_copy(
            update={
                "target_refs": ["localhost"],
                "result_refs": [str(summary["result_id"])],
                "summary": summary,
            }
        )
        store.save_task_run(task)
    except (ConfigError, AutomationError) as exc:
        if "task" in locals():
            failed_task = finish_task_run(task, status=TaskStatus.failed)
            store.save_task_run(failed_task)
        console.print(f"[red]自动化动作失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="清理本机 DNS 缓存")
    table.add_column("项目")
    table.add_column("值")
    table.add_row("模式", "dry-run" if summary["dry_run"] else "confirm")
    table.add_row("风险等级", "low_change")
    table.add_row("是否执行", "是" if summary["executed"] else "否")
    table.add_row("结果", str(summary["result"]["status"]))
    table.add_row("任务 ID", task.id)
    console.print(table)
    console.print(f"[bold]结论：[/bold]{summary['title']}")
    console.print(f"[bold]建议：[/bold]{summary['recommendation']}")


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
    table.add_column("结论")
    table.add_column("开始时间")
    table.add_column("结束时间")

    for task in tasks:
        table.add_row(
            task.id,
            _task_type_label(task),
            task.status.value,
            task.risk_level.value,
            str(task.summary.get("title", "")) if task.summary else "",
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
    console.print(f"[bold]类型：[/bold]{_task_type_label(task)}")
    console.print(f"[bold]状态：[/bold]{task.status.value}")
    console.print(f"[bold]风险：[/bold]{task.risk_level.value}")
    console.print(f"[bold]来源：[/bold]{task.source}")
    console.print(f"[bold]执行人：[/bold]{task.requested_by}")
    console.print(f"[bold]开始时间：[/bold]{task.started_at.isoformat()}")
    console.print(f"[bold]结束时间：[/bold]{task.ended_at.isoformat() if task.ended_at else ''}")
    console.print(f"[bold]目标引用：[/bold]{task.target_refs}")
    console.print(f"[bold]结果引用：[/bold]{task.result_refs}")
    console.print(f"[bold]日志引用：[/bold]{task.log_refs}")
    results = store.list_probe_results_for_task(task.id)

    if task.summary:
        console.print(f"[bold]摘要：[/bold]{task.summary.get('title', '')}")
        console.print(f"[bold]可能范围：[/bold]{task.summary.get('likely_area', '')}")
        console.print(f"[bold]建议：[/bold]{task.summary.get('recommendation', '')}")
        if task.summary.get("scenario") == "printer" and task.summary.get("ports"):
            ports = ",".join(str(port) for port in task.summary["ports"])
            console.print(f"[bold]检查端口：[/bold]{ports}")
            reachable_ports: list[str] = []
            for result in results:
                if result.probe_type != "tcp" or result.status.value != "success":
                    continue
                port = result.observations.get("port")
                if port is None and ":" in result.target.value:
                    port = result.target.value.rsplit(":", 1)[-1]
                if port is None:
                    continue
                port_value = str(port)
                if port_value not in reachable_ports:
                    reachable_ports.append(port_value)
            console.print(f"[bold]可达端口：[/bold]{','.join(reachable_ports) if reachable_ports else '无'}")
        if task.summary.get("scenario") == "dns":
            if task.summary.get("expected_ip"):
                console.print(f"[bold]期望 IP：[/bold]{task.summary.get('expected_ip')}")
            resolved_addresses: list[str] = []
            tcp_reachable_addresses: list[str] = []
            for result in results:
                if result.probe_type == "dns":
                    addresses = result.observations.get("addresses", [])
                    if isinstance(addresses, list):
                        resolved_addresses = [str(address) for address in addresses]
                if result.probe_type == "tcp" and result.status.value == "success":
                    tcp_reachable_addresses.append(result.target.value)
            console.print(
                f"[bold]解析地址：[/bold]{','.join(resolved_addresses) if resolved_addresses else '无'}"
            )
            if task.summary.get("expected_ip"):
                matched = str(task.summary.get("expected_ip")) in resolved_addresses
                console.print(f"[bold]期望命中：[/bold]{'是' if matched else '否'}")
            if task.summary.get("tcp_port"):
                console.print(f"[bold]TCP 检查端口：[/bold]{task.summary.get('tcp_port')}")
                console.print(
                    f"[bold]TCP 可达地址：[/bold]{','.join(tcp_reachable_addresses) if tcp_reachable_addresses else '无'}"
                )

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


@web_app.command("run")
def web_run(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    host: Annotated[
        str,
        typer.Option("--host", help="监听地址。"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="监听端口。"),
    ] = 8080,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="开发模式热重载。"),
    ] = False,
) -> None:
    """启动 Web Console 服务。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    store.ensure_schema()

    try:
        import uvicorn
    except ImportError as exc:
        console.print("[red]缺少 Web 依赖。[/red]请安装：pip install 'it-ops-toolkit[web]'")
        raise typer.Exit(code=1) from exc

    from .web.app import app as web_app_instance, set_config, set_store

    set_store(store)
    set_config(loaded)
    console.print(f"[bold green]Web Console 启动中...[/bold green]")
    console.print(f"  地址：[cyan]http://{host}:{port}[/cyan]")
    console.print(f"  API 文档：[cyan]http://{host}:{port}/docs[/cyan]")
    console.print(f"  数据库：[dim]{store.path}[/dim]")
    console.print(f"  巡检配置：[dim]{', '.join(loaded.health_profiles.keys()) or '无'}[/dim]")
    console.print(f"  扫描配置：[dim]{', '.join(loaded.scan_profiles.keys()) or '无'}[/dim]")
    console.print(f"  [yellow]按 Ctrl+C 停止服务[/yellow]")
    uvicorn.run(web_app_instance, host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------
# 定时任务调度
# ---------------------------------------------------------------------------


@schedule_app.command("list")
def schedule_list(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """列出所有定时任务。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    engine = SchedulerEngine(config=loaded, store=store)
    tasks = engine.list_tasks()

    if not tasks:
        console.print("[dim]没有定时任务。[/dim]")
        return

    table = Table(title="定时任务")
    table.add_column("ID")
    table.add_column("名称")
    table.add_column("类型")
    table.add_column("Profile")
    table.add_column("Cron")
    table.add_column("启用")
    table.add_column("上次状态")
    table.add_column("下次执行")
    table.add_column("告警级别")

    for task in tasks:
        table.add_row(
            task.id,
            task.name,
            task.task_type,
            task.profile,
            task.cron,
            "✓" if task.enabled else "✗",
            task.last_status.value if task.last_status else "-",
            task.next_run.isoformat() if task.next_run else "-",
            ",".join(s.value for s in task.alert_on) if task.alert_on else "-",
        )

    console.print(table)


@schedule_app.command("add")
def schedule_add(
    name: Annotated[str, typer.Option("--name", help="任务名称。")],
    cron: Annotated[str, typer.Option("--cron", help="Cron 表达式（分 时 日 月 周）。")],
    task_type: Annotated[str, typer.Option("--type", help="任务类型：health_check / security_check / asset_scan。")] = "health_check",
    profile: Annotated[str, typer.Option("--profile", help="巡检/扫描配置 profile 名称。")] = "default",
    alert_on: Annotated[str, typer.Option("--alert-on", help="触发告警的级别，逗号分隔。")] = "warning,critical",
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """添加一个定时任务。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    alert_levels = [s.strip() for s in alert_on.split(",") if s.strip()]

    try:
        task = create_scheduled_task(
            name=name,
            task_type=task_type,
            profile=profile,
            cron=cron,
            alert_on=alert_levels,
        )
    except SchedulerError as exc:
        console.print(f"[red]创建任务失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    engine = SchedulerEngine(config=loaded, store=store)
    engine.add_task(task)
    console.print(f"[green]已添加定时任务：[/green]{task.id}")
    console.print(f"  名称：{task.name}")
    console.print(f"  类型：{task.task_type}")
    console.print(f"  Cron：{task.cron}")
    console.print(f"  下次执行：{task.next_run.isoformat() if task.next_run else '-'}")


@schedule_app.command("remove")
def schedule_remove(
    task_id: Annotated[str, typer.Argument(help="任务 ID。")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """删除一个定时任务。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    engine = SchedulerEngine(config=loaded, store=store)
    removed = engine.remove_task(task_id)
    if removed:
        console.print(f"[green]已删除定时任务：[/green]{task_id}")
    else:
        console.print(f"[red]任务不存在：[/red]{task_id}")
        raise typer.Exit(code=1)


@schedule_app.command("enable")
def schedule_enable(
    task_id: Annotated[str, typer.Argument(help="任务 ID。")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """启用一个定时任务。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    engine = SchedulerEngine(config=loaded, store=store)
    task = engine.enable_task(task_id)
    if task:
        console.print(f"[green]已启用：[/green]{task.name}")
    else:
        console.print(f"[red]任务不存在：[/red]{task_id}")
        raise typer.Exit(code=1)


@schedule_app.command("disable")
def schedule_disable(
    task_id: Annotated[str, typer.Argument(help="任务 ID。")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """禁用一个定时任务。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    engine = SchedulerEngine(config=loaded, store=store)
    task = engine.disable_task(task_id)
    if task:
        console.print(f"[green]已禁用：[/green]{task.name}")
    else:
        console.print(f"[red]任务不存在：[/red]{task_id}")
        raise typer.Exit(code=1)


@schedule_app.command("run-now")
def schedule_run_now(
    task_id: Annotated[str, typer.Argument(help="任务 ID。")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """立即执行一次定时任务（不等调度时间）。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    engine = SchedulerEngine(config=loaded, store=store)
    task = engine.run_task_now(task_id)
    if task is None:
        console.print(f"[red]任务不存在：[/red]{task_id}")
        raise typer.Exit(code=1)

    if task.last_status and task.last_status.value == "success":
        console.print(f"[green]执行完成：[/green]{task.name}")
    else:
        console.print(f"[red]执行失败：[/red]{task.name}")
        if task.last_error:
            console.print(f"  错误：{task.last_error}")
        raise typer.Exit(code=1)


@schedule_app.command("run")
def schedule_run(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    poll_interval: Annotated[
        float,
        typer.Option("--poll-interval", help="轮询间隔（秒）。"),
    ] = 30.0,
) -> None:
    """以阻塞模式运行调度器（无 Web Console）。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    store.ensure_schema()
    engine = SchedulerEngine(
        config=loaded, store=store, poll_interval_seconds=poll_interval
    )

    tasks = engine.list_tasks()
    console.print(f"[bold green]调度器启动中...[/bold green]")
    console.print(f"  定时任务数：[cyan]{len(tasks)}[/cyan]")
    console.print(f"  轮询间隔：[dim]{poll_interval}s[/dim]")
    console.print(f"  数据库：[dim]{store.path}[/dim]")
    for task in tasks:
        console.print(
            f"  {'✓' if task.enabled else '✗'} {task.name} "
            f"[dim]{task.cron}[/dim] "
            f"下次: [dim]{task.next_run.isoformat() if task.next_run else '-'}[/dim]"
        )
    console.print(f"  [yellow]按 Ctrl+C 停止[/yellow]")

    try:
        engine.run_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]调度器已停止。[/yellow]")


# ---------------------------------------------------------------------------
# 告警管理
# ---------------------------------------------------------------------------


@alert_app.command("list")
def alert_list(
    status: Annotated[
        str | None,
        typer.Option("--status", help="按状态筛选：active / resolved / suppressed。"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="最多返回条数。"),
    ] = 50,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """列出告警事件。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    events = store.list_alert_events(status=status, limit=limit)

    if not events:
        console.print("[dim]没有告警事件。[/dim]")
        return

    table = Table(title="告警事件")
    table.add_column("ID")
    table.add_column("严重程度")
    table.add_column("规则")
    table.add_column("目标")
    table.add_column("实际值")
    table.add_column("阈值")
    table.add_column("状态")
    table.add_column("已确认")
    table.add_column("触发时间")

    severity_colors = {
        "critical": "red",
        "warning": "yellow",
        "info": "blue",
    }

    for event in events:
        color = severity_colors.get(event.severity.value, "white")
        table.add_row(
            event.id,
            f"[{color}]{event.severity.value.upper()}[/{color}]",
            event.rule_name,
            event.target,
            event.value,
            event.threshold,
            event.status.value,
            "✓" if event.acknowledged else "✗",
            event.triggered_at.isoformat(),
        )

    console.print(table)


@alert_app.command("acknowledge")
def alert_acknowledge(
    event_id: Annotated[str, typer.Argument(help="告警事件 ID。")],
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """确认一个告警事件。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    try:
        event = acknowledge_alert_event(event_id=event_id, store=store)
    except AlertEngineError as exc:
        console.print(f"[red]确认失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]已确认告警：[/green]{event.id}")
    console.print(f"  规则：{event.rule_name}")
    console.print(f"  目标：{event.target}")
    console.print(f"  确认时间：{event.acknowledged_at.isoformat() if event.acknowledged_at else '-'}")


@alert_app.command("rules")
def alert_rules(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """列出已配置的告警规则。"""
    try:
        loaded, _ = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    rules = load_rules_from_config(loaded.alert_rules)

    if not rules:
        console.print("[dim]没有告警规则。[/dim]")
        return

    table = Table(title="告警规则")
    table.add_column("ID")
    table.add_column("名称")
    table.add_column("探针类型")
    table.add_column("指标")
    table.add_column("操作符")
    table.add_column("阈值")
    table.add_column("严重程度")
    table.add_column("冷却(分)")
    table.add_column("启用")

    for rule in rules:
        table.add_row(
            rule.id,
            rule.name,
            rule.condition.probe_type,
            rule.condition.metric,
            rule.condition.operator,
            str(rule.condition.threshold),
            rule.severity.value,
            str(rule.cooldown_minutes),
            "✓" if rule.enabled else "✗",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# 历史趋势分析
# ---------------------------------------------------------------------------


@trend_app.command("targets")
def trend_targets(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
    probe_type: Annotated[
        str | None,
        typer.Option("--type", help="按探针类型筛选。"),
    ] = None,
) -> None:
    """列出有历史数据的目标。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    targets = list_available_targets(store=store, probe_type=probe_type)

    if not targets:
        console.print("[dim]没有历史数据。[/dim]")
        return

    table = Table(title="可用目标")
    table.add_column("探针类型")
    table.add_column("目标")

    for t in targets:
        table.add_row(t["probe_type"], t["target"])

    console.print(table)


@trend_app.command("show")
def trend_show(
    probe_type: Annotated[str, typer.Argument(help="探针类型：ping / dns / tcp / http / tls_cert。")],
    target: Annotated[str | None, typer.Option("--target", help="目标筛选。")] = None,
    metric: Annotated[
        str | None,
        typer.Option("--metric", help="指定指标，不指定则返回所有。"),
    ] = None,
    days: Annotated[
        int,
        typer.Option("--days", help="查询天数范围。"),
    ] = 7,
    granularity: Annotated[
        str,
        typer.Option("--granularity", help="聚合粒度：daily / hourly。"),
    ] = "daily",
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看趋势详情（含时间序列）。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    try:
        trend = get_trend(
            store=store,
            probe_type=probe_type,
            target=target,
            metric=metric,
            days=days,
            granularity=granularity,
        )
    except TrendError as exc:
        console.print(f"[red]查询失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    dist = trend["status_distribution"]
    console.print(f"\n[bold]探针类型：[/bold]{probe_type}  [bold]目标：[/bold]{target or '全部'}  [bold]范围：[/bold]{days} 天")
    console.print(
        f"  总检查数：{dist['total']}  "
        f"成功率：[green]{dist['success_rate']}%[/green]  "
        f"失败：[red]{dist['failed_count']}[/red]  "
        f"超时：[yellow]{dist['timeout_count']}[/yellow]"
    )

    for m, stats in trend["metric_stats"].items():
        console.print(f"\n[bold cyan]指标：{m}[/bold cyan]")
        table = Table(title=f"{m} 趋势")
        table.add_column("时间")
        table.add_column("样本数")
        table.add_column("平均")
        table.add_column("最小")
        table.add_column("最大")
        table.add_column("P95")

        for s in stats:
            table.add_row(
                s["time_bucket"],
                str(s["count"]),
                str(s["avg"]) if s["avg"] is not None else "-",
                str(s["min"]) if s["min"] is not None else "-",
                str(s["max"]) if s["max"] is not None else "-",
                str(s["p95"]) if s["p95"] is not None else "-",
            )

        console.print(table)


@trend_app.command("summary")
def trend_summary(
    probe_type: Annotated[str, typer.Argument(help="探针类型。")],
    target: Annotated[str | None, typer.Option("--target", help="目标筛选。")] = None,
    days: Annotated[
        int,
        typer.Option("--days", help="查询天数范围。"),
    ] = 7,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看趋势摘要（快速概览）。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    try:
        summary = get_trend_summary(
            store=store,
            probe_type=probe_type,
            target=target,
            days=days,
        )
    except TrendError as exc:
        console.print(f"[red]查询失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"\n[bold]趋势摘要：[/bold]{probe_type} / {target or '全部'} / {days} 天")
    console.print(f"  总检查数：{summary['total_checks']}")
    console.print(f"  成功率：[green]{summary['success_rate']}%[/green]")
    console.print(f"  失败：[red]{summary['failed_count']}[/red]  超时：[yellow]{summary['timeout_count']}[/yellow]")

    if summary["metrics"]:
        table = Table(title="指标汇总")
        table.add_column("指标")
        table.add_column("数据点")
        table.add_column("平均")
        table.add_column("最小")
        table.add_column("最大")
        table.add_column("P95均值")

        for m, stats in summary["metrics"].items():
            table.add_row(
                m,
                str(stats["data_points"]),
                str(stats["avg"]) if stats["avg"] is not None else "-",
                str(stats["min"]) if stats["min"] is not None else "-",
                str(stats["max"]) if stats["max"] is not None else "-",
                str(stats["p95_avg"]) if stats["p95_avg"] is not None else "-",
            )
        console.print(table)
    else:
        console.print("[dim]无数值型指标数据。[/dim]")


# ---------------------------------------------------------------------------
# AI 运维助手
# ---------------------------------------------------------------------------


@ai_app.command("summarize")
def ai_summarize(
    task_id: Annotated[str, typer.Argument(help="任务 ID。")],
    prompt: Annotated[
        str | None,
        typer.Option("--prompt", help="自定义提示词。"),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """对指定任务生成 AI 摘要。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    try:
        output = summarize_task(
            task_id=task_id,
            store=store,
            config=loaded,
            prompt=prompt,
        )
    except AIAdapterError as exc:
        console.print(f"[red]AI 摘要失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    _print_ai_output(output)


@ai_app.command("explain")
def ai_explain(
    task_id: Annotated[str, typer.Argument(help="任务 ID。")],
    question: Annotated[
        str | None,
        typer.Option("--question", help="自然语言提问。"),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """解释指定任务中的异常。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    try:
        output = explain_anomaly(
            task_id=task_id,
            store=store,
            config=loaded,
            question=question,
        )
    except AIAdapterError as exc:
        console.print(f"[red]AI 解释失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    _print_ai_output(output)


@ai_app.command("weekly")
def ai_weekly(
    days: Annotated[
        int,
        typer.Option("--days", help="汇总天数。"),
    ] = 7,
    prompt: Annotated[
        str | None,
        typer.Option("--prompt", help="自定义提示词。"),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """生成 AI 周报摘要。"""
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    try:
        output = summarize_recent(
            store=store,
            config=loaded,
            days=days,
            prompt=prompt,
        )
    except AIAdapterError as exc:
        console.print(f"[red]AI 周报失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    _print_ai_output(output)


@ai_app.command("logs")
def ai_logs(
    task_id: Annotated[
        str | None,
        typer.Option("--task", help="按任务 ID 筛选。"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="最多返回条数。"),
    ] = 50,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看 AI 调用审计日志。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    logs = store.list_ai_call_logs(task_id=task_id, limit=limit)

    if not logs:
        console.print("[dim]没有 AI 调用记录。[/dim]")
        return

    table = Table(title="AI 调用日志")
    table.add_column("ID")
    table.add_column("任务 ID")
    table.add_column("后端")
    table.add_column("成功")
    table.add_column("耗时(ms)")
    table.add_column("错误")
    table.add_column("时间")

    for log in logs:
        table.add_row(
            log.id,
            log.task_id,
            log.backend,
            "✓" if log.success else "✗",
            str(log.duration_ms),
            log.error or "-",
            log.called_at.isoformat(),
        )

    console.print(table)


def _print_ai_output(output: AIOutput) -> None:
    """格式化输出 AI 结果。"""
    console.print(f"\n[bold]摘要：[/bold]{output.summary}")
    console.print(f"  后端：[cyan]{output.backend}[/cyan]  置信度：{output.confidence}  耗时：{output.duration_ms or '-'}ms")

    if output.facts:
        console.print(f"\n[bold green]事实：[/bold green]")
        for i, fact in enumerate(output.facts, 1):
            console.print(f"  {i}. {fact}")

    if output.inferences:
        console.print(f"\n[bold yellow]推断：[/bold yellow]")
        for i, inf in enumerate(output.inferences, 1):
            console.print(f"  {i}. {inf}")

    if output.recommendations:
        console.print(f"\n[bold blue]建议：[/bold blue]")
        for i, rec in enumerate(output.recommendations, 1):
            console.print(f"  {i}. {rec}")

    if output.needs_human_review:
        console.print(f"\n[bold red]⚠ 需要人工确认[/bold red]")

    if output.sources:
        console.print(f"\n[dim]引用来源：{', '.join(output.sources)}[/dim]")


def _store_from_config(config_path: Path) -> SQLiteStore:
    loaded, store = _load_config_and_store(config_path)
    return store


def _load_config_and_store(config_path: Path) -> tuple[OpsConfig, SQLiteStore]:
    loaded = load_config(config_path)
    storage_path = loaded.storage.path
    if not storage_path.is_absolute():
        storage_path = config_path.resolve().parent / storage_path
    return loaded, SQLiteStore(storage_path.resolve())


def _parse_dns_servers(value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    servers = [s.strip() for s in value.split(",") if s.strip()]
    if not servers:
        return []
    return servers


def _task_type_label(task) -> str:
    if task.task_type == "asset_scan":
        return "资产扫描"
    if task.task_type == "asset_diff":
        return str(task.summary.get("scenario_label", "")).strip() or "资产变化对比"
    if task.task_type == "asset_import_notes":
        return str(task.summary.get("scenario_label", "")).strip() or "资产备注导入"
    if task.task_type == "health_check":
        return "巡检"
    if task.task_type == "security_check":
        if task.summary.get("scenario_label"):
            return str(task.summary["scenario_label"])
        return "安全检查"
    if task.task_type == "report_generate":
        return "报告生成"
    if task.task_type == "ops_collect":
        return "本机信息采集"
    if task.task_type == "automation":
        return str(task.summary.get("scenario_label", "")).strip() or "自动化动作"
    if task.task_type == "diagnosis":
        return str(task.summary.get("scenario_label", "")).strip() or "诊断"
    return task.task_type


def _result_observation_summary(result) -> str:
    if result.probe_type == "dns":
        addresses = result.observations.get("addresses", [])
        if isinstance(addresses, list):
            return ",".join(str(address) for address in addresses)
    if result.probe_type == "tcp":
        port = result.observations.get("port", "")
        open_state = result.observations.get("open", "")
        return f"port={port}, open={open_state}"
    if result.probe_type == "tls_cert":
        days = result.observations.get("days_remaining", "")
        expires = result.observations.get("expires_at", "")
        return f"days_remaining={days}, expires_at={expires}"
    return ""


def _parse_tls_target(value: str) -> tuple[str, int]:
    raw = value.strip()
    if not raw:
        raise ValueError("target is required")
    parsed = urlparse(raw)
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("certificate target must be an https:// URL or host[:port]")
        return parsed.hostname, parsed.port or 443
    if raw.count(":") == 1:
        host, raw_port = raw.rsplit(":", 1)
        if host and raw_port.isdigit():
            port = int(raw_port)
            if port < 1 or port > 65535:
                raise ValueError(f"invalid TCP port: {port}")
            return host, port
    return raw, 443


def _certificate_summary_title(result, findings) -> str:
    if findings:
        return findings[0].title
    if result.status.value != "success":
        return "TLS 证书检查失败"
    return "TLS 证书有效"


# ---------------------------------------------------------------------------
# Phase 8：网络拓扑与资产关系
# ---------------------------------------------------------------------------


@topology_app.command("show")
def topology_show(
    traceroute_target: str = typer.Option(
        None, "--traceroute", "-t", help="可选：对指定目标执行 traceroute"
    ),
    max_hops: int = typer.Option(15, "--max-hops", help="traceroute 最大跳数"),
    reconcile: bool = typer.Option(
        True, "--reconcile/--no-reconcile", help="是否与资产库对比"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """展示本机视角的网络拓扑。"""
    from .topology import get_topology

    store = None
    if reconcile:
        try:
            store = _store_from_config(config)
        except ConfigError as exc:
            console.print(f"[red]读取配置失败：[/red]{exc}")
            raise typer.Exit(code=1) from exc

    view = get_topology(
        store=store,
        traceroute_target=traceroute_target,
        max_hops=max_hops,
    )

    if output_format == "json":
        typer.echo(view.model_dump_json(indent=2))
        return

    _print_topology_table(view)


@topology_app.command("arp")
def topology_arp(
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
) -> None:
    """采集并展示本机 ARP 表。"""
    from .probes.arp import collect_arp_table

    entries = collect_arp_table()

    if output_format == "json":
        import json

        typer.echo(
            json.dumps([e.model_dump() for e in entries], indent=2, ensure_ascii=False)
        )
        return

    if not entries:
        typer.echo("ARP 表为空。")
        return

    typer.echo(f"共 {len(entries)} 条 ARP 记录：\n")
    typer.echo(f"{'IP':<18} {'MAC':<20} {'接口':<16} {'状态':<10} {'厂商':<20} {'类型'}")
    typer.echo("-" * 100)
    for e in entries:
        typer.echo(
            f"{e.ip:<18} {e.mac:<20} {e.interface:<16} {e.state:<10} "
            f"{(e.vendor or 'Unknown'):<20} {(e.device_type or 'unknown')}"
        )


@topology_app.command("unknown")
def topology_unknown(
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """检测 ARP 表中不在资产库的未知设备。"""
    from .probes.arp import collect_arp_table
    from .topology import detect_unknown_devices

    try:
        store = _store_from_config(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    arp_entries = collect_arp_table()
    unknown = detect_unknown_devices(arp_entries=arp_entries, store=store)

    if output_format == "json":
        import json

        typer.echo(
            json.dumps([e.model_dump() for e in unknown], indent=2, ensure_ascii=False)
        )
        return

    if not unknown:
        typer.echo("未发现未知设备。")
        return

    typer.echo(f"⚠️  发现 {len(unknown)} 个未知设备：\n")
    typer.echo(f"{'IP':<18} {'MAC':<20} {'厂商':<20} {'类型'}")
    typer.echo("-" * 70)
    for e in unknown:
        typer.echo(
            f"{e.ip:<18} {e.mac:<20} {(e.vendor or 'Unknown'):<20} {(e.device_type or 'unknown')}"
        )


@probe_app.command("traceroute")
def probe_traceroute(
    target: str = typer.Argument(..., help="目标主机（IP 或主机名）"),
    max_hops: int = typer.Option(15, "--max-hops", "-m", help="最大跳数"),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
) -> None:
    """执行路由追踪。"""
    from .probes.traceroute import run_traceroute

    result = run_traceroute(target=target, max_hops=max_hops)

    if output_format == "json":
        typer.echo(result.model_dump_json(indent=2))
        return

    typer.echo(f"路由追踪：{result.source} → {result.target}")
    typer.echo(f"总跳数：{result.total_hops}  到达：{'是' if result.reached else '否'}\n")
    typer.echo(f"{'跳数':<6} {'IP':<18} {'RTT (ms)':<30} {'状态'}")
    typer.echo("-" * 70)
    for hop in result.hops:
        if hop.timeout:
            typer.echo(f"{hop.hop:<6} {'*':<18} {'* * *':<30} 超时")
        else:
            rtt_str = "  ".join(f"{r:.1f}" for r in hop.rtt_ms) if hop.rtt_ms else "-"
            typer.echo(f"{hop.hop:<6} {(hop.ip or '*'):<18} {rtt_str:<30} 正常")


@probe_app.command("snmp")
def probe_snmp(
    target: Annotated[
        str,
        typer.Argument(help="目标设备 IP 地址。"),
    ],
    community: Annotated[
        str,
        typer.Option("--community", help="SNMP community 字符串。"),
    ] = "public",
    port: Annotated[
        int,
        typer.Option("--port", help="SNMP UDP 端口。"),
    ] = 161,
    oid: Annotated[
        str,
        typer.Option("--oid", help="查询单个 OID（不指定则采集设备基础信息）。"),
    ] = "",
    timeout_ms: Annotated[
        int,
        typer.Option("--timeout", help="超时时间（毫秒）。"),
    ] = 3000,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """通过 SNMP v2c 采集设备信息或查询单个 OID。"""
    from .probes.snmp import collect_snmp_info, snmp_get, SnmpError

    if oid:
        # 查询单个 OID
        try:
            resp_oid, value = snmp_get(
                target=target,
                oid=oid,
                community=community,
                port=port,
                timeout_ms=timeout_ms,
            )
            console.print(f"[green]SNMP GET 成功[/green]")
            console.print(f"  OID: {resp_oid}")
            console.print(f"  值: {value}")
        except SnmpError as exc:
            console.print(f"[red]SNMP GET 失败：[/red]{exc}")
            raise typer.Exit(code=1) from exc
        return

    # 采集设备基础信息
    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    task = new_task_run(task_type="snmp_probe")
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
    task = task.model_copy(update={"result_refs": [result.id]})
    store.save_task_run(task)

    if result.status != "success":
        console.print(f"[red]SNMP 采集失败：[/red]{result.error.message if result.error else '未知错误'}")
        raise typer.Exit(code=1)

    obs = result.observations
    console.print(f"[green]SNMP 设备信息采集完成[/green]  任务 ID: {task.id}")
    console.print()

    table = Table(title=f"SNMP 设备信息 — {target}")
    table.add_column("属性", style="cyan")
    table.add_column("值")
    table.add_row("sysDescr", str(obs.get("sysDescr", "-")))
    table.add_row("sysName", str(obs.get("sysName", "-")))
    table.add_row("sysObjectID", str(obs.get("sysObjectID", "-")))
    table.add_row("sysUpTime", str(obs.get("sysUpTime", "-")))
    table.add_row("sysContact", str(obs.get("sysContact", "-")))
    table.add_row("sysLocation", str(obs.get("sysLocation", "-")))
    table.add_row("sysServices", str(obs.get("sysServices", "-")))
    table.add_row("接口数量", str(obs.get("interface_count", "-")))

    console.print(table)

    # 接口列表
    interfaces = obs.get("interfaces", [])
    if interfaces:
        console.print()
        iface_table = Table(title="接口列表")
        iface_table.add_column("序号")
        iface_table.add_column("描述")
        iface_table.add_column("状态")
        for iface in interfaces:
            status_str = str(iface.get("oper_status", "-"))
            # SNMP ifOperStatus: 1=up, 2=down, 3=testing
            if status_str == "1":
                status_str = "[green]up[/green]"
            elif status_str == "2":
                status_str = "[red]down[/red]"
            elif status_str == "3":
                status_str = "[yellow]testing[/yellow]"
            iface_table.add_row(
                str(iface.get("index", "-")),
                str(iface.get("descr", "-")),
                status_str,
            )
        console.print(iface_table)


def _print_topology_table(view) -> None:
    """以表格形式打印拓扑视图。"""
    typer.echo("=" * 70)
    typer.echo("网络拓扑视图（本机视角）")
    typer.echo("=" * 70)

    typer.echo(f"\n本机 IP：{view.source}")
    typer.echo(f"默认网关：{view.gateway or '未检测到'}")

    # 网络接口
    if view.interfaces:
        typer.echo("\n── 网络接口 ──")
        for iface in view.interfaces:
            typer.echo(
                f"  {iface.get('name', '?')}: {iface.get('ip', 'N/A')}"
            )

    # ARP 表
    if view.arp_entries:
        typer.echo(f"\n── ARP 表（{len(view.arp_entries)} 条）──")
        typer.echo(
            f"  {'IP':<16} {'MAC':<20} {'厂商':<20} {'类型'}"
        )
        typer.echo(f"  {'-'*66}")
        for e in view.arp_entries:
            typer.echo(
                f"  {e.ip:<16} {e.mac:<20} {(e.vendor or 'Unknown'):<20} "
                f"{(e.device_type or 'unknown')}"
            )

    # Traceroute
    if view.traceroute:
        tr = view.traceroute
        typer.echo(f"\n── Traceroute: {tr.source} → {tr.target} ──")
        typer.echo(f"  总跳数：{tr.total_hops}  到达：{'是' if tr.reached else '否'}")
        for hop in tr.hops:
            if hop.timeout:
                typer.echo(f"  Hop {hop.hop}: * * * (超时)")
            else:
                rtt = "  ".join(f"{r:.1f}ms" for r in hop.rtt_ms) if hop.rtt_ms else "-"
                typer.echo(f"  Hop {hop.hop}: {hop.ip}  {rtt}")

    # 资产对比
    if view.reconciliation:
        rec = view.reconciliation
        typer.echo("\n── 资产对比 ──")
        typer.echo(f"  匹配设备：{len(rec.matched)}")
        typer.echo(f"  新设备（ARP 有、资产库无）：{len(rec.new_devices)}")
        typer.echo(f"  离线设备（资产库有、ARP 无）：{len(rec.offline_devices)}")
        typer.echo(f"  未知厂商：{len(rec.unknown_vendors)}")

        if rec.new_devices:
            typer.echo("\n  ⚠️ 新设备：")
            for d in rec.new_devices:
                typer.echo(
                    f"    {d.ip}  {d.mac}  {d.vendor or 'Unknown'}"
                )

        if rec.offline_devices:
            typer.echo("\n  💤 离线设备：")
            for d in rec.offline_devices:
                typer.echo(f"    {d.ip}  {d.hostname or d.mac or 'N/A'}")

    typer.echo("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Phase 9：受控 Agent 工作流
# ---------------------------------------------------------------------------


@workflow_app.command("list")
def workflow_list(
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
) -> None:
    """列出所有可用工作流。"""
    from .agent_workflow import get_builtin_workflows

    workflows = get_builtin_workflows()

    if output_format == "json":
        import json

        typer.echo(
            json.dumps(
                [w.model_dump() for w in workflows], indent=2, ensure_ascii=False
            )
        )
        return

    typer.echo(f"共 {len(workflows)} 个可用工作流：\n")
    for wf in workflows:
        typer.echo(f"  📋 {wf.name}")
        typer.echo(f"     {wf.description}")
        typer.echo(f"     步骤：{' → '.join(s.id for s in wf.steps)}")
        typer.echo(f"     触发：{', '.join(wf.triggers)}")
        typer.echo()


@workflow_app.command("run")
def workflow_run(
    name: str = typer.Argument(..., help="工作流名称"),
    confirm: bool = typer.Option(
        False, "--confirm", help="自动批准低风险变更步骤"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """执行指定工作流。"""
    from .agent_workflow import (
        WorkflowError,
        execute_workflow,
        get_workflow_by_name,
    )

    try:
        loaded, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    try:
        wf = get_workflow_by_name(name)
    except WorkflowError as exc:
        console.print(f"[red]工作流不存在：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]开始执行工作流：[/bold]{wf.name}")
    console.print(f"  {wf.description}\n")

    execution = execute_workflow(
        workflow=wf,
        store=store,
        config=loaded,
        trigger="cli",
        auto_approve_low_risk=confirm,
    )

    if output_format == "json":
        typer.echo(execution.model_dump_json(indent=2))
        return

    _print_workflow_execution(execution)


@workflow_app.command("show")
def workflow_show(
    execution_id: str = typer.Argument(..., help="工作流执行 ID"),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看工作流执行详情。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    execution = store.get_workflow_execution(execution_id)
    if execution is None:
        console.print(f"[red]执行记录不存在：[/red]{execution_id}")
        raise typer.Exit(code=1)

    if output_format == "json":
        typer.echo(execution.model_dump_json(indent=2))
        return

    _print_workflow_execution(execution)


@workflow_app.command("history")
def workflow_history(
    workflow_name: str | None = typer.Option(
        None, "--name", "-n", help="按工作流名称筛选"
    ),
    status: str | None = typer.Option(
        None, "--status", "-s", help="按状态筛选"
    ),
    limit: int = typer.Option(20, "--limit", help="最多返回条数"),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="输出格式：table | json"
    ),
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="配置文件路径。"),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """查看工作流执行历史。"""
    try:
        _, store = _load_config_and_store(config)
    except ConfigError as exc:
        console.print(f"[red]读取配置失败：[/red]{exc}")
        raise typer.Exit(code=1) from exc

    executions = store.list_workflow_executions(
        limit=limit,
        workflow_name=workflow_name,
        status=status,
    )

    if output_format == "json":
        import json

        typer.echo(
            json.dumps(
                [e.model_dump(mode="json") for e in executions],
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if not executions:
        typer.echo("没有工作流执行记录。")
        return

    typer.echo(f"共 {len(executions)} 条执行记录：\n")
    typer.echo(
        f"{'ID':<20} {'工作流':<25} {'状态':<10} {'触发':<8} {'开始时间':<25} {'摘要'}"
    )
    typer.echo("-" * 120)
    for e in executions:
        typer.echo(
            f"{e.id:<20} {e.workflow_name:<25} {e.status.value:<10} "
            f"{e.trigger:<8} {e.started_at.isoformat():<25} "
            f"{e.result_summary or '-'}"
        )


def _print_workflow_execution(execution) -> None:
    """格式化输出工作流执行结果。"""
    status_colors = {
        "success": "green",
        "failed": "red",
        "running": "yellow",
        "paused": "cyan",
        "cancelled": "dim",
        "pending": "dim",
    }
    color = status_colors.get(execution.status.value, "white")

    typer.echo("=" * 70)
    typer.echo(f"工作流执行：{execution.id}")
    typer.echo(f"  名称：{execution.workflow_name}")
    typer.echo(f"  状态：{execution.status.value}")
    typer.echo(f"  触发：{execution.trigger}")
    typer.echo(f"  开始：{execution.started_at.isoformat()}")
    if execution.ended_at:
        typer.echo(f"  结束：{execution.ended_at.isoformat()}")
    typer.echo()

    typer.echo("── 执行步骤 ──")
    for step in execution.steps:
        step_color = status_colors.get(step.status.value, "white")
        icon = {
            "success": "✓",
            "failed": "✗",
            "skipped": "⊘",
            "awaiting_approval": "⏸",
            "rejected": "✗",
            "pending": "○",
            "running": "→",
            "approved": "✓",
        }.get(step.status.value, "?")

        typer.echo(
            f"  {icon} {step.step_id:<25} {step.action:<25} "
            f"[{step.status.value}] ({step.risk_level.value})"
        )

        if step.error:
            typer.echo(f"      错误：{step.error}")

        if step.result:
            for k, v in step.result.items():
                if k != "task_id":
                    typer.echo(f"      {k}: {v}")

    if execution.result_summary:
        typer.echo(f"\n  摘要：{execution.result_summary}")

    typer.echo("\n" + "=" * 70)

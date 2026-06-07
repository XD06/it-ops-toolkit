from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    create_default_config_file,
    load_config,
)
from .storage import SQLiteStore, TaskRecordNotFound
from .tasks import get_task, list_tasks

console = Console()

app = typer.Typer(
    name="ops",
    help="中小企业 IT 运维工具箱。",
    no_args_is_help=True,
    invoke_without_command=True,
)
config_app = typer.Typer(help="配置管理。")
task_app = typer.Typer(help="任务记录。")
app.add_typer(config_app, name="config")
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


def _store_from_config(config_path: Path) -> SQLiteStore:
    loaded = load_config(config_path)
    storage_path = loaded.storage.path
    if not storage_path.is_absolute():
        storage_path = config_path.resolve().parent / storage_path
    return SQLiteStore(storage_path.resolve())

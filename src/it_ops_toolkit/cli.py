from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from . import __version__
from .config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    create_default_config_file,
    load_config,
)

console = Console()

app = typer.Typer(
    name="ops",
    help="中小企业 IT 运维工具箱。",
    no_args_is_help=True,
    invoke_without_command=True,
)
config_app = typer.Typer(help="配置管理。")
app.add_typer(config_app, name="config")


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

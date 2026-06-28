#!/usr/env python
"""IT Ops Toolkit 打包脚本。

使用 PyInstaller 将 CLI 打包为单文件可执行程序。

用法：
    python build/build_exe.py           # 打包（默认含 Web 依赖）
    python build/build_exe.py --cli     # 仅 CLI（不含 Web 依赖）
    python build/build_exe.py --clean   # 清理后重新打包

前置条件：
    pip install pyinstaller
    pip install -e ".[web]"  # 或 pip install -e ".[dev]"

输出：
    dist/ops.exe (Windows) 或 dist/ops (Linux/macOS)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = Path(__file__).resolve().parent / "it_ops_toolkit.spec"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build" / "pyinstaller"


def check_pyinstaller() -> bool:
    """检查 PyInstaller 是否已安装。"""
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


def run_build(cli_only: bool = False) -> int:
    """执行 PyInstaller 打包。"""
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
    ]

    if cli_only:
        # CLI-only 模式：排除 Web 相关模块
        cmd.append("--exclude-module=fastapi")
        cmd.append("--exclude-module=uvicorn")
        cmd.append("--exclude-module=starlette")

    print(f"[build] 运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def clean() -> None:
    """清理构建产物。"""
    for path in [DIST_DIR, BUILD_DIR]:
        if path.exists():
            print(f"[clean] 删除 {path}")
            shutil.rmtree(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="IT Ops Toolkit 打包脚本")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="仅打包 CLI（排除 Web 依赖，体积更小）",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="清理旧构建产物后重新打包",
    )
    args = parser.parse_args()

    if args.clean:
        clean()

    if not check_pyinstaller():
        print("[error] 未安装 PyInstaller。请执行：pip install pyinstaller")
        sys.exit(1)

    print(f"[build] 项目根目录: {PROJECT_ROOT}")
    print(f"[build] Spec 文件: {SPEC_FILE}")
    print(f"[build] 输出目录: {DIST_DIR}")
    print(f"[build] 模式: {'CLI-only' if args.cli else '完整（含 Web）'}")
    print()

    ret = run_build(cli_only=args.cli)
    if ret != 0:
        print(f"[error] 打包失败，退出码: {ret}")
        sys.exit(ret)

    exe_name = "ops.exe" if sys.platform == "win32" else "ops"
    exe_path = DIST_DIR / exe_name
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print()
        print(f"[success] 打包完成！")
        print(f"  可执行文件: {exe_path}")
        print(f"  文件大小: {size_mb:.1f} MB")
        print(f"  使用方法: {exe_path} --help")
    else:
        print(f"[warning] 可执行文件未找到: {exe_path}")


if __name__ == "__main__":
    main()

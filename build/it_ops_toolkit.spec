# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for IT Ops Toolkit.

用法：
    pyinstaller build/it_ops_toolkit.spec --noconfirm

或在项目根目录执行：
    python build/build_exe.py
"""

import sys
from pathlib import Path

block_cipher = None

# 项目根目录
project_root = Path(SPECPATH).parent
src_dir = project_root / "src"

# 需要收集的隐藏导入（PyInstaller 静态分析可能遗漏的动态导入）
hiddenimports = [
    # 运维工具箱内部模块（部分通过运行时 import 触发）
    "it_ops_toolkit.adapters",
    "it_ops_toolkit.ai_copilot",
    "it_ops_toolkit.agent_workflow",
    "it_ops_toolkit.alert_engine",
    "it_ops_toolkit.assets",
    "it_ops_toolkit.automation",
    "it_ops_toolkit.config",
    "it_ops_toolkit.diagnosis",
    "it_ops_toolkit.export",
    "it_ops_toolkit.health",
    "it_ops_toolkit.health_matrix",
    "it_ops_toolkit.health_matrix_http",
    "it_ops_toolkit.local_collect",
    "it_ops_toolkit.models",
    "it_ops_toolkit.notify",
    "it_ops_toolkit.probes.arp",
    "it_ops_toolkit.probes.dns",
    "it_ops_toolkit.probes.http",
    "it_ops_toolkit.probes.ping",
    "it_ops_toolkit.probes.tcp",
    "it_ops_toolkit.probes.tls_cert",
    "it_ops_toolkit.probes.traceroute",
    "it_ops_toolkit.reports",
    "it_ops_toolkit.scheduler",
    "it_ops_toolkit.security",
    "it_ops_toolkit.storage",
    "it_ops_toolkit.tasks",
    "it_ops_toolkit.topology",
    "it_ops_toolkit.web.app",
    "it_ops_toolkit.web.dashboard",
    # 第三方依赖
    "uvicorn.logging",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.loops.auto",
]

# 需要排除的大型不需要模块
excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "PyQt5",
    "PyQt6",
    "PySide6",
    "IPython",
    "jupyter",
    "notebook",
]

a = Analysis(
    [str(src_dir / "it_ops_toolkit" / "__main__.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[
        # 打包默认配置文件
        (str(project_root / "config.example.yaml"), "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ops",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

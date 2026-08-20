# -*- mode: python ; coding: utf-8 -*-
"""UU护航 双入口共享依赖 PyInstaller spec。

生成结构：
    dist/UU护航/
    ├─ UU护航.exe        (主程序，黑色 U)
    ├─ UU测算.exe        (轻量版，蓝色 U)
    └─ _internal/        (共享 Python/Qt/资源)
"""
from pathlib import Path

root = Path(SPECPATH)

# ── 主程序 Analysis ───────────────────────────────────────────
a = Analysis(
    [str(root / "src" / "profit_accounting_26" / "ui" / "app.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        # 配置
        (str(root / "config"), "config"),
        # 校准资源
        (str(root / "calibration" / "logistics_v2"), "calibration/logistics_v2"),
        (str(root / "calibration" / "runtime_safety_baseline"), "calibration/runtime_safety_baseline"),
        # UI forms（主程序）
        (str(root / "src" / "profit_accounting_26" / "ui" / "forms"), "profit_accounting_26/ui/forms"),
        # UI forms（商品采集）
        (str(root / "src" / "profit_accounting_26" / "product_collector" / "ui" / "forms"), "profit_accounting_26/product_collector/ui/forms"),
        # UI assets（图标、SVG、PNG）
        (str(root / "src" / "profit_accounting_26" / "ui" / "assets"), "src/profit_accounting_26/ui/assets"),
    ],
    hiddenimports=["PIL", "playwright", "profit_accounting_26.ui.quick_calculator_window"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# ── UU测算 Analysis（独立入口，共享依赖）──────────────────────
a_quick = Analysis(
    [str(root / "src" / "profit_accounting_26" / "ui" / "quick_calculator_app.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[],  # 共享主程序的 datas
    hiddenimports=["PIL"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# ── 共享 PYZ ──────────────────────────────────────────────────
pyz = PYZ(a.pure)

# ── UU护航 EXE（主程序，黑色 U）──────────────────────────────
exe_main = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UU护航",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "src" / "profit_accounting_26" / "ui" / "assets" / "uu_main_black.ico"),
)

# ── UU测算 EXE（轻量版，蓝色 U）──────────────────────────────
exe_quick = EXE(
    pyz,
    a_quick.scripts,
    [],
    exclude_binaries=True,
    name="UU测算",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "src" / "profit_accounting_26" / "ui" / "assets" / "uu_quick_blue.ico"),
)

# ── 共享 COLLECT ──────────────────────────────────────────────
coll = COLLECT(
    exe_main,
    exe_quick,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="UU护航",
)

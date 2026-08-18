# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "src" / "profit_accounting_26" / "ui" / "app.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (str(root / "config"), "config"),
        (str(root / "calibration" / "logistics_v2"), "calibration/logistics_v2"),
        (str(root / "calibration" / "runtime_safety_baseline"), "calibration/runtime_safety_baseline"),
        (str(root / "src" / "profit_accounting_26" / "ui" / "forms"), "src/profit_accounting_26/ui/forms"),
        (str(root / "src" / "profit_accounting_26" / "ui" / "assets"), "src/profit_accounting_26/ui/assets"),
    ],
    hiddenimports=["PIL"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProfitAccounting26",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ProfitAccounting26",
)

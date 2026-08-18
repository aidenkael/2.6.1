"""软件版本唯一来源与 PyInstaller spec 契约测试。

1. 确认 _version.py 是版本唯一来源（pyproject 通过 attr: 读取）。
2. 确认所有 Python 入口使用 _version.__version__ 而非硬编码。
3. 确认 ProfitAccounting26.spec 包含所有运行时必需资源。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_version_single_source_of_truth() -> None:
    """_version.py 是软件版本唯一来源，pyproject 通过 attr: 读取。"""
    from profit_accounting_26._version import __version__

    assert __version__, "版本号不能为空"
    assert re.match(r"^\d+\.\d+\.\d+", __version__), (
        f"版本号格式不合法: {__version__!r}"
    )

    # pyproject.toml 使用 dynamic version
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject, (
        "pyproject.toml 必须使用 dynamic version"
    )
    assert "profit_accounting_26._version.__version__" in pyproject, (
        "pyproject.toml 必须通过 attr: 读取 _version.__version__"
    )


def test_no_hardcoded_version_in_entry_points() -> None:
    """入口文件不应硬编码版本号，应从 _version 导入。"""
    entry_files = [
        ROOT / "src" / "profit_accounting_26" / "ui" / "app.py",
        ROOT / "src" / "profit_accounting_26" / "ui" / "bootstrap.py",
        ROOT / "src" / "profit_accounting_26" / "ui" / "quick_calculator_app.py",
    ]
    for path in entry_files:
        content = path.read_text(encoding="utf-8")
        assert "from profit_accounting_26._version import __version__" in content, (
            f"{path.relative_to(ROOT)} 必须从 _version 导入 __version__"
        )


def test_pyinstaller_spec_has_required_resources() -> None:
    """ProfitAccounting26.spec 必须包含运行时必需的非 Python 资源。"""
    spec_path = ROOT / "ProfitAccounting26.spec"
    assert spec_path.is_file(), "ProfitAccounting26.spec 不存在"
    content = spec_path.read_text(encoding="utf-8")

    required_resources = [
        "calibration/runtime_safety_baseline",
        "calibration/logistics_v2",
        "src/profit_accounting_26/ui/forms",
        "src/profit_accounting_26/ui/assets",
        "config",
    ]
    for resource in required_resources:
        assert resource in content, (
            f"ProfitAccounting26.spec 缺少运行时资源: {resource}"
        )

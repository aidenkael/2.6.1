"""UI 文件运行时加载器。

负责从 ``forms/`` 和 ``forms/pages/`` 目录加载 Qt Designer ``.ui`` 文件。
运行时直接使用仓库中的 ``.ui``，不生成也不维护 Python 布局副本。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtUiTools import QUiLoader


_FORMS_DIR = Path(__file__).resolve().parent / "forms"
_PAGES_DIR = _FORMS_DIR / "pages"


def forms_dir() -> Path:
    """返回 ``forms/`` 目录的绝对路径。"""
    return _FORMS_DIR


def pages_dir() -> Path:
    """返回 ``forms/pages/`` 模块化页面目录的绝对路径。"""
    return _PAGES_DIR


def load_ui(file_name: str, parent=None):
    """加载 ``forms/<file_name>`` 并返回顶层 widget。

    使用 ``QUiLoader`` 在运行时直接加载 ``.ui`` XML，不依赖 ``pyside6-uic`` 预编译。
    """
    ui_path = _FORMS_DIR / file_name
    return _load_ui_path(ui_path, parent)


def load_page_module(page_name: str, parent=None):
    """加载 ``forms/pages/<page_name>`` 模块化页面 UI 并返回顶层 widget。"""
    ui_path = _PAGES_DIR / page_name
    if not ui_path.exists():
        # 回退到 forms/
        ui_path = _FORMS_DIR / page_name
    return _load_ui_path(ui_path, parent)


def _load_ui_path(ui_path: Path, parent=None):
    """从指定路径加载 .ui 文件。"""
    if not ui_path.exists():
        raise FileNotFoundError(f"UI 文件不存在：{ui_path}")

    loader = QUiLoader()
    file_obj = QFile(str(ui_path))
    if not file_obj.open(QIODevice.OpenModeFlag.ReadOnly):
        raise IOError(f"无法打开 UI 文件：{ui_path}")
    try:
        widget = loader.load(file_obj, parent)
    finally:
        file_obj.close()

    if widget is None:
        raise RuntimeError(f"UI 文件加载失败（返回 None）：{ui_path}")
    return widget


def load_main_window(parent=None):
    """加载主窗口 ``main_window.ui``。"""
    return load_ui("main_window.ui", parent)


def load_settings_page(parent=None):
    """加载设置页（兼容旧路径，指向 forms/pages/）。"""
    return load_page_module("settings_page.ui", parent)

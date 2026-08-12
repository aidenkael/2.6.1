"""薄 UI 加载器 —— 只负责加载 Qt Designer .ui 文件。

不引入 AppContext / Binder / theme 等主软件架构。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget

_UI_DIR = Path(__file__).resolve().parent
_UI_FILE = _UI_DIR / "forms" / "product_collection.ui"


def load_ui(parent: QWidget | None = None) -> QWidget:
    """加载 product_collection.ui 并返回顶层 QWidget。"""
    loader = QUiLoader()
    widget = loader.load(str(_UI_FILE), parent)
    if widget is None:
        raise RuntimeError(f"无法加载 UI 文件: {_UI_FILE}")
    return widget

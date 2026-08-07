"""图片框 Controller —— 第一阶段 Controller 拆分。

只负责图片框管理：重建、数量增减、保存配置、删除、指纹与剪贴板粘贴。
从 ``CalculationPage`` 原样迁移以下方法（逻辑零改动）：
``rebuild_image_slots`` / ``change_slot_count`` / ``save_image_config`` /
``remove_image`` / ``image_fingerprint`` / ``paste_from_clipboard`` /
``_slot_under_cursor``。

边界约定：
- 继续绑定稳定 ``main_window.ui`` 中的原有 objectName
  （btnDecreaseImageSlots / btnIncreaseImageSlots / btnSaveImageLayout /
  lblImageSlotCount / imageSlotsLayout）；
- 不创建新的页面布局结构、不修改 .ui；负责现有 imageSlotsLayout 内
  动态 ImageSlotWidget 的创建与生命周期管理；
- 不含业务公式，不创建 Service；
- **不接管 AI/Recognition 状态**：图片框内容变化通过注入的
  ``image_changed_callback`` 通知页面，AI 按钮文案、AI整体重估判断与
  识图线程状态仍留在 ``CalculationPage._image_changed``；
- ``settings_provider`` 由页面注入，每次调用必须返回 ``CalculationPage``
  当前的 ``self.settings``（``refresh_settings`` 会用新 dict 整体替换
  ``self.settings``，因此禁止持有固定 dict 引用），也禁止在此
  ``settings_service.load()`` 创建第二份缓存。
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from profit_accounting_26.domain.models import ImageType
from profit_accounting_26.ui.widgets import ImageSlotWidget


class ImageSlotsController:
    """图片框管理 Controller（不创建布局结构，管理动态 ImageSlotWidget，不接管 AI 状态）。"""

    def __init__(
        self,
        root: QWidget,
        parent: QWidget,
        settings_service: Any,
        settings_provider: Callable[[], dict[str, Any]],
        image_changed_callback: Callable[[], None],
        mark_dirty_callback: Callable[[], None],
    ) -> None:
        self._parent = parent
        self._settings_service = settings_service
        self._settings_provider = settings_provider
        self._image_changed_callback = image_changed_callback
        self._mark_dirty_callback = mark_dirty_callback
        self.image_slots: list[ImageSlotWidget] = []

        f = root.findChild
        btn_decrease = f(QPushButton, "btnDecreaseImageSlots")
        self._slot_count_label = f(QLabel, "lblImageSlotCount")
        btn_increase = f(QPushButton, "btnIncreaseImageSlots")
        btn_save_layout = f(QPushButton, "btnSaveImageLayout")
        self._slots_layout = f(QHBoxLayout, "imageSlotsLayout")

        btn_decrease.clicked.connect(lambda: self.change_slot_count(-1))
        btn_increase.clicked.connect(lambda: self.change_slot_count(1))
        btn_save_layout.clicked.connect(self.save_image_config)

    # ------------------------------------------------------------------
    # 图片框
    # ------------------------------------------------------------------

    def rebuild_image_slots(self, count: int) -> None:
        while self._slots_layout.count():
            item = self._slots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        existing = [(slot.path, slot.image_type()) for slot in self.image_slots]
        self.image_slots = []
        for index in range(count):
            slot = ImageSlotWidget(index, ImageType.MAIN)
            slot.changed.connect(self._image_changed_callback)
            slot.removeRequested.connect(self.remove_image)
            if index < len(existing) and existing[index][0] is not None:
                slot.load_path(existing[index][0])
                slot.set_image_type(existing[index][1])
            self.image_slots.append(slot)
            self._slots_layout.addWidget(slot)
        self._slot_count_label.setText(str(count))

    def change_slot_count(self, delta: int) -> None:
        new_count = len(self.image_slots) + delta
        if not 3 <= new_count <= 6:
            return
        if delta < 0 and self.image_slots[-1].path is not None:
            QMessageBox.information(self._parent, "无法减少", "请先删除最后一个图片框中的图片。")
            return
        self.rebuild_image_slots(new_count)
        self._mark_dirty_callback()

    def save_image_config(self) -> None:
        settings = self._settings_provider()
        settings["image_slot_count"] = len(self.image_slots)
        settings.pop("image_slot_types", None)
        self._settings_service.save(settings)
        QMessageBox.information(self._parent, "已保存", "图片框数量、顺序和默认类型已保存。")

    def remove_image(self, index: int) -> None:
        if 0 <= index < len(self.image_slots):
            self.image_slots[index].clear_image()

    def image_fingerprint(self) -> tuple[tuple[str, str], ...]:
        result: list[tuple[str, str]] = []
        for slot in self.image_slots:
            if slot.path and slot.path.is_file():
                try:
                    digest = hashlib.sha256(slot.path.read_bytes()).hexdigest()
                except OSError:
                    digest = "unreadable"
                result.append((slot.image_type().value, digest))
        return tuple(result)

    def paste_from_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        target = self._slot_under_cursor()
        if target is None:
            return False
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    target.load_path(Path(url.toLocalFile()))
                    return True
        image = clipboard.image()
        if not image.isNull():
            array = QByteArray()
            buffer = QBuffer(array)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            data = bytes(array)
            digest = hashlib.sha256(data).hexdigest()
            temp_dir = Path(tempfile.gettempdir()) / "profit_accounting_26_clipboard"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp = temp_dir / f"clipboard_{digest[:20]}.png"
            if not temp.exists():
                temp.write_bytes(data)
            target.load_path(temp)
            return True
        return False

    def _slot_under_cursor(self) -> ImageSlotWidget | None:
        widget = QApplication.widgetAt(QCursor.pos())
        while widget is not None:
            if isinstance(widget, ImageSlotWidget) and widget in self.image_slots:
                return widget
            widget = widget.parentWidget()
        return None

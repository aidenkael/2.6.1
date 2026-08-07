"""ImageSlotsController 单测（第一阶段 Controller 拆分）。

覆盖：
1. 初始数量；
2. 3–6 数量边界；
3. 最后一个图片框有图时禁止减少；
4. rebuild 后已有图片路径保留；
5. remove_image；
6. image_fingerprint 稳定；
7. save_image_config 写入与页面同一个 settings 对象；
8. 剪贴板无目标时返回 False。

约束：qapp 由 tests/conftest.py 的会话级 fixture 提供，禁止在本文件内
创建 QApplication。
"""

from __future__ import annotations

import hashlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from profit_accounting_26.application import AppContext
from profit_accounting_26.domain.models import ImageType


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    from profit_accounting_26.ui.pages import CalculationPage

    p = CalculationPage(temp_context)
    yield p
    p.deleteLater()
    qapp.processEvents()


def _write_png(tmp_path, name="slot.png") -> "object":
    """写一张真实可读的小 PNG（load_path 对不可读图片会拒绝）。"""
    img_path = tmp_path / name
    QImage(8, 8, QImage.Format_ARGB32).save(str(img_path), "PNG")
    assert img_path.is_file()
    return img_path


def _silence_info(monkeypatch):
    """屏蔽模态提示框，并记录调用次数。"""
    calls = []

    def _fake_information(*args, **kwargs):
        calls.append(args)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", _fake_information)
    return calls


# 1. 初始数量来自 defaults.json 的 image_slot_count（5）
def test_initial_slot_count(page):
    assert len(page.image_slots) == 5
    # page.image_slots 表面保持兼容，且与 Controller 持有同一列表对象
    assert page.image_slots is page.image_slots_controller.image_slots


# 2. 3–6 数量边界
def test_slot_count_bounds(page, monkeypatch):
    _silence_info(monkeypatch)
    # 上界：5 → 6 允许，6 → 7 保持 6
    page.change_slot_count(1)
    assert len(page.image_slots) == 6
    page.change_slot_count(1)
    assert len(page.image_slots) == 6
    # 下界：6 → 3 允许，3 → 2 保持 3
    for _ in range(3):
        page.change_slot_count(-1)
    assert len(page.image_slots) == 3
    page.change_slot_count(-1)
    assert len(page.image_slots) == 3


# 3. 最后一个图片框有图时禁止减少
def test_decrease_blocked_when_last_slot_has_image(page, tmp_path, monkeypatch):
    calls = _silence_info(monkeypatch)
    page.image_slots[-1].load_path(_write_png(tmp_path))
    assert page.image_slots[-1].path is not None

    page.change_slot_count(-1)

    assert len(page.image_slots) == 5  # 数量未变
    assert page.image_slots[-1].path is not None  # 图片仍在
    assert calls  # 弹出了“无法减少”提示


# 4. rebuild 后已有图片路径保留
def test_rebuild_keeps_existing_paths(page, tmp_path):
    img_path = _write_png(tmp_path)
    page.image_slots[0].load_path(img_path)
    assert page.image_slots[0].path == img_path

    page.rebuild_image_slots(6)
    assert len(page.image_slots) == 6
    assert page.image_slots[0].path == img_path

    page.rebuild_image_slots(3)
    assert len(page.image_slots) == 3
    assert page.image_slots[0].path == img_path


# 5. remove_image
def test_remove_image(page, tmp_path):
    page.image_slots[1].load_path(_write_png(tmp_path))
    assert page.image_slots[1].path is not None

    page.remove_image(1)
    assert page.image_slots[1].path is None
    # 越界索引静默忽略，不抛异常
    page.remove_image(99)
    page.remove_image(-1)


# 6. image_fingerprint 稳定（含页面旧调用表面 _image_fingerprint 兼容）
def test_image_fingerprint_stable(page, tmp_path):
    empty = page._image_fingerprint()
    assert empty == ()
    assert empty == page.image_slots_controller.image_fingerprint()

    img_path = _write_png(tmp_path)
    page.image_slots[2].load_path(img_path)
    digest = hashlib.sha256(img_path.read_bytes()).hexdigest()
    expected = ((ImageType.MAIN.value, digest),)

    assert page._image_fingerprint() == expected
    assert page._image_fingerprint() == expected  # 重复调用结果一致
    assert page._image_fingerprint() == page.image_slots_controller.image_fingerprint()


# 7. 保存数量写入与页面同一个 settings 对象（禁止第二份缓存）
def test_save_image_config_writes_same_settings_object(page, monkeypatch):
    _silence_info(monkeypatch)
    settings_obj = page.settings
    assert page.image_slots_controller.settings is settings_obj

    page.change_slot_count(1)  # 5 → 6
    page.save_image_config()

    assert settings_obj["image_slot_count"] == 6
    assert "image_slot_types" not in settings_obj
    # 持久化后重新加载仍是 6（经由同一个被保存的 dict）
    assert page.context.settings_service.load()["image_slot_count"] == 6


# 8. 剪贴板无目标（光标下无图片框）时返回 False
def test_paste_without_target_returns_false(qapp, page):
    clipboard = qapp.clipboard()
    clipboard.clear()
    clipboard.setText("not-an-image")
    assert page.paste_from_clipboard() is False
    clipboard.clear()

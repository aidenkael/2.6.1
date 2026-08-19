"""UU护航 / UU测算 单实例 targeted tests（任务书十三、十四节）。

覆盖（源码阶段，同一 QApplication 内模拟多实例启动）：
A. 同一 key 连续创建 10 个守卫 → 只有第一个为唯一实例，其余 already_running=True；
B. UU测算 key 连续创建 10 个 → 同理；
C. UU护航 + UU测算 两个不同 key 的实例可同时并存（各自 listen 成功）；
D. 关闭 UU护航 守卫后重新创建 → 正常获得唯一实例；
E. 关闭 UU测算 守卫后重新创建 → 正常获得唯一实例；
- 无死锁 / 无残留锁（close 后可立即重新 listen 成功）。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.ui.single_instance import (  # noqa: E402
    UU_CALCULATOR_INSTANCE_KEY,
    UU_ESCORT_INSTANCE_KEY,
    SingleInstanceGuard,
)


class TestSingleInstanceEscort:
    def test_ten_consecutive_starts_only_one_instance(self, qapp):
        """A：连续启动 UU护航 10 次 → 只能存在一个实例。"""
        first = SingleInstanceGuard(UU_ESCORT_INSTANCE_KEY, parent=qapp)
        try:
            assert first.already_running is False
            for _ in range(9):
                extra = SingleInstanceGuard(UU_ESCORT_INSTANCE_KEY, parent=qapp)
                try:
                    assert extra.already_running is True, "重复启动必须识别为已有实例"
                finally:
                    extra.close()
        finally:
            first.close()

    def test_reopen_after_close(self, qapp):
        """D：关闭 UU护航 以后重新打开正常。"""
        first = SingleInstanceGuard(UU_ESCORT_INSTANCE_KEY, parent=qapp)
        assert first.already_running is False
        first.close()
        second = SingleInstanceGuard(UU_ESCORT_INSTANCE_KEY, parent=qapp)
        try:
            assert second.already_running is False, "关闭后重新启动应获得唯一实例"
        finally:
            second.close()


class TestSingleInstanceCalculator:
    def test_ten_consecutive_starts_only_one_instance(self, qapp):
        """B：连续启动 UU测算 10 次 → 只能存在一个实例。"""
        first = SingleInstanceGuard(UU_CALCULATOR_INSTANCE_KEY, parent=qapp)
        try:
            assert first.already_running is False
            for _ in range(9):
                extra = SingleInstanceGuard(UU_CALCULATOR_INSTANCE_KEY, parent=qapp)
                try:
                    assert extra.already_running is True
                finally:
                    extra.close()
        finally:
            first.close()

    def test_reopen_after_close(self, qapp):
        """E：关闭 UU测算 以后重新打开正常。"""
        first = SingleInstanceGuard(UU_CALCULATOR_INSTANCE_KEY, parent=qapp)
        assert first.already_running is False
        first.close()
        second = SingleInstanceGuard(UU_CALCULATOR_INSTANCE_KEY, parent=qapp)
        try:
            assert second.already_running is False
        finally:
            second.close()


class TestSingleInstanceCoexist:
    def test_escort_and_calculator_can_run_together(self, qapp):
        """C：UU护航 + UU测算 两个 key 同时各运行一个。"""
        escort = SingleInstanceGuard(UU_ESCORT_INSTANCE_KEY, parent=qapp)
        calculator = SingleInstanceGuard(UU_CALCULATOR_INSTANCE_KEY, parent=qapp)
        try:
            assert escort.already_running is False
            assert calculator.already_running is False
        finally:
            escort.close()
            calculator.close()

    def test_keys_are_distinct(self):
        assert UU_ESCORT_INSTANCE_KEY != UU_CALCULATOR_INSTANCE_KEY

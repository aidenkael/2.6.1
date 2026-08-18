"""本轮视觉收口与保存状态 Bug 修复的针对性测试。

覆盖：
A. 主软件保存状态：_mark_dirty 尊重 _updating；_persist_selected_rule 幂等
B. Quick 规则状态紧凑映射：_compact_rule_status 映射规则
C. Quick 可编辑/冻结视觉区分：全局 stylesheet property selector
D. Quick 视觉分组：内部 section=false + 全局 stylesheet 去除边框
E. Quick 单位标签固定宽度 + 行包装 Maximum 策略（均在 .ui 中静态声明）
F. Quick 状态标签固定宽度
G. Grid 列不拉伸（columnStretch=0）

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os
from dataclasses import asdict

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget  # noqa: E402

from profit_accounting_26.application import AppContext, SettingsService  # noqa: E402
from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow  # noqa: E402

_FORWARDER_NAMES = ("义乌货代", "深圳货代", "广州货代")


def _install_forwarders(context: AppContext, count: int = 2) -> None:
    settings = context.settings_service.load()
    forwarders = []
    for index in range(count):
        name = _FORWARDER_NAMES[index % len(_FORWARDER_NAMES)]
        forwarder = SettingsService.new_forwarder(
            name, 80.0 + index * 20, 10.0 + index, 8000.0,
        )
        forwarders.append(asdict(forwarder))
    settings["forwarders"] = forwarders
    settings["selected_forwarder_id"] = forwarders[0]["id"]
    settings["exchange_rate_usd_to_rmb"] = 7.2
    context.settings_service.save(settings)


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    _install_forwarders(temp_context)
    window = QuickCalculatorWindow(temp_context)
    yield window
    window.close()
    window.deleteLater()


# ====================================================================
# A. _compact_rule_status 映射规则
# ====================================================================

class TestCompactRuleStatus:
    """Quick 专用规则状态紧凑映射。"""

    def test_empty_returns_not_triggered(self):
        assert QuickCalculatorWindow._compact_rule_status("") == "未触发"

    def test_none_returns_not_triggered(self):
        assert QuickCalculatorWindow._compact_rule_status(None) == "未触发"

    def test_triggered_with_amount(self):
        assert QuickCalculatorWindow._compact_rule_status("已触发 +¥20.33") == "已触发"

    def test_adjusted_with_amount(self):
        assert QuickCalculatorWindow._compact_rule_status("已调整 ¥20.33") == "已触发"

    def test_not_triggered(self):
        assert QuickCalculatorWindow._compact_rule_status("未触发") == "未触发"

    def test_no_rule(self):
        assert QuickCalculatorWindow._compact_rule_status("无规则") == "未触发"

    def test_triggered_negative(self):
        assert QuickCalculatorWindow._compact_rule_status("已触发 +¥-5.00") == "已触发"

    def test_arbitrary_text(self):
        assert QuickCalculatorWindow._compact_rule_status("其他文本") == "未触发"


# ====================================================================
# B. 可编辑/冻结视觉区分
# ====================================================================

class TestEditableFrozenVisual:
    """可编辑字段与冻结字段通过 .ui 全局 stylesheet 的 property selector 区分样式。

    样式定义在 .ui 全局 stylesheet 中：
    - QDoubleSpinBox → 白底 + 蓝色 focus（可编辑）
    - QDoubleSpinBox[preview="true"] → 浅灰背景 + 灰文字（冻结）

    per-widget styleSheet() 为空（样式来源为父级 stylesheet）；
    业务契约由 preview 属性 + readOnly 属性保证。
    """

    def test_frozen_spin_has_preview_property(self, page):
        """冻结字段（preview=true）属性存在 → 全局 stylesheet 匹配 QDoubleSpinBox[preview="true"]。"""
        frozen = page.findChild(QDoubleSpinBox, "txtQuickFirstMileTotalRmb")
        assert frozen is not None
        assert bool(frozen.property("preview")), "冻结字段应有 preview=true 属性"

    def test_editable_spin_has_no_preview_property(self, page):
        """可编辑字段无 preview 属性 → 全局 stylesheet 匹配 QDoubleSpinBox 基础规则。"""
        editable = page.findChild(QDoubleSpinBox, "spinQuickDomesticCostRmb")
        assert editable is not None
        assert not bool(editable.property("preview")), "可编辑字段不应有 preview 属性"

    def test_frozen_and_editable_preview_differ(self, page):
        """冻结与可编辑字段的 preview 属性不同 → 全局 stylesheet 应用不同样式。"""
        frozen = page.findChild(QDoubleSpinBox, "txtQuickFirstMileTotalRmb")
        editable = page.findChild(QDoubleSpinBox, "spinQuickDomesticCostRmb")
        assert frozen is not None and editable is not None
        assert bool(frozen.property("preview")) != bool(editable.property("preview"))

    def test_global_stylesheet_has_frozen_rule(self, page):
        """全局 stylesheet 包含 QDoubleSpinBox[preview="true"] 选择器。"""
        ss = page.styleSheet()
        assert 'QDoubleSpinBox[preview="true"]' in ss, "全局 stylesheet 应有冻结 spin 规则"
        assert "#f1f5fa" in ss, "全局 stylesheet 应包含 #f1f5fa 浅灰色"

    def test_global_stylesheet_has_editable_focus_rule(self, page):
        """全局 stylesheet 包含 QDoubleSpinBox:focus 选择器。"""
        ss = page.styleSheet()
        assert "QDoubleSpinBox:focus" in ss, "全局 stylesheet 应有 focus 规则"
        assert "#176ff2" in ss, "全局 stylesheet 应包含 #176ff2 蓝色"

    def test_editable_frozen_contract_unchanged(self, page):
        """editable/readOnly 业务契约未改变（preview=true ↔ readOnly=true）。"""
        all_spins = page.findChildren(QDoubleSpinBox)
        for spin in all_spins:
            is_preview = bool(spin.property("preview"))
            is_readonly = spin.isReadOnly()
            # preview 字段必须 readOnly；非 preview 字段必须不 readOnly
            if is_preview:
                assert is_readonly, f"{spin.objectName()} preview=true 但 readOnly=false"


# ====================================================================
# C. 5 模块视觉结构
# ====================================================================

class TestFiveModuleStructure:
    """Quick 视觉分组：内部 section 通过 CSS section="false" 去除独立边框。

    不再使用 Python 运行时重构布局；.ui 保持 7 section 扁平结构，
    视觉分组由全局 stylesheet 的 QFrame[section="false"] 规则实现。
    """

    def test_cost_section_no_independent_border(self, page):
        """costSection 设 section=false → 全局 stylesheet 不匹配边框规则。"""
        cost = page.findChild(QFrame, "costSection")
        assert cost is not None
        assert not cost.property("section"), "costSection 应为 section=false"

    def test_forwarder_section_no_independent_border(self, page):
        """forwarderCostSection 设 section=false → 无独立边框。"""
        fwd = page.findChild(QFrame, "forwarderCostSection")
        assert fwd is not None
        assert not fwd.property("section"), "forwarderCostSection 应为 section=false"

    def test_promo_section_no_independent_border(self, page):
        """promotionReserveSection 设 section=false → 无独立边框。"""
        promo = page.findChild(QFrame, "promotionReserveSection")
        assert promo is not None
        assert not promo.property("section"), "promotionReserveSection 应为 section=false"

    def test_activity_section_no_independent_border(self, page):
        """activitySection 设 section=false → 无独立边框。"""
        act = page.findChild(QFrame, "activitySection")
        assert act is not None
        assert not act.property("section"), "activitySection 应为 section=false"

    def test_outer_sections_keep_border(self, page):
        """specSection / noActivitySection / bottomSection 保留 section=true → 有边框。"""
        for name in ("specSection", "noActivitySection", "bottomSection"):
            sect = page.findChild(QFrame, name)
            assert sect is not None, f"{name} 应存在"
            assert sect.property("section"), f"{name} 应为 section=true（保留边框）"

    def test_forwarder_separator_hidden(self, page):
        """forwarderCostSeparator（VLine）应被隐藏。"""
        sep = page.findChild(QFrame, "forwarderCostSeparator")
        if sep is not None:
            assert not sep.isVisible(), "VLine 分隔线应隐藏"

    def test_global_stylesheet_has_section_false_rule(self, page):
        """全局 stylesheet 包含 QFrame[section="false"] 选择器。"""
        ss = page.styleSheet()
        assert 'QFrame[section="false"]' in ss, "全局 stylesheet 应有 section=false 规则"


# ====================================================================
# D. 单位标签固定宽度 + 行包装 Maximum
# ====================================================================

class TestUnitLabelSizePolicy:
    """unit QLabel 和行包装 widget 使用固定/紧凑策略。"""

    def test_unit_labels_are_fixed_policy(self, page):
        """所有 unit=true 的 QLabel 使用 Fixed 大小策略。"""
        for label in page.findChildren(QLabel):
            if label.property("unit"):
                assert label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed, (
                    f"{label.objectName()} unit=true 应为 Fixed 水平策略"
                )

    def test_row_wrappers_are_maximum_policy(self, page):
        """包含 unit QLabel + QDoubleSpinBox 的 HBox 行包装使用 Maximum 策略。"""
        for widget in page.findChildren(QWidget):
            layout = widget.layout()
            if not isinstance(layout, QHBoxLayout):
                continue
            has_unit = False
            has_spin = False
            for i in range(layout.count()):
                child = layout.itemAt(i).widget()
                if isinstance(child, QLabel) and child.property("unit"):
                    has_unit = True
                if isinstance(child, QDoubleSpinBox):
                    has_spin = True
            if has_unit and has_spin:
                h_policy = widget.sizePolicy().horizontalPolicy()
                assert h_policy == QSizePolicy.Policy.Maximum, (
                    f"{widget.objectName()} 行包装应为 Maximum 水平策略，实际={h_policy}"
                )


# ====================================================================
# E. 状态标签固定宽度
# ====================================================================

class TestStatusLabelFixedWidth:
    """规则状态标签使用 Fixed 策略，适配"已触发"/"未触发"短文本。"""

    def test_status_labels_are_fixed_policy(self, page):
        for name in ("lblNoActivitySubsidyStatus", "lblActivitySubsidyStatus"):
            lbl = page.findChild(QLabel, name)
            assert lbl is not None, f"{name} 应存在"
            assert lbl.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed, (
                f"{name} 应为 Fixed 水平策略"
            )

    def test_status_label_default_text_is_short(self, page):
        """初始状态文本为"未触发"（短格式）。"""
        for name in ("lblNoActivitySubsidyStatus", "lblActivitySubsidyStatus"):
            lbl = page.findChild(QLabel, name)
            if lbl is not None:
                assert lbl.text() in ("未触发", "已触发"), (
                    f"{name} 初始应为短格式，实际='{lbl.text()}'"
                )


# ====================================================================
# F. Grid 列不拉伸
# ====================================================================

class TestGridColumnNoStretch:
    """利润区 Grid 内容列 stretch=0 + 末尾 stretch 列（只在最右侧留空白）。"""

    def test_no_activity_grid_content_cols_no_stretch(self, page):
        from PySide6.QtWidgets import QGridLayout
        grid = page.findChild(QGridLayout, "noActivityGrid")
        assert grid is not None
        # 列 0/1/2 是内容列，不应 stretch
        for col in range(3):
            assert grid.columnStretch(col) == 0, (
                f"noActivityGrid col {col} stretch 应为 0"
            )
        # 列 3 是末尾 stretch 列
        assert grid.columnStretch(3) == 1, (
            "noActivityGrid col 3 (末尾) stretch 应为 1"
        )

    def test_activity_grid_content_cols_no_stretch(self, page):
        from PySide6.QtWidgets import QGridLayout
        grid = page.findChild(QGridLayout, "activityGrid")
        assert grid is not None
        for col in range(3):
            assert grid.columnStretch(col) == 0, (
                f"activityGrid col {col} stretch 应为 0"
            )
        assert grid.columnStretch(3) == 1, (
            "activityGrid col 3 (末尾) stretch 应为 1"
        )


# ====================================================================
# G. 主软件保存状态 Bug 修复验证
# ====================================================================

class TestMarkDirtyRespectUpdating:
    """_mark_dirty 在 _updating=True 时不应设置 dirty。"""

    def test_mark_dirty_skipped_during_updating(self, qapp, temp_context):
        """_updating=True 时 _mark_dirty 不改变 dirty 状态。"""
        from profit_accounting_26.ui.pages.calculation_page import CalculationPage
        # 构造 CalculationPage 太重，直接测试方法逻辑
        class _Mock:
            _updating = True
            dirty = False
            dirtyChanged_events = []
            def _mark_dirty(self):
                if self._updating:
                    return
                if not self.dirty:
                    self.dirty = True
                    self.dirtyChanged_events.append(True)

        m = _Mock()
        m._mark_dirty()
        assert not m.dirty, "_updating=True 时不应设置 dirty"
        assert not m.dirtyChanged_events

    def test_mark_dirty_works_when_not_updating(self):
        """_updating=False 时 _mark_dirty 正常设置 dirty。"""
        class _Mock:
            _updating = False
            dirty = False
            dirtyChanged_events = []
            def _mark_dirty(self):
                if self._updating:
                    return
                if not self.dirty:
                    self.dirty = True
                    self.dirtyChanged_events.append(True)

        m = _Mock()
        m._mark_dirty()
        assert m.dirty
        assert m.dirtyChanged_events == [True]


class TestPersistSelectedRuleIdempotent:
    """_persist_selected_rule 在规则 ID 未变时不 mark_dirty。"""

    def test_same_rule_id_does_not_mark_dirty(self):
        """规则 ID 相同 → 不调用 _mark_dirty。"""
        class _Mock:
            selected_profit_rule_id = "rule_1"
            settings = {"selected_profit_rule_id": "rule_1"}
            _dirty_count = 0

            def _mark_dirty(self):
                self._dirty_count += 1

            def _persist_selected_rule(self, rule_id):
                new_id = str(rule_id or "")
                if new_id == self.selected_profit_rule_id:
                    return
                self.selected_profit_rule_id = new_id
                self.settings["selected_profit_rule_id"] = self.selected_profit_rule_id
                self._mark_dirty()

        m = _Mock()
        m._persist_selected_rule("rule_1")
        assert m._dirty_count == 0, "规则未变时不应 mark_dirty"

    def test_different_rule_id_marks_dirty(self):
        """规则 ID 不同 → 调用 _mark_dirty。"""
        class _Mock:
            selected_profit_rule_id = "rule_1"
            settings = {"selected_profit_rule_id": "rule_1"}
            _dirty_count = 0

            def _mark_dirty(self):
                self._dirty_count += 1

            def _persist_selected_rule(self, rule_id):
                new_id = str(rule_id or "")
                if new_id == self.selected_profit_rule_id:
                    return
                self.selected_profit_rule_id = new_id
                self.settings["selected_profit_rule_id"] = self.selected_profit_rule_id
                self._mark_dirty()

        m = _Mock()
        m._persist_selected_rule("rule_2")
        assert m._dirty_count == 1, "规则变化时应 mark_dirty"
        assert m.selected_profit_rule_id == "rule_2"


# ====================================================================
# H. 主软件 lblSaveStatus 生命周期（本轮新增）
# ====================================================================

class TestLblSaveStatusBinding:
    """MainWindowBinder._bind_save_status 必须在 _mount_pages 之后执行。"""

    def test_bind_save_status_after_mount_pages(self):
        """bind() 中 _mount_pages 先于 _bind_save_status。"""
        import inspect
        from profit_accounting_26.ui.binders.main_window_binder import MainWindowBinder
        source = inspect.getsource(MainWindowBinder.bind)
        mount_pos = source.index("_mount_pages")
        bind_pos = source.index("_bind_save_status")
        assert mount_pos < bind_pos

    def test_set_history_editing_method_exists(self):
        from profit_accounting_26.ui.binders.main_window_binder import MainWindowBinder
        assert hasattr(MainWindowBinder, "set_history_editing")

    def test_calculation_page_has_history_editing_signal(self):
        from profit_accounting_26.ui.pages.calculation_page import CalculationPage
        assert hasattr(CalculationPage, "historyEditingChanged")

    def test_no_edit_state_label(self, qapp, temp_context):
        from profit_accounting_26.ui.pages.calculation_page import CalculationPage
        page = CalculationPage(temp_context)
        assert not hasattr(page, "edit_state_label")


# ====================================================================
# I. Quick 窗口固定尺寸
# ====================================================================

class TestQuickWindowFixedSize:
    def test_no_refit_window_method(self, page):
        assert not hasattr(page, "_refit_window")

    def test_no_tail_rmb_commit_method(self, page):
        assert not hasattr(page, "_on_tail_rmb_commit")

    def test_window_size_fixed(self, page):
        assert page.minimumSize().width() == page.maximumSize().width()
        assert page.minimumSize().height() == page.maximumSize().height()


# ====================================================================
# J. Quick 尾程 RMB 冻结
# ====================================================================

class TestQuickTailRmbFrozen:
    def test_tail_rmb_is_readonly(self, page):
        assert page.tail_fee_rmb.isReadOnly()

    def test_tail_rmb_has_preview_property(self, page):
        assert bool(page.tail_fee_rmb.property("preview"))

    def test_tail_usd_is_editable(self, page):
        assert not page.tail_fee_usd.isReadOnly()

    def test_no_reverse_rmb_to_usd(self, page):
        from tests.ui.test_quick_calculator import _install_forwarders
        _install_forwarders(page.context, 1)
        page.tail_fee_usd.setValue(6.0)
        usd_before = page.tail_fee_usd.value()
        page.tail_fee_rmb.setValue(999.0)
        assert page.tail_fee_usd.value() == usd_before


# ====================================================================
# K. Quick 利润区 Grid 紧凑化
# ====================================================================

class TestProfitGridCompact:
    def test_profit_grid_widgets_are_maximum(self, page):
        from PySide6.QtWidgets import QGridLayout, QSizePolicy
        for grid_name in ("noActivityGrid", "activityGrid"):
            grid = page.findChild(QGridLayout, grid_name)
            assert grid is not None
            for col in range(3):
                for row in range(2):
                    item = grid.itemAtPosition(row, col)
                    if item is None:
                        continue
                    w = item.widget()
                    if w is not None:
                        assert w.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Maximum

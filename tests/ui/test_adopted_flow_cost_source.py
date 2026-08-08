"""Commit 1 针对性测试：AI估算/当前采用收敛 + 总成本唯一来源 + 用户修正保存。

覆盖任务书第十五节第 1-17 项：
1. 首次 AI 返回后 AI估算 = 当前采用；
2. AI估算只读；
3. 用户修改当前采用不会改变 AI估算；
4. 当前采用是唯一正式包装计算输入；
5. 再次 AI 不覆盖第一次 AI估算；
6. 新商品清空后允许重新建立新的第一次 AI估算；
7-11. 成本/运费/包装/货代/尾程与汇率联动；
12. 当前系统总成本与利润区使用同一个总成本结果；
13-16. 保存后 ai_initial/current_estimate/user_note/suggested_package 语义；
17. 历史重新打开后 AI估算 / 当前采用 / 修正说明正确恢复。
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.domain.models import (
    AIObservation,
    PackagingProposal,
    PackagingScenario,
)
from profit_accounting_26.ui.pages import CalculationPage

RATE = 7.2


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    widget = CalculationPage(temp_context)
    yield widget
    widget.deleteLater()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_proposal(dims=(17.0, 32.0, 17.0, 720.0), method="AI建议包装"):
    length, width, height, weight = dims
    scenario = PackagingScenario(
        label="正常档",
        packaging_method=method,
        length_cm=length,
        width_cm=width,
        height_cm=height,
        weight_g=weight,
        confidence="medium",
        needs_review=False,
    )
    return PackagingProposal(normal=scenario, conservative=scenario, needs_review=False)


def _simulate_ai(page, dims=(17.0, 32.0, 17.0, 720.0), method="AI建议包装"):
    """按 _recognition_completed 的顺序模拟一次 AI 识图成功。"""
    proposal = _make_proposal(dims, method)
    page._adopt_packaging(proposal)
    page.apply_proposal(page._adopted_packaging())
    page._maybe_capture_initial_ai_snapshot(AIObservation(), None)
    page.recalculate()
    return proposal


def _ensure_forwarders(page):
    settings = page.context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
    settings["selected_forwarder_id"] = shenzhen.id
    page.context.settings_service.save(settings)
    page.refresh_settings()
    return shenzhen.id, yiwu.id


def _arm_costs(page):
    page.product_cost.setValue(66.80)
    page.domestic_shipping.setValue(28.0)


def _silence_save_dialogs(monkeypatch):
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(qw.QMessageBox, "warning", lambda *a, **k: None)


def _total_from_label(page) -> float:
    match = re.search(r"¥\s*([\d.]+)", page.system_total.text())
    assert match is not None, f"总成本标签格式异常: {page.system_total.text()!r}"
    return float(match.group(1))


def _fill_and_save(page, monkeypatch):
    _silence_save_dialogs(monkeypatch)
    _arm_costs(page)
    _ensure_forwarders(page)
    _simulate_ai(page)
    page.recalculate()
    assert page.current_quote is not None
    page.save_record()
    assert page.record_id
    return page.record_id


# ---------------------------------------------------------------------------
# 1-6：AI估算 / 当前采用 行为
# ---------------------------------------------------------------------------


class TestAdoptedFlow:
    def test_first_ai_fills_both_cards_identically(self, page):
        """第 1 项：首次 AI 返回后 AI估算 = 当前采用。"""
        _simulate_ai(page)
        for key in ("length", "width", "height", "weight"):
            assert page.normal_fields[key].value() == page.conservative_fields[key].value()
        assert page.normal_fields["method"].text() == page.conservative_fields["method"].text()
        assert page.initial_ai_snapshot is not None

    def test_ai_estimate_card_is_read_only(self, page):
        """第 2 项：AI估算（左卡）包装方式与四维全部只读。"""
        _simulate_ai(page)
        assert page.normal_fields["method"]._widget.isReadOnly()
        for key in ("length", "width", "height", "weight"):
            assert page.normal_fields[key].spin.isReadOnly()
        # 当前采用（右卡）必须可编辑
        assert not page.conservative_fields["method"]._widget.isReadOnly()
        for key in ("length", "width", "height", "weight"):
            assert not page.conservative_fields[key].spin.isReadOnly()

    def test_editing_adopted_does_not_touch_ai_estimate(self, page):
        """第 3 项：用户修改当前采用不会改变 AI估算。"""
        _simulate_ai(page)
        page.conservative_fields["length"].setValue(25.0)
        page.conservative_fields["weight"].setValue(900.0)
        assert page.normal_fields["length"].value() == pytest.approx(17.0)
        assert page.normal_fields["weight"].value() == pytest.approx(720.0)

    def test_adopted_is_the_only_calculation_input(self, page):
        """第 4 项：当前采用是唯一正式包装计算输入。"""
        _ensure_forwarders(page)
        _arm_costs(page)
        _simulate_ai(page)
        page.recalculate()
        base_total = page.current_quote.total_logistics_rmb
        # 只改左卡（AI估算）：计算结果不变
        page._updating = False
        page.normal_fields["length"].setValue(99.0)
        page.recalculate()
        assert page.current_quote.total_logistics_rmb == pytest.approx(base_total)
        # 改右卡（当前采用）：计算结果变化
        page.conservative_fields["length"].setValue(60.0)
        page.recalculate()
        assert page.current_quote.total_logistics_rmb != pytest.approx(base_total)
        scenario = page.current_scenario()
        assert scenario.length_cm == pytest.approx(60.0)

    def test_second_ai_does_not_overwrite_frozen_estimate(self, page):
        """第 5 项：再次 AI 不覆盖第一次 AI估算与已编辑的当前采用。"""
        _simulate_ai(page, dims=(17.0, 32.0, 17.0, 720.0))
        page.conservative_fields["length"].setValue(25.0)
        _simulate_ai(page, dims=(99.0, 99.0, 99.0, 9999.0), method="第二次AI")
        assert page.normal_fields["length"].value() == pytest.approx(17.0)
        assert page.normal_fields["method"].text() == "AI建议包装"
        assert page.conservative_fields["length"].value() == pytest.approx(25.0)

    def test_clear_new_allows_new_first_ai(self, qapp, page, monkeypatch):
        """第 6 项：新商品清空后允许重新建立新的第一次 AI估算。"""
        import profit_accounting_26.ui.pages.calculation_page as calculation_page_module

        monkeypatch.setattr(calculation_page_module, "confirm_action", lambda *a, **k: True)
        _simulate_ai(page)
        page.clear_new()
        assert page.initial_ai_snapshot is None
        assert page.current_feedback_id is None
        assert page.user_correction.text() == ""
        _simulate_ai(page, dims=(40.0, 30.0, 10.0, 500.0), method="新首次AI")
        assert page.normal_fields["length"].value() == pytest.approx(40.0)
        assert page.conservative_fields["length"].value() == pytest.approx(40.0)
        assert page.initial_ai_snapshot is not None


# ---------------------------------------------------------------------------
# 7-12：总成本唯一来源与联动
# ---------------------------------------------------------------------------


class TestSingleCostSource:
    def _arm(self, page):
        _ensure_forwarders(page)
        _arm_costs(page)
        _simulate_ai(page)
        page.recalculate()
        assert page.current_quote is not None

    def test_product_cost_change_syncs_total(self, page):
        """第 7 项：商品成本修改 → 当前系统总成本同步。"""
        self._arm(page)
        before = _total_from_label(page)
        page.product_cost.spin.setValue(100.0)  # 真实控件 valueChanged 直连 recalculate
        after = _total_from_label(page)
        assert after == pytest.approx(before + (100.0 - 66.80), abs=0.01)

    def test_domestic_shipping_change_syncs_total(self, page):
        """第 8 项：国内运费修改 → 当前系统总成本同步。"""
        self._arm(page)
        before = _total_from_label(page)
        page.domestic_shipping.spin.setValue(40.0)
        after = _total_from_label(page)
        assert after == pytest.approx(before + (40.0 - 28.0), abs=0.01)

    def test_adopted_dims_change_syncs_full_chain(self, page):
        """第 9 项：当前采用尺寸/重量修改 → 计费重/头程/总成本/利润同步。"""
        self._arm(page)
        before_total = _total_from_label(page)
        before_logistics = page.current_quote.total_logistics_rmb
        page.conservative_fields["weight"].spin.setValue(2000.0)
        assert page.current_quote.total_logistics_rmb != pytest.approx(before_logistics)
        assert _total_from_label(page) != pytest.approx(before_total)
        # 利润区成本同步（同一总成本结果）
        assert page.profit_binder._calculation_total_cost_rmb == pytest.approx(_total_from_label(page), abs=0.01)

    def test_forwarder_switch_syncs_first_mile_and_total(self, page):
        """第 10 项：切换货代 → 头程费 + 固定服务费 + 总成本同步。"""
        shenzhen_id, yiwu_id = _ensure_forwarders(page)
        _arm_costs(page)
        _simulate_ai(page)
        page.recalculate()
        shenzhen_total = _total_from_label(page)
        assert "深圳货代" in page.system_rows["first_mile"].text()
        page.selected_forwarder_id = yiwu_id
        page.recalculate()
        assert "义乌货代" in page.system_rows["first_mile"].text()
        assert _total_from_label(page) != pytest.approx(shenzhen_total)

    def test_tail_usd_and_rate_change_sync_rmb_and_total(self, page):
        """第 11 项：尾程 USD / 汇率变化 → RMB尾程 + 总成本 + 利润同步。"""
        self._arm(page)
        usd_before = page.tail_fee_usd.value()
        rmb_before = page.tail_fee_rmb.value()
        page.tail_fee_usd.spin.setValue(usd_before + 1.0)  # 真实控件实时联动
        assert page.tail_fee_rmb.value() == pytest.approx(rmb_before + RATE, abs=0.01)
        assert "尾程" in page.system_names["tail"].text()

        # 汇率变化 → refresh_settings 后尾程 RMB 与总成本同步
        settings = page.context.settings_service.load()
        settings["exchange_rate_usd_to_rmb"] = 7.0
        page.context.settings_service.save(settings)
        page.refresh_settings()
        assert page.tail_fee_rmb.value() == pytest.approx(page.tail_fee_usd.value() * 7.0, abs=0.01)
        assert page.profit_binder._calculation_total_cost_rmb == pytest.approx(_total_from_label(page), abs=0.01)

    def test_cost_label_and_profit_area_share_one_result(self, page):
        """第 12 项：当前系统总成本与利润区使用同一个总成本结果。"""
        self._arm(page)
        shown = _total_from_label(page)
        assert page.current_system_cost == pytest.approx(shown, abs=0.01)
        assert page.profit_binder._calculation_total_cost_rmb == pytest.approx(shown, abs=0.01)
        # 六行唯一成本显示：采购成本 / 国内运费 / 头程(带货代名) / 服务费 / 尾程
        assert "¥66.80" in page.system_rows["product"].text()
        assert "¥28.00" in page.system_rows["domestic"].text()
        assert "深圳货代" in page.system_rows["first_mile"].text()
        # 第五轮：摘要尾程只显示 RMB（USD 输入已移到总成本标题上方）
        assert "¥" in page.system_rows["tail"].text()
        assert "$" not in page.system_rows["tail"].text()


# ---------------------------------------------------------------------------
# 13-17：保存语义与历史恢复
# ---------------------------------------------------------------------------


class TestSaveAndRestore:
    def test_ai_initial_never_overwritten_on_resave(self, qapp, page, monkeypatch):
        """第 13 项：保存后 ai_initial 不被覆盖。"""
        rid = _fill_and_save(page, monkeypatch)
        # 修改当前采用后再次保存（同一记录）
        page.conservative_fields["length"].setValue(40.0)
        page.recalculate()
        page.save_record()
        record = page.context.record_service.load(rid)
        ai_pkg = record["_v2"]["ai_initial"]["adopted_packaging"]["normal"]
        assert ai_pkg["length_cm"] == pytest.approx(17.0)
        assert ai_pkg["packaging_method"] == "AI建议包装"

    def test_current_estimate_stores_adopted_card(self, qapp, page, monkeypatch):
        """第 14 项：current_estimate 保存当前采用。"""
        rid = _fill_and_save(page, monkeypatch)
        record = page.context.record_service.load(rid)
        current = record["_v2"]["current_estimate"]
        assert current["length_cm"] == pytest.approx(17.0)
        assert current["weight_g"] == pytest.approx(720.0)
        assert record["layers"]["adopted"]["selected_packaging"] == "保守档"
        # 修改后重存
        page.conservative_fields["length"].setValue(40.0)
        page.recalculate()
        page.save_record()
        record = page.context.record_service.load(rid)
        assert record["_v2"]["current_estimate"]["length_cm"] == pytest.approx(40.0)

    def test_user_correction_saved_as_user_note(self, qapp, page, monkeypatch):
        """第 15 项：用户修正保存为 user_note；同一 feedback_id 更新不重复创建。"""
        _silence_save_dialogs(monkeypatch)
        _arm_costs(page)
        _ensure_forwarders(page)
        _simulate_ai(page)
        page.user_correction.setText("这个包可以压扁，肩带可以拆下来单独放")
        page.recalculate()
        page.save_record()
        rid = page.record_id
        feedback_id = page.current_feedback_id
        assert feedback_id
        feedback = page.context.calibration_feedback_service.load(feedback_id)
        assert feedback.user_note == "这个包可以压扁，肩带可以拆下来单独放"
        assert feedback.source == "user"
        # 记录已 link_feedback
        record = page.context.record_service.load(rid)
        assert record["_v2"]["calibration_feedback_id"] == feedback_id
        # 再次保存：更新同一个 feedback_id，禁止重复创建
        page.product_cost.setValue(70.0)
        page.recalculate()
        page.save_record()
        assert page.current_feedback_id == feedback_id
        assert len(page.context.calibration_feedback_service.for_record(rid)) == 1

    def test_no_empty_feedback_created(self, qapp, page, monkeypatch):
        """第 15 项补充：无修改无修正说明时不创建空 feedback。"""
        rid = _fill_and_save(page, monkeypatch)
        assert page.current_feedback_id is None
        assert page.context.calibration_feedback_service.for_record(rid) == []

    def test_suggested_package_is_user_suggested_not_measured(self, qapp, page, monkeypatch):
        """第 16 项：suggested_package 不会被标为实际测量；绝不写 actual_logistics。"""
        _silence_save_dialogs(monkeypatch)
        _arm_costs(page)
        _ensure_forwarders(page)
        _simulate_ai(page)
        # 用真实控件路径模拟用户手动修改（触发用户校准 dirty）
        page.conservative_fields["length"].spin.setValue(25.0)
        page.recalculate()
        page.save_record()
        feedback = page.context.calibration_feedback_service.load(page.current_feedback_id)
        assert feedback.suggested_package is not None
        assert feedback.suggested_package.evidence_level == "user_suggested"
        assert feedback.suggested_package.length_cm == pytest.approx(25.0)
        # 主界面保存绝不写实际测量数据
        assert feedback.actual_logistics is None

    def test_reopen_restores_ai_estimate_adopted_and_note(self, qapp, page, monkeypatch):
        """第 17 项：历史重新打开后 AI估算 / 当前采用 / 修正说明正确恢复。"""
        _silence_save_dialogs(monkeypatch)
        _arm_costs(page)
        _ensure_forwarders(page)
        _simulate_ai(page)
        page.conservative_fields["length"].setValue(25.0)
        page.user_correction.setText("肩带可拆")
        page.recalculate()
        page.save_record()
        rid = page.record_id

        page.load_record_payload(rid)
        # AI估算恢复首次 AI 数据
        assert page.normal_fields["length"].value() == pytest.approx(17.0)
        assert page.normal_fields["method"].text() == "AI建议包装"
        # 当前采用恢复用户修改后的数据
        assert page.conservative_fields["length"].value() == pytest.approx(25.0)
        # 修正说明恢复
        assert page.user_correction.text() == "肩带可拆"
        assert page.current_feedback_id is not None

    def test_reopen_legacy_record_without_v2(self, qapp, temp_context, monkeypatch):
        """第 28 项相关：旧记录（无 _v2）仍可打开且不伪造第一次 AI 数据。"""
        page = CalculationPage(temp_context)
        try:
            rid = _fill_and_save(page, monkeypatch)
            # 模拟旧记录：移除 _v2 块后直接写回存储
            store = temp_context.store
            raw = store.load_record(rid)
            raw.pop("_v2", None)
            store.update_record(rid, raw, snapshot_kind="recalculation")
            page.load_record_payload(rid)
            # 回退 adopted.normal / selected 槽，正常显示
            assert page.normal_fields["length"].value() == pytest.approx(17.0)
            assert page.conservative_fields["length"].value() == pytest.approx(17.0)
            assert page.current_feedback_id is None
        finally:
            page.deleteLater()

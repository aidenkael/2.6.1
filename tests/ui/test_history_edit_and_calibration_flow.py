"""Commit 1 针对性测试：历史编辑闭环 + 用户校准统一 + dirty 状态。

覆盖本轮任务书第一至五节、第十五节场景 A/B/C 与验收第 1-19 项相关行为：
1. AI 首次自动复制不标校准、不置用户校准 dirty；
2/3. 用户手动改当前采用尺寸或填写用户修正才置 dirty；
5/6. suggested_package 恒 user_suggested，绝不写 actual_measured/actual_logistics；
11. 历史恢复后保存不被“包装估算已过期”阻止；
12/13/14/15. 更新原 record_id、revision 递增、不重复记录、不重复 feedback；
16. 清空并新建退出编辑模式；
18. 历史恢复后再次 AI 不覆盖 AI估算/当前采用；
双向一致：主页改 → 历史对话框预填；历史改 → 主页恢复显示；再主页改更新同一条。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario
from profit_accounting_26.ui.pages import CalculationPage
from profit_accounting_26.ui.pages.calibration_feedback_dialog import CalibrationFeedbackDialog


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
    proposal = _make_proposal(dims, method)
    page._adopt_packaging(proposal)
    page.apply_proposal(page._adopted_packaging())
    page._maybe_capture_initial_ai_snapshot(AIObservation(), None)
    page.recalculate()
    return proposal


def _ensure_forwarders(page):
    settings = page.context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen)]
    settings["selected_forwarder_id"] = shenzhen.id
    page.context.settings_service.save(settings)
    page.refresh_settings()
    return shenzhen.id


def _silence_dialogs(monkeypatch):
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(qw.QMessageBox, "warning", lambda *a, **k: None)


def _arm_and_save_new(page, monkeypatch, *, user_edit: bool = True) -> str:
    """完整走一遍新商品保存；user_edit=True 时用户手动改过当前采用长度。"""
    _silence_dialogs(monkeypatch)
    page.product_cost.setValue(66.80)
    page.domestic_shipping.setValue(28.0)
    _ensure_forwarders(page)
    _simulate_ai(page)
    if user_edit:
        page.conservative_fields["length"].spin.setValue(25.0)
    page.recalculate()
    assert page.current_quote is not None
    page.save_record()
    assert page.record_id
    return page.record_id


# ---------------------------------------------------------------------------
# 用户校准 dirty 语义
# ---------------------------------------------------------------------------


class TestUserCalibrationDirty:
    def test_ai_copy_does_not_set_dirty(self, page):
        """第 1 项：AI 首次自动复制到当前采用不算用户校准。"""
        _simulate_ai(page)
        assert page.user_calibration_dirty is False
        assert page.conservative_fields["length"].value() == pytest.approx(17.0)

    def test_manual_dims_edit_sets_dirty(self, page):
        """第 2 项：用户手动改当前采用长/宽/高/重量 → dirty。"""
        _simulate_ai(page)
        page.conservative_fields["length"].spin.setValue(25.0)
        assert page.user_calibration_dirty is True

    def test_manual_note_sets_dirty(self, page):
        """第 3 项：填写/修改用户修正 → dirty。"""
        _simulate_ai(page)
        page.user_correction._widget.setPlainText("这个包可以压扁")
        assert page.user_calibration_dirty is True

    def test_programmatic_restore_does_not_set_dirty(self, page):
        """程序化 setValue/setText（AI复制、历史恢复）不置 dirty。"""
        _simulate_ai(page)
        page.conservative_fields["length"].setValue(30.0)
        page.user_correction.setText("程序化写入")
        assert page.user_calibration_dirty is False

    def test_ai_copy_without_dirty_creates_no_feedback(self, qapp, page, monkeypatch):
        """第 1 项：纯 AI 复制保存后不产生校准反馈。"""
        rid = _arm_and_save_new(page, monkeypatch, user_edit=False)
        assert page.current_feedback_id is None
        assert page.context.calibration_feedback_service.for_record(rid) == []

    def test_suggested_is_user_suggested_never_measured(self, qapp, page, monkeypatch):
        """第 6 项：suggested_package 恒 user_suggested，绝不 actual_measured。"""
        _arm_and_save_new(page, monkeypatch, user_edit=True)
        feedback = page.context.calibration_feedback_service.load(page.current_feedback_id)
        assert feedback.suggested_package is not None
        assert feedback.suggested_package.evidence_level == "user_suggested"
        assert feedback.actual_logistics is None


# ---------------------------------------------------------------------------
# 历史编辑闭环
# ---------------------------------------------------------------------------


class TestHistoryEditClosedLoop:
    def test_load_enters_edit_mode_and_clears_stale(self, qapp, page, monkeypatch):
        """第 11 项：恢复后进入编辑模式，保存不再被“包装估算已过期”阻止。"""
        rid = _arm_and_save_new(page, monkeypatch)
        # 模拟一条曾标记过期的记录
        raw = page.context.store.load_record(rid)
        raw["layers"]["adopted"]["packaging_estimate_stale"] = True
        page.context.store.update_record(rid, raw, snapshot_kind="recalculation")

        page.load_record_payload(rid)
        assert page.editing_record_id == rid
        assert page.record_id == rid
        assert page.packaging_stale is False
        assert page.btn_save_record.text() == "更新此记录"
        assert page.edit_state_label.text() == "正在编辑历史记录"
        assert page.edit_state_label.isVisibleTo(page)

        # 恢复后改任何字段都允许直接重算保存（裸规格变化也不会标过期）
        page.bare_weight.spin.setValue(500.0)
        page.product_cost.spin.setValue(70.0)
        assert page.packaging_stale is False
        page.recalculate()
        page.save_record()
        assert page.record_id == rid
        assert len(page.context.record_service.list()) == 1

    def test_resave_updates_same_record_and_bumps_revision(self, qapp, page, monkeypatch):
        """第 12/13/14 项：更新原 record_id、revision 递增、不新建记录。"""
        rid = _arm_and_save_new(page, monkeypatch)
        v2 = page.context.history_record_v2_service
        assert v2.load_v2(rid).revision == 1
        page.load_record_payload(rid)
        page.conservative_fields["length"].spin.setValue(28.0)
        page.recalculate()
        page.save_record()
        assert page.record_id == rid
        assert len(page.context.record_service.list()) == 1
        updated = v2.load_v2(rid)
        assert updated.revision == 2
        assert updated.current_estimate["length_cm"] == pytest.approx(28.0)
        # ai_initial 保留不被覆盖
        assert updated.ai_initial is not None
        assert updated.ai_initial["adopted_packaging"]["normal"]["length_cm"] == pytest.approx(17.0)

    def test_resave_does_not_duplicate_feedback(self, qapp, page, monkeypatch):
        """第 15 项：历史编辑再次保存更新同一个 feedback_id。"""
        rid = _arm_and_save_new(page, monkeypatch)
        first_feedback_id = page.current_feedback_id
        assert first_feedback_id is not None
        page.load_record_payload(rid)
        assert page.current_feedback_id == first_feedback_id
        page.conservative_fields["length"].spin.setValue(26.0)
        page.recalculate()
        page.save_record()
        assert page.current_feedback_id == first_feedback_id
        assert len(page.context.calibration_feedback_service.for_record(rid)) == 1
        feedback = page.context.calibration_feedback_service.load(first_feedback_id)
        assert feedback.suggested_package.length_cm == pytest.approx(26.0)

    def test_second_ai_after_load_does_not_overwrite_cards(self, qapp, page, monkeypatch):
        """第 18 项：历史恢复后再次 AI 不覆盖 AI估算与当前采用。"""
        rid = _arm_and_save_new(page, monkeypatch)
        page.load_record_payload(rid)
        _simulate_ai(page, dims=(99.0, 99.0, 99.0, 9999.0), method="第二次AI")
        assert page.normal_fields["length"].value() == pytest.approx(17.0)
        assert page.normal_fields["method"].text() == "AI建议包装"
        assert page.conservative_fields["length"].value() == pytest.approx(25.0)

    def test_clear_new_exits_edit_mode(self, qapp, page, monkeypatch):
        """第 16 项：清空并新建退出编辑模式并复位全部编辑状态。"""
        import profit_accounting_26.ui.pages.calculation_page as calculation_page_module

        _arm_and_save_new(page, monkeypatch)
        page.load_record_payload(page.record_id)
        monkeypatch.setattr(calculation_page_module, "confirm_action", lambda *a, **k: True)
        page.clear_new()
        assert page.editing_record_id is None
        assert page.record_id is None
        assert page.current_feedback_id is None
        assert page.initial_ai_snapshot is None
        assert page.user_calibration_dirty is False
        assert page.btn_save_record.text() == "保存本次记录"
        assert not page.edit_state_label.isVisibleTo(page)
        # 新商品允许重建第一次 AI
        _simulate_ai(page, dims=(40.0, 30.0, 10.0, 500.0), method="新首次AI")
        assert page.initial_ai_snapshot is not None
        assert page.normal_fields["length"].value() == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# 双向一致：主页入口 A ↔ 历史对话框入口 B
# ---------------------------------------------------------------------------


class TestBidirectionalCalibration:
    def test_scenario_a_then_b_then_a_same_record_and_feedback(self, qapp, page, monkeypatch):
        """场景 A/B/C：主页改→历史预填；历史改→主页恢复；再主页改更新同一条。"""
        # 场景 A：主页用户校准（长度 25）保存
        rid = _arm_and_save_new(page, monkeypatch, user_edit=True)
        feedback_id = page.current_feedback_id
        assert feedback_id is not None

        # 历史对话框预填主页保存的当前采用
        existing = page.context.calibration_feedback_service.load(feedback_id)
        dialog = CalibrationFeedbackDialog(page.context, rid, feedback=existing)
        assert dialog.length_edit.text() == "25"

        # 场景 B：历史对话框修改（长度 30）→ 同步 current_estimate + 同一条 feedback
        dialog.length_edit.setText("30")
        dialog.user_note.setPlainText("历史页校准")
        assert dialog.save() == feedback_id
        v2 = page.context.history_record_v2_service.load_v2(rid)
        assert v2.current_estimate["length_cm"] == pytest.approx(30.0)
        assert len(page.context.calibration_feedback_service.for_record(rid)) == 1

        # 主页恢复后显示历史页校准后的最新值
        page.load_record_payload(rid)
        assert page.conservative_fields["length"].value() == pytest.approx(30.0)
        assert page.user_correction.text() == "历史页校准"
        assert page.current_feedback_id == feedback_id

        # 场景 C：再回主页修改（长度 35）→ 更新同一条记录与同一条 feedback
        page.conservative_fields["length"].spin.setValue(35.0)
        page.recalculate()
        page.save_record()
        assert page.record_id == rid
        assert page.current_feedback_id == feedback_id
        assert len(page.context.record_service.list()) == 1
        assert len(page.context.calibration_feedback_service.for_record(rid)) == 1
        feedback = page.context.calibration_feedback_service.load(feedback_id)
        assert feedback.suggested_package.length_cm == pytest.approx(35.0)
        final = page.context.history_record_v2_service.load_v2(rid)
        assert final.current_estimate["length_cm"] == pytest.approx(35.0)

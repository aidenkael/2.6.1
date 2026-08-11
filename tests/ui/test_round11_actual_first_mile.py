"""真实头程反馈：主页面“当前采用”卡新增真实头程（选填），保存进 actual_logistics，不参与计算。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QScrollArea, QWidget

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.ui.main_window import MainWindow
from profit_accounting_26.ui.pages import CalculationPage, HistoryPage
from profit_accounting_26.ui.pages.calibration_feedback_dialog import CalibrationFeedbackDialog


@pytest.fixture()
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _install_forwarders(context, *, with_archived: bool = False, with_disabled: bool = False):
    settings = context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
    forwarders = [asdict(shenzhen), asdict(yiwu)]
    if with_archived:
        archived = SettingsService.new_forwarder("已归档货代", 90.0, 8.0, 8000.0)
        archived_data = asdict(archived)
        archived_data["archived"] = True
        archived_data["enabled"] = False
        forwarders.append(archived_data)
    if with_disabled:
        disabled = SettingsService.new_forwarder("停用未归档货代", 88.0, 7.0, 8000.0)
        disabled_data = asdict(disabled)
        disabled_data["enabled"] = False
        forwarders.append(disabled_data)
    settings["forwarders"] = forwarders
    settings["selected_forwarder_id"] = shenzhen.id
    context.settings_service.save(settings)
    return shenzhen.id, yiwu.id


def _make_page(context) -> CalculationPage:
    page = CalculationPage(context)
    _install_forwarders(page.context)
    page.conservative_fields["length"].setValue(25.0)
    page.conservative_fields["width"].setValue(18.0)
    page.conservative_fields["height"].setValue(6.0)
    page.conservative_fields["weight"].setValue(320.0)
    page.refresh_settings()
    page.recalculate()
    return page


def _create_record(context, name: str = "真实头程商品") -> str:
    payload = {
        "product_name": name,
        "product_link": "",
        "status": "active",
        "layers": {
            "adopted": {
                "selected_packaging": "保守档",
                "conservative": {
                    "packaging_method": "袋装",
                    "length_cm": 25,
                    "width_cm": 18,
                    "height_cm": 6,
                    "weight_g": 320,
                },
            },
            "calculated": {"system_cost_rmb": 100.0, "exchange_rate": 7.2},
        },
    }
    return context.record_service.save(payload, images=[])


class TestMainPageLayout:
    def test_actual_first_mile_display_contract_and_geometry(self, qapp, temp_context):
        page = _make_page(temp_context)
        try:
            page.resize(1688, 929)
            page.show()
            qapp.processEvents()
            card = page.conservative_fields["card"]
            texts = [label.text() for label in card.findChildren(QLabel)]
            assert "用户修正" not in texts, "独立“用户修正”小标题应删除"
            assert "真实头程（选填）" not in texts
            assert "真实头程" in texts
            assert "选填，仅记录，不影响计算" in texts
            row = page.actual_first_mile_row
            row_texts = [label.text() for label in row.findChildren(QLabel)]
            assert "RMB" not in row_texts
            assert "¥" in row_texts
            assert page.actual_first_mile_fee_edit.width() < 72
            row_controls = (
                row.findChild(QLabel, "actualFirstMileLabel"),
                page.actual_forwarder_combo,
                row.findChild(QLabel, "actualFirstMileCurrency"),
                page.actual_first_mile_fee_edit,
            )
            assert all(row_controls)
            for index, left in enumerate(row_controls):
                for right in row_controls[index + 1:]:
                    assert not left.geometry().intersects(right.geometry())
            # 用户修正框仍在（同一控件），无第二个文本框
            assert page.user_correction._widget is not None
        finally:
            page.close()
            page.deleteLater()
            qapp.processEvents()

    def test_1920_viewport_has_no_vertical_overflow_or_badge_overlap(self, qapp, temp_context):
        window = MainWindow(temp_context)
        try:
            window.resize(1920, 1080)
            window.show()
            window.switch_page(0)
            qapp.processEvents()
            page = window.calculation_page
            root = page._root
            scroll = root.findChild(QScrollArea, "calculationScrollArea")
            body = root.findChild(QWidget, "calculationBody")
            assert scroll is not None and body is not None
            viewport_height = scroll.viewport().height()
            assert body.minimumSizeHint().height() <= viewport_height
            assert body.sizeHint().height() <= viewport_height
            assert scroll.verticalScrollBar().maximum() == 0

            title = root.findChild(QLabel, "lblAiSummaryTitle")
            badge = page.review_badge
            title_rect = QRect(title.mapTo(window, title.rect().topLeft()), title.size())
            badge_rect = QRect(badge.mapTo(window, badge.rect().topLeft()), badge.size())
            assert not title_rect.intersects(badge_rect)

            profit_section = root.findChild(QWidget, "profitSection")
            profit_fields = root.findChild(QWidget, "profitFieldsHost")
            assert profit_section is not None and profit_fields is not None
            bottom_gap = profit_section.height() - (profit_fields.y() + profit_fields.height())
            assert bottom_gap <= 16

            # 窄窗口可出现滚动，但标题 badge 不能压到标题文字上。
            window.resize(1280, 800)
            qapp.processEvents()
            title_rect = QRect(title.mapTo(window, title.rect().topLeft()), title.size())
            badge_rect = QRect(badge.mapTo(window, badge.rect().topLeft()), badge.size())
            assert not title_rect.intersects(badge_rect)
        finally:
            window.close()
            window.deleteLater()
            qapp.processEvents()

    def test_forwarder_combo_only_unarchived(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _install_forwarders(page.context, with_archived=True)
            page.refresh_settings()
            combo = page.actual_forwarder_combo
            names = [combo.itemText(i) for i in range(combo.count())]
            assert "深圳货代" in names and "义乌货代" in names
            assert "已归档货代" not in names
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_forwarder_combo_keeps_disabled_but_unarchived(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _install_forwarders(page.context, with_archived=True, with_disabled=True)
            page.refresh_settings()
            names = [page.actual_forwarder_combo.itemText(i) for i in range(page.actual_forwarder_combo.count())]
            assert "停用未归档货代" in names
            assert "已归档货代" not in names
        finally:
            page.deleteLater()
            qapp.processEvents()


class TestSaveFeedback:
    def test_note_only_saves(self, qapp, temp_context):
        page = _make_page(temp_context)
        try:
            record_id = _create_record(page.context)
            page.record_id = record_id
            page.user_correction.setText("这个包可以压扁")
            page._save_user_feedback()
            feedbacks = page.context.calibration_feedback_service.for_record(record_id)
            assert len(feedbacks) == 1
            assert feedbacks[0].user_note == "这个包可以压扁"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_adopted_change_saves_as_user_calibration(self, qapp, temp_context):
        page = _make_page(temp_context)
        try:
            record_id = _create_record(page.context)
            page.record_id = record_id
            page.user_calibration_dirty = True
            page._save_user_feedback()
            feedbacks = page.context.calibration_feedback_service.for_record(record_id)
            assert len(feedbacks) == 1
            assert feedbacks[0].suggested_package is not None
            assert feedbacks[0].suggested_package.evidence_level == "user_suggested"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_actual_first_mile_only_saves_to_actual_logistics(self, qapp, temp_context):
        page = _make_page(temp_context)
        try:
            record_id = _create_record(page.context)
            page.record_id = record_id
            page.actual_first_mile_fee_edit.setText("26")
            combo_index = page.actual_forwarder_combo.findText("深圳货代")
            page.actual_forwarder_combo.setCurrentIndex(combo_index)
            page._save_user_feedback()
            feedbacks = page.context.calibration_feedback_service.for_record(record_id)
            assert len(feedbacks) == 1
            feedback = feedbacks[0]
            assert feedback.actual_logistics is not None
            assert feedback.actual_logistics.actual_first_mile_fee_rmb == 26.0
            assert feedback.actual_logistics.actual_forwarder == "深圳货代"
            # 绝不进入 suggested_package
            assert feedback.suggested_package is None
            assert feedback.user_note is None
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_actual_first_mile_does_not_affect_calculation(self, qapp, temp_context):
        page = _make_page(temp_context)
        try:
            before = (
                page.system_total.text(),
                page.system_rows["tail"].text(),
                page.current_system_cost,
            )
            page.actual_first_mile_fee_edit.setText("999")
            page.recalculate()
            after = (
                page.system_total.text(),
                page.system_rows["tail"].text(),
                page.current_system_cost,
            )
            assert before == after
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_update_keeps_same_feedback_id(self, qapp, temp_context):
        page = _make_page(temp_context)
        try:
            record_id = _create_record(page.context)
            first_id = page.context.calibration_feedback_service.save(
                {"record_id": record_id, "source": "user", "user_note": "v1"}
            )
            page.context.history_record_v2_service.link_feedback(record_id, first_id)
            page.load_record_payload(record_id)
            page.actual_first_mile_fee_edit.setText("26")
            page._save_user_feedback()
            feedbacks = page.context.calibration_feedback_service.for_record(record_id)
            assert len(feedbacks) == 1
            assert feedbacks[0].feedback_id == first_id
            assert feedbacks[0].actual_logistics is not None
            assert feedbacks[0].user_note == "v1"
        finally:
            page.deleteLater()
            qapp.processEvents()


class TestHistoryDialogAndTable:
    def _feedback_with_actual(self, context, record_id, forwarder="深圳货代", fee=26.0):
        return context.calibration_feedback_service.save(
            {
                "record_id": record_id,
                "source": "user",
                "actual_logistics": {
                    "actual_first_mile_fee_rmb": fee,
                    "actual_forwarder": forwarder,
                },
            }
        )

    def test_dialog_prefills_actual_first_mile(self, qapp, temp_context):
        record_id = _create_record(temp_context)
        fid = self._feedback_with_actual(temp_context, record_id)
        temp_context.history_record_v2_service.link_feedback(record_id, fid)
        feedback = temp_context.calibration_feedback_service.load(fid)
        dialog = CalibrationFeedbackDialog(temp_context, record_id, feedback=feedback)
        assert dialog.actual_first_mile_fee_edit.text() == "26"
        assert dialog.actual_forwarder_combo.currentText() == "深圳货代"

    def test_new_dialog_loads_current_unarchived_forwarders(self, qapp, temp_context):
        record_id = _create_record(temp_context)
        _install_forwarders(temp_context, with_disabled=True)
        dialog = CalibrationFeedbackDialog(temp_context, record_id)
        names = [dialog.actual_forwarder_combo.itemText(i) for i in range(dialog.actual_forwarder_combo.count())]
        assert "深圳货代" in names
        assert "义乌货代" in names
        assert "停用未归档货代" in names

    def test_archived_forwarder_still_shown_in_dialog_and_table(self, qapp, temp_context):
        record_id = _create_record(temp_context)
        fid = self._feedback_with_actual(temp_context, record_id, forwarder="老货代A", fee=26.0)
        temp_context.history_record_v2_service.link_feedback(record_id, fid)
        feedback = temp_context.calibration_feedback_service.load(fid)
        dialog = CalibrationFeedbackDialog(temp_context, record_id, feedback=feedback)
        names = [dialog.actual_forwarder_combo.itemText(i) for i in range(dialog.actual_forwarder_combo.count())]
        assert "老货代A" in names
        assert dialog.actual_forwarder_combo.currentText() == "老货代A"
        # 历史主表“校准内容”仍显示真实头程
        page = HistoryPage(temp_context)
        try:
            row = 0
            for r in range(page.table.rowCount()):
                if page.table.item(r, 0).data(256) == record_id:
                    row = r
                    break
            label = page.table.cellWidget(row, 7)
            text = label.findChild(QLabel).text()
            assert text.startswith("已反馈")
            assert "真实头程：老货代A ¥26" in text
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_history_shows_suggested_package_with_actual_first_mile_only(self, qapp, temp_context):
        record_id = _create_record(temp_context)
        feedback_id = temp_context.calibration_feedback_service.save(
            {
                "record_id": record_id,
                "source": "user",
                "suggested_package": {
                    "length_cm": 22.0,
                    "width_cm": 16.0,
                    "height_cm": 5.0,
                    "weight_g": 280.0,
                    "evidence_level": "user_suggested",
                },
                "actual_logistics": {
                    "actual_first_mile_fee_rmb": 26.0,
                    "actual_forwarder": "深圳货代",
                },
            }
        )
        temp_context.history_record_v2_service.link_feedback(record_id, feedback_id)
        page = HistoryPage(temp_context)
        try:
            row = next(
                row for row in range(page.table.rowCount())
                if page.table.item(row, 0).data(256) == record_id
            )
            text = page.table.cellWidget(row, 7).findChild(QLabel).text()
            assert "22×16×5 / 280g" in text
            assert "真实头程：深圳 ¥26" in text
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_history_shows_current_estimate_with_actual_first_mile_only(self, qapp, temp_context):
        record_id = _create_record(temp_context)
        temp_context.history_record_v2_service.update_current_estimate(
            record_id,
            {"length_cm": 24.0, "width_cm": 15.0, "height_cm": 4.0, "weight_g": 260.0},
        )
        feedback_id = self._feedback_with_actual(temp_context, record_id, fee=26.0)
        temp_context.history_record_v2_service.link_feedback(record_id, feedback_id)
        page = HistoryPage(temp_context)
        try:
            row = next(
                row for row in range(page.table.rowCount())
                if page.table.item(row, 0).data(256) == record_id
            )
            text = page.table.cellWidget(row, 7).findChild(QLabel).text()
            assert "24×15×4 / 260g" in text
            assert "真实头程：深圳 ¥26" in text
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_loading_record_without_actual_first_mile_clears_previous_value(self, qapp, temp_context):
        record_a = _create_record(temp_context, "有真实头程")
        record_b = _create_record(temp_context, "无真实头程")
        feedback_id = self._feedback_with_actual(temp_context, record_a, fee=26.0)
        temp_context.history_record_v2_service.link_feedback(record_a, feedback_id)
        page = CalculationPage(temp_context)
        try:
            _install_forwarders(page.context)
            page.load_record_payload(record_a)
            assert page.actual_first_mile_fee_edit.text() == "26"
            page.load_record_payload(record_b)
            assert page.actual_first_mile_fee_edit.text() == ""
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_actual_first_mile_changes_mark_page_dirty_without_user_calibration(self, qapp, temp_context):
        page = _make_page(temp_context)
        try:
            page.mark_saved()
            page.user_calibration_dirty = False
            page.actual_first_mile_fee_edit.setText("26")
            assert page.dirty is True
            assert page.user_calibration_dirty is False
            page.mark_saved()
            page.actual_forwarder_combo.setCurrentIndex(1)
            assert page.dirty is True
            assert page.user_calibration_dirty is False
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_dialog_edit_keeps_same_feedback_id(self, qapp, temp_context):
        record_id = _create_record(temp_context)
        fid = self._feedback_with_actual(temp_context, record_id, fee=20.0)
        temp_context.history_record_v2_service.link_feedback(record_id, fid)
        feedback = temp_context.calibration_feedback_service.load(fid)
        dialog = CalibrationFeedbackDialog(temp_context, record_id, feedback=feedback)
        dialog.actual_first_mile_fee_edit.setText("30")
        dialog.actual_forwarder_combo.setCurrentIndex(dialog.actual_forwarder_combo.findText("义乌货代"))
        saved_id = dialog.save()
        assert saved_id == fid
        updated = temp_context.calibration_feedback_service.load(fid)
        assert updated.actual_logistics.actual_first_mile_fee_rmb == 30.0
        assert updated.actual_logistics.actual_forwarder == "义乌货代"
        assert len(temp_context.calibration_feedback_service.for_record(record_id)) == 1

    def test_history_table_still_eight_columns(self, qapp, temp_context):
        _create_record(temp_context)
        page = HistoryPage(temp_context)
        try:
            assert page.table.columnCount() == 8
        finally:
            page.deleteLater()
            qapp.processEvents()

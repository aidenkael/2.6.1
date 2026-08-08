"""第四轮修正三/四/七：设置页永久删除必须立即落盘，重启后不复现。

覆盖任务书第十九节：
B8. 创建 profile → 删除 → 当前列表不存在（UI 级）；
C14. 货代永久删除后 settings.json 不再包含货代；
C15. 新建 SettingsService 重新 load 后仍不存在；
C16. 删除当前 selected forwarder 后 selected id 合法重选/清空；
C17. 归档仍可以恢复；
C18. 永久删除和归档语义没有混淆；
D19. 利润规则永久删除后 settings.json 不再包含规则；
D20. 新建 SettingsService 重新 load 后仍不存在；
D21. 删除当前 selected rule 后 selected id 合法重选/清空；
D22. 主页面规则列表刷新后不再显示已删除规则。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtWidgets import QMessageBox

from profit_accounting_26.application import (
    AppContext,
    SettingsService,
)
from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
    VISUAL_AI,
)
from profit_accounting_26.ui.pages import CalculationPage, SettingsPage


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def accept_all_dialogs(monkeypatch):
    """确认类弹窗全部返回确认：中文弹窗走 confirm_action，旧路径兼容 question。"""
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    import profit_accounting_26.ui.pages.settings_page as spm

    monkeypatch.setattr(spm, "confirm_action", lambda *a, **k: True)
    # 永久删除后的 information 提示不阻塞
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))


def _install_two_forwarders(context):
    settings = context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
    settings["selected_forwarder_id"] = shenzhen.id
    context.settings_service.save(settings)
    return shenzhen.id, yiwu.id


def _fresh_settings(context) -> dict:
    """模拟重启：新建 SettingsService 从磁盘重新 load。"""
    service = SettingsService(context.settings_service.path)
    return service.load()


# ---------------------------------------------------------------------------
# C 组：货代永久删除立即落盘
# ---------------------------------------------------------------------------


class TestForwarderPermanentDelete:
    def test_permanent_delete_persists_to_settings_json(self, qapp, temp_context, accept_all_dialogs):
        """第 14 项：永久删除后 settings.json 立即不再包含货代。"""
        shenzhen_id, yiwu_id = _install_two_forwarders(temp_context)
        page = SettingsPage(temp_context)
        try:
            # 永久删除前必须先归档（使用中的货代不允许直接删除）
            page.toggle_forwarder_archive(yiwu_id)
            saved_signal = []
            page.forwardersSaved.connect(lambda: saved_signal.append(True))
            page._delete_forwarder_permanently(yiwu_id)

            settings_on_disk = temp_context.settings_service.load()
            ids = [item["id"] for item in settings_on_disk["forwarders"]]
            assert yiwu_id not in ids
            assert shenzhen_id in ids
            assert saved_signal == [True], "永久删除必须 emit forwardersSaved"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_permanent_delete_survives_settings_service_restart(self, qapp, temp_context, accept_all_dialogs):
        """第 15 项：新建 SettingsService 重新 load 后货代仍不存在。"""
        _shenzhen_id, yiwu_id = _install_two_forwarders(temp_context)
        page = SettingsPage(temp_context)
        try:
            page.toggle_forwarder_archive(yiwu_id)
            page._delete_forwarder_permanently(yiwu_id)

            reloaded = _fresh_settings(temp_context)
            assert all(item["id"] != yiwu_id for item in reloaded["forwarders"])
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_delete_selected_forwarder_reselects_valid_one(self, qapp, temp_context, accept_all_dialogs):
        """第 16 项：删除当前 selected forwarder 后 selected id 合法重选。"""
        shenzhen_id, yiwu_id = _install_two_forwarders(temp_context)
        page = SettingsPage(temp_context)
        try:
            # 归档并永久删除当前选中的深圳货代
            page.toggle_forwarder_archive(shenzhen_id)
            page._delete_forwarder_permanently(shenzhen_id)

            settings_on_disk = temp_context.settings_service.load()
            assert settings_on_disk["selected_forwarder_id"] == yiwu_id
            # 再把仅剩的货代也删掉 → selected 清空
            page.toggle_forwarder_archive(yiwu_id)
            page._delete_forwarder_permanently(yiwu_id)
            settings_on_disk = temp_context.settings_service.load()
            assert settings_on_disk["forwarders"] == []
            assert settings_on_disk["selected_forwarder_id"] == ""
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_archive_is_recoverable_and_not_permanent(self, qapp, temp_context, accept_all_dialogs):
        """第 17/18 项：归档可恢复；归档不等于永久删除（未保存前重启仍在）。"""
        _shenzhen_id, yiwu_id = _install_two_forwarders(temp_context)
        page = SettingsPage(temp_context)
        try:
            page.toggle_forwarder_archive(yiwu_id)
            row = page._find_forwarder_row(yiwu_id)
            assert page.forwarder_table.item(row, 7).text() == "1"
            # 恢复：无需确认，立即回到使用中
            page.toggle_forwarder_archive(yiwu_id)
            row = page._find_forwarder_row(yiwu_id)
            assert page.forwarder_table.item(row, 7).text() == "0"
            # 归档（未点保存）不会把货代从磁盘删除：重启后仍存在
            page.toggle_forwarder_archive(yiwu_id)
            reloaded = _fresh_settings(temp_context)
            assert any(item["id"] == yiwu_id for item in reloaded["forwarders"])
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# D 组：利润规则删除立即落盘
# ---------------------------------------------------------------------------


class TestProfitRuleDelete:
    @staticmethod
    def _select_rule(page, rule_id: str) -> None:
        for visible_row, source in enumerate(page.visible_rule_indices):
            if page.rules_data[source].get("id") == rule_id:
                page.rule_list.setCurrentRow(visible_row)
                return
        raise AssertionError(f"规则 {rule_id} 不在可见列表中")

    def test_delete_rule_persists_to_settings_json(self, qapp, temp_context, accept_all_dialogs):
        """第 19 项：永久删除后 settings.json 立即不再包含规则。"""
        page = SettingsPage(temp_context)
        try:
            assert page.rules_data, "默认应存在利润规则"
            target_id = str(page.rules_data[0].get("id"))
            self._select_rule(page, target_id)
            saved_signal = []
            page.forwardersSaved.connect(lambda: saved_signal.append(True))
            page.delete_current_rule()

            settings_on_disk = temp_context.settings_service.load()
            assert all(str(item.get("id")) != target_id for item in settings_on_disk["profit_rules"])
            assert saved_signal == [True], "删除规则必须触发主页面刷新信号"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_delete_rule_survives_settings_service_restart(self, qapp, temp_context, accept_all_dialogs):
        """第 20 项：新建 SettingsService 重新 load 后规则仍不存在（默认值不复活）。"""
        page = SettingsPage(temp_context)
        try:
            target_id = str(page.rules_data[0].get("id"))
            self._select_rule(page, target_id)
            page.delete_current_rule()

            reloaded = _fresh_settings(temp_context)
            assert all(str(item.get("id")) != target_id for item in reloaded["profit_rules"])
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_delete_selected_rule_reselects_or_clears(self, qapp, temp_context, accept_all_dialogs):
        """第 21 项：删除当前 selected rule 后 selected id 合法重选/清空。"""

        def _rule(rule_id: str, name: str) -> dict:
            return {
                "id": rule_id,
                "name": name,
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 10.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 1.0,
                "currency": "USD",
                "percent_base": None,
                "enabled": True,
                "archived": False,
                "description": "",
            }

        settings = temp_context.settings_service.load()
        settings["profit_rules"] = [_rule("rule_target", "待删规则"), _rule("rule_other", "保留规则")]
        settings["selected_profit_rule_id"] = "rule_target"
        temp_context.settings_service.save(settings)

        page = SettingsPage(temp_context)
        try:
            self._select_rule(page, "rule_target")
            page.delete_current_rule()
            settings_on_disk = temp_context.settings_service.load()
            assert settings_on_disk["selected_profit_rule_id"] == "rule_other"
            # 删掉仅剩规则 → selected 清空
            self._select_rule(page, "rule_other")
            page.delete_current_rule()
            settings_on_disk = temp_context.settings_service.load()
            assert settings_on_disk["profit_rules"] == []
            assert settings_on_disk["selected_profit_rule_id"] == ""
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_main_page_rule_combo_drops_deleted_rule(self, qapp, temp_context, accept_all_dialogs):
        """第 22 项：主页面规则列表刷新后不再显示已删除规则。"""
        page = SettingsPage(temp_context)
        calc_page = CalculationPage(temp_context)
        try:
            page.forwardersSaved.connect(calc_page.refresh_settings)
            target = page.rules_data[0]
            target_id = str(target.get("id"))
            target_name = str(target.get("name"))
            target["enabled"] = True
            target["archived"] = False
            self._select_rule(page, target_id)
            page.delete_current_rule()

            combo = calc_page.profit_binder.cmb_rule
            texts = [combo.itemText(index) for index in range(combo.count())]
            assert target_name not in texts
            ids = [combo.itemData(index) for index in range(combo.count())]
            assert target_id not in ids
        finally:
            calc_page.deleteLater()
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# B8：设置页 UI 级 API 删除
# ---------------------------------------------------------------------------


class TestApiDeleteFromSettingsPage:
    def test_delete_profile_via_settings_page(self, qapp, temp_context, monkeypatch):
        """第 8 项：创建 profile → 删除 → 当前下拉框不再显示且磁盘无残留。"""
        import profit_accounting_26.ui.pages.settings_page as spm

        monkeypatch.setattr(spm, "confirm_action", lambda *a, **k: True)
        store = temp_context.api_profile_store
        profile = ApiProfile.create(
            display_name="111",
            provider="OpenAI",
            api_url="https://api.example.test/v1/chat/completions",
            model_name="vision-model",
        )
        store.save_profile(profile, "secret-key")
        store.bind(VISUAL_AI, profile.profile_id)

        page = SettingsPage(temp_context)
        try:
            # 选中该配置后删除
            idx = page.api_profile_select.findData(profile.profile_id)
            assert idx >= 0, "新建的 profile 应出现在下拉框中"
            page.api_profile_select.setCurrentIndex(idx)
            page._delete_api_profile()

            # 下拉框不再显示
            ids = [
                page.api_profile_select.itemData(i)
                for i in range(page.api_profile_select.count())
            ]
            assert profile.profile_id not in ids
            # 磁盘文件与绑定无残留（重启验证交给 Store 级测试）
            fresh = ApiProfileStore(temp_context.paths.data_dir)
            assert all(
                item.get("profile_id") != profile.profile_id
                for item in fresh.load_public()["profiles"]
            )
            assert profile.profile_id not in fresh.load_keys()
            assert fresh.bound_profile(VISUAL_AI) is None
        finally:
            page.deleteLater()
            qapp.processEvents()

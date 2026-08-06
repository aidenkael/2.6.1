"""UI 合同测试（模块化拆分后版本）。

覆盖：
- .ui XML 可解析；
- objectName 无重复；
- 关键 objectName 在其所属文件中存在；
- 运行时能加载；
- 冻结状态验证。
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FORMS_DIR = Path(__file__).resolve().parents[2] / "src" / "profit_accounting_26" / "ui" / "forms"
PAGES_DIR = FORMS_DIR / "pages"


# ── helpers ──────────────────────────────────────────────────────────

def _collect_names(tree: ET.Element) -> set[str]:
    names = {w.get("name") for w in tree.iter("widget") if w.get("name")}
    names |= {l.get("name") for l in tree.iter("layout") if l.get("name")}
    return names


# ── 15.1 UI 文件 ─────────────────────────────────────────────────────

class TestUIFileContract:
    """.ui 文件可解析、objectName 无重复、关键 objectName 存在。"""

    @pytest.fixture(scope="class")
    def main_window_tree(self):
        return ET.parse(FORMS_DIR / "main_window.ui")

    @pytest.fixture(scope="class")
    def settings_page_tree(self):
        return ET.parse(FORMS_DIR / "settings_page.ui")

    @pytest.fixture(scope="class")
    def calculation_page_tree(self):
        return ET.parse(PAGES_DIR / "calculation_page.ui")

    def test_main_window_ui_parseable(self, main_window_tree):
        assert main_window_tree.getroot() is not None

    def test_calculation_page_ui_parseable(self, calculation_page_tree):
        assert calculation_page_tree.getroot() is not None

    def test_settings_page_ui_parseable(self, settings_page_tree):
        assert settings_page_tree.getroot() is not None

    def test_main_window_no_duplicate_objectnames(self, main_window_tree):
        names = _collect_names(main_window_tree)
        assert len(names) == len(set(names))

    def test_calculation_page_no_duplicate_objectnames(self, calculation_page_tree):
        names = _collect_names(calculation_page_tree)
        assert len(names) == len(set(names))

    def test_settings_page_no_duplicate_objectnames(self, settings_page_tree):
        names = _collect_names(settings_page_tree)
        assert len(names) == len(set(names))

    def test_main_window_key_objectnames_exist(self, main_window_tree):
        """main_window.ui 中只保留壳层 objectName。"""
        names = _collect_names(main_window_tree)
        required = [
            "btnNavImageSearch", "btnNavCalculation", "btnNavHistory",
            "btnNavImportExport", "btnNavCalibration", "btnNavSettings",
            "pageImageSearch", "pageCalculation", "pageHistory",
            "pageImportExport", "pageCalibration", "pageSettingsHost",
            "mainStack",
            "btnRefreshGreeting", "lblGreetingTitle", "lblGreetingSubtitle",
            "lblGreetingHi", "lblGreetingUserName",
            "lblDataDirectoryPath", "btnChangeDataDirectory",
            "spinExchangeRate", "btnRefreshExchangeRate", "lblExchangeRateUpdated",
            "lblSaveStatus",
        ]
        missing = [n for n in required if n not in names]
        assert not missing, f"main_window.ui 缺少 objectName: {missing}"

    def test_calculation_page_key_objectnames_exist(self, calculation_page_tree):
        """测算页模块 UI 中关键 objectName 全部存在。"""
        names = _collect_names(calculation_page_tree)
        required = [
            # 利润区
            "txtSheinPriceRmb", "txtSheinPriceUsd",
            "txtCalculatedCostRmb", "txtCalculatedCostUsd",
            "spinProfitRate",
            "txtNoActivityPriceRmb", "txtNoActivityPriceUsd",
            "txtNoActivityProfitRmb", "txtNoActivityProfitUsd",
            "spinPromotionReserve",
            "txtActivityPriceRmb", "txtActivityPriceUsd",
            "txtActivityProfitRmb", "txtActivityProfitUsd",
            "lblNoActivitySubsidyStatus", "lblActivitySubsidyStatus",
            "lblListPriceProfitRateTitle", "txtListPriceProfitRate",
            "cmbProfitRule", "lblProfitConclusion",
            # 图片
            "imageSlotsLayout", "btnDecreaseImageSlots", "lblImageSlotCount",
            "btnIncreaseImageSlots", "btnSaveImageLayout", "btnAiRecognize",
            # 包装
            "radioNormalPackage", "txtNormalReminder",
            "spinNormalLengthCm", "spinNormalWidthCm", "spinNormalHeightCm", "spinNormalWeightG",
            "radioConservativePackage", "txtConservativeMethod",
            "spinConservativeLengthCm", "spinConservativeWidthCm", "spinConservativeHeightCm", "spinConservativeWeightG",
            # 货代
            "forwarderCardsLayout",
            # 尾程
            "spinTailFreightUsd", "spinTailFreightRmb",
            # 系统成本
            "btnSystemCalculate",
            # 商品
            "spinProductCostRmb", "spinDomesticFreightRmb",
            "spinBareLengthCm", "spinBareWidthCm", "spinBareHeightCm", "spinBareWeightG",
            # 底部
            "txtProductLink", "btnSaveCurrentRecord", "btnClearAndNew",
        ]
        missing = [n for n in required if n not in names]
        assert not missing, f"calculation_page.ui 缺少 objectName: {missing}"

    def test_settings_page_key_objectnames_exist(self, settings_page_tree):
        """settings_page.ui 中关键 objectName 全部存在。"""
        names = _collect_names(settings_page_tree)
        required = [
            "txtDisplayName", "cmbLogLevel", "spinLogRetentionDays",
            "btnOpenLogDirectory", "btnSaveSettings", "btnDiscardSettings",
            "cmbApiProfileSelect", "btnAddApiConfig",
            "cmbVisionApiConfig", "cmbPartialEstimateApiConfig",
            "txtApiProfileName", "cmbApiProvider", "txtApiEndpoint", "txtApiModel", "txtApiKey",
            "btnSaveApiProfile", "btnShowApiKey1", "btnTestApi1", "btnDeleteApi1",
            "tableForwarders", "btnAddFreightForwarder", "btnSaveForwarders",
            "listProfitRules", "btnAddProfitRule", "btnSaveProfitRule",
            "btnDisableProfitRule", "btnArchiveProfitRule", "btnDeleteProfitRule",
        ]
        missing = [n for n in required if n not in names]
        assert not missing, f"settings_page.ui 缺少 objectName: {missing}"

    def test_ui_sha256_matches_contract(self):
        """.ui SHA 与输入文件一致。"""
        expected = {
            "main_window.ui": "551adb6dfbd323825d758e70f4ba3301e680b63bd5a2cecb02c7628e84688b13",
        }
        for file_rel, sha in expected.items():
            fpath = FORMS_DIR / file_rel
            data = fpath.read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            assert actual == sha, f"{file_rel} SHA 不匹配: {actual} != {sha}"


# ── 15.2 运行时加载与冻结状态 ────────────────────────────────────────

def _load_page(name: str):
    from profit_accounting_26.ui.ui_loader import load_page_module
    return load_page_module(name)


class TestRuntimeLoading:
    """运行时加载 .ui 并验证冻结状态。"""

    @pytest.fixture(scope="class")
    def main_window_ui(self, qapp):
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
        from profit_accounting_26.ui.ui_loader import load_main_window
        return load_main_window()

    @pytest.fixture(scope="class")
    def calc_page_ui(self, qapp):
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
        return _load_page("calculation_page.ui")

    def test_main_window_loads_as_qmainwindow(self, main_window_ui):
        from PySide6.QtWidgets import QMainWindow
        assert isinstance(main_window_ui, QMainWindow)

    def test_main_stack_has_six_pages(self, main_window_ui):
        from PySide6.QtWidgets import QStackedWidget
        stack = main_window_ui.findChild(QStackedWidget, "mainStack")
        assert stack is not None
        assert stack.count() == 6

    def test_calculation_page_has_key_fields(self, calc_page_ui):
        """验算页模块独立加载后关键字段可访问。"""
        from PySide6.QtWidgets import QDoubleSpinBox, QLabel
        fields = ["txtSheinPriceRmb", "txtCalculatedCostRmb", "spinProfitRate",
                   "txtNoActivityPriceUsd", "txtActivityProfitRmb"]
        for name in fields:
            w = calc_page_ui.findChild(QDoubleSpinBox, name)
            assert w is not None, f"利润区字段 {name} 不可访问"
        label = calc_page_ui.findChild(QLabel, "txtListPriceProfitRate")
        assert label is not None


class TestFrozenStates:
    """冻结状态验证（契约 §7）。"""

    @pytest.fixture
    def binder(self, qapp):
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
        from PySide6.QtWidgets import QWidget
        from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder
        self._ui = _load_page("calculation_page.ui")
        page = self._ui

        class MockContext:
            class _ss:
                def load(self): return {"exchange_rate_usd_to_rmb": 7.2}
            settings_service = _ss()

        return CalculationBinder(page, MockContext())

    def test_shein_rmb_frozen(self, binder): assert binder.txt_shein_rmb.isReadOnly()
    def test_shein_usd_editable(self, binder): assert not binder.txt_shein_usd.isReadOnly()
    def test_cost_rmb_editable(self, binder): assert not binder.txt_cost_rmb.isReadOnly()
    def test_cost_usd_frozen(self, binder): assert binder.txt_cost_usd.isReadOnly()
    def test_na_price_usd_editable(self, binder): assert not binder.txt_na_price_usd.isReadOnly()
    def test_na_price_rmb_frozen(self, binder): assert binder.txt_na_price_rmb.isReadOnly()
    def test_na_profit_rmb_editable(self, binder): assert not binder.txt_na_profit_rmb.isReadOnly()
    def test_na_profit_usd_frozen(self, binder): assert binder.txt_na_profit_usd.isReadOnly()
    def test_act_price_rmb_frozen(self, binder): assert binder.txt_act_price_rmb.isReadOnly()
    def test_act_price_usd_frozen(self, binder): assert binder.txt_act_price_usd.isReadOnly()
    def test_act_profit_rmb_editable(self, binder): assert not binder.txt_act_profit_rmb.isReadOnly()
    def test_act_profit_usd_frozen(self, binder): assert binder.txt_act_profit_usd.isReadOnly()

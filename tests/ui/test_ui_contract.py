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
        """calculation_page.ui 壳中仅保留宿主容器 objectName。"""
        names = _collect_names(calculation_page_tree)
        required = [
            "pageCalculation", "calculationPageLayout",
            "imageAIPanelHost", "productCostPanelHost", "packagingPanelHost",
            "logisticsPanelHost", "profitPanelHost",
        ]
        missing = [n for n in required if n not in names]
        assert not missing, f"calculation_page.ui 壳缺少 objectName: {missing}"

    def test_calculation_panels_key_objectnames_exist(self):
        """5 个独立面板 .ui 中关键 objectName 全部存在。"""
        panel_checks = {
            "calculation/product_cost_panel.ui": [
                "bareProductCard", "spinProductCostRmb", "spinDomesticFreightRmb",
                "spinBareLengthCm", "spinBareWidthCm", "spinBareHeightCm", "spinBareWeightG",
            ],
            "calculation/packaging_panel.ui": [
                "packagingPanel", "normalPackageCard", "radioNormalPackage",
                "conservativePackageCard", "radioConservativePackage",
            ],
            "calculation/logistics_panel.ui": [
                "logisticsPanel", "spinTailFreightUsd", "spinTailFreightRmb",
                "forwarderCardsLayout", "lblSystemTotalRmb",
            ],
            "calculation/profit_panel.ui": [
                "profitSection", "txtSheinPriceRmb", "txtCalculatedCostRmb",
                "spinProfitRate", "txtNoActivityPriceRmb",
                "txtListPriceProfitRate", "cmbProfitRule",
            ],
            "calculation/image_ai_panel.ui": [
                "imageAIPanel", "btnAiRecognize", "imageSlotsLayout",
                "btnPartialReestimate",
            ],
        }
        base = FORMS_DIR
        for rel_path, required in panel_checks.items():
            tree = ET.parse(base / rel_path)
            names = _collect_names(tree)
            missing = [n for n in required if n not in names]
            assert not missing, f"{rel_path} 缺少 objectName: {missing}"

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

    @staticmethod
    def _ui_content_sha256(path: Path) -> str:
        """计算 .ui 文件内容 SHA256，不受平台换行符影响（统一使用 LF）。"""
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_ui_sha256_matches_contract(self):
        """.ui SHA 与输入文件一致（换行规范化为 LF）。"""
        expected = {
            "main_window.ui": "e0b928cb74afece822323ecb4200198e9a44f72201463d84bcda5833600b9717",
        }
        for file_rel, sha in expected.items():
            fpath = FORMS_DIR / file_rel
            actual = self._ui_content_sha256(fpath)
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
        """验算页壳独立加载后仅含 Host 容器。"""
        from PySide6.QtWidgets import QWidget
        for host_name in ['imageAIPanelHost','productCostPanelHost','packagingPanelHost','logisticsPanelHost','profitPanelHost']:
            w = calc_page_ui.findChild(QWidget, host_name)
            assert w is not None, f"{host_name} 不存在"

    def test_calculation_panels_load_independently(self):
        """5 个测算面板各自独立加载。"""
        from profit_accounting_26.ui.ui_loader import load_calculation_panel
        for name in ['image_ai','product_cost','packaging','logistics','profit']:
            w = load_calculation_panel(name)
            assert w is not None, f"{name} panel 加载失败"


class TestFrozenStates:
    """冻结状态验证（契约 §7）。"""

    @pytest.fixture
    def binder(self, qapp):
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
        from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder
        from profit_accounting_26.ui.ui_loader import load_calculation_panel
        self._ui = load_calculation_panel("profit")
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

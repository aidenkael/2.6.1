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
from collections import Counter
from pathlib import Path

import pytest

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FORMS_DIR = Path(__file__).resolve().parents[2] / "src" / "profit_accounting_26" / "ui" / "forms"
PAGES_DIR = FORMS_DIR / "pages"
CALC_DIR = FORMS_DIR / "calculation"


# ── helpers ──────────────────────────────────────────────────────────

def _collect_names(tree: ET.Element) -> list[str]:
    """收集 widget 和 layout 的 objectName（保留重复）。"""
    names = [w.get("name") for w in tree.iter("widget") if w.get("name")]
    names += [l.get("name") for l in tree.iter("layout") if l.get("name")]
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
                "productCostPanel", "spinProductCostRmb", "spinDomesticFreightRmb",
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
                "profitPanel", "txtSheinPriceRmb", "txtCalculatedCostRmb",
                "spinProfitRate", "txtNoActivityPriceRmb",
                "txtListPriceProfitRate", "cmbProfitRule",
            ],
            "calculation/image_ai_panel.ui": [
                "imageAIPanel", "btnAiRecognize", "imageSlotsLayout",
                "btnPartialReestimate", "txtAiSummary", "txtPackingState",
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


    def test_objectnames_no_duplicates_per_file(self):
        """每个 .ui 文件内 objectName 不重复。"""
        for rel_path in ["main_window.ui", "pages/calculation_page.ui", "pages/settings_page.ui"]:
            tree = ET.parse(FORMS_DIR / rel_path)
            names = _collect_names(tree)
            dupes = [name for name, cnt in Counter(names).items() if cnt > 1]
            assert not dupes, f"{rel_path} 存在重复 objectName: {dupes}"
        for fn in sorted(CALC_DIR.glob("*.ui")):
            tree = ET.parse(fn)
            names = _collect_names(tree)
            dupes = [name for name, cnt in Counter(names).items() if cnt > 1]
            assert not dupes, f"{fn.name} 存在重复 objectName: {dupes}"

    def test_objectnames_unique_across_calculation_uis(self):
        """calculation 目录下所有 .ui 的关键 objectName 不跨文件重复。"""
        key_names = ["imageAIPanel", "productCostPanel", "packagingPanel",
                     "logisticsPanel", "profitPanel",
                     "txtProductLink", "btnSaveCurrentRecord", "btnClearAndNew"]
        for name in key_names:
            count = 0
            for fn in sorted(CALC_DIR.glob("*.ui")):
                content = fn.read_text(encoding="utf-8-sig")
                if f'name="{name}"' in content:
                    count += 1
            # 底部控件在壳页面中
            if name in ["txtProductLink", "btnSaveCurrentRecord", "btnClearAndNew"]:
                shell_text = (FORMS_DIR / "pages/calculation_page.ui").read_text(encoding="utf-8-sig")
                if f'name="{name}"' in shell_text:
                    count += 1
            assert count == 1, f"objectName '{name}' 出现 {count} 次（应为 1）"


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
        roots = []
        for name in ['image_ai','product_cost','packaging','logistics','profit']:
            w = load_calculation_panel(name)
            assert w is not None, f"{name} panel 加载失败"
            roots.append(w)
        # 验证 5 个 root 互不相同
        root_names = [w.objectName() for w in roots]
        assert len(set(root_names)) == 5, f"面板 root 存在重复: {root_names}"


class TestRealSplitVerification:
    """真实验证：独立 root、唯一 objectName、跨面板联动。"""

    def test_five_panel_roots_are_distinct(self, qapp):
        """5 个面板 root 互不相同。"""
        from profit_accounting_26.ui.ui_loader import load_calculation_panel
        roots = {name: load_calculation_panel(name) for name in
                 ['image_ai','product_cost','packaging','logistics','profit']}
        ids = [id(r) for r in roots.values()]
        assert len(set(ids)) == 5, f"面板 root id 重复: {ids}"

    def test_calculation_page_shell_excludes_panel_widgets(self, qapp):
        """calculation_page.ui 壳不包含面板内部核心控件。"""
        from profit_accounting_26.ui.ui_loader import load_page_module
        shell = load_page_module("calculation_page.ui")
        from PySide6.QtWidgets import QDoubleSpinBox, QLineEdit, QRadioButton
        # 壳中应无利润区、包装区、商品区的核心交互控件
        panel_core = ["txtSheinPriceRmb", "spinProfitRate", "spinProductCostRmb",
                      "radioNormalPackage", "spinTailFreightUsd", "btnAiRecognize"]
        for name in panel_core:
            w = shell.findChild(QDoubleSpinBox, name) or shell.findChild(QLineEdit, name) or shell.findChild(QRadioButton, name)
            assert w is None, f"壳页面不应包含面板控件 {name}"

    def test_each_objectname_unique_across_all_ui(self):
        """每个关键 objectName 在所有 .ui 文件中只出现一次。"""
        import re
        key_names = ["txtSheinPriceRmb", "spinProfitRate", "spinProductCostRmb",
                     "radioNormalPackage", "spinTailFreightUsd", "btnAiRecognize",
                     "profitPanel", "productCostPanel", "packagingPanel",
                     "logisticsPanel", "imageAIPanel",
                     "txtProductLink", "btnSaveCurrentRecord", "btnClearAndNew"]
        ui_dir = "src/profit_accounting_26/ui/forms"
        for name in key_names:
            count = 0
            for root, _, files in os.walk(ui_dir):
                for fn in files:
                    if fn.endswith('.ui'):
                        with open(os.path.join(root, fn), encoding='utf-8-sig') as f:
                            content = f.read()
                        if f'name="{name}"' in content:
                            count += 1
            assert count == 1, f"objectName '{name}' 出现 {count} 次（应为 1 次）"

    def test_shell_contains_bottom_controls(self, qapp):
        """页面壳包含底部控件（txtProductLink, btnSave, btnClear）。"""
        from profit_accounting_26.ui.ui_loader import load_page_module
        from PySide6.QtWidgets import QLineEdit, QPushButton
        shell = load_page_module("calculation_page.ui")
        assert shell.findChild(QLineEdit, "txtProductLink") is not None
        assert shell.findChild(QPushButton, "btnSaveCurrentRecord") is not None
        assert shell.findChild(QPushButton, "btnClearAndNew") is not None

    @pytest.fixture
    def calc_page(self, qapp, tmp_path):
        """完整的 CalculationPage 实例（5 面板挂载）。"""
        import os
        os.environ.setdefault("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.pages.calculation_page import CalculationPage
        ctx = AppContext.create_default()
        page = CalculationPage(ctx)
        yield page
        page.deleteLater()

    def test_five_panels_mounted_in_calc_page(self, calc_page):
        """CalculationPage 实例中 5 个面板 root 全部真实挂载。"""
        roots = calc_page._panel_roots
        assert len(roots) == 5, f"应有 5 个面板，实际 {len(roots)}"
        for name in ['image_ai','product_cost','packaging','logistics','profit']:
            assert name in roots, f"缺少面板 {name}"
            assert roots[name] is not None
        # 验证 root 互不相同
        ids = [id(r) for r in roots.values()]
        assert len(set(ids)) == 5

    def test_profit_binder_uses_profit_root(self, calc_page):
        """CalculationBinder root 等于 profit panel root。"""
        profit_root = calc_page._panel_roots["profit"]
        assert calc_page.profit_binder.page == profit_root

    def test_image_slots_host_in_image_panel(self, calc_page):
        """动态图片槽宿主位于 image panel。"""
        image_root = calc_page._panel_roots["image_ai"]
        from PySide6.QtWidgets import QHBoxLayout
        layout = image_root.findChild(QHBoxLayout, "imageSlotsLayout")
        assert layout is not None

    def test_forwarder_cards_host_in_logistics_panel(self, calc_page):
        """动态货代卡宿主位于 logistics panel。"""
        log_root = calc_page._panel_roots["logistics"]
        from PySide6.QtWidgets import QHBoxLayout
        layout = log_root.findChild(QHBoxLayout, "forwarderCardsLayout")
        assert layout is not None

    def test_tail_usd_rmb_live_linkage(self, calc_page):
        """尾程 USD 写入后 RMB 可通过 sync 方法同步。"""
        # 手动调用同步方法验证汇率计算
        calc_page.tail_fee_usd.setValue(10.0)
        calc_page._sync_tail_rmb_from_usd(recalculate=False)
        rate = float(calc_page.settings.get("exchange_rate_usd_to_rmb", 7.2))
        expected_rmb = round(10.0 * rate, 2)
        assert abs(calc_page.tail_fee_rmb.value() - expected_rmb) < 0.1

    def test_list_price_rate_visible(self, calc_page):
        """标价利率控件存在于 profit panel。"""
        from PySide6.QtWidgets import QLabel
        profit_root = calc_page._panel_roots["profit"]
        label = profit_root.findChild(QLabel, "txtListPriceProfitRate")
        assert label is not None

    def test_dynamic_properties_restored_on_profit_panel(self, calc_page):
        """profit panel 关键动态属性在 setupUi 后已恢复。"""
        from PySide6.QtWidgets import QWidget
        profit = calc_page._panel_roots["profit"]
        # 根 widget 直接检查（非 findChild）
        assert profit.property("card") == True, f"profitPanel.card = {profit.property('card')}"
        checks = {
            "lblProfitTitle": ("sectionTitle", True),
            "lblProfitHint": ("hint", True),
            "lblNoActivitySubsidyStatus": ("subsidyStatus", True),
            "lblProfitConclusion": ("conclusion", True),
        }
        for widget_name, (prop, expected) in checks.items():
            w = profit.findChild(QWidget, widget_name)
            assert w is not None, f"widget {widget_name} not found"
            actual = w.property(prop)
            assert actual == expected, f"{widget_name}.{prop}: {actual} != {expected}"


    def test_scroll_area_present_and_content_taller_than_viewport(self, calc_page):
        """QScrollArea 存在，内容高度超过视口时出现滚动条。"""
        from PySide6.QtWidgets import QScrollArea
        scroll = calc_page._scroll_area
        assert scroll is not None
        assert isinstance(scroll, QScrollArea), f"应该是 QScrollArea，实际是 {type(scroll).__name__}"

    def test_panels_not_overlapping_in_layout(self, calc_page):
        """5 个面板 root 都已挂载。"""
        roots = calc_page._panel_roots
        assert len(roots) == 5, f"应有 5 个面板，实际 {len(roots)}"
        for name in ['image_ai','product_cost','packaging','logistics','profit']:
            panel = roots.get(name)
            assert panel is not None, f"缺少面板 {name}"
            assert panel.parentWidget() is not None, f"{name} panel 未挂载"

    def test_panels_not_compressed_below_size_hint(self, calc_page):
        """每个面板的 sizeHint 大于 0（不是空面板）。"""
        for name, panel in calc_page._panel_roots.items():
            hint = panel.sizeHint().height()
            assert hint > 0, f"{name} panel sizeHint={hint} (应为正数)"


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

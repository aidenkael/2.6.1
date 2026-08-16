"""UI 合同测试。

覆盖契约 §15.1 和 §15.2：
- 两份 .ui XML 可解析
- objectName 无重复
- 关键 objectName 全部存在
- 运行时能加载
- 主窗口和设置页不会重复嵌套
- 冻结状态验证
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


FORMS_DIR = Path(__file__).resolve().parents[2] / "src" / "profit_accounting_26" / "ui" / "forms"


# ---------------------------------------------------------------------------
# 15.1 UI 文件
# ---------------------------------------------------------------------------

class TestUIFileContract:
    """.ui 文件可解析、objectName 无重复、关键 objectName 存在。"""

    @pytest.fixture(scope="class")
    def main_window_tree(self):
        return ET.parse(FORMS_DIR / "main_window.ui")

    @pytest.fixture(scope="class")
    def settings_page_tree(self):
        return ET.parse(FORMS_DIR / "settings_page.ui")

    def test_main_window_ui_parseable(self, main_window_tree):
        """main_window.ui XML 可解析。"""
        assert main_window_tree.getroot() is not None

    def test_settings_page_ui_parseable(self, settings_page_tree):
        """settings_page.ui XML 可解析。"""
        assert settings_page_tree.getroot() is not None

    def test_main_window_no_duplicate_objectnames(self, main_window_tree):
        """main_window.ui 中 objectName 无重复。"""
        names = [
            w.get("name")
            for w in main_window_tree.iter("widget")
            if w.get("name")
        ] + [
            l.get("name")
            for l in main_window_tree.iter("layout")
            if l.get("name")
        ]
        assert len(names) == len(set(names)), f"重复的 objectName: {set(names) - set() }"

    def test_settings_page_no_duplicate_objectnames(self, settings_page_tree):
        """settings_page.ui 中 objectName 无重复。"""
        names = [
            w.get("name")
            for w in settings_page_tree.iter("widget")
            if w.get("name")
        ] + [
            l.get("name")
            for l in settings_page_tree.iter("layout")
            if l.get("name")
        ]
        assert len(names) == len(set(names))

    def test_main_window_key_objectnames_exist(self, main_window_tree):
        """main_window.ui 中关键 objectName 全部存在（含 widget 和 layout）。"""
        names = {w.get("name") for w in main_window_tree.iter("widget") if w.get("name")}
        names |= {l.get("name") for l in main_window_tree.iter("layout") if l.get("name")}
        required = [
            # 导航（Stage 4：精简为 3 项）
            "btnNavCalculation", "btnNavHistory", "btnNavSettings",
            # 页面（Stage 4：以图搜图/数据导入导出/模型校准反馈已删除）
            "pageCalculation", "pageHistory", "pageSettingsHost",
            "mainStack",
            # 问候
            "btnRefreshGreeting", "lblGreetingTitle", "lblGreetingSubtitle",
            "lblGreetingHi", "lblGreetingUserName",
            # 数据目录和汇率
            "lblDataDirectoryPath", "btnChangeDataDirectory",
            "spinExchangeRate", "btnRefreshExchangeRate", "lblExchangeRateUpdated",
            # 保存状态
            "lblSaveStatus",
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
        ]
        missing = [n for n in required if n not in names]
        assert not missing, f"main_window.ui 缺少 objectName: {missing}"

    def test_settings_page_key_objectnames_exist(self, settings_page_tree):
        """settings_page.ui 中关键 objectName 全部存在。"""
        names = {w.get("name") for w in settings_page_tree.iter("widget") if w.get("name")}
        required = [
            "txtDisplayName", "cmbLogLevel", "spinLogRetentionDays",
            "btnOpenLogDirectory", "btnSaveSettings", "btnDiscardSettings",
            "cmbApiProfileSelect", "btnAddApiConfig",
            "cmbVisionApiConfig", "cmbPartialEstimateApiConfig", "cmbImageRiskApiConfig",
            "txtApiProfileName", "cmbApiProvider", "txtApiEndpoint", "txtApiModel", "txtApiKey",
            "btnSaveApiProfile", "btnShowApiKey1", "btnTestApi1", "btnDeleteApi1",
            "tableForwarders", "btnAddFreightForwarder", "btnSaveForwarders",
            "listProfitRules", "btnAddProfitRule", "btnSaveProfitRule",
            "btnDisableProfitRule", "btnArchiveProfitRule", "btnDeleteProfitRule",
            # 物流校准规则（Stage 4：校准包版本管理迁入 Settings）
            "calibrationSection", "tableCalibrationPackages",
            "btnImportCalibrationPackage", "btnActivateCalibrationPackage",
            "btnDeleteCalibrationPackage", "lblCalibrationActiveStatus",
        ]
        missing = [n for n in required if n not in names]
        assert not missing, f"settings_page.ui 缺少 objectName: {missing}"

    def test_ui_sha256_matches_contract(self):
        """.ui SHA 与输入文件一致（跨平台换行符规范化）。"""
        expected = {
            # Stage 4：导航精简 + 校准管理迁入 Settings 后的新契约 SHA
            # Product Collector 集成后 main_window.ui 新增导航按钮和页面占位
            # 2.6.1 第二轮：导航交换（商品采集在前）+ 新品测算演示数字清零
            # PR #39：品牌更名为 UU护航 3.0.1，风险标签优化，未保存位置调整
            # PR #39 收口：导航按钮 text-align 改为 center，图标 SVG 替换为黑色 U
            # 风险标签根因修复 + 导航 SVG 图标两列对齐
            # PR #39 最终：底部商品链接布局调整（取消 400px 限制）
            "main_window.ui": "9dfd78b558fc7d1dcb85bc8a79c94e46e95994483f76ddc6f8fd7f03f33c41a9",
            "settings_page.ui": "e7ff5f8b380066a097462f094f1e25e31c81d1c1efc857c3cb35eafa30bdd614",
        }
        for name, sha in expected.items():
            data = (FORMS_DIR / name).read_bytes()
            # 规范化换行符：CRLF -> LF, CR -> LF，确保跨平台 SHA 一致
            normalized = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
            actual = hashlib.sha256(normalized).hexdigest()
            assert actual == sha, f"{name} SHA 不匹配: {actual} != {sha}"


# ---------------------------------------------------------------------------
# 15.2 运行时加载与冻结状态
# ---------------------------------------------------------------------------

class TestRuntimeLoading:
    """运行时加载 .ui 并验证冻结状态。"""

    @pytest.fixture(scope="class")
    def qt_app(self, qapp):
        # 使用 tests/conftest.py 的会话级 qapp；不在测试内创建临时 QApplication
        import os
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
        return qapp

    @pytest.fixture(scope="class")
    def main_window_ui(self, qt_app):
        from profit_accounting_26.ui.ui_loader import load_main_window
        return load_main_window()

    def test_main_window_loads_as_qmainwindow(self, main_window_ui):
        from PySide6.QtWidgets import QMainWindow
        assert isinstance(main_window_ui, QMainWindow)

    def test_main_stack_has_three_pages(self, main_window_ui):
        from PySide6.QtWidgets import QStackedWidget
        stack = main_window_ui.findChild(QStackedWidget, "mainStack")
        assert stack is not None
        # Product Collector 集成后为 4 页：测算 / 采集 / 历史 / 设置
        assert stack.count() == 4

    def test_profit_fields_accessible(self, main_window_ui):
        from PySide6.QtWidgets import QDoubleSpinBox
        for name in ["txtSheinPriceRmb", "txtCalculatedCostRmb", "spinProfitRate",
                      "txtNoActivityPriceUsd", "txtActivityProfitRmb"]:
            w = main_window_ui.findChild(QDoubleSpinBox, name)
            assert w is not None, f"利润区字段 {name} 不可访问"


class TestFrozenStates:
    """冻结状态验证（契约 §7）。"""

    @pytest.fixture  # function-scoped: 每个 test 独立加载，避免 C++ 对象被回收
    def binder(self, qapp):
        # 使用 tests/conftest.py 的会话级 qapp；不在测试内创建临时 QApplication
        import os
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
        from PySide6.QtWidgets import QWidget
        from profit_accounting_26.ui.ui_loader import load_main_window
        from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder
        # 保留 ui 引用防止垃圾回收
        self._ui = load_main_window()
        page = self._ui.findChild(QWidget, "pageCalculation")

        class MockContext:
            class _ss:
                def load(self): return {"exchange_rate_usd_to_rmb": 7.2}
            settings_service = _ss()

        return CalculationBinder(page, MockContext())

    def test_shein_rmb_frozen(self, binder):
        """SHEIN 核价 RMB 冻结。"""
        assert binder.txt_shein_rmb.isReadOnly()

    def test_shein_usd_editable(self, binder):
        """SHEIN 核价 USD 可编辑。"""
        assert not binder.txt_shein_usd.isReadOnly()

    def test_cost_rmb_editable(self, binder):
        """计算总成本 RMB 可编辑。"""
        assert not binder.txt_cost_rmb.isReadOnly()

    def test_cost_usd_frozen(self, binder):
        """计算总成本 USD 冻结。"""
        assert binder.txt_cost_usd.isReadOnly()

    def test_na_price_usd_editable(self, binder):
        """无活动售价 USD 可编辑。"""
        assert not binder.txt_na_price_usd.isReadOnly()

    def test_na_price_rmb_frozen(self, binder):
        """无活动售价 RMB 冻结。"""
        assert binder.txt_na_price_rmb.isReadOnly()

    def test_na_profit_rmb_editable(self, binder):
        """无活动利润 RMB 可编辑。"""
        assert not binder.txt_na_profit_rmb.isReadOnly()

    def test_na_profit_usd_frozen(self, binder):
        """无活动利润 USD 冻结。"""
        assert binder.txt_na_profit_usd.isReadOnly()

    def test_act_price_rmb_frozen(self, binder):
        """活动后售价 RMB 冻结。"""
        assert binder.txt_act_price_rmb.isReadOnly()

    def test_act_price_usd_frozen(self, binder):
        """活动后售价 USD 冻结。"""
        assert binder.txt_act_price_usd.isReadOnly()

    def test_act_profit_rmb_editable(self, binder):
        """活动后利润 RMB 可编辑。"""
        assert not binder.txt_act_profit_rmb.isReadOnly()

    def test_act_profit_usd_frozen(self, binder):
        """活动后利润 USD 冻结。"""
        assert binder.txt_act_profit_usd.isReadOnly()

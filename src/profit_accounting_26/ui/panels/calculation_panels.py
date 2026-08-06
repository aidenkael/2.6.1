"""新产品测算页 5 个面板包装器。

每个面板持有其负责区域的控件引用，提供独立操作接口。
跨面板通信通过 CalculationPage 协调方法完成，面板间不直接 findChild 查询对方控件。

用法:
    from profit_accounting_26.ui.panels.calculation_panels import (
        ImageAIPanel, ProductCostPanel, PackagingPanel, LogisticsPanel, ProfitPanel
    )
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QTextEdit, QWidget,
)


class ImageAIPanel(QObject):
    """图片区域、AI 识图、商品/包装摘要、局部重估。"""

    def __init__(self, page_root: QWidget, parent: QObject | None = None):
        super().__init__(parent)
        f = page_root.findChild
        self.btn_ai: QPushButton = f(QPushButton, "btnAiRecognize")
        self.btn_partial: QPushButton = f(QPushButton, "btnPartialReestimate")
        self.slots_layout: QHBoxLayout = f(QHBoxLayout, "imageSlotsLayout")
        self.btn_decr: QPushButton = f(QPushButton, "btnDecreaseImageSlots")
        self.btn_incr: QPushButton = f(QPushButton, "btnIncreaseImageSlots")
        self.lbl_count: QLabel = f(QLabel, "lblImageSlotCount")
        self.btn_save_layout: QPushButton = f(QPushButton, "btnSaveImageLayout")


class ProductCostPanel(QObject):
    """商品成本、国内运费、裸尺寸、裸重。"""

    def __init__(self, page_root: QWidget, parent: QObject | None = None):
        super().__init__(parent)
        f = page_root.findChild
        self.product_cost: QDoubleSpinBox = f(QDoubleSpinBox, "spinProductCostRmb")
        self.domestic_shipping: QDoubleSpinBox = f(QDoubleSpinBox, "spinDomesticFreightRmb")
        self.bare_length: QDoubleSpinBox = f(QDoubleSpinBox, "spinBareLengthCm")
        self.bare_width: QDoubleSpinBox = f(QDoubleSpinBox, "spinBareWidthCm")
        self.bare_height: QDoubleSpinBox = f(QDoubleSpinBox, "spinBareHeightCm")
        self.bare_weight: QDoubleSpinBox = f(QDoubleSpinBox, "spinBareWeightG")


class PackagingPanel(QObject):
    """正常档 / 保守档包装。"""

    def __init__(self, page_root: QWidget, parent: QObject | None = None):
        super().__init__(parent)
        f = page_root.findChild
        self.normal_fields: dict[str, Any] = {
            "card": f(QWidget, "normalPackageCard"),
            "radio": f(QRadioButton, "radioNormalPackage"),
            "method": f(QTextEdit, "txtNormalReminder"),
            "length": f(QDoubleSpinBox, "spinNormalLengthCm"),
            "width": f(QDoubleSpinBox, "spinNormalWidthCm"),
            "height": f(QDoubleSpinBox, "spinNormalHeightCm"),
            "weight": f(QDoubleSpinBox, "spinNormalWeightG"),
        }
        self.conservative_fields: dict[str, Any] = {
            "card": f(QWidget, "conservativePackageCard"),
            "radio": f(QRadioButton, "radioConservativePackage"),
            "method": f(QLineEdit, "txtConservativeMethod"),
            "length": f(QDoubleSpinBox, "spinConservativeLengthCm"),
            "width": f(QDoubleSpinBox, "spinConservativeWidthCm"),
            "height": f(QDoubleSpinBox, "spinConservativeHeightCm"),
            "weight": f(QDoubleSpinBox, "spinConservativeWeightG"),
        }


class LogisticsPanel(QObject):
    """尾程费用、动态货代卡宿主、系统总成本。"""

    def __init__(self, page_root: QWidget, parent: QObject | None = None):
        super().__init__(parent)
        f = page_root.findChild
        self.tail_fee_usd: QDoubleSpinBox = f(QDoubleSpinBox, "spinTailFreightUsd")
        self.tail_fee_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "spinTailFreightRmb")
        self.forwarder_cards_layout: QHBoxLayout = f(QHBoxLayout, "forwarderCardsLayout")
        self.btn_calculate: QPushButton = f(QPushButton, "btnSystemCalculate")
        self.system_rows: dict[str, QLabel] = {
            "package": f(QLabel, "lblSystemCostValue0"),
            "forwarder": f(QLabel, "lblSystemCostValue1"),
            "actual": f(QLabel, "lblSystemCostValue2"),
            "volume": f(QLabel, "lblSystemCostValue3"),
            "chargeable": f(QLabel, "lblSystemCostValue4"),
            "logistics": f(QLabel, "lblSystemCostValue5"),
            "tail": f(QLabel, "lblSystemCostValue6"),
        }
        self.system_total: QLabel = f(QLabel, "lblSystemTotalRmb")
        self.system_total_usd: QLabel = f(QLabel, "lblSystemTotalUsd")


class ProfitPanel(QObject):
    """利润区 — 委托 CalculationBinder 管理（由 CalculationPage 注入）。"""

    def __init__(self, page_root: QWidget, parent: QObject | None = None):
        super().__init__(parent)
        f = page_root.findChild
        self.product_link: QLineEdit = f(QLineEdit, "txtProductLink")
        self.btn_save: QPushButton = f(QPushButton, "btnSaveCurrentRecord")
        self.btn_clear: QPushButton = f(QPushButton, "btnClearAndNew")
        self.binder = None  # 由 CalculationPage 在 init 中注入已有的 profit_binder

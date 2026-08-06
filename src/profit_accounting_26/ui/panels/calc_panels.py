"""计算面板 widget —— pyside6-uic 生成 UI，setupUi 构建控件树。

每个面板拥有独立的 C++ widget 树，不再依赖 QUiLoader 运行时加载。
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QWidget, QVBoxLayout

from profit_accounting_26.ui.generated.image_ai_panel_view import Ui_ImageAIPanel
from profit_accounting_26.ui.generated.product_cost_panel_view import Ui_ProductCostPanel
from profit_accounting_26.ui.generated.packaging_panel_view import Ui_PackagingPanel
from profit_accounting_26.ui.generated.logistics_panel_view import Ui_LogisticsPanel
from profit_accounting_26.ui.generated.profit_panel_view import Ui_ProfitPanel


class ImageAIPanelWidget(QWidget):
    """图片+AI 面板。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_ImageAIPanel()
        self.ui.setupUi(self)


class ProductCostPanelWidget(QFrame):
    """商品成本 + 裸尺寸面板。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_ProductCostPanel()
        self.ui.setupUi(self)


class PackagingPanelWidget(QWidget):
    """包装面板（正常档 + 保守档）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PackagingPanel()
        self.ui.setupUi(self)


class LogisticsPanelWidget(QWidget):
    """物流面板（尾程 + 货代卡 + 系统成本）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_LogisticsPanel()
        self.ui.setupUi(self)


class ProfitPanelWidget(QFrame):
    """利润面板（双场景 + 标价利率 + 利润规则）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_ProfitPanel()
        self.ui.setupUi(self)

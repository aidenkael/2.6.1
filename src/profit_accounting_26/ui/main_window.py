from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QWidget

from profit_accounting_26.application import AppContext
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.binders.main_window_binder import MainWindowBinder
from profit_accounting_26.ui.pages import (
    CalculationPage,
    CalibrationPage,
    HistoryPage,
    ImageSearchPage,
    ImportExportPage,
    SettingsPage,
)
from profit_accounting_26.ui.theme import APP_STYLE
# 保留 NAV_ITEMS 供 app.py 和测试导入
NAV_ITEMS = [
    "以图搜图",
    "新商品测算",
    "历史记录管理",
    "数据导入导出",
    "模型校准反馈",
    "设置",
]
SUBTITLES = {
    "以图搜图": "导入图片并复用已登录的Edge与1688插件",
    "新商品测算": "图片识别、物流估算与利润测算在同一页面完成",
    "历史记录管理": "打开记录、查看快照并补充实际反馈",
    "数据导入导出": "受控导入、导出记录和校准反馈",
    "模型校准反馈": "管理校准包、版本与回滚",
    "设置": "货代、利润规则与AI识图配置",
}


class MainWindow(QMainWindow):
    """主窗口 —— 从 main_window.ui 加载布局，通过 MainWindowBinder 绑定控件。

    架构变更（2.6.1-dual-profit）：
    - .ui 决定布局（侧边栏、导航、顶部问候、汇率、数据目录）；
    - MainWindowBinder 按 objectName 绑定信号与状态同步；
    - 六个页面挂载到 .ui 的 mainStack 页面占位中；
    - 利润双场景由 CalculationBinder 负责（在 CalculationPage 重写后启用）。
    """

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.settings = context.settings_service.load()
        self.setMinimumSize(1280, 800)
        self.setStyleSheet(APP_STYLE)

        # 从 .ui 加载主窗口布局
        from profit_accounting_26.ui.ui_loader import load_main_window

        loaded_ui = load_main_window()
        # 将 .ui 的 central widget 移植到 self
        loaded_central = loaded_ui.centralWidget()
        loaded_central.setParent(self)
        self.setCentralWidget(loaded_central)
        # 窗口标题使用 .ui 中的 windowTitle（运行时为 2.6.1），不硬编码旧版本
        self.setWindowTitle(loaded_ui.windowTitle())
        self.resize(loaded_ui.size())
        if loaded_ui.minimumSize().width() > 0:
            self.setMinimumSize(loaded_ui.minimumSize())

        # 设置窗口图标
        self.setWindowIcon(
            QIcon(
                str(
                    resource_path(
                        "src/profit_accounting_26/ui/assets/app_icon_desktop_taskbar.svg"
                    )
                )
            )
        )

        # 创建六个页面（保留现有程序化页面，确保功能不丢失）
        self.image_search_page = ImageSearchPage(context)
        self.calculation_page = CalculationPage(context)
        self.history_page = HistoryPage(context)
        self.import_export_page = ImportExportPage(context)
        self.calibration_page = CalibrationPage(context)
        self.settings_page = SettingsPage(context)

        # 使用 Binder 绑定 .ui 控件
        self.binder = MainWindowBinder(self, context)
        self.binder.calculation_page = self.calculation_page
        self.binder.settings_page = self.settings_page
        self.binder.image_search_page = self.image_search_page
        self.binder.history_page = self.history_page
        self.binder.import_export_page = self.import_export_page
        self.binder.calibration_page = self.calibration_page
        self.binder.bind()

        # 跨页面信号（保留现有行为）
        self.calculation_page.dirtyChanged.connect(self.binder.set_dirty)
        self.settings_page.dirtyChanged.connect(self.binder.set_dirty)
        self.settings_page.settingsSaved.connect(self.binder.on_settings_saved)
        self.settings_page.forwardersSaved.connect(self.calculation_page.refresh_settings)
        self.calculation_page.saved.connect(lambda _record_id: self.history_page.refresh())
        self.history_page.recordRequested.connect(self.open_record)
        self.image_search_page.sendToCalculation.connect(self.send_image_to_calculation)

    def switch_page(self, index: int) -> None:
        """委托给 binder。"""
        self.binder.switch_page(index)

    def set_dirty(self, dirty: bool) -> None:
        self.binder.set_dirty(dirty)

    def open_record(self, record_id: str) -> None:
        self.calculation_page.load_record_payload(record_id)
        self.switch_page(1)

    def send_image_to_calculation(self, path: str, link: str) -> None:
        target = next(
            (slot for slot in self.calculation_page.image_slots if slot.path is None),
            self.calculation_page.image_slots[0],
        )
        target.load_path(Path(path))
        self.calculation_page.set_product_link(link)
        self.switch_page(1)

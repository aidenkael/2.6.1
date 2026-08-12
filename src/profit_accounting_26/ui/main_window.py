from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QWidget

from profit_accounting_26.application import AppContext
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.binders.main_window_binder import MainWindowBinder
from profit_accounting_26.ui.pages import (
    CalculationPage,
    HistoryPage,
    SettingsPage,
)
from profit_accounting_26.ui.theme import APP_STYLE
from profit_accounting_26.product_collector import ProductCollectionPage
# 保留 NAV_ITEMS 供 app.py 和测试导入
NAV_ITEMS = [
    "新商品测算",
    "商品采集",
    "历史记录管理",
    "设置",
]
SUBTITLES = {
    "新商品测算": "图片识别、物流估算与利润测算在同一页面完成",
    "商品采集": "AliExpress Business 商品搜索与候选管理",
    "历史记录管理": "打开记录、查看快照并补充实际反馈",
    "设置": "货代、利润规则、AI识图与物流校准配置",
}


class MainWindow(QMainWindow):
    """主窗口 —— 从 main_window.ui 加载布局，通过 MainWindowBinder 绑定控件。

    架构变更（2.6.1-dual-profit）：
    - .ui 决定布局（侧边栏、导航、顶部问候、汇率、数据目录）；
    - MainWindowBinder 按 objectName 绑定信号与状态同步；
    - 三个页面挂载到 .ui 的 mainStack 页面占位中（Stage 4：导航精简）；
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

        # 创建三个页面（Stage 4：以图搜图/数据导入导出/模型校准反馈已删除）
        self.calculation_page = CalculationPage(context)
        self.history_page = HistoryPage(context)
        self.settings_page = SettingsPage(context)

        # 创建商品采集页（独立模块，不依赖 AppContext）
        self.product_collection_page = ProductCollectionPage()
        # 注入日志目录：<data_dir>/product_collector/
        collector_log_dir = str(context.paths.data_dir / "product_collector")
        self.product_collection_page.set_log_dir(collector_log_dir)
        # 注入 API Profile Store（用于风险检测）
        self.product_collection_page.set_api_profile_store(context.api_profile_store)

        # 使用 Binder 绑定 .ui 控件
        self.binder = MainWindowBinder(self, context)
        self.binder.calculation_page = self.calculation_page
        self.binder.product_collection_page = self.product_collection_page
        self.binder.settings_page = self.settings_page
        self.binder.history_page = self.history_page
        self.binder.bind()

        # 跨页面信号（保留现有行为）
        self.calculation_page.dirtyChanged.connect(self.binder.set_dirty)
        self.settings_page.dirtyChanged.connect(self.binder.set_dirty)
        self.settings_page.settingsSaved.connect(self.binder.on_settings_saved)
        self.settings_page.forwardersSaved.connect(self.calculation_page.refresh_settings)
        self.calculation_page.saved.connect(lambda _record_id: self.history_page.refresh())
        self.history_page.recordRequested.connect(self.open_record)

    def switch_page(self, index: int) -> None:
        """委托给 binder。"""
        self.binder.switch_page(index)

    def set_dirty(self, dirty: bool) -> None:
        self.binder.set_dirty(dirty)

    def open_record(self, record_id: str) -> None:
        self.calculation_page.load_record_payload(record_id)
        self.switch_page(0)

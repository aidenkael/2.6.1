"""主窗口 Binder。

在 ``MainWindow`` 加载 ``main_window.ui`` 后，按 ``objectName`` 绑定：
- 顶部问候（btnRefreshGreeting / lblGreetingTitle / lblGreetingSubtitle）
- 左侧三导航（btnNav*）与 mainStack 页面切换（Stage 4：导航精简）
- 数据目录（lblDataDirectoryPath / btnChangeDataDirectory）
- 汇率（spinExchangeRate / btnRefreshExchangeRate / lblExchangeRateUpdated）
- 保存状态（lblSaveStatus）

页面挂载策略：
- pageCalculation：使用 .ui 自带的计算页布局（由 CalculationBinder 绑定）；
- pageSettingsHost：将 settings_page.ui 挂载进 pageSettingsHostLayout；
- pageHistory：清除 Designer 占位提示后挂载现有页面 QWidget。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.greeting_header import GreetingHeaderController
from profit_accounting_26.ui.ui_loader import load_settings_page


# 导航按钮 objectName 与页面 objectName 的映射（顺序固定）
NAV_BINDINGS: list[tuple[str, str, str]] = [
    ("btnNavProductCollection", "pageProductCollection", "商品采集"),
    ("btnNavCalculation", "pageCalculation", "新商品测算"),
    ("btnNavHistory", "pageHistory", "历史记录管理"),
    ("btnNavSettings", "pageSettingsHost", "设置"),
]


class MainWindowBinder:
    """绑定已加载的 main_window.ui 上的所有控件。"""

    settingsSaved = Signal()
    forwardersSaved = Signal()

    def __init__(self, window: QMainWindow, context: AppContext) -> None:
        self.window = window
        self.context = context
        self.settings = context.settings_service.load()
        self.greeting_header: GreetingHeaderController | None = None
        self._nav_buttons: list[QPushButton] = []
        self._page_widgets: dict[str, QWidget] = {}
        # 外部设置：由 MainWindow 注入实际页面 widget
        self.calculation_page = None
        self.product_collection_page = None
        self.settings_page = None
        self.history_page = None

    # ------------------------------------------------------------------
    # 绑定入口
    # ------------------------------------------------------------------

    def bind(self) -> None:
        """执行所有绑定。在 MainWindow 完成页面注入后调用。"""
        self._bind_greeting()
        self._bind_navigation()
        self._bind_data_directory()
        self._bind_exchange_rate()
        self._bind_save_status()
        self._mount_pages()
        # 默认切换到测算页（Stage 4：新导航顺序下为 index 0）
        self.switch_page(0)

    # ------------------------------------------------------------------
    # 顶部问候
    # ------------------------------------------------------------------

    def _bind_greeting(self) -> None:
        btn_refresh = self.window.findChild(QPushButton, "btnRefreshGreeting")
        lbl_title = self.window.findChild(QLabel, "lblGreetingTitle")
        lbl_subtitle = self.window.findChild(QLabel, "lblGreetingSubtitle")
        lbl_user_name = self.window.findChild(QLabel, "lblGreetingUserName")

        self.greeting_header = GreetingHeaderController(
            lambda: str(self.settings.get("display_name") or "用户"), self.window
        )
        if btn_refresh and lbl_title and lbl_subtitle:
            self.greeting_header.bind_existing_header(
                title_label=lbl_title,
                subtitle_label=lbl_subtitle,
                shuffle_button=btn_refresh,
                user_name_label=lbl_user_name,
            )

    # ------------------------------------------------------------------
    # 导航与页面
    # ------------------------------------------------------------------

    def _bind_navigation(self) -> None:
        self._nav_buttons = []
        for btn_name, _page_name, _label in NAV_BINDINGS:
            btn = self.window.findChild(QPushButton, btn_name)
            if btn:
                btn.setCheckable(True)
                # 每个按钮只连接一次
                idx = len(self._nav_buttons)
                btn.clicked.connect(lambda _checked, i=idx: self.switch_page(i))
                self._nav_buttons.append(btn)

    def switch_page(self, index: int) -> None:
        """切换到第 index 个导航页（索引按 NAV_BINDINGS 显示顺序）。

        mainStack 物理顺序与导航显示顺序可能不同（pageCalculation 占位在挂载时
        被替换为真实 CalculationPage），因此按导航项对应的页面实际索引切换。
        """
        stack = self.window.findChild(QStackedWidget, "mainStack")
        if not stack or not (0 <= index < len(NAV_BINDINGS)):
            return
        _btn_name, page_name, label = NAV_BINDINGS[index]
        real_index = self._page_stack_index(stack, page_name)
        if real_index < 0:
            real_index = index
        stack.setCurrentIndex(real_index)
        for idx, btn in enumerate(self._nav_buttons):
            btn.setChecked(idx == index)
        # 触发页面刷新
        if label == "历史记录管理" and self.history_page:
            self.history_page.refresh()
        elif label == "设置" and self.settings_page and not getattr(self.settings_page, "dirty", False):
            if hasattr(self.settings_page, "load_settings"):
                self.settings_page.load_settings()

    def _page_stack_index(self, stack: QStackedWidget, page_name: str) -> int:
        """导航项对应页面在 mainStack 中的实际索引。

        pageCalculation 占位在挂载时被替换为真实 CalculationPage；
        其余页面仍以占位 widget 形式挂在 stack 中。
        """
        if page_name == "pageCalculation" and self.calculation_page is not None:
            idx = stack.indexOf(self.calculation_page)
            if idx >= 0:
                return idx
        placeholder = self.window.findChild(QWidget, page_name)
        if placeholder is not None:
            return stack.indexOf(placeholder)
        return -1

    def _mount_pages(self) -> None:
        """将现有页面 widget 挂载到 .ui 的页面占位中。"""
        page_map = {
            "pageCalculation": self.calculation_page,
            "pageProductCollection": self.product_collection_page,
            "pageHistory": self.history_page,
            "pageSettingsHost": self.settings_page,
        }
        stack = self.window.findChild(QStackedWidget, "mainStack")
        for page_name, page_widget in page_map.items():
            if page_widget is None:
                continue
            placeholder = self.window.findChild(QWidget, page_name)
            if placeholder is None:
                continue
            if page_name == "pageCalculation" and stack is not None:
                # CalculationPage 自带从同一 .ui 加载的 pageCalculation 根节点；
                # 直接替换 stack 中的占位页，避免同名控件重复嵌套。
                index = stack.indexOf(placeholder)
                stack.removeWidget(placeholder)
                placeholder.setParent(None)
                placeholder.deleteLater()
                stack.insertWidget(index, page_widget)
                page_widget.setVisible(True)  # setParent 会清除可见标记，必须显式恢复
                continue
            self._replace_placeholder(placeholder, page_widget)

        # 设置页：加载 settings_page.ui 挂载进 pageSettingsHostLayout
        settings_host = self.window.findChild(QWidget, "pageSettingsHost")
        if settings_host and self.settings_page is None:
            # 如果没有外部注入的设置页，加载 .ui 版本
            self._mounted_settings_widget = load_settings_page(parent=settings_host)
            host_layout = settings_host.layout()
            if host_layout:
                host_layout.addWidget(self._mounted_settings_widget)

    @staticmethod
    def _replace_placeholder(placeholder: QWidget, real_widget: QWidget) -> None:
        """清除 Designer 占位内容，将 real_widget 挂载进 placeholder 的布局。"""
        layout = placeholder.layout()
        if layout is None:
            layout = QVBoxLayout(placeholder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        # 清除 Designer 占位子控件（ QLabel with uiPlaceholder property 等）
        from PySide6.QtWidgets import QLayout

        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None and child is not real_widget:
                child.setParent(None)
                child.deleteLater()
        real_widget.setParent(placeholder)
        real_widget.setVisible(True)  # setParent 会清除可见标记，必须显式恢复
        layout.addWidget(real_widget)

    # ------------------------------------------------------------------
    # 数据目录
    # ------------------------------------------------------------------

    def _bind_data_directory(self) -> None:
        self.lbl_data_dir = self.window.findChild(QLabel, "lblDataDirectoryPath")
        btn_change = self.window.findChild(QPushButton, "btnChangeDataDirectory")
        if self.lbl_data_dir:
            self.lbl_data_dir.setText(str(self.context.paths.data_dir))
            self.lbl_data_dir.setWordWrap(True)
        if btn_change:
            btn_change.clicked.connect(self.change_data_directory)

    def change_data_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self.window, "选择新的数据目录", str(self.context.paths.data_dir)
        )
        if not selected:
            return
        from profit_accounting_26.application.settings_migration import sync_user_config
        from profit_accounting_26.shared import ApplicationPaths
        from profit_accounting_26.storage import SQLiteStore

        # 1) 先解析并创建目标目录；此时不写 location.json。
        target = Path(selected).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        target_store = SQLiteStore(target / self.context.paths.database_path.name)
        try:
            summary = sync_user_config(
                self.context.paths.data_dir,
                target,
                source_store=self.context.store,
                target_store=target_store,
            )
        except Exception as exc:
            # 2) 同步失败：location.json 保持原 data_dir，明确提示，不进入半迁移目录。
            QMessageBox.critical(
                self.window,
                "数据目录切换失败",
                f"配置同步失败，已保持原数据目录：\n{self.context.paths.data_dir}\n\n原因：{exc}",
            )
            return
        # 3) 同步全部成功后才提交 location.json。
        ApplicationPaths.save_data_dir(target)
        synced = "、".join(summary.copied_files) or "（无配置文件）"
        notes = []
        if summary.copied_package_files:
            notes.append(f"校准包文件 {summary.copied_package_files} 个")
        if summary.calibration_registry_migrated:
            notes.append("校准版本注册表已同步")
        elif summary.calibration_registry_skipped_reason:
            notes.append(f"校准版本注册表未同步：{summary.calibration_registry_skipped_reason}")
        QMessageBox.information(
            self.window,
            "数据目录已设置",
            f"新数据目录：{target}\n"
            f"已同步配置：{synced}\n"
            f"{'；'.join(notes)}\n"
            "历史记录与图片不会迁移；软件重启后数据目录生效。",
        )
        if getattr(self, "lbl_data_dir", None):
            self.lbl_data_dir.setText(str(self.context.paths.data_dir))

    # ------------------------------------------------------------------
    # 汇率
    # ------------------------------------------------------------------

    def _bind_exchange_rate(self) -> None:
        from PySide6.QtWidgets import QDoubleSpinBox

        self.spin_rate = self.window.findChild(QDoubleSpinBox, "spinExchangeRate")
        btn_refresh = self.window.findChild(QPushButton, "btnRefreshExchangeRate")
        self.lbl_rate_updated = self.window.findChild(QLabel, "lblExchangeRateUpdated")
        if self.spin_rate:
            self.spin_rate.setValue(float(self.settings.get("exchange_rate_usd_to_rmb", 7.2)))
        if self.lbl_rate_updated:
            updated = str(self.settings.get("exchange_rate_updated_at") or "未记录")
            self.lbl_rate_updated.setText(f"最后修改：{updated}")
        if btn_refresh:
            btn_refresh.clicked.connect(self.save_exchange_rate)
        if self.spin_rate:
            self.spin_rate.valueChanged.connect(self._on_rate_live_changed)

    def _on_rate_live_changed(self, _value: float) -> None:
        """汇率实时变化时仅更新更新时间标签，不自动保存。"""
        # 实时保存由 refresh 按钮触发；这里只做 UI 反馈
        if self.lbl_rate_updated:
            self.lbl_rate_updated.setText("未保存修改")

    def save_exchange_rate(self) -> None:
        if not self.spin_rate:
            return
        value = self.spin_rate.value()
        if value <= 0:
            QMessageBox.warning(self.window, "汇率无效", "汇率必须大于0。")
            return
        self.settings = self.context.settings_service.load()
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.settings["exchange_rate_usd_to_rmb"] = value
        self.settings["exchange_rate_updated_at"] = updated_at
        # 尾程 RMB = USD × 汇率（USD 为主字段）
        self.settings["default_tail_fee_rmb"] = float(
            self.settings.get("default_tail_fee_usd", 5.56)
        ) * value
        self.context.settings_service.save(self.settings)
        self.spin_rate.setValue(value)
        if self.lbl_rate_updated:
            self.lbl_rate_updated.setText(f"最后修改：{updated_at}")
        # 通知计算页刷新利润区冻结换算值（含尾程 RMB）
        if self.calculation_page and hasattr(self.calculation_page, "refresh_settings"):
            self.calculation_page.refresh_settings()
        self.settingsSaved.emit()

    # ------------------------------------------------------------------
    # 保存状态
    # ------------------------------------------------------------------

    def _bind_save_status(self) -> None:
        self.lbl_save_status = self.window.findChild(QLabel, "lblSaveStatus")

    def set_dirty(self, dirty: bool) -> None:
        if not self.lbl_save_status:
            return
        if dirty:
            self.lbl_save_status.setText("未保存")
            self.lbl_save_status.setStyleSheet(
                "background:#FFF4E5;color:#C77600;padding:6px 11px;border-radius:14px;"
            )
        else:
            self.lbl_save_status.setText("已保存")
            self.lbl_save_status.setStyleSheet(
                "background:#EAF9F2;color:#168A58;padding:6px 11px;border-radius:14px;"
            )

    # ------------------------------------------------------------------
    # 设置保存后刷新
    # ------------------------------------------------------------------

    def on_settings_saved(self) -> None:
        self.settings = self.context.settings_service.load()
        if self.greeting_header:
            self.greeting_header.refresh_display_name()
        if self.spin_rate:
            self.spin_rate.setValue(float(self.settings.get("exchange_rate_usd_to_rmb", 7.2)))
        if self.lbl_rate_updated:
            updated = str(self.settings.get("exchange_rate_updated_at") or "未记录")
            self.lbl_rate_updated.setText(f"最后修改：{updated}")
        if self.calculation_page and hasattr(self.calculation_page, "refresh_settings"):
            self.calculation_page.refresh_settings()
        self.set_dirty(False)

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
    QToolButton,
)

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.greeting_header import GreetingHeaderController
from profit_accounting_26.ui.pages import (
    CalculationPage,
    CalibrationPage,
    HistoryPage,
    ImageSearchPage,
    ImportExportPage,
    SettingsPage,
)
from profit_accounting_26.ui.theme import APP_STYLE
from profit_accounting_26.ui.widgets import QuickLineEdit

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
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.settings = context.settings_service.load()
        self.setWindowTitle("微智能利润管理软件 2.6")
        self.resize(1600, 960)
        self.setMinimumSize(1280, 800)
        self.setStyleSheet(APP_STYLE)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.topbar = self._build_topbar()
        right_layout.addWidget(self.topbar)
        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)
        root_layout.addWidget(right, 1)

        self.image_search_page = ImageSearchPage(context)
        self.calculation_page = CalculationPage(context)
        self.history_page = HistoryPage(context)
        self.import_export_page = ImportExportPage(context)
        self.calibration_page = CalibrationPage(context)
        self.settings_page = SettingsPage(context)
        self.pages = [
            self.image_search_page,
            self.calculation_page,
            self.history_page,
            self.import_export_page,
            self.calibration_page,
            self.settings_page,
        ]
        for page in self.pages:
            self.stack.addWidget(page)

        self.calculation_page.dirtyChanged.connect(self.set_dirty)
        self.settings_page.dirtyChanged.connect(self.set_dirty)
        self.settings_page.settingsSaved.connect(self.settings_saved)
        self.settings_page.forwardersSaved.connect(self.calculation_page.refresh_settings)
        self.calculation_page.saved.connect(lambda _record_id: self.history_page.refresh())
        self.history_page.recordRequested.connect(self.open_record)
        self.image_search_page.sendToCalculation.connect(self.send_image_to_calculation)
        self.greeting_header = GreetingHeaderController(
            lambda: str(self.settings.get("display_name") or "用户"), self
        )
        self.greeting_header.bind_existing_header(
            title_label=self.page_title,
            subtitle_label=self.page_subtitle,
            shuffle_button=self.greeting_refresh,
        )

        self.switch_page(1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 14)
        layout.setSpacing(8)

        brand = QHBoxLayout()
        logo = QLabel("↗")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(42, 42)
        logo.setStyleSheet("background:#1769F6;color:white;border-radius:11px;font-size:22px;font-weight:700;")
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        title = QLabel("微智能利润管理软件")
        title.setStyleSheet("font-weight:600;font-size:14px;")
        version = QLabel("v2.6.0-rc1 · 本地桌面版")
        version.setProperty("muted", True)
        brand_text.addWidget(title)
        brand_text.addWidget(version)
        brand.addLayout(brand_text)
        layout.addLayout(brand)
        layout.addSpacing(18)

        icon_names = [
            "nav_image_search.svg", "nav_new_product_estimate.svg", "nav_history_records.svg",
            "nav_data_import_export.svg", "nav_model_calibration_feedback.svg", "nav_settings.svg",
        ]
        self.nav_buttons: list[QPushButton] = []
        for index, (icon_name, name) in enumerate(zip(icon_names, NAV_ITEMS, strict=True)):
            button = QPushButton(name)
            button.setIcon(QIcon(str(resource_path(Path("src/profit_accounting_26/ui/assets") / icon_name))))
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, idx=index: self.switch_page(idx))
            self.nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)

        data_card = QFrame()
        data_card.setProperty("card", True)
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(10, 8, 10, 8)
        data_layout.addWidget(QLabel("数据目录"))
        self.data_dir_label = QLabel(str(self.context.paths.data_dir))
        self.data_dir_label.setWordWrap(True)
        self.data_dir_label.setProperty("muted", True)
        data_layout.addWidget(self.data_dir_label)
        change_dir = QPushButton("更改目录")
        change_dir.clicked.connect(self.change_data_directory)
        data_layout.addWidget(change_dir)
        layout.addWidget(data_card)

        rate_card = QFrame()
        rate_card.setProperty("card", True)
        rate_layout = QVBoxLayout(rate_card)
        rate_layout.setContentsMargins(10, 8, 10, 8)
        rate_layout.setSpacing(5)
        rate_layout.addWidget(QLabel("USD → RMB 汇率"))
        rate_row = QHBoxLayout()
        self.sidebar_rate = QuickLineEdit(f"{float(self.settings.get('exchange_rate_usd_to_rmb', 7.2)):.4f}")
        self.sidebar_rate.setFixedWidth(105)
        save_rate = QPushButton("保存")
        save_rate.clicked.connect(self.save_sidebar_rate)
        rate_row.addWidget(self.sidebar_rate)
        rate_row.addWidget(save_rate)
        rate_layout.addLayout(rate_row)
        updated = str(self.settings.get("exchange_rate_updated_at") or "未记录")
        self.rate_updated_label = QLabel(f"最后修改：{updated}")
        self.rate_updated_label.setProperty("muted", True)
        self.rate_updated_label.setWordWrap(True)
        rate_layout.addWidget(self.rate_updated_label)
        layout.addWidget(rate_card)
        version_label = QLabel("当前版本：2.6.0-rc1")
        version_label.setProperty("muted", True)
        layout.addWidget(version_label)
        return sidebar

    def _build_topbar(self) -> QWidget:
        top = QWidget()
        top.setObjectName("topBar")
        top.setFixedHeight(68)
        layout = QHBoxLayout(top)
        layout.setContentsMargins(16, 8, 18, 8)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.page_title = QLabel("新商品测算")
        self.page_title.setProperty("heading", True)
        self.page_subtitle = QLabel(SUBTITLES["新商品测算"])
        self.page_subtitle.setProperty("subheading", True)
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)
        layout.addLayout(title_box)
        self.greeting_refresh = QToolButton()
        layout.addWidget(self.greeting_refresh)
        layout.addStretch(1)
        self.save_status = QLabel("已保存")
        self.save_status.setStyleSheet("background:#EAF9F2;color:#168A58;padding:6px 11px;border-radius:14px;")
        layout.addWidget(self.save_status)
        self.avatar = QLabel("用")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(30, 30)
        self.avatar.setStyleSheet("background:#1769F6;color:white;border-radius:15px;font-weight:600;")
        layout.addWidget(self.avatar)
        self.user_name = QLabel(str(self.settings.get("display_name") or "用户"))
        layout.addWidget(self.user_name)
        return top

    def switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for idx, button in enumerate(self.nav_buttons):
            button.setChecked(idx == index)
        name = NAV_ITEMS[index]
        if name == "历史记录管理":
            self.history_page.refresh()
        elif name == "模型校准反馈":
            self.calibration_page.refresh()
        elif name == "设置" and not self.settings_page.dirty:
            self.settings_page.load_settings()

    def set_dirty(self, dirty: bool) -> None:
        if dirty:
            self.save_status.setText("未保存")
            self.save_status.setStyleSheet("background:#FFF4E5;color:#C77600;padding:6px 11px;border-radius:14px;")
        else:
            self.save_status.setText("已保存")
            self.save_status.setStyleSheet("background:#EAF9F2;color:#168A58;padding:6px 11px;border-radius:14px;")

    def settings_saved(self) -> None:
        self.settings = self.context.settings_service.load()
        display_name = str(self.settings.get("display_name") or "用户")
        self.user_name.setText(display_name)
        self.avatar.setText(display_name[:1])
        self.greeting_header.refresh_display_name()
        self.sidebar_rate.setText(f"{float(self.settings.get('exchange_rate_usd_to_rmb', 7.2)):.4f}")
        updated = str(self.settings.get("exchange_rate_updated_at") or "未记录")
        self.rate_updated_label.setText(f"最后修改：{updated}")
        self.calculation_page.refresh_settings()
        self.set_dirty(False)

    def save_sidebar_rate(self) -> None:
        try:
            value = float(self.sidebar_rate.text().strip())
        except ValueError:
            QMessageBox.warning(self, "汇率无效", "请输入有效数字。")
            return
        if value <= 0:
            QMessageBox.warning(self, "汇率无效", "汇率必须大于0。")
            return
        self.settings = self.context.settings_service.load()
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.settings["exchange_rate_usd_to_rmb"] = value
        self.settings["exchange_rate_updated_at"] = updated_at
        self.settings["default_tail_fee_usd"] = float(self.settings.get("default_tail_fee_rmb", 40.0)) / value
        self.context.settings_service.save(self.settings)
        self.sidebar_rate.setText(f"{value:.4f}")
        self.rate_updated_label.setText(f"最后修改：{updated_at}")
        self.calculation_page.refresh_settings()
        QMessageBox.information(self, "已保存", "汇率已保存并用于当前测算。")

    def change_data_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择新的数据目录", str(self.context.paths.data_dir))
        if not selected:
            return
        from profit_accounting_26.shared import ApplicationPaths
        target = ApplicationPaths.save_data_dir(selected)
        # The active context remains on the old directory until restart.  Copy the
        # current settings now so a new settings.json is not silently initialized
        # with defaults on the next launch.
        SettingsService.save_copy(
            self.context.settings_service.load(),
            target / "settings.json",
        )
        QMessageBox.information(
            self,
            "数据目录已设置",
            f"新数据目录：{target}\n当前设置已同步；软件重启后数据目录生效，当前目录和历史数据不会被删除。",
        )

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

from __future__ import annotations

import os
import sys

from profit_accounting_26.ui.main_window import NAV_ITEMS, MainWindow


def _install_chinese_translator(app) -> None:
    """安装 Qt 官方中文翻译，让标准弹窗按钮显示中文（确定/取消等）。"""
    try:
        from pathlib import Path

        import PySide6
        from PySide6.QtCore import QTranslator

        translations_dir = Path(PySide6.__file__).parent / "translations"
        translator = QTranslator(app)
        if translator.load(str(translations_dir / "qt_zh_CN.qm")):
            app.installTranslator(translator)
    except Exception:
        pass


def _choose_data_directory(app) -> Path | None:
    """首次运行：引导用户选择数据保存目录；选择“退出”时返回 None。"""
    from pathlib import Path

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    while True:
        box = QMessageBox(app.activeWindow() or None)
        box.setWindowTitle("请选择软件数据保存目录")
        box.setText(
            "请选择软件数据保存目录\n\n"
            "货代、利润规则、API配置、历史记录、图片和日志都会保存在该目录中。"
        )
        choose_button = box.addButton("选择目录", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("退出", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not choose_button:
            return None
        selected = QFileDialog.getExistingDirectory(
            app.activeWindow() or None,
            "选择软件数据保存目录",
            str(Path.home() / "Desktop"),
        )
        if not selected:
            continue
        target = Path(selected).expanduser().resolve()
        if target.is_dir():
            return target


def build_window(data_dir=None):
    """构造主窗口。

    ``data_dir`` 显式传入（测试/工具）时直接使用，跳过 location.json 与首次
    目录选择；未传入时走正式启动逻辑：

    - location.json 已存在 → 以其为唯一数据目录（忽略 PROFIT_ACCOUNTING_DATA_DIR）；
    - 不存在 → 弹窗要求选择数据目录，取消则返回 ``(app, None)``。
    """
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from profit_accounting_26.application import AppContext
    from profit_accounting_26.shared import ApplicationPaths, resource_path

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication(sys.argv)
    _install_chinese_translator(app)
    app.setApplicationName("微智能利润管理软件 2.6.1")
    app.setOrganizationName("ProfitAccounting26")
    app.setWindowIcon(QIcon(str(resource_path("src/profit_accounting_26/ui/assets/app_icon_desktop_taskbar.svg"))))
    if data_dir is not None:
        paths = ApplicationPaths.from_data_dir(data_dir)
    else:
        paths = ApplicationPaths.ui_default()
        if paths is None:
            selected = _choose_data_directory(app)
            if selected is None:
                return app, None
            ApplicationPaths.save_data_dir(selected)
            paths = ApplicationPaths.from_data_dir(selected)
    context = AppContext.create_default(paths=paths)
    window = MainWindow(context)
    return app, window


def main() -> int:
    app, window = build_window()
    if window is None:
        return 0
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

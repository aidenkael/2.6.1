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


def build_window():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from profit_accounting_26.application import AppContext
    from profit_accounting_26.shared import resource_path

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication(sys.argv)
    _install_chinese_translator(app)
    app.setApplicationName("微智能利润管理软件 2.6.1")
    app.setOrganizationName("ProfitAccounting26")
    app.setWindowIcon(QIcon(str(resource_path("src/profit_accounting_26/ui/assets/app_icon_desktop_taskbar.svg"))))
    context = AppContext.create_default()
    window = MainWindow(context)
    return app, window


def main() -> int:
    app, window = build_window()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import sys

from profit_accounting_26.ui.main_window import NAV_ITEMS, MainWindow


def build_window():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from profit_accounting_26.application import AppContext
    from profit_accounting_26.shared import resource_path

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication(sys.argv)
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

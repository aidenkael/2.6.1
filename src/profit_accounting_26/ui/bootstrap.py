"""UU护航 / UU测算 共享的 UI 启动 bootstrap（QApplication + 数据目录解析）。

从 ``ui/app.py`` 提取的最小共享层：主软件 ``build_window`` 与 UU测算 的
quick 入口共用同一套 QApplication / 中文翻译 / location.json 数据目录解析，
保证主软件行为与既有测试零变化；UU测算 只替换应用名与窗口图标。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from profit_accounting_26.shared import ApplicationPaths, resource_path


def install_chinese_translator(app) -> None:
    """安装 Qt 官方中文翻译，让标准弹窗按钮显示中文（确定/取消等）。"""
    try:
        import PySide6
        from PySide6.QtCore import QTranslator

        translations_dir = Path(PySide6.__file__).parent / "translations"
        translator = QTranslator(app)
        if translator.load(str(translations_dir / "qt_zh_CN.qm")):
            app.installTranslator(translator)
    except Exception:
        pass


def choose_data_directory(app) -> Path | None:
    """首次运行：引导用户选择数据保存目录；选择“退出”时返回 None。"""
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


def bootstrap_application(
    *,
    data_dir=None,
    app_name: str = "UU护航 3.0.1",
    icon_relative: str | None = None,
):
    """建立 QApplication 并解析数据目录，返回 ``(app, paths)``。

    - ``data_dir`` 显式传入（测试/工具）时直接使用，跳过 location.json 与首次目录选择；
    - 未传入时走正式启动逻辑：location.json 已存在 → 以其为唯一数据目录；
      不存在 → 弹窗要求选择数据目录，取消则返回 ``(app, None)``；
    - ``icon_relative`` 传入时同时设置 ``QApplication.setWindowIcon``
      （主软件黑色 U / UU测算 蓝色 U）。
    """
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication(sys.argv)
    install_chinese_translator(app)
    app.setApplicationName(app_name)
    app.setOrganizationName("ProfitAccounting26")
    if icon_relative:
        app.setWindowIcon(QIcon(str(resource_path(icon_relative))))
    if data_dir is not None:
        return app, ApplicationPaths.from_data_dir(data_dir)
    paths = ApplicationPaths.ui_default()
    if paths is None:
        selected = choose_data_directory(app)
        if selected is None:
            return app, None
        ApplicationPaths.save_data_dir(selected)
        paths = ApplicationPaths.from_data_dir(selected)
    return app, paths

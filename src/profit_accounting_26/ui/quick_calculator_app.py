"""UU测算 —— 独立启动入口。

用户体验：双击 UU测算 直接打开轻量核算小窗口，不需要先启动 UU护航；
与主软件共用同一个数据目录 / location.json / SettingsService / AppContext。
极薄入口：只建立 QApplication、解析数据目录、创建同一个 AppContext、
设置蓝色 U 图标、打开 QuickCalculatorWindow；不构造 MainWindow。
"""

from __future__ import annotations

from PySide6.QtGui import QIcon

from profit_accounting_26.application import AppContext
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.bootstrap import bootstrap_application
from profit_accounting_26.ui.quick_calculator_window import (
    QUICK_ICON_RELATIVE,
    QuickCalculatorWindow,
)


def build_quick_window(data_dir=None):
    """构造 UU测算 窗口（不构造 MainWindow）。

    ``data_dir`` 显式传入（测试/工具）时直接使用；未传入时走与主软件相同的
    location.json 数据目录解析（共享 bootstrap_application）。
    返回 ``(app, window)``；首次运行取消选择目录时 window 为 None。
    """
    app, paths = bootstrap_application(
        data_dir=data_dir,
        app_name="UU测算 3.0.1",
        icon_relative=QUICK_ICON_RELATIVE,
    )
    if paths is None:
        return app, None
    context = AppContext.create_default(paths=paths)
    window = QuickCalculatorWindow(context)
    # 窗口级图标与 QApplication.setWindowIcon 都使用蓝色 U（见 §8）
    window.setWindowIcon(QIcon(str(resource_path(QUICK_ICON_RELATIVE))))
    return app, window


def main() -> int:
    app, window = build_quick_window()
    if window is None:
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

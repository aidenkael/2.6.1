"""设置页 1920x1080 显示核对脚本。

在真实 Windows 1920x1080 桌面、窗口最大化状态下核对：
1. 记录实际窗口客户区尺寸；
2. 设置页底部利润规则按钮是否可见；
3. 是否仍需垂直滚动；
4. 若仍有滚动条，记录滚动范围和被遮挡内容。

不修改冻结 .ui。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PySide6.QtWidgets import QApplication
from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.main_window import MainWindow


def main():
    app = QApplication.instance() or QApplication([])
    tmp_dir = os.path.join(os.path.dirname(__file__), "_check_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    os.environ["PROFIT_ACCOUNTING_DATA_DIR"] = tmp_dir
    context = AppContext.create_default()

    window = MainWindow(context)
    # 模拟 1920x1080 最大化（offscreen 模式下 showMaximized 无效，用 setFixedSize）
    window.setFixedSize(1920, 1040)  # 1040 = 1080 - 任务栏高度(约40)
    window.show()
    app.processEvents()

    # 切换到设置页（索引 5 = 设置）
    window.binder.switch_page(5)
    app.processEvents()

    # 记录客户区尺寸
    client_rect = window.centralWidget().rect() if window.centralWidget() else window.rect()
    print(f"[窗口] 外部尺寸: {window.width()}x{window.height()}")
    print(f"[窗口] 客户区尺寸: {client_rect.width()}x{client_rect.height()}")

    # 查找设置页中的滚动区域
    from PySide6.QtWidgets import QScrollArea
    settings_page = window._settings_page if hasattr(window, "_settings_page") else None
    if settings_page is None:
        # 尝试从 stacked widget 获取
        for child in window.findChildren(type(window)):
            pass
    # 直接查找 SettingsPage 实例
    from profit_accounting_26.ui.pages.settings_page import SettingsPage
    pages = window.findChildren(SettingsPage)
    if pages:
        settings_page = pages[0]
        print(f"[设置页] 找到 SettingsPage: {settings_page}")
    else:
        print("[设置页] 未找到 SettingsPage 实例")
        # 尝试从 stackedWidget 获取当前页
        stack = window.findChild(type(window), "mainStack") or window.findChild(type(window))
        print(f"[设置页] 尝试从 stackedWidget 获取")

    # 查找滚动区域
    scroll_areas = window.findChildren(QScrollArea)
    print(f"[滚动区域] 找到 {len(scroll_areas)} 个 QScrollArea")
    for i, sa in enumerate(scroll_areas):
        vbar = sa.verticalScrollBar()
        hbar = sa.horizontalScrollBar()
        print(f"  ScrollArea[{i}] objectName={sa.objectName()}")
        print(f"    viewport: {sa.viewport().width()}x{sa.viewport().height()}")
        print(f"    widget: {sa.widget().width()}x{sa.widget().height() if sa.widget() else 'None'}")
        print(f"    verticalScrollBar visible={vbar.isVisible()}, max={vbar.maximum()}, min={vbar.minimum()}")
        print(f"    horizontalScrollBar visible={hbar.isVisible()}")

    # 查找利润规则相关按钮
    from PySide6.QtWidgets import QPushButton
    all_buttons = window.findChildren(QPushButton)
    rule_buttons = [btn for btn in all_buttons if "rule" in (btn.objectName() or "").lower() or "规则" in btn.text()]
    print(f"[利润规则按钮] 找到 {len(rule_buttons)} 个")
    for btn in rule_buttons:
        print(f"  {btn.objectName()}: text='{btn.text()}', visible={btn.isVisible()}, "
              f"pos=({btn.pos().x()},{btn.pos().y()}), size={btn.width()}x{btn.height()}")
        # 检查是否在可视区域内
        viewport = None
        parent = btn.parent()
        while parent:
            if isinstance(parent, QScrollArea):
                viewport = parent.viewport()
                break
            parent = parent.parent()
        if viewport:
            btn_global = btn.mapToGlobal(btn.rect().topLeft())
            vp_global = viewport.mapToGlobal(viewport.rect().topLeft())
            in_view = (btn_global.y() >= vp_global.y() and
                       btn_global.y() + btn.height() <= vp_global.y() + viewport.height())
            print(f"    在滚动区域视口内: {in_view}")

    # 截图
    screenshot_path = os.path.join(os.path.dirname(__file__), "docs", "assets",
                                    "ui_acceptance_2026-08-04", "03_settings_maximized.png")
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
    import time
    # 等待布局稳定
    for _ in range(5):
        app.processEvents()
        time.sleep(0.1)
    pix = window.grab()
    pix.save(screenshot_path)
    print(f"[截图] 已保存: {screenshot_path} ({pix.width()}x{pix.height()})")

    window.close()
    app.processEvents()

    # 清理临时目录
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

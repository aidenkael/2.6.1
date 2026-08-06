"""第八轮人工验收截图生成器（Windows 1920×1080）。

展示 7 项要素：
1. Hi
2. 蓝色背景用户名
3. 中文问候
4. 英文问候
5. 右上角刷新图标
6. 尾程 USD 与正确联动的 RMB
7. 可见的标价利率
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Skip if not Qt
try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLabel
except ImportError:
    print("PySide6 不可用，跳过截图")
    sys.exit(0)

# Redirect data dir to temp
data_dir = Path(tempfile.mkdtemp(prefix="pa26_screenshot_"))
os.environ["PROFIT_ACCOUNTING_DATA_DIR"] = str(data_dir)

from profit_accounting_26.application import AppContext
from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.ui.binders.calculation_binder import (
    DRIVER_NO_ACTIVITY_PROFIT,
)
from profit_accounting_26.ui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)

context = AppContext.create_default()

# Setup: set display_name to show blue box
settings = context.settings_service.load()
settings["display_name"] = "验收入"
settings["exchange_rate_usd_to_rmb"] = 7.2
context.settings_service.save(settings)

# Build main window
window = MainWindow(context)
window.resize(1920, 1080)
window.show()
app.processEvents()

# ----- Setup tail fee linkage visibility -----
page = window.calculation_page
# Set tail USD to show real-time linkage with RMB
usd_spin = page._root.findChild(QDoubleSpinBox, "spinTailFreightUsd")
rmb_spin = page._root.findChild(QDoubleSpinBox, "spinTailFreightRmb")
if usd_spin:
    usd_spin.setValue(5.56)   # RMB should be ~40.03 at rate 7.2
app.processEvents()

# ----- Setup profit: cost=100, na_profit=40.81 → list-price rate 40.81% -----
binder = page.profit_binder
binder.set_calculation_cost(100.0)
binder._profit_driver = DRIVER_NO_ACTIVITY_PROFIT
binder.txt_na_profit_rmb.setValue(40.81)
app.processEvents()

# ----- Take screenshot -----
output_path = Path(__file__).resolve().parents[1] / ".workbuddy" / "artifacts" / "windows_acceptance_2026-08-06.png"
output_path.parent.mkdir(parents=True, exist_ok=True)

pixmap = window.grab()
pixmap.save(str(output_path))
print(f"Screenshot saved: {output_path}")

# Verify rate label
rate_label = window.findChild(QLabel, "txtListPriceProfitRate")
if rate_label:
    print(f"List price rate: {rate_label.text()}")

window.close()
app.processEvents()
print("Done.")

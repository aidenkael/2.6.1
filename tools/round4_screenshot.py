"""第四轮修正 UI 截图生成器（Windows 1920×1080 主窗口 + 设置/历史页局部）。

用途：与 docs/assets/ui_round4_2026-08-09/ 参考截图并排核对：
1. 当前系统总成本 6 行排版（正常值）；
2. 采购成本/国内运费 = 0 的红色弱提醒；
3. 货代管理启用/操作列居中与按钮宽度（使用中 + 已归档两个视图）；
4. 历史记录多行文字顶部对齐。
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("PySide6 不可用，跳过截图")
    sys.exit(0)

data_dir = Path(tempfile.mkdtemp(prefix="pa26_round4_"))
os.environ["PROFIT_ACCOUNTING_DATA_DIR"] = str(data_dir)

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.ui.main_window import MainWindow
from profit_accounting_26.ui.pages import HistoryPage, SettingsPage

app = QApplication.instance() or QApplication(sys.argv)
context = AppContext.create_default()

# 数据准备：两家货代（其中一家归档）+ 默认规则
settings = context.settings_service.load()
shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
old = SettingsService.new_forwarder("旧货代（示例）", 90.0, 8.0, 6000.0)
old_dict = asdict(old)
old_dict["enabled"] = False
old_dict["archived"] = True
settings["forwarders"] = [asdict(shenzhen), asdict(yiwu), old_dict]
settings["selected_forwarder_id"] = shenzhen.id
settings["exchange_rate_usd_to_rmb"] = 7.2
context.settings_service.save(settings)

# 历史数据：两条记录，成本/包装/校准多行文本
for index in (1, 2):
    payload = {
        "product_name": f"示例商品 {index}（名称较长用于测试换行与顶部对齐效果）",
        "product_link": f"https://detail.1688.com/offer/sample{index}.html",
        "created_at": "2026-08-08T00:00:00Z",
        "updated_at": "2026-08-08T01:00:00Z",
        "product_cost_rmb": 66.80,
        "domestic_shipping_rmb": 28.00,
        "shein_quote_usd": 30.0,
        "layers": {
            "adopted": {
                "selected_packaging": "保守档",
                "conservative": {
                    "packaging_method": "气泡袋",
                    "length_cm": 17,
                    "width_cm": 32,
                    "height_cm": 17,
                    "weight_g": 720,
                },
            },
            "calculated": {
                "system_cost_rmb": 237.26,
                "exchange_rate": 7.2,
                "forwarder_name": "深圳货代",
                "logistics_quote": {
                    "weight_fee_rmb": 92.48,
                    "fixed_fee_rmb": 10.0,
                    "tail_fee_rmb": 39.98,
                    "total_logistics_rmb": 142.46,
                },
            },
        },
        "profit_scenarios": {
            "no_activity": {"sale_price_usd": 30.0, "profit_rmb": 78.9},
        },
    }
    context.record_service.save(payload, images=[], ai_initial=None)

output_dir = Path(__file__).resolve().parents[1] / "docs" / "assets" / "ui_round4_2026-08-09"
output_dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 主窗口
window = MainWindow(context)
window.resize(1920, 1080)
window.show()
app.processEvents()

page = window.calculation_page
page.product_cost.setValue(66.80)
page.domestic_shipping.setValue(28.00)
page.conservative_fields["length"].setValue(25.0)
page.conservative_fields["width"].setValue(18.0)
page.conservative_fields["height"].setValue(6.0)
page.conservative_fields["weight"].setValue(320.0)
page.refresh_settings()
page.recalculate()
app.processEvents()
window.grab().save(str(output_dir / "main_cost_six_rows.png"))

# 0 值红色弱提醒
page.product_cost.setValue(0.0)
page.domestic_shipping.setValue(0.0)
page.recalculate()
app.processEvents()
window.grab().save(str(output_dir / "main_cost_zero_warn.png"))
window.close()
app.processEvents()

# ---------------------------------------------------------------- 设置页：货代表
settings_page = SettingsPage(context)
settings_page.resize(1700, 980)
settings_page.show()
app.processEvents()
settings_page.filter_forwarders(False)
app.processEvents()
settings_page.grab().save(str(output_dir / "settings_forwarders_active.png"))
settings_page.filter_forwarders(True)
app.processEvents()
settings_page.grab().save(str(output_dir / "settings_forwarders_archived.png"))
settings_page.close()
app.processEvents()

# ---------------------------------------------------------------- 历史页
history_page = HistoryPage(context)
history_page.resize(1700, 980)
history_page.show()
app.processEvents()
history_page.grab().save(str(output_dir / "history_top_aligned.png"))
history_page.close()
app.processEvents()

print(f"Screenshots saved to: {output_dir}")

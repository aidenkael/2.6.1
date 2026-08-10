"""阶段 3 最后一次综合调整验收截图（Windows 1920×1080）。

生成两张截图：
1. 新品测算页 —— 商品简洁摘要 placeholder（商品主体；主要结构；发货相关特征）
   与用户修正框新两行提示（确认未增加卡片高度）；
2. HistoryPage —— 总成本加粗 ¥/$、售价三行顺序、利润标题、
   包装列收窄 / 校准列加宽、长反馈截断 + tooltip。
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

try:
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
except ImportError:
    print("PySide6 不可用，跳过截图")
    sys.exit(0)

data_dir = Path(tempfile.mkdtemp(prefix="pa26_stage3_final_"))
os.environ["PROFIT_ACCOUNTING_DATA_DIR"] = str(data_dir)

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.application.settings_service import SettingsService
from profit_accounting_26.domain.models import ImageType
from profit_accounting_26.ui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)
context = AppContext.create_default()

# ------------------------------------------------------------- 基础设置
settings = context.settings_service.load()
settings["display_name"] = "验收入"
settings["exchange_rate_usd_to_rmb"] = 7.2
shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
settings["selected_forwarder_id"] = shenzhen.id
context.settings_service.save(settings)

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "ui_acceptance_2026-08-11"
OUT_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR = data_dir / "demo_images"
IMG_DIR.mkdir(parents=True, exist_ok=True)


def _make_image(name: str, color: QColor) -> Path:
    image = QImage(320, 320, QImage.Format.Format_RGB32)
    image.fill(color)
    path = IMG_DIR / name
    assert image.save(str(path), "PNG")
    return path


def _payload(product_name: str, *, with_rate: bool = True, cost: float = 66.80) -> dict:
    calculated: dict = {
        "system_cost_rmb": 237.26,
        "forwarder_name": "深圳货代",
        "logistics_quote": {
            "weight_fee_rmb": 92.48,
            "fixed_fee_rmb": 10.0,
            "tail_fee_rmb": 39.98,
            "total_logistics_rmb": 142.46,
        },
    }
    if with_rate:
        calculated["exchange_rate"] = 7.2
    return {
        "product_name": product_name,
        "product_link": "https://detail.1688.com/offer/demo.html",
        "created_at": "2026-08-10T09:00:00Z",
        "updated_at": "2026-08-10T10:00:00Z",
        "product_cost_rmb": cost,
        "domestic_shipping_rmb": 28.00,
        "shein_quote_usd": 30.0,
        "layers": {
            "adopted": {
                "selected_packaging": "保守档",
                "normal": {
                    "packaging_method": "气泡袋", "length_cm": 17, "width_cm": 32,
                    "height_cm": 17, "weight_g": 720,
                },
                "conservative": {
                    "packaging_method": "气泡袋", "length_cm": 17, "width_cm": 32,
                    "height_cm": 17, "weight_g": 720,
                },
                "bare": {"length_cm": 45, "width_cm": 30, "height_cm": 15, "weight_g": 580},
            },
            "calculated": calculated,
        },
        "profit_scenarios": {
            "driver": "no_activity_price",
            "no_activity": {
                "sale_price_usd": 30.0, "profit_rmb": 78.74,
                "profit_rate_on_cost": 0.5, "rule_status": {},
            },
            "activity": {
                "sale_price_usd": 27.0, "profit_rmb": 55.12,
                "profit_rate_on_cost": 0.35, "rule_status": {},
            },
        },
    }


def _ai_initial(summary: str) -> dict:
    return {
        "model": "demo-model",
        "observation": {"product_name": summary.split("；")[0], "display_product_summary": summary},
        "adopted_packaging": {
            "normal": {
                "packaging_method": "气泡袋", "length_cm": 17, "width_cm": 32,
                "height_cm": 17, "weight_g": 720,
            }
        },
    }


# ------------------------------------------------------------- 演示记录
png1 = _make_image("nightcap.png", QColor("#7A9CC6"))
png2 = _make_image("strap.png", QColor("#C67A9C"))

record_a = context.record_service.save(
    _payload("睡帽；软布结构；可压缩"),
    images=[
        SessionImage(png1, ImageType.MAIN, "sha-demo-a1", png1.name),
        SessionImage(png2, ImageType.MAIN, "sha-demo-a2", png2.name),
    ],
    ai_initial=_ai_initial("睡帽；软布结构；可压缩"),
)
record_b = context.record_service.save(
    _payload("蝴蝶结手机挂绳；软包；袋装发货", cost=39.90),
    images=[],
    ai_initial=_ai_initial("蝴蝶结手机挂绳；软包；袋装发货"),
)
record_c = context.record_service.save(
    _payload("皮质手提包；硬壳结构；不可压缩", with_rate=False),
    images=[],
    ai_initial=_ai_initial("皮质手提包；硬壳结构；不可压缩"),
)
record_d = context.record_service.save(
    _payload("折叠水杯；硅胶；可压缩", cost=25.00),
    images=[],
    ai_initial=_ai_initial("折叠水杯；硅胶；可压缩"),
)

feedback_service = context.calibration_feedback_service

# A：长反馈 → 截断 + tooltip
long_note = "实际发货时用了压缩袋，包装体积比AI估算小很多，头程重量也更低。" * 6
fid_a = feedback_service.save({"record_id": record_a, "user_note": long_note})
context.history_record_v2_service.link_feedback(record_a, fid_a)

# D：建议包装 + 真实头程
fid_d = feedback_service.save(
    {
        "record_id": record_d,
        "user_note": "杯身可压扁发货",
        "suggested_package": {"length_cm": 12, "width_cm": 9, "height_cm": 4, "weight_g": 210},
        "actual_logistics": {
            "actual_forwarder": "深圳",
            "actual_first_mile_fee_rmb": 26.0,
            "evidence_level": "actual_logistics",
        },
    }
)
context.history_record_v2_service.link_feedback(record_d, fid_d)

# ------------------------------------------------------------- 窗口与截图
window = MainWindow(context)
window.resize(1920, 1080)
window.show()
app.processEvents()

# 截图 1：新品测算页（用户修正框保持为空，展示新两行提示；高度不变）
window.binder.switch_page(1)
app.processEvents()
shot1 = OUT_DIR / "阶段3_新品测算页_摘要与修正提示_1920x1080.png"
window.grab().save(str(shot1))
print(f"Screenshot saved: {shot1}")

# 截图 2：HistoryPage
window.binder.switch_page(2)
app.processEvents()
shot2 = OUT_DIR / "阶段3_历史记录页_成本售价利润列宽_1920x1080.png"
window.grab().save(str(shot2))
print(f"Screenshot saved: {shot2}")

window.close()
app.processEvents()
print("Done.")

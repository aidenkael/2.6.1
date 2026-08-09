"""第九轮：货代卡只展示头程——移除尾程行（保留空白高度）、物流总价改为头程总费用。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtWidgets import QLabel

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.domain.models import LogisticsQuote
from profit_accounting_26.ui.pages import CalculationPage
from profit_accounting_26.ui.widgets import QuoteCard


@pytest.fixture()
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _install_forwarders(context):
    settings = context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
    settings["selected_forwarder_id"] = shenzhen.id
    context.settings_service.save(settings)


def _quote(*, tail_fee_rmb: float = 40.03) -> LogisticsQuote:
    return LogisticsQuote(
        forwarder_id="f1",
        actual_weight_kg=0.5,
        volume_weight_kg=0.45,
        chargeable_weight_kg=0.5,
        weight_fee_rmb=316.54,
        fixed_fee_rmb=10.0,
        tail_fee_rmb=tail_fee_rmb,
        total_logistics_rmb=316.54 + 10.0 + tail_fee_rmb,
    )


class TestQuoteCardDisplay:
    def test_tail_row_removed_but_space_kept_and_total_renamed(self, qapp):
        card = QuoteCard("f1", "测试货代")
        card.show()
        card.update_quote(_quote())
        qapp.processEvents()
        texts = [label.text() for label in card.findChildren(QLabel)]
        assert "尾程" not in texts
        assert "物流总价" not in texts
        assert "头程总费用" in texts
        # 尾程行仍在布局中且保留空白高度（标题与金额均为空）
        assert card.rows["tail"].text() == ""
        assert card.rows["tail"].height() > 0
        # 头程总费用 = 头程费 + 固定服务费（不含尾程）
        assert card.rows["weight_fee"].text() == "¥316.54"
        assert card.rows["fixed"].text() == "¥10.00"
        assert card.rows["total"].text() == "¥326.54"

    def test_tail_change_does_not_affect_card_total(self, qapp):
        card = QuoteCard("f1", "测试货代")
        card.update_quote(_quote(tail_fee_rmb=40.03))
        assert card.rows["total"].text() == "¥326.54"
        card.update_quote(_quote(tail_fee_rmb=99.99))
        assert card.rows["total"].text() == "¥326.54"
        assert card.rows["tail"].text() == ""

    def test_other_fields_unchanged(self, qapp):
        card = QuoteCard("f1", "测试货代")
        card.update_quote(_quote())
        assert card.rows["actual"].text() == "0.500 kg"
        assert card.rows["volume"].text() == "0.450 kg"
        assert card.rows["chargeable"].text() == "0.500 kg"


class TestForwarderCardsOnPage:
    @pytest.fixture()
    def page(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        _install_forwarders(page.context)
        page.conservative_fields["length"].setValue(25.0)
        page.conservative_fields["width"].setValue(18.0)
        page.conservative_fields["height"].setValue(6.0)
        page.conservative_fields["weight"].setValue(320.0)
        page.refresh_settings()
        page.recalculate()
        yield page
        page.deleteLater()
        qapp.processEvents()

    def test_both_cards_identical_structure_without_tail_and_with_total_fee(self, page):
        cards = list(page.quote_cards.values())
        assert len(cards) == 2
        structures = []
        for card in cards:
            texts = [label.text() for label in card.findChildren(QLabel)]
            assert "尾程" not in texts
            assert "物流总价" not in texts
            assert "头程总费用" in texts
            assert card.rows["tail"].text() == ""
            # 只比较行标题（不比较数值），确保两张卡结构一致
            titles = []
            for index in range(card.layout().count()):
                item = card.layout().itemAt(index)
                row = item.layout() if item is not None else None
                if row is not None and row.count():
                    widget = row.itemAt(0).widget()
                    if isinstance(widget, QLabel):
                        titles.append(widget.text())
            structures.append(sorted(titles))
        assert structures[0] == structures[1], "两张货代卡结构不一致"
        assert set(structures[0]) == {"", "实际重", "体积重", "计费重", "头程费", "头程总费用", "固定费"}

    def test_tail_still_updates_system_cost_but_not_card_total(self, page, qapp):
        before_cards = {fid: card.rows["total"].text() for fid, card in page.quote_cards.items()}
        before_tail = page.system_rows["tail"].text()
        page.tail_fee_usd.spin.setValue(10.0)  # 真实控件 → valueChanged → 实时重算
        qapp.processEvents()
        assert page.system_rows["tail"].text() != before_tail, "尾程仍应影响右侧系统成本"
        for fid, card in page.quote_cards.items():
            assert card.rows["total"].text() == before_cards[fid], "货代卡头程总费用不应随尾程变化"

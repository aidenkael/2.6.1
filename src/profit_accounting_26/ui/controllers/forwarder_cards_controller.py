"""货代卡 Controller —— 第二阶段 Controller 拆分。

只负责动态货代卡管理与货代选择状态：从 ``CalculationPage`` 原样迁移
``rebuild_quote_cards`` / ``select_forwarder``（逻辑零改动），并持有
``quote_cards`` / ``selected_forwarder_id`` / ``forwarder_selection_changed``
三项状态。

边界约定：
- 继续绑定稳定 ``main_window.ui`` 中的原有 objectName（forwarderCardsLayout）；
- 不创建新的页面布局结构、不修改 .ui；只负责现有 forwarderCardsLayout 内
  动态 QuoteCard 的创建与生命周期管理；
- 不含任何物流公式，不创建 Service；报价与系统成本计算仍由
  ``CalculationPage.recalculate`` 与本地确定性引擎完成；
- 用户选择货代后通过注入的 ``mark_dirty_callback`` / ``recalculate_callback``
  通知页面，各调用恰好一次；
- ``settings_provider`` 由页面注入，每次 rebuild 必须返回 ``CalculationPage``
  当前的 ``self.settings``（``refresh_settings`` 会用新 dict 整体替换
  ``self.settings``，因此禁止持有固定 dict 引用），也禁止在此
  ``settings_service.load()`` 创建第二份缓存；
- 页面初始化顺序不变：Designer 预览卡片清理与 ``quote_insert_index`` 的
  定义仍留在 ``CalculationPage._build_dynamic_regions``，本 Controller 只
  通过构造参数接收插入位置。
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import QHBoxLayout, QWidget

from profit_accounting_26.ui.widgets import QuoteCard


class ForwarderCardsController:
    """动态货代卡管理 Controller（不创建布局结构，不接管页面初始化，不含物流公式）。"""

    def __init__(
        self,
        root: QWidget,
        settings_service: Any,
        settings_provider: Callable[[], dict[str, Any]],
        insert_index: int,
        selected_forwarder_id: str,
        mark_dirty_callback: Callable[[], None],
        recalculate_callback: Callable[[], None],
    ) -> None:
        self._settings_service = settings_service
        self._settings_provider = settings_provider
        self._insert_index = insert_index
        self._mark_dirty_callback = mark_dirty_callback
        self._recalculate_callback = recalculate_callback
        self.quote_cards: dict[str, QuoteCard] = {}
        self.selected_forwarder_id = str(selected_forwarder_id or "")
        self.forwarder_selection_changed = False
        self._forwarder_cards_layout = root.findChild(QHBoxLayout, "forwarderCardsLayout")

    # ------------------------------------------------------------------
    # 货代卡
    # ------------------------------------------------------------------

    def rebuild_quote_cards(self) -> None:
        if self._forwarder_cards_layout is None:
            return
        for card in self.quote_cards.values():
            self._forwarder_cards_layout.removeWidget(card)
            card.deleteLater()
        self.quote_cards = {}
        settings = self._settings_provider()
        forwarders = self._settings_service.forwarders_from_settings(settings)
        enabled = [item for item in forwarders if item.enabled and not item.archived]
        priority = {"义乌货代": 0, "深圳货代": 1}
        enabled.sort(key=lambda item: (priority.get(item.name, 9), item.name))
        if enabled and self.selected_forwarder_id not in {item.id for item in enabled}:
            self.selected_forwarder_id = enabled[0].id
        for offset, forwarder in enumerate(enabled):
            card = QuoteCard(forwarder.id, forwarder.name)
            card.selected.connect(self.select_forwarder)
            card.set_checked(
                forwarder.id == self.selected_forwarder_id,
                user_changed=self.forwarder_selection_changed,
            )
            self.quote_cards[forwarder.id] = card
            self._forwarder_cards_layout.insertWidget(self._insert_index + offset, card, 1)

    def select_forwarder(self, forwarder_id: str) -> None:
        self.selected_forwarder_id = forwarder_id
        self.forwarder_selection_changed = True
        for identifier, card in self.quote_cards.items():
            card.set_checked(identifier == forwarder_id, user_changed=True)
        self._mark_dirty_callback()
        self._recalculate_callback()

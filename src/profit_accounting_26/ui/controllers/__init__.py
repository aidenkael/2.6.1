"""UI Controller 层。

Controller 只负责：信号连接、读取既有 objectName 控件、调用业务服务、回写控件。
Controller 层不创建新的页面布局结构、不修改 .ui；
部分 Controller 可负责既有布局内动态 Widget 的创建与生命周期管理。
不得复制业务公式，不重复创建 Service。
"""

from profit_accounting_26.ui.controllers.forwarder_cards_controller import ForwarderCardsController
from profit_accounting_26.ui.controllers.image_slots_controller import ImageSlotsController

__all__ = ["ForwarderCardsController", "ImageSlotsController"]

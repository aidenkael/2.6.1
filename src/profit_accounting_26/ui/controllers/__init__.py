"""UI Controller 层。

Controller 只负责：信号连接、读取既有 objectName 控件、调用业务服务、回写控件。
不拥有或创建 UI，不修改控件布局，不复制业务公式，不重复创建 Service。
"""

from profit_accounting_26.ui.controllers.image_slots_controller import ImageSlotsController

__all__ = ["ImageSlotsController"]

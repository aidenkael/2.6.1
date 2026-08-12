"""Product Collector —— 独立商品采集模块。

从 standalone product_collector 迁入，保持采集核心不变。
"""

from .collector_core import CandidateProduct, collect
from .ui import ProductCollectionPage

__all__ = ["CandidateProduct", "collect", "ProductCollectionPage"]

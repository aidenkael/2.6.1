"""AliExpress Business 极简商品采集包。

Vendored from Electronic-Commerce-Auto commit 796baaa
(product_collector/collector_core/) - 仅做包路径适配。
"""

from .business_source import collect
from .models import CandidateProduct

__all__ = ["CandidateProduct", "collect"]

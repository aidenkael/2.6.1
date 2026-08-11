"""极简商品候选模型

Vendored from Electronic-Commerce-Auto commit 796baaa
(product_collector/collector_core/models.py) - 仅做包路径适配。
"""

from dataclasses import dataclass


@dataclass
class CandidateProduct:
    """搜索采集到的候选商品"""

    product_id: str
    title: str
    main_image: str
    product_url: str
    keyword: str
    position: int

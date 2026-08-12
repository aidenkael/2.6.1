"""极简商品候选模型"""

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

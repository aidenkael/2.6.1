"""AliExpress Business 极简采集核心"""

from .models import CandidateProduct
from .business_source import collect

__all__ = ["CandidateProduct", "collect"]

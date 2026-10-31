"""数据同步适配器包。

每种数据类型一个 adapter module，独立的 fetch → transform → upsert 管线。
"""

from .daily_kline import DailyKlineAdapter
from .stock_basic import StockBasicAdapter
from .indicator_cache import IndicatorCacheAdapter
from .stk_factor import StkFactorAdapter
from .daily_basic import DailyBasicAdapter
from .moneyflow import MoneyflowAdapter

__all__ = [
    "DailyKlineAdapter",
    "StockBasicAdapter",
    "IndicatorCacheAdapter",
    "StkFactorAdapter",
    "DailyBasicAdapter",
    "MoneyflowAdapter",
]

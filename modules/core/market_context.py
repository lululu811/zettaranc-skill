"""
市场环境判断公共逻辑（v3.9.0 技术债务清理）

提取市场环境分类的核心逻辑，供 simulator/market_context.py 使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..constants import (
    MARKET_REGIME_STRONG_BREADTH,
    MARKET_REGIME_STRONG_MONEYFLOW,
    MARKET_REGIME_STRONG_TREND,
    MARKET_REGIME_WEAK_BREADTH,
    MARKET_REGIME_WEAK_MONEYFLOW,
    MARKET_REGIME_WEAK_TREND,
)


class MarketRegime(Enum):
    """市场环境状态"""

    STRONG = "强势"  # 大盘趋势向上，可积极开仓
    NEUTRAL = "震荡"  # 无明确方向，控制仓位
    WEAK = "弱势"  # 趋势向下，空仓或轻仓


@dataclass
class MarketContext:
    """每日市场环境快照"""

    date: str
    regime: MarketRegime
    index_trend: float  # 大盘指数趋势得分 0-100
    breadth: float  # 涨跌家数比，-1 ~ 1
    moneyflow_score: float  # 资金流向得分 0-100
    notes: list[str] = field(default_factory=list)


def classify_market_regime(
    trend_score: float,
    breadth: float,
    moneyflow_score: float,
    strong_threshold: float = MARKET_REGIME_STRONG_TREND,
    weak_threshold: float = MARKET_REGIME_WEAK_TREND,
    breadth_strong: float = MARKET_REGIME_STRONG_BREADTH,
    breadth_weak: float = MARKET_REGIME_WEAK_BREADTH,
    moneyflow_strong: float = MARKET_REGIME_STRONG_MONEYFLOW,
    moneyflow_weak: float = MARKET_REGIME_WEAK_MONEYFLOW,
) -> MarketRegime:
    """
    根据指标判定市场环境。

    Args:
        trend_score: 趋势得分 0-100
        breadth: 涨跌广度 -1 ~ 1
        moneyflow_score: 资金得分 0-100
        strong_threshold: 强势趋势阈值
        weak_threshold: 弱势趋势阈值
        breadth_strong: 强势涨跌广度阈值
        breadth_weak: 弱势涨跌广度阈值
        moneyflow_strong: 强势资金阈值
        moneyflow_weak: 弱势资金阈值

    Returns:
        MarketRegime
    """
    # 强势判定：三个指标都达到强势阈值
    if trend_score >= strong_threshold and breadth > breadth_strong and moneyflow_score >= moneyflow_strong:
        return MarketRegime.STRONG

    # 弱势判定：任一指标达到弱势阈值
    if trend_score <= weak_threshold or breadth < breadth_weak or moneyflow_score <= moneyflow_weak:
        return MarketRegime.WEAK

    # 其他情况为震荡
    return MarketRegime.NEUTRAL


__all__ = [
    "MarketRegime",
    "MarketContext",
    "classify_market_regime",
]

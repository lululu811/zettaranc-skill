"""
组合回测引擎 - 向后兼容层

v3.9.0 重构：实际实现已迁移到 modules.backtest.portfolio
此模块保留以维持向后兼容性。
"""

# 从新位置导入所有公共接口
from modules.backtest.portfolio import (
    PortfolioConfig,
    MarketAdaptiveConfig,
    Position,
    PortfolioBacktestResult,
    PortfolioBacktestEngine,
    StrategyStats,
    EntrySignal,
)

__all__ = [
    "PortfolioConfig",
    "MarketAdaptiveConfig",
    "Position",
    "PortfolioBacktestResult",
    "PortfolioBacktestEngine",
    "StrategyStats",
    "EntrySignal",
]

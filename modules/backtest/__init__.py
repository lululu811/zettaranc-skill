"""
回测引擎模块

提供单股和组合回测功能。
"""

from .single import (
    Trade,
    BacktestResult,
    backtest_signals,
    backtest_strategy,
    _calc_shares,
    _calc_stats,
    backtest_multi_strategy,
    backtest_portfolio,
    SinglePosition,
    MultiStrategyBacktestResult,
)

from .portfolio import (
    PortfolioConfig,
    MarketAdaptiveConfig,
    Position,
    PortfolioBacktestResult,
    PortfolioBacktestEngine,
    StrategyStats,
    EntrySignal,
)

__all__ = [
    # single
    "Trade",
    "BacktestResult",
    "backtest_signals",
    "backtest_strategy",
    "_calc_shares",
    "_calc_stats",
    "backtest_multi_strategy",
    "backtest_portfolio",
    "SinglePosition",
    "MultiStrategyBacktestResult",
    # portfolio
    "PortfolioConfig",
    "MarketAdaptiveConfig",
    "Position",
    "PortfolioBacktestResult",
    "PortfolioBacktestEngine",
]

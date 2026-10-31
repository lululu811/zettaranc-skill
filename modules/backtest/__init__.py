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

from .b1_b2_backtest import (
    B1B2PoolResult,
    run_b1_b2_single,
    run_b1_b2_pool,
    run_b1_b2_walkforward,
)

from .shaofu import (
    ShaofuBacktestResult,
    backtest_shaofu_single,
    summary_text,
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
    # b1+b2
    "B1B2PoolResult",
    "run_b1_b2_single",
    "run_b1_b2_pool",
    "run_b1_b2_walkforward",
    # shaofu（v4.8.0 从 backtest_six_step.py 迁入）
    "ShaofuBacktestResult",
    "backtest_shaofu_single",
    "summary_text",
]

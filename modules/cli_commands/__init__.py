"""CLI 子命令包（按职责组织）。

模块：
    analyze     — analyze / score 子命令
    screen      — screen 子命令
    diagnose    — diagnose / workflow 子命令
    portfolio   — watchlist / trade / daily 子命令
    data        — sync / track / self-optimize / monitor / market-timing 子命令
    backtest    — backtest / verify / simulate 子命令
    strategy_alias — CLI 策略别名常量

外部兼容：`modules.cli` 仍暴露 main() 与 build_parser() 入口。
"""

from __future__ import annotations

from .analyze import analyze_core, cmd_analyze, cmd_score
from .backtest import (
    _b1_b2_pool_to_dict,
    _portfolio_result_to_dict,
    _shaofu_portfolio_to_dict,
    _shaofu_result_to_dict,
    add_verify_v10_parser,
    cmd_backtest,
    cmd_verify_v10,
)
from .data import (
    add_self_optimize_parser,
    cmd_monitor,
    cmd_market_timing,
    cmd_self_optimize,
    cmd_sync,
    cmd_track,
)
from .diagnose import cmd_diagnose, cmd_workflow
from .portfolio import cmd_daily, cmd_trade, cmd_watchlist
from .screen import cmd_screen
from .simulate import _simulate_narrate_text, _simulate_print_narrative, cmd_simulate
from .strategy_alias import STRATEGY_ALIAS, STRATEGY_CHOICES

__all__ = [
    # analyze
    "cmd_analyze",
    "cmd_score",
    "analyze_core",
    # screen
    "cmd_screen",
    # diagnose
    "cmd_diagnose",
    "cmd_workflow",
    # portfolio
    "cmd_watchlist",
    "cmd_trade",
    "cmd_daily",
    # data
    "cmd_sync",
    "cmd_self_optimize",
    "add_self_optimize_parser",
    "cmd_track",
    "cmd_monitor",
    "cmd_market_timing",
    # backtest
    "cmd_backtest",
    "cmd_verify_v10",
    "add_verify_v10_parser",
    "cmd_simulate",
    "_shaofu_result_to_dict",
    "_portfolio_result_to_dict",
    "_shaofu_portfolio_to_dict",
    "_b1_b2_pool_to_dict",
    "STRATEGY_ALIAS",
    "STRATEGY_CHOICES",
]

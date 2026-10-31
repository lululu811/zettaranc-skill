"""
少妇战法回测 —— **兼容层**（DEPRECATED）。

实现已迁至 :mod:`modules.backtest.shaofu`。本 module 只做两件事：

1. 重新导出已迁走的 4 个符号（``ShaofuBacktestResult`` / ``_calc_metrics`` /
   ``backtest_shaofu_single`` / ``summary_text``），让旧导入路径继续可用
   —— 包已发布到 PyPI，外部调用方不能突然 ImportError。
2. 组合回测已迁至 :mod:`modules.backtest.portfolio`（``PortfolioBacktestEngine``
   真组合：共享资金池 + 费率 + 仓位上限）。原先的"各标的独立回测后按
   1/max_concurrent 加权平均资金曲线"等权组合实现已删除——它不建模资金竞争
   与交易费用，收益数字与真实组合不可比（ADR-0002 决策 1，阶段 4）。

新代码请直接调用 :mod:`modules.backtest`：
    from modules.backtest import backtest_shaofu_single
"""

from __future__ import annotations

import logging

from .backtest.shaofu import (
    ShaofuBacktestResult,
    _calc_metrics,
    backtest_shaofu_single,
    summary_text,
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="少妇战法六步闭环回测")
    subparsers = parser.add_subparsers(dest="command")

    # 单股回测
    single_parser = subparsers.add_parser("single", help="单股回测")
    single_parser.add_argument("ts_code", help="股票代码")
    single_parser.add_argument("--days", type=int, default=250, help="回测天数")

    args = parser.parse_args()

    if args.command == "single":
        result = backtest_shaofu_single(args.ts_code, days=args.days)
        print(summary_text(result))

    else:
        parser.print_help()


__all__ = [
    "ShaofuBacktestResult",
    "_calc_metrics",
    "backtest_shaofu_single",
    "summary_text",
]

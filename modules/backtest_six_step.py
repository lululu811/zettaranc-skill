"""
少妇战法回测 —— **兼容层**（DEPRECATED）。

实现已迁至 :mod:`modules.backtest.shaofu`。本 module 只做两件事：

1. 重新导出已迁走的 4 个符号（``ShaofuBacktestResult`` / ``_calc_metrics`` /
   ``backtest_shaofu_single`` / ``summary_text``），让旧导入路径继续可用
   —— 包已发布到 PyPI，外部调用方不能突然 ImportError。
2. 暂留 ``backtest_shaofu_portfolio``。它是"各标的独立回测后加权平均资金曲线"
   的**等权组合**实现（无共享资金池、无费率），与
   :class:`modules.backtest.portfolio.PortfolioBacktestEngine` 的真组合语义不同。
   ADR-0002 决策 1 已定：由真组合取代它——替换发生在 BacktestRunner 阶段 4。

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
from .core.metrics import compute_drawdown, compute_sharpe, daily_returns
from .loop_engine import LoopConfig

logger = logging.getLogger(__name__)


def backtest_shaofu_portfolio(
    ts_codes: list[str],
    days: int = 250,
    config: LoopConfig | None = None,
    max_concurrent: int = 5,
    total_capital: float = 1_000_000,
) -> dict:
    """
    多股票组合回测（等权组合实现）。

    .. deprecated::
        这是"各标的独立回测后按 1/max_concurrent 加权平均资金曲线"的实现，
        **不建模**共享资金池与交易费用，因此给出的收益数字与
        :class:`modules.backtest.portfolio.PortfolioBacktestEngine`（真组合）
        不可比。ADR-0002 决策 1：由真组合取代。

    Args:
        ts_codes: 股票代码列表
        days: 回测天数
        config: 策略参数
        max_concurrent: 最多同时持有几只
        total_capital: 总资金

    Returns:
        {
            "results": list[ShaofuBacktestResult],
            "total_return": float,
            "total_trades": int,
            "overall_win_rate": float,
            "max_drawdown": float,
            "sharpe_ratio": float,
            "equity_curve": list[float],
        }
    """
    # 取消代理
    from .core.net import disable_proxy

    disable_proxy()

    # 1. 逐股回测
    results: list[ShaofuBacktestResult] = []
    for code in ts_codes:
        r = backtest_shaofu_single(code, days=days, config=config)
        results.append(r)

    # 2. 汇总统计
    all_trades_count = sum(r.total_trades for r in results)
    all_win = sum(r.win_count for r in results)
    overall_win_rate = all_win / all_trades_count if all_trades_count > 0 else 0.0

    # 3. 合并资金曲线（加权平均，按 max_concurrent 分配权重）
    #    每只股票分配 1/max_concurrent 的权重
    active_count = min(len(ts_codes), max_concurrent)
    weight = 1.0 / active_count if active_count > 0 else 1.0

    # 找到最长的资金曲线长度
    curves = [r.equity_curve for r in results if r.equity_curve]
    if not curves:
        return {
            "results": results,
            "total_return": 0.0,
            "total_trades": 0,
            "overall_win_rate": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "equity_curve": [100.0],
        }

    max_len = max(len(c) for c in curves)

    # 加权合并：每条曲线按 weight 加权，不足的用最后一个值填充
    merged_curve: list[float] = []
    for i in range(max_len):
        val = 0.0
        for c in curves:
            point = c[i] if i < len(c) else c[-1]
            val += point * weight
        merged_curve.append(val)

    # 4. 从合并曲线计算组合级回撤
    max_dd, _ = compute_drawdown(merged_curve)

    # 5. 组合级收益率和夏普
    total_return = (merged_curve[-1] / 100.0) - 1.0 if merged_curve else 0.0

    # 夏普比率：用每日（逐点）收益率
    sharpe = 0.0
    if len(merged_curve) > 1:
        daily_rets = daily_returns(merged_curve)
        sharpe = compute_sharpe(daily_rets)

    return {
        "results": results,
        "total_return": total_return,
        "total_trades": all_trades_count,
        "overall_win_rate": overall_win_rate,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "equity_curve": merged_curve,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="少妇战法六步闭环回测")
    subparsers = parser.add_subparsers(dest="command")

    # 单股回测
    single_parser = subparsers.add_parser("single", help="单股回测")
    single_parser.add_argument("ts_code", help="股票代码")
    single_parser.add_argument("--days", type=int, default=250, help="回测天数")

    # 组合回测
    portfolio_parser = subparsers.add_parser("portfolio", help="组合回测")
    portfolio_parser.add_argument("ts_codes", nargs="+", help="股票代码列表")
    portfolio_parser.add_argument("--days", type=int, default=250, help="回测天数")
    portfolio_parser.add_argument("--max-concurrent", type=int, default=5, help="最多同时持有")
    portfolio_parser.add_argument("--capital", type=float, default=1_000_000, help="总资金")

    args = parser.parse_args()

    if args.command == "single":
        result = backtest_shaofu_single(args.ts_code, days=args.days)
        print(summary_text(result))

    elif args.command == "portfolio":
        port_result = backtest_shaofu_portfolio(
            args.ts_codes,
            days=args.days,
            max_concurrent=args.max_concurrent,
            total_capital=args.capital,
        )
        print(f"{'=' * 60}")
        print("少妇战法组合回测结果")
        print(f"{'=' * 60}")
        print(f"股票数量:     {len(args.ts_codes)}")
        print(f"总交易次数:   {port_result['total_trades']}")
        print(f"整体胜率:     {port_result['overall_win_rate']:.1%}")
        print(f"累计收益:     {port_result['total_return']:+.2%}")
        print(f"最大回撤:     {port_result['max_drawdown']:.2%}")
        print(f"夏普比率:     {port_result['sharpe_ratio']:.2f}")
        print(f"{'=' * 60}")
        print("\n各股明细:")
        for r in port_result["results"]:
            status = "有交易" if r.total_trades > 0 else "无交易"
            print(f"  {r.ts_code}: {status} {r.total_trades}笔 胜率{r.win_rate:.0%} 收益{r.total_return:+.2%}")

    else:
        parser.print_help()


__all__ = [
    "ShaofuBacktestResult",
    "_calc_metrics",
    "backtest_shaofu_single",
    "backtest_shaofu_portfolio",
    "summary_text",
]

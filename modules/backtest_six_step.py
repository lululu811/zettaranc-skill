"""
少妇战法六步闭环回测模块

基于 ShaofuLoopEngine 的回测封装，支持单股票和组合回测。
六步 SOP：择时 -> 选股 -> 等 B1 -> 设止损 -> 止盈(卤煮) -> 离场(BBI两日破位)
"""

from typing import Optional
import os
import math
from dataclasses import dataclass, field

from .loop_engine import ShaofuLoopEngine, LoopConfig, LoopTrade
from .indicators import DailyData, get_kline_data


@dataclass
class ShaofuBacktestResult:
    """少妇战法回测结果"""

    ts_code: str
    trades: list[LoopTrade] = field(default_factory=list)  # 所有完成的交易
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0  # 胜率
    avg_pnl: float = 0  # 平均盈亏%
    avg_win: float = 0  # 平均盈利%
    avg_loss: float = 0  # 平均亏损%
    max_win: float = 0  # 最大单笔盈利%
    max_loss: float = 0  # 最大单笔亏损%
    avg_holding_days: float = 0  # 平均持仓天数
    profit_factor: float = 0  # 盈亏比（总盈利/总亏损）
    total_return: float = 0  # 累计收益%
    max_drawdown: float = 0  # 最大回撤%
    sharpe_ratio: float = 0  # 夏普比率
    equity_curve: list[float] = field(default_factory=list)  # 资金曲线


def _calc_metrics(result: ShaofuBacktestResult) -> None:
    """
    从交易列表计算所有统计指标

    Args:
        result: 回测结果对象（trades 字段需已填充）
    """
    trades = result.trades
    if not trades:
        return

    result.total_trades = len(trades)

    # 盈亏统计
    pnl_list = [t.pnl_pct for t in trades]
    win_pnls = [p for p in pnl_list if p > 0]
    loss_pnls = [p for p in pnl_list if p < 0]

    result.win_count = len(win_pnls)
    result.loss_count = len(loss_pnls)
    result.win_rate = result.win_count / result.total_trades if result.total_trades > 0 else 0.0

    # 平均盈亏
    result.avg_pnl = sum(pnl_list) / result.total_trades
    result.avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    result.avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0

    # 最大单笔
    result.max_win = max(pnl_list) if pnl_list else 0.0
    result.max_loss = min(pnl_list) if pnl_list else 0.0

    # 平均持仓天数
    holding_days = [t.holding_days for t in trades if hasattr(t, "holding_days")]
    if holding_days:
        result.avg_holding_days = sum(holding_days) / len(holding_days)

    # 盈亏比（总盈利 / 总亏损的绝对值）
    total_profit = sum(win_pnls)
    total_loss = abs(sum(loss_pnls))
    result.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

    # 资金曲线：从 100 开始，逐笔复利
    equity = 100.0
    curve = [equity]
    for pnl in pnl_list:
        equity *= 1 + pnl
        curve.append(equity)
    result.equity_curve = curve

    # 累计收益
    result.total_return = (equity / 100.0) - 1.0

    # 最大回撤（基于资金曲线）
    peak = curve[0]
    max_dd = 0.0
    for val in curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    result.max_drawdown = max_dd

    # 夏普比率（用每笔交易收益率，年化）
    if len(pnl_list) > 1:
        avg_ret = sum(pnl_list) / len(pnl_list)
        variance = sum((r - avg_ret) ** 2 for r in pnl_list) / (len(pnl_list) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std > 0:
            # 假设平均每笔交易间隔约 10-20 天，年化约 252/avg_days 次交易
            # 保守用 sqrt(252) 做标准化
            result.sharpe_ratio = (avg_ret / std) * math.sqrt(252)


def backtest_shaofu_single(
    ts_code: str,
    days: int = 250,
    config: LoopConfig | None = None,
    klines: list[DailyData] | None = None,
) -> ShaofuBacktestResult:
    """
    单股票少妇战法回测

    Args:
        ts_code: 股票代码
        days: 回测天数
        config: 策略参数，None 使用默认
        klines: 外部传入的 K 线数据，None 则从数据库读取

    Returns:
        ShaofuBacktestResult with all metrics
    """
    # 取消代理（与 backtest.py 保持一致）
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

    # 1. 获取 K 线数据
    if klines is None:
        klines = get_kline_data(ts_code, days)

    result = ShaofuBacktestResult(ts_code=ts_code)

    if not klines or len(klines) < 30:
        return result

    # 2. 创建引擎并运行
    engine = ShaofuLoopEngine(config)
    trades = engine.run_stock(klines, ts_code=ts_code)

    if not trades:
        return result

    result.trades = trades

    # 3. 计算指标
    _calc_metrics(result)

    return result


def backtest_shaofu_portfolio(
    ts_codes: list[str],
    days: int = 250,
    config: LoopConfig | None = None,
    max_concurrent: int = 5,
    total_capital: float = 1_000_000,
) -> dict:
    """
    多股票组合回测

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
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

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
    peak = merged_curve[0]
    max_dd = 0.0
    for val in merged_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # 5. 组合级收益率和夏普
    total_return = (merged_curve[-1] / 100.0) - 1.0 if merged_curve else 0.0

    # 夏普比率：用每日（逐点）收益率
    sharpe = 0.0
    if len(merged_curve) > 1:
        daily_rets = []
        for i in range(1, len(merged_curve)):
            if merged_curve[i - 1] > 0:
                daily_rets.append((merged_curve[i] - merged_curve[i - 1]) / merged_curve[i - 1])
        if daily_rets:
            avg_r = sum(daily_rets) / len(daily_rets)
            var = sum((r - avg_r) ** 2 for r in daily_rets) / (len(daily_rets) - 1)
            std = math.sqrt(var) if var > 0 else 0.0
            if std > 0:
                sharpe = (avg_r / std) * math.sqrt(252)

    return {
        "results": results,
        "total_return": total_return,
        "total_trades": all_trades_count,
        "overall_win_rate": overall_win_rate,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "equity_curve": merged_curve,
    }


def summary_text(result: ShaofuBacktestResult) -> str:
    """
    格式化单股回测结果为可读文本

    Args:
        result: 少妇战法回测结果

    Returns:
        格式化字符串
    """
    lines = [
        f"{'=' * 60}",
        f"少妇战法回测结果: {result.ts_code}",
        f"{'=' * 60}",
        f"总交易次数:   {result.total_trades}",
        f"盈利次数:     {result.win_count}",
        f"亏损次数:     {result.loss_count}",
        f"胜率:         {result.win_rate:.1%}",
        f"盈亏比:       {result.profit_factor:.2f}",
        f"平均盈亏:     {result.avg_pnl:+.2%}",
        f"平均盈利:     {result.avg_win:+.2%}",
        f"平均亏损:     {result.avg_loss:+.2%}",
        f"最大单笔盈:   {result.max_win:+.2%}",
        f"最大单笔亏:   {result.max_loss:+.2%}",
        f"平均持仓天数: {result.avg_holding_days:.1f}",
        f"累计收益:     {result.total_return:+.2%}",
        f"最大回撤:     {result.max_drawdown:.2%}",
        f"夏普比率:     {result.sharpe_ratio:.2f}",
        f"{'=' * 60}",
    ]

    if result.trades:
        lines.append("最近5笔交易:")
        for t in result.trades[-5:]:
            pnl = t.pnl_pct if hasattr(t, "pnl_pct") else 0.0
            marker = "+" if pnl > 0 else ""
            lines.append(f"  {t.entry_date}->{t.exit_date or '持有中'} {marker}{pnl:.2f}%")

    return "\n".join(lines)


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
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

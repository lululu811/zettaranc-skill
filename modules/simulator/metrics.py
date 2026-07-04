#!/usr/bin/env python3
"""
专业回测绩效指标模块。

基于资金曲线、基准曲线与成交记录计算常用量化评估指标。
所有收益类指标均为小数形式（如 0.05 表示 5%）。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any


@dataclass
class PerformanceMetrics:
    """专业回测绩效指标。"""

    total_return: float = 0.0
    annualized_return: float = 0.0
    benchmark_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    gain_loss_ratio: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    volatility_annual: float = 0.0


def _daily_returns(values: list[float]) -> list[float]:
    """从序列计算日收益率。"""
    rets: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        cur = values[i]
        if prev == 0:
            rets.append(0.0)
        else:
            rets.append((cur - prev) / prev)
    return rets


def _compute_drawdown(values: list[float]) -> tuple[float, int]:
    """
    计算最大回撤与最长回撤持续时间。

    最大回撤以正值返回（如 0.05 表示回撤 5%）。
    持续时间为「高点 → 下一个新高点」之间的最长交易日数。
    """
    if not values:
        return 0.0, 0

    peak = values[0]
    peak_idx = 0
    max_dd = 0.0
    max_duration = 0

    for i, val in enumerate(values):
        if val > peak:
            duration = i - peak_idx
            if duration > max_duration:
                max_duration = duration
            peak = val
            peak_idx = i

        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return max_dd, max_duration


def calculate_metrics(
    equity_curve: list[dict[str, Any]],
    benchmark_curve: list[dict[str, Any]],
    trades: list[Any],
) -> PerformanceMetrics:
    """
    计算回测绩效指标。

    Args:
        equity_curve: 资金曲线，每个元素至少包含 ``date`` 与 ``equity``。
        benchmark_curve: 基准曲线，每个元素至少包含 ``date`` 与 ``close``。
        trades: 成交记录列表，通常为由 ``TradeRecord`` 构成的序列。

    Returns:
        PerformanceMetrics: 各项绩效指标。
    """
    metrics = PerformanceMetrics()

    if not equity_curve:
        return metrics

    equities = [float(p.get("equity", 0)) for p in equity_curve]
    initial = equities[0]
    final = equities[-1]

    if initial > 0:
        metrics.total_return = (final / initial) - 1.0

    n_periods = len(equity_curve) - 1
    if n_periods > 0 and initial > 0:
        metrics.annualized_return = (final / initial) ** (252.0 / n_periods) - 1.0

    daily_rets = _daily_returns(equities)

    # 年化波动率
    if len(daily_rets) > 1:
        metrics.volatility_annual = statistics.stdev(daily_rets) * math.sqrt(252.0)

    # 夏普比率
    if daily_rets:
        avg_ret = sum(daily_rets) / len(daily_rets)
        std_ret = statistics.stdev(daily_rets) if len(daily_rets) > 1 else 0.0
        if std_ret > 0:
            metrics.sharpe_ratio = (avg_ret / std_ret) * math.sqrt(252.0)

    # 索提诺比率：仅使用负收益计算下行标准差
    if daily_rets:
        avg_ret = sum(daily_rets) / len(daily_rets)
        negative_rets = [r for r in daily_rets if r < 0]
        std_neg = statistics.stdev(negative_rets) if len(negative_rets) > 1 else 0.0
        if std_neg > 0:
            metrics.sortino_ratio = (avg_ret / std_neg) * math.sqrt(252.0)
        elif avg_ret > 0:
            # 无下行波动但平均收益为正，按正无穷表示
            metrics.sortino_ratio = float("inf")

    # 最大回撤与持续时间
    max_dd, max_duration = _compute_drawdown(equities)
    metrics.max_drawdown = max_dd
    metrics.max_drawdown_duration = max_duration

    # Calmar 比率
    if metrics.max_drawdown != 0:
        metrics.calmar_ratio = metrics.annualized_return / abs(metrics.max_drawdown)

    # 基准收益与 beta/alpha
    if benchmark_curve:
        bench_values = [float(p.get("close", 0)) for p in benchmark_curve]
        if bench_values and bench_values[0] > 0:
            metrics.benchmark_return = (bench_values[-1] / bench_values[0]) - 1.0

        bench_rets = _daily_returns(bench_values)
        if len(daily_rets) == len(bench_rets) and len(daily_rets) > 1:
            try:
                slope, intercept = statistics.linear_regression(bench_rets, daily_rets)
                metrics.beta = slope
                # alpha 为日超额收益，年化后更直观
                metrics.alpha = intercept * 252.0
            except statistics.StatisticsError:
                metrics.beta = 0.0
                metrics.alpha = 0.0

    # 交易统计（仅 SELL 成交）
    sell_trades = [t for t in trades if getattr(t, "action", None) == "SELL"]
    if sell_trades:
        pnls = [float(getattr(t, "pnl", 0)) for t in sell_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        metrics.win_rate = len(wins) / len(pnls) if pnls else 0.0

        total_profit = sum(wins)
        total_loss = abs(sum(losses))
        metrics.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        metrics.avg_win = statistics.mean(wins) if wins else 0.0
        metrics.avg_loss = abs(statistics.mean(losses)) if losses else 0.0
        metrics.gain_loss_ratio = (
            metrics.avg_win / metrics.avg_loss if metrics.avg_loss > 0 else 0.0
        )

        # 最大连胜 / 连亏
        max_wins = 0
        max_losses = 0
        cur_wins = 0
        cur_losses = 0
        for pnl in pnls:
            if pnl > 0:
                cur_wins += 1
                cur_losses = 0
                if cur_wins > max_wins:
                    max_wins = cur_wins
            else:
                cur_losses += 1
                cur_wins = 0
                if cur_losses > max_losses:
                    max_losses = cur_losses
        metrics.max_consecutive_wins = max_wins
        metrics.max_consecutive_losses = max_losses

    return metrics

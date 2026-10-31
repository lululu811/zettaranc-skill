"""
绩效指标计算公共逻辑（v3.9.0 技术债务清理）

统一的绩效指标计算模块，供 simulator/metrics.py、verify/pipeline.py 及其他模块使用。
包含完整的 20 字段 PerformanceMetrics 与 calculate_metrics 函数。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace
from collections.abc import Sequence
from typing import Any

# 每年交易日数（A 股年化因子统一常量）
TRADING_DAYS_PER_YEAR = 252


@dataclass
class PerformanceMetrics:
    """专业回测绩效指标（20 字段）。"""

    # 收益类
    total_return: float = 0.0  # 总收益率
    annualized_return: float = 0.0  # 年化收益率
    benchmark_return: float = 0.0  # 基准收益率
    alpha: float = 0.0  # Jensen's alpha（年化）
    beta: float = 0.0  # 市场 beta

    # 风险调整收益
    sharpe_ratio: float = 0.0  # 夏普比率
    sortino_ratio: float = 0.0  # 索提诺比率
    calmar_ratio: float = 0.0  # 卡尔玛比率
    max_drawdown: float = 0.0  # 最大回撤（正值）
    max_drawdown_duration: int = 0  # 最长回撤持续天数

    # 交易统计
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈亏比（总盈利/总亏损）
    avg_win: float = 0.0  # 平均盈利
    avg_loss: float = 0.0  # 平均亏损（正值）
    gain_loss_ratio: float = 0.0  # 盈亏比（avg_win / avg_loss）
    max_consecutive_wins: int = 0  # 最大连胜
    max_consecutive_losses: int = 0  # 最大连亏

    # 波动率
    volatility_annual: float = 0.0  # 年化波动率

    # 兼容字段（原 core 独有）
    total_trades: int = 0  # 总交易次数
    avg_holding_days: float = 0.0  # 平均持仓天数


def daily_returns(values: list[float]) -> list[float]:
    """
    从序列计算日收益率（v3.9.0 提取自 simulator/metrics.py）。

    当前值与前值之差除以前值，前值为 0 时记为 0。
    """
    rets: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        cur = values[i]
        if prev == 0:
            rets.append(0.0)
        else:
            rets.append((cur - prev) / prev)
    return rets


@dataclass(frozen=True)
class TradeStats:
    """逐笔交易的统计聚合（口径见 :func:`calc_trade_stats`）。

    ``avg_loss`` 与 ``max_loss`` 是**有符号的**（负值表示亏损），与逐笔盈亏
    序列同口径；需要"亏损幅度"的调用方自行取绝对值。
    """

    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0  # 有符号（负值）
    max_win: float = 0.0
    max_loss: float = 0.0  # 有符号（负值）
    profit_factor: float = 0.0
    avg_holding_days: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


def calc_trade_stats(pnls: Sequence[float], holding_days: Sequence[float] | None = None) -> TradeStats:
    """从逐笔盈亏算交易统计 —— **交易统计算法的唯一实现**。

    口径：

    - ``p > 0`` 为盈利，``p < 0`` 为亏损，``p == 0`` 为**不盈不亏**
      （计入总交易数，但既不计入盈利也不计入亏损）。
      零盈亏不是亏损——历史上有实现把它算成亏损，两边口径因此不一致。
    - ``avg_loss`` / ``max_loss`` 为有符号的负值（与输入同单位）。
    - 连胜/连亏：零盈亏的成交会**同时打断**连胜与连亏。

    Args:
        pnls: 逐笔盈亏序列（单位随调用方：金额或百分比）。
        holding_days: 与 ``pnls`` 对齐的持仓天数序列，可选。

    Returns:
        TradeStats。
    """
    if not pnls:
        return TradeStats()

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = len(pnls)
    win_count, loss_count = len(wins), len(losses)

    total_profit = sum(wins)
    total_loss = abs(sum(losses))

    stats = TradeStats(
        total_trades=total,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_count / total if total else 0.0,
        avg_pnl=sum(pnls) / total,
        avg_win=sum(wins) / win_count if win_count else 0.0,
        avg_loss=sum(losses) / loss_count if loss_count else 0.0,
        max_win=max(pnls),
        max_loss=min(pnls),
        profit_factor=total_profit / total_loss if total_loss > 0 else float("inf"),
    )

    if holding_days:
        stats = replace(stats, avg_holding_days=sum(holding_days) / len(holding_days))

    # 连胜 / 连亏：零盈亏的成交同时打断两者
    max_wins = max_losses = 0
    cur_wins = cur_losses = 0
    for pnl in pnls:
        if pnl > 0:
            cur_wins += 1
            cur_losses = 0
            max_wins = max(max_wins, cur_wins)
        elif pnl < 0:
            cur_losses += 1
            cur_wins = 0
            max_losses = max(max_losses, cur_losses)
        else:
            cur_wins = 0
            cur_losses = 0
    stats = replace(stats, max_consecutive_wins=max_wins, max_consecutive_losses=max_losses)

    return stats


@dataclass(frozen=True)
class CurveStats:
    """净值序列的曲线类指标。"""

    total_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0


def calc_curve_metrics(values: list[float], trading_days: int | None = None) -> CurveStats:
    """从净值序列算曲线类指标 —— **曲线指标算法的唯一实现**。

    Args:
        values: 净值序列（升序）。
        trading_days: 年化分母（交易日数）。``None`` 或 <= 0 表示不做年化。
            **调用方必须显式传入**——不同路径的序列长度不同（单股按 K 线天数、
            组合按净值序列长度），年化结果因此不同。

    Returns:
        CurveStats。
    """
    if not values or len(values) < 2:
        return CurveStats()

    initial, final = values[0], values[-1]
    total_return = (final / initial - 1.0) if initial > 0 else 0.0

    annualized = 0.0
    if trading_days and trading_days > 0 and initial > 0:
        annualized = (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / trading_days) - 1.0

    max_dd, _ = compute_drawdown(values)
    sharpe = compute_sharpe(daily_returns(values))

    return CurveStats(
        total_return=total_return,
        annualized_return=annualized,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
    )


def _is_closed_trade(trade: Any) -> bool:
    """判断一笔成交是否计入交易统计。

    - 带 ``action`` 字段（模拟器的 ``TradeRecord``、dict 代理）：只有 SELL 计入。
    - 不带 ``action`` 字段（回测的 ``LoopTrade``）：按"已平仓"判定——
      ``exit_date`` 非空即为已平仓。未平仓的持仓 ``exit_date`` 为空且 pnl_pct 为 0。
    """
    action = getattr(trade, "action", None)
    if action is not None:
        return action == "SELL"
    return bool(getattr(trade, "exit_date", ""))


def _trade_pnl(trade: Any) -> float:
    """取一笔成交的盈亏。

    优先用绝对金额 ``pnl``；没有时退回 ``pnl_pct``（此时统计口径随输入单位）。
    """
    pnl = getattr(trade, "pnl", None)
    if pnl is None:
        pnl = getattr(trade, "pnl_pct", 0)
    return float(pnl or 0.0)


def compute_sharpe(returns: list[float], periods_per_year: float = TRADING_DAYS_PER_YEAR) -> float:
    """计算夏普比率（sample std，不减无风险利率）。

    Args:
        returns: 收益率序列（日收益率或其他频率）。
        periods_per_year: 年化因子，默认 252（A 股交易日）。

    Returns:
        年化夏普比率；序列长度不足或标准差为零时返回 0.0。
    """
    if len(returns) < 2:
        return 0.0
    avg_ret = sum(returns) / len(returns)
    variance = sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1)
    std_ret = variance**0.5
    if std_ret > 0:
        return (avg_ret / std_ret) * (periods_per_year**0.5)
    return 0.0


def compute_drawdown(values: list[float]) -> tuple[float, int]:
    """
    计算最大回撤与最长回撤持续时间（v3.9.0 提取自 simulator/metrics.py）。

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
    计算回测绩效指标 —— 所有回测路径的统一入口。

    计算口径：
    - 波动率与夏普/索提诺使用 sample std（``statistics.stdev``）
    - 夏普/索提诺不减无风险利率
    - 支持 benchmark 曲线计算 alpha/beta
    - 交易统计仅统计**已平仓**成交：带 ``action`` 字段的按 ``action == "SELL"``，
      不带 ``action`` 字段的（回测的 ``LoopTrade``）按 ``exit_date`` 非空判定
    - 零盈亏的成交（``pnl == 0``）不计入盈利也不计入亏损，但计入总交易数

    Args:
        equity_curve: 资金曲线，每个元素至少包含 ``date`` 与 ``equity``。
        benchmark_curve: 基准曲线，每个元素至少包含 ``date`` 与 ``close``。
        trades: 成交记录列表，通常为 ``TradeRecord`` 序列；也可传 ``LoopTrade``
            （此时盈亏取 ``pnl_pct``，统计口径随输入单位）。

    Returns:
        PerformanceMetrics: 各项绩效指标。
    """
    # 注意：当前函数签名接受 dict 列表格式（历史原因）
    # 未来可以扩展为接受 (equity_curve: list[float], trades: list[Any], trading_days: int)
    # 以实现更清晰的统一接口
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
        metrics.annualized_return = (final / initial) ** (TRADING_DAYS_PER_YEAR / n_periods) - 1.0

    daily_rets = daily_returns(equities)

    # 年化波动率
    if len(daily_rets) > 1:
        metrics.volatility_annual = statistics.stdev(daily_rets) * math.sqrt(TRADING_DAYS_PER_YEAR)

    # 夏普比率（不减无风险利率）
    metrics.sharpe_ratio = compute_sharpe(daily_rets)

    # 索提诺比率：仅使用负收益计算下行标准差
    if daily_rets:
        avg_ret = sum(daily_rets) / len(daily_rets)
        negative_rets = [r for r in daily_rets if r < 0]
        std_neg = statistics.stdev(negative_rets) if len(negative_rets) > 1 else 0.0
        if std_neg > 0:
            metrics.sortino_ratio = (avg_ret / std_neg) * math.sqrt(TRADING_DAYS_PER_YEAR)
        elif avg_ret > 0:
            # 无下行波动但平均收益为正，按正无穷表示
            metrics.sortino_ratio = float("inf")

    # 最大回撤与持续时间
    max_dd, max_duration = compute_drawdown(equities)
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

        bench_rets = daily_returns(bench_values)
        if len(daily_rets) == len(bench_rets) and len(daily_rets) > 1:
            try:
                slope, intercept = statistics.linear_regression(bench_rets, daily_rets)
                metrics.beta = slope
                # alpha 为日超额收益，年化后更直观
                metrics.alpha = intercept * TRADING_DAYS_PER_YEAR
            except statistics.StatisticsError:
                metrics.beta = 0.0
                metrics.alpha = 0.0

    # 交易统计（仅已平仓成交）
    closed_trades = [t for t in trades if _is_closed_trade(t)]
    pnls = [_trade_pnl(t) for t in closed_trades]
    holding_days_list = [float(getattr(t, "holding_days", 0) or 0) for t in closed_trades]
    stats = calc_trade_stats(pnls, holding_days_list)

    metrics.total_trades = stats.total_trades
    metrics.win_rate = stats.win_rate
    metrics.profit_factor = stats.profit_factor
    metrics.avg_win = stats.avg_win
    # calc_trade_stats 的 avg_loss 是有符号的负值；这里取幅度（正值）
    metrics.avg_loss = abs(stats.avg_loss)
    metrics.gain_loss_ratio = metrics.avg_win / metrics.avg_loss if metrics.avg_loss > 0 else 0.0
    metrics.max_consecutive_wins = stats.max_consecutive_wins
    metrics.max_consecutive_losses = stats.max_consecutive_losses
    metrics.avg_holding_days = stats.avg_holding_days

    return metrics


def calculate_performance_metrics(
    equity_curve: list[float],
    trades: list[dict] | None = None,
    risk_free_rate: float = 0.03,
    periods_per_year: int = 252,
) -> PerformanceMetrics:
    """
    兼容别名：将简单接口转换为 ``calculate_metrics`` 格式后调用。

    注意：此函数保持旧接口签名不变，但返回类型为新的 20 字段 PerformanceMetrics。
    计算口径以 ``calculate_metrics`` 为准（sample std、不减无风险利率）。

    Args:
        equity_curve: 资金曲线（按时间顺序的浮点数列表）
        trades: 交易记录列表（可选，每个元素为 dict，含 ``pnl`` 等键）
        risk_free_rate: 无风险利率（保留参数，实际不参与计算）
        periods_per_year: 每年的周期数（保留参数，实际使用 252）

    Returns:
        PerformanceMetrics
    """
    # 将 float 列表转换为 dict 列表以适配 calculate_metrics 接口
    eq_dicts = [{"equity": v} for v in equity_curve]

    # 将 dict trades 转换为带 action 属性的对象
    class _TradeProxy:
        """轻量代理，让 dict 形式的 trade 可被 calculate_metrics 消费。"""

        def __init__(self, d: dict) -> None:
            self.action = d.get("action", "SELL")
            self.pnl = d.get("pnl", 0)
            self.holding_days = d.get("holding_days", 0)

    trade_objs = [_TradeProxy(t) for t in trades] if trades else []

    return calculate_metrics(eq_dicts, [], trade_objs)


__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "PerformanceMetrics",
    "TradeStats",
    "CurveStats",
    "calc_trade_stats",
    "calc_curve_metrics",
    "calculate_metrics",
    "calculate_metrics_unified",
    "calculate_performance_metrics",
    "compute_sharpe",
    "daily_returns",
    "compute_drawdown",
]


def calculate_metrics_unified(
    net_values: list[float],
    trades: list[Any],
    trading_days: int,
    *,
    pnl_unit: str = "pct",
) -> PerformanceMetrics:
    """统一绩效指标计算 —— 所有回测路径的唯一入口。

    这是 calculate_metrics 的简化版本，接受净值序列而非 dict 列表。
    各回测引擎应统一输出 (net_values, trades, trading_days)，然后调用此函数。

    Args:
        net_values: 净值序列（如 [100.0, 101.5, 103.2, ...]）
        trades: 交易列表（LoopTrade 或 Trade）
        trading_days: 年化分母（交易日数）
        pnl_unit: trades 中 pnl_pct 的单位
            "pct" → LoopTrade 风格，5.0 表示 5%
            "frac" → Trade 风格，0.05 表示 5%

    Returns:
        PerformanceMetrics: 各项绩效指标

    口径说明：
        - Sharpe 使用日收益率年化（sqrt(252)），与 portfolio/single 一致
        - 交易统计走 calc_trade_stats（唯一实现）
        - 曲线指标走 calc_curve_metrics（唯一实现）
    """
    metrics = PerformanceMetrics()

    if not net_values or len(net_values) < 2:
        return metrics

    initial = net_values[0]
    final = net_values[-1]

    if initial > 0:
        metrics.total_return = (final / initial) - 1.0

    n_periods = len(net_values) - 1
    if n_periods > 0 and initial > 0:
        metrics.annualized_return = (final / initial) ** (TRADING_DAYS_PER_YEAR / n_periods) - 1.0

    daily_rets = daily_returns(net_values)

    # 年化波动率
    if len(daily_rets) > 1:
        metrics.volatility_annual = statistics.stdev(daily_rets) * math.sqrt(TRADING_DAYS_PER_YEAR)

    # 夏普比率（日收益率年化，sqrt(252)）
    metrics.sharpe_ratio = compute_sharpe(daily_rets, periods_per_year=TRADING_DAYS_PER_YEAR)

    # 索提诺比率
    if daily_rets:
        avg_ret = sum(daily_rets) / len(daily_rets)
        negative_rets = [r for r in daily_rets if r < 0]
        std_neg = statistics.stdev(negative_rets) if len(negative_rets) > 1 else 0.0
        if std_neg > 0:
            metrics.sortino_ratio = (avg_ret / std_neg) * math.sqrt(TRADING_DAYS_PER_YEAR)
        elif avg_ret > 0:
            metrics.sortino_ratio = float("inf")

    # 最大回撤与持续时间
    max_dd, max_duration = compute_drawdown(net_values)
    metrics.max_drawdown = max_dd
    metrics.max_drawdown_duration = max_duration

    # Calmar 比率
    if metrics.max_drawdown != 0:
        metrics.calmar_ratio = metrics.annualized_return / abs(metrics.max_drawdown)

    # 交易统计
    if trades:
        # 根据 pnl_unit 调整 pnl_pct
        if pnl_unit == "pct":
            # LoopTrade 风格：5.0 表示 5%，需要除以 100 转为 calc_trade_stats 期望的分数
            pnls = [t.pnl_pct / 100.0 for t in trades if _is_closed_trade(t)]
        else:
            # Trade 风格：0.05 表示 5%，已经是分数
            pnls = [t.pnl_pct for t in trades if _is_closed_trade(t)]

        holding_days_list: list[float] = []
        for t in trades:
            if _is_closed_trade(t):
                hd = getattr(t, "holding_days", None) or getattr(t, "hold_days", 0)
                holding_days_list.append(float(hd) if hd is not None else 0.0)

        stats = calc_trade_stats(pnls, holding_days_list if holding_days_list else None)

        metrics.total_trades = stats.total_trades
        metrics.win_rate = stats.win_rate
        metrics.profit_factor = stats.profit_factor
        metrics.avg_win = abs(stats.avg_win) * 100  # 转为百分数
        metrics.avg_loss = abs(stats.avg_loss) * 100  # 转为百分数（正值）
        metrics.max_consecutive_wins = stats.max_consecutive_wins
        metrics.max_consecutive_losses = stats.max_consecutive_losses
        metrics.avg_holding_days = stats.avg_holding_days

    return metrics

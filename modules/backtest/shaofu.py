"""少妇战法（shaofu）单股回测。

本 module 是 shaofu 回测的**唯一实现**。原先这些实现位于
``modules/backtest_six_step.py``，而那个 module 又被"新"的
``modules/backtest`` 包反过来 import——依赖方向倒挂。v4.8.0 起实现迁到这里，
``modules/backtest_six_step.py`` 降级为兼容 re-export。

六步 SOP：择时 -> 选股 -> 等 B1 -> 设止损 -> 止盈(卤煮) -> 离场(BBI两日破位)。
策略与离场规则由 :class:`modules.loop_engine.ShaofuLoopEngine` 提供，
本 module 只负责"跑一次 + 算指标 + 格式化"。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..core.metrics import TRADING_DAYS_PER_YEAR, compute_drawdown, compute_sharpe
from ..core.net import disable_proxy
from ..indicators import DailyData, get_kline_data
from ..loop_engine import LoopConfig, LoopTrade, ShaofuLoopEngine

logger = logging.getLogger(__name__)


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

    # 资金曲线：从 100 开始，逐笔按实际仓位复利
    # 注意：pnl_pct 是百分比数值（如 5.0 表示 5%），需除以 100 转为小数比例
    equity = 100.0
    curve = [equity]
    for t in trades:
        pnl = t.pnl_pct
        pos_pct = getattr(t, "position_pct", 1.0) or 1.0
        equity *= 1 + (pnl / 100.0) * pos_pct
        curve.append(equity)
    result.equity_curve = curve

    # 累计收益
    result.total_return = (equity / 100.0) - 1.0

    # 最大回撤（基于资金曲线）
    max_dd, _ = compute_drawdown(curve)
    result.max_drawdown = max_dd

    # 夏普比率（用每笔交易收益率，按交易频率年化）
    if len(pnl_list) >= 3:
        avg_hold = result.avg_holding_days if result.avg_holding_days > 0 else 10.0
        result.sharpe_ratio = compute_sharpe(pnl_list, periods_per_year=TRADING_DAYS_PER_YEAR / avg_hold)


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
    disable_proxy()

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
        # avg_pnl / avg_win / avg_loss / max_win / max_loss 是百分数
        # （由 LoopTrade.pnl_pct 聚合而来），不能用 :.2%（那会再乘 100）
        f"平均盈亏:     {result.avg_pnl:+.2f}%",
        f"平均盈利:     {result.avg_win:+.2f}%",
        f"平均亏损:     {result.avg_loss:+.2f}%",
        f"最大单笔盈:   {result.max_win:+.2f}%",
        f"最大单笔亏:   {result.max_loss:+.2f}%",
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


__all__ = [
    "ShaofuBacktestResult",
    "_calc_metrics",
    "backtest_shaofu_single",
    "summary_text",
]

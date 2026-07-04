#!/usr/bin/env python3
"""
少女/少妇模拟器核心编排器。

逐日遍历历史数据：
1. 判断市场环境 → 决定当日最大开仓数
2. 选股/信号过滤 → 得到候选买入列表
3. 对候选股按评分排序，依次开仓（直到达到仓位上限）
4. 检查已有持仓的退出条件 → 执行卖出
5. 记录资金曲线与成交
6. 输出统计指标

设计原则：
- 只做规则执行，不做预测
- 使用收盘价决策，次日开盘价成交（避免未来函数）
- 资金管理优先：单笔风险固定，仓位动态调整
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from . import (
    MarketRegime,
    Position,
    SimulationConfig,
    SimulationResult,
    TradeRecord,
    SignalScore,
    SignalVerdict,
    MarketContext,
)
from ..datasource import DataSource, get_datasource
from ..indicators import DailyData
from ..screener.data import get_all_stocks, get_recent_klines
from .execution_engine import execute_buy, execute_partial_sell, execute_sell
from .exit_manager import check_exit
from .market_context import get_market_context, max_positions_allowed
from .position_sizer import build_position
from .signal_filter import filter_signals, evaluate_stock
from .metrics import calculate_metrics


@dataclass
class _SimulatorState:
    """模拟器运行时状态"""

    cash: float
    equity: float
    positions: list[Position] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    benchmark_curve: list[dict[str, Any]] = field(default_factory=list)


def _available_dates(ts_code: str, days: int, datasource: DataSource) -> list[str]:
    """获取某只股票回测区间内的所有交易日。"""
    raw = datasource.get_kline_dicts(ts_code, days=days)
    return [k["trade_date"] for k in raw]


def _load_benchmark_curve(
    dates: list[str], benchmark_code: str, datasource: DataSource
) -> list[dict[str, Any]]:
    """加载基准指数在回测区间内的收盘价曲线。"""
    if not dates or not benchmark_code:
        return []
    try:
        df = datasource.get_index_daily(benchmark_code, dates[0], dates[-1])
        if df is None or getattr(df, "empty", True):
            return []
        records = df.to_dict("records")
        date_set = set(dates)
        curve = []
        for row in sorted(records, key=lambda x: x.get("trade_date", "")):
            date = row.get("trade_date", "")
            if date in date_set:
                curve.append({"date": date, "close": float(row.get("close", 0))})
        return curve
    except Exception:
        return []


def _portfolio_value(state: _SimulatorState, date: str, klines_map: dict[str, list[DailyData]]) -> float:
    """计算当前组合市值（现金 + 持仓按收盘价估值）。"""
    value = state.cash
    for pos in state.positions:
        klines = klines_map.get(pos.ts_code)
        if not klines:
            continue
        # 找到 date 对应的 K 线
        price = next((k.close for k in klines if k.trade_date == date), 0)
        if price:
            value += pos.shares * price
    return value


def _klines_for_date(klines: list[DailyData], date: str) -> list[DailyData]:
    """截取到指定日期（含）为止的 K 线。"""
    result = []
    for k in klines:
        result.append(k)
        if k.trade_date == date:
            break
    return result


def _entry_stop_loss(klines: list[DailyData]) -> float:
    """以入场前最近 20 日低点作为止损参考。"""
    if len(klines) < 5:
        return klines[-1].low if klines else 0
    window = klines[-20:]
    return min(k.low for k in window)


def _entry_take_profit(entry_price: float, stop_loss: float, rr: float) -> float:
    risk = entry_price - stop_loss
    return entry_price + risk * rr


def _run_single_day(
    date: str,
    state: _SimulatorState,
    candidates: list[SignalScore],
    klines_map: dict[str, list[DailyData]],
    context: Any,
    config: SimulationConfig,
) -> None:
    """执行单日的买入和卖出逻辑。"""

    # ---------- 1. 先处理卖出 ----------
    remaining_positions: list[Position] = []
    for position in state.positions:
        klines = klines_map.get(position.ts_code)
        if not klines:
            remaining_positions.append(position)
            continue

        sub_klines = _klines_for_date(klines, date)
        action, sell_shares = check_exit(position, sub_klines, config)

        if action == "HOLD":
            remaining_positions.append(position)
            continue

        current_kline = sub_klines[-1]
        if action == "TAKE_PROFIT_PARTIAL":
            trade = execute_partial_sell(position, current_kline, config, sell_shares, "卤煮：达到2R减半", sub_klines)
            state.trades.append(trade)
            state.cash += trade.shares * trade.price - trade.fee
            position.shares -= sell_shares
            position.partial_exited = True
            remaining_positions.append(position)
        else:
            reason = "止损" if action == "STOP_LOSS" else "移动止盈"
            trade = execute_sell(position, current_kline, config, reason, sub_klines)
            state.trades.append(trade)
            state.cash += trade.shares * trade.price - trade.fee
            # 已平仓，不再加入 remaining_positions

    state.positions = remaining_positions

    # ---------- 2. 计算当前净值和可开仓数 ----------
    state.equity = _portfolio_value(state, date, klines_map)
    max_pos = max_positions_allowed(context, config.max_positions, config.market_neutral_max_positions)
    open_slots = max(0, max_pos - len(state.positions))

    if open_slots <= 0:
        return

    # 弱势环境降低开仓意愿
    if context.regime == MarketRegime.WEAK:
        candidates = [c for c in candidates if c.score >= config.position_score_threshold + 10]

    # ---------- 3. 按评分依次开仓 ----------
    for sig in candidates[:open_slots]:
        # 已在持仓中则跳过
        if any(p.ts_code == sig.ts_code for p in state.positions):
            continue

        klines = klines_map.get(sig.ts_code)
        if not klines:
            continue

        sub_klines = _klines_for_date(klines, date)
        if len(sub_klines) < 2:
            continue

        # 买入价：次日开盘价（当前日就是买入日，用当日 open）
        entry_price = sub_klines[-1].open
        stop_loss = _entry_stop_loss(sub_klines[:-1])
        take_profit = _entry_take_profit(entry_price, stop_loss, config.partial_take_profit_rr)

        built = build_position(
            ts_code=sig.ts_code,
            name=sig.name,
            entry_date=date,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            cash=state.cash,
            equity=state.equity,
            config=config,
        )
        if not built:
            continue
        pos: Position = built

        trade = execute_buy(pos, sub_klines[-1], config, sub_klines)
        state.trades.append(trade)
        state.cash -= trade.shares * trade.price + trade.fee
        state.positions.append(pos)


def run_simulation(
    ts_codes: list[str] | None = None,
    days: int = 250,
    config: SimulationConfig | None = None,
    datasource: DataSource | None = None,
) -> SimulationResult:
    """
    运行少女/少妇模拟器回测。

    Args:
        ts_codes: 股票池，None 则取全市场前 500 只
        days: 回测天数
        config: 模拟配置
        datasource: 数据源

    Returns:
        SimulationResult
    """
    config = config or SimulationConfig()
    ds = datasource or get_datasource()

    if ts_codes is None:
        stocks = get_all_stocks(datasource=ds)
        ts_codes = [s["ts_code"] for s in stocks[:500]]

    if not ts_codes:
        return SimulationResult(config=config, initial_capital=config.initial_capital)

    # 统一日期序列：以第一只股票的交易日期为基准
    dates = _available_dates(ts_codes[0], days, ds)
    if not dates:
        return SimulationResult(config=config, initial_capital=config.initial_capital)

    # 预加载所有 K 线
    klines_map: dict[str, list[DailyData]] = {}
    for code in ts_codes:
        loaded = get_recent_klines(code, days + 60, datasource=ds)
        if loaded:
            klines_map[code] = loaded

    if not klines_map:
        return SimulationResult(config=config, initial_capital=config.initial_capital)

    state = _SimulatorState(
        cash=config.initial_capital,
        equity=config.initial_capital,
        benchmark_curve=_load_benchmark_curve(dates, config.benchmark_code, ds),
    )

    for date in dates:
        # 市场环境
        context = get_market_context(date, datasource=ds)

        # 评估候选信号
        candidates: list[SignalScore] = []
        for code in ts_codes:
            stock_klines = klines_map.get(code)
            if not stock_klines:
                continue
            sub = _klines_for_date(stock_klines, date)
            if len(sub) < 60:
                continue
            sig = evaluate_stock(code, date, klines=sub, datasource=ds)
            if sig.verdict == SignalVerdict.PASS:
                candidates.append(sig)

        filtered = filter_signals(candidates, config.position_score_threshold, config.signal_min_count)

        _run_single_day(date, state, filtered, klines_map, context, config)

        # 记录资金曲线
        state.equity = _portfolio_value(state, date, klines_map)
        state.equity_curve.append(
            {
                "date": date,
                "equity": round(state.equity, 2),
                "cash": round(state.cash, 2),
                "positions": len(state.positions),
                "regime": context.regime.value,
            }
        )

    return _build_result(state, config)


def _build_result(state: _SimulatorState, config: SimulationConfig) -> SimulationResult:
    """从运行时状态计算最终统计指标。"""
    result = SimulationResult(
        config=config,
        trades=state.trades,
        equity_curve=state.equity_curve,
        positions=state.positions,
        initial_capital=config.initial_capital,
        final_value=round(state.equity, 2),
    )

    if not result.equity_curve:
        return result

    # 总收益
    result.total_return = (result.final_value / config.initial_capital) - 1.0

    # 最大回撤
    peak = result.equity_curve[0]["equity"]
    max_dd = 0.0
    for point in result.equity_curve:
        val = point["equity"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    result.max_drawdown = max_dd

    # 夏普比率（用每日收益率）
    if len(result.equity_curve) > 1:
        rets = []
        for i in range(1, len(result.equity_curve)):
            prev = result.equity_curve[i - 1]["equity"]
            cur = result.equity_curve[i]["equity"]
            if prev > 0:
                rets.append((cur - prev) / prev)
        if len(rets) > 1:
            avg_r = sum(rets) / len(rets)
            var = sum((r - avg_r) ** 2 for r in rets) / (len(rets) - 1)
            std = math.sqrt(var) if var > 0 else 0.0
            if std > 0:
                result.sharpe_ratio = (avg_r / std) * math.sqrt(252)

    # 交易统计
    sells = [t for t in result.trades if t.action == "SELL"]
    result.total_trades = len(sells)
    if sells:
        wins = [t for t in sells if t.pnl > 0]
        result.win_rate = len(wins) / len(sells)
        total_profit = sum(t.pnl for t in wins)
        total_loss = abs(sum(t.pnl for t in sells if t.pnl <= 0))
        result.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        # 平均持仓天数：用 SELL 与 BUY 日期差近似
        holding_days = []
        buy_dates: dict[str, str] = {}
        for t in result.trades:
            if t.action == "BUY":
                buy_dates[t.ts_code] = t.date
            elif t.action == "SELL" and t.ts_code in buy_dates:
                from datetime import datetime

                d1 = datetime.strptime(buy_dates[t.ts_code], "%Y%m%d")
                d2 = datetime.strptime(t.date, "%Y%m%d")
                holding_days.append((d2 - d1).days)
        if holding_days:
            result.avg_holding_days = sum(holding_days) / len(holding_days)

    # 基准曲线与专业绩效指标
    benchmark_curve = getattr(state, "benchmark_curve", None) or []
    if not isinstance(benchmark_curve, list):
        benchmark_curve = []
    result.benchmark_curve = benchmark_curve
    result.metrics = calculate_metrics(
        result.equity_curve, benchmark_curve, result.trades
    )

    return result


def summary_text(result: SimulationResult) -> str:
    """格式化模拟结果为可读文本。"""
    lines = [
        f"{'=' * 60}",
        "少女/少妇模拟器 v0.1 回测结果",
        f"{'=' * 60}",
        f"初始资金:     {result.initial_capital:,.2f}",
        f"最终市值:     {result.final_value:,.2f}",
        f"总收益:       {result.total_return:+.2%}",
        f"最大回撤:     {result.max_drawdown:.2%}",
        f"夏普比率:     {result.sharpe_ratio:.2f}",
        f"总交易次数:   {result.total_trades}",
        f"胜率:         {result.win_rate:.1%}",
        f"盈亏比:       {result.profit_factor:.2f}",
        f"平均持仓天数: {result.avg_holding_days:.1f}",
        f"未平仓数:     {len(result.positions)}",
        f"{'=' * 60}",
    ]
    return "\n".join(lines)

#!/usr/bin/env python3
"""
策略回测框架

基于策略信号 + 历史K线，模拟交易并输出统计指标。

用法：
    from modules.backtest import backtest_strategy
    result = backtest_strategy('600487.SH', days=240)
    print(result.summary())
"""

import os
from dataclasses import dataclass, field
from typing import Any, Optional

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载）
# try:
#     from modules.strategies import detect_all_strategies, get_kline_data, Priority
# except ImportError:
#     from strategies import detect_all_strategies, get_kline_data, Priority

from modules.strategies import detect_all_strategies, get_kline_data


@dataclass
class Trade:
    """单笔交易记录"""

    ts_code: str
    entry_date: str
    entry_price: float
    exit_date: str | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    exit_reason: str = ""  # 'signal', 'stop_loss', 'take_profit', 'end_of_data'


@dataclass
class BacktestResult:
    """回测结果"""

    ts_code: str
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    avg_return: float = 0.0
    avg_hold_days: float = 0.0
    total_return: float = 0.0
    trades: list[Trade] = field(default_factory=list)

    def summary(self) -> str:
        """格式化回测摘要"""
        lines = [
            f"{'=' * 60}",
            f"回测结果: {self.ts_code}",
            f"{'=' * 60}",
            f"总交易次数: {self.total_trades}",
            f"盈利次数:   {self.win_trades}",
            f"亏损次数:   {self.loss_trades}",
            f"胜率:       {self.win_rate:.1%}",
            f"盈亏比:     {self.profit_factor:.2f}",
            f"最大回撤:   {self.max_drawdown:.1%}",
            f"平均收益:   {self.avg_return:.2%}",
            f"平均持仓:   {self.avg_hold_days:.1f}天",
            f"总收益率:   {self.total_return:.2%}",
            f"{'=' * 60}",
        ]

        if self.trades:
            lines.append("最近5笔交易:")
            for t in self.trades[-5:]:
                status = "🟢" if t.pnl > 0 else "🔴" if t.pnl < 0 else "⚪"
                lines.append(f"  {status} {t.entry_date}→{t.exit_date or '持有中'} {t.pnl_pct:+.2f}% ({t.exit_reason})")

        return "\n".join(lines)


def backtest_signals(
    signals: list[Any],
    klines: list[dict[str, Any]],
    ts_code: str,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
    position_pct: float = 1.0,
) -> BacktestResult:
    """
    基于策略信号进行回测

    Args:
        signals: 策略信号列表（StrategySignal），按日期升序
        klines: 历史K线数据，按日期升序
        ts_code: 股票代码
        stop_loss_pct: 止损比例（默认7%）
        take_profit_pct: 止盈比例（默认15%）

    Returns:
        BacktestResult
    """
    result = BacktestResult(ts_code=ts_code)

    if not klines:
        return result

    # 构建日期 -> 信号 映射
    signal_map: dict[str, Any] = {}
    for sig in signals:
        signal_map[sig.trade_date] = sig

    # 当前持仓
    current_trade: Trade | None = None
    entry_high: float = 0.0

    # 按日期升序遍历 K 线（确保每天都检查止损/止盈）
    for k in klines:
        date = k["trade_date"]
        price = k["close"]
        day_high = k["high"]
        day_low = k["low"]

        # 检查止损/止盈（如果持有中）
        if current_trade is not None:
            entry_high = max(entry_high, day_high)

            if _is_stop_loss_triggered(day_low, current_trade.entry_price, stop_loss_pct):
                exit_price = _stop_loss_price(current_trade.entry_price, stop_loss_pct)
                current_trade.exit_date = date
                current_trade.exit_price = exit_price
                current_trade.pnl, current_trade.pnl_pct = _calc_pnl(current_trade.entry_price, exit_price)
                current_trade.exit_reason = "stop_loss"
                result.trades.append(current_trade)
                current_trade = None
                continue

            if _is_take_profit_triggered(day_high, current_trade.entry_price, take_profit_pct):
                exit_price = _take_profit_price(current_trade.entry_price, take_profit_pct)
                current_trade.exit_date = date
                current_trade.exit_price = exit_price
                current_trade.pnl, current_trade.pnl_pct = _calc_pnl(current_trade.entry_price, exit_price)
                current_trade.exit_reason = "take_profit"
                result.trades.append(current_trade)
                current_trade = None
                continue

        # 处理当天信号
        sig = signal_map.get(date)
        if sig is None:
            continue

        # 买入信号
        if sig.action == "BUY" and current_trade is None:
            current_trade = Trade(
                ts_code=ts_code,
                entry_date=date,
                entry_price=price,
            )
            entry_high = price

        # 卖出信号
        elif sig.action == "SELL" and current_trade is not None:
            trade = _make_trade(
                ts_code,
                current_trade.entry_date,
                current_trade.entry_price,
                date,
                price,
                "signal",
            )
            result.trades.append(trade)
            current_trade = None

    # 数据末尾强制平仓
    if current_trade is not None and klines:
        last = klines[-1]
        trade = _make_trade(
            ts_code,
            current_trade.entry_date,
            current_trade.entry_price,
            last["trade_date"],
            last["close"],
            "end_of_data",
        )
        result.trades.append(trade)

    # 计算统计指标
    if result.trades:
        result.total_trades = len(result.trades)
        result.win_trades = sum(1 for t in result.trades if t.pnl > 0)
        result.loss_trades = sum(1 for t in result.trades if t.pnl < 0)
        result.win_rate = result.win_trades / result.total_trades

        total_profit = sum(t.pnl for t in result.trades if t.pnl > 0)
        total_loss = abs(sum(t.pnl for t in result.trades if t.pnl < 0))
        result.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        result.avg_return = sum(t.pnl_pct for t in result.trades) / result.total_trades
        result.avg_hold_days = sum(t.hold_days for t in result.trades) / result.total_trades

        # 最大回撤
        peak = 0.0
        drawdown = 0.0
        cumulative = 0.0
        for t in result.trades:
            cumulative += t.pnl_pct
            peak = max(peak, cumulative)
            drawdown = max(drawdown, peak - cumulative)
        result.max_drawdown = drawdown

        # 总收益率（复利）
        result.total_return = 1.0
        for t in result.trades:
            result.total_return *= 1 + t.pnl_pct
        result.total_return -= 1.0

    return result


def backtest_strategy(
    ts_code: str,
    days: int = 240,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
) -> BacktestResult:
    """
    对单只股票进行策略回测（便捷函数）

    Args:
        ts_code: 股票代码
        days: 回测天数
        stop_loss_pct: 止损比例（None = 从 registry 读取或默认 7%）
        take_profit_pct: 止盈比例（None = 默认 15%）

    Returns:
        BacktestResult
    """
    # 取消代理
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

    try:
        from modules.self_optimizer.param_registry import get_active_param
    except ImportError:

        def get_active_param(strategy: str, name: str, default: Any = None) -> Any:
            return default  # fallback

    if stop_loss_pct is None:
        stop_loss_pct = get_active_param("stop_loss", "stop_loss_pct", 7.0) / 100.0
    if take_profit_pct is None:
        take_profit_pct = 0.15

    position_pct = get_active_param("position", "single_position_pct", 30.0) / 100.0
    klines = get_kline_data(ts_code, days)
    signals = detect_all_strategies(ts_code, days)

    return backtest_signals(signals, klines, ts_code, stop_loss_pct, take_profit_pct, position_pct)


# ==================== 策略组合回测 ====================


@dataclass
class Position:
    """持仓记录"""

    ts_code: str
    entry_date: str
    entry_price: float
    shares: int = 0  # 持股数量（A股100股为1手）
    cost_basis: float = 0.0  # 总成本
    current_price: float = 0.0
    current_value: float = 0.0
    high_since_entry: float = 0.0

    def update_price(self, price: float) -> None:
        """更新当前价格"""
        self.current_price = price
        self.current_value = self.shares * price
        self.high_since_entry = max(self.high_since_entry, price)

    def unrealized_pnl_pct(self) -> float:
        """未实现盈亏比例"""
        if self.cost_basis == 0:
            return 0.0
        return (self.current_value - self.cost_basis) / self.cost_basis


@dataclass
class PortfolioBacktestResult:
    """组合回测结果（含资金曲线）"""

    initial_capital: float = 100000.0
    final_value: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)

    def summary(self) -> str:
        """格式化回测摘要"""
        lines = [
            f"{'=' * 60}",
            "组合回测结果",
            f"{'=' * 60}",
            f"初始资金:   ¥{self.initial_capital:,.0f}",
            f"最终资产:   ¥{self.final_value:,.0f}",
            f"总收益率:   {self.total_return:.2%}",
            f"年化收益:   {self.annualized_return:.2%}",
            f"夏普比率:   {self.sharpe_ratio:.2f}",
            f"最大回撤:   {self.max_drawdown:.1%}",
            f"胜率:       {self.win_rate:.1%}",
            f"盈亏比:     {self.profit_factor:.2f}",
            f"总交易次数: {self.total_trades}",
            f"{'=' * 60}",
        ]

        if self.trades:
            lines.append("最近5笔交易:")
            for t in self.trades[-5:]:
                status = "🟢" if t.pnl > 0 else "🔴" if t.pnl < 0 else "⚪"
                lines.append(
                    f"  {status} {t.ts_code} {t.entry_date}→{t.exit_date or '持有中'} "
                    f"{t.pnl_pct:+.2f}% ({t.exit_reason})"
                )

        return "\n".join(lines)


def _calc_shares(invest_amount: float, price: float) -> int:
    """计算可买入股数（A股100股为1手）"""
    if price <= 0 or invest_amount <= 0:
        return 0
    shares = int(invest_amount / price / 100) * 100
    return shares


# ==================== 通用回测工具函数（v3.x 重构：消除 3 处重复） ====================


def _calc_pnl(entry_price: float, exit_price: float, shares: int = 1) -> tuple[float, float]:
    """计算盈亏金额和比例（shares=1 时 pnl 即价差）"""
    pnl = (exit_price - entry_price) * shares
    pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0.0
    return pnl, pnl_pct


def _make_trade(
    ts_code: str, entry_date: str, entry_price: float, exit_date: str, exit_price: float, reason: str, shares: int = 1
) -> Trade:
    """构建 Trade 记录（统一创建入口，避免各方法手写 Trade(...)）"""
    pnl, pnl_pct = _calc_pnl(entry_price, exit_price, shares)
    return Trade(
        ts_code=ts_code,
        entry_date=entry_date,
        entry_price=entry_price,
        exit_date=exit_date,
        exit_price=exit_price,
        pnl=pnl,
        pnl_pct=pnl_pct,
        exit_reason=reason,
    )


def _is_stop_loss_triggered(day_low: float, entry_price: float, stop_loss_pct: float) -> bool:
    """检查止损触发"""
    return day_low <= entry_price * (1 - stop_loss_pct)


def _is_take_profit_triggered(day_high: float, entry_price: float, take_profit_pct: float) -> bool:
    """检查止盈触发"""
    return day_high >= entry_price * (1 + take_profit_pct)


def _stop_loss_price(entry_price: float, stop_loss_pct: float) -> float:
    """止损价格"""
    return entry_price * (1 - stop_loss_pct)


def _take_profit_price(entry_price: float, take_profit_pct: float) -> float:
    """止盈价格"""
    return entry_price * (1 + take_profit_pct)


def _calc_stats(result: PortfolioBacktestResult, trading_days: int = 0):
    """计算组合回测统计指标"""
    if not result.equity_curve:
        return

    # 总收益率
    result.final_value = result.equity_curve[-1][1]
    result.total_return = (result.final_value - result.initial_capital) / result.initial_capital

    # 年化收益（按252个交易日/年）
    if trading_days > 0:
        result.annualized_return = (1 + result.total_return) ** (252 / trading_days) - 1

    # 最大回撤 & 日收益率序列
    peak = result.initial_capital
    drawdown = 0.0
    daily_returns = []

    for i, (date, value) in enumerate(result.equity_curve):
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        drawdown = max(drawdown, dd)

        if i > 0:
            prev_value = result.equity_curve[i - 1][1]
            if prev_value > 0:
                daily_returns.append((value - prev_value) / prev_value)

    result.max_drawdown = drawdown

    # 夏普比率（假设无风险利率为0）
    if daily_returns:
        avg_return = sum(daily_returns) / len(daily_returns)
        variance = sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns)
        std = variance**0.5
        if std > 0:
            result.sharpe_ratio = (avg_return / std) * (252**0.5)

    # 交易统计
    if result.trades:
        result.total_trades = len(result.trades)
        win_trades = sum(1 for t in result.trades if t.pnl > 0)
        result.win_rate = win_trades / result.total_trades

        total_profit = sum(t.pnl for t in result.trades if t.pnl > 0)
        total_loss = abs(sum(t.pnl for t in result.trades if t.pnl < 0))
        result.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")


def backtest_multi_strategy(
    ts_code: str,
    days: int = 240,
    initial_capital: float = 100000.0,
    position_pct: float = 0.3,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> PortfolioBacktestResult:
    """
    单股票多策略融合回测

    逻辑：
    - 收集所有策略信号，按优先级（CRITICAL > OPPORTUNITY > OBSERVE）排序
    - 每天只执行最高优先级的买入/卖出信号
    - 仓位管理：每次最多使用 position_pct 比例的资金

    Args:
        ts_code: 股票代码
        days: 回测天数
        initial_capital: 初始资金
        position_pct: 单次仓位比例（默认30%）
        stop_loss_pct: 止损比例
        take_profit_pct: 止盈比例

    Returns:
        PortfolioBacktestResult
    """
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

    klines = get_kline_data(ts_code, days)
    signals = detect_all_strategies(ts_code, days)

    result = PortfolioBacktestResult(initial_capital=initial_capital)

    if not klines:
        return result

    # 构建日期 -> [信号列表] 映射
    signal_map: dict[str, list[Any]] = {}
    for sig in signals:
        signal_map.setdefault(sig.trade_date, []).append(sig)

    cash = initial_capital
    position: Position | None = None

    # 按日期升序遍历
    for k in klines:
        date = k["trade_date"]
        price = k["close"]
        day_high = k["high"]
        day_low = k["low"]

        # 更新持仓市值
        if position is not None:
            position.update_price(price)

            # 止损
            if _is_stop_loss_triggered(day_low, position.entry_price, stop_loss_pct):
                exit_price = _stop_loss_price(position.entry_price, stop_loss_pct)
                cash += position.shares * exit_price
                trade = _make_trade(
                    ts_code,
                    position.entry_date,
                    position.entry_price,
                    date,
                    exit_price,
                    "stop_loss",
                    position.shares,
                )
                result.trades.append(trade)
                position = None
                result.equity_curve.append((date, cash))
                continue

            # 止盈
            if _is_take_profit_triggered(day_high, position.entry_price, take_profit_pct):
                exit_price = _take_profit_price(position.entry_price, take_profit_pct)
                cash += position.shares * exit_price
                trade = _make_trade(
                    ts_code,
                    position.entry_date,
                    position.entry_price,
                    date,
                    exit_price,
                    "take_profit",
                    position.shares,
                )
                result.trades.append(trade)
                position = None
                result.equity_curve.append((date, cash))
                continue

        # 处理当天信号
        day_signals = signal_map.get(date, [])
        if not day_signals:
            # 无信号，记录当前资产
            total_value = cash + (position.current_value if position else 0)
            result.equity_curve.append((date, total_value))
            continue

        # 按优先级排序（数值越小优先级越高：CRITICAL=1, OPPORTUNITY=2, OBSERVE=3）
        day_signals.sort(key=lambda s: s.priority.value if hasattr(s.priority, "value") else 3)

        # 取最高优先级信号
        top_signal = day_signals[0]

        # 买入信号
        if top_signal.action == "BUY" and position is None:
            invest_amount = cash * position_pct
            shares = _calc_shares(invest_amount, price)
            if shares >= 100:
                cost = shares * price
                cash -= cost
                position = Position(
                    ts_code=ts_code,
                    entry_date=date,
                    entry_price=price,
                    shares=shares,
                    cost_basis=cost,
                    current_price=price,
                    current_value=cost,
                    high_since_entry=price,
                )

        # 卖出信号
        elif top_signal.action == "SELL" and position is not None:
            cash += position.shares * price
            trade = _make_trade(
                ts_code,
                position.entry_date,
                position.entry_price,
                date,
                price,
                "signal",
                position.shares,
            )
            result.trades.append(trade)
            position = None

        total_value = cash + (position.current_value if position else 0)
        result.equity_curve.append((date, total_value))

    # 数据末尾强制平仓
    if position is not None and klines:
        last = klines[-1]
        exit_price = last["close"]
        cash += position.shares * exit_price
        trade = _make_trade(
            ts_code,
            position.entry_date,
            position.entry_price,
            last["trade_date"],
            exit_price,
            "end_of_data",
            position.shares,
        )
        result.trades.append(trade)
        position = None
        result.equity_curve[-1] = (last["trade_date"], cash)

    _calc_stats(result, trading_days=len(klines))
    return result


def backtest_portfolio(
    stock_configs: list[dict[str, Any]],
    days: int = 240,
    initial_capital: float = 100000.0,
    position_pct: float = 0.2,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> PortfolioBacktestResult:
    """
    多股票组合回测

    Args:
        stock_configs: 股票配置列表，每项包含 {'ts_code': 'xxx', 'max_weight': 0.2}
        days: 回测天数
        initial_capital: 初始资金
        position_pct: 单只股票最大仓位比例
        stop_loss_pct: 止损比例
        take_profit_pct: 止盈比例

    Returns:
        PortfolioBacktestResult
    """
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

    result = PortfolioBacktestResult(initial_capital=initial_capital)

    # 为每只股票获取数据和信号
    stock_data = {}
    all_dates: set[str] = set()

    for config in stock_configs:
        ts_code = config["ts_code"]
        klines = get_kline_data(ts_code, days)
        signals = detect_all_strategies(ts_code, days)

        if not klines:
            continue

        signal_map: dict[str, list] = {}
        for sig in signals:
            signal_map.setdefault(sig.trade_date, []).append(sig)

        stock_data[ts_code] = {
            "klines": klines,
            "signal_map": signal_map,
            "klines_map": {k["trade_date"]: k for k in klines},
            "max_weight": config.get("max_weight", position_pct),
            "position": None,
        }
        all_dates.update(k["trade_date"] for k in klines)

    if not stock_data:
        return result

    # 按日期升序遍历
    sorted_dates = sorted(all_dates)
    cash = initial_capital

    for date in sorted_dates:
        # 1. 检查每只股票持仓的止损/止盈
        for ts_code, data in stock_data.items():
            pos = data["position"]
            if pos is None:
                continue

            kline = data["klines_map"].get(date)
            if not kline:
                continue

            price = kline["close"]
            day_high = kline["high"]
            day_low = kline["low"]
            pos.update_price(price)

            # 止损
            if _is_stop_loss_triggered(day_low, pos.entry_price, stop_loss_pct):
                exit_price = _stop_loss_price(pos.entry_price, stop_loss_pct)
                cash += pos.shares * exit_price
                trade = _make_trade(
                    ts_code,
                    pos.entry_date,
                    pos.entry_price,
                    date,
                    exit_price,
                    "stop_loss",
                    pos.shares,
                )
                result.trades.append(trade)
                data["position"] = None

            # 止盈
            elif _is_take_profit_triggered(day_high, pos.entry_price, take_profit_pct):
                exit_price = _take_profit_price(pos.entry_price, take_profit_pct)
                cash += pos.shares * exit_price
                trade = _make_trade(
                    ts_code,
                    pos.entry_date,
                    pos.entry_price,
                    date,
                    exit_price,
                    "take_profit",
                    pos.shares,
                )
                result.trades.append(trade)
                data["position"] = None

        # 2. 处理新信号（买入/卖出）
        for ts_code, data in stock_data.items():
            kline = data["klines_map"].get(date)
            if not kline:
                continue

            price = kline["close"]
            pos = data["position"]
            day_signals = data["signal_map"].get(date, [])

            if not day_signals:
                continue

            # 按优先级排序
            day_signals.sort(key=lambda s: s.priority.value if hasattr(s.priority, "value") else 3)
            top_signal = day_signals[0]

            # 买入
            if top_signal.action == "BUY" and pos is None:
                # 计算该股票允许的最大投入金额
                total_value = cash + sum(
                    (p.current_value if p else 0) for p in [s["position"] for s in stock_data.values()]
                )
                max_invest = total_value * data["max_weight"]
                invest_amount = min(cash, max_invest)
                shares = _calc_shares(invest_amount, price)

                if shares >= 100:
                    cost = shares * price
                    cash -= cost
                    data["position"] = Position(
                        ts_code=ts_code,
                        entry_date=date,
                        entry_price=price,
                        shares=shares,
                        cost_basis=cost,
                        current_price=price,
                        current_value=cost,
                        high_since_entry=price,
                    )

            # 卖出
            elif top_signal.action == "SELL" and pos is not None:
                cash += pos.shares * price
                trade = _make_trade(
                    ts_code,
                    pos.entry_date,
                    pos.entry_price,
                    date,
                    price,
                    "signal",
                    pos.shares,
                )
                result.trades.append(trade)
                data["position"] = None

        # 3. 记录当日总资产
        positions_value = sum((p.current_value if p else 0) for p in [s["position"] for s in stock_data.values()])
        result.equity_curve.append((date, cash + positions_value))

    # 强制平仓所有持仓
    for ts_code, data in stock_data.items():
        pos = data["position"]
        if pos is None:
            continue

        klines = data["klines"]
        if not klines:
            continue

        last = klines[-1]
        exit_price = last["close"]
        cash += pos.shares * exit_price
        trade = _make_trade(
            ts_code,
            pos.entry_date,
            pos.entry_price,
            last["trade_date"],
            exit_price,
            "end_of_data",
            pos.shares,
        )
        result.trades.append(trade)
        data["position"] = None

    if result.equity_curve:
        result.equity_curve[-1] = (result.equity_curve[-1][0], cash)

    _calc_stats(result, trading_days=len(sorted_dates))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="策略回测")
    subparsers = parser.add_subparsers(dest="command")

    # 单策略回测
    single_parser = subparsers.add_parser("single", help="单策略回测")
    single_parser.add_argument("ts_code", help="股票代码")
    single_parser.add_argument("--days", type=int, default=240, help="回测天数")
    single_parser.add_argument("--stop-loss", type=float, default=0.07, help="止损比例")
    single_parser.add_argument("--take-profit", type=float, default=0.15, help="止盈比例")

    # 多策略融合回测
    multi_parser = subparsers.add_parser("multi", help="多策略融合回测")
    multi_parser.add_argument("ts_code", help="股票代码")
    multi_parser.add_argument("--days", type=int, default=240, help="回测天数")
    multi_parser.add_argument("--capital", type=float, default=100000, help="初始资金")
    multi_parser.add_argument("--position", type=float, default=0.3, help="单次仓位比例")
    multi_parser.add_argument("--stop-loss", type=float, default=0.07, help="止损比例")
    multi_parser.add_argument("--take-profit", type=float, default=0.15, help="止盈比例")

    args = parser.parse_args()

    if args.command == "single":
        result: BacktestResult | PortfolioBacktestResult = backtest_strategy(
            args.ts_code,
            days=args.days,
            stop_loss_pct=args.stop_loss,
            take_profit_pct=args.take_profit,
        )
        print(result.summary())
    elif args.command == "multi":
        result = backtest_multi_strategy(
            args.ts_code,
            days=args.days,
            initial_capital=args.capital,
            position_pct=args.position,
            stop_loss_pct=args.stop_loss,
            take_profit_pct=args.take_profit,
        )
        print(result.summary())
    else:
        parser.print_help()

"""
少妇战法六步闭环回测模块

基于 ShaofuLoopEngine 的回测封装，支持单股票和组合回测。
六步 SOP：择时 -> 选股 -> 等 B1 -> 设止损 -> 止盈(卤煮) -> 离场(BBI两日破位)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import os
import math
from dataclasses import dataclass, field

from .loop_engine import ShaofuLoopEngine, LoopConfig, LoopTrade, _calc_stop_loss_price
from .indicators import DailyData, get_kline_data
from .market_regime import MarketRegime
from .statistics import sharpe_t_test, monte_carlo_permutation_test, analyze_sub_periods
from .statistics.criteria import validate_strategy, ValidationReport, CriteriaLevel

if TYPE_CHECKING:
    from .market_regime import MarketRegimeClassifier
    from .position_manager import PositionManager
    from .industry_filter import IndustryFilter


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
    validation_report: ValidationReport | None = None  # 统计检验报告（可选）


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
    # 注意：pnl_pct 是百分比数值（如 5.0 表示 5%），需除以 100 转为小数比例
    equity = 100.0
    curve = [equity]
    for pnl in pnl_list:
        equity *= 1 + pnl / 100.0
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

    # 夏普比率（用每笔交易收益率，按交易频率年化）
    if len(pnl_list) >= 3:
        avg_ret = sum(pnl_list) / len(pnl_list)
        variance = sum((r - avg_ret) ** 2 for r in pnl_list) / (len(pnl_list) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std > 0.1:
            avg_hold = result.avg_holding_days if result.avg_holding_days > 0 else 10.0
            annualization = math.sqrt(252.0 / avg_hold)
            result.sharpe_ratio = (avg_ret / std) * annualization


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


def backtest_shaofu_with_validation(
    ts_code: str,
    days: int = 250,
    config: LoopConfig | None = None,
    klines: list[DailyData] | None = None,
    market_regimes: dict[str, str] | None = None,
    validation_level: CriteriaLevel = CriteriaLevel.MODERATE,
) -> ShaofuBacktestResult:
    """
    单股票少妇战法回测 + 统计检验

    在基础回测之上，自动运行：
    1. 夏普比率 t 检验（p-value）
    2. Bootstrap 置信区间（95% CI）
    3. Monte Carlo 置换检验（防数据挖掘）
    4. 子周期分析（牛/熊/震荡稳健性）

    Args:
        ts_code: 股票代码
        days: 回测天数
        config: 策略参数
        klines: K线数据（可选）
        market_regimes: 市场环境映射 {date: 'bull'/'bear'/'sideways'}（可选）
        validation_level: 验证级别（strict/moderate/loose）

    Returns:
        ShaofuBacktestResult with validation_report

    Example:
        >>> result = backtest_shaofu_with_validation("600519.SH")
        >>> print(result.validation_report.generate_summary())
    """
    # 1. 基础回测
    result = backtest_shaofu_single(ts_code, days=days, config=config, klines=klines)

    if not result.trades:
        return result

    # 2. 提取收益率序列（从资金曲线计算日收益率）
    equity_curve = result.equity_curve
    if len(equity_curve) < 5:
        # 样本量太小，无法有效检验（至少需要5笔交易）
        return result

    daily_returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] > 0:
            daily_returns.append((equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1])

    if len(daily_returns) < 5:
        return result

    # 3. 夏普 t 检验 + Bootstrap CI
    sharpe_test = sharpe_t_test(daily_returns)

    # 4. Monte Carlo 置换检验
    mc_test = monte_carlo_permutation_test(daily_returns, n_permutations=1000)

    # 5. 子周期分析（如果提供了市场环境数据）
    sub_period = None
    if market_regimes:
        trades_data = [
            {
                "date": t.entry_date,
                "pnl_pct": t.pnl_pct,
                "holding_days": t.holding_days,
            }
            for t in result.trades
        ]
        sub_period = analyze_sub_periods(trades_data, market_regimes)

    # 6. 生成验证报告
    perf_metrics = {
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio,
    }

    report = validate_strategy(
        strategy_name=f"少妇战法-{ts_code}",
        sharpe_test_result=sharpe_test,
        monte_carlo_result=mc_test,
        sub_period_result=sub_period,
        performance_metrics=perf_metrics,
        level=validation_level,
    )

    result.validation_report = report

    return result


def summary_with_validation(result: ShaofuBacktestResult) -> str:
    """
    格式化带统计检验的回测结果

    Args:
        result: 带验证报告的回测结果

    Returns:
        格式化字符串
    """
    lines = [summary_text(result), ""]

    if result.validation_report:
        lines.append(result.validation_report.generate_summary())

    return "\n".join(lines)


def backtest_shaofu_portfolio_integrated(
    ts_codes: list[str],
    days: int = 250,
    base_config: LoopConfig | None = None,
    regime_classifier: MarketRegimeClassifier | None = None,
    position_manager: PositionManager | None = None,
    industry_filter: IndustryFilter | None = None,
    initial_capital: float = 1_000_000,
    regime_params: dict[str, dict] | None = None,
) -> dict:
    """
    集成化组合回测（真实资金管理 + 动态参数 + 行业约束）

    与 backtest_shaofu_portfolio() 的区别：
    - 共享 cash pool（真实资金竞争）
    - 集成市场状态分类器（动态参数调整）
    - 集成仓位管理器（基于风险的仓位计算）
    - 集成行业过滤器（行业分散化约束）

    按日驱动的真实组合回测：
    1. 预热期（第 30~119 日）：各股独立运行引擎以积累指标状态，不进入仓位管理
    2. 集成期（第 120 日起）：逐日处理所有股票的入场/离场，共享资金池

    Args:
        ts_codes: 股票代码列表
        days: 回测天数
        base_config: 基础策略参数
        regime_classifier: 市场状态分类器（None 则不使用动态参数，固定 SIDEWAYS）
        position_manager: 仓位管理器（None 则使用默认配置）
        industry_filter: 行业过滤器（None 则不检查行业约束）
        initial_capital: 初始资金
        regime_params: 各市场状态的参数覆盖字典（可选）
                       格式: {"BULL": {"j_threshold": 18, ...}, "BEAR": {...}, ...}
                       为 None 时使用 DynamicConfigAdapter 默认映射

    Returns:
        {
            "result": ShaofuBacktestResult,  # 组合级回测结果
            "daily_equity": list[tuple[str, float]],  # 每日净值 [(date, equity), ...]
            "regime_history": list[tuple[str, str]],  # 市场状态历史 [(date, regime), ...]
            "trade_details": list[dict],  # 详细交易记录
        }
    """
    # 取消代理
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""

    cfg = base_config or LoopConfig()

    # ── 1. 加载数据 ──────────────────────────────────────
    # 多请求 warmup 数据，供指标预热使用（最少 120 日）
    warmup_days = max(120, 30)
    stock_klines: dict[str, list[DailyData]] = {}
    for code in ts_codes:
        klines = get_kline_data(code, days + warmup_days)
        if klines and len(klines) >= 30:
            stock_klines[code] = klines

    if not stock_klines:
        empty = ShaofuBacktestResult(ts_code="PORTFOLIO")
        return {
            "result": empty,
            "daily_equity": [],
            "regime_history": [],
            "trade_details": [],
        }

    # 大盘指数 K 线（用于市场状态分类）
    index_klines: list[DailyData] = []
    try:
        index_klines = get_kline_data("000001.SH", days + warmup_days)
    except Exception:
        pass  # 无指数数据时走固定参数路径

    # 回测起始日：取各股 K 线长度的最大值，保证至少有 120 日可用
    min_kline_len = min(len(kl) for kl in stock_klines.values())
    start_idx = min(120, min_kline_len)

    # ── 2. 初始化组件 ────────────────────────────────────
    # 动态参数适配器（延迟导入，避免循环依赖）
    if regime_classifier is None:
        # 无分类器：固定使用 SIDEWAYS 参数
        from .dynamic_config import DynamicConfigAdapter

        dynamic_config = DynamicConfigAdapter(base_config=cfg, regime_params=regime_params)
        has_regime = False
    else:
        from .dynamic_config import DynamicConfigAdapter

        has_regime = bool(index_klines and len(index_klines) >= start_idx)
        dynamic_config = DynamicConfigAdapter(base_config=cfg, regime_params=regime_params)

    # 仓位管理器
    if position_manager is None:
        from .position_manager import PositionManager

        pm = PositionManager(initial_capital=initial_capital)
    else:
        pm = position_manager
        if pm.cash == 0.0:
            pm.reset(initial_capital)

    # ── 3. 逐股状态初始化 ────────────────────────────────
    stock_states: dict[str, dict] = {}
    for code, klines in stock_klines.items():
        stock_states[code] = {
            "klines": klines,
            "engine": ShaofuLoopEngine(cfg),
            "current_trade": None,  # 当前持仓 LoopTrade | None
            "in_warmup": True,  # 是否仍在预热期
            "idle": True,  # 预热期是否空闲（无持仓）
        }

    # ── 4. 预计算各股 warmup 期止损参数 ──────────────────
    # warmup 期使用固定 base_config 的止损参数，集成期切换到动态 config
    stop_loss_configs: dict[str, LoopConfig] = {
        code: LoopConfig(
            stop_loss_method=cfg.stop_loss_method,
            stop_loss_pct=cfg.stop_loss_pct,
        )
        for code in stock_klines
    }

    # 大盘指数数据对齐（确保足够长度）
    if has_regime and len(index_klines) < start_idx:
        has_regime = False

    # ── 5. 记录容器 ─────────────────────────────────────
    daily_equity: list[tuple[str, float]] = []
    regime_history: list[tuple[str, str]] = []
    trade_details: list[dict] = []  # 已完成交易明细

    last_regime: str | None = None

    # ── 6. 按日驱动主循环 ────────────────────────────────
    for day_idx in range(start_idx, min_kline_len):
        # ── 6a. 市场状态分类 ─────────────────────────────
        if has_regime and day_idx < len(index_klines):
            regime = regime_classifier.classify_date(index_klines, day_idx)
            current_config = dynamic_config.get_config(regime)
            regime_str = regime.value
        else:
            current_config = dynamic_config.get_config(MarketRegime.SIDEWAYS)
            regime_str = "SIDEWAYS"

        # 获取当日日期字符串（优先使用第一只有数据的股票）
        current_date = ""
        for st in stock_states.values():
            if day_idx < len(st["klines"]):
                current_date = st["klines"][day_idx].trade_date
                break

        # 记录市场状态变化
        if regime_str != last_regime:
            regime_history.append((current_date, regime_str))
            last_regime = regime_str

        # ── 6b. 计算当前组合净值 ─────────────────────────
        # equity = 现金 + 所有持仓的当日市值
        positions_value = 0.0
        for code, st in stock_states.items():
            if st["current_trade"] is not None:
                positions_value += st["current_trade"].shares_equiv * st["klines"][day_idx].close
        current_equity = pm.cash + positions_value

        # ── 6c. 逐股状态转移（warmup → active） ──────────
        for code, st in stock_states.items():
            if day_idx >= len(st["klines"]):
                continue

            klines = st["klines"]
            engine = st["engine"]

            # ── 预热期：独立运行引擎积累指标状态 ─────────
            if st["in_warmup"]:
                if st["idle"]:
                    # 空闲状态：检查是否有入场信号
                    signal = engine._check_entry_internal(klines, day_idx)
                    if signal is not None:
                        entry_price = klines[day_idx].close
                        sl_cfg = stop_loss_configs[code]
                        stop_loss = _calc_stop_loss_price(
                            klines,
                            day_idx,
                            sl_cfg.stop_loss_method,
                            sl_cfg.stop_loss_pct,
                        )
                        st["current_trade"] = LoopTrade(
                            ts_code=code,
                            entry_date=klines[day_idx].trade_date,
                            entry_price=entry_price,
                            entry_reason=signal.get("reason", "B1信号(warmup)"),
                            stop_loss_price=stop_loss,
                            market_regime=regime_str,
                        )
                        st["idle"] = False
                else:
                    # 持仓状态：检查离场条件
                    trade = st["current_trade"]
                    updated_trade, completed = engine._apply_exit_checks(klines, day_idx, trade)
                    if completed:
                        # 预热期平仓 → 记录交易但不进入仓位管理
                        trade_details.append(
                            {
                                "ts_code": code,
                                "entry_date": completed.entry_date,
                                "exit_date": completed.exit_date,
                                "entry_price": completed.entry_price,
                                "exit_price": completed.exit_price,
                                "exit_reason": completed.exit_reason,
                                "pnl_pct": completed.pnl_pct,
                                "holding_days": completed.holding_days,
                                "market_regime": completed.market_regime,
                                "phase": "warmup",
                            }
                        )
                        st["current_trade"] = None
                        st["idle"] = True
                    elif updated_trade is not None:
                        st["current_trade"] = updated_trade
                    # updated_trade is None 理论上不会出现在 _apply_exit_checks 中

                # 预热期结束：将未平仓的 warmup 交易注册到仓位管理器
                if day_idx == start_idx and st["current_trade"] is not None:
                    st["in_warmup"] = False
                    trade = st["current_trade"]
                    shares_equiv = int(pm.cash // trade.entry_price // 100) * 100  # A 股整手
                    if shares_equiv >= 100:
                        pm.record_entry(code, shares_equiv, trade.entry_price, trade.stop_loss_price)
                        trade.shares_equiv = shares_equiv  # type: ignore[attr-defined]
                    else:
                        # 资金不足，放弃该 warmup 持仓
                        st["current_trade"] = None
                        st["idle"] = True
                continue

            # ── 集成期：正常 warmup 结束 ─────────────────
            st["in_warmup"] = False

            # ── 离场检查（集成期持仓） ───────────────────
            if st["current_trade"] is not None:
                trade = st["current_trade"]
                # 临时同步引擎配置为当日动态参数
                engine.config = current_config

                updated_trade, completed = engine._apply_exit_checks(klines, day_idx, trade)

                if completed:
                    # 平仓 → 更新仓位管理器
                    pnl_amount = pm.record_exit(code, completed.exit_price)
                    trade_details.append(
                        {
                            "ts_code": code,
                            "entry_date": completed.entry_date,
                            "exit_date": completed.exit_date,
                            "entry_price": completed.entry_price,
                            "exit_price": completed.exit_price,
                            "exit_reason": completed.exit_reason,
                            "pnl_pct": completed.pnl_pct,
                            "holding_days": completed.holding_days,
                            "market_regime": completed.market_regime,
                            "pnl_amount": pnl_amount,
                            "phase": "integrated",
                        }
                    )
                    st["current_trade"] = None
                elif updated_trade is not None:
                    st["current_trade"] = updated_trade
                continue

            # ── 入场检查（空闲状态） ─────────────────────
            signal = engine._check_entry_internal(klines, day_idx)
            if signal is None:
                continue

            entry_price = klines[day_idx].close
            if entry_price <= 0:
                continue

            # 止损价
            stop_loss = _calc_stop_loss_price(
                klines,
                day_idx,
                current_config.stop_loss_method,
                current_config.stop_loss_pct,
            )
            if stop_loss >= entry_price:
                continue

            # 仓位约束 + 行业约束
            current_holdings = list(pm.positions.keys())
            if industry_filter is not None:
                if not industry_filter.check_industry_limit(code, current_holdings):
                    continue
            if not pm.can_enter(code, current_holdings, industry_filter):
                continue

            # 计算买入股数
            shares = pm.calculate_position_size(
                ts_code=code,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
                current_equity=current_equity,
                regime=(
                    regime_classifier.classify_date(index_klines, day_idx)
                    if has_regime and day_idx < len(index_klines)
                    else MarketRegime.SIDEWAYS
                ),
            )
            if shares < 100:
                continue

            # 记录建仓
            pm.record_entry(code, shares, entry_price, stop_loss)
            st["current_trade"] = LoopTrade(
                ts_code=code,
                entry_date=klines[day_idx].trade_date,
                entry_price=entry_price,
                entry_reason=signal.get("reason", "B1信号"),
                stop_loss_price=stop_loss,
                position_pct=shares * entry_price / current_equity if current_equity > 0 else 0,
                market_regime=regime_str,
            )
            st["current_trade"].shares_equiv = shares  # type: ignore[attr-defined]

        # ── 6d. 记录每日净值 ─────────────────────────────
        positions_value = 0.0
        for code, st in stock_states.items():
            if st["current_trade"] is not None:
                shares = getattr(st["current_trade"], "shares_equiv", 0)
                if shares > 0 and day_idx < len(st["klines"]):
                    positions_value += shares * st["klines"][day_idx].close
        equity = pm.cash + positions_value
        daily_equity.append((current_date, equity))

    # ── 7. 汇总统计 ──────────────────────────────────────
    # 所有交易（含 warmup + integrated）
    all_trade_records: list[LoopTrade] = []
    for td in trade_details:
        t = LoopTrade(
            ts_code=td["ts_code"],
            entry_date=td["entry_date"],
            exit_date=td.get("exit_date", ""),
            entry_price=td["entry_price"],
            exit_price=td.get("exit_price", 0),
            entry_reason=td.get("entry_reason", ""),
            exit_reason=td.get("exit_reason", ""),
            pnl_pct=td.get("pnl_pct", 0),
            holding_days=td.get("holding_days", 0),
            market_regime=td.get("market_regime", ""),
        )
        all_trade_records.append(t)

    # 组合级结果
    portfolio_result = ShaofuBacktestResult(ts_code="PORTFOLIO")
    portfolio_result.trades = all_trade_records
    if all_trade_records:
        _calc_metrics(portfolio_result)

    # 覆盖 total_return / max_drawdown / sharpe_ratio（基于每日净值序列）
    if daily_equity:
        equities = [e for _, e in daily_equity]
        portfolio_result.total_return = (equities[-1] / initial_capital - 1.0) if initial_capital > 0 else 0.0

        # 最大回撤
        peak = equities[0]
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        portfolio_result.max_drawdown = max_dd

        # 夏普比率（基于每日收益率）
        if len(equities) >= 3:
            daily_rets = []
            for i in range(1, len(equities)):
                if equities[i - 1] > 0:
                    daily_rets.append((equities[i] - equities[i - 1]) / equities[i - 1])
            if len(daily_rets) >= 2:
                avg_r = sum(daily_rets) / len(daily_rets)
                var_r = sum((r - avg_r) ** 2 for r in daily_rets) / (len(daily_rets) - 1)
                std_r = math.sqrt(var_r) if var_r > 0 else 0.0
                if std_r > 0:
                    portfolio_result.sharpe_ratio = (avg_r / std_r) * math.sqrt(252)

    return {
        "result": portfolio_result,
        "daily_equity": daily_equity,
        "regime_history": regime_history,
        "trade_details": trade_details,
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

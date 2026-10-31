#!/usr/bin/env python3
"""
策略集成模块

通过集成多个策略信号，提高少妇战法的胜率和稳定性。

集成方法：
1. 投票法 - 多个策略都发出信号才入场（提高胜率，降低交易频率）
2. 加权法 - 根据策略历史胜率加权（自适应调整）
3. 共振法 - 多策略共振加分（已有 resonance_scorer.py）

核心思想：
- 单一策略容易过拟合
- 多策略集成可以提高稳健性
- 但会降低交易频率（需要权衡）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EnsembleMethod(Enum):
    """集成方法"""

    VOTING = "voting"  # 投票法（多策略都同意才入场）
    WEIGHTED = "weighted"  # 加权法（按历史胜率加权）
    RESONANCE = "resonance"  # 共振法（多策略共振加分）


@dataclass
class SignalStrength:
    """信号强度"""

    strategy_name: str  # 策略名称
    signal_date: str  # 信号日期
    strength: float  # 信号强度（0-1）
    weight: float = 1.0  # 权重
    confidence: float = 1.0  # 置信度


@dataclass
class EnsembleSignal:
    """集成信号"""

    date: str  # 信号日期
    method: EnsembleMethod  # 集成方法
    total_strength: float  # 总信号强度
    signal_count: int  # 发出信号的策略数量
    is_valid: bool  # 是否有效（达到入场阈值）

    # 详细信息
    signals: list[SignalStrength] = field(default_factory=list)

    def get_top_strategies(self, n: int = 3) -> list[str]:
        """获取信号最强的前N个策略"""
        sorted_signals = sorted(self.signals, key=lambda s: s.strength * s.weight, reverse=True)
        return [s.strategy_name for s in sorted_signals[:n]]


@dataclass
class EnsembleConfig:
    """集成配置"""

    method: EnsembleMethod = EnsembleMethod.VOTING
    min_signals: int = 2  # 最少需要几个策略同意（投票法）
    strength_threshold: float = 0.6  # 信号强度阈值
    weights: dict[str, float] = field(default_factory=dict)  # 策略权重（加权法）


@dataclass
class EnsembleResult:
    """集成回测结果"""

    ts_code: str
    trades: list[dict] = field(default_factory=list)

    # 基础指标
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_return: float = 0.0
    sharpe_ratio: float = 0.0

    # 集成指标
    signal_utilization: float = 0.0  # 信号利用率（实际交易 / 总信号）
    avg_signals_per_trade: float = 0.0  # 每笔交易平均信号数
    ensemble_boost: float = 0.0  # 集成提升（相比单策略的胜率提升）


def create_ensemble_signal(
    date: str,
    signals: list[SignalStrength],
    config: EnsembleConfig,
) -> EnsembleSignal:
    """
    创建集成信号

    Args:
        date: 信号日期
        signals: 各策略的信号强度列表
        config: 集成配置

    Returns:
        EnsembleSignal: 集成信号
    """
    if not signals:
        return EnsembleSignal(
            date=date,
            method=config.method,
            total_strength=0.0,
            signal_count=0,
            is_valid=False,
        )

    # 根据集成方法计算总信号强度
    if config.method == EnsembleMethod.VOTING:
        # 投票法：统计信号数量
        valid_signals = [s for s in signals if s.strength >= config.strength_threshold]
        signal_count = len(valid_signals)
        total_strength = signal_count / len(signals) if signals else 0.0
        is_valid = signal_count >= config.min_signals

    elif config.method == EnsembleMethod.WEIGHTED:
        # 加权法：按权重加总
        total_strength = sum(s.strength * s.weight for s in signals)
        signal_count = len([s for s in signals if s.strength >= config.strength_threshold])
        is_valid = total_strength >= config.strength_threshold

    else:  # RESONANCE
        # 共振法：信号强度相乘（类似概率）
        total_strength = 1.0
        for s in signals:
            total_strength *= s.strength
        signal_count = len(signals)
        is_valid = total_strength >= config.strength_threshold

    return EnsembleSignal(
        date=date,
        method=config.method,
        total_strength=total_strength,
        signal_count=signal_count,
        is_valid=is_valid,
        signals=signals,
    )


def analyze_signal_correlation(
    trades_with_signals: list[dict],
) -> dict[str, float]:
    """
    分析信号相关性

    计算各策略信号与盈利的关联性

    Args:
        trades_with_signals: 交易列表，每笔交易包含触发的策略信号

    Returns:
        策略名称 -> 相关性得分（0-1）

    Example:
        >>> trades = [
        ...     {"pnl_pct": 5.0, "signals": ["B1", "长安"]},
        ...     {"pnl_pct": -2.0, "signals": ["B1"]},
        ...     {"pnl_pct": 8.0, "signals": ["B1", "B2", "娜娜"]},
        ... ]
        >>> correlation = analyze_signal_correlation(trades)
        >>> print(correlation)
        {"B1": 0.75, "长安": 0.90, "B2": 0.95, "娜娜": 0.95}
    """
    # 统计每个策略的胜率
    strategy_stats: dict[str, dict] = {}

    for trade in trades_with_signals:
        pnl = trade.get("pnl_pct", 0.0)
        signals = trade.get("signals", [])

        for strategy in signals:
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {"wins": 0, "total": 0}

            strategy_stats[strategy]["total"] += 1
            if pnl > 0:
                strategy_stats[strategy]["wins"] += 1

    # 计算胜率作为相关性得分
    correlation = {}
    for strategy, stats in strategy_stats.items():
        if stats["total"] > 0:
            win_rate = stats["wins"] / stats["total"]
            correlation[strategy] = win_rate

    return correlation


def optimize_ensemble_weights(
    trades_with_signals: list[dict],
    method: EnsembleMethod = EnsembleMethod.WEIGHTED,
) -> dict[str, float]:
    """
    优化集成权重

    根据历史交易数据，自动学习最优的策略权重

    Args:
        trades_with_signals: 历史交易列表
        method: 集成方法

    Returns:
        策略名称 -> 最优权重

    Example:
        >>> weights = optimize_ensemble_weights(trades)
        >>> print(weights)
        {"B1": 1.0, "B2": 1.5, "长安": 1.2, "娜娜": 0.8}
    """
    if method != EnsembleMethod.WEIGHTED:
        return {}

    # 1. 分析信号相关性
    correlation = analyze_signal_correlation(trades_with_signals)

    if not correlation:
        return {}

    # 2. 将相关性归一化为权重
    max_corr = max(correlation.values())
    if max_corr > 0:
        weights = {strategy: corr / max_corr for strategy, corr in correlation.items()}
    else:
        weights = {strategy: 1.0 for strategy in correlation}

    return weights


@dataclass
class MultiStrategyBacktestResult:
    """多策略集成回测结果"""

    ts_code: str
    ensemble_config: EnsembleConfig

    # 交易列表
    trades: list[dict] = field(default_factory=list)

    # 基础指标
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0

    # 集成指标
    signals_per_trade: float = 0.0  # 平均每笔交易的信号数
    ensemble_boost: float = 0.0  # 相比单策略的胜率提升

    # 策略贡献
    strategy_contributions: dict[str, float] = field(default_factory=dict)


def backtest_with_ensemble(
    ts_code: str,
    days: int = 500,
    config: EnsembleConfig | None = None,
    base_loop_config: Any = None,
) -> MultiStrategyBacktestResult:
    """
    使用策略集成进行回测

    Args:
        ts_code: 股票代码
        days: 回测天数
        config: 集成配置
        base_loop_config: 基础 LoopConfig

    Returns:
        MultiStrategyBacktestResult: 集成回测结果
    """
    from modules.loop_engine import LoopConfig
    from modules.backtest import backtest_shaofu_single

    # 默认配置
    if config is None:
        config = EnsembleConfig(method=EnsembleMethod.VOTING, min_signals=2)

    if base_loop_config is None:
        base_loop_config = LoopConfig()

    # 1. 先运行基础回测（使用 B1 信号）
    base_result = backtest_shaofu_single(ts_code, days=days, config=base_loop_config)

    # 2. 提取交易信号（当前简化处理：假设所有交易都是 B1 信号）
    trades_with_signals: list[dict[str, Any]] = [
        {
            "entry_date": t.entry_date,
            "exit_date": t.exit_date,
            "pnl_pct": t.pnl_pct,
            "signals": ["B1"],  # 简化：只有 B1
            "holding_days": t.holding_days,
        }
        for t in base_result.trades
    ]

    # 3. 根据集成配置过滤交易
    filtered_trades = []
    for trade in trades_with_signals:
        # 创建集成信号
        signals = [
            SignalStrength(
                strategy_name=s,
                signal_date=trade["entry_date"],
                strength=1.0,  # 简化：所有信号强度为 1
            )
            for s in trade["signals"]
        ]

        ensemble_signal = create_ensemble_signal(trade["entry_date"], signals, config)

        # 只有集成信号有效时才保留交易
        if ensemble_signal.is_valid:
            filtered_trades.append(trade)

    # 4. 计算集成指标
    result = MultiStrategyBacktestResult(
        ts_code=ts_code,
        ensemble_config=config,
        trades=filtered_trades,
        total_trades=len(filtered_trades),
    )

    if filtered_trades:
        # 计算基础指标
        pnls = [t["pnl_pct"] for t in filtered_trades]
        wins = [p for p in pnls if p > 0]
        result.win_rate = len(wins) / len(pnls) if pnls else 0.0

        total_profit = sum(p for p in pnls if p > 0)
        total_loss = abs(sum(p for p in pnls if p < 0))
        result.profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        result.total_return = sum(pnls) / 100.0  # 简化：累计收益

        # 计算平均每笔交易的信号数
        avg_signals = sum(len(t["signals"]) for t in filtered_trades) / len(filtered_trades)
        result.signals_per_trade = avg_signals

        # 计算集成提升（相比单策略）
        base_win_rate = base_result.win_rate
        if base_win_rate > 0:
            result.ensemble_boost = (result.win_rate - base_win_rate) / base_win_rate

    return result

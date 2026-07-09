#!/usr/bin/env python3
"""
统计检验框架

提供策略绩效的统计显著性检验，包括：
- 夏普比率 t 检验（判断夏普是否显著大于0）
- Bootstrap 置信区间（估计夏普的真实范围）
- Monte Carlo 置换检验（防数据挖掘）

核心问题：夏普比率 0.8 是"真有能力"还是"运气好"？

依赖：仅使用 Python 标准库 + numpy（通过传递依赖）
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class SharpeTestResult:
    """夏普比率统计检验结果"""

    # 点估计
    sharpe_ratio: float  # 样本夏普比率

    # t 检验
    t_statistic: float  # t 统计量
    p_value: float  # p-value（H0: 夏普=0）
    is_significant: bool  # p < 0.05？

    # Bootstrap 置信区间
    ci_lower: float  # 95% CI 下界
    ci_upper: float  # 95% CI 上界
    ci_significant: bool  # CI 下界 > 0.3？

    # 标准误
    standard_error: float  # 夏普比率的标准误

    # 元数据
    sample_size: int  # 样本量（交易日数）
    n_bootstrap: int  # Bootstrap 重采样次数


def _calculate_sharpe(returns: list[float], rf: float = 0.0) -> float:
    """
    计算夏普比率（年化）

    Args:
        returns: 日收益率序列（小数形式，如 0.01 表示 1%）
        rf: 无风险利率（年化，默认 0）

    Returns:
        年化夏普比率
    """
    if len(returns) < 2:
        return 0.0

    n = len(returns)
    mean_ret = sum(returns) / n
    daily_rf = rf / 252.0  # 日无风险利率

    # 样本标准差（除以 n-1）
    variance = sum((r - mean_ret) ** 2 for r in returns) / (n - 1)
    # 零方差防御：跨 Python 版本/浮点实现的 sum 可能产生 1e-36 量级非零残差，
    # 直接进 sqrt 会让 std_ret 极小、夏普爆炸到 1e+16。这里把"近似零"按零处理。
    std_ret = math.sqrt(variance) if variance > 1e-18 else 0.0

    if std_ret == 0:
        return 0.0

    # 日夏普 × √252 = 年化夏普
    daily_sharpe = (mean_ret - daily_rf) / std_ret
    return daily_sharpe * math.sqrt(252.0)


def sharpe_t_test(
    returns: list[float],
    rf: float = 0.0,
    alpha: float = 0.05,
) -> SharpeTestResult:
    """
    夏普比率 t 检验

    H0: 夏普比率 = 0（策略无效）
    H1: 夏普比率 > 0（策略有效）

    使用 Lo (2002) 的标准误估计方法：
    SE(Sharpe) ≈ √[(1 + Sharpe²/2) / n]

    Args:
        returns: 日收益率序列
        rf: 无风险利率（年化）
        alpha: 显著性水平（默认 0.05）

    Returns:
        SharpeTestResult: 包含 t 统计量、p-value、置信区间
    """
    n = len(returns)
    if n < 10:
        # 样本量太小，无法有效检验，但仍然计算夏普比率
        sharpe = _calculate_sharpe(returns, rf)
        return SharpeTestResult(
            sharpe_ratio=sharpe,
            t_statistic=0.0,
            p_value=1.0,
            is_significant=False,
            ci_lower=0.0,
            ci_upper=0.0,
            ci_significant=False,
            standard_error=0.0,
            sample_size=n,
            n_bootstrap=0,
        )

    # 1. 计算点估计夏普
    sharpe = _calculate_sharpe(returns, rf)

    # 2. 计算标准误（Lo 2002 近似）
    # SE = √[(1 + SR²/2) / n]
    se = math.sqrt((1.0 + sharpe**2 / 2.0) / n)

    # 3. t 统计量
    t_stat = sharpe / se if se > 0 else 0.0

    # 4. p-value（单侧检验，H1: SR > 0）
    # 使用 t 分布的 CDF 近似（大样本下近似正态）
    # 简化实现：使用正态分布近似
    p_value = _normal_cdf(-t_stat)  # P(Z < -t) = 1 - P(Z < t)

    # 5. Bootstrap 置信区间
    ci_lower, ci_upper, n_bootstrap = _bootstrap_ci(returns, rf, n_iterations=1000, alpha=alpha)

    # 6. 判断显著性
    is_significant = p_value < alpha
    ci_significant = ci_lower > 0.3  # 实际交易中，下界 > 0.3 才有意义

    return SharpeTestResult(
        sharpe_ratio=sharpe,
        t_statistic=t_stat,
        p_value=p_value,
        is_significant=is_significant,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_significant=ci_significant,
        standard_error=se,
        sample_size=n,
        n_bootstrap=n_bootstrap,
    )


def _bootstrap_ci(
    returns: list[float],
    rf: float = 0.0,
    n_iterations: int = 1000,
    alpha: float = 0.05,
    seed: int | None = None,
) -> tuple[float, float, int]:
    """
    Bootstrap 置信区间

    通过重采样估计夏普比率的真实分布

    Args:
        returns: 日收益率序列
        rf: 无风险利率
        n_iterations: Bootstrap 次数
        alpha: 置信水平（0.05 = 95% CI）
        seed: 随机种子（可选，用于复现）

    Returns:
        (ci_lower, ci_upper, n_iterations): 置信区间上下界和实际迭代次数
    """
    if len(returns) < 2:
        return 0.0, 0.0, 0

    if seed is not None:
        random.seed(seed)

    sharpes = []
    n = len(returns)

    for _ in range(n_iterations):
        # 有放回重采样
        sample = [returns[random.randint(0, n - 1)] for _ in range(n)]
        sharpe = _calculate_sharpe(sample, rf)
        sharpes.append(sharpe)

    if not sharpes:
        return 0.0, 0.0, 0

    # 排序后取分位数
    sharpes.sort()
    lower_idx = int((alpha / 2) * len(sharpes))
    upper_idx = int((1 - alpha / 2) * len(sharpes)) - 1

    ci_lower = sharpes[max(0, lower_idx)]
    ci_upper = sharpes[min(len(sharpes) - 1, upper_idx)]

    return ci_lower, ci_upper, len(sharpes)


def _normal_cdf(x: float) -> float:
    """
    标准正态分布 CDF 近似

    使用 Abramowitz and Stegun 公式 7.1.26
    误差 < 1.5e-7
    """
    # 使用误差函数近似：Φ(x) = 0.5 * [1 + erf(x/√2)]
    # 简化实现：使用多项式近似
    if x < -8.0:
        return 0.0
    if x > 8.0:
        return 1.0

    # 标准正态 CDF 的多项式近似
    # 基于 Handbook of Mathematical Functions (Abramowitz & Stegun)
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911

    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2.0)

    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)

    return 0.5 * (1.0 + sign * y)


@dataclass
class MonteCarloTestResult:
    """Monte Carlo 置换检验结果"""

    actual_sharpe: float  # 真实策略夏普
    mean_permuted_sharpe: float  # 随机策略平均夏普
    std_permuted_sharpe: float  # 随机策略夏普标准差
    p_value: float  # p-value（随机策略打败真实策略的概率）
    is_significant: bool  # p < 0.05？
    n_permutations: int  # 置换次数


def monte_carlo_permutation_test(
    returns: list[float],
    rf: float = 0.0,
    n_permutations: int = 1000,
    alpha: float = 0.05,
    seed: int | None = None,
) -> MonteCarloTestResult:
    """
    Monte Carlo 置换检验

    打乱交易信号日期，检验策略是否只是"运气好"

    H0: 策略收益来自随机分布（策略无效）
    H1: 策略收益显著高于随机（策略有效）

    Args:
        returns: 策略的日收益率序列
        rf: 无风险利率
        n_permutations: 置换次数
        alpha: 显著性水平
        seed: 随机种子

    Returns:
        MonteCarloTestResult: 置换检验结果
    """
    if len(returns) < 10:
        return MonteCarloTestResult(
            actual_sharpe=0.0,
            mean_permuted_sharpe=0.0,
            std_permuted_sharpe=0.0,
            p_value=1.0,
            is_significant=False,
            n_permutations=0,
        )

    if seed is not None:
        random.seed(seed)

    # 1. 计算真实夏普
    actual_sharpe = _calculate_sharpe(returns, rf)

    # 2. 置换检验
    permuted_sharpes = []

    for _ in range(n_permutations):
        # 打乱收益率序列（模拟随机信号日期）
        permuted = returns.copy()
        random.shuffle(permuted)
        sharpe = _calculate_sharpe(permuted, rf)
        permuted_sharpes.append(sharpe)

    # 3. 计算统计量
    mean_perm = sum(permuted_sharpes) / len(permuted_sharpes)
    variance = sum((s - mean_perm) ** 2 for s in permuted_sharpes) / (len(permuted_sharpes) - 1)
    std_perm = math.sqrt(variance) if variance > 0 else 0.0

    # 4. p-value: 随机策略夏普 >= 真实策略夏普的概率
    n_beat = sum(1 for s in permuted_sharpes if s >= actual_sharpe)
    p_value = n_beat / len(permuted_sharpes)

    # 5. 判断显著性
    is_significant = p_value < alpha

    return MonteCarloTestResult(
        actual_sharpe=actual_sharpe,
        mean_permuted_sharpe=mean_perm,
        std_permuted_sharpe=std_perm,
        p_value=p_value,
        is_significant=is_significant,
        n_permutations=n_permutations,
    )


@dataclass
class SubPeriodAnalysis:
    """子周期分析结果"""

    # 整体
    overall_sharpe: float
    overall_return: float
    overall_max_drawdown: float

    # 按市场环境分组
    bull_sharpe: float = 0.0
    bull_return: float = 0.0
    bull_win_rate: float = 0.0
    bull_trades: int = 0

    bear_sharpe: float = 0.0
    bear_return: float = 0.0
    bear_win_rate: float = 0.0
    bear_trades: int = 0

    sideways_sharpe: float = 0.0
    sideways_return: float = 0.0
    sideways_win_rate: float = 0.0
    sideways_trades: int = 0

    # 稳健性评分
    robustness_score: float = 0.0  # 0-100，三个子周期都赚钱得分高

    def is_robust(self) -> bool:
        """判断策略是否稳健（三个子周期都有效）"""
        return (
            self.bull_sharpe > 0.0
            and self.bear_sharpe > 0.0
            and self.sideways_sharpe > 0.0
            and self.robustness_score >= 60.0
        )


def analyze_sub_periods(
    trades: list[dict],
    market_regimes: dict[str, str],
) -> SubPeriodAnalysis:
    """
    子周期分析

    分别统计牛市/熊市/震荡市的绩效，检验策略是否只在特定市场有效

    Args:
        trades: 交易列表，每个交易包含 date, pnl_pct, holding_days
        market_regimes: 日期 -> 市场环境映射 ('bull'/'bear'/'sideways')

    Returns:
        SubPeriodAnalysis: 子周期分析结果
    """
    # 按市场环境分组
    bull_trades = []
    bear_trades = []
    sideways_trades = []
    all_returns = []

    for trade in trades:
        trade_date = trade.get("date", "")
        pnl = trade.get("pnl_pct", 0.0)

        regime = market_regimes.get(trade_date, "unknown")
        if regime == "bull":
            bull_trades.append(trade)
        elif regime == "bear":
            bear_trades.append(trade)
        elif regime == "sideways":
            sideways_trades.append(trade)

        # 收集所有收益（用于整体计算）
        all_returns.append(pnl / 100.0)  # 转为小数

    # 计算整体指标
    overall_sharpe = _calculate_sharpe(all_returns) if all_returns else 0.0
    overall_return = sum(all_returns) if all_returns else 0.0
    overall_max_dd = _calc_max_drawdown_from_returns(all_returns) if all_returns else 0.0

    # 计算各子周期指标
    def calc_sub_stats(trade_list):
        if not trade_list:
            return 0.0, 0.0, 0.0

        pnls = [t.get("pnl_pct", 0.0) / 100.0 for t in trade_list]
        wins = [p for p in pnls if p > 0]
        sharpe = _calculate_sharpe(pnls) if pnls else 0.0
        ret = sum(pnls) if pnls else 0.0
        win_rate = len(wins) / len(pnls) if pnls else 0.0
        return sharpe, ret, win_rate

    bull_sharpe, bull_ret, bull_wr = calc_sub_stats(bull_trades)
    bear_sharpe, bear_ret, bear_wr = calc_sub_stats(bear_trades)
    sideways_sharpe, sideways_ret, sideways_wr = calc_sub_stats(sideways_trades)

    # 稳健性评分（0-100）
    # 三个子周期都赚钱：基础 60 分
    # 每个子周期夏普 > 0.5：额外 10 分
    # 最差子周期夏普 > 0：额外 10 分
    score = 0.0
    if bull_sharpe > 0 and bear_sharpe > 0 and sideways_sharpe > 0:
        score += 60.0
    if bull_sharpe > 0.5:
        score += 10.0
    if bear_sharpe > 0.5:
        score += 10.0
    if sideways_sharpe > 0.5:
        score += 10.0
    min_sharpe = min(bull_sharpe, bear_sharpe, sideways_sharpe)
    if min_sharpe > 0:
        score += 10.0

    return SubPeriodAnalysis(
        overall_sharpe=overall_sharpe,
        overall_return=overall_return,
        overall_max_drawdown=overall_max_dd,
        bull_sharpe=bull_sharpe,
        bull_return=bull_ret,
        bull_win_rate=bull_wr,
        bull_trades=len(bull_trades),
        bear_sharpe=bear_sharpe,
        bear_return=bear_ret,
        bear_win_rate=bear_wr,
        bear_trades=len(bear_trades),
        sideways_sharpe=sideways_sharpe,
        sideways_return=sideways_ret,
        sideways_win_rate=sideways_wr,
        sideways_trades=len(sideways_trades),
        robustness_score=score,
    )


def _calc_max_drawdown_from_returns(returns: list[float]) -> float:
    """从收益率序列计算最大回撤"""
    if not returns:
        return 0.0

    # 从收益率计算累计净值
    equity = [1.0]
    for r in returns:
        equity.append(equity[-1] * (1 + r))

    # 计算最大回撤
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return max_dd

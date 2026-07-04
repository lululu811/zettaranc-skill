"""
专业回测绩效指标模块测试。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from modules.simulator.metrics import PerformanceMetrics, calculate_metrics


def test_calculate_metrics_basic():
    """基础功能：返回 PerformanceMetrics 并计算总收益与最大回撤。"""
    equity_curve = [
        {"date": "20240101", "equity": 1000000},
        {"date": "20240102", "equity": 1100000},
        {"date": "20240103", "equity": 1050000},
    ]
    benchmark_curve = [
        {"date": "20240101", "close": 100},
        {"date": "20240102", "close": 102},
        {"date": "20240103", "close": 101},
    ]
    trades = []
    m = calculate_metrics(equity_curve, benchmark_curve, trades)
    assert isinstance(m, PerformanceMetrics)
    assert m.total_return == pytest.approx(0.05)
    assert m.max_drawdown > 0


def test_total_and_annualized_return():
    """总收益与年化收益按 252 个交易日年化。"""
    equity_curve = [
        {"date": "20240101", "equity": 1000000},
        {"date": "20240102", "equity": 1100000},
    ]
    m = calculate_metrics(equity_curve, [], [])
    assert m.total_return == pytest.approx(0.10)
    # (1.1)^(252/1) - 1
    assert m.annualized_return == pytest.approx(1.1**252 - 1.0, rel=1e-9)


def test_sharpe_and_sortino():
    """夏普与索提诺使用日收益率年化。"""
    equity_curve = [
        {"date": "20240101", "equity": 100},
        {"date": "20240102", "equity": 99},
        {"date": "20240103", "equity": 98},
        {"date": "20240104", "equity": 102},
    ]
    m = calculate_metrics(equity_curve, [], [])
    rets = [-0.01, -1 / 99, (102 - 98) / 98]
    mean_r = sum(rets) / len(rets)
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1))
    assert m.sharpe_ratio == pytest.approx((mean_r / std_r) * math.sqrt(252))

    neg = [r for r in rets if r < 0]
    mean_neg = sum(neg) / len(neg)
    std_neg = math.sqrt(sum((r - mean_neg) ** 2 for r in neg) / (len(neg) - 1))
    assert m.sortino_ratio == pytest.approx((mean_r / std_neg) * math.sqrt(252))


def test_max_drawdown_and_duration():
    """最大回撤为正值，持续时间按高点到下一新高计算。"""
    equity_curve = [
        {"date": "20240101", "equity": 100},
        {"date": "20240102", "equity": 110},
        {"date": "20240103", "equity": 105},
        {"date": "20240104", "equity": 100},
        {"date": "20240105", "equity": 115},
    ]
    m = calculate_metrics(equity_curve, [], [])
    # 从 110 跌到 100，回撤 10/110
    assert m.max_drawdown == pytest.approx(10 / 110)
    # 高点在 idx1，下一新高在 idx4，持续 3 个交易日
    assert m.max_drawdown_duration == 3


def test_calmar_ratio():
    """Calmar = 年化收益 / |最大回撤|。"""
    equity_curve = [
        {"date": "20240101", "equity": 100},
        {"date": "20240102", "equity": 110},
        {"date": "20240103", "equity": 99},
    ]
    m = calculate_metrics(equity_curve, [], [])
    assert m.calmar_ratio == pytest.approx(
        m.annualized_return / abs(m.max_drawdown), rel=1e-9
    )


def test_benchmark_return_alpha_beta():
    """基准收益、beta、alpha 计算正确。"""
    equity_curve = [
        {"date": "20240101", "equity": 100},
        {"date": "20240102", "equity": 102},
        {"date": "20240103", "equity": 101},
    ]
    benchmark_curve = [
        {"date": "20240101", "close": 100},
        {"date": "20240102", "close": 101},
        {"date": "20240103", "close": 100},
    ]
    m = calculate_metrics(equity_curve, benchmark_curve, [])
    assert m.benchmark_return == pytest.approx(0.0)
    # strategy rets: 0.02, -0.00490099; benchmark rets: 0.01, -0.00990099
    strat_rets = [0.02, (101 - 102) / 102]
    bench_rets = [0.01, (100 - 101) / 101]
    slope, intercept = calculate_linear_regression(bench_rets, strat_rets)
    assert m.beta == pytest.approx(slope, rel=1e-6)
    assert m.alpha == pytest.approx(intercept * 252.0, rel=1e-6)


def test_trade_statistics():
    """交易统计仅使用 SELL 成交。"""
    equity_curve = [
        {"date": "20240101", "equity": 100000},
        {"date": "20240102", "equity": 100000},
    ]

    @dataclass
    class _Trade:
        action: str
        pnl: float

    trades = [
        _Trade(action="BUY", pnl=0),
        _Trade(action="SELL", pnl=1000),
        _Trade(action="SELL", pnl=-500),
        _Trade(action="SELL", pnl=800),
        _Trade(action="SELL", pnl=-200),
    ]
    m = calculate_metrics(equity_curve, [], trades)
    assert m.win_rate == pytest.approx(0.5)
    assert m.avg_win == pytest.approx(900.0)
    assert m.avg_loss == pytest.approx(350.0)
    assert m.profit_factor == pytest.approx(1800 / 700)
    assert m.gain_loss_ratio == pytest.approx(900 / 350)
    assert m.max_consecutive_wins == 1
    assert m.max_consecutive_losses == 1


def test_max_consecutive_wins_and_losses():
    """连胜/连亏按 SELL 顺序统计。"""
    equity_curve = [{"date": "20240101", "equity": 100}, {"date": "20240102", "equity": 100}]

    @dataclass
    class _Trade:
        action: str
        pnl: float

    trades = [
        _Trade(action="SELL", pnl=100),
        _Trade(action="SELL", pnl=100),
        _Trade(action="SELL", pnl=-50),
        _Trade(action="SELL", pnl=-50),
        _Trade(action="SELL", pnl=-50),
        _Trade(action="SELL", pnl=200),
    ]
    m = calculate_metrics(equity_curve, [], trades)
    assert m.max_consecutive_wins == 2
    assert m.max_consecutive_losses == 3


def test_empty_inputs_return_defaults():
    """空输入返回默认零值指标。"""
    m = calculate_metrics([], [], [])
    assert m.total_return == 0.0
    assert m.sharpe_ratio == 0.0
    assert m.max_drawdown == 0.0


def test_single_equity_point():
    """单点资金曲线无法计算日收益，总收益为零。"""
    m = calculate_metrics([{"date": "20240101", "equity": 100}], [], [])
    assert m.total_return == 0.0
    assert m.annualized_return == 0.0


def test_volatility_annual():
    """年化波动率 = 日收益标准差 * sqrt(252)。"""
    equity_curve = [
        {"date": "20240101", "equity": 100},
        {"date": "20240102", "equity": 101},
        {"date": "20240103", "equity": 99},
        {"date": "20240104", "equity": 102},
    ]
    m = calculate_metrics(equity_curve, [], [])
    rets = [0.01, -0.01980198, 0.03030303]
    mean_r = sum(rets) / len(rets)
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1))
    assert m.volatility_annual == pytest.approx(std_r * math.sqrt(252))


def calculate_linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """测试辅助：手动实现一元线性回归。"""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return 0.0, mean_y
    slope = cov / var_x
    intercept = mean_y - slope * mean_x
    return slope, intercept

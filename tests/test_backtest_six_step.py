"""少妇战法六步闭环回测测试"""

from __future__ import annotations

import pytest

from modules.backtest_six_step import _calc_metrics, ShaofuBacktestResult
from modules.loop_engine import LoopTrade


def _make_trade(pnl_pct: float, position_pct: float = 1.0) -> LoopTrade:
    """构造一笔带仓位比例的 LoopTrade"""
    return LoopTrade(
        ts_code="600519.SH",
        entry_date="20260101",
        entry_price=100.0,
        entry_reason="B1",
        stop_loss_price=95.0,
        exit_date="20260102",
        exit_price=100.0 * (1 + pnl_pct / 100),
        exit_reason="白线跌破",
        pnl_pct=pnl_pct,
        holding_days=5,
        position_pct=position_pct,
    )


def test_calc_metrics_full_position_compound():
    """全仓时资金曲线按正常复利计算"""
    result = ShaofuBacktestResult(ts_code="600519.SH")
    result.trades = [_make_trade(10.0, 1.0), _make_trade(-5.0, 1.0)]
    _calc_metrics(result)

    # 曲线：100 -> 110 -> 104.5
    assert result.total_return == pytest.approx(1.10 * 0.95 - 1, rel=1e-6)
    assert result.equity_curve == pytest.approx([100.0, 110.0, 104.5], rel=1e-6)
    assert result.max_drawdown > 0


def test_calc_metrics_half_position_reduces_risk():
    """半仓时最大回撤和收益绝对值都下降，但 Sharpe 不变"""
    result_full = ShaofuBacktestResult(ts_code="600519.SH")
    result_full.trades = [_make_trade(10.0, 1.0), _make_trade(-10.0, 1.0)]
    _calc_metrics(result_full)

    result_half = ShaofuBacktestResult(ts_code="600519.SH")
    result_half.trades = [_make_trade(10.0, 0.5), _make_trade(-10.0, 0.5)]
    _calc_metrics(result_half)

    # 半仓最大回撤应小于全仓
    assert result_half.max_drawdown < result_full.max_drawdown
    # 半仓收益绝对值应小于全仓
    assert abs(result_half.total_return) < abs(result_full.total_return)
    # 单笔收益分布未变，Sharpe 应近似
    assert result_half.sharpe_ratio == pytest.approx(result_full.sharpe_ratio, rel=1e-6)


def test_calc_metrics_zero_position_pct_defaults_to_full():
    """position_pct 为 0 时退化到全仓，避免资金曲线僵死"""
    result = ShaofuBacktestResult(ts_code="600519.SH")
    result.trades = [_make_trade(10.0, 0.0), _make_trade(-5.0, 0.0)]
    _calc_metrics(result)

    # position_pct=0 时按 1.0 处理，资金曲线仍有变化
    assert result.total_return == pytest.approx(1.10 * 0.95 - 1, rel=1e-6)
    assert result.equity_curve[-1] != 100.0

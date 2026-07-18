"""组合级 Walk-forward 验证测试（v3.7.7）"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.verify.portfolio_engine import PortfolioBacktestResult, PortfolioConfig
from modules.verify.portfolio_walk_forward import (
    _aggregate_portfolio_results,
    portfolio_walk_forward_verify,
)
from modules.verify.walk_forward import WFResult


def _make_portfolio_result(
    total_trades: int = 5,
    win_count: int = 3,
    total_return: float = 0.10,
    annualized_return: float = 0.25,
    sharpe_ratio: float = 1.0,
    max_drawdown: float = 0.10,
    calmar: float = 2.5,
) -> PortfolioBacktestResult:
    result = PortfolioBacktestResult()
    result.total_trades = total_trades
    result.win_count = win_count
    result.loss_count = total_trades - win_count
    result.win_rate = win_count / total_trades if total_trades > 0 else 0.0
    result.total_return = total_return
    result.annualized_return = annualized_return
    result.sharpe_ratio = sharpe_ratio
    result.max_drawdown = max_drawdown
    result.calmar = calmar
    return result


def test_portfolio_wf_degrades_when_too_few_splits(monkeypatch):
    """实际交易日太少导致切片数 < 3 时降级"""
    engine_mock = MagicMock()
    engine_mock.load_data.return_value = ({}, ["d1", "d2"])

    monkeypatch.setattr(
        "modules.verify.portfolio_walk_forward.PortfolioBacktestEngine",
        lambda *args, **kwargs: engine_mock,
    )

    result = portfolio_walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=250,
        wf_train_days=120,
        wf_test_days=60,
    )
    assert isinstance(result, WFResult)
    assert result.degraded
    assert result.splits == []


def test_portfolio_wf_runs_is_and_oos_windows(monkeypatch):
    """IS 段好 / OOS 段差，oos_is_ratio 必须反映差异"""
    call_idx = {"n": 0}

    def fake_run_with_data(klines_map, all_dates, start_date=None, end_date=None):
        call_idx["n"] += 1
        # 调用顺序：IS1, OOS1, IS2, OOS2, IS3, OOS3
        is_is = call_idx["n"] % 2 == 1
        return _make_portfolio_result(
            sharpe_ratio=2.0 if is_is else 0.6,
            total_trades=5,
        )

    engine_mock = MagicMock()
    engine_mock.load_data.return_value = (
        {},
        [f"d{i}" for i in range(1, 16)],  # 15 个交易日，train=6 test=3 生成 3 段
    )
    engine_mock.run_with_data = fake_run_with_data

    monkeypatch.setattr(
        "modules.verify.portfolio_walk_forward.PortfolioBacktestEngine",
        lambda *args, **kwargs: engine_mock,
    )

    result = portfolio_walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=15,
        wf_train_days=6,
        wf_test_days=3,
    )

    assert not result.degraded
    assert len(result.splits) == 3
    assert call_idx["n"] == 6
    assert result.is_metrics is not None
    assert result.oos_metrics is not None
    assert result.is_metrics.sharpe == pytest.approx(2.0, rel=1e-6)
    assert result.oos_metrics.sharpe == pytest.approx(0.6, rel=1e-6)
    assert result.oos_is_ratio == pytest.approx(0.3, rel=1e-6)


def test_portfolio_wf_aggregates_segments(monkeypatch):
    """3 段 × (IS+OOS) 共 6 次 run_with_data 调用"""
    call_idx = {"n": 0}

    def fake_run_with_data(klines_map, all_dates, start_date=None, end_date=None):
        call_idx["n"] += 1
        idx = call_idx["n"]
        return _make_portfolio_result(
            total_trades=5,
            win_count=3,
            total_return=0.05 * idx,
            annualized_return=0.10 * idx,
            sharpe_ratio=1.0 + 0.1 * idx,
            max_drawdown=0.05 * idx,
            calmar=2.0 + 0.1 * idx,
        )

    engine_mock = MagicMock()
    engine_mock.load_data.return_value = ({}, [f"d{i}" for i in range(1, 16)])
    engine_mock.run_with_data = fake_run_with_data

    monkeypatch.setattr(
        "modules.verify.portfolio_walk_forward.PortfolioBacktestEngine",
        lambda *args, **kwargs: engine_mock,
    )

    result = portfolio_walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=15,
        wf_train_days=6,
        wf_test_days=3,
    )

    assert call_idx["n"] == 6
    assert result.is_metrics.total_trades == 15  # 3 段 × 5 笔
    assert result.oos_metrics.total_trades == 15
    # IS 调用序号为 1,3,5 → max_drawdown = 0.05*5 = 0.25
    assert result.is_metrics.max_drawdown == pytest.approx(0.25, rel=1e-6)
    # OOS 调用序号为 2,4,6 → max_drawdown = 0.05*6 = 0.30
    assert result.oos_metrics.max_drawdown == pytest.approx(0.30, rel=1e-6)


def test_portfolio_wf_ignores_low_trade_segments(monkeypatch):
    """total_trades < 3 的段不计入 Sharpe 平均"""
    call_idx = {"n": 0}

    def fake_run_with_data(klines_map, all_dates, start_date=None, end_date=None):
        call_idx["n"] += 1
        idx = call_idx["n"]
        # 调用顺序：IS1, OOS1, IS2, OOS2, IS3, OOS3, IS4, OOS4
        is_is = idx % 2 == 1
        if is_is and idx == 1:
            return _make_portfolio_result(total_trades=1, sharpe_ratio=9.0)
        if is_is:
            return _make_portfolio_result(total_trades=5, sharpe_ratio=2.0)
        return _make_portfolio_result(total_trades=5, sharpe_ratio=1.0)

    engine_mock = MagicMock()
    # 12 个交易日：train=4 test=2 → 4 段
    engine_mock.load_data.return_value = ({}, [f"d{i}" for i in range(1, 13)])
    engine_mock.run_with_data = fake_run_with_data

    monkeypatch.setattr(
        "modules.verify.portfolio_walk_forward.PortfolioBacktestEngine",
        lambda *args, **kwargs: engine_mock,
    )

    result = portfolio_walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=12,
        wf_train_days=4,
        wf_test_days=2,
    )

    assert call_idx["n"] == 8
    # IS 中剔除了 total_trades=1 的第一段，剩余 3 段 sharpe=2.0
    assert result.is_metrics.sharpe == pytest.approx(2.0, rel=1e-6)
    assert result.oos_metrics.sharpe == pytest.approx(1.0, rel=1e-6)
    assert result.oos_is_ratio == pytest.approx(0.5, rel=1e-6)


def test_aggregate_portfolio_results_empty():
    """空结果返回默认 AggregateMetrics"""
    metrics = _aggregate_portfolio_results([])
    assert metrics.total_trades == 0
    assert metrics.sharpe == 0.0


def test_aggregate_portfolio_results_basic():
    """聚合多段组合回测结果"""
    results = [
        _make_portfolio_result(
            total_trades=10,
            win_count=6,
            total_return=0.10,
            annualized_return=0.20,
            sharpe_ratio=1.5,
            max_drawdown=0.08,
            calmar=2.5,
        ),
        _make_portfolio_result(
            total_trades=20,
            win_count=10,
            total_return=0.05,
            annualized_return=0.10,
            sharpe_ratio=0.5,
            max_drawdown=0.12,
            calmar=0.8,
        ),
    ]
    metrics = _aggregate_portfolio_results(results)
    assert metrics.total_trades == 30
    assert metrics.win_rate == pytest.approx(16 / 30, rel=1e-6)
    assert metrics.total_return_pct == pytest.approx(0.075, rel=1e-6)
    assert metrics.annualized_return == pytest.approx(0.15, rel=1e-6)
    assert metrics.sharpe == pytest.approx(1.0, rel=1e-6)
    assert metrics.max_drawdown == pytest.approx(0.12, rel=1e-6)
    assert metrics.calmar == pytest.approx(1.65, rel=1e-6)

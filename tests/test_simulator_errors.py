#!/usr/bin/env python3
"""
simulator 错误码接入测试（v3.10.4）

覆盖：
- ``run_simulation`` 配置非法（initial_capital / max_positions / days <= 0）
  → ``ZettarancError(SIMULATOR_INVALID_PRICE)``
- ``run_simulation`` 全部候选都拿不到 K 线
  → ``ZettarancError(SIMULATOR_NO_KLINES)``
- ``run_simulation`` 空 ts_codes 仍返回空 SimulationResult（保持向后兼容）
- ``run_simulation`` 正常路径返回 SimulationResult
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from modules.core.errors import ErrorCode, ZettarancError
from modules.simulator import SimulationConfig, SimulationResult, MarketRegime, MarketContext


def _ctx():
    return MarketContext(
        date="20260101", regime=MarketRegime.NEUTRAL, index_trend=50, breadth=0, moneyflow_score=50
    )


def test_run_simulation_invalid_initial_capital_raises():
    """initial_capital <= 0 → SIMULATOR_INVALID_PRICE"""
    from modules.simulator.simulator import run_simulation

    cfg = SimulationConfig(initial_capital=0.0)
    with pytest.raises(ZettarancError) as exc_info:
        run_simulation(ts_codes=[], days=30, config=cfg)
    assert exc_info.value.code == ErrorCode.SIMULATOR_INVALID_PRICE
    assert "initial_capital" in exc_info.value.message


def test_run_simulation_negative_initial_capital_raises():
    from modules.simulator.simulator import run_simulation

    cfg = SimulationConfig(initial_capital=-1000.0)
    with pytest.raises(ZettarancError) as exc_info:
        run_simulation(ts_codes=["600519.SH"], days=30, config=cfg)
    assert exc_info.value.code == ErrorCode.SIMULATOR_INVALID_PRICE


def test_run_simulation_invalid_max_positions_raises():
    from modules.simulator.simulator import run_simulation

    cfg = SimulationConfig(max_positions=0)
    with pytest.raises(ZettarancError) as exc_info:
        run_simulation(ts_codes=["600519.SH"], days=30, config=cfg)
    assert exc_info.value.code == ErrorCode.SIMULATOR_INVALID_PRICE
    assert "max_positions" in exc_info.value.message


def test_run_simulation_invalid_days_raises():
    from modules.simulator.simulator import run_simulation

    with pytest.raises(ZettarancError) as exc_info:
        run_simulation(ts_codes=["600519.SH"], days=0)
    assert exc_info.value.code == ErrorCode.SIMULATOR_INVALID_PRICE
    assert "days" in exc_info.value.message


def test_run_simulation_no_klines_raises():
    """全部候选都拿不到 K 线 → SIMULATOR_NO_KLINES"""
    from modules.simulator.simulator import run_simulation

    mock_ds = MagicMock()
    # 模拟"有 dates 但所有候选都拿不到 K 线"的场景
    dates = [f"20260{i:02d}01" for i in range(1, 31)]
    # _available_dates 走 ds.get_kline_dicts（必须返回非空以便 dates 有内容）
    mock_ds.get_kline_dicts.return_value = [{"trade_date": d} for d in dates]
    mock_ds.get_index_daily.return_value = MagicMock()
    mock_ds.get_index_daily.return_value.empty = True

    with patch("modules.simulator.simulator.get_datasource", return_value=mock_ds):
        # get_recent_klines 返回空 → klines_map 为空 → SIMULATOR_NO_KLINES
        with patch("modules.simulator.simulator.get_recent_klines", return_value=[]):
            with pytest.raises(ZettarancError) as exc_info:
                run_simulation(ts_codes=["600519.SH"], days=30, datasource=mock_ds)
    assert exc_info.value.code == ErrorCode.SIMULATOR_NO_KLINES
    assert "600519.SH" in exc_info.value.message
    assert "K 线" in exc_info.value.message


def test_run_simulation_empty_pool_returns_result():
    """空 ts_codes 仍返回空 SimulationResult（向后兼容）"""
    from modules.simulator.simulator import run_simulation

    result = run_simulation(ts_codes=[], days=30)
    assert isinstance(result, SimulationResult)
    assert result.total_trades == 0


def test_run_simulation_success_returns_result():
    """正常路径返回 SimulationResult，不抛错"""
    from modules.simulator.simulator import run_simulation
    from modules.simulator import SignalScore

    # 构造 60 根 K 线 + 1 个 PASS 信号
    klines = []
    for i in range(90):
        date = f"2026{i:02d}01" if i < 10 else "20260101"
        klines.append(
            type(
                "K",
                (),
                {
                    "trade_date": f"2026{(i // 30) + 1:02d}{(i % 30) + 1:02d}",
                    "open": 100.0,
                    "high": 102.0,
                    "low": 98.0,
                    "close": 101.0,
                    "vol": 10000.0,
                    "amount": 1010000.0,
                    "pct_chg": 1.0,
                },
            )()
        )
    sim_dates = [k.trade_date for k in klines[-30:]]

    mock_ds = MagicMock()
    mock_ds.get_kline_dicts.return_value = [
        {
            "trade_date": d,
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 101.0,
            "vol": 10000.0,
            "amount": 1010000.0,
            "pct_chg": 1.0,
        }
        for d in sim_dates
    ]
    mock_ds.get_index_daily.return_value = MagicMock()
    mock_ds.get_index_daily.return_value.empty = True

    with patch("modules.simulator.simulator.get_datasource", return_value=mock_ds):
        with patch("modules.simulator.simulator.get_recent_klines", return_value=klines):
            with patch("modules.simulator.simulator.get_market_context") as mock_ctx:
                mock_ctx.return_value = _ctx()
                with patch("modules.simulator.simulator.evaluate_stock") as mock_eval:
                    mock_eval.return_value = SignalScore(
                        ts_code="600519.SH",
                        name="茅台",
                        date=sim_dates[0],
                        score=85.0,
                        b1_score=80.0,
                        trend_score=80.0,
                        volume_score=80.0,
                        risk_score=80.0,
                        signals=[],
                        reasons=[],
                        warnings=[],
                    )
                    result = run_simulation(
                        ts_codes=["600519.SH"], days=30, datasource=mock_ds
                    )
    assert isinstance(result, SimulationResult)


def test_zettaranc_error_is_value_error_subclass_for_backward_compat():
    """ZettarancError 仍为 ValueError 子类 → 老 except ValueError 不受影响"""
    from modules.simulator.simulator import run_simulation

    with pytest.raises(ValueError):
        run_simulation(ts_codes=["600519.SH"], days=0)

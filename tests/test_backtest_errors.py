#!/usr/bin/env python3
"""
backtest 错误码接入测试（v3.10.4）

覆盖：
- ``PortfolioBacktestEngine.__init__`` 配置非法（initial_capital / max_positions /
  position_pct / min_cash_pct 越界）→ ``ZettarancError(BACKTEST_INVALID_CONFIG)``
- ``PortfolioBacktestEngine.run`` days <= 0 → ``BACKTEST_INVALID_CONFIG``
- ``PortfolioBacktestEngine.run`` ts_codes 为空 → ``BACKTEST_INVALID_CONFIG``
- ``PortfolioBacktestEngine.run`` 全部候选无 K 线 → ``BACKTEST_EMPTY_KLINES``
- ``backtest_strategy`` days <= 0 / ts_code 空 / stop_loss_pct <= 0 /
  take_profit_pct <= 0 → ``BACKTEST_INVALID_CONFIG``
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from modules.core.errors import ErrorCode, ZettarancError


def test_portfolio_engine_invalid_initial_capital_raises():
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(initial_capital=0.0)
    with pytest.raises(ZettarancError) as exc_info:
        PortfolioBacktestEngine(portfolio_config=cfg)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG
    assert "initial_capital" in exc_info.value.message


def test_portfolio_engine_negative_initial_capital_raises():
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(initial_capital=-1000.0)
    with pytest.raises(ZettarancError) as exc_info:
        PortfolioBacktestEngine(portfolio_config=cfg)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG


def test_portfolio_engine_invalid_max_positions_raises():
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(max_positions=0)
    with pytest.raises(ZettarancError) as exc_info:
        PortfolioBacktestEngine(portfolio_config=cfg)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG
    assert "max_positions" in exc_info.value.message


def test_portfolio_engine_invalid_position_pct_raises():
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(position_pct=0.0)
    with pytest.raises(ZettarancError) as exc_info:
        PortfolioBacktestEngine(portfolio_config=cfg)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG
    assert "position_pct" in exc_info.value.message


def test_portfolio_engine_invalid_position_pct_too_large_raises():
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(position_pct=1.5)
    with pytest.raises(ZettarancError) as exc_info:
        PortfolioBacktestEngine(portfolio_config=cfg)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG


def test_portfolio_engine_invalid_min_cash_pct_raises():
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(min_cash_pct=-0.1)
    with pytest.raises(ZettarancError) as exc_info:
        PortfolioBacktestEngine(portfolio_config=cfg)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG
    assert "min_cash_pct" in exc_info.value.message


def test_portfolio_engine_invalid_min_cash_pct_too_large_raises():
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(min_cash_pct=1.0)
    with pytest.raises(ZettarancError) as exc_info:
        PortfolioBacktestEngine(portfolio_config=cfg)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG


def test_portfolio_engine_valid_config_accepted():
    """合法配置必须能构造"""
    from modules.backtest import PortfolioBacktestEngine, PortfolioConfig

    cfg = PortfolioConfig(initial_capital=100_000.0, max_positions=5)
    engine = PortfolioBacktestEngine(portfolio_config=cfg)
    assert engine.portfolio_config.initial_capital == 100_000.0


def test_portfolio_run_invalid_days_raises():
    from modules.backtest import PortfolioBacktestEngine

    engine = PortfolioBacktestEngine()
    with pytest.raises(ZettarancError) as exc_info:
        engine.run(ts_codes=["600519.SH"], days=0)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG
    assert "days" in exc_info.value.message


def test_portfolio_run_empty_ts_codes_raises():
    from modules.backtest import PortfolioBacktestEngine

    engine = PortfolioBacktestEngine()
    with pytest.raises(ZettarancError) as exc_info:
        engine.run(ts_codes=[], days=30)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG
    assert "ts_codes" in exc_info.value.message


def test_portfolio_run_no_klines_raises():
    from modules.backtest import PortfolioBacktestEngine

    engine = PortfolioBacktestEngine()
    with patch("modules.backtest.portfolio.get_kline_data", return_value=[]):
        with pytest.raises(ZettarancError) as exc_info:
            engine.run(ts_codes=["600519.SH"], days=30)
    assert exc_info.value.code == ErrorCode.BACKTEST_EMPTY_KLINES
    assert "600519.SH" in exc_info.value.message


def test_portfolio_run_with_mocked_klines_returns_result():
    """合法路径：注入 mock klines 验证正常返回"""
    from modules.backtest import PortfolioBacktestEngine, PortfolioBacktestResult

    engine = PortfolioBacktestEngine()
    n = 90
    klines = []
    for i in range(n):
        klines.append(
            type(
                "K",
                (),
                {
                    "trade_date": f"2026{i:04d}",
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

    with patch("modules.backtest.portfolio.get_kline_data", return_value=klines):
        with patch("modules.backtest.portfolio.precompute_market_contexts", return_value={}):
            result = engine.run(ts_codes=["600519.SH"], days=30)
    assert isinstance(result, PortfolioBacktestResult)


def test_backtest_strategy_invalid_days_raises():
    from modules.backtest import backtest_strategy

    with pytest.raises(ZettarancError) as exc_info:
        backtest_strategy("600519.SH", days=0)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG


def test_backtest_strategy_empty_ts_code_raises():
    from modules.backtest import backtest_strategy

    with pytest.raises(ZettarancError) as exc_info:
        backtest_strategy("", days=30)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG
    assert "ts_code" in exc_info.value.message


def test_backtest_strategy_invalid_stop_loss_raises():
    from modules.backtest import backtest_strategy

    with pytest.raises(ZettarancError) as exc_info:
        backtest_strategy("600519.SH", days=30, stop_loss_pct=0.0)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG


def test_backtest_strategy_invalid_take_profit_raises():
    from modules.backtest import backtest_strategy

    with pytest.raises(ZettarancError) as exc_info:
        backtest_strategy("600519.SH", days=30, take_profit_pct=-0.1)
    assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG


def test_backtest_zettaranc_is_value_error_subclass():
    """ZettarancError 仍为 ValueError 子类，老 except ValueError 不受影响"""
    from modules.backtest import backtest_strategy

    with pytest.raises(ValueError):
        backtest_strategy("600519.SH", days=0)

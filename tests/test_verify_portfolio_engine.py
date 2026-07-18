"""组合级回测引擎测试"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.indicators import DailyData
from modules.loop_engine import LoopConfig, LoopTrade
from modules.verify.portfolio_engine import (
    MarketAdaptiveConfig,
    PortfolioBacktestEngine,
    PortfolioConfig,
    PortfolioBacktestResult,
)
from modules.simulator import MarketContext, MarketRegime


def _make_kline(
    ts_code: str = "600519.SH",
    date: str = "20260101",
    close: float = 100.0,
    vol: float = 10000.0,
) -> DailyData:
    """快速构造 DailyData"""
    return DailyData(
        ts_code=ts_code,
        trade_date=date,
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        vol=vol,
        amount=close * vol,
        pct_chg=0.0,
        prev_close=close * 0.99,
    )


def _make_klines(
    ts_code: str,
    dates: list[str],
    closes: list[float],
) -> list[DailyData]:
    """按日期和收盘价序列构造 K 线"""
    return [_make_kline(ts_code, d, c) for d, c in zip(dates, closes)]


class TestPortfolioBacktestEngine:
    """PortfolioBacktestEngine 核心行为测试"""

    def test_empty_universe(self):
        """v3.10.4: 空候选池抛 BACKTEST_INVALID_CONFIG（之前返回空结果）"""
        from modules.core.errors import ErrorCode, ZettarancError

        engine = PortfolioBacktestEngine()
        with pytest.raises(ZettarancError) as exc_info:
            engine.run([], days=30)
        assert exc_info.value.code == ErrorCode.BACKTEST_INVALID_CONFIG

    def test_no_signals_no_trades(self, monkeypatch):
        """没有 B1 信号时只记录净值，不产生交易"""
        engine = PortfolioBacktestEngine()
        # 阻止真实 K 线加载：mock _load_klines
        klines = _make_klines("600519.SH", ["20260101", "20260102", "20260103"], [100.0, 101.0, 102.0])
        monkeypatch.setattr(engine, "_load_klines", lambda *args, **kwargs: {"600519.SH": klines})
        # mock _check_multi_entry 无信号（v3.10.0 多策略接口）
        monkeypatch.setattr(engine, "_check_multi_entry", lambda *args, **kwargs: [])

        result = engine.run(["600519.SH"], days=3)
        assert result.total_trades == 0
        assert len(result.net_values) == 3
        # 无交易，净值恒为初始资金
        assert result.net_values[-1] == pytest.approx(result.net_values[0], rel=1e-6)

    def test_signal_triggers_buy(self, monkeypatch):
        """B1 信号触发买入，持仓后净值包含股票市值"""
        from modules.backtest.portfolio import EntrySignal

        engine = PortfolioBacktestEngine(
            portfolio_config=PortfolioConfig(
                initial_capital=1_000_000.0,
                max_positions=1,
                position_pct=1.0,  # 全仓买入单票
                commission_rate=0.0,
                min_commission=0.0,
                min_signal_days=1,
            ),
            loop_config=LoopConfig(position_pct=1.0),
        )
        klines = _make_klines(
            "600519.SH",
            ["20260101", "20260102", "20260103"],
            [100.0, 101.0, 102.0],
        )
        monkeypatch.setattr(engine, "_load_klines", lambda *args, **kwargs: {"600519.SH": klines})

        # 第二天收盘出现 B1 信号（v3.10.0 多策略接口）
        def mock_check_multi_entry(klines_arg, idx, enabled):
            if idx >= 1 and klines_arg[idx].trade_date == "20260102":
                return [EntrySignal(strategy="B1", confidence=0.9, reason="J=-15", stop_loss_price=97.0)]
            return []

        monkeypatch.setattr(engine, "_check_multi_entry", mock_check_multi_entry)
        # process_day 不触发离场
        monkeypatch.setattr(
            engine.loop_engine,
            "process_day",
            lambda *args, **kwargs: (kwargs.get("current_trade"), None),
        )

        result = engine.run(["600519.SH"], days=3)
        assert result.total_trades == 0  # 未平仓
        # 净值应上涨：第二天买入，第三天收盘价 102
        assert result.net_values[1] == pytest.approx(1_000_000.0, rel=1e-6)
        # 第三天净值 ≈ 现金剩余 + 持仓市值（全仓买入 101 元股票，涨到 102）
        assert result.net_values[2] > 1_000_000.0

    def test_max_positions_respected(self, monkeypatch):
        """最多同时持仓 max_positions 只"""
        from modules.backtest.portfolio import EntrySignal

        engine = PortfolioBacktestEngine(
            portfolio_config=PortfolioConfig(
                initial_capital=1_000_000.0,
                max_positions=2,
                position_pct=0.5,
                commission_rate=0.0,
                min_signal_days=1,
            ),
            loop_config=LoopConfig(position_pct=1.0),
        )
        codes = ["600519.SH", "600000.SH", "000001.SZ", "000002.SZ"]
        klines_map = {}
        for code in codes:
            klines_map[code] = _make_klines(
                code,
                ["20260101", "20260102", "20260103"],
                [100.0, 101.0, 102.0],
            )
        monkeypatch.setattr(engine, "_load_klines", lambda *args, **kwargs: klines_map)

        # 所有股票第二天都有 B1 信号（v3.10.0 多策略接口）
        monkeypatch.setattr(
            engine,
            "_check_multi_entry",
            lambda klines_arg, idx, enabled: [
                EntrySignal(strategy="B1", confidence=0.8, reason="B1", stop_loss_price=97.0)
            ],
        )
        monkeypatch.setattr(
            engine.loop_engine,
            "process_day",
            lambda *args, **kwargs: (kwargs.get("current_trade"), None),
        )

        result = engine.run(codes, days=3)
        # 第二天最多买入 2 只，第三天不再买入（因为已满仓）
        # 由于 process_day 不返回 completed，总交易数为 0
        assert result.total_trades == 0
        # 第三天净值不应超过初始资金太多，因为只买了 2 只
        # 主要验证没崩溃
        assert len(result.net_values) == 3

    def test_sell_updates_cash(self, monkeypatch):
        """平仓后现金增加并记录交易"""
        from modules.backtest.portfolio import EntrySignal

        engine = PortfolioBacktestEngine(
            portfolio_config=PortfolioConfig(
                initial_capital=1_000_000.0,
                max_positions=1,
                position_pct=1.0,
                commission_rate=0.0,
                stamp_duty_rate=0.0,
                min_signal_days=1,
            ),
            loop_config=LoopConfig(position_pct=1.0),
        )
        klines = _make_klines(
            "600519.SH",
            ["20260101", "20260102", "20260103"],
            [100.0, 101.0, 102.0],
        )
        monkeypatch.setattr(engine, "_load_klines", lambda *args, **kwargs: {"600519.SH": klines})

        # 第二天买入（v3.10.0 多策略接口：只在 20260102 返回信号）
        def mock_check_multi_entry(klines_arg, idx, enabled):
            if idx >= 1 and klines_arg[idx].trade_date == "20260102":
                return [EntrySignal(strategy="B1", confidence=0.9, reason="J=-15", stop_loss_price=97.0)]
            return []

        monkeypatch.setattr(engine, "_check_multi_entry", mock_check_multi_entry)

        # 第三天平仓，盈利 10%
        def mock_process_day(ts_code, klines, day_idx, current_trade):
            if klines[day_idx].trade_date == "20260103" and current_trade is not None:
                completed = LoopTrade(
                    ts_code=ts_code,
                    entry_date=current_trade.entry_date,
                    entry_price=current_trade.entry_price,
                    entry_reason=current_trade.entry_reason,
                    stop_loss_price=current_trade.stop_loss_price,
                    exit_date=klines[day_idx].trade_date,
                    exit_price=klines[day_idx].close,
                    exit_reason="白线跌破",
                    pnl_pct=10.0,
                    holding_days=1,
                    position_pct=1.0,
                )
                return None, completed
            return current_trade, None

        monkeypatch.setattr(engine.loop_engine, "process_day", mock_process_day)

        result = engine.run(["600519.SH"], days=3)
        assert result.total_trades == 1
        assert result.win_count == 1
        assert result.net_values[-1] > 1_000_000.0

    def test_metrics_calculation(self):
        """_build_result 正确计算收益、回撤、Sharpe、Calmar"""
        engine = PortfolioBacktestEngine()
        dates = ["20260101", "20260102", "20260103", "20260104"]
        net_values = [100.0, 110.0, 105.0, 120.0]
        cash_history = [100.0, 0.0, 0.0, 120.0]
        result = engine._build_result(
            dates=dates,
            net_values=net_values,
            cash_history=cash_history,
            completed_trades=[],
            days=4,
        )
        assert result.total_return == pytest.approx(0.20, rel=1e-6)
        # 回撤：peak=110, trough=105, dd=5/110
        assert result.max_drawdown == pytest.approx(5 / 110, rel=1e-6)
        assert result.calmar == pytest.approx(result.annualized_return / result.max_drawdown, rel=1e-6)


class TestPortfolioEngineMarketAdaptive:
    """市场环境自适应仓位控制测试（v3.8.0）"""

    def test_adaptive_weak_no_new_entries(self):
        """WEAK 环境下禁止新开仓且仓位参数收缩"""
        config = PortfolioConfig(
            max_positions=5,
            position_pct=0.2,
            max_entries_per_day=2,
            adaptive=MarketAdaptiveConfig(
                enabled=True,
                weak_no_new_entries=True,
                weak_max_positions_factor=0.0,
                weak_position_pct_factor=0.5,
                weak_max_entries_factor=0.0,
            ),
        )
        engine = PortfolioBacktestEngine(portfolio_config=config)
        ctx = MarketContext(
            date="20260102",
            regime=MarketRegime.WEAK,
            index_trend=30.0,
            breadth=-0.3,
            moneyflow_score=35.0,
        )
        mp, pp, me, allow_new = engine._resolve_adaptive(config, ctx)
        assert not allow_new
        assert me == 0
        assert mp == 0
        assert pp == pytest.approx(0.1, rel=1e-6)

    def test_adaptive_disabled_unchanged(self):
        """adaptive.enabled=False 时保持原配置"""
        config = PortfolioConfig(
            max_positions=5,
            position_pct=0.2,
            max_entries_per_day=2,
        )
        engine = PortfolioBacktestEngine(portfolio_config=config)
        mp, pp, me, allow_new = engine._resolve_adaptive(config, None)
        assert allow_new
        assert mp == 5
        assert pp == pytest.approx(0.2, rel=1e-6)
        assert me == 2

    def test_adaptive_lag_uses_previous_day_context(self, monkeypatch):
        """买入决策使用上一交易日市场环境，避免偷看当天"""
        config = PortfolioConfig(
            max_positions=1,
            position_pct=1.0,
            commission_rate=0.0,
            min_commission=0.0,
            min_signal_days=1,
            adaptive=MarketAdaptiveConfig(enabled=True),
        )
        engine = PortfolioBacktestEngine(
            portfolio_config=config,
            loop_config=LoopConfig(position_pct=1.0),
        )
        klines = _make_klines(
            "600519.SH",
            ["20260101", "20260102", "20260103"],
            [100.0, 101.0, 102.0],
        )
        monkeypatch.setattr(engine, "_load_klines", lambda *args, **kwargs: {"600519.SH": klines})
        monkeypatch.setattr(engine.loop_engine, "check_entry", lambda *args, **kwargs: None)

        # 01 强势 → 02 震荡 → 03 弱势；决策应滞后一天
        contexts = {
            "20260101": MarketContext(
                date="20260101",
                regime=MarketRegime.STRONG,
                index_trend=70.0,
                breadth=0.2,
                moneyflow_score=60.0,
            ),
            "20260102": MarketContext(
                date="20260102",
                regime=MarketRegime.NEUTRAL,
                index_trend=50.0,
                breadth=0.0,
                moneyflow_score=50.0,
            ),
            "20260103": MarketContext(
                date="20260103",
                regime=MarketRegime.WEAK,
                index_trend=30.0,
                breadth=-0.2,
                moneyflow_score=35.0,
            ),
        }
        monkeypatch.setattr(
            "modules.backtest.portfolio.precompute_market_contexts",
            lambda *args, **kwargs: contexts,
        )

        captured: list[MarketRegime] = []
        original_scan = engine._scan_and_buy

        def scanning_scan(*args, **kwargs):
            captured.append(kwargs.get("prev_context").regime)
            return original_scan(*args, **kwargs)

        monkeypatch.setattr(engine, "_scan_and_buy", scanning_scan)

        engine.run(["600519.SH"], days=3)
        # 20260101 无上一日 → NEUTRAL；20260102 用 20260101 STRONG；20260103 用 20260102 NEUTRAL
        assert captured == [MarketRegime.NEUTRAL, MarketRegime.STRONG, MarketRegime.NEUTRAL]


class TestPortfolioEngineDateWindow:
    """PortfolioBacktestEngine 日期窗口切片测试（v3.7.7）"""

    def test_run_with_date_range(self, monkeypatch):
        """run(start_date, end_date) 只在窗口内迭代"""
        engine = PortfolioBacktestEngine()
        klines = _make_klines(
            "600519.SH",
            ["20260101", "20260102", "20260103", "20260104", "20260105"],
            [100.0, 101.0, 102.0, 103.0, 104.0],
        )
        monkeypatch.setattr(engine, "_load_klines", lambda *args, **kwargs: {"600519.SH": klines})
        monkeypatch.setattr(engine.loop_engine, "check_entry", lambda *args, **kwargs: None)

        result = engine.run(
            ["600519.SH"],
            days=5,
            start_date="20260102",
            end_date="20260104",
        )
        assert result.dates == ["20260102", "20260103", "20260104"]
        assert len(result.net_values) == 3
        assert result.net_values[0] == pytest.approx(1_000_000.0, rel=1e-6)

    def test_run_with_open_end_date(self, monkeypatch):
        """end_date=None 时从 start_date 跑到最后"""
        engine = PortfolioBacktestEngine()
        klines = _make_klines(
            "600519.SH",
            ["20260101", "20260102", "20260103"],
            [100.0, 101.0, 102.0],
        )
        monkeypatch.setattr(engine, "_load_klines", lambda *args, **kwargs: {"600519.SH": klines})
        monkeypatch.setattr(engine.loop_engine, "check_entry", lambda *args, **kwargs: None)

        result = engine.run(["600519.SH"], days=3, start_date="20260102")
        assert result.dates == ["20260102", "20260103"]

    def test_build_result_uses_actual_trading_days(self):
        """_build_result 用 len(net_values) 年化，而不是传入的 days"""
        engine = PortfolioBacktestEngine()
        dates = ["d1", "d2", "d3"]
        net_values = [100.0, 110.0, 121.0]
        result = engine._build_result(
            dates=dates,
            net_values=net_values,
            cash_history=[100.0, 0.0, 121.0],
            completed_trades=[],
            days=999,  # 故意传入很大值，应被忽略
        )
        # 3 天总收益 21%，年化 = 1.21^(250/3) - 1
        expected_annual = (1.0 + 0.21) ** (252.0 / 3.0) - 1.0
        assert result.annualized_return == pytest.approx(expected_annual, rel=1e-6)

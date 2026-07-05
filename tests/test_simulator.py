"""
少女/少妇模拟器单元测试
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from dataclasses import asdict

import pytest

from modules.indicators import DailyData
from modules.simulator import (
    CostModel,
    MarketRegime,
    Position,
    SimulationConfig,
    SimulationResult,
    SlippageModel,
    TradeRecord,
)
from modules.simulator.execution_constraints import next_trading_date
from modules.simulator.execution_engine import execute_buy, execute_sell
from modules.simulator.exit_manager import check_exit
from modules.simulator.market_context import MarketContext, get_market_context, max_positions_allowed
from modules.simulator.position_sizer import build_position, calculate_position_size
from modules.simulator.signal_filter import SignalScore, SignalVerdict, filter_signals
from modules.simulator.simulator import _build_result, _portfolio_value, _run_single_day


def _make_klines(n=60, ts_code="600519.SH", start_price=100.0, trend=0.01):
    """生成测试 K 线（DailyData 对象）"""
    klines = []
    dt = datetime(2026, 1, 1)
    price = start_price
    for i in range(n):
        date_str = dt.strftime("%Y%m%d")
        prev = price
        price *= 1 + trend
        klines.append(
            DailyData(
                ts_code=ts_code,
                trade_date=date_str,
                open=prev,
                high=price * 1.02,
                low=prev * 0.98,
                close=price,
                vol=10000 + i * 100,
                amount=price * (10000 + i * 100),
                pct_chg=trend * 100,
                prev_close=prev,
            )
        )
        dt += timedelta(days=1)
    return klines


def _make_mock_breadth_conn(limit_up=50, limit_down=3, turnover_up=True):
    """构造模拟的 SQLite 连接，用于市场环境测试。"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # 构造 40 个交易日成交额：递增表示趋势向上，递减表示趋势向下
    base_date = datetime(2024, 1, 1)
    turnover_rows = []
    for i in range(40):
        date_str = (base_date + timedelta(days=i)).strftime("%Y%m%d")
        factor = 1 + i * 0.01 if turnover_up else 1 - i * 0.01
        turnover_rows.append({"trade_date": date_str, "total_amount": 1e10 * factor})

    def fake_execute(sql, params):
        if "pct_chg" in sql:
            mock_cursor.fetchone.return_value = {"limit_up": limit_up, "limit_down": limit_down}
        elif "SUM(amount)" in sql:
            # 查询结果按 trade_date DESC 返回
            mock_cursor.fetchall.return_value = list(reversed(turnover_rows))
        return mock_cursor

    mock_cursor.execute.side_effect = fake_execute
    return mock_conn


def test_simulation_config_default_fields():
    from modules.simulator import SimulationConfig, CostModel, SlippageModel

    cfg = SimulationConfig()
    assert cfg.t1_lock is True
    assert cfg.apply_price_limit is True
    assert cfg.benchmark_code == "000300.SH"
    assert cfg.max_position_pct == 0.20
    assert cfg.cost_model.min_commission == 5.0
    assert cfg.slippage_model.base_slippage == 0.001


def test_raw_strategy_signal_dataclass():
    from modules.simulator import RawStrategySignal

    s = RawStrategySignal(strategy="B1", category="rebound", action="BUY", confidence=0.8, trade_date="20240101")
    assert s.strategy == "B1"
    assert s.confidence == 0.8


def test_simulation_config_strategy_mode_defaults():
    from modules.simulator import SimulationConfig

    cfg = SimulationConfig()
    assert cfg.strategy_mode == "simple"
    assert cfg.strategy_lookback_days == 5
    assert cfg.min_resonance_score == 0.35
    assert cfg.strategy_category_weights == {}


class TestPositionSizer:
    def test_basic_size(self):
        shares, risk = calculate_position_size(
            equity=1000000,
            entry_price=100,
            stop_loss=95,
            cash=1000000,
            config=SimulationConfig(risk_per_trade=0.02),
        )
        assert shares >= 100
        assert shares % 100 == 0
        assert risk > 0

    def test_cash_limit(self):
        shares, _ = calculate_position_size(
            equity=1000000,
            entry_price=10000,
            stop_loss=9500,
            cash=100000,
            config=SimulationConfig(risk_per_trade=0.02),
        )
        # 现金只够买 10 股，但 A 股最小 100 股
        assert shares == 0

    def test_invalid_stop_loss(self):
        shares, risk = calculate_position_size(
            equity=1000000,
            entry_price=100,
            stop_loss=100,
            cash=1000000,
            config=SimulationConfig(),
        )
        assert shares == 0
        assert risk == 0

    def test_build_position(self):
        pos = build_position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            stop_loss=95,
            take_profit=110,
            cash=1000000,
            equity=1000000,
            config=SimulationConfig(),
        )
        assert pos is not None
        assert pos.shares >= 100
        assert pos.shares % 100 == 0
        assert pos.stop_loss == 95


class TestExecutionEngine:
    def test_buy_slippage_and_fee(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        kline = DailyData(
            ts_code="600519.SH",
            trade_date="20260101",
            open=100,
            high=102,
            low=99,
            close=101,
            vol=10000,
            amount=1010000,
            pct_chg=1.0,
            prev_close=100,
        )
        trade = execute_buy(pos, kline, SimulationConfig(slippage=0.001, commission_rate=0.0003))
        assert trade.action == "BUY"
        assert trade.price > 100  # 滑点加价
        assert trade.fee > 0

    def test_sell_pnl(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        kline = DailyData(
            ts_code="600519.SH",
            trade_date="20260105",
            open=110,
            high=112,
            low=109,
            close=110,
            vol=10000,
            amount=1100000,
            pct_chg=10.0,
            prev_close=100,
        )
        trade = execute_sell(pos, kline, SimulationConfig(), "止盈")
        assert trade.action == "SELL"
        assert trade.pnl > 0
        assert trade.pnl_pct > 0


class TestExitManager:
    def test_stop_loss(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        klines = _make_klines(n=10, start_price=100, trend=-0.02)
        action, shares = check_exit(pos, klines, SimulationConfig())
        assert action == "STOP_LOSS"
        assert shares == 1000

    def test_hold_when_above_stop(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=90,
            take_profit=120,
            risk_amount=5000,
        )
        klines = _make_klines(n=25, start_price=100, trend=0.005)
        action, shares = check_exit(pos, klines, SimulationConfig(partial_take_profit_rr=10))
        assert action == "HOLD"
        assert shares == 0


class TestMarketContext:
    def test_max_positions_strong(self):
        ctx = MarketContext(
            date="20260101", regime=MarketRegime.STRONG, index_trend=80, breadth=0.3, moneyflow_score=70
        )
        assert max_positions_allowed(ctx, config_max=5, weak_max=1) == 5

    def test_max_positions_weak(self):
        ctx = MarketContext(date="20260101", regime=MarketRegime.WEAK, index_trend=30, breadth=-0.3, moneyflow_score=30)
        assert max_positions_allowed(ctx, config_max=5, weak_max=1) == 1

    def test_max_positions_neutral(self):
        ctx = MarketContext(date="20260101", regime=MarketRegime.NEUTRAL, index_trend=50, breadth=0, moneyflow_score=50)
        assert max_positions_allowed(ctx, config_max=5, weak_max=1) == 4

    @patch("modules.simulator.market_context.get_datasource")
    @patch("modules.simulator.market_context.get_connection")
    def test_market_context_includes_breadth_notes(self, mock_get_conn, mock_get_ds):
        raw_klines = [asdict(k) for k in _make_klines(n=70, ts_code="000001.SH", trend=0.01)]
        mock_ds = MagicMock()
        mock_ds.get_kline_dicts.return_value = raw_klines
        mock_get_ds.return_value = mock_ds

        mock_conn = _make_mock_breadth_conn(limit_up=50, limit_down=3, turnover_up=True)
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_conn)
        cm.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = cm

        ctx = get_market_context("20240115")
        assert any("涨停" in n or "跌停" in n for n in ctx.notes)
        assert any("情绪贪婪" in n for n in ctx.notes)

    @patch("modules.simulator.market_context.get_datasource")
    @patch("modules.simulator.market_context.get_connection")
    def test_market_context_panic_downgrades_strong(self, mock_get_conn, mock_get_ds):
        raw_klines = [asdict(k) for k in _make_klines(n=70, ts_code="000001.SH", trend=0.01)]
        mock_ds = MagicMock()
        mock_ds.get_kline_dicts.return_value = raw_klines
        mock_get_ds.return_value = mock_ds

        mock_conn = _make_mock_breadth_conn(limit_up=10, limit_down=50, turnover_up=False)
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_conn)
        cm.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value = cm

        ctx = get_market_context("20240115")
        assert any("情绪恐慌" in n for n in ctx.notes)
        assert ctx.regime in (MarketRegime.NEUTRAL, MarketRegime.WEAK)


class TestSignalFilter:
    def test_filter_requires_pass_verdict(self):
        good = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date="20260101",
            score=80,
            b1_score=70,
            trend_score=70,
            volume_score=70,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1信号"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )
        bad = SignalScore(
            ts_code="000001.SZ",
            name="平安",
            date="20260101",
            score=80,
            b1_score=70,
            trend_score=70,
            volume_score=70,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1信号"],
            warnings=[],
            verdict=SignalVerdict.HIGH_RISK,
        )
        result = filter_signals([good, bad], score_threshold=70, min_signal_count=2)
        assert len(result) == 1
        assert result[0].ts_code == "600519.SH"

    def test_filter_requires_min_signals(self):
        s = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date="20260101",
            score=80,
            b1_score=70,
            trend_score=70,
            volume_score=70,
            risk_score=80,
            signals=["B1"],
            reasons=["B1信号"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )
        result = filter_signals([s], score_threshold=70, min_signal_count=2)
        assert len(result) == 0


class TestSimulatorCore:
    def test_portfolio_value(self):
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=90,
            take_profit=120,
            risk_amount=5000,
        )
        klines = _make_klines(n=10, start_price=100, trend=0.01)
        state = MagicMock()
        state.cash = 500000
        state.positions = [pos]
        value = _portfolio_value(state, klines[-1].trade_date, {"600519.SH": klines})
        assert value > state.cash

    def test_build_result_empty(self):
        config = SimulationConfig()
        state = MagicMock()
        state.equity = config.initial_capital
        state.trades = []
        state.equity_curve = [{"date": "20260101", "equity": config.initial_capital}]
        state.positions = []
        result = _build_result(state, config)
        assert result.total_return == 0
        assert result.max_drawdown == 0

    def test_build_result_with_trades(self):
        config = SimulationConfig()
        state = MagicMock()
        state.equity = config.initial_capital * 1.1
        state.trades = [
            TradeRecord(ts_code="600519.SH", name="茅台", action="BUY", date="20260101", price=100, shares=100),
            TradeRecord(
                ts_code="600519.SH",
                name="茅台",
                action="SELL",
                date="20260105",
                price=110,
                shares=100,
                pnl=1000,
                pnl_pct=0.1,
            ),
        ]
        state.equity_curve = [
            {"date": "20260101", "equity": config.initial_capital},
            {"date": "20260105", "equity": config.initial_capital * 1.1},
        ]
        state.positions = []
        result = _build_result(state, config)
        assert result.total_return > 0
        assert result.total_trades == 1
        assert result.win_rate == 1.0


class TestRunSingleDay:
    @patch("modules.simulator.simulator.execute_buy")
    @patch("modules.simulator.simulator.execute_sell")
    @patch("modules.simulator.simulator.get_market_context")
    @patch("modules.simulator.simulator.build_position")
    def test_opens_position_when_signal_pass(self, mock_build, mock_ctx, mock_sell, mock_buy):
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig(max_positions=1)
        state = _SimulatorState(cash=1000000, equity=1000000)

        ctx = MarketContext(
            date="20260110", regime=MarketRegime.STRONG, index_trend=70, breadth=0.1, moneyflow_score=60
        )
        mock_ctx.return_value = ctx

        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260110",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        mock_build.return_value = pos
        mock_buy.return_value = TradeRecord(
            ts_code="600519.SH", name="茅台", action="BUY", date="20260110", price=100, shares=1000
        )

        klines = _make_klines(n=70, start_price=100, trend=0.005)
        klines_map = {"600519.SH": klines}

        sig = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date="20260110",
            score=85,
            b1_score=80,
            trend_score=80,
            volume_score=75,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )

        dates = ["20260109", "20260110", "20260111"]
        _run_single_day("20260110", dates, state, [sig], klines_map, ctx, config)
        assert len(state.positions) == 1
        assert state.cash < 1000000
        mock_buy.assert_called_once()

    @patch("modules.simulator.simulator.execute_sell")
    @patch("modules.simulator.simulator.check_exit")
    @patch("modules.simulator.simulator.get_market_context")
    def test_exits_position_on_stop_loss(self, mock_ctx, mock_exit, mock_sell):
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig()
        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date="20260101",
            entry_price=100,
            shares=1000,
            stop_loss=95,
            take_profit=110,
            risk_amount=5000,
        )
        state = _SimulatorState(cash=0, equity=100000, positions=[pos])

        ctx = MarketContext(
            date="20260105", regime=MarketRegime.STRONG, index_trend=70, breadth=0.1, moneyflow_score=60
        )
        mock_ctx.return_value = ctx
        mock_exit.return_value = ("STOP_LOSS", 1000)
        mock_sell.return_value = TradeRecord(
            ts_code="600519.SH", name="茅台", action="SELL", date="20260105", price=94, shares=1000, pnl=-6000
        )

        dates = ["20260104", "20260105", "20260106"]
        klines = _make_klines(n=10, start_price=100, trend=-0.02)
        _run_single_day("20260105", dates, state, [], {"600519.SH": klines}, ctx, config)
        assert len(state.positions) == 0
        mock_sell.assert_called_once()


class TestIntegration:
    @patch("modules.simulator.simulator.get_datasource")
    @patch("modules.simulator.simulator.get_all_stocks")
    @patch("modules.simulator.simulator.get_recent_klines")
    @patch("modules.simulator.simulator.get_market_context")
    def test_run_simulation_empty_pool(self, mock_ctx, mock_klines, mock_stocks, mock_ds):
        from modules.simulator.simulator import run_simulation

        mock_ds.return_value = MagicMock()
        mock_stocks.return_value = []
        mock_ctx.return_value = MarketContext(
            date="20260101", regime=MarketRegime.NEUTRAL, index_trend=50, breadth=0, moneyflow_score=50
        )

        result = run_simulation(ts_codes=[], days=30)
        assert isinstance(result, SimulationResult)
        assert result.total_trades == 0
        assert result.initial_capital == SimulationConfig().initial_capital


def test_run_simulation_returns_metrics():
    """端到端回归：run_simulation 必须返回非空 metrics 对象。"""
    from modules.simulator.simulator import run_simulation
    from modules.simulator import SimulationConfig

    klines = _make_klines(n=90, start_price=100, trend=0.005)
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

    with (
        patch("modules.simulator.simulator.get_datasource", return_value=mock_ds),
        patch("modules.simulator.simulator.get_recent_klines", return_value=klines),
        patch("modules.simulator.simulator.get_market_context") as mock_ctx,
        patch("modules.simulator.simulator.evaluate_stock") as mock_eval,
    ):
        mock_ctx.return_value = MarketContext(
            date=sim_dates[0],
            regime=MarketRegime.NEUTRAL,
            index_trend=50,
            breadth=0.0,
            moneyflow_score=50,
        )
        mock_eval.return_value = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date=sim_dates[0],
            score=85,
            b1_score=80,
            trend_score=80,
            volume_score=75,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )

        result = run_simulation(ts_codes=["600519.SH"], days=30, config=SimulationConfig(), datasource=mock_ds)

    assert result.metrics is not None
    assert len(result.equity_curve) == 30


class TestConstraintsIntegration:
    def test_rejected_entry_on_limit_up(self):
        """涨停开盘的候选股应被记录到 rejected_entries，且不会开仓。"""
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig(max_positions=1)
        klines = _make_klines(n=10, start_price=100, trend=0.01)
        dates = [k.trade_date for k in klines]

        # 将当日开盘价打到涨停价以上，触发买入约束
        prev_close = klines[-2].close
        klines[-1].open = round(prev_close * 1.11, 2)

        state = _SimulatorState(cash=1_000_000, equity=1_000_000)
        ctx = MarketContext(
            date=klines[-1].trade_date,
            regime=MarketRegime.STRONG,
            index_trend=70,
            breadth=0.1,
            moneyflow_score=60,
        )
        sig = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date=klines[-1].trade_date,
            score=85,
            b1_score=80,
            trend_score=80,
            volume_score=75,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )

        _run_single_day(klines[-1].trade_date, dates, state, [sig], {"600519.SH": klines}, ctx, config)
        assert len(state.positions) == 0
        assert len(state.rejected_entries) == 1
        assert "涨停" in state.rejected_entries[0]["reason"]

    def test_t1_lock_prevents_same_day_sell(self):
        """T+1 制度下，买入当日即使触发止损也不应卖出。"""
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig(t1_lock=True)
        klines = _make_klines(n=10, start_price=100, trend=-0.05)
        dates = [k.trade_date for k in klines]
        entry_date = dates[1]
        can_sell = next_trading_date(dates, entry_date)

        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date=entry_date,
            entry_price=100,
            shares=1000,
            stop_loss=99,
            take_profit=110,
            risk_amount=5000,
            can_sell_date=can_sell,
        )
        state = _SimulatorState(cash=0, equity=100_000, positions=[pos])
        ctx = MarketContext(
            date=entry_date,
            regime=MarketRegime.STRONG,
            index_trend=70,
            breadth=0.1,
            moneyflow_score=60,
        )

        _run_single_day(entry_date, dates, state, [], {"600519.SH": klines}, ctx, config)
        assert len(state.positions) == 1
        assert any("T+1" in note for note in pos.notes)

    def test_build_result_populates_v02_fields(self):
        """_build_result 必须填充 metrics、benchmark_curve、rejected_entries，同时保留 v0.1 字段。"""
        config = SimulationConfig()
        state = MagicMock()
        state.equity = config.initial_capital
        state.trades = []
        state.equity_curve = [{"date": "20260101", "equity": config.initial_capital}]
        state.positions = []
        state.benchmark_curve = [{"date": "20260101", "close": 100}]
        state.rejected_entries = [{"date": "20260101", "ts_code": "600519.SH", "reason": "涨停"}]

        result = _build_result(state, config)
        assert result.metrics is not None
        assert result.benchmark_curve == state.benchmark_curve
        assert result.rejected_entries == state.rejected_entries
        # v0.1 字段保持兼容
        assert result.total_return == 0
        assert result.max_drawdown == 0

    def test_summary_text_includes_new_metrics(self):
        """summary_text 应包含年化、Calmar、Sortino、基准收益、胜率、gain/loss 比。"""
        from modules.simulator.simulator import summary_text
        from modules.simulator.metrics import PerformanceMetrics

        result = SimulationResult(config=SimulationConfig())
        result.metrics = PerformanceMetrics(
            annualized_return=0.12,
            calmar_ratio=1.5,
            sortino_ratio=2.0,
            benchmark_return=0.08,
            win_rate=0.55,
            gain_loss_ratio=1.8,
        )
        text = summary_text(result)
        assert "年化收益" in text
        assert "Calmar" in text
        assert "索提诺" in text
        assert "基准收益" in text
        assert "gain/loss" in text
        assert "12.00%" in text

    def test_limit_down_prevents_sell(self):
        """跌停日卖出约束应阻止 check_exit 触发卖出。"""
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig(t1_lock=False)
        klines = _make_klines(n=10, start_price=100, trend=-0.01)
        dates = [k.trade_date for k in klines]
        entry_date = dates[1]
        can_sell = dates[1]  # 已过 T+1

        # 让当日收盘跌停，触发卖出约束
        prev_close = klines[-2].close
        klines[-1].close = round(prev_close * 0.90, 2)

        pos = Position(
            ts_code="600519.SH",
            name="茅台",
            entry_date=entry_date,
            entry_price=100,
            shares=1000,
            stop_loss=1,  # 极低止损，确保会被触发
            take_profit=110,
            risk_amount=5000,
            can_sell_date=can_sell,
        )
        state = _SimulatorState(cash=0, equity=100_000, positions=[pos])
        ctx = MarketContext(
            date=klines[-1].trade_date,
            regime=MarketRegime.STRONG,
            index_trend=70,
            breadth=0.1,
            moneyflow_score=60,
        )

        _run_single_day(klines[-1].trade_date, dates, state, [], {"600519.SH": klines}, ctx, config)
        assert len(state.positions) == 1
        assert any("跌停" in note for note in pos.notes)


class TestAtrSizingIntegration:
    def test_build_position_receives_klines_and_can_sell_date(self):
        """build_position 必须接收到 klines、can_sell_date、is_st 参数。"""
        from modules.simulator.simulator import _SimulatorState

        config = SimulationConfig(use_atr_sizing=True, max_positions=1)
        klines = _make_klines(n=70, start_price=100, trend=0.005)
        dates = [k.trade_date for k in klines]

        state = _SimulatorState(cash=1_000_000, equity=1_000_000)
        ctx = MarketContext(
            date=klines[-1].trade_date,
            regime=MarketRegime.STRONG,
            index_trend=70,
            breadth=0.1,
            moneyflow_score=60,
        )
        sig = SignalScore(
            ts_code="600519.SH",
            name="茅台",
            date=klines[-1].trade_date,
            score=85,
            b1_score=80,
            trend_score=80,
            volume_score=75,
            risk_score=80,
            signals=["B1", "沙漏完美"],
            reasons=["B1"],
            warnings=[],
            verdict=SignalVerdict.PASS,
        )

        with patch("modules.simulator.simulator.build_position") as mock_build:
            mock_pos = Position(
                ts_code="600519.SH",
                name="茅台",
                entry_date=sig.date,
                entry_price=klines[-1].open,
                shares=1000,
                stop_loss=95,
                take_profit=110,
                risk_amount=5000,
            )
            mock_build.return_value = mock_pos
            with patch("modules.simulator.simulator.execute_buy") as mock_buy:
                mock_buy.return_value = TradeRecord(
                    ts_code="600519.SH",
                    name="茅台",
                    action="BUY",
                    date=sig.date,
                    price=klines[-1].open,
                    shares=1000,
                )
                _run_single_day(sig.date, dates, state, [sig], {"600519.SH": klines}, ctx, config)

        assert mock_build.called
        _, kwargs = mock_build.call_args
        assert kwargs.get("klines") is not None
        assert len(kwargs.get("klines")) == len(klines)
        assert kwargs.get("can_sell_date") == next_trading_date(dates, sig.date)
        assert kwargs.get("is_st") is False


def test_evaluate_stock_resonance_mode_uses_strategies():
    """resonance 模式下 evaluate_stock 应使用 modules.strategies 信号并返回共振分。"""
    from modules.simulator.signal_filter import evaluate_stock
    from modules.simulator import SimulationConfig, SignalVerdict, MarketContext, MarketRegime
    from modules.strategies import StrategySignal, StrategyType, Action

    klines = _make_klines(n=70, ts_code="000001.SZ", start_price=10.0, trend=0.01)
    mock_signal = StrategySignal(
        ts_code="000001.SZ",
        trade_date="20240101",
        strategy=StrategyType.B1,
        action=Action.BUY.value,
        confidence=0.9,
        description="B1买点",
        reason="B1买点",
    )

    cfg = SimulationConfig(strategy_mode="resonance")
    ctx = MarketContext(
        date="20240101",
        regime=MarketRegime.STRONG,
        index_trend=70,
        breadth=0.1,
        moneyflow_score=60,
    )

    with patch("modules.simulator.signal_filter.detect_all_strategies", return_value=[mock_signal]) as mock_detect:
        score = evaluate_stock("000001.SZ", "20240101", klines=klines, datasource=MagicMock(), config=cfg, context=ctx)

    mock_detect.assert_called_once_with("000001.SZ", days=120)
    assert score.resonance is not None
    assert score.verdict == SignalVerdict.PASS
    assert score.score > 0
    assert "B1" in score.signals
    assert any("共振分" in r for r in score.reasons)


def test_evaluate_stock_simple_mode_unchanged():
    """simple 模式下 evaluate_stock 保持 v0.2 行为，resonance 字段为 None。"""
    from modules.simulator.signal_filter import evaluate_stock
    from modules.simulator import SimulationConfig, SignalVerdict
    from modules.screener import StockScore

    klines = _make_klines(n=70, ts_code="600519.SH", start_price=100.0, trend=0.01)
    cfg = SimulationConfig(strategy_mode="simple")

    mock_score = StockScore(
        ts_code="600519.SH",
        name="茅台",
        score=75,
        b1_score=70,
        trend_score=70,
        volume_score=70,
        risk_score=80,
        reasons=["B1信号"],
        warnings=[],
    )

    with patch("modules.simulator.signal_filter.analyze_stock", return_value=mock_score):
        score = evaluate_stock("600519.SH", "20260101", klines=klines, datasource=MagicMock(), config=cfg)

    assert score.resonance is None
    assert score.verdict == SignalVerdict.PASS
    assert score.score == 75
    assert "B1" in score.signals

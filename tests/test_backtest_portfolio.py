"""组合回测引擎数据结构与纯逻辑单元测试

覆盖 PortfolioBacktestResult、PortfolioConfig、MarketAdaptiveConfig 数据类，
以及 PortfolioBacktestEngine 的纯逻辑方法（_resolve_adaptive、_build_result、_recent_return）。
v3.10.0 新增：_resolve_strategy_weights、_compute_strategy_stats、StrategyStats。
"""

import math

import pytest

from modules.backtest.portfolio import (
    MarketAdaptiveConfig,
    PortfolioBacktestEngine,
    PortfolioBacktestResult,
    PortfolioConfig,
    StrategyStats,
)
from modules.loop_engine import LoopTrade
from modules.simulator import MarketContext, MarketRegime


# ---------------------------------------------------------------------------
# MarketAdaptiveConfig
# ---------------------------------------------------------------------------


class TestMarketAdaptiveConfig:
    def test_defaults(self):
        cfg = MarketAdaptiveConfig()
        assert cfg.enabled is False
        assert cfg.weak_no_new_entries is True
        assert cfg.strong_max_positions_factor == 1.0
        assert cfg.neutral_max_positions_factor == 1.0
        assert cfg.weak_max_positions_factor == 0.0
        assert cfg.strong_position_pct_factor == 1.0
        assert cfg.neutral_position_pct_factor == 1.0
        assert cfg.weak_position_pct_factor == 0.5
        assert cfg.strong_max_entries_factor == 1.0
        assert cfg.neutral_max_entries_factor == 1.0
        assert cfg.weak_max_entries_factor == 0.0

    def test_custom_values(self):
        cfg = MarketAdaptiveConfig(
            enabled=True,
            weak_no_new_entries=False,
            strong_max_positions_factor=1.5,
            weak_max_positions_factor=0.3,
        )
        assert cfg.enabled is True
        assert cfg.weak_no_new_entries is False
        assert cfg.strong_max_positions_factor == 1.5
        assert cfg.weak_max_positions_factor == 0.3
        # 未指定的字段仍为默认值
        assert cfg.neutral_max_positions_factor == 1.0


# ---------------------------------------------------------------------------
# PortfolioConfig
# ---------------------------------------------------------------------------


class TestPortfolioConfig:
    def test_defaults(self):
        cfg = PortfolioConfig()
        assert cfg.initial_capital == 1_000_000.0
        assert cfg.max_positions == 5
        assert cfg.position_pct == 0.2
        assert cfg.min_cash_pct == 0.05
        assert cfg.max_entries_per_day == 2
        assert cfg.commission_rate == 0.00025
        assert cfg.min_commission == 5.0
        assert cfg.stamp_duty_rate == 0.0005
        assert cfg.min_signal_days == 30
        # adaptive 默认关闭
        assert isinstance(cfg.adaptive, MarketAdaptiveConfig)
        assert cfg.adaptive.enabled is False

    def test_custom_values(self):
        adaptive = MarketAdaptiveConfig(enabled=True)
        cfg = PortfolioConfig(
            initial_capital=500_000.0,
            max_positions=3,
            position_pct=0.15,
            adaptive=adaptive,
        )
        assert cfg.initial_capital == 500_000.0
        assert cfg.max_positions == 3
        assert cfg.position_pct == 0.15
        assert cfg.adaptive.enabled is True
        # 未覆盖字段保持默认
        assert cfg.min_cash_pct == 0.05
        assert cfg.max_entries_per_day == 2

    def test_adaptive_independent_per_instance(self):
        """每个 PortfolioConfig 实例应有独立的 adaptive 对象"""
        c1 = PortfolioConfig()
        c2 = PortfolioConfig()
        c1.adaptive.enabled = True
        assert c2.adaptive.enabled is False


# ---------------------------------------------------------------------------
# PortfolioBacktestResult
# ---------------------------------------------------------------------------


class TestPortfolioBacktestResult:
    def test_defaults(self):
        r = PortfolioBacktestResult()
        assert r.dates == []
        assert r.net_values == []
        assert r.cash_history == []
        assert r.trades == []
        assert r.total_trades == 0
        assert r.win_count == 0
        assert r.loss_count == 0
        assert r.win_rate == 0.0
        assert r.total_return == 0.0
        assert r.annualized_return == 0.0
        assert r.sharpe_ratio == 0.0
        assert r.max_drawdown == 0.0
        assert r.calmar == 0.0

    def test_field_assignment(self):
        trade = LoopTrade(
            ts_code="000001.SZ",
            entry_date="20260101",
            entry_price=10.0,
            entry_reason="B1",
            stop_loss_price=9.0,
        )
        r = PortfolioBacktestResult(
            dates=["20260101", "20260102"],
            net_values=[1_000_000.0, 1_050_000.0],
            cash_history=[500_000.0, 550_000.0],
            trades=[trade],
            total_trades=1,
            win_count=1,
            loss_count=0,
            win_rate=1.0,
            total_return=0.05,
            annualized_return=0.10,
            sharpe_ratio=1.5,
            max_drawdown=0.03,
            calmar=3.33,
        )
        assert r.dates == ["20260101", "20260102"]
        assert r.net_values == [1_000_000.0, 1_050_000.0]
        assert r.cash_history == [500_000.0, 550_000.0]
        assert len(r.trades) == 1
        assert r.trades[0].ts_code == "000001.SZ"
        assert r.total_trades == 1
        assert r.win_rate == 1.0
        assert r.total_return == 0.05
        assert r.annualized_return == 0.10
        assert r.sharpe_ratio == 1.5
        assert r.max_drawdown == 0.03
        assert r.calmar == 3.33

    def test_default_lists_are_independent(self):
        """dataclass default_factory 保证各实例列表互不干扰"""
        r1 = PortfolioBacktestResult()
        r2 = PortfolioBacktestResult()
        r1.dates.append("20260101")
        assert r2.dates == []


# ---------------------------------------------------------------------------
# PortfolioBacktestEngine — 纯逻辑方法
# ---------------------------------------------------------------------------


class TestPortfolioBacktestEngineInit:
    def test_default_configs(self):
        engine = PortfolioBacktestEngine()
        assert isinstance(engine.portfolio_config, PortfolioConfig)
        assert engine.portfolio_config.initial_capital == 1_000_000.0

    def test_custom_configs(self):
        pc = PortfolioConfig(initial_capital=200_000.0)
        engine = PortfolioBacktestEngine(portfolio_config=pc)
        assert engine.portfolio_config.initial_capital == 200_000.0


class TestResolveAdaptive:
    """测试 _resolve_adaptive 根据市场环境解析有效仓位参数"""

    def _make_engine(self, **adaptive_kwargs):
        adaptive = MarketAdaptiveConfig(**adaptive_kwargs)
        pc = PortfolioConfig(
            max_positions=6,
            position_pct=0.2,
            max_entries_per_day=4,
            adaptive=adaptive,
        )
        return PortfolioBacktestEngine(portfolio_config=pc)

    def test_disabled_returns_base_values(self):
        engine = self._make_engine(enabled=False)
        mp, pp, me, allow = engine._resolve_adaptive(engine.portfolio_config, None)
        assert mp == 6
        assert pp == 0.2
        assert me == 4
        assert allow is True

    def test_none_context_returns_base_values(self):
        engine = self._make_engine(enabled=True)
        mp, pp, me, allow = engine._resolve_adaptive(engine.portfolio_config, None)
        assert mp == 6
        assert pp == 0.2
        assert me == 4
        assert allow is True

    def test_strong_regime(self):
        engine = self._make_engine(
            enabled=True,
            strong_max_positions_factor=1.5,
            strong_position_pct_factor=1.2,
            strong_max_entries_factor=2.0,
        )
        ctx = MarketContext(
            date="20260101",
            regime=MarketRegime.STRONG,
            index_trend=80.0,
            breadth=0.5,
            moneyflow_score=80.0,
        )
        mp, pp, me, allow = engine._resolve_adaptive(engine.portfolio_config, ctx)
        assert mp == 9  # 6 * 1.5
        assert pp == pytest.approx(0.24)  # 0.2 * 1.2
        assert me == 8  # 4 * 2.0
        assert allow is True

    def test_neutral_regime(self):
        engine = self._make_engine(
            enabled=True,
            neutral_max_positions_factor=0.8,
            neutral_position_pct_factor=0.9,
            neutral_max_entries_factor=1.0,
        )
        ctx = MarketContext(
            date="20260101",
            regime=MarketRegime.NEUTRAL,
            index_trend=50.0,
            breadth=0.0,
            moneyflow_score=50.0,
        )
        mp, pp, me, allow = engine._resolve_adaptive(engine.portfolio_config, ctx)
        assert mp == 5  # round(6 * 0.8) = 5
        assert pp == pytest.approx(0.18)  # 0.2 * 0.9
        assert me == 4  # 4 * 1.0
        assert allow is True

    def test_weak_regime_no_new_entries(self):
        engine = self._make_engine(
            enabled=True,
            weak_no_new_entries=True,
            weak_max_positions_factor=0.0,
        )
        ctx = MarketContext(
            date="20260101",
            regime=MarketRegime.WEAK,
            index_trend=20.0,
            breadth=-0.5,
            moneyflow_score=20.0,
        )
        mp, pp, me, allow = engine._resolve_adaptive(engine.portfolio_config, ctx)
        assert allow is False
        assert me == 0

    def test_weak_regime_allow_entries(self):
        engine = self._make_engine(
            enabled=True,
            weak_no_new_entries=False,
            weak_max_positions_factor=0.5,
            weak_position_pct_factor=0.5,
            weak_max_entries_factor=0.5,
        )
        ctx = MarketContext(
            date="20260101",
            regime=MarketRegime.WEAK,
            index_trend=20.0,
            breadth=-0.5,
            moneyflow_score=20.0,
        )
        mp, pp, me, allow = engine._resolve_adaptive(engine.portfolio_config, ctx)
        assert allow is True
        assert mp == 3  # round(6 * 0.5)
        assert pp == pytest.approx(0.1)  # 0.2 * 0.5
        assert me == 2  # round(4 * 0.5)


class TestBuildResult:
    """测试 _build_result 统计计算"""

    def _make_engine(self):
        return PortfolioBacktestEngine()

    def _make_trade(self, pnl_pct: float) -> LoopTrade:
        return LoopTrade(
            ts_code="000001.SZ",
            entry_date="20260101",
            entry_price=10.0,
            entry_reason="B1",
            stop_loss_price=9.0,
            exit_date="20260110",
            exit_price=10.0 * (1 + pnl_pct),
            pnl_pct=pnl_pct,
        )

    def test_empty_net_values(self):
        engine = self._make_engine()
        result = engine._build_result([], [], [], [])
        assert result.total_return == 0.0
        assert result.total_trades == 0

    def test_single_value_no_returns(self):
        engine = self._make_engine()
        result = engine._build_result(
            dates=["20260101"],
            net_values=[1_000_000.0],
            cash_history=[1_000_000.0],
            completed_trades=[],
        )
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0

    def test_basic_stats_with_trades(self):
        engine = self._make_engine()
        trades = [self._make_trade(0.10), self._make_trade(-0.05), self._make_trade(0.20)]
        net_values = [1_000_000.0, 1_050_000.0, 1_100_000.0, 1_150_000.0]
        result = engine._build_result(
            dates=["20260101", "20260102", "20260103", "20260104"],
            net_values=net_values,
            cash_history=[1_000_000.0] * 4,
            completed_trades=trades,
        )
        assert result.total_trades == 3
        assert result.win_count == 2
        assert result.loss_count == 1
        assert result.win_rate == pytest.approx(2 / 3)

        # total_return = 1_150_000 / 1_000_000 - 1 = 0.15
        assert result.total_return == pytest.approx(0.15)
        # annualized_return = (1.15)^(250/4) - 1
        expected_annual = (1.15) ** (252.0 / 4) - 1.0
        assert result.annualized_return == pytest.approx(expected_annual)

    def test_sharpe_calculation(self):
        """构造平坦净值序列（日收益=0），验证 Sharpe=0"""
        engine = self._make_engine()
        # 所有净值相同 → 日收益率全为 0 → std=0 → sharpe=0
        net_values = [100.0] * 10
        result = engine._build_result(
            dates=[f"202601{i + 1:02d}" for i in range(10)],
            net_values=net_values,
            cash_history=[100.0] * 10,
            completed_trades=[],
        )
        assert result.sharpe_ratio == 0.0

    def test_sharpe_with_varying_returns(self):
        engine = self._make_engine()
        # 交替涨跌，产生非零标准差
        net_values = [100.0, 102.0, 101.0, 103.0, 102.0, 104.0]
        result = engine._build_result(
            dates=[f"2026010{i}" for i in range(6)],
            net_values=net_values,
            cash_history=[100.0] * 6,
            completed_trades=[],
        )
        # 手动计算验证
        daily_rets = [(net_values[i] - net_values[i - 1]) / net_values[i - 1] for i in range(1, len(net_values))]
        avg_r = sum(daily_rets) / len(daily_rets)
        var = sum((r - avg_r) ** 2 for r in daily_rets) / (len(daily_rets) - 1)
        std = math.sqrt(var)
        expected_sharpe = (avg_r / std) * math.sqrt(252)
        assert result.sharpe_ratio == pytest.approx(expected_sharpe)

    def test_calmar_zero_drawdown(self):
        engine = self._make_engine()
        # 单调递增 → max_drawdown=0 → calmar=0
        net_values = [100.0, 101.0, 102.0, 103.0]
        result = engine._build_result(
            dates=["20260101", "20260102", "20260103", "20260104"],
            net_values=net_values,
            cash_history=[100.0] * 4,
            completed_trades=[],
        )
        assert result.max_drawdown == 0.0
        assert result.calmar == 0.0

    def test_win_rate_zero_trades(self):
        engine = self._make_engine()
        result = engine._build_result(
            dates=["20260101", "20260102"],
            net_values=[100.0, 101.0],
            cash_history=[100.0, 100.0],
            completed_trades=[],
        )
        assert result.total_trades == 0
        assert result.win_rate == 0.0


class TestRecentReturn:
    """测试 _recent_return 近期涨幅计算"""

    def _make_engine(self):
        return PortfolioBacktestEngine()

    def _make_daily_data(self, prices):
        """构造简易 DailyData 列表（只需 close 和 trade_date）"""
        from modules.indicators import DailyData

        result = []
        for i, p in enumerate(prices):
            dd = DailyData(
                ts_code="000001.SZ",
                trade_date=f"202601{i + 1:02d}",
                open=p,
                high=p * 1.01,
                low=p * 0.99,
                close=p,
                vol=1000.0,
                amount=p * 1000.0,
                prev_close=p,
                pct_chg=0.0,
            )
            result.append(dd)
        return result

    def test_basic_return(self):
        engine = self._make_engine()
        klines = self._make_daily_data([10.0, 11.0, 12.0, 10.5, 13.0])
        # idx=4, lookback=60 → start=0, return = (13-10)/10 = 0.3
        ret = engine._recent_return(klines, 4, lookback=60)
        assert ret == pytest.approx(0.3)

    def test_limited_lookback(self):
        engine = self._make_engine()
        klines = self._make_daily_data([10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 12.0])
        # idx=7, lookback=3 → start=5, return = (12-10)/10 = 0.2
        ret = engine._recent_return(klines, 7, lookback=3)
        assert ret == pytest.approx(0.2)

    def test_start_ge_idx_returns_zero(self):
        engine = self._make_engine()
        klines = self._make_daily_data([10.0, 11.0])
        # idx=0, lookback=5 → start=max(0,-4)=0, start >= idx → return 0
        ret = engine._recent_return(klines, 0, lookback=5)
        assert ret == 0.0

    def test_zero_price_returns_zero(self):
        engine = self._make_engine()
        klines = self._make_daily_data([0.0, 10.0, 11.0])
        # idx=2, lookback=60 → start=0, first_close=0 → return 0
        ret = engine._recent_return(klines, 2, lookback=60)
        assert ret == 0.0


class TestRunWithDataEdgeCases:
    """测试 run_with_data 的边界情况（空数据）"""

    def test_empty_klines_map(self):
        engine = PortfolioBacktestEngine()
        result = engine.run_with_data({}, [])
        assert result.dates == []
        assert result.net_values == []
        assert result.total_return == 0.0

    def test_empty_dates(self):
        engine = PortfolioBacktestEngine()
        result = engine.run_with_data({"000001.SZ": []}, [])
        assert result.dates == []


# ---------------------------------------------------------------------------
# v3.10.0：StrategyStats 数据结构
# ---------------------------------------------------------------------------


class TestStrategyStats:
    def test_defaults(self):
        stats = StrategyStats()
        assert stats.trade_count == 0
        assert stats.win_count == 0
        assert stats.loss_count == 0
        assert stats.win_rate == 0.0
        assert stats.total_pnl_pct == 0.0
        assert stats.avg_pnl_pct == 0.0
        assert stats.contribution_pct == 0.0

    def test_field_assignment(self):
        stats = StrategyStats(
            trade_count=10,
            win_count=6,
            loss_count=4,
            win_rate=0.6,
            total_pnl_pct=0.15,
            avg_pnl_pct=0.015,
            contribution_pct=0.75,
        )
        assert stats.trade_count == 10
        assert stats.win_count == 6
        assert stats.win_rate == 0.6
        assert stats.contribution_pct == 0.75


# ---------------------------------------------------------------------------
# v3.10.0：_resolve_strategy_weights
# ---------------------------------------------------------------------------


class TestResolveStrategyWeights:
    def _make_engine(self, **adaptive_kwargs):
        adaptive = MarketAdaptiveConfig(**adaptive_kwargs)
        pc = PortfolioConfig(
            strategy_weights={"B1": 1.0, "B2": 0.8},
            regime_strategy_weights={
                "STRONG": {"B1": 1.2, "B2": 1.0},
                "NEUTRAL": {"B1": 1.0, "B2": 0.8},
                "WEAK": {"B1": 0.7, "B2": 0.5},
            },
            adaptive=adaptive,
        )
        return PortfolioBacktestEngine(portfolio_config=pc)

    def test_disabled_returns_default_weights(self):
        engine = self._make_engine(enabled=False)
        weights = engine._resolve_strategy_weights(engine.portfolio_config, None)
        assert weights == {"B1": 1.0, "B2": 0.8}

    def test_none_context_returns_default_weights(self):
        engine = self._make_engine(enabled=True)
        weights = engine._resolve_strategy_weights(engine.portfolio_config, None)
        assert weights == {"B1": 1.0, "B2": 0.8}

    def test_strong_regime_returns_strong_weights(self):
        engine = self._make_engine(enabled=True)
        ctx = MarketContext(
            date="20260101",
            regime=MarketRegime.STRONG,
            index_trend=80.0,
            breadth=0.5,
            moneyflow_score=80.0,
        )
        weights = engine._resolve_strategy_weights(engine.portfolio_config, ctx)
        assert weights == {"B1": 1.2, "B2": 1.0}

    def test_weak_regime_returns_weak_weights(self):
        engine = self._make_engine(enabled=True)
        ctx = MarketContext(
            date="20260101",
            regime=MarketRegime.WEAK,
            index_trend=20.0,
            breadth=-0.5,
            moneyflow_score=20.0,
        )
        weights = engine._resolve_strategy_weights(engine.portfolio_config, ctx)
        assert weights == {"B1": 0.7, "B2": 0.5}

    def test_unknown_regime_falls_back_to_default(self):
        """配置中缺少的环境退回默认权重"""
        config = PortfolioConfig(
            strategy_weights={"B1": 1.0},
            regime_strategy_weights={"STRONG": {"B1": 1.5}},
        )
        adaptive = MarketAdaptiveConfig(enabled=True)
        config.adaptive = adaptive
        engine = PortfolioBacktestEngine(portfolio_config=config)
        ctx = MarketContext(
            date="20260101",
            regime=MarketRegime.WEAK,  # 未配置 WEAK
            index_trend=20.0,
            breadth=-0.5,
            moneyflow_score=20.0,
        )
        weights = engine._resolve_strategy_weights(config, ctx)
        assert weights == {"B1": 1.0}  # 退回默认


# ---------------------------------------------------------------------------
# v3.10.0：_compute_strategy_stats
# ---------------------------------------------------------------------------


class TestComputeStrategyStats:
    def _make_trade(self, pnl_pct: float, strategy_source: str) -> LoopTrade:
        return LoopTrade(
            ts_code="000001.SZ",
            entry_date="20260101",
            entry_price=10.0,
            entry_reason="test",
            stop_loss_price=9.0,
            exit_date="20260110",
            exit_price=10.0 * (1 + pnl_pct),
            pnl_pct=pnl_pct,
            strategy_source=strategy_source,
        )

    def test_empty_trades(self):
        stats = PortfolioBacktestEngine._compute_strategy_stats([])
        assert stats == {}

    def test_single_strategy(self):
        trades = [
            self._make_trade(0.10, "B1"),
            self._make_trade(-0.05, "B1"),
            self._make_trade(0.08, "B1"),
        ]
        stats = PortfolioBacktestEngine._compute_strategy_stats(trades)
        assert "B1" in stats
        b1 = stats["B1"]
        assert b1.trade_count == 3
        assert b1.win_count == 2
        assert b1.loss_count == 1
        assert b1.win_rate == pytest.approx(2 / 3)
        assert b1.total_pnl_pct == pytest.approx(0.13)  # 0.10 - 0.05 + 0.08
        assert b1.avg_pnl_pct == pytest.approx(0.13 / 3)

    def test_multiple_strategies(self):
        trades = [
            self._make_trade(0.10, "B1"),
            self._make_trade(0.20, "SB1"),
            self._make_trade(-0.05, "B1"),
        ]
        stats = PortfolioBacktestEngine._compute_strategy_stats(trades)
        assert set(stats.keys()) == {"B1", "SB1"}
        assert stats["SB1"].trade_count == 1
        assert stats["SB1"].win_count == 1
        assert stats["SB1"].total_pnl_pct == pytest.approx(0.20)

    def test_multi_strategy_resonance_splits_pnl(self):
        """多策略共振交易 pnl 均分到各策略"""
        # B1+SB1 共振，pnl=0.12 → 各分 0.06
        trades = [self._make_trade(0.12, "B1+SB1")]
        stats = PortfolioBacktestEngine._compute_strategy_stats(trades)
        assert "B1" in stats
        assert "SB1" in stats
        assert stats["B1"].trade_count == 1
        assert stats["SB1"].trade_count == 1
        assert stats["B1"].total_pnl_pct == pytest.approx(0.06)
        assert stats["SB1"].total_pnl_pct == pytest.approx(0.06)
        assert stats["B1"].win_count == 1
        assert stats["SB1"].win_count == 1

    def test_contribution_pct_sums_to_one(self):
        """所有策略 contribution_pct 之和应约等于 1"""
        trades = [
            self._make_trade(0.30, "B1"),
            self._make_trade(0.20, "SB1"),
            self._make_trade(-0.10, "B2"),
        ]
        stats = PortfolioBacktestEngine._compute_strategy_stats(trades)
        total_contrib = sum(s.contribution_pct for s in stats.values())
        assert total_contrib == pytest.approx(1.0)

    def test_unknown_strategy_source(self):
        """空 strategy_source 归类为 unknown"""
        trades = [self._make_trade(0.05, "")]
        stats = PortfolioBacktestEngine._compute_strategy_stats(trades)
        assert "unknown" in stats
        assert stats["unknown"].trade_count == 1

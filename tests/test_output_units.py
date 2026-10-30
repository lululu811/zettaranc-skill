"""输出单位约定回归测试。

同一个"单笔盈亏百分比"在本仓库有三种载体，单位并不相同：

| 类型 | 来源 | pnl_pct 单位 |
|---|---|---|
| `loop_engine.LoopTrade` | 少妇战法 / B1B2 回测 | **百分数**（10.0 = +10%） |
| `backtest.single.Trade` | 多策略组合回测 | **分数**（0.1 = +10%） |
| `simulator.TradeRecord` | 少女少妇模拟器 | **分数**（0.1 = +10%） |

序列化时把分数乘 100 变成百分数是对的，把已经是百分数的再乘 100 就错了
（+10% 会变成 1000%）。这些测试把四个序列化器的单位钉死，避免再次漂移。
"""

from __future__ import annotations

import pytest

from modules.backtest.single import (
    BacktestResult,
    MultiStrategyBacktestResult,
    Trade,
    _make_trade,
)
from modules.backtest_six_step import ShaofuBacktestResult, summary_text
from modules.loop_engine import LoopTrade

# 一笔 +10% 的交易
ENTRY = 100.0
EXIT = 110.0
PCT = 10.0


def _loop_trade() -> LoopTrade:
    """LoopTrade：pnl_pct 是百分数。"""
    return LoopTrade(
        ts_code="600519.SH",
        entry_date="20260101",
        entry_price=ENTRY,
        exit_date="20260110",
        exit_price=EXIT,
        pnl_pct=PCT,
        entry_reason="B2确认",
        stop_loss_price=95.0,
    )


def _single_trade() -> Trade:
    """single.Trade：pnl_pct 是分数。"""
    return _make_trade("600519.SH", "20260101", ENTRY, "20260110", EXIT, "signal")


def _shaofu_result() -> ShaofuBacktestResult:
    """少妇战法结果：trades 是 LoopTrade，avg_pnl 等聚合字段同为百分数。"""
    return ShaofuBacktestResult(
        ts_code="600519.SH",
        trades=[_loop_trade()],
        total_trades=1,
        win_count=1,
        win_rate=1.0,
        avg_pnl=PCT,
        avg_win=PCT,
        avg_loss=0.0,
        max_win=PCT,
        max_loss=0.0,
        total_return=0.1,
        max_drawdown=0.05,
        sharpe_ratio=1.0,
        avg_holding_days=3.0,
    )


class TestApiShaofuSerializerUnits:
    """API 的少妇战法序列化（LoopTrade → 百分数，不能再乘 100）。"""

    @pytest.fixture
    def response(self):
        from api.services.backtest_service import _shaofu_to_response

        return _shaofu_to_response("600519.SH", _shaofu_result())

    def test_trade_pnl_pct_is_percentage(self, response):
        assert response["trades"][0]["pnl_pct"] == pytest.approx(PCT)

    def test_aggregate_pnl_fields_are_percentage(self, response):
        summary = response["summary"]
        assert summary["avg_pnl"] == pytest.approx(PCT)
        assert summary["max_win"] == pytest.approx(PCT)

    def test_fraction_fields_stay_percentage(self, response):
        """total_return / max_drawdown 是分数，乘 100 才对。"""
        summary = response["summary"]
        assert summary["total_return"] == pytest.approx(10.0)
        assert summary["max_drawdown"] == pytest.approx(5.0)

    def test_equity_curve_compounds_correctly(self, response):
        """+10% 的交易 → 100000 变 110000（复利要除以 100）。"""
        assert response["equity_curve"][0][1] == pytest.approx(110000.0)


class TestApiPortfolioSerializerUnits:
    """API 的组合序列化（single.Trade → 分数，乘 100 才对）。"""

    def test_trade_pnl_pct_is_percentage(self):
        from api.services.backtest_service import _portfolio_to_response

        result = MultiStrategyBacktestResult(trades=[_single_trade()], total_trades=1, total_return=0.1)
        out = _portfolio_to_response("600519.SH", result)
        assert out["trades"][0]["pnl_pct"] == pytest.approx(PCT)


class TestCliSerializerUnits:
    """CLI 的两个序列化器。"""

    def test_shaofu_trade_pnl_pct_is_percentage(self):
        from modules.cli_commands.backtest import _shaofu_result_to_dict

        out = _shaofu_result_to_dict(_shaofu_result())
        assert out["trades"][0]["pnl_pct"] == pytest.approx(PCT)

    def test_portfolio_trade_pnl_pct_is_percentage(self):
        from modules.cli_commands.backtest import _portfolio_result_to_dict

        result = MultiStrategyBacktestResult(trades=[_single_trade()], total_trades=1, total_return=0.1)
        out = _portfolio_result_to_dict(result)
        assert out["trades"][0]["pnl_pct"] == pytest.approx(PCT)

    def test_cli_and_api_agree_on_portfolio_pnl_pct(self):
        """同一份结果，CLI 与 API 必须给出同一个 pnl_pct。

        这条是核心护栏：过去两者单位假设相反，CLI 给 0.1、API 给 10.0。
        """
        from api.services.backtest_service import _portfolio_to_response
        from modules.cli_commands.backtest import _portfolio_result_to_dict

        result = MultiStrategyBacktestResult(trades=[_single_trade()], total_trades=1, total_return=0.1)
        cli_value = _portfolio_result_to_dict(result)["trades"][0]["pnl_pct"]
        api_value = _portfolio_to_response("600519.SH", result)["trades"][0]["pnl_pct"]
        assert cli_value == api_value == pytest.approx(PCT)


class TestSimulatorSerializerUnits:
    """模拟器的 TradeRecord.pnl_pct 是分数，×100 是对的——别"顺手修错"。"""

    def test_simulator_service_keeps_fraction_to_percentage(self):
        from api.services.simulator_service import _result_to_response
        from modules.simulator import SimulationConfig, SimulationResult, TradeRecord

        trade = TradeRecord(
            ts_code="600519.SH",
            name="贵州茅台",
            action="SELL",
            date="20260110",
            price=EXIT,
            shares=100,
            pnl=1000.0,
            pnl_pct=0.1,
            reason="止盈",
            fee=5.0,
            stamp_duty=1.0,
            transfer_fee=0.1,
        )
        result = SimulationResult(
            config=SimulationConfig(),
            trades=[trade],
            initial_capital=100000.0,
            final_value=101000.0,
            total_return=0.1,
            total_trades=1,
            win_rate=1.0,
            profit_factor=2.0,
            max_drawdown=0.02,
            sharpe_ratio=1.0,
            avg_holding_days=3.0,
        )
        out = _result_to_response(result)
        assert out["trades"][0]["pnl_pct"] == pytest.approx(PCT)


class TestReportFormatters:
    """报告格式化器：别把已经是百分数的值再用 :.2%（那会再乘 100）。"""

    def test_six_step_summary_shows_real_percentage(self):
        text = summary_text(_shaofu_result())
        assert "平均盈亏:     +10.00%" in text
        assert "1000.00%" not in text

    def test_single_summary_shows_real_percentage(self):
        result = BacktestResult(ts_code="600519.SH", trades=[_single_trade()])
        result.avg_return = 0.1
        text = result.summary()
        assert "平均收益:   10.00%" in text
        assert "0.10%" not in text

    def test_single_trade_detail_shows_real_percentage(self):
        result = BacktestResult(ts_code="600519.SH", trades=[_single_trade()])
        text = result.summary()
        assert "+10.00%" in text

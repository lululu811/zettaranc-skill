"""v1.0 验收管线测试"""

from __future__ import annotations

import os

import pytest

from modules.verify.pipeline import (
    AggregateMetrics,
    GateResult,
    StockResult,
    VerifyResult,
    _load_klines_with_precheck,
    _run_single_stock_backtest,
    verify_v10_pipeline,
)

# 真实数据回归：未配置 TUSHARE_TOKEN 时整条测试 skip
_TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
_RUN_REALDATA = os.environ.get("RUN_REALDATA", "").lower() == "true"


def test_dataclasses_importable():
    """数据契约能被外部 import"""
    assert VerifyResult is not None
    assert StockResult is not None
    assert AggregateMetrics is not None
    assert GateResult is not None


def test_pipeline_function_exists():
    """verify_v10_pipeline 是公开 API"""
    assert callable(verify_v10_pipeline)


def test_pipeline_empty_stocks_returns_empty_result():
    """空股票列表：返回带零指标的 VerifyResult，不抛异常"""
    result = verify_v10_pipeline(ts_codes=[], days=250)
    assert isinstance(result, VerifyResult)
    assert result.per_stock == []
    assert result.aggregate.total_trades == 0
    assert result.aggregate.win_rate == 0.0


def test_load_klines_skips_short_history():
    """数据 < 60 天的股票应被标记 skipped"""
    # 真实数据缺失时自动跳过（不需要 stub）
    result = _load_klines_with_precheck(
        ts_codes=["000001.SZ", "999999.SH"],  # 999999 不存在
        days=250,
    )
    assert isinstance(result, list)
    assert any(r.skipped for r in result)
    skipped_codes = [r.ts_code for r in result if r.skipped]
    assert "999999.SH" in skipped_codes


@pytest.mark.realdata
@pytest.mark.skipif(
    not _TUSHARE_TOKEN or not _RUN_REALDATA,
    reason="需配置 TUSHARE_TOKEN 并设置 RUN_REALDATA=true 才能跑真实数据回归",
)
def test_backtest_single_real_stock_returns_metrics():
    """真实股票回测返回有效指标（无 token 时 skip）"""
    result = _run_single_stock_backtest("600519.SH", days=250)
    assert isinstance(result, StockResult)
    assert result.ts_code == "600519.SH"
    assert not result.skipped
    # 至少有一个交易或零交易（极端行情）
    assert result.trades >= 0
    assert 0.0 <= result.win_rate <= 1.0


def test_pipeline_aggregate_has_zero_for_empty_run():
    """全跳过的 pipeline：aggregate 是零值，不是抛异常"""
    result = verify_v10_pipeline(ts_codes=["999999.SH"], days=250)
    assert isinstance(result, VerifyResult)
    assert isinstance(result.aggregate, AggregateMetrics)
    assert result.aggregate.total_trades == 0
    # meta 记录跳过的股票数
    assert result.meta.get("skipped_count", 0) >= 1


def test_pipeline_meta_contains_run_metadata():
    """meta 字段包含样本信息"""
    result = verify_v10_pipeline(ts_codes=[], days=250)
    assert "ts_codes_count" in result.meta or "empty_input" in result.meta


def test_aggregate_metrics_uses_merged_equity_curve():
    """_aggregate_metrics 应基于组合资金曲线计算收益、回撤和 Calmar"""
    from modules.verify.pipeline import _aggregate_metrics

    stocks = [
        StockResult(
            ts_code="A",
            name="",
            trades=2,
            win_rate=0.5,
            return_pct=0.0,
            sharpe=0.5,
            max_drawdown=0.10,
            equity_curve=[100.0, 110.0, 100.0],
        ),
        StockResult(
            ts_code="B",
            name="",
            trades=2,
            win_rate=0.5,
            return_pct=0.02,
            sharpe=0.3,
            max_drawdown=0.03,
            equity_curve=[100.0, 105.0, 102.0],
        ),
    ]
    metrics = _aggregate_metrics(stocks, days=250)

    # 总交易数 = 4
    assert metrics.total_trades == 4
    # 组合曲线 = [100, 107.5, 101]
    assert metrics.total_return_pct == pytest.approx(101.0 / 100.0 - 1.0, rel=1e-6)
    # 最大回撤基于组合曲线：peak=107.5, trough=101
    expected_max_dd = (107.5 - 101.0) / 107.5
    assert metrics.max_drawdown == pytest.approx(expected_max_dd, rel=1e-6)
    # Calmar 应基于组合年化收益 / 组合最大回撤，且为正
    assert metrics.calmar > 0
    assert metrics.calmar == pytest.approx(metrics.annualized_return / metrics.max_drawdown, rel=1e-6)


def test_aggregate_metrics_empty_active_returns_zero():
    """无有效交易时返回零值"""
    from modules.verify.pipeline import _aggregate_metrics

    metrics = _aggregate_metrics([], days=250)
    assert metrics.total_trades == 0
    assert metrics.annualized_return == 0.0
    assert metrics.max_drawdown == 0.0
    assert metrics.calmar == 0.0


def test_pipeline_use_portfolio_engine_branch():
    """use_portfolio_engine=True 时走组合引擎分支"""
    from unittest.mock import patch, MagicMock

    mock_pb_result = MagicMock()
    mock_pb_result.total_trades = 10
    mock_pb_result.win_count = 6
    mock_pb_result.win_rate = 0.6
    mock_pb_result.total_return = 0.15
    mock_pb_result.annualized_return = 0.20
    mock_pb_result.sharpe_ratio = 0.8
    mock_pb_result.max_drawdown = 0.10
    mock_pb_result.calmar = 2.0
    mock_pb_result.trades = []

    with patch(
        "modules.verify.portfolio_engine.PortfolioBacktestEngine.run",
        return_value=mock_pb_result,
    ):
        result = verify_v10_pipeline(
            ts_codes=["600519.SH"],
            days=250,
            use_portfolio_engine=True,
        )

    assert isinstance(result, VerifyResult)
    assert result.meta.get("use_portfolio_engine") is True
    assert result.aggregate.total_trades == 10
    assert result.aggregate.annualized_return == pytest.approx(0.20, rel=1e-6)
    assert result.aggregate.calmar == pytest.approx(2.0, rel=1e-6)


def test_pipeline_passes_portfolio_config_to_engine():
    """pipeline 将 portfolio_config（含 adaptive 配置）传给组合引擎"""
    from unittest.mock import patch
    from modules.verify.portfolio_engine import PortfolioConfig, MarketAdaptiveConfig

    captured_config = None

    def capture_init(self, portfolio_config=None, loop_config=None):
        nonlocal captured_config
        captured_config = portfolio_config

    with (
        patch(
            "modules.verify.portfolio_engine.PortfolioBacktestEngine.__init__",
            capture_init,
        ),
        patch(
            "modules.verify.portfolio_engine.PortfolioBacktestEngine.run",
            return_value=None,
        ),
    ):
        # run 返回 None 会触发属性错误，这里只验证构造时传入的配置
        try:
            verify_v10_pipeline(
                ts_codes=["600519.SH"],
                days=250,
                use_portfolio_engine=True,
                portfolio_config=PortfolioConfig(
                    adaptive=MarketAdaptiveConfig(enabled=True),
                ),
            )
        except AttributeError:
            pass

    assert captured_config is not None
    assert captured_config.adaptive.enabled is True

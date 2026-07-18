"""
core 模块测试
"""

import pytest
from modules.core import (
    WalkForwardSplit,
    make_walk_forward_splits,
    MarketRegime,
    MarketContext,
    classify_market_regime,
    PerformanceMetrics,
    calculate_performance_metrics,
    daily_returns,
    compute_drawdown,
    disable_proxy,
)


class TestWalkForward:
    """Walk-forward 测试"""

    def test_make_splits_basic(self):
        """基本切片功能"""
        splits = make_walk_forward_splits(
            total_days=300,
            train_days=120,
            test_days=60,
        )
        assert len(splits) > 0
        assert all(isinstance(s, WalkForwardSplit) for s in splits)

    def test_make_splits_no_overlap(self):
        """OOS 段不重叠"""
        splits = make_walk_forward_splits(
            total_days=300,
            train_days=120,
            test_days=60,
        )
        for i in range(len(splits) - 1):
            assert splits[i].test_end <= splits[i + 1].test_start

    def test_make_splits_insufficient_data(self):
        """数据不足时返回空列表"""
        splits = make_walk_forward_splits(
            total_days=100,
            train_days=120,
            test_days=60,
        )
        assert len(splits) == 0

    def test_make_splits_partial_last(self):
        """允许最后一段部分覆盖"""
        splits = make_walk_forward_splits(
            total_days=250,
            train_days=120,
            test_days=60,
            allow_partial_last=True,
        )
        # 应该有切片
        assert len(splits) > 0
        # 最后一段的 test_end 应该 <= total_days
        assert splits[-1].test_end <= 250


class TestMarketContext:
    """市场环境测试"""

    def test_classify_strong(self):
        """强势市场判定"""
        regime = classify_market_regime(
            trend_score=70.0,
            breadth=0.2,
            moneyflow_score=60.0,
        )
        assert regime == MarketRegime.STRONG

    def test_classify_weak_trend(self):
        """弱势市场判定（趋势弱）"""
        regime = classify_market_regime(
            trend_score=30.0,
            breadth=0.0,
            moneyflow_score=50.0,
        )
        assert regime == MarketRegime.WEAK

    def test_classify_weak_breadth(self):
        """弱势市场判定（ breadth 弱）"""
        regime = classify_market_regime(
            trend_score=50.0,
            breadth=-0.2,
            moneyflow_score=50.0,
        )
        assert regime == MarketRegime.WEAK

    def test_classify_weak_moneyflow(self):
        """弱势市场判定（资金弱）"""
        regime = classify_market_regime(
            trend_score=50.0,
            breadth=0.0,
            moneyflow_score=30.0,
        )
        assert regime == MarketRegime.WEAK

    def test_classify_neutral(self):
        """震荡市场判定"""
        regime = classify_market_regime(
            trend_score=50.0,
            breadth=0.0,
            moneyflow_score=50.0,
        )
        assert regime == MarketRegime.NEUTRAL

    def test_market_context_dataclass(self):
        """MarketContext 数据类"""
        ctx = MarketContext(
            date="20260711",
            regime=MarketRegime.STRONG,
            index_trend=70.0,
            breadth=0.2,
            moneyflow_score=60.0,
            notes=["test"],
        )
        assert ctx.date == "20260711"
        assert ctx.regime == MarketRegime.STRONG
        assert "test" in ctx.notes


class TestDailyReturns:
    """日收益率计算测试"""

    def test_basic(self):
        """基本日收益率计算"""
        values = [100.0, 110.0, 105.0, 120.0]
        rets = daily_returns(values)
        assert len(rets) == 3
        assert rets[0] == pytest.approx(0.10, rel=1e-6)
        assert rets[1] == pytest.approx(-5.0 / 110.0, rel=1e-6)
        assert rets[2] == pytest.approx(15.0 / 105.0, rel=1e-6)

    def test_with_zero(self):
        """前值为 0 时返回 0"""
        values = [0.0, 100.0, 200.0]
        rets = daily_returns(values)
        assert rets[0] == 0.0
        assert rets[1] == pytest.approx(1.0, rel=1e-6)

    def test_empty(self):
        """空列表返回空列表"""
        assert daily_returns([]) == []

    def test_single_value(self):
        """单值返回空列表"""
        assert daily_returns([100.0]) == []


class TestComputeDrawdown:
    """回撤计算测试"""

    def test_basic(self):
        """基本回撤计算"""
        values = [100.0, 110.0, 90.0, 120.0]
        max_dd, duration = compute_drawdown(values)
        # 最大回撤: (110 - 90) / 110
        assert max_dd == pytest.approx(20.0 / 110.0, rel=1e-6)

    def test_no_drawdown(self):
        """单调上涨无回撤"""
        values = [100.0, 110.0, 120.0, 130.0]
        max_dd, _ = compute_drawdown(values)
        assert max_dd == 0.0

    def test_empty(self):
        """空列表返回 (0.0, 0)"""
        max_dd, duration = compute_drawdown([])
        assert max_dd == 0.0
        assert duration == 0

    def test_duration(self):
        """回撤持续时间计算"""
        # 峰值在 index 1 (110), 新高在 index 4 (115)
        # 持续时间 = 4 - 1 = 3
        values = [100.0, 110.0, 95.0, 90.0, 115.0]
        max_dd, duration = compute_drawdown(values)
        assert duration == 3
        # 最大回撤: (110 - 90) / 110
        assert max_dd == pytest.approx(20.0 / 110.0, rel=1e-6)


class TestMetrics:
    """绩效指标测试"""

    def test_calculate_basic(self):
        """基本指标计算"""
        equity_curve = [100.0, 110.0, 105.0, 120.0]
        metrics = calculate_performance_metrics(equity_curve)

        assert metrics.total_return == pytest.approx(0.20, rel=1e-6)
        assert metrics.max_drawdown > 0
        assert metrics.annualized_return != 0

    def test_calculate_empty_curve(self):
        """空资金曲线"""
        metrics = calculate_performance_metrics([])
        assert metrics.total_return == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_calculate_with_trades(self):
        """带交易记录"""
        equity_curve = [100.0, 110.0, 105.0, 120.0]
        trades = [
            {"pnl": 10.0, "holding_days": 5},
            {"pnl": -5.0, "holding_days": 3},
            {"pnl": 15.0, "holding_days": 7},
        ]
        metrics = calculate_performance_metrics(equity_curve, trades)

        assert metrics.total_trades == 3
        assert metrics.win_rate == pytest.approx(2 / 3, rel=1e-6)
        assert metrics.avg_holding_days == pytest.approx(5.0, rel=1e-6)

    def test_calculate_max_drawdown(self):
        """最大回撤计算"""
        equity_curve = [100.0, 110.0, 90.0, 120.0]
        metrics = calculate_performance_metrics(equity_curve)

        # 最大回撤应该是 (110 - 90) / 110
        expected_dd = (110.0 - 90.0) / 110.0
        assert metrics.max_drawdown == pytest.approx(expected_dd, rel=1e-6)

    def test_calculate_sharpe_ratio(self):
        """夏普比率计算"""
        # 稳定上涨的资金曲线
        equity_curve = [100.0, 101.0, 102.0, 103.0, 104.0]
        metrics = calculate_performance_metrics(equity_curve)

        # 应该有正的夏普比率
        assert metrics.sharpe_ratio > 0


class TestNet:
    """disable_proxy 测试"""

    def test_disable_proxy_clears_env(self, monkeypatch):
        """调用后 HTTP_PROXY 和 HTTPS_PROXY 被清空"""
        monkeypatch.setenv("HTTP_PROXY", "http://proxy.example.com:8080")
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.com:8443")

        disable_proxy()

        import os

        assert os.environ["HTTP_PROXY"] == ""
        assert os.environ["HTTPS_PROXY"] == ""

    def test_disable_proxy_when_not_set(self, monkeypatch):
        """环境变量不存在时，调用后被设置为空字符串"""
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)

        disable_proxy()

        import os

        assert os.environ["HTTP_PROXY"] == ""
        assert os.environ["HTTPS_PROXY"] == ""

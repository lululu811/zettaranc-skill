"""Tests for BacktestScorer — 参数评分引擎。"""
import pytest

from modules.self_optimizer.backtest_scorer import (
    BacktestScorer,
    StockScore,
    ScoringResult,
)
from modules.self_optimizer.param_registry import get_defaults, using_params, get_active_param
from conftest import generate_b1_scenario, write_klines_to_db, write_stock_basic


@pytest.fixture
def scorer():
    """小股票池 + 短回测周期。"""
    return BacktestScorer(
        stock_pool=["600487.SH"],
        days=60,
    )

@pytest.fixture
def seeded_db(temp_db, db_conn):
    """临时数据库灌入 B1 场景数据。"""
    ts_code = "SEEDED_B1"
    rows = generate_b1_scenario(ts_code=ts_code)
    write_stock_basic(db_conn, ts_code=ts_code, name="测试B1")
    write_klines_to_db(db_conn, rows)
    return ts_code


class TestStockScore:
    def test_has_trades_positive(self):
        s = StockScore(ts_code="A", win_rate=0.5, sharpe_ratio=0, total_return=0, max_drawdown=0, total_trades=5, score=50)
        assert s.has_trades is True

    def test_has_trades_zero(self):
        s = StockScore(ts_code="A", win_rate=0, sharpe_ratio=0, total_return=0, max_drawdown=0, total_trades=0, score=0)
        assert s.has_trades is False


class TestScoringResult:
    def test_empty_result(self):
        r = ScoringResult()
        assert r.composite_score == 0.0
        assert r.stock_count == 0
        assert r.traded_count == 0

    def test_single_stock(self):
        r = ScoringResult(scores=[StockScore("A", 0.5, 0, 0.1, 0.2, 10, 66.0)])
        assert r.composite_score == 66.0

    def test_multiple_stocks(self):
        r = ScoringResult(scores=[
            StockScore("A", 0, 0, 0, 0, 0, 50),
            StockScore("B", 0, 0, 0, 0, 0, 70),
        ])
        assert r.composite_score == 60.0

    def test_traded_count(self):
        r = ScoringResult(scores=[
            StockScore("A", 0, 0, 0, 0, 5, 50),
            StockScore("B", 0, 0, 0, 0, 0, 0),
            StockScore("C", 0, 0, 0, 0, 3, 30),
        ])
        assert r.traded_count == 2


class TestBacktestScorer:
    def test_score_returns_result(self, scorer):
        result = scorer.score()
        assert isinstance(result, ScoringResult)
        assert result.stock_count == 1

    def test_score_with_null_params(self, scorer):
        """params=None 应正常运行（用 registry 默认值）。"""
        result = scorer.score(params=None)
        assert result.composite_score >= 0

    def test_score_with_overrides(self, scorer):
        """传 override 参数应能跑完且分数在合理范围。"""
        params = get_defaults()
        params["b1"]["j_threshold"] = -8
        result = scorer.score(params=params)
        assert 0 <= result.composite_score <= 100

    def test_score_vs_baseline(self, scorer):
        """score_vs_baseline 返回两套结果。"""
        params = get_defaults()
        params["b1"]["j_threshold"] = -15
        baseline, mutated = scorer.score_vs_baseline(params)
        assert isinstance(baseline, ScoringResult)
        assert isinstance(mutated, ScoringResult)
        assert baseline.composite_score >= 0
        assert mutated.composite_score >= 0

    @pytest.mark.skip(reason="需真实数据——合成数据不触发 B1 信号")
    def test_override_actually_changes_backtest(self, seeded_db):
        """极端参数应产生可测量的分数变化（集成测试）。"""
        scorer = BacktestScorer(stock_pool=[seeded_db], days=250)
        baseline = scorer.score()
        params = get_defaults()
        params["b1"]["j_threshold"] = -30
        mutated = scorer.score(params=params)

        scores_eq = abs(mutated.composite_score - baseline.composite_score) < 0.01
        trade_counts_eq = (
            sum(s.total_trades for s in mutated.scores)
            == sum(s.total_trades for s in baseline.scores)
        )
        assert not (scores_eq and trade_counts_eq)

    def test_pool_selection_respects_max_stocks(self):
        """max_stocks 限制股票池大小。"""
        pool = ["A", "B", "C", "D", "E"]
        scorer = BacktestScorer(stock_pool=pool, max_stocks=2)
        selected = scorer._select_pool()
        assert len(selected) <= 2

    def test_errors_gracefully(self):
        """无效股票代码应优雅降级（score=0 而非抛异常）。"""
        scorer = BacktestScorer(stock_pool=["NOT_EXIST"], days=30)
        result = scorer.score()
        assert result.composite_score == 0


class TestOverrideIntegration:
    def test_using_params_context(self):
        """using_params 上下文管理器正确设置和恢复。"""
        # Before: 没有 override
        assert get_active_param("b1", "j_threshold", -10) == -10

        params = {"b1": {"j_threshold": -99}}
        with using_params(params):
            assert get_active_param("b1", "j_threshold", -10) == -99

        # After: 自动恢复
        assert get_active_param("b1", "j_threshold", -10) == -10

    def test_using_params_nested(self):
        """嵌套 using_params 应正确恢复外层。"""
        outer = {"b1": {"j_threshold": -10}}
        inner = {"b1": {"j_threshold": -20}}

        with using_params(outer):
            assert get_active_param("b1", "j_threshold", 0) == -10
            with using_params(inner):
                assert get_active_param("b1", "j_threshold", 0) == -20
            assert get_active_param("b1", "j_threshold", 0) == -10

    def test_using_params_with_exception(self):
        """异常退出上下文也应恢复。"""
        params = {"b1": {"j_threshold": -99}}
        try:
            with using_params(params):
                assert get_active_param("b1", "j_threshold", -10) == -99
                raise ValueError("模拟异常")
        except ValueError:
            pass
        assert get_active_param("b1", "j_threshold", -10) == -10

    def test_set_active_params_direct(self):
        """set_active_params 直接设置。"""
        from modules.self_optimizer.param_registry import set_active_params

        set_active_params({"b1": {"j_threshold": 100}})
        assert get_active_param("b1", "j_threshold", 0) == 100
        # 清理
        set_active_params({})

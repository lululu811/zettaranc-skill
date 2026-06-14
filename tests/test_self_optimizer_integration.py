"""集成测试: phase1 baseline + phase2 keep/revert + phase2 break."""
from __future__ import annotations

import pytest

from modules.self_optimizer.phase1_baseline import phase1_baseline
from modules.self_optimizer.phase2_hillclimb import (
    RoundResult,
    run_round,
    check_break_signal,
)
from modules.self_optimizer.backtest_scorer import BacktestScorer, ScoringResult, StockScore
from modules.self_optimizer.mutator import ParamMutator
from modules.self_optimizer.param_registry import get_defaults


def test_phase1_baseline_with_mock_data(mock_monthly_reviews_with_poor_strategy):
    """mock 3 个月数据, baseline_score 必须在 [0, 100]."""
    score = phase1_baseline(target="trading", review_months=3)
    assert 0 <= score <= 100
    assert 25 <= score <= 40


class TestPhase2V2Pipeline:
    """V2 管线：用 mock scorer/mutator 测试 keep/revert 逻辑。"""

    @pytest.fixture(autouse=True)
    def _mock_blacklist(self, monkeypatch):
        """忽略 reflex_blacklist（本类只测 ratchet 逻辑）。"""
        monkeypatch.setattr(
            "modules.self_optimizer.phase2_hillclimb.check_all",
            lambda ctx: [],
        )

    def _make_fake_scorer(self, baseline: float, mutated: float) -> BacktestScorer:
        """scorer 返回固定基线/变异分数。"""
        class FakeScorer(BacktestScorer):
            def score(self, **kw):
                ss = StockScore("FAKE", 0, 0, 0, 0, 5, mutated)
                return ScoringResult(scores=[ss])
            def score_vs_baseline(self, params):
                b = ScoringResult(scores=[StockScore("FAKE", 0, 0, 0, 0, 5, baseline)])
                m = ScoringResult(scores=[StockScore("FAKE", 0, 0, 0, 0, 5, mutated)])
                return b, m
        return FakeScorer(stock_pool=["FAKE"], days=30, max_stocks=1)

    def test_revert_when_score_drops(self):
        """变异得分低于基线 → revert。"""
        mutator = ParamMutator(seed=42)
        scorer = self._make_fake_scorer(baseline=80.0, mutated=50.0)
        params = get_defaults()

        result = run_round(
            round_n=1, old_score=80.0, target="trading", history=[],
            scorer=scorer, mutator=mutator, current_best_params=params,
        )
        assert result.status == "revert"
        assert result.new_score < result.old_score

    def test_keep_when_score_improves(self):
        """变异得分高于基线 → keep。"""
        mutator = ParamMutator(seed=42)
        scorer = self._make_fake_scorer(baseline=80.0, mutated=90.0)
        params = get_defaults()

        result = run_round(
            round_n=1, old_score=80.0, target="trading", history=[],
            scorer=scorer, mutator=mutator, current_best_params=params,
        )
        assert result.status == "keep"
        assert result.new_score > result.old_score

    def test_break_after_consecutive_small_deltas(self):
        """连续 3 轮 delta<0.5 → break。"""
        mutator = ParamMutator(seed=42)

        class StaircaseScorer(BacktestScorer):
            def __init__(self):
                super().__init__(stock_pool=["FAKE"], days=30, max_stocks=1)
                self._call = 0
            def score(self, **kw):
                self._call += 1
                score = {1: 80.3, 2: 80.1, 3: 80.4}.get(self._call, 80.0)
                ss = StockScore("FAKE", 0, 0, 0, 0, 5, score)
                return ScoringResult(scores=[ss])
            def score_vs_baseline(self, params):
                m = self.score()
                b = self.score()
                return b, m

        scorer = StaircaseScorer()
        params = get_defaults()
        history: list[RoundResult] = []

        for n in range(1, 5):
            old = 80.0 if n == 1 else (history[-1].new_score if history else 80.0)
            result = run_round(
                round_n=n, old_score=old, target="trading", history=history,
                scorer=scorer, mutator=mutator, current_best_params=params,
            )
            history.append(result)
            if result.status == "break":
                break

        assert history[-1].status == "break"

    def test_round_result_contains_mutated_params(self):
        """RoundResult 记录变异参数。"""
        mutator = ParamMutator(seed=1)
        params = get_defaults()

        class TrackingScorer(BacktestScorer):
            def score(self, **kw):
                ss = StockScore("FAKE", 0.5, 0, 0.1, 0.2, 5, 85.0)
                return ScoringResult(scores=[ss])
            def score_vs_baseline(self, p):
                b = self.score()
                m = self.score()
                return b, m

        result = run_round(
            round_n=1, old_score=80.0, target="trading", history=[],
            scorer=TrackingScorer(stock_pool=["FAKE"], days=30, max_stocks=1),
            mutator=mutator, current_best_params=params,
        )
        assert result.mutated_params != {}
        assert "b1" in result.mutated_params

    def test_check_break_signal_utility(self):
        """check_break_signal 纯函数正常工作。"""
        def make(status, delta):
            return RoundResult(
                    round=1, old_score=80.0, new_score=80.0 + delta,
                    delta=delta, status=status, violations=[],
                    proposed_diff="", timestamp="",
                )
        assert check_break_signal([make("keep", 0.3), make("keep", 0.4)], 0.5) is True
        assert check_break_signal([make("keep", 1.0), make("keep", 1.0)], 0.5) is False
        assert check_break_signal([]) is False
        assert check_break_signal([make("keep", 0.3)]) is False


class TestOptimizerSmoke:
    """端到端冒烟测试：真实 scorer + mutator + 几轮优化。"""

    def test_pipeline_runs_without_error(self):
        """完整的 3 轮优化管线不崩溃、返回合理分数。"""
        scorer = BacktestScorer(stock_pool=["600487.SH"], days=60, max_stocks=1, seed=42)
        mutator = ParamMutator(seed=42)
        params = get_defaults()

        baseline = scorer.score()
        assert 0 <= baseline.composite_score <= 100

        best_score = baseline.composite_score
        best_params = dict(params)

        for n in range(3):
            new_params, rec = mutator.mutate_one(best_params, strategy="jitter")
            result = scorer.score(params=new_params)
            if result.composite_score > best_score:
                best_score = result.composite_score
                best_params = dict(new_params)

        assert best_score >= 0
        assert best_score <= 100

    def test_wired_params_only_by_default(self):
        """mutator 默认只选 wired=True 的参数。"""
        mutator = ParamMutator(seed=42)
        seen_unwired = set()

        for _ in range(100):
            _, rec = mutator.mutate_one(get_defaults())
            spec = __import__("modules.self_optimizer.param_registry", fromlist=[""]).get_param_info(
                rec.strategy, rec.param_name
            )
            if spec and not spec.wired:
                seen_unwired.add(f"{rec.strategy}.{rec.param_name}")

        assert len(seen_unwired) == 0, f"选中了 unwired 参数: {seen_unwired}"

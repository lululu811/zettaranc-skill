"""E2E test for self-optimizer V2 pipeline."""
import json
from pathlib import Path

import pytest

from modules.self_optimizer import SelfOptimizer
from modules.self_optimizer.backtest_scorer import BacktestScorer, ScoringResult, StockScore
from modules.self_optimizer.mutator import ParamMutator
from modules.self_optimizer.param_registry import get_defaults


class FixedScorer(BacktestScorer):
    """Mock scorer: 返回递增固定分数。"""
    def __init__(self, scores: list[float]):
        super().__init__(stock_pool=["FAKE"], days=30, max_stocks=1)
        self._scores = iter(scores)
        self._last = 80.0

    def score(self, **kwargs):
        self._last = next(self._scores)
        ss = StockScore("FAKE", 0.5, 0, 0.1, 0.2, 5, self._last)
        return ScoringResult(scores=[ss])

    def score_vs_baseline(self, params):
        m = self.score()
        b = self.score()
        return b, m


class FixedMutator(ParamMutator):
    """Mock mutator: 每次单步调整 j_threshold。"""
    def __init__(self):
        super().__init__(seed=0)

    def mutate(self, params: dict) -> dict:
        mutated = {k: dict(v) for k, v in params.items()}
        if "b1" in mutated and "j_threshold" in mutated["b1"]:
            mutated["b1"]["j_threshold"] = mutated["b1"]["j_threshold"] + 2
        return mutated


@pytest.mark.slow
def test_full_run_dry_run(tmp_path, monkeypatch):
    """端到端 dry-run: 跑 3 轮, 验证 tsv + drafts + log."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "optimization_drafts").mkdir()

    scorer = FixedScorer(scores=[82.0, 83.5, 84.0])
    mutator = FixedMutator()

    monkeypatch.setattr(SelfOptimizer, "phase1_baseline", lambda self: 80.0)

    opt = SelfOptimizer(rounds=3)
    result = opt.run(scorer=scorer, mutator=mutator)

    # 验证 results.tsv
    tsv = Path("logs/results.tsv")
    assert tsv.exists()
    lines = tsv.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 4
    assert lines[0].startswith("timestamp\tcommit\tskill")

    # 验证 drafts
    drafts = list(Path("optimization_drafts").glob("*.md"))
    assert len(drafts) == 3

    # 验证 log
    log = Path("logs/improvement_log.jsonl")
    assert log.exists()
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").strip().split("\n") if line]
    assert len(entries) == 3

    # 验证返回值
    assert result["rounds"] == 3
    assert "results_tsv" in result
    assert "drafts_dir" in result

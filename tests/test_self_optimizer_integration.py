"""集成测试: phase1 baseline + phase2 keep/revert + phase2 break."""
import pytest

from modules.self_optimizer.phase1_baseline import phase1_baseline
from modules.self_optimizer.phase2_hillclimb import (
    RoundResult,
    run_round,
    check_break_signal,
)


def test_phase1_baseline_with_mock_data(mock_monthly_reviews_with_poor_strategy):
    """mock 3 个月数据, baseline_score 必须在 [0, 100]."""
    score = phase1_baseline(target="trading", review_months=3)
    assert 0 <= score <= 100
    # 胜率 -30% 映射 0 分; 回撤 45% → (50-45)/40*30 = 3.75; 准确率 20% → 8
    # 真实分 = 0 + 3.75 + 8 = 11.75
    # LLM stub = 20
    # 总分 = 31.75 ± 5
    assert 25 <= score <= 40


def test_phase2_keep_revert_cycle(monkeypatch):
    """mock 一个会让 new_score < old_score 的提议 → revert."""

    # stub harness_updater
    from modules.self_optimizer import phase2_hillclimb

    def fake_propose(_old_score: float) -> dict:
        return {"proposed": [], "analysis": {"strategy_stats": []}}

    def fake_score(_proposed: dict, **_kwargs) -> float:
        return 50.0  # 总分低于 baseline 80

    monkeypatch.setattr(phase2_hillclimb, "_harness_propose", fake_propose)
    monkeypatch.setattr(phase2_hillclimb, "_score_proposal", fake_score)

    result = run_round(round_n=1, old_score=80.0, target="trading", history=[])
    assert result.status == "revert"
    assert result.new_score < result.old_score


def test_phase2_break_signal(monkeypatch):
    """连续 3 轮 delta<2 → break."""
    from modules.self_optimizer import phase2_hillclimb

    def fake_propose(_old_score: float) -> dict:
        return {"proposed": [], "analysis": {"strategy_stats": []}}

    def fake_score_close(_proposed: dict, **_kwargs) -> float:
        # 返回 old_score + 0.5 (连续 delta<2)
        return phase2_hillclimb._last_old + 0.5  # type: ignore[attr-defined]

    monkeypatch.setattr(phase2_hillclimb, "_harness_propose", fake_propose)
    monkeypatch.setattr(phase2_hillclimb, "_score_proposal", fake_score_close)
    monkeypatch.setattr(phase2_hillclimb, "_last_old", 80.0, raising=False)

    history = []
    for n in range(1, 4):
        old = 80.0 if n == 1 else history[-1].new_score
        phase2_hillclimb._last_old = old  # type: ignore[attr-defined]
        result = run_round(round_n=n, old_score=old, target="trading", history=history)
        history.append(result)
        if result.status == "break":
            break

    assert history[-1].status == "break"

"""Phase 2 hill-climbing: mutate → backtest → ratchet.

用 ParamMutator 变异参数 → BacktestScorer 跑回测评分 → ratchet keep/revert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from modules.self_optimizer.backtest_scorer import BacktestScorer, ScoringResult
from modules.self_optimizer.mutator import ParamMutator
from modules.self_optimizer.param_registry import get_defaults, set_active_params
from modules.self_optimizer.reflex_blacklist import check_all
from modules.self_optimizer.scorer import compute_total_score


@dataclass
class RoundResult:
    """单轮迭代结果."""

    round: int
    old_score: float
    new_score: float
    delta: float
    status: Literal["keep", "revert", "break"]
    violations: list[str]
    proposed_diff: str
    timestamp: str
    # 新增字段 for v2 管线
    mutated_params: dict = field(default_factory=dict)
    baseline_detail: ScoringResult = field(default_factory=ScoringResult)
    mutated_detail: ScoringResult = field(default_factory=ScoringResult)


def check_break_signal(history: list[RoundResult], threshold: float = 0.5) -> bool:
    """连续 2 轮 abs(delta) < threshold → break."""
    if len(history) < 2:
        return False
    return abs(history[-1].delta) < threshold and abs(history[-2].delta) < threshold


def run_round(
    round_n: int,
    old_score: float,
    target: str,
    history: list[RoundResult],
    *,
    scorer: BacktestScorer | None = None,
    mutator: ParamMutator | None = None,
    current_best_params: dict | None = None,
) -> RoundResult:
    """单轮迭代: mutate → blacklist → score → ratchet.

    如果提供了 scorer/mutator/current_best_params 则使用 v2 实参优化管线；
    否则向后兼容使用旧 HarnessUpdater(被废弃).
    """
    timestamp = datetime.now().isoformat()

    if mutator is not None and current_best_params is not None:
        return _run_v2_round(
            round_n, old_score, history, scorer, mutator,
            current_best_params, timestamp,
        )
    return _run_v1_legacy_round(round_n, old_score, target, history, timestamp)


def _run_v2_round(
    round_n: int,
    old_score: float,
    history: list,
    scorer: BacktestScorer | None,
    mutator: ParamMutator,
    current_best_params: dict,
    timestamp: str,
) -> RoundResult:
    """新管线：变异 → 黑名单 → 回测评分 → ratchet."""
    mutation, _ = mutator.mutate_one(current_best_params, strategy="jitter")
    proposed_diff = _format_mutation_diff(current_best_params, mutation)

    # 2. reflex_blacklist 硬阻断（对变异内容做安全检查）
    blacklist_ctx = {
        "proposed": list(mutation.keys()),
        "llm_input": {"contains_harness_output": False},
        "history": [{"status": h.status} for h in history],
        "scoring": {"real_weight": 0.6, "llm_weight": 0.4, "hard_rule_weight": 0.0},
    }
    violations = check_all(blacklist_ctx)
    if violations:
        return RoundResult(
            round=round_n,
            old_score=old_score,
            new_score=old_score,
            delta=0.0,
            status="revert",
            violations=[v.name for v in violations],
            proposed_diff=proposed_diff,
            timestamp=timestamp,
            mutated_params=mutation,
        )

    # 3. 回测评分（基线 + 变异并行）
    if scorer:
        baseline_detail, mutated_detail = scorer.score_vs_baseline(mutation)
        new_score = mutated_detail.composite_score
    else:
        # 降级：没有 scorer 时用旧评分系统（仅兼容）
        new_score = old_score

    # 4. ratchet
    delta = new_score - old_score
    status: Literal["keep", "revert"] = "keep" if delta > 0 else "revert"

    # 如果是 keep，更新 active params
    if status == "keep":
        set_active_params(mutation)

    result = RoundResult(
        round=round_n,
        old_score=old_score,
        new_score=new_score,
        delta=delta,
        status=status,
        violations=[],
        proposed_diff=proposed_diff,
        timestamp=timestamp,
        mutated_params=mutation,
        baseline_detail=baseline_detail,
        mutated_detail=mutated_detail,
    )

    # 5. break signal
    if check_break_signal(history + [result]):
        result.status = "break"

    return result


def _run_v1_legacy_round(
    round_n: int,
    old_score: float,
    target: str,
    history: list,
    timestamp: str,
) -> RoundResult:
    """V1 旧管线（HarnessUpdater，已废弃但保留向后兼容）。"""
    from modules.harness_updater import HarnessUpdater

    updater = HarnessUpdater()
    analysis = updater.analyze_strategy_performance()
    if not analysis.get("success"):
        proposal = {"proposed": [], "analysis": {"strategy_stats": []}}
    else:
        proposal = {
            "proposed": updater.generate_guardrails_update(analysis).get("updates", []),
            "analysis": analysis,
        }

    blacklist_ctx = {
        **proposal,
        "llm_input": {"contains_harness_output": False},
        "history": [{"status": h.status} for h in history],
        "scoring": {"real_weight": 0.6, "llm_weight": 0.4, "hard_rule_weight": 0.0},
    }
    violations = check_all(blacklist_ctx)
    if violations:
        return RoundResult(
            round=round_n,
            old_score=old_score,
            new_score=old_score,
            delta=0.0,
            status="revert",
            violations=[v.name for v in violations],
            proposed_diff=str(proposal.get("proposed", [])),
            timestamp=timestamp,
        )

    new_score, _ = compute_total_score("latest", {}, proposed=proposal)
    delta = new_score - old_score
    status: Literal["keep", "revert"] = "keep" if delta > 0 else "revert"

    result = RoundResult(
        round=round_n,
        old_score=old_score,
        new_score=new_score,
        delta=delta,
        status=status,
        violations=[],
        proposed_diff=str(proposal.get("proposed", [])),
        timestamp=timestamp,
    )

    if check_break_signal(history + [result]):
        result.status = "break"

    return result


def _format_mutation_diff(before: dict, after: dict) -> str:
    """生成人类可读的变异差异说明。"""
    lines = []
    for group, params in after.items():
        before_group = before.get(group, {})
        for key, value in params.items():
            old_val = before_group.get(key, "<absent>")
            if old_val != value:
                lines.append(f"  {group}.{key}: {old_val} → {value}")
    return "\n".join(lines) if lines else "  (无变化)"

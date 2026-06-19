"""Darwin Self-Optimizer for zettaranc-skill.

V2: 使用 ParamMutator + BacktestScorer 的实参优化管线；
V1 dry-run 向后保留作为回退.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查
    from modules.self_optimizer.backtest_scorer import BacktestScorer
    from modules.self_optimizer.mutator import ParamMutator
    from modules.self_optimizer.param_registry import get_defaults
    from modules.self_optimizer.phase1_baseline import phase1_baseline
    from modules.self_optimizer.phase2_hillclimb import (
        RoundResult,
        check_break_signal,
        run_round,
    )
    from modules.self_optimizer.phase3_report import (
        append_improvement_log,
        write_optimization_draft,
        write_results_tsv,
    )


class SelfOptimizer:
    """Self-optimizer orchestrator.

    Args:
        target: 优化目标 (trading | skill).
        rounds: 最大迭代轮数 (默认 3).
        mode: dry_run | auto_revert. V2 仅支持 dry_run.
        review_months: 基线评估用的最近月份数 (默认 3).
        stock_pool: 回测股票池 (None = 使用 BacktestScorer 默认池).
        backtest_days: 每只股票的回测天数.
    """

    def __init__(
        self,
        target: Literal["trading", "skill"] = "trading",
        rounds: int = 3,
        mode: Literal["dry_run", "auto_revert"] = "dry_run",
        review_months: int = 3,
        stock_pool: list[str] | None = None,
        backtest_days: int = 240,
    ) -> None:
        if target not in ("trading", "skill"):
            raise ValueError(f"仅支持 trading/skill, 收到: {target}")
        if mode not in ("dry_run", "auto_revert"):
            raise ValueError(f"仅支持 dry_run/auto_revert, 收到: {mode}")
        if mode == "auto_revert":
            raise NotImplementedError("V2 不支持 auto_revert")
        if rounds < 1 or rounds > 10:
            raise ValueError(f"rounds 必须在 [1, 10], 收到: {rounds}")

        self.target = target
        self.rounds = rounds
        self.mode = mode
        self.review_months = review_months
        self.stock_pool = stock_pool
        self.backtest_days = backtest_days
        self.log_dir = Path("logs")
        self.draft_dir = Path("optimization_drafts")
        self.results_tsv = self.log_dir / "results.tsv"

    def run(
        self,
        scorer: BacktestScorer | None = None,
        mutator: ParamMutator | None = None,
    ) -> dict:
        """Phase 1 → 2 → 3 完整跑一次.

        Args:
            scorer: 外部注入的 BacktestScorer（测试用）。None = 自动创建。
            mutator: 外部注入的 ParamMutator（测试用）。None = 自动创建。
        """
        from modules.self_optimizer.backtest_scorer import BacktestScorer
        from modules.self_optimizer.mutator import ParamMutator
        from modules.self_optimizer.param_registry import get_defaults
        from modules.self_optimizer.phase2_hillclimb import RoundResult, run_round

        if scorer is None:
            scorer = BacktestScorer(
                stock_pool=self.stock_pool,
                days=self.backtest_days,
                max_stocks=13,
            )
        if mutator is None:
            mutator = ParamMutator(seed=42)

        baseline = self.phase1_baseline()
        current_best_params = get_defaults()

        history: list[RoundResult] = []
        for n in range(1, self.rounds + 1):
            old_score = history[-1].new_score if history else baseline
            result = run_round(
                round_n=n,
                old_score=old_score,
                target=self.target,
                history=history,
                scorer=scorer,
                mutator=mutator,
                current_best_params=current_best_params,
            )
            history.append(result)

            if result.status == "keep" and result.delta > 0:
                current_best_params = result.mutated_params

            if result.status == "break":
                break

        return self.phase3_report(history)

    def phase1_baseline(self) -> float:
        from modules.self_optimizer.phase1_baseline import phase1_baseline

        return phase1_baseline(target=self.target, review_months=self.review_months)

    def phase3_report(self, history: list[RoundResult]) -> dict:
        from datetime import datetime

        from modules.self_optimizer.phase3_report import (
            append_improvement_log,
            write_optimization_draft,
            write_results_tsv,
        )

        run_id = datetime.now().strftime("%Y-%m-%d-r%H%M%S")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.draft_dir.mkdir(parents=True, exist_ok=True)
        tsv_path = write_results_tsv(self.results_tsv, run_id, history)
        for r in history:
            write_optimization_draft(self.draft_dir, run_id, r)
            append_improvement_log(self.log_dir, r)
        return {
            "run_id": run_id,
            "rounds": len(history),
            "keep": sum(1 for r in history if r.status == "keep"),
            "revert": sum(1 for r in history if r.status == "revert"),
            "break": sum(1 for r in history if r.status == "break"),
            "results_tsv": str(tsv_path),
            "drafts_dir": str(self.draft_dir),
        }


__all__ = [
    "SelfOptimizer",
]

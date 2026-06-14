"""
BacktestScorer — 基于真实回测的参数评分引擎

用变异后的参数集跑回测，返回 [0, 100] 综合分数。
通过 param_registry.using_params() 注入 override 参数，无需修改策略函数。

评分公式（向实盘看齐）：
  40% 胜率          win_rate ∈ [0, 1]    → [0, 40]
  25% 夏普比率      sharpe ∈ [0, 3]      → [0, 25]  clamp, 负数=0
  20% 总收益率      return ∈ [-10%, +50%] → [0, 20]  clamp
  15% 最大回撤      dd ∈ [0%, 40%]       → [15, 0]  线性反向
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from modules.backtest import backtest_strategy, BacktestResult
from modules.self_optimizer.param_registry import (
    get_defaults,
    using_params,
)

logger = logging.getLogger(__name__)


@dataclass
class StockScore:
    ts_code: str
    win_rate: float
    sharpe_ratio: float
    total_return: float
    max_drawdown: float
    total_trades: int
    score: float

    @property
    def has_trades(self) -> bool:
        return self.total_trades > 0


@dataclass
class ScoringResult:
    scores: list[StockScore] = field(default_factory=list)
    _composite: float = 0.0  # cached

    @property
    def composite_score(self) -> float:
        if self._composite != 0.0 and self.scores:
            return self._composite
        if not self.scores:
            return 0.0
        self._composite = sum(s.score for s in self.scores) / len(self.scores)
        return round(self._composite, 2)

    @property
    def stock_count(self) -> int:
        return len(self.scores)

    @property
    def traded_count(self) -> int:
        return sum(1 for s in self.scores if s.has_trades)

    def summary(self) -> str:
        lines = [
            f"ScoringResult: {self.composite_score}/100",
            f"  股票池: {self.stock_count} 只",
            f"  有交易: {self.traded_count} 只",
        ]
        if self.scores:
            best = max(self.scores, key=lambda s: s.score)
            worst = min(self.scores, key=lambda s: s.score)
            lines.append(f"  最佳: {best.ts_code} {best.score:.1f}")
            lines.append(f"  最差: {worst.ts_code} {worst.score:.1f}")
        return "\n".join(lines)


class BacktestScorer:
    """参数评分器：跑回测 → 算分数。

    Args:
        stock_pool: 回测股票池（代码列表）。None = 自动用默认池。
        days: 每只股票的回测天数。
        seed: 随机种子（用于从大池子抽样）。
        max_stocks: 最多跑多少只（None = 全跑）。
    """

    # 默认股票池：有完整数据的历史回测票
    DEFAULT_POOL = [
        "000001.SZ", "000002.SZ", "000004.SZ", "000005.SZ",
        "000006.SZ", "000007.SZ", "000008.SZ", "000009.SZ",
        "000010.SZ", "000011.SZ", "000012.SZ", "000014.SZ",
        "600487.SH",
    ]

    def __init__(
        self,
        stock_pool: list[str] | None = None,
        days: int = 240,
        seed: int | None = None,
        max_stocks: int | None = None,
    ):
        self._pool = stock_pool or list(self.DEFAULT_POOL)
        self._days = days
        self._rng = random.Random(seed) if seed else None
        self._max_stocks = min(max_stocks, len(self._pool)) if max_stocks else len(self._pool)

    def score(
        self,
        params: dict[str, dict[str, Any]] | None = None,
    ) -> ScoringResult:
        """用给定参数跑回测，返回综合评分。

        如果 params=None，使用 registry 默认值（即出厂基线）。
        """
        pool = self._select_pool()
        all_scores: list[StockScore] = []

        for ts_code in pool:
            score = self._score_single(ts_code, params)
            all_scores.append(score)

        return ScoringResult(scores=all_scores)

    def score_vs_baseline(
        self,
        params: dict[str, dict[str, Any]],
    ) -> tuple[ScoringResult, ScoringResult]:
        """同时跑基线 + 变异参数回测，返回 (baseline, mutated)。"""
        baseline = self.score(params=None)
        mutated = self.score(params=params)
        return baseline, mutated

    def _score_single(
        self,
        ts_code: str,
        params: dict[str, dict[str, Any]] | None,
    ) -> StockScore:
        """跑单只股票的回测，返回 StockScore。"""
        try:
            if params:
                with using_params(params):
                    result = backtest_strategy(ts_code, days=self._days)
            else:
                result = backtest_strategy(ts_code, days=self._days)
        except Exception as e:
            logger.warning("回测 %s 失败: %s", ts_code, e)
            return StockScore(
                ts_code=ts_code, win_rate=0, sharpe_ratio=0,
                total_return=0, max_drawdown=0, total_trades=0, score=0,
            )

        score = self._compute_single_score(result)
        return StockScore(
            ts_code=ts_code,
            win_rate=result.win_rate,
            sharpe_ratio=result.sharpe_ratio if hasattr(result, 'sharpe_ratio') else 0,
            total_return=result.total_return,
            max_drawdown=result.max_drawdown,
            total_trades=result.total_trades,
            score=score,
        )

    def _compute_single_score(self, r: BacktestResult) -> float:
        """单只股票评分 [0, 100]。

        使用 BacktestResult 可用字段：
          40% 胜率 + 20% 盈亏比(profit_factor) + 25% 平均收益 + 15% 回撤
        """
        if r.total_trades == 0:
            return 0.0

        s_win = min(40.0, r.win_rate * 40.0)
        raw_pf = r.profit_factor if r.profit_factor != float("inf") else 10.0
        s_pf = max(0, min(20.0, raw_pf / 10.0 * 20.0))
        raw_ret = r.avg_return if hasattr(r, 'avg_return') else 0
        s_ret = max(0, min(25.0, (raw_ret + 0.10) / 0.30 * 25.0))

        # 15% 最大回撤（clamp [0%, 40%]，越小越好）
        raw_dd = r.max_drawdown if hasattr(r, 'max_drawdown') else 0
        s_dd = max(0, min(15.0, (0.40 - raw_dd) / 0.40 * 15.0))

        return round(s_win + s_pf + s_ret + s_dd, 2)

    def _select_pool(self) -> list[str]:
        """从股票池选股。如果设了 max_stocks 则随机抽样。"""
        if self._max_stocks >= len(self._pool):
            return list(self._pool)
        chosen = self._pool[:]
        if self._rng:
            self._rng.shuffle(chosen)
        else:
            import random as _r
            _r.shuffle(chosen)
        return chosen[:self._max_stocks]


def demo() -> None:
    """演示：跑一次基线评分 + 一次变异评分。"""
    scorer = BacktestScorer(max_stocks=5, days=120)

    print("=== 基线评分（出厂默认参数）===")
    baseline = scorer.score()
    print(baseline.summary())

    print("\n=== 变异评分（降低 B1 J threshold 到 -15）===")
    mutated_params = get_defaults()
    mutated_params["b1"]["j_threshold"] = -15
    mutated = scorer.score(params=mutated_params)
    print(mutated.summary())

    if baseline.composite_score > 0:
        delta = mutated.composite_score - baseline.composite_score
        print(f"\nΔ = {delta:+.2f} 分 ({'↑' if delta > 0 else '↓' if delta < 0 else '='})")


if __name__ == "__main__":
    demo()

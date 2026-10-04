# 少妇战法 v1.0 验收参数寻优（v3.7.1）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把少妇战法 v1.0 验收门（5 项硬指标）的 passed_count 从当前 1/5 推到 ≥4/5；用 V2 达尔文式 5 轮 hill-climb 在 100 股 × 250 天 + WF 上寻优，写回 `param_registry:shaofu_v1`，最后用 v3.7.0 `zt verify v1.0` 验收。

**Architecture:** 新增 `V10VerifyScorer`（封装 `verify_v10_pipeline` 作 fitness）+ 独立 `scripts/optimize_for_v10_verify.py` 跑 hill-climb，写回 `param_registry:shaofu_v1`。不重写 SelfOptimizer；用现有 `LoopConfig` + `verify/walk_forward/gates`。

**Tech Stack:** Python 3.14 + 现有 `modules/verify/` + `modules/loop_engine.LoopConfig` + `modules/self_optimizer/param_registry` (Task 7 已铺好的 `from_registry` / `write_optimization_to_registry`)。

---

## Global Constraints

1. 五项硬指标阈值**不动**：Sharpe≥0.5 / Calmar≥0.5 / WinRate≥40% / MaxDD≤25% / OOS/IS≥0.6
2. 寻优起点 = `LoopConfig()` 默认值（用户已确认）
3. 寻优字段（7 个）= `j_threshold` / `stop_loss_pct` / `vol_shrink_threshold` / `bbi_break_days` / `min_holding_days` / `lu_half` / `position_pct`
4. 必须启用 Walk-forward（OOS/IS 门才能产出有意义信号）
5. 真实数据优先：不写 mock，对接 Tushare
6. 不修改 `modules/loop_engine.py` / `modules/backtest_six_step.py` / `modules/verify/{pipeline,gates,walk_forward,registry_writer,report,cli}.py`
7. 全套测试基线 ≥ 954 passed / 12 skipped（v3.7.0 终态），允许向上增长，不允许下跌
8. SKILL.md 不动（corpus 12/12 强约束）
9. ruff 配置：line-length=120, target py310, `--select=F,E,W,UP --ignore=E501,F401,F403`
10. 项目代码风格：4-space 缩进 / UTF-8 / LF / 中文 docstring / 类型注解

---

## Spec 一致性检查

| spec 段 | 对应 task |
|---|---|
| M1 Scorer 类 | Task 1-2 |
| M2 寻优脚本 | Task 3 |
| M3 真实数据跑批 | Task 4 |
| M4 验收 + v3.7.1 tag | Task 5 |
| 错误处理矩阵（R1/R3 等）| Task 3-5 inline |
| 测试策略（3 个 scorer 用例）| Task 2 |

---

## Task 1: V10VerifyScorer scaffold + dataclass（骨架先于测试）

**Files:**
- Create: `modules/verify/scorer.py`
- Modify: `modules/verify/__init__.py`

**Interfaces:**
- Produces: `V10VerifyScorer` 类（最终 Task 2 补全方法），先放 dataclass + `__init__`
- Consumes: 无

**为什么先骨架**：让模块对外暴露类型，便于 Task 2 写测试时 import 不报 ImportError。

- [ ] **Step 1: 创建 scorer.py 骨架**

文件：`modules/verify/scorer.py`：

```python
"""v1.0 验收适配的达尔文可调评分器

封装 verify_v10_pipeline 作为 fitness，方便 V2 hill-climb 寻优。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class V10ScoreResult:
    """单次评分的结果"""
    passed_count: int = 0
    total_count: int = 5
    sharpe: float = 0.0
    fit: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class V10VerifyScorer:
    """达尔文友好的 v1.0 验收适配器

    接口形态与 modules.self_optimizer.BacktestScorer 对齐：
      - 构造时接收 stock_pool / days / wf 等配置
      - score(params) 返回 V10ScoreResult（fit 为爬山适应度）
    """

    def __init__(
        self,
        stock_pool: list[str],
        days: int = 250,
        walk_forward: bool = True,
        wf_train_days: int = 120,
        wf_test_days: int = 60,
    ):
        self.stock_pool = stock_pool
        self.days = days
        self.walk_forward = walk_forward
        self.wf_train_days = wf_train_days
        self.wf_test_days = wf_test_days
```

- [ ] **Step 2: 在 __init__.py 追加导出**

修改 `modules/verify/__init__.py`，**保留已有行**，在 `__all__` 列表**末尾**追加 `V10ScoreResult` 和 `V10VerifyScorer`：

```python
"""v1.0 验收工程化子包"""
from .pipeline import (
    AggregateMetrics,
    GateResult,
    StockResult,
    VerifyResult,
    verify_v10_pipeline,
)
from .scorer import V10ScoreResult, V10VerifyScorer

__all__ = [
    "AggregateMetrics",
    "GateResult",
    "StockResult",
    "VerifyResult",
    "verify_v10_pipeline",
    "V10ScoreResult",
    "V10VerifyScorer",
]
```

- [ ] **Step 3: 跑现有 v3.7.0 测试，确认导入不破坏**

Run: `python3 -m pytest tests/ -v 2>&1 | tail -5`
Expected: 仍 954+ passed

- [ ] **Step 4: Commit**

```bash
git add modules/verify/scorer.py modules/verify/__init__.py
git commit -m "feat(verify): V10VerifyScorer 骨架（dataclass + __init__）"
```

---

## Task 2: V10VerifyScorer.score() + 单元测试

**Files:**
- Modify: `modules/verify/scorer.py`
- Create: `tests/test_verify_scorer.py`

**Interfaces:**
- Consumes: `verify_v10_pipeline`（Task 1-6 已铺好）/ `VerifyResult.gates`
- Produces: `V10VerifyScorer.score(params: dict) -> V10ScoreResult`，params 是 LoopConfig 的 7 字段子集

- [ ] **Step 1: 写失败的测试**

文件：`tests/test_verify_scorer.py`：

```python
"""V10VerifyScorer 单元测试"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from modules.verify.pipeline import GateResult, VerifyResult, AggregateMetrics
from modules.verify.scorer import V10VerifyScorer, V10ScoreResult


def _make_passed_gates() -> dict[str, GateResult]:
    """5 个 gate 全通过"""
    return {
        "sharpe":       GateResult(name="sharpe",       value=1.2,  threshold=0.5, passed=True),
        "calmar":       GateResult(name="calmar",       value=0.8,  threshold=0.5, passed=True),
        "win_rate":     GateResult(name="win_rate",     value=0.55, threshold=0.4, passed=True),
        "max_drawdown": GateResult(name="max_drawdown", value=0.15, threshold=0.25, passed=True),
        "oos_is_ratio": GateResult(name="oos_is_ratio", value=0.7,  threshold=0.6, passed=True),
    }


def _make_failed_gates() -> dict[str, GateResult]:
    """5 个 gate 全失败"""
    return {
        "sharpe":       GateResult(name="sharpe",       value=-0.5, threshold=0.5, passed=False),
        "calmar":       GateResult(name="calmar",       value=-0.2, threshold=0.5, passed=False),
        "win_rate":     GateResult(name="win_rate",     value=0.2,  threshold=0.4, passed=False),
        "max_drawdown": GateResult(name="max_drawdown", value=0.4,  threshold=0.25, passed=False),
        "oos_is_ratio": GateResult(name="oos_is_ratio", value=0.1,  threshold=0.6, passed=False),
    }


def test_score_with_all_gates_passed_returns_high_fit():
    """5/5 通过 → fit 应当高（passed_count=5 + 0.1*sharpe）"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    mock_result = MagicMock(spec=VerifyResult)
    mock_result.gates = _make_passed_gates()

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result):
        out = scorer.score({"j_threshold": 8})

    assert isinstance(out, V10ScoreResult)
    assert out.passed_count == 5
    assert out.total_count == 5
    # fit = 5 + 0.1 * 1.2 = 5.12
    assert abs(out.fit - 5.12) < 1e-6
    assert out.error == ""


def test_score_with_all_gates_failed_returns_low_fit():
    """0/5 通过 → fit 应当低（0 + 0.1 * (-0.5) = -0.05，clamp 到 0）"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    mock_result = MagicMock(spec=VerifyResult)
    mock_result.gates = _make_failed_gates()

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result):
        out = scorer.score({"stop_loss_pct": -0.07})

    assert out.passed_count == 0
    # fit = max(0, 0 + 0.1 * sharpe_negative)
    assert out.fit >= 0.0
    assert out.error == ""


def test_score_handles_pipeline_exception_without_crashing():
    """verify_v10_pipeline 抛异常 → 不传播，返回 fit=0+error"""
    pool = ["999999.SH"]  # 不存在
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    with patch(
        "modules.verify.scorer.verify_v10_pipeline",
        side_effect=RuntimeError("Tushare rate limit"),
    ):
        out = scorer.score({"j_threshold": 12})

    assert out.passed_count == 0
    assert "Tushare rate limit" in out.error
    assert out.fit == 0.0


def test_score_emits_partial_pass_count():
    """1/5 通过 → passed_count=1, sharpe 为负数, fit=正值（passed=1 主导）"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    gates = _make_passed_gates()
    gates["sharpe"].passed = False
    gates["sharpe"].value = -0.3
    gates["calmar"].passed = False
    gates["calmar"].value = -0.1
    gates["win_rate"].passed = False
    gates["win_rate"].value = 0.2
    gates["oos_is_ratio"].passed = False
    gates["oos_is_ratio"].value = 0.1
    # 只留 max_drawdown 通过

    mock_result = MagicMock(spec=VerifyResult)
    mock_result.gates = gates

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result):
        out = scorer.score({"j_threshold": 12})

    assert out.passed_count == 1
    assert out.total_count == 5
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `python3 -m pytest tests/test_verify_scorer.py -v`
Expected: 4 个测试都 FAIL（`scorer()` 不存在）

- [ ] **Step 3: 实现 score() 方法**

替换 `modules/verify/scorer.py` 全文：

```python
"""v1.0 验收适配的达尔文可调评分器

封装 verify_v10_pipeline 作为 fitness，方便 V2 hill-climb 寻优。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from modules.loop_engine import LoopConfig

logger = logging.getLogger(__name__)

# LoopConfig 的可调字段（与 v3.7.0 验收一致）
LOOP_CONFIG_FIELDS = (
    "j_threshold",
    "stop_loss_pct",
    "vol_shrink_threshold",
    "bbi_break_days",
    "min_holding_days",
    "lu_half",
    "position_pct",
)


@dataclass
class V10ScoreResult:
    """单次评分的结果"""
    passed_count: int = 0
    total_count: int = 5
    sharpe: float = 0.0
    fit: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class V10VerifyScorer:
    """达尔文友好的 v1.0 验收适配器

    接口形态与 modules.self_optimizer.BacktestScorer 对齐：
      - 构造时接收 stock_pool / days / wf 等配置
      - score(params) 返回 V10ScoreResult（fit 为爬山适应度）
    """

    def __init__(
        self,
        stock_pool: list[str],
        days: int = 250,
        walk_forward: bool = True,
        wf_train_days: int = 120,
        wf_test_days: int = 60,
    ):
        self.stock_pool = stock_pool
        self.days = days
        self.walk_forward = walk_forward
        self.wf_train_days = wf_train_days
        self.wf_test_days = wf_test_days

    def score(self, params: dict[str, Any]) -> V10ScoreResult:
        """用 params（LoopConfig 字段子集）跑 verify_v10_pipeline，返回 V10ScoreResult。

        适应度公式：fit = passed_count + max(0, 0.1 * sharpe)
          - passed_count ∈ [0, 5] 是核心目标
          - sharpe 小幅保序（同等 passed_count 下 sharpe 高的赢）

        任何 verify 异常都被捕获，返回 fit=0 + error 文本，不阻断寻优。
        """
        # 局部 import 避免循环
        from modules.verify.pipeline import verify_v10_pipeline

        try:
            config = LoopConfig(**{k: v for k, v in params.items() if k in LOOP_CONFIG_FIELDS})
            result = verify_v10_pipeline(
                ts_codes=self.stock_pool,
                days=self.days,
                config=config,
                walk_forward=self.walk_forward,
                wf_train_days=self.wf_train_days,
                wf_test_days=self.wf_test_days,
            )
        except Exception as e:  # noqa: BLE001 - 单次评分失败不应中断爬山
            logger.warning("V10VerifyScorer 评分异常: %s", e)
            return V10ScoreResult(
                passed_count=0,
                total_count=5,
                fit=0.0,
                params=dict(params),
                error=f"{type(e).__name__}: {e!s:.80}",
            )

        gates = result.gates or {}
        passed_count = sum(1 for g in gates.values() if g.passed)
        total_count = len(gates)
        sharpe_gate = gates.get("sharpe")
        sharpe_value = sharpe_gate.value if sharpe_gate else 0.0
        fit = passed_count + max(0.0, 0.1 * sharpe_value)

        return V10ScoreResult(
            passed_count=passed_count,
            total_count=total_count,
            sharpe=sharpe_value,
            fit=fit,
            params=dict(params),
        )
```

- [ ] **Step 4: 跑测试确认 PASS**

Run: `python3 -m pytest tests/test_verify_scorer.py -v`
Expected: 4 passed

- [ ] **Step 5: 跑全套确认 958+ passed 零回归**

Run: `python3 -m pytest tests/ -v 2>&1 | tail -3`
Expected: 958 passed (954 + 4 new), 12 skipped

- [ ] **Step 6: lint**

Run: `ruff check modules/verify/scorer.py tests/test_verify_scorer.py --select=F,E,W,UP --ignore=E501,F401,F403`
Expected: 零错误

- [ ] **Step 7: Commit**

```bash
git add modules/verify/scorer.py tests/test_verify_scorer.py
git commit -m "feat(verify): V10VerifyScorer.score() 接入 verify_v10_pipeline"
```

---

## Task 3: scripts/optimize_for_v10_verify.py hill-climb 寻优

**Files:**
- Create: `scripts/optimize_for_v10_verify.py`

**Interfaces:**
- Consumes: `V10VerifyScorer` (Task 2) + `LoopConfig` (v3.7.0) + `param_registry.write_optimization_to_registry` (Task 7)
- Produces: `optimization_drafts/v10_verify_<timestamp>.json`（中间产物）+ `param_registry:shaofu_v1`（最终）

**为什么独立脚本而非复用 SelfOptimizer**：现有 `SelfOptimizer` 用 `params: dict[str, dict[str, Any]]` 格式（嵌套 strategy_name），而 LoopConfig 的 7 字段是 flat dict。独立实现 80 行比对接复杂得多。

- [ ] **Step 1: 创建脚本**

文件：`scripts/optimize_for_v10_verify.py`：

```python
#!/usr/bin/env python3
"""少妇战法 v1.0 验收参数寻优（v3.7.1）

用 5 轮 hill-climb 在 100 股 × 240 天 + Walk-forward 上跑
V10VerifyScorer，按 passed_count + 0.1*sharpe 适应度爬山，
最佳参数集写回 param_registry:shaofu_v1。

用法：
  python -m scripts.optimize_for_v10_verify --rounds 5 --stocks 100
  python -m scripts.optimize_for_v10_verify --smoke   # 1 round × 5 stocks
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# 让 `python -m scripts.optimize_for_v10_verify` 能跑（项目根目录加 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.database import get_all_stock_codes  # noqa: E402
from modules.loop_engine import LoopConfig  # noqa: E402
from modules.self_optimizer.param_registry import (  # noqa: E402
    write_optimization_to_registry,
)
from modules.verify.scorer import V10VerifyScorer, V10ScoreResult, LOOP_CONFIG_FIELDS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# LoopConfig 字段的 (min, max, step) 元组（用于爬山边界）
PARAM_SPACE = {
    "j_threshold":         (3,    20,   1),
    "stop_loss_pct":      (-0.10, -0.01, 0.01),
    "vol_shrink_threshold": (0.5,  1.0,  0.1),
    "bbi_break_days":      (1,     5,    1),
    "min_holding_days":    (2,     7,    1),
    "lu_half":             (0,     1,    1),   # bool 当 int 用
    "position_pct":        (0.10,  0.50, 0.05),
}


def _clip(name: str, value: float) -> int | float | bool:
    lo, hi, step = PARAM_SPACE[name]
    v = max(lo, min(hi, value))
    # 离散化到 step
    v = round((v - lo) / step) * step + lo
    v = max(lo, min(hi, v))
    if name in ("lu_half",):
        return bool(int(v))
    return v


def _mutate(base: dict, rng: random.Random, n_mutations: int = 2) -> dict:
    """随机挑选 n_mutations 个字段微扰"""
    new = dict(base)
    keys = list(PARAM_SPACE.keys())
    picked = rng.sample(keys, k=min(n_mutations, len(keys)))
    for k in picked:
        lo, hi, step = PARAM_SPACE[k]
        # 在 ±2 个 step 内扰动
        delta = rng.choice([-2, -1, 1, 2]) * step
        new[k] = _clip(k, new.get(k, lo) + delta)
    return new


def _load_pool(stocks_arg: int | None) -> list[str]:
    """加载股票池：默认从 stock_basic 取前 N 只"""
    limit = stocks_arg or 100
    return get_all_stock_codes(limit=limit)


def run_hillclimb(
    scorer: V10VerifyScorer,
    initial: dict,
    rounds: int,
    rng: random.Random,
) -> tuple[dict, V10ScoreResult, list[dict]]:
    """返回 (best_params, best_score, history)"""
    current = dict(initial)
    current_result = scorer.score(current)
    history: list[dict] = [{
        "round": 0,
        "kind": "baseline",
        "params": current,
        "fit": current_result.fit,
        "passed_count": current_result.passed_count,
    }]
    logger.info(
        "基线 fit=%.3f passed=%d/%d",
        current_result.fit,
        current_result.passed_count,
        current_result.total_count,
    )

    best = current
    best_result = current_result
    no_improve = 0

    for r in range(1, rounds + 1):
        candidate = _mutate(current, rng)
        candidate_result = scorer.score(candidate)
        history.append({
            "round": r,
            "kind": "candidate",
            "params": candidate,
            "fit": candidate_result.fit,
            "passed_count": candidate_result.passed_count,
            "error": candidate_result.error,
        })

        if candidate_result.fit > current_result.fit:
            current = candidate
            current_result = candidate_result
            no_improve = 0
            status = "keep"
        else:
            no_improve += 1
            status = "revert"

        if candidate_result.fit > best_result.fit:
            best = candidate
            best_result = candidate_result

        logger.info(
            "round %d: %s fit=%.3f passed=%d/%d (best so far fit=%.3f passed=%d/%d)",
            r, status, candidate_result.fit, candidate_result.passed_count,
            candidate_result.total_count, best_result.fit, best_result.passed_count,
            best_result.total_count,
        )

        if no_improve >= 3:  # 连续 3 轮无 improvement 视为收敛
            logger.info("收敛于 round %d", r)
            break

    return best, best_result, history


def main() -> int:
    parser = argparse.ArgumentParser(description="v1.0 验收参数寻优")
    parser.add_argument("--rounds", type=int, default=5, help="爬山轮数（默认 5）")
    parser.add_argument("--stocks", type=int, default=100, help="股票池大小（默认 100）")
    parser.add_argument("--days", type=int, default=240, help="回测天数（默认 240）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--smoke", action="store_true", help="冒烟模式：1 轮 × 5 股")
    parser.add_argument("--extras", type=int, default=0, help="额外补充轮数")
    args = parser.parse_args()

    if args.smoke:
        args.rounds = 1
        args.stocks = 5

    rng = random.Random(args.seed)

    # 1. 加载股票池
    pool = _load_pool(args.stocks)
    if not pool:
        logger.error("无法加载股票池（数据库可能未初始化）")
        return 1
    logger.info("股票池: %d 只", len(pool))

    # 2. 构造 scorer
    scorer = V10VerifyScorer(
        stock_pool=pool,
        days=args.days,
        walk_forward=True,
        wf_train_days=120,
        wf_test_days=60,
    )

    # 3. 基线 = LoopConfig() 默认值
    baseline_params = {
        f: getattr(LoopConfig(), f)
        for f in LOOP_CONFIG_FIELDS
    }
    # 修正 lu_half 是 bool
    baseline_params["lu_half"] = bool(baseline_params["lu_half"])

    # 4. 爬山
    total_rounds = args.rounds + args.extras
    t0 = time.time()
    best_params, best_result, history = run_hillclimb(
        scorer=scorer,
        initial=baseline_params,
        rounds=total_rounds,
        rng=rng,
    )
    elapsed = time.time() - t0

    # 5. 落盘中间产物
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    draft_dir = Path("optimization_drafts")
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"v10_verify_{run_id}.json"
    draft_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "elapsed_sec": elapsed,
                "rounds": total_rounds,
                "stocks": len(pool),
                "baseline_params": baseline_params,
                "best_params": best_params,
                "best_fit": best_result.fit,
                "best_passed_count": best_result.passed_count,
                "best_total_count": best_result.total_count,
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("中间产物：%s (%.1f s)", draft_path, elapsed)

    # 6. 写回 param_registry:shaofu_v1
    write_optimization_to_registry(
        optimization_results={"best_params": best_params},
        strategy_name="shaofu_v1",
    )
    logger.info(
        "已写回 param_registry:shaofu_v1 → fit=%.3f passed=%d/%d",
        best_result.fit,
        best_result.passed_count,
        best_result.total_count,
    )

    print(f"PASSED: {best_result.passed_count}/{best_result.total_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 跑冒烟命令**

Run: `set -a && source .env && set +a && python3 -m scripts.optimize_for_v10_verify --smoke 2>&1 | tail -10`
Expected: 
- 基线 log（fit/passed）
- 1 轮候选 log
- 中间产物路径
- "已写回 param_registry:shaofu_v1"
- `PASSED: X/5`（X 可以是 0-5，冒烟模式不要求高）

- [ ] **Step 3: 验证 LoopConfig.from_registry 能拿到**

Run: `python3 -c "from modules.loop_engine import LoopConfig; c = LoopConfig.from_registry('shaofu_v1'); print('OK' if c else 'NONE'); print(repr(c)[:200] if c else '')"`
Expected: `OK` 然后打印 LoopConfig(...) 含实际数值

- [ ] **Step 4: lint**

Run: `ruff check scripts/optimize_for_v10_verify.py --select=F,E,W,UP --ignore=E501,F401,F403`
Expected: 零错误

- [ ] **Step 5: Commit**

```bash
git add scripts/optimize_for_v10_verify.py
git commit -m "feat(verify): scripts/optimize_for_v10_verify.py 5 轮 hill-climb 寻优"
```

---

## Task 4: 真实数据全量跑批（5 轮 × 100 股）

**Files:** 无（仅跑命令）

**Interfaces:** 跑 Task 3 的脚本

- [ ] **Step 1: 正式跑**

Run: `set -a && source .env && set +a && time python3 -m scripts.optimize_for_v10_verify --rounds 5 --stocks 100 --seed 42 2>&1 | tee /tmp/v10_optimize.log`
Expected:
- exit 0
- 日志含 5 轮收敛过程
- 含 "已写回 param_registry:shaofu_v1" 行
- 末尾 `PASSED: X/5`（**目标 ≥ 4**，否则下一步走 `--extras`）
- Wall-clock ≤ 3 小时（实估 1-1.5h）

- [ ] **Step 2: 若 PASSED < 4，跑 --extras**

Run: `set -a && source .env && set +a && time python3 -m scripts.optimize_for_v10_verify --rounds 5 --stocks 100 --seed 42 --extras 3 2>&1 | tee /tmp/v10_optimize_extras.log`
Expected: 自动用上次 best_params 作起点（**注意**：当前实现 baseline_params 永远用 `LoopConfig()` 默认值，extras 不持久化 — **接受这个限制**，因为重启脚本的"warm start"逻辑会增加复杂度，超出 v3.7.1 范围）

实际操作：`--extras` 会**重新从 LoopConfig 默认值开始跑额外 3 轮**。如果首次跑出 ≥ 4，直接跳到 Task 5；如果首次跑出 < 4，则必须接受"重新启动"的现实（bug 不掩盖）— 在 commit message 里说明，重新跑的 draft 编号会不同。

- [ ] **Step 3: 验证 registry 已写**

Run: `python3 -c "
from modules.loop_engine import LoopConfig
c = LoopConfig.from_registry('shaofu_v1')
print('Loaded from registry:', c is not None)
print('j_threshold:', c.j_threshold)
print('stop_loss_pct:', c.stop_loss_pct)
print('position_pct:', c.position_pct)
"`
Expected: 
- `Loaded from registry: True`
- 打印的字段值与 draft JSON 中的 `best_params` 一致

- [ ] **Step 4: 记录 outcomes（不 commit，仅记入笔记）**

把 Task 4 实际跑出的数字写进笔记文件 `/Users/chenlei/005_skill/skills/zettaranc-skill/.superpowers/sdd/task-4-run-log.md`（带时间戳，便于回溯）。**不 commit**（属于 scratch 文件）。

---

## Task 5: 验收 + v3.7.1 文档同步 + tag

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: 用 v3.7.0 入口跑一次最终验收**

Run: `set -a && source .env && set +a && time python3 -m modules.cli verify v1.0 --limit 50 --days 250 --walk-forward 2>&1 | tee /tmp/v10_verify_final.log`
Expected:
- exit 0
- 末尾打印 `少妇战法 v1.0 验收：X/5 通过`，**X ≥ 4**（硬门）

- [ ] **Step 2: 读最新 JSON 报告**

Run: `LATEST=$(ls -t data/reports/verify_v10_*.json | head -1); echo $LATEST; python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
print('passed_count:', d['passed_count'], '/', d['total_count'])
print('summary:', d.get('summary'))
print('gates:')
for k, g in d['gates'].items():
    mark = '✅' if g['passed'] else '❌'
    print(f'  {mark} {k}: value={g[\"value\"]:.4f}, threshold={g[\"threshold\"]}')
" "$LATEST"`
Expected: 5 个 gate 详情，至少 4 个 ✅

- [ ] **Step 3: 跑全套测试确认 958+ passed 零回归**

Run: `python3 -m pytest tests/ -v 2>&1 | tail -3`
Expected: 958 passed, 12 skipped（**不得低于 958**）

- [ ] **Step 4: 跑 lint + quality gate**

```bash
ruff check modules/verify tests/test_verify_* scripts/optimize_for_v10_verify.py --select=F,E,W,UP --ignore=E501,F401,F403
python3 corpus/quality_check.py SKILL.md
```
Expected:
- lint: 零错误
- quality gate: 12/12 通过

- [ ] **Step 5: 文档同步**

修改 `pyproject.toml`：找到 `version = "3.7.0"`，改为：
```toml
version = "3.7.1"
```

修改 `docs/CHANGELOG.md`：在 `## v3.7.0 (2026-07-10)` 段**之前**插入：
```markdown
## v3.7.1 (2026-07-11)

### 少妇战法 v1.0 验收参数寻优

> **「v3.7.1：少妇战法 v1.0 验收参数寻优 —— 5 轮 hill-climb × 100 股，把 passed_count 从 1/5 推到 ≥4/5。」**

#### 新增

- `modules/verify/scorer.py` — `V10VerifyScorer`（达尔文友好适配）
- `scripts/optimize_for_v10_verify.py` — 5 轮 hill-climb CLI

#### 测试

- 新增 `tests/test_verify_scorer.py`（4 用例）
- 零回归：954 → 958 passed（+ 4）

#### 验收门（实测）

| 指标 | v3.7.0 默认 | v3.7.1 寻优后 |
|---|---|---|
| passed_count | 1 / 5 | **≥ 4 / 5** |
```

修改 `README.md`：找到「v3.7.0」行**之后**追加：
```markdown
| **v3.7.1** | 少妇战法 v1.0 验收参数寻优（passed_count 从 1/5 → ≥4/5） | ✅ 已完成 |
```

并在 README 的「## v3.7.0 验收工程化」段之后追加：
```markdown
## v3.7.1 寻优重跑

```bash
python3 -m scripts.optimize_for_v10_verify --rounds 5 --stocks 100
```

输出：
- `optimization_drafts/v10_verify_<timestamp>.json` — 中间产物
- 自动写回 `param_registry:shaofu_v1`
```

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml docs/CHANGELOG.md README.md
git commit -m "docs: v3.7.1 文档同步 (CHANGELOG + README + 版本号)"
```

- [ ] **Step 7: 打 v3.7.1 tag 并推送**

```bash
git tag -a v3.7.1 -m "v3.7.1: 少妇战法 v1.0 验收参数寻优（passed_count 1/5 → X/5）"
git push origin v3.7.1
git push origin main
```
Expected:
- tag 创建成功
- 推送成功
- 两个 `* [new tag]` 或 `main -> main` 行

- [ ] **Step 8: 写最终报告**

Write: `/Users/chenlei/005_skill/skills/zettaranc-skill/.superpowers/sdd/task-5-report.md`
- 5 个任务（Task 1-5）全过的 commits（应该有 6-7 个 commit）
- 最终 passed_count 数字
- v3.7.1 tag URL
- 后续优化方向（如有）

**不 commit**（scratch 文件）。

---

## Self-Review

**1. Spec 覆盖**：扫 spec 5 节（架构 / 组件 / Milestones / 错误处理 / 测试策略）— 5 个 task 对应 M1-M4 + 文档同步。无遗漏。

**2. 占位符扫描**：grep "TODO|TBD|fill in later" — 5 个 task 中无；Step 4.2 注脚明确说明 `--extras` 不持久化的已知限制（**不掩盖 bug**）。

**3. 类型一致性**：
- `V10ScoreResult`（Task 1 定义）→ Task 2 测试引用 ✓
- `V10VerifyScorer.score(params)`（Task 2）→ Task 3 调用 ✓
- `LOOP_CONFIG_FIELDS`（Task 2）→ Task 3 引用 ✓
- `write_optimization_to_registry`（v3.7.0 Task 7）→ Task 3 调用 ✓
- `get_all_stock_codes`（v3.7.1 Task 11.1 修复）→ Task 3 调用 ✓

无类型不一致。

**4. 文件路径**：
- `modules/verify/scorer.py` ✓
- `tests/test_verify_scorer.py` ✓
- `scripts/optimize_for_v10_verify.py` ✓
- `modules/verify/__init__.py` ✓
- `pyproject.toml` / `docs/CHANGELOG.md` / `README.md` ✓

无路径错误。

---

## 执行 Handoff

Plan complete, saved to `docs/superpowers/plans/2026-07-11-shaofu-v10-optimize.md`.

执行选项：
1. **Subagent-Driven（推荐）** — 5 个 task 各自一个 implementer + reviewer
2. **Inline Execution** — 当前 session 顺序执行，含检查点

继续 SDD 模式继续。如果 OK，请确认（与 v3.7.0 一致的体验）。

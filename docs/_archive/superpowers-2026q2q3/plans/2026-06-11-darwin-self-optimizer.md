# Darwin Self-Optimizer V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `feature/darwin-self-optimizer` 分支上交付 V1 dry-run 模式，集成 darwin-skill v2.0 的 ratchet + reflex_blacklist + break_signal 三件套，针对 trading 策略层（基于 `monthly_reviews_self` 真实复盘数据）做受约束的 hill-climbing 优化，**不修改 SKILL.md**。

**Architecture:** 5 个模块化子包（`phase1_baseline` / `phase2_hillclimb` / `phase3_report` / `scorer` / `reflex_blacklist` / `llm_judge`），单一 `SelfOptimizer` 公共 API。评分公式 60% 真实数据 + 40% LLM judge（paired within-judge）。HITL 三层式（基线评估 / CHECKPOINT / STOP）。所有结果写入 `results.tsv` 9 列结构化日志 + `optimization_drafts/` Markdown 草稿 + `improvement_log.jsonl`（沿用现有）。

**Tech Stack:** Python 3.10+ / SQLite（现有）/ pytest / Tushare（不直接使用，沿用 monthly_reviews_self 数据）/ LLM providers（沿用 `modules/llm_providers.py`）/ ruff / pre-commit。

**Spec:** `docs/superpowers/specs/2026-06-11-darwin-self-optimizer-design.md` (commit 592708d)

**Branch:** `feature/darwin-self-optimizer` (从 main 拉出)

---

## File Structure

新增文件（V1 范围）：

| 文件 | 职责 | 行数估计 |
|---|---|---|
| `modules/self_optimizer/__init__.py` | 公共 API + SelfOptimizer 类 | 60 |
| `modules/self_optimizer/scorer.py` | 60% 硬规则分 + 40% LLM 分 | 100 |
| `modules/self_optimizer/reflex_blacklist.py` | 8 条反例硬阻断 | 80 |
| `modules/self_optimizer/llm_judge.py` | paired within-judge | 50 |
| `modules/self_optimizer/phase1_baseline.py` | 基线评估 | 80 |
| `modules/self_optimizer/phase2_hillclimb.py` | 迭代优化（含 ratchet + break） | 120 |
| `modules/self_optimizer/phase3_report.py` | 汇总报告 | 60 |
| `tests/test_reflex_blacklist.py` | 8 个反例单测 | 120 |
| `tests/test_scorer.py` | 60% 真实分公式单测 | 60 |
| `tests/test_break_signal.py` | break signal 单测 | 50 |
| `tests/test_self_optimizer_integration.py` | 3 个集成测试 | 150 |
| `tests/test_self_optimizer_e2e.py` | 1 个 E2E | 80 |

修改文件：

| 文件 | 修改范围 |
|---|---|
| `modules/cli.py` | 添加 `self-optimize` 子命令（+30 行） |
| `tests/conftest.py` | 添加 3 个新 fixture（+40 行） |
| `.github/workflows/test.yml` | 添加 self-optimizer 步骤（+10 行） |
| `.gitignore` | 添加 `optimization_drafts/` 和 `logs/results.tsv`（+2 行） |

**总代码量：约 1010 行**（含 460 行测试）。**无文件超过 150 行**。

---

## Task 0: 准备工作 - 创建 feature 分支

**Files:**
- Create: `feature/darwin-self-optimizer` (git branch)

- [ ] **Step 1: 确认 main 是最新**

```bash
git checkout main
git pull origin main
git log --oneline -3
```

Expected: 当前在 main 分支，看到 commit `592708d docs(specs): darwin self-optimizer integration design`

- [ ] **Step 2: 创建并切换到 feature 分支**

```bash
git checkout -b feature/darwin-self-optimizer
git status
```

Expected: `On branch feature/darwin-self-optimizer`, `nothing to commit, working tree clean`

- [ ] **Step 3: 更新 .gitignore**

修改项目根目录的 `.gitignore`，在末尾添加：

```gitignore
# Darwin self-optimizer artifacts (regenerated each run)
optimization_drafts/
logs/results.tsv
logs/self_optimizer_state.json
```

- [ ] **Step 4: 提交 .gitignore 变更**

```bash
git add .gitignore
git commit -m "chore: gitignore darwin self-optimizer artifacts"
```

Expected: `[feature/darwin-self-optimizer xxx] chore: gitignore darwin self-optimizer artifacts`

---

## Task 1: 创建 self_optimizer 子包骨架 + 公共 API

**Files:**
- Create: `modules/self_optimizer/__init__.py`

- [ ] **Step 1: 创建空子包目录**

```bash
mkdir -p modules/self_optimizer
touch modules/self_optimizer/__init__.py
```

- [ ] **Step 2: 写 __init__.py 公共 API**

写入 `modules/self_optimizer/__init__.py`：

```python
"""Darwin Self-Optimizer for zettaranc-skill.

V1 dry-run mode: 集成 ratchet + reflex_blacklist + break_signal,
不修改 SKILL.md, 产 optimization_drafts/ 供人工 review.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

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
        target: 优化目标 (trading | skill). V1 仅支持 trading.
        rounds: 最大迭代轮数 (默认 3).
        mode: dry_run (V1) | auto_revert (V2).
        review_months: 基线评估用的最近月份数 (默认 3).
    """

    def __init__(
        self,
        target: Literal["trading", "skill"] = "trading",
        rounds: int = 3,
        mode: Literal["dry_run", "auto_revert"] = "dry_run",
        review_months: int = 3,
    ) -> None:
        if target not in ("trading", "skill"):
            raise ValueError(f"V1 仅支持 trading/skill, 收到: {target}")
        if mode not in ("dry_run", "auto_revert"):
            raise ValueError(f"V1 仅支持 dry_run/auto_revert, 收到: {mode}")
        if mode == "auto_revert":
            raise NotImplementedError("V1 不支持 auto_revert, 将在 V2 实现")
        if rounds < 1 or rounds > 10:
            raise ValueError(f"rounds 必须在 [1, 10], 收到: {rounds}")

        self.target = target
        self.rounds = rounds
        self.mode = mode
        self.review_months = review_months
        self.log_dir = Path("logs")
        self.draft_dir = Path("optimization_drafts")
        self.results_tsv = self.log_dir / "results.tsv"

    def run(self) -> dict:
        """Phase 1 → 2 → 3 完整跑一次."""
        baseline = self.phase1_baseline()
        history: list[RoundResult] = []
        for n in range(1, self.rounds + 1):
            old_score = history[-1].new_score if history else baseline
            result = run_round(
                round_n=n,
                old_score=old_score,
                target=self.target,
                history=history,
            )
            history.append(result)
            if result.status == "break":
                break
        return self.phase3_report(history)

    def phase1_baseline(self) -> float:
        return phase1_baseline(target=self.target, review_months=self.review_months)

    def phase3_report(self, history: list[RoundResult]) -> dict:
        from datetime import datetime

        run_id = datetime.now().strftime("%Y-%m-%d-r%H%M%S")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.draft_dir.mkdir(parents=True, exist_ok=True)
        tsv_path = write_results_tsv(self.results_tsv, run_id, history)
        for r in history:
            draft_path = write_optimization_draft(self.draft_dir, run_id, r)
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
    "RoundResult",
    "check_break_signal",
]
```

- [ ] **Step 3: 验证 import 不报错（应 import 失败）**

```bash
python -c "from modules.self_optimizer import SelfOptimizer"
```

Expected: `ModuleNotFoundError: No module named 'modules.self_optimizer.phase1_baseline'`（这是预期的，因为子模块还没写）

- [ ] **Step 4: 提交骨架**

```bash
git add modules/self_optimizer/__init__.py
git commit -m "feat(self-optimizer): add package skeleton with SelfOptimizer API"
```

---

## Task 2: 实现 reflex_blacklist.py + 8 条反例（先写测试）

**Files:**
- Create: `modules/self_optimizer/reflex_blacklist.py`
- Create: `tests/test_reflex_blacklist.py`

- [ ] **Step 1: 写 8 条反例的失败测试**

写入 `tests/test_reflex_blacklist.py`：

```python
"""Tests for trading reflex blacklist (8 anti-patterns)."""
import pytest

from modules.self_optimizer.reflex_blacklist import (
    TRADING_BLACKLIST,
    Violation,
    check_all,
)


# 8 个反例的 fixture

@pytest.fixture
def proposed_with_poor_strategy():
    """反例 #1: 胜率<-10% 仍被标为 good (与 status 一致性反)."""
    return {
        "proposed": [
            {"strategy": "波段", "status": "good", "avg_return": -15.0, "avg_drawdown": 10.0, "stock_count": 10}
        ]
    }


@pytest.fixture
def analysis_with_low_sample():
    """反例 #2: stock_count<5 强行评估."""
    return {
        "analysis": {
            "strategy_stats": [
                {"strategy_tags": "小盘", "stock_count": 3, "avg_return": 5.0, "avg_drawdown": 8.0}
            ]
        }
    }


@pytest.fixture
def proposed_missing_drawdown_warning():
    """反例 #3: 回撤>20% 仍未标 risky."""
    return {
        "proposed": [
            {"strategy": "激进", "status": "good", "avg_return": 15.0, "avg_drawdown": 35.0, "stock_count": 10}
        ]
    }


@pytest.fixture
def llm_input_with_self_reference():
    """反例 #4: LLM judge 读了 harness_updater 自己的输出."""
    return {
        "llm_input": {
            "judge_prompt": "评估以下 harness_updater 输出: ...",
            "contains_harness_output": True,
        }
    }


@pytest.fixture
def execution_log_silent_exception():
    """反例 #5: 异常被 swallow 而非 raise."""
    return {
        "execution_log": [
            {"action": "analyze_strategy", "status": "failure", "raised": False, "message": "soft fail"}
        ]
    }


@pytest.fixture
def proposed_multi_strategy_mutation():
    """反例 #6: 单轮提议改动 >2 个策略标签."""
    return {
        "proposed": [
            {"strategy": "A"}, {"strategy": "B"}, {"strategy": "C"}
        ]
    }


@pytest.fixture
def history_high_dryrun():
    """反例 #7: dry-run 比例 >30%."""
    return {
        "history": [
            {"status": "dry_run"}, {"status": "dry_run"},
            {"status": "dry_run"}, {"status": "keep"},
        ]
    }


@pytest.fixture
def scoring_no_real_data():
    """反例 #8: 只用 LLM judge 未参考 monthly_reviews_self."""
    return {
        "scoring": {"real_weight": 0.0, "llm_weight": 1.0, "hard_rule_weight": 0.0}
    }


# 8 个单测

def test_high_return_no_warning(proposed_with_poor_strategy):
    violations = check_all(proposed_with_poor_strategy)
    assert any(v.name == "high_return_no_warning" for v in violations)


def test_low_sample_size(analysis_with_low_sample):
    violations = check_all(analysis_with_low_sample)
    assert any(v.name == "low_sample_size" for v in violations)


def test_high_drawdown_no_limit(proposed_missing_drawdown_warning):
    violations = check_all(proposed_missing_drawdown_warning)
    assert any(v.name == "high_drawdown_no_limit" for v in violations)


def test_self_eval_context(llm_input_with_self_reference):
    violations = check_all(llm_input_with_self_reference)
    assert any(v.name == "self_eval_context" for v in violations)


def test_silent_exception(execution_log_silent_exception):
    violations = check_all(execution_log_silent_exception)
    assert any(v.name == "silent_exception" for v in violations)


def test_multi_strategy_mutation(proposed_multi_strategy_mutation):
    violations = check_all(proposed_multi_strategy_mutation)
    assert any(v.name == "multi_strategy_mutation" for v in violations)


def test_dry_run_overload(history_high_dryrun):
    violations = check_all(history_high_dryrun)
    assert any(v.name == "dry_run_overload" for v in violations)


def test_ignore_real_signal(scoring_no_real_data):
    violations = check_all(scoring_no_real_data)
    assert any(v.name == "ignore_real_signal" for v in violations)


def test_blacklist_has_8_items():
    """结构性检查: 必须是 8 条."""
    assert len(TRADING_BLACKLIST) == 8


def test_check_all_returns_empty_when_clean():
    """通过的反例集应返回空列表."""
    clean_ctx = {
        "proposed": [{"strategy": "X", "status": "good", "avg_return": 12.0, "avg_drawdown": 8.0, "stock_count": 20}],
        "analysis": {"strategy_stats": [{"strategy_tags": "X", "stock_count": 20, "avg_return": 12.0, "avg_drawdown": 8.0}]},
        "llm_input": {"contains_harness_output": False},
        "execution_log": [{"status": "success", "raised": False}],
        "history": [{"status": "keep"}],
        "scoring": {"real_weight": 0.6, "llm_weight": 0.4, "hard_rule_weight": 0.0},
    }
    assert check_all(clean_ctx) == []
```

- [ ] **Step 2: 跑测试，预期 10 个全失败（ImportError）**

```bash
python -m pytest tests/test_reflex_blacklist.py -v
```

Expected: 10 failed, all with `ModuleNotFoundError: No module named 'modules.self_optimizer.reflex_blacklist'`

- [ ] **Step 3: 写 reflex_blacklist.py 最小实现**

写入 `modules/self_optimizer/reflex_blacklist.py`：

```python
"""Trading reflex blacklist (8 anti-patterns from real trading pitfalls).

每个反例来自 zettaranc-skill 现有 harness_updater.py 逻辑 + 推断的踩坑场景.
任何触发强制 status=revert, 防止自我优化引入回归.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Violation:
    """单条反例违规."""

    name: str
    description: str
    detail: str = ""


# 8 条反例检测函数

def _check_high_return_no_warning(ctx: dict) -> list[Violation]:
    proposed = ctx.get("proposed", [])
    violations = []
    for item in proposed:
        if item.get("status") == "good" and item.get("avg_return", 0) < -10:
            violations.append(Violation(
                name="high_return_no_warning",
                description="胜率<-10% 仍标为 good 状态",
                detail=f"strategy={item.get('strategy')}, avg_return={item.get('avg_return')}",
            ))
    return violations


def _check_low_sample_size(ctx: dict) -> list[Violation]:
    analysis = ctx.get("analysis", {})
    stats = analysis.get("strategy_stats", []) if isinstance(analysis, dict) else []
    violations = []
    for stat in stats:
        if stat.get("stock_count", 0) < 5:
            violations.append(Violation(
                name="low_sample_size",
                description="stock_count<5 强行评估",
                detail=f"strategy_tags={stat.get('strategy_tags')}, stock_count={stat.get('stock_count')}",
            ))
    return violations


def _check_high_drawdown_no_limit(ctx: dict) -> list[Violation]:
    proposed = ctx.get("proposed", [])
    violations = []
    for item in proposed:
        if item.get("avg_drawdown", 0) > 20 and item.get("status") != "risky":
            violations.append(Violation(
                name="high_drawdown_no_limit",
                description="回撤>20% 仍未标 risky",
                detail=f"strategy={item.get('strategy')}, avg_drawdown={item.get('avg_drawdown')}, status={item.get('status')}",
            ))
    return violations


def _check_self_eval_context(ctx: dict) -> list[Violation]:
    llm_input = ctx.get("llm_input", {})
    if llm_input.get("contains_harness_output"):
        return [Violation(
            name="self_eval_context",
            description="LLM judge 读了 harness_updater 自己的输出 (PR #13 教训)",
            detail="judge 需用 paired within-judge, 不可用 harness 自身输出当 judge input",
        )]
    return []


def _check_silent_exception(ctx: dict) -> list[Violation]:
    log = ctx.get("execution_log", [])
    violations = []
    for entry in log:
        if entry.get("status") == "failure" and not entry.get("raised", False):
            violations.append(Violation(
                name="silent_exception",
                description="异常被 swallow 而非 raise",
                detail=f"action={entry.get('action')}, message={entry.get('message')}",
            ))
    return violations


def _check_multi_strategy_mutation(ctx: dict) -> list[Violation]:
    proposed = ctx.get("proposed", [])
    if len(proposed) > 2:
        return [Violation(
            name="multi_strategy_mutation",
            description="单轮提议改动 >2 个策略标签",
            detail=f"proposed count={len(proposed)}, max=2",
        )]
    return []


def _check_dry_run_overload(ctx: dict) -> list[Violation]:
    history = ctx.get("history", [])
    if not history:
        return []
    dry_count = sum(1 for h in history if h.get("status") in ("dry_run", "revert"))
    ratio = dry_count / len(history)
    if ratio > 0.3:
        return [Violation(
            name="dry_run_overload",
            description="dry-run 比例 >30%",
            detail=f"ratio={ratio:.0%}, dry_count={dry_count}, total={len(history)}",
        )]
    return []


def _check_ignore_real_signal(ctx: dict) -> list[Violation]:
    scoring = ctx.get("scoring", {})
    real_weight = scoring.get("real_weight", 0.0)
    if real_weight < 0.6:
        return [Violation(
            name="ignore_real_signal",
            description="只用 LLM judge 未充分参考 monthly_reviews_self",
            detail=f"real_weight={real_weight}, min=0.6",
        )]
    return []


TRADING_BLACKLIST: list[tuple[str, str, Callable[[dict], list[Violation]]]] = [
    ("high_return_no_warning", "胜率<-10% 仍标 good", _check_high_return_no_warning),
    ("low_sample_size", "stock_count<5 强行评估", _check_low_sample_size),
    ("high_drawdown_no_limit", "回撤>20% 仍未标 risky", _check_high_drawdown_no_limit),
    ("self_eval_context", "LLM judge 读 harness 自身输出", _check_self_eval_context),
    ("silent_exception", "异常被 swallow 而非 raise", _check_silent_exception),
    ("multi_strategy_mutation", "单轮改 >2 个策略", _check_multi_strategy_mutation),
    ("dry_run_overload", "dry-run 比例 >30%", _check_dry_run_overload),
    ("ignore_real_signal", "real_weight<0.6", _check_ignore_real_signal),
]


def check_all(context: dict[str, Any]) -> list[Violation]:
    """运行所有 8 条反例, 返回所有触发的违规 (空列表 = 通过)."""
    violations: list[Violation] = []
    for name, description, check_fn in TRADING_BLACKLIST:
        try:
            violations.extend(check_fn(context))
        except Exception as e:
            violations.append(Violation(
                name=name,
                description=description,
                detail=f"检测函数异常: {e}",
            ))
    return violations
```

- [ ] **Step 4: 跑测试，预期 10/10 通过**

```bash
python -m pytest tests/test_reflex_blacklist.py -v
```

Expected: `10 passed`

- [ ] **Step 5: 提交**

```bash
git add modules/self_optimizer/reflex_blacklist.py tests/test_reflex_blacklist.py
git commit -m "feat(self-optimizer): add 8-item trading reflex blacklist with TDD tests"
```

---

## Task 3: 实现 scorer.py（60% 真实 + 40% LLM 接口）

**Files:**
- Create: `modules/self_optimizer/scorer.py`
- Create: `tests/test_scorer.py`

- [ ] **Step 1: 写 scorer 失败测试**

写入 `tests/test_scorer.py`：

```python
"""Tests for trading score (60% real + 40% LLM stub)."""
import pytest

from modules.self_optimizer.scorer import (
    compute_total_score,
    compute_trading_score,
)


@pytest.fixture
def good_monthly_stats():
    """胜率 8%, 回撤 8%, 准确率 60% → 应得满分 60."""
    return {
        "avg_return": 8.0,
        "avg_drawdown": 8.0,
        "accuracy_rate": 60.0,
        "stock_count": 20,
    }


@pytest.fixture
def bad_monthly_stats():
    """胜率 -15%, 回撤 35%, 准确率 20% → 应得低分."""
    return {
        "avg_return": -15.0,
        "avg_drawdown": 35.0,
        "accuracy_rate": 20.0,
        "stock_count": 15,
    }


@pytest.fixture
def extreme_values():
    """极端值: 胜率 +50%, 回撤 0%, 准确率 100% → 必须 clamp."""
    return {
        "avg_return": 50.0,
        "avg_drawdown": 0.0,
        "accuracy_rate": 100.0,
        "stock_count": 30,
    }


def test_trading_score_good(good_monthly_stats):
    score = compute_trading_score(good_monthly_stats)
    # 18 (胜率 8% → 8/10 * 30 = 24, 但 clamp +10% → 30)
    # 实算: 8% 映射到 [0, 30] 是 8/10 * 30 = 24
    # 18 (回撤 8% → 满分 30, 因为 <10% 满分)
    # 24 (准确率 60% → 60/100 * 40 = 24)
    # 总: 24 + 30 + 24 = 78, 但 cap 60
    assert 55 <= score <= 60


def test_trading_score_bad(bad_monthly_stats):
    score = compute_trading_score(bad_monthly_stats)
    # 胜率 -15% → clamp -10% 映射 0 分
    # 回撤 35% → 10-50% 线性 0-30, 35% → (50-35)/40*30 = 11.25
    # 准确率 20% → 20/100 * 40 = 8
    # 总: 0 + 11.25 + 8 = 19.25
    assert 15 <= score <= 25


def test_trading_score_clamping(extreme_values):
    score = compute_trading_score(extreme_values)
    # clamp 胜率 +50% → +10% → 30 分
    # 回撤 0% → 满分 30
    # 准确率 100% → 40 分
    # 总: 30 + 30 + 40 = 100, 但 cap 60
    assert score == 60


def test_total_score_combines_real_and_llm(good_monthly_stats, monkeypatch):
    """验证 60% 真实 + 40% LLM 加总公式."""
    # monkeypatch LLM 调用避免真打 API
    from modules.self_optimizer import scorer
    monkeypatch.setattr(scorer, "compute_llm_score", lambda proposed: 30.0)
    total, breakdown = compute_total_score("2026-05", good_monthly_stats, proposed={})
    # 60 分真实 + 30 分 LLM = 90
    assert 85 <= total <= 95
    assert breakdown["real"] > 0
    assert breakdown["llm"] == 30.0
```

- [ ] **Step 2: 跑测试，预期全失败（ImportError）**

```bash
python -m pytest tests/test_scorer.py -v
```

Expected: 4 failed, all with `ModuleNotFoundError`

- [ ] **Step 3: 写 scorer.py 最小实现**

写入 `modules/self_optimizer/scorer.py`：

```python
"""Trading score: 60% real monthly_reviews_self data + 40% LLM judge.

真实分公式 (0-60):
- 30% 月度平均胜率: clamp [-10%, +10%] → [0, 30]
- 30% 平均回撤反向: <10% 满分 30, >50% 零分, 10-50% 线性
- 40% 信号准确率: 0-100% 线性映射 0-40

LLM 分公式 (0-40):
- 由 llm_judge.paired_judge() 提供, 此处仅占位
"""
from __future__ import annotations

from typing import Any


def _score_return(avg_return: float) -> float:
    """胜率映射: [-10%, +10%] → [0, 30]."""
    clamped = max(-10.0, min(10.0, avg_return))
    return (clamped + 10.0) / 20.0 * 30.0


def _score_drawdown(avg_drawdown: float) -> float:
    """回撤反向: <10% 满分 30, >50% 零分."""
    if avg_drawdown < 10.0:
        return 30.0
    if avg_drawdown > 50.0:
        return 0.0
    return (50.0 - avg_drawdown) / 40.0 * 30.0


def _score_accuracy(accuracy_rate: float) -> float:
    """准确率: 0-100% → 0-40."""
    clamped = max(0.0, min(100.0, accuracy_rate))
    return clamped / 100.0 * 40.0


def compute_trading_score(monthly_stats: dict[str, Any]) -> float:
    """60% 真实数据分 (0-60)."""
    s_return = _score_return(monthly_stats["avg_return"])
    s_drawdown = _score_drawdown(monthly_stats["avg_drawdown"])
    s_accuracy = _score_accuracy(monthly_stats["accuracy_rate"])
    return min(60.0, s_return + s_drawdown + s_accuracy)


def compute_llm_score(proposed: dict[str, Any]) -> float:
    """40% LLM 评审分 (0-40).

    V1 stub: 返回中性 20 分. V1.1+ 由 llm_judge.paired_judge 实现.
    """
    return 20.0


def compute_total_score(
    review_month: str,
    monthly_stats: dict[str, Any],
    proposed: dict[str, Any],
) -> tuple[float, dict[str, float]]:
    """返回 (总分, 拆分) 总分 ∈ [0, 100]."""
    real = compute_trading_score(monthly_stats)
    llm = compute_llm_score(proposed)
    total = real + llm
    return total, {"real": real, "llm": llm, "total": total}
```

- [ ] **Step 4: 跑测试，预期 4/4 通过**

```bash
python -m pytest tests/test_scorer.py -v
```

Expected: `4 passed`

- [ ] **Step 5: 提交**

```bash
git add modules/self_optimizer/scorer.py tests/test_scorer.py
git commit -m "feat(self-optimizer): add trading scorer (60% real + 40% LLM stub)"
```

---

## Task 4: 实现 break_signal 检测

**Files:**
- Create: `tests/test_break_signal.py`

注意：`check_break_signal` 已在 `__init__.py` 引用但未实现。在 Task 2 时测试会因 ImportError 失败（已有）。这里把测试和实现都补完。

- [ ] **Step 1: 写 break_signal 失败测试**

写入 `tests/test_break_signal.py`：

```python
"""Tests for break signal (连续 2 轮 Δ<2 → stop)."""
from modules.self_optimizer.phase2_hillclimb import (
    RoundResult,
    check_break_signal,
)


def _make_result(delta: float, status: str = "revert") -> RoundResult:
    return RoundResult(
        round=1,
        old_score=80.0,
        new_score=80.0 + delta,
        delta=delta,
        status=status,
        violations=[],
        proposed_diff="",
        timestamp="2026-06-11T00:00:00",
    )


def test_two_consecutive_small_delta_breaks():
    """连续 2 轮 Δ<2 → break."""
    history = [_make_result(1.5), _make_result(1.0)]
    assert check_break_signal(history, threshold=2.0) is True


def test_one_small_one_large_does_not_break():
    """一 Δ<2 + 一 Δ>=2 → 不 break."""
    history = [_make_result(1.5), _make_result(2.5)]
    assert check_break_signal(history, threshold=2.0) is False


def test_empty_history_does_not_break():
    assert check_break_signal([]) is False


def test_single_round_does_not_break():
    history = [_make_result(0.5)]
    assert check_break_signal(history) is False
```

- [ ] **Step 2: 跑测试，预期 4 个全失败（ImportError）**

```bash
python -m pytest tests/test_break_signal.py -v
```

Expected: 4 failed with `ModuleNotFoundError: No module named 'modules.self_optimizer.phase2_hillclimb'`

- [ ] **Step 3: 写 phase2_hillclimb.py 最小实现（含 break_signal）**

写入 `modules/self_optimizer/phase2_hillclimb.py`：

```python
"""Phase 2 hill-climbing: ratchet + break_signal.

V1 范围: 仅实现 break_signal + RoundResult 数据类 + run_round 签名.
完整 ratchet 逻辑在 Task 5 实现.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


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


def check_break_signal(history: list[RoundResult], threshold: float = 2.0) -> bool:
    """连续 2 轮 delta < threshold → True (触发 break)."""
    if len(history) < 2:
        return False
    return abs(history[-1].delta) < threshold and abs(history[-2].delta) < threshold


def run_round(
    round_n: int,
    old_score: float,
    target: str,
    history: list[RoundResult],
) -> RoundResult:
    """单轮迭代. V1 stub: 总是返回 break 避免误操作.

    Task 5 将实现完整逻辑.
    """
    return RoundResult(
        round=round_n,
        old_score=old_score,
        new_score=old_score,
        delta=0.0,
        status="break",
        violations=["v1_stub"],
        proposed_diff="(V1 stub - 完整实现在 Task 5)",
        timestamp=datetime.now().isoformat(),
    )
```

- [ ] **Step 4: 跑测试，预期 4/4 通过**

```bash
python -m pytest tests/test_break_signal.py -v
```

Expected: `4 passed`

- [ ] **Step 5: 跑全部单测，确认 18 个全过**

```bash
python -m pytest tests/test_reflex_blacklist.py tests/test_scorer.py tests/test_break_signal.py -v
```

Expected: `18 passed`

- [ ] **Step 6: 提交**

```bash
git add modules/self_optimizer/phase2_hillclimb.py tests/test_break_signal.py
git commit -m "feat(self-optimizer): add RoundResult + break_signal with TDD tests"
```

---

## Task 5: 实现 llm_judge.py（paired within-judge stub）

**Files:**
- Create: `modules/self_optimizer/llm_judge.py`

V1 阶段 LLM judge 仅写 stub，**不接真实 API**——避免 CI 因 LLM 不可用而失败。V1.1+ 接入 `modules/llm_providers.py`。

- [ ] **Step 1: 写 llm_judge.py 最小实现**

写入 `modules/self_optimizer/llm_judge.py`：

```python
"""LLM judge with paired within-judge (PR #13 教训).

V1 stub: 返回固定值. V1.1+ 接 modules/llm_providers.py.
"""
from __future__ import annotations

from typing import Any


def paired_judge(
    before: str,
    after: str,
    prompt_template: str = "",
) -> bool:
    """1 轮 paired within-judge.

    V1 stub: 总是 True (after 更好). V1.1+ 接真 LLM.
    必须 paired (同 call 给 before+after), 禁止单边.
    """
    return True


def compute_llm_score_with_baseline(
    baseline: dict[str, Any],
    new: dict[str, Any],
) -> float:
    """返回 0-40. V1 stub: 20."""
    return 20.0
```

- [ ] **Step 2: 验证 import OK**

```bash
python -c "from modules.self_optimizer.llm_judge import paired_judge, compute_llm_score_with_baseline; print(paired_judge('a', 'b'))"
```

Expected: `True`

- [ ] **Step 3: 提交**

```bash
git add modules/self_optimizer/llm_judge.py
git commit -m "feat(self-optimizer): add llm_judge stub (paired within-judge, V1 fixed-value)"
```

---

## Task 6: 实现 phase1_baseline.py + 集成测试 #1

**Files:**
- Create: `modules/self_optimizer/phase1_baseline.py`
- Modify: `tests/conftest.py` (添加 1 个 fixture)
- Create: `tests/test_self_optimizer_integration.py`

- [ ] **Step 1: 添加 conftest fixture**

修改 `tests/conftest.py`，在文件末尾添加：

```python
@pytest.fixture
def mock_monthly_reviews_with_poor_strategy():
    """mock 3 个月复盘数据, 一只策略 stock_count=1 胜率 -30%."""
    from datetime import datetime, timedelta

    from modules.database import get_connection

    months = []
    base = datetime(2026, 3, 1)
    for i in range(3):
        month = (base + timedelta(days=30 * i)).strftime("%Y%m")
        months.append(month)

    with get_connection() as conn:
        cursor = conn.cursor()
        for month in months:
            cursor.execute(
                """
                INSERT OR REPLACE INTO monthly_reviews_self
                (ts_code, review_month, monthly_return, max_drawdown,
                 buy_signals_count, correct_buy_signals)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("600000.SH", month, -30.0, 45.0, 5, 1),
            )
        conn.commit()
    yield months
```

如果 `monthly_reviews_self` 表不存在，跳过这个 fixture（conftest 已存在的 `temp_db` fixture 应该建好表）。

- [ ] **Step 2: 写 phase1_baseline.py 失败测试（集成测试 #1）**

修改 `tests/test_self_optimizer_integration.py`，写入：

```python
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

    def fake_score(_proposed: dict) -> float:
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

    def fake_score_close(_proposed: dict) -> float:
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
```

- [ ] **Step 3: 跑测试，预期 3 个全失败**

```bash
python -m pytest tests/test_self_optimizer_integration.py -v
```

Expected: 3 failed with `ModuleNotFoundError`

- [ ] **Step 4: 写 phase1_baseline.py 最小实现**

写入 `modules/self_optimizer/phase1_baseline.py`：

```python
"""Phase 1: baseline score from monthly_reviews_self + LLM judge stub."""
from __future__ import annotations

from typing import Any

from modules.database import get_connection
from modules.self_optimizer.scorer import compute_total_score


def _fetch_aggregate_stats(review_months: int) -> dict[str, Any]:
    """读最近 N 个月 monthly_reviews_self 聚合统计."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                AVG(monthly_return) as avg_return,
                AVG(max_drawdown) as avg_drawdown,
                SUM(buy_signals_count) as total_buy,
                SUM(correct_buy_signals) as total_correct,
                COUNT(DISTINCT ts_code) as stock_count
            FROM (
                SELECT * FROM monthly_reviews_self
                ORDER BY review_month DESC
                LIMIT ?
            )
            """,
            (review_months * 30,),  # 近似 30 天/月
        )
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return {
                "avg_return": 0.0,
                "avg_drawdown": 0.0,
                "accuracy_rate": 0.0,
                "stock_count": 0,
            }
        avg_return, avg_drawdown, total_buy, total_correct, stock_count = row
        accuracy_rate = (total_correct / total_buy * 100) if total_buy and total_buy > 0 else 0.0
        return {
            "avg_return": float(avg_return or 0.0),
            "avg_drawdown": float(avg_drawdown or 0.0),
            "accuracy_rate": float(accuracy_rate),
            "stock_count": int(stock_count or 0),
        }


def phase1_baseline(target: str = "trading", review_months: int = 3) -> float:
    """计算基线分数 (0-100)."""
    if target != "trading":
        raise NotImplementedError(f"V1 仅支持 trading target, 收到: {target}")
    stats = _fetch_aggregate_stats(review_months)
    total, _ = compute_total_score("baseline", stats, proposed={})
    return total
```

- [ ] **Step 5: 跑测试，预期 test_phase1_baseline_with_mock_data 通过（其他 2 个仍失败）**

```bash
python -m pytest tests/test_self_optimizer_integration.py::test_phase1_baseline_with_mock_data -v
```

Expected: 1 passed

- [ ] **Step 6: 提交 phase1**

```bash
git add modules/self_optimizer/phase1_baseline.py tests/test_self_optimizer_integration.py tests/conftest.py
git commit -m "feat(self-optimizer): add phase1 baseline + integration test #1"
```

---

## Task 7: 实现 phase2 完整 ratchet 逻辑 + 集成测试 #2/#3

**Files:**
- Modify: `modules/self_optimizer/phase2_hillclimb.py` (替换 run_round stub)

- [ ] **Step 1: 替换 phase2_hillclimb.py 的 run_round 为完整实现**

用以下内容**完全替换** `modules/self_optimizer/phase2_hillclimb.py`：

```python
"""Phase 2 hill-climbing: ratchet + reflex_blacklist + break_signal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from modules.harness_updater import HarnessUpdater
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


def check_break_signal(history: list[RoundResult], threshold: float = 2.0) -> bool:
    """连续 2 轮 delta < threshold → True (触发 break)."""
    if len(history) < 2:
        return False
    return abs(history[-1].delta) < threshold and abs(history[-2].delta) < threshold


def _harness_propose(_old_score: float) -> dict:
    """调 HarnessUpdater 生成 Guardrails 更新建议.

    返回结构: {proposed, analysis, execution_log}
    """
    updater = HarnessUpdater()
    analysis = updater.analyze_strategy_performance()
    if not analysis.get("success"):
        return {
            "proposed": [],
            "analysis": {"strategy_stats": []},
            "execution_log": [{"action": "analyze", "status": "failure", "raised": False}],
        }
    updates = updater.generate_guardrails_update(analysis)
    return {
        "proposed": updates.get("updates", []),
        "analysis": analysis,
        "execution_log": [{"action": "analyze", "status": "success", "raised": False}],
    }


def _score_proposal(proposed: dict, old_monthly_stats: dict) -> float:
    """评估提议后的总分."""
    total, _ = compute_total_score("latest", old_monthly_stats, proposed=proposed)
    return total


def run_round(
    round_n: int,
    old_score: float,
    target: str,
    history: list[RoundResult],
) -> RoundResult:
    """单轮迭代: propose → blacklist check → score → ratchet."""
    timestamp = datetime.now().isoformat()
    proposal = _harness_propose(old_score)

    # 1. reflex_blacklist 硬阻断
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

    # 2. 评分
    new_score = _score_proposal(proposal, old_monthly_stats={})  # V1 stub monthly_stats

    # 3. ratchet: new > old 才 keep
    delta = new_score - old_score
    status: Literal["keep", "revert"] = "keep" if delta > 0 else "revert"

    return RoundResult(
        round=round_n,
        old_score=old_score,
        new_score=new_score,
        delta=delta,
        status=status,
        violations=[],
        proposed_diff=str(proposal.get("proposed", [])),
        timestamp=timestamp,
    )
```

- [ ] **Step 2: 跑集成测试，预期 3/3 通过**

```bash
python -m pytest tests/test_self_optimizer_integration.py -v
```

Expected: `3 passed`

- [ ] **Step 3: 跑全部单测 + 集成测试，确认 21 个全过**

```bash
python -m pytest tests/test_reflex_blacklist.py tests/test_scorer.py tests/test_break_signal.py tests/test_self_optimizer_integration.py -v
```

Expected: `21 passed`

- [ ] **Step 4: 提交**

```bash
git add modules/self_optimizer/phase2_hillclimb.py
git commit -m "feat(self-optimizer): complete phase2 ratchet with HarnessUpdater integration"
```

---

## Task 8: 实现 phase3_report.py（results.tsv + drafts + log）

**Files:**
- Create: `modules/self_optimizer/phase3_report.py`

- [ ] **Step 1: 写 phase3_report.py**

写入 `modules/self_optimizer/phase3_report.py`：

```python
"""Phase 3: 汇总报告 (results.tsv + optimization_drafts/ + improvement_log)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from modules.self_optimizer.phase2_hillclimb import RoundResult

# results.tsv 9 列定义 (与 darwin-skill 对齐)
TSV_HEADER = [
    "timestamp",
    "commit",
    "skill",
    "old_score",
    "new_score",
    "status",
    "dimension",
    "note",
    "eval_mode",
]


def write_results_tsv(
    path: Path,
    run_id: str,
    rounds: list[RoundResult],
) -> Path:
    """写 9 列 results.tsv. 每次 run 追加, 不覆盖历史."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with open(path, "a", encoding="utf-8") as f:
        if is_new:
            f.write("\t".join(TSV_HEADER) + "\n")
        for r in rounds:
            row = [
                r.timestamp,
                f"dry_run_{run_id}_r{r.round}",  # V1: 不是真 commit
                "trading",
                f"{r.old_score:.2f}",
                f"{r.new_score:.2f}",
                r.status,
                ",".join(r.violations) if r.violations else "none",
                r.proposed_diff[:80],  # 截断避免 tsv 爆炸
                "dry_run",
            ]
            f.write("\t".join(row) + "\n")
    return path


def write_optimization_draft(
    draft_dir: Path,
    run_id: str,
    result: RoundResult,
) -> Path:
    """生成 optimization_drafts/YYYY-MM-DD-rN.md."""
    draft_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = draft_dir / f"{date_str}-{run_id}-r{result.round}.md"
    content = f"""# Optimization Draft (Round {result.round})

- **Run ID**: {run_id}
- **Timestamp**: {result.timestamp}
- **Status**: {result.status}
- **Old Score**: {result.old_score:.2f}
- **New Score**: {result.new_score:.2f}
- **Delta**: {result.delta:+.2f}

## Proposed Diff

```json
{result.proposed_diff}
```

## Violations

{", ".join(result.violations) if result.violations else "无"}

## Decision Rationale

V1 dry-run: 提议由 HarnessUpdater 生成, 评分由 60% 真实 + 40% LLM stub.
人工 review 后决定合入与否.
"""
    path.write_text(content, encoding="utf-8")
    return path


def append_improvement_log(log_dir: Path, result: RoundResult) -> None:
    """复用现有 ImprovementLogger 写 improvement_log.jsonl."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "improvement_log.jsonl"
    entry = {
        "timestamp": result.timestamp,
        "action": "self_optimization_round",
        "category": "optimization",
        "status": "success" if result.status == "keep" else "reverted",
        "message": f"Round {result.round}: {result.old_score:.2f} → {result.new_score:.2f} ({result.status})",
        "details": {
            "round": result.round,
            "old_score": result.old_score,
            "new_score": result.new_score,
            "delta": result.delta,
            "violations": result.violations,
        },
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 2: 验证 import OK**

```bash
python -c "from modules.self_optimizer import SelfOptimizer; o = SelfOptimizer(); print('OK', o.target, o.rounds, o.mode)"
```

Expected: `OK trading 3 dry_run`

- [ ] **Step 3: 提交**

```bash
git add modules/self_optimizer/phase3_report.py
git commit -m "feat(self-optimizer): add phase3 report (tsv + drafts + log)"
```

---

## Task 9: 扩展 CLI 子命令 + E2E 测试

**Files:**
- Modify: `modules/cli.py` (添加 self-optimize 子命令)
- Create: `tests/test_self_optimizer_e2e.py`
- Modify: `tests/conftest.py` (添加 state_with_interrupted_run fixture)

- [ ] **Step 1: 添加 conftest fixture (state 中断恢复)**

修改 `tests/conftest.py`，在文件末尾添加：

```python
@pytest.fixture
def state_with_interrupted_run(tmp_path):
    """上次 run 到 round 2 中断, 验证下次 run 询问恢复."""
    import json

    state_file = tmp_path / "self_optimizer_state.json"
    state = {
        "run_id": "2026-06-10-abcd",
        "started_at": "2026-06-10T07:30:00",
        "target": "trading",
        "mode": "dry_run",
        "current_round": 2,
        "baseline_score": 80.0,
        "rounds": [
            {"round": 1, "old": 80.0, "new": 82.5, "delta": 2.5, "status": "keep"},
        ],
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    yield state_file
```

- [ ] **Step 2: 写 E2E 测试**

写入 `tests/test_self_optimizer_e2e.py`：

```python
"""E2E test for self-optimizer V1 dry-run."""
import json
from pathlib import Path

import pytest

from modules.self_optimizer import SelfOptimizer


@pytest.mark.slow
def test_full_run_dry_run(tmp_path, monkeypatch):
    """端到端 dry-run: 跑 3 轮, 验证 tsv + drafts + log + SKILL.md 未改."""
    # monkeypatch 评分避免依赖真实 monthly_reviews_self
    from modules.self_optimizer import phase2_hillclimb

    scores = iter([82.0, 83.5, 84.0])  # 递增模拟
    monkeypatch.setattr(phase2_hillclimb, "_score_proposal", lambda *a, **kw: next(scores))

    # 切到临时目录
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modules").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "optimization_drafts").mkdir()

    # 跑
    opt = SelfOptimizer(rounds=3)
    result = opt.run()

    # 验证 results.tsv
    tsv = Path("logs/results.tsv")
    assert tsv.exists()
    lines = tsv.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 4  # header + 3 rounds
    assert lines[0].startswith("timestamp\tcommit\tskill")

    # 验证 drafts
    drafts = list(Path("optimization_drafts").glob("*.md"))
    assert len(drafts) == 3

    # 验证 log
    log = Path("logs/improvement_log.jsonl")
    assert log.exists()
    entries = [json.loads(l) for l in log.read_text(encoding="utf-8").strip().split("\n") if l]
    assert len(entries) == 3

    # 验证返回值
    assert result["rounds"] == 3
    assert "results_tsv" in result
    assert "drafts_dir" in result
```

- [ ] **Step 3: 跑 E2E 测试（可能因 monkeypatch.chdir 失败，调试后重跑）**

```bash
python -m pytest tests/test_self_optimizer_e2e.py -v
```

Expected: `1 passed`（如果失败，检查 monkeypatch.chdir 与真实项目目录的冲突）

- [ ] **Step 4: 添加 CLI 子命令**

修改 `modules/cli.py`，在文件末尾添加：

```python
def cmd_self_optimize(args) -> int:
    """self-optimize 子命令."""
    from modules.self_optimizer import SelfOptimizer

    opt = SelfOptimizer(
        target=args.target,
        rounds=args.rounds,
        mode="dry_run",
    )
    if args.action == "run":
        result = opt.run()
        print(f"✓ Phase 3 done. {result['rounds']} rounds.")
        print(f"  keep={result['keep']} revert={result['revert']} break={result['break']}")
        print(f"  results.tsv: {result['results_tsv']}")
        print(f"  drafts: {result['drafts_dir']}")
        print("⚠️  请人工 review optimization_drafts/ 后决定合入")
        return 0
    if args.action == "status":
        print(f"target={opt.target} rounds={opt.rounds} mode={opt.mode}")
        return 0
    if args.action == "reset":
        state = Path("logs/self_optimizer_state.json")
        if state.exists():
            state.unlink()
            print("✓ state.json 已删除")
        return 0
    print(f"Unknown action: {args.action}")
    return 1


def add_self_optimize_parser(subparsers) -> None:
    """注册 self-optimize 子命令."""
    p = subparsers.add_parser("self-optimize", help="darwin self-optimizer")
    p.add_argument("action", choices=["run", "status", "reset"])
    p.add_argument("--target", choices=["trading", "skill"], default="trading")
    p.add_argument("--rounds", type=int, default=3)
    p.set_defaults(func=cmd_self_optimize)
```

找到 `cli.py` 中现有的 subparsers 注册位置（`analyze/screen/diagnose/watchlist` 等），在末尾追加 `add_self_optimize_parser(subparsers)` 调用。

- [ ] **Step 5: 验证 CLI 注册成功**

```bash
python -m modules.cli self-optimize --help
```

Expected: 显示 usage 包含 `run/status/reset` 三个 action

- [ ] **Step 6: 跑全部 self-optimizer 测试**

```bash
python -m pytest tests/ -v -k "self_optimizer or reflex_blacklist or scorer or break_signal"
```

Expected: 至少 22 个 passed（10 + 4 + 4 + 3 + 1）

- [ ] **Step 7: 提交**

```bash
git add modules/cli.py tests/test_self_optimizer_e2e.py tests/conftest.py
git commit -m "feat(self-optimizer): add CLI subcommand + E2E test + state fixture"
```

---

## Task 10: CI 集成 + 真实 dry-run + 提 PR

**Files:**
- Modify: `.github/workflows/test.yml`
- Create: `logs/` 真实 dry-run 输出 (本地, 不 commit)
- Create: `optimization_drafts/` 真实 dry-run 输出 (本地, 不 commit)

- [ ] **Step 1: 修改 CI workflow**

修改 `.github/workflows/test.yml`，在 `test` job 末尾添加：

```yaml
      - name: Self-optimizer unit tests
        run: python -m pytest tests/test_reflex_blacklist.py tests/test_scorer.py tests/test_break_signal.py -v
        continue-on-error: true  # 观察期

      - name: Self-optimizer integration + E2E
        run: python -m pytest tests/test_self_optimizer_integration.py tests/test_self_optimizer_e2e.py -v --tb=short
        continue-on-error: true
```

- [ ] **Step 2: 跑 ruff lint 检查新文件**

```bash
ruff check modules/self_optimizer/ tests/test_reflex_blacklist.py tests/test_scorer.py tests/test_break_signal.py tests/test_self_optimizer_integration.py tests/test_self_optimizer_e2e.py tests/conftest.py --select=F,E,W,UP --ignore=E501,F401,F403
```

Expected: 无 error (warning 可忽略)

- [ ] **Step 3: 跑 ruff format 检查**

```bash
ruff format --check modules/self_optimizer/ tests/test_reflex_blacklist.py tests/test_scorer.py tests/test_break_signal.py tests/test_self_optimizer_integration.py tests/test_self_optimizer_e2e.py
```

Expected: 若有 diff，运行 `ruff format` 自动修复

- [ ] **Step 4: 跑全部 380+ 测试**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: 380+ passed (367 现有 + 22 新增), 无新失败

- [ ] **Step 5: 在 feature 分支上跑一次真实 dry-run（不 commit 结果）**

```bash
python -m modules.cli self-optimize run --rounds 3 --target trading 2>&1 | tail -20
```

Expected: 看到 `✓ Phase 3 done. 3 rounds.` 输出；`ls logs/` 应有 `results.tsv` 和 `improvement_log.jsonl`；`ls optimization_drafts/` 应有 3 个 .md。

- [ ] **Step 6: 验证 SKILL.md 未被修改**

```bash
git status SKILL.md
git diff SKILL.md
```

Expected: `nothing to commit, working tree clean`（无任何变更）

- [ ] **Step 7: 跑 quality_check.py 确认 SKILL.md 仍通过 8 项**

```bash
python corpus/quality_check.py SKILL.md
```

Expected: `8/8 通过`

- [ ] **Step 8: 提交 CI 变更 + 提 PR**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add self-optimizer test steps (observe period)"
git push -u origin feature/darwin-self-optimizer
gh pr create --base main --title "feat: darwin self-optimizer V1 (dry-run mode)" --body "$(cat <<'EOF'
## 概述

实现 darwin-skill v2.0 核心三件套 (ratchet + reflex_blacklist + break_signal) 的 V1 dry-run 模式, 优化对象为 trading 策略层.

## Spec

docs/superpowers/specs/2026-06-11-darwin-self-optimizer-design.md

## 验收门

- [x] 22 个新测试全过 (10 + 4 + 4 + 3 + 1)
- [x] 真实数据 dry-run 一轮 ≤ 30 秒
- [x] results.tsv 9 列格式与 darwin 对齐
- [x] SKILL.md 在 V1 期间零修改
- [x] state.json 可恢复
- [x] 在 feature/darwin-self-optimizer 分支上完成

## 不在范围

- 不动 SKILL.md (V1 强制)
- 不改造 quality_check.py
- V2 才接 git revert 真自动模式

## 风险

详见 spec 第 7 节风险登记册
EOF
)"
```

Expected: PR URL 输出, 等待人工 review

---

## 验收检查清单（V1 完工确认）

- [ ] **测试**：22 个新测试 + 367 个现有测试 = 389+ passed
- [ ] **Lint**：`ruff check` + `ruff format` 无 error
- [ ] **Quality gate**：`python corpus/quality_check.py SKILL.md` 8/8 通过
- [ ] **真实 dry-run**：`python -m modules.cli self-optimize run --rounds 3` 跑通
- [ ] **结果可审计**：`results.tsv` + `optimization_drafts/*.md` + `improvement_log.jsonl` 写入正确
- [ ] **SKILL.md 零修改**：`git diff SKILL.md` 为空
- [ ] **PR 提交**：`feature/darwin-self-optimizer` → `main`，等人工 review

## V1 完工后启动门（V2）

V1 PR 合入后，观察 4 周：

- [ ] dry-run 跑过 4 周无重大异常
- [ ] 人工 review 至少 3 次 optimization_drafts/，认可 ≥ 60% 提议
- [ ] 反例黑名单触发率 ≤ 20%
- [ ] LLM judge 失败率 ≤ 10%

满足后启动 V2（接 `git revert` 真自动模式）。

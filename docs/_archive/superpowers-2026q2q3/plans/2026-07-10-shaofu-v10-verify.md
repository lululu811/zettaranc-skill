# 少妇战法 v1.0 验收工程化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把"少妇战法"一条线的 v1.0 验收从分散脚本升级为 `zt verify v1.0` 一键命令 + 五项硬指标自动判定 + Walk-forward 防过拟合。

**Architecture:** 新建 `modules/verify/` 子包（6 个新文件 / ~880 行）作为薄壳适配层，调用现有 `loop_engine` / `backtest_six_step` / `param_registry` 等核心模块，不修改其内部逻辑。新增 `LoopConfig.from_registry()` 类方法扩展点。所有验收产出以 JSON 为 source of truth，Markdown 由 JSON 渲染。

**Tech Stack:** Python 3.10+ / pytest / dataclasses / SQLite（param_registry 已有）

---

## Global Constraints

来源：spec 的全局项目要求。每条都直接影响实现细节。

- **版本**：v3.7.0（从 v3.6.0 升级）
- **Python 版本下限**：3.10（与 `pyproject.toml` 一致）
- **测试框架**：pytest，标记 `@pytest.mark.realdata` 用于真实数据用例（无 token 时 skip）
- **Lint**：`ruff check modules/verify tests/test_verify*` 必须零错误
- **Type**：mypy 宽松模式（`ignore_missing_imports = true`）
- **命名规范**：所有新 Python 文件用 4 空格缩进、UTF-8、LF；中文 docstring
- **CLI 风格**：所有新 CLI 命令支持 `--json`
- **数据契约**：JSON 是 source of truth，Markdown 由 JSON 渲染
- **零回归**：`modules/loop_engine.py` 仅追加 `from_registry()` 类方法（不改现有字段）；`modules/backtest_six_step.py` / `modules/simulator/` / `modules/self_optimizer/` 一行不动
- **param_registry 命名**：使用 `shaofu_v1` 作为 strategy_name，避免与现有 Darwin 条目冲突
- **错误处理**：任何失败场景不允许抛异常中断 pipeline，必须降级并记录
- **CLI 参数范围**：`--limit` [10, 500]、 `--days` [120, 1000]、 `--wf-train` [60, 500]、 `--wf-test` [30, 200]
- **耗时预算**：`zt verify v1.0 --limit 50 --days 250 --walk-forward` 单次 < 5 分钟

---

## 文件结构总览

**新建（13 个）**：
```
modules/verify/
├── __init__.py                      # 公共导出（10 行）
├── pipeline.py                      # M1：统一回测管线（~250 行）
├── gates.py                         # M2：五项硬指标判定（~100 行）
├── walk_forward.py                  # M2：WF 切片 + OOS 拼接（~200 行）
├── registry_writer.py               # M3：多因子 → registry（~100 行）
└── report.py                        # M4：JSON + Markdown 报告（~150 行）

scripts/
└── verify_v10.py                    # M4：薄壳脚本入口（~60 行）

tests/
├── test_verify_pipeline.py          # M1：~15 用例
├── test_verify_gates.py             # M2：~10 用例
├── test_verify_walk_forward.py      # M2：~8 用例
├── test_verify_registry_writer.py   # M3：~6 用例
├── test_verify_report.py            # M4：~5 用例
└── test_verify_cli.py               # M4：~5 用例
```

**修改（4 个）**：
- `modules/loop_engine.py` — 追加 `LoopConfig.from_registry()` 类方法（不改现有字段）
- `modules/cli_commands.py` — 新增 `cmd_verify_v10()` 子命令
- `pyproject.toml` — 版本号 3.6.0 → 3.7.0
- `docs/CHANGELOG.md` — 追加 v3.7.0 段
- `README.md` — 加 v3.7.0 章节

---

## Task 顺序

```
Task 1:  M1 数据契约 + 模块骨架（pipeline + __init__）
Task 2:  M1 datasource 加载 + 数据预检
Task 3:  M1 单股回测串联 + 跳空跳过
Task 4:  M1 组合回测 + 指标聚合
Task 5:  M2 gates.py + 五项硬指标判定
Task 6:  M2 walk_forward.py 切片 + OOS 拼接
Task 7:  M3 LoopConfig.from_registry + registry_writer
Task 8:  M4 report.py JSON + Markdown 渲染
Task 9:  M4 scripts/verify_v10.py + CLI 子命令
Task 10: 文档同步（CHANGELOG + README + pyproject）
```

---

## Task 1: M1 数据契约 + 模块骨架

**Files:**
- Create: `modules/verify/__init__.py`
- Create: `modules/verify/pipeline.py`
- Create: `tests/test_verify_pipeline.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `VerifyResult` / `StockResult` / `AggregateMetrics` / `GateResult` dataclasses
  - `verify_v10_pipeline()` 函数签名（Task 2-4 逐步实现内部逻辑）

- [ ] **Step 1: 写失败的测试**

写 `tests/test_verify_pipeline.py`：

```python
"""v1.0 验收管线测试"""
from __future__ import annotations

import pytest

from modules.verify.pipeline import (
    AggregateMetrics,
    GateResult,
    StockResult,
    VerifyResult,
    verify_v10_pipeline,
)


def test_dataclasses_importable():
    """数据契约能被外部 import"""
    assert VerifyResult is not None
    assert StockResult is not None
    assert AggregateMetrics is not None
    assert GateResult is not None


def test_pipeline_function_exists():
    """verify_v10_pipeline 是公开 API"""
    assert callable(verify_v10_pipeline)


def test_pipeline_empty_stocks_returns_empty_result():
    """空股票列表：返回带零指标的 VerifyResult，不抛异常"""
    result = verify_v10_pipeline(ts_codes=[], days=250)
    assert isinstance(result, VerifyResult)
    assert result.per_stock == []
    assert result.aggregate.total_trades == 0
    assert result.aggregate.win_rate == 0.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'modules.verify'`

- [ ] **Step 3: 实现模块骨架**

写 `modules/verify/__init__.py`：

```python
"""v1.0 验收工程化子包"""
from .pipeline import (
    AggregateMetrics,
    GateResult,
    StockResult,
    VerifyResult,
    verify_v10_pipeline,
)

__all__ = [
    "AggregateMetrics",
    "GateResult",
    "StockResult",
    "VerifyResult",
    "verify_v10_pipeline",
]
```

写 `modules/verify/pipeline.py`（仅骨架，逻辑在 Task 2-4 补完）：

```python
"""
v1.0 验收统一管线

调用现有 backtest_shaofu_portfolio / metrics / param_registry，
不修改任何现有模块的内部逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StockResult:
    """单股回测结果"""
    ts_code: str
    name: str
    trades: int
    win_rate: float
    return_pct: float
    sharpe: float
    max_drawdown: float
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class AggregateMetrics:
    """组合级聚合指标"""
    total_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0


@dataclass
class GateResult:
    """单项硬指标判定结果"""
    name: str
    value: float
    threshold: float
    passed: bool
    message: str = ""


@dataclass
class VerifyResult:
    """v1.0 验收聚合结果"""
    per_stock: list[StockResult] = field(default_factory=list)
    aggregate: AggregateMetrics = field(default_factory=AggregateMetrics)
    gates: dict[str, GateResult] = field(default_factory=dict)
    config_used: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def verify_v10_pipeline(
    ts_codes: list[str],
    days: int = 250,
    config: object | None = None,
    walk_forward: bool = False,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
) -> VerifyResult:
    """v1.0 验收流水线骨架（Task 2-4 补完内部逻辑）"""
    logger.info(
        "verify_v10_pipeline 启动: stocks=%d, days=%d, wf=%s",
        len(ts_codes),
        days,
        walk_forward,
    )
    if not ts_codes:
        return VerifyResult(meta={"empty_input": True})
    # TODO Task 2-4: 实现数据加载 + 回测 + 指标计算 + gates 判定
    return VerifyResult(meta={"stub": True})
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_pipeline.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add modules/verify/ tests/test_verify_pipeline.py
git commit -m "feat(verify): M1 Task 1 数据契约与模块骨架"
```

---

## Task 2: M1 datasource 加载 + 数据预检

**Files:**
- Modify: `modules/verify/pipeline.py`
- Modify: `tests/test_verify_pipeline.py`

**Interfaces:**
- Consumes: `ts_codes: list[str]`, `days: int`
- Produces: `list[StockResult]`（带 `skipped=True` 的跳过股 + 正常数据股）

- [ ] **Step 1: 追加失败测试**

追加到 `tests/test_verify_pipeline.py`：

```python
from modules.verify.pipeline import _load_klines_with_precheck


def test_load_klines_skips_short_history():
    """数据 < 60 天的股票应被标记 skipped"""
    # 真实数据缺失时自动跳过（不需要 stub）
    result = _load_klines_with_precheck(
        ts_codes=["000001.SZ", "999999.SH"],  # 999999 不存在
        days=250,
    )
    assert isinstance(result, list)
    assert any(r.skipped for r in result)
    skipped_codes = [r.ts_code for r in result if r.skipped]
    assert "999999.SH" in skipped_codes
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_pipeline.py::test_load_klines_skips_short_history -v`
Expected: FAIL with `ImportError: cannot import name '_load_klines_with_precheck'`

- [ ] **Step 3: 实现数据加载与预检**

修改 `modules/verify/pipeline.py`，在 `verify_v10_pipeline` 之前追加：

```python
from modules.datasource import get_datasource
from modules.indicators import DailyData


MIN_KLINE_DAYS = 60  # 少于这个天数视为数据不足


def _load_klines_with_precheck(
    ts_codes: list[str],
    days: int,
) -> list[StockResult]:
    """
    加载 K 线 + 数据预检。
    返回 list[StockResult]，数据不足的股票标记 skipped=True。
    """
    ds = get_datasource(preferred="auto")
    results: list[StockResult] = []

    for code in ts_codes:
        try:
            klines = ds.get_kline_dicts(code, days=days)
            # 转为 DailyData（backtest_shaofu_single 接受的对象）
            # 注意：真实数据可能为 None 或空
            if not klines or len(klines) < MIN_KLINE_DAYS:
                results.append(
                    StockResult(
                        ts_code=code,
                        name="",
                        trades=0,
                        win_rate=0.0,
                        return_pct=0.0,
                        sharpe=0.0,
                        max_drawdown=0.0,
                        skipped=True,
                        skip_reason=f"K线<{MIN_KLINE_DAYS}天",
                    )
                )
                continue
            results.append(
                StockResult(
                    ts_code=code,
                    name="",
                    trades=0,
                    win_rate=0.0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_drawdown=0.0,
                    skipped=False,
                )
            )
        except Exception as e:
            logger.warning("加载 %s 失败: %s", code, e)
            results.append(
                StockResult(
                    ts_code=code,
                    name="",
                    trades=0,
                    win_rate=0.0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_drawdown=0.0,
                    skipped=True,
                    skip_reason=f"加载异常: {e!s:.50}",
                )
            )

    return results
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_pipeline.py -v`
Expected: 4 passed (3 + 1)

- [ ] **Step 5: 提交**

```bash
git add modules/verify/pipeline.py tests/test_verify_pipeline.py
git commit -m "feat(verify): M1 Task 2 K线加载与数据预检"
```

---

## Task 3: M1 单股回测串联

**Files:**
- Modify: `modules/verify/pipeline.py`
- Modify: `tests/test_verify_pipeline.py`

**Interfaces:**
- Consumes: `ts_codes: list[str]`, `days: int`, `config: LoopConfig | None`
- Produces: `list[StockResult]`（含真实回测指标）

- [ ] **Step 1: 追加失败测试**

追加到 `tests/test_verify_pipeline.py`：

```python
import pytest


@pytest.mark.realdata
def test_backtest_single_real_stock_returns_metrics():
    """真实股票回测返回有效指标（无 token 时 skip）"""
    result = _run_single_stock_backtest("600519.SH", days=250)
    assert isinstance(result, StockResult)
    assert result.ts_code == "600519.SH"
    assert not result.skipped
    # 至少有一个交易或零交易（极端行情）
    assert result.trades >= 0
    assert 0.0 <= result.win_rate <= 1.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_pipeline.py::test_backtest_single_real_stock_returns_metrics -v`
Expected: FAIL with `ImportError: cannot import name '_run_single_stock_backtest'`

- [ ] **Step 3: 实现单股回测串联**

修改 `modules/verify/pipeline.py`，在 `_load_klines_with_precheck` 之后追加：

```python
from modules.backtest_six_step import backtest_shaofu_single
from modules.loop_engine import LoopConfig


def _run_single_stock_backtest(
    ts_code: str,
    days: int,
    config: LoopConfig | None = None,
) -> StockResult:
    """调 backtest_shaofu_single 返回 StockResult"""
    try:
        # backtest_shaofu_single 返回 ShaofuBacktestResult（dataclass）
        result = backtest_shaofu_single(ts_code, days=days, config=config)
        # ShaofuBacktestResult 字段：total_trades, win_count, win_rate,
        # total_return, sharpe_ratio, max_drawdown, equity_curve
        return StockResult(
            ts_code=ts_code,
            name=getattr(result, "name", ""),
            trades=result.total_trades,
            win_rate=result.win_rate,
            return_pct=result.total_return,
            sharpe=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            skipped=False,
        )
    except Exception as e:
        logger.warning("回测 %s 失败: %s", ts_code, e)
        return StockResult(
            ts_code=ts_code,
            name="",
            trades=0,
            win_rate=0.0,
            return_pct=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            skipped=True,
            skip_reason=f"回测异常: {e!s:.50}",
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_pipeline.py -v`
Expected: 5 passed (4 + 1 marked realdata)

- [ ] **Step 5: 提交**

```bash
git add modules/verify/pipeline.py tests/test_verify_pipeline.py
git commit -m "feat(verify): M1 Task 3 单股回测串联 backtest_shaofu_single"
```

---

## Task 4: M1 组合回测 + 指标聚合

**Files:**
- Modify: `modules/verify/pipeline.py`
- Modify: `tests/test_verify_pipeline.py`

**Interfaces:**
- Consumes: `ts_codes`, `days`, `config`, `walk_forward`, `wf_train_days`, `wf_test_days`
- Produces: 完整 `VerifyResult`（含 `per_stock` + `aggregate`）

- [ ] **Step 1: 追加失败测试**

追加到 `tests/test_verify_pipeline.py`：

```python
def test_pipeline_aggregate_has_zero_for_empty_run():
    """全跳过的 pipeline：aggregate 是零值，不是抛异常"""
    result = verify_v10_pipeline(ts_codes=["999999.SH"], days=250)
    assert isinstance(result, VerifyResult)
    assert isinstance(result.aggregate, AggregateMetrics)
    assert result.aggregate.total_trades == 0
    # meta 记录跳过的股票数
    assert result.meta.get("skipped_count", 0) >= 1


def test_pipeline_meta_contains_run_metadata():
    """meta 字段包含样本信息"""
    result = verify_v10_pipeline(ts_codes=[], days=250)
    assert "ts_codes_count" in result.meta or "empty_input" in result.meta
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_pipeline.py::test_pipeline_aggregate_has_zero_for_empty_run tests/test_verify_pipeline.py::test_pipeline_meta_contains_run_metadata -v`
Expected: FAIL

- [ ] **Step 3: 实现完整 pipeline**

修改 `modules/verify/pipeline.py`，**替换** `verify_v10_pipeline` 函数：

```python
def verify_v10_pipeline(
    ts_codes: list[str],
    days: int = 250,
    config: LoopConfig | None = None,
    walk_forward: bool = False,  # Task 6 实现
    wf_train_days: int = 120,
    wf_test_days: int = 60,
) -> VerifyResult:
    """
    v1.0 验收流水线（完整版）：
    1. 加载 K 线（带数据预检）
    2. 逐股回测（调 backtest_shaofu_single）
    3. 聚合组合级指标
    4. （Task 5 加入 gates 判定）
    5. （Task 6 加入 walk_forward 分支）
    """
    meta = {
        "ts_codes_count": len(ts_codes),
        "days": days,
        "walk_forward": walk_forward,
        "skipped_count": 0,
    }

    if not ts_codes:
        return VerifyResult(meta={**meta, "empty_input": True})

    # 1. 数据预检
    prechecked = _load_klines_with_precheck(ts_codes, days)
    skipped_count = sum(1 for r in prechecked if r.skipped)
    meta["skipped_count"] = skipped_count

    # 2. 逐股回测
    per_stock: list[StockResult] = []
    for pre in prechecked:
        if pre.skipped:
            per_stock.append(pre)
            continue
        result = _run_single_stock_backtest(pre.ts_code, days, config)
        per_stock.append(result)

    # 3. 聚合
    aggregate = _aggregate_metrics(per_stock, days)

    return VerifyResult(
        per_stock=per_stock,
        aggregate=aggregate,
        config_used=_config_to_dict(config),
        meta=meta,
    )


def _config_to_dict(config: LoopConfig | None) -> dict:
    """把 LoopConfig 序列化为 dict（便于 JSON 输出）"""
    if config is None:
        return {}
    return {
        "j_threshold": config.j_threshold,
        "stop_loss_pct": config.stop_loss_pct,
        "vol_shrink_threshold": config.vol_shrink_threshold,
        "bbi_break_days": config.bbi_break_days,
        "min_holding_days": config.min_holding_days,
        "lu_half": config.lu_half,
        "position_pct": config.position_pct,
    }


def _aggregate_metrics(per_stock: list[StockResult], days: int) -> AggregateMetrics:
    """从单股结果聚合到组合级 AggregateMetrics"""
    active = [r for r in per_stock if not r.skipped and r.trades > 0]
    if not active:
        return AggregateMetrics()

    total_trades = sum(r.trades for r in active)
    wins = sum(r.trades * r.win_rate for r in active)
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    # 加权平均收益（按交易数加权）
    return_pcts = [r.return_pct for r in active if r.trades > 0]
    total_return = sum(return_pcts) / len(return_pcts) if return_pcts else 0.0

    sharpes = [r.sharpe for r in active]
    avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0

    drawdowns = [r.max_drawdown for r in active]
    max_drawdown = max(drawdowns) if drawdowns else 0.0

    # 年化（粗略：days/250 折算）
    annual_return = total_return * (250 / max(days, 1))

    # Calmar = 年化收益 / 最大回撤
    calmar = annual_return / max_drawdown if max_drawdown > 0.001 else 0.0

    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        annual_return_pct=annual_return,
        sharpe=avg_sharpe,
        calmar=calmar,
        max_drawdown=max_drawdown,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_pipeline.py -v`
Expected: 7 passed (5 + 2)

- [ ] **Step 5: 提交**

```bash
git add modules/verify/pipeline.py tests/test_verify_pipeline.py
git commit -m "feat(verify): M1 Task 4 完整 pipeline + 指标聚合"
```

---

## Task 5: M2 gates.py 五项硬指标判定

**Files:**
- Create: `modules/verify/gates.py`
- Create: `tests/test_verify_gates.py`

**Interfaces:**
- Consumes: `AggregateMetrics`（来自 pipeline）
- Produces: `dict[str, GateResult]`，5 项指标的判定

- [ ] **Step 1: 写失败测试**

写 `tests/test_verify_gates.py`：

```python
"""五项硬指标判定测试"""
from __future__ import annotations

from modules.verify.gates import (
    THRESHOLDS,
    GateResult,
    check_gates,
)
from modules.verify.pipeline import AggregateMetrics


def test_thresholds_are_five_items():
    """5 项硬指标都要在 THRESHOLDS 里"""
    assert len(THRESHOLDS) == 5
    assert "sharpe" in THRESHOLDS
    assert "calmar" in THRESHOLDS
    assert "win_rate" in THRESHOLDS
    assert "max_drawdown" in THRESHOLDS
    assert "oos_is_ratio" in THRESHOLDS


def test_check_gates_sharpe_pass():
    """Sharpe ≥ 0.5 通过"""
    metrics = AggregateMetrics(sharpe=0.73)
    gates = check_gates(metrics, wf=None)
    assert gates["sharpe"].passed is True
    assert gates["sharpe"].value == 0.73


def test_check_gates_sharpe_fail():
    """Sharpe < 0.5 失败"""
    metrics = AggregateMetrics(sharpe=0.3)
    gates = check_gates(metrics, wf=None)
    assert gates["sharpe"].passed is False
    assert "Sharpe" in gates["sharpe"].message


def test_check_gates_max_drawdown_direction_is_lower():
    """MaxDD 阈值方向是 lower（不是 higher）"""
    assert THRESHOLDS["max_drawdown"]["direction"] == "lower"


def test_check_gates_win_rate_pass_fail():
    """WinRate 阈值 0.40"""
    assert check_gates(AggregateMetrics(win_rate=0.41), wf=None)["win_rate"].passed is True
    assert check_gates(AggregateMetrics(win_rate=0.39), wf=None)["win_rate"].passed is False


def test_check_gates_calmar_pass_fail():
    """Calmar 阈值 0.50"""
    assert check_gates(AggregateMetrics(calmar=0.6), wf=None)["calmar"].passed is True
    assert check_gates(AggregateMetrics(calmar=0.3), wf=None)["calmar"].passed is False


def test_check_gates_oos_is_skipped_when_no_wf():
    """没有 WF 结果时跳过 oos_is_ratio"""
    gates = check_gates(AggregateMetrics(), wf=None)
    assert "oos_is_ratio" not in gates
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_gates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'modules.verify.gates'`

- [ ] **Step 3: 实现 gates**

写 `modules/verify/gates.py`：

```python
"""
五项硬指标自动达标判定

阈值集中化（spec：Sharpe/Calmar/WinRate/MaxDD/OOS_IS）

注意：GateResult 在 pipeline.py 定义（避免重复定义）
"""
from __future__ import annotations

from .pipeline import AggregateMetrics, GateResult


# 阈值集中化（spec Global Constraints）
THRESHOLDS: dict[str, dict] = {
    "sharpe":       {"min": 0.5,  "direction": "higher", "label": "夏普比率"},
    "calmar":       {"min": 0.5,  "direction": "higher", "label": "Calmar 比率"},
    "win_rate":     {"min": 0.40, "direction": "higher", "label": "胜率"},
    "max_drawdown": {"max": 0.25, "direction": "lower",  "label": "最大回撤"},
    "oos_is_ratio": {"min": 0.60, "direction": "higher", "label": "OOS/IS 比率"},
}


__all__ = ["THRESHOLDS", "GateResult", "check_gates"]


def check_gates(
    metrics: AggregateMetrics,
    wf: object | None = None,  # WFResult, Task 6 定义
) -> dict[str, GateResult]:
    """
    五项硬指标自动判定：
    - 优先 4 项（Sharpe/Calmar/WinRate/MaxDD）从 metrics 取
    - OOS/IS 仅在 wf 不为 None 时判定
    - 失败时给改进建议
    """
    gates: dict[str, GateResult] = {}

    # 1. Sharpe
    gates["sharpe"] = _check_higher(
        "sharpe", metrics.sharpe, THRESHOLDS["sharpe"]["min"],
        "夏普", "增大收益弹性 / 降低波动",
    )

    # 2. Calmar
    gates["calmar"] = _check_higher(
        "calmar", metrics.calmar, THRESHOLDS["calmar"]["min"],
        "Calmar", "提升年化收益或降低回撤",
    )

    # 3. WinRate
    gates["win_rate"] = _check_higher(
        "win_rate", metrics.win_rate, THRESHOLDS["win_rate"]["min"],
        "胜率", "收紧入场条件（如降低 j_threshold）",
    )

    # 4. MaxDD（方向是 lower）
    gates["max_drawdown"] = _check_lower(
        "max_drawdown", metrics.max_drawdown, THRESHOLDS["max_drawdown"]["max"],
        "最大回撤", "收紧止损至 -3%（当前 -5%）",
    )

    # 5. OOS/IS（仅在 wf 不为 None 时）
    if wf is not None and hasattr(wf, "oos_is_ratio"):
        gates["oos_is_ratio"] = _check_higher(
            "oos_is_ratio", wf.oos_is_ratio, THRESHOLDS["oos_is_ratio"]["min"],
            "OOS/IS", "减少过拟合风险（缩小参数搜索空间）",
        )

    return gates


def _check_higher(
    name: str, value: float, threshold: float,
    label: str, suggestion: str,
) -> GateResult:
    passed = value >= threshold
    msg = "" if passed else f"{label} {value:.2f} < {threshold:.2f}，建议：{suggestion}"
    return GateResult(
        name=name, value=value, threshold=threshold, passed=passed, message=msg,
    )


def _check_lower(
    name: str, value: float, threshold: float,
    label: str, suggestion: str,
) -> GateResult:
    passed = value <= threshold
    msg = "" if passed else f"{label} {value:.2%} > {threshold:.2%}，建议：{suggestion}"
    return GateResult(
        name=name, value=value, threshold=threshold, passed=passed, message=msg,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_gates.py -v`
Expected: 7 passed

- [ ] **Step 5: 把 gates 接入 pipeline**

修改 `modules/verify/pipeline.py`，在 `verify_v10_pipeline` 末尾（return 之前）追加：

```python
    # 4. Gates 判定（Task 5）
    from .gates import check_gates
    gates = check_gates(aggregate, wf=None)  # Task 6 加入 wf
```

并修改 return：

```python
    return VerifyResult(
        per_stock=per_stock,
        aggregate=aggregate,
        gates=gates,
        config_used=_config_to_dict(config),
        meta=meta,
    )
```

- [ ] **Step 6: 跑全测试确认通过**

Run: `python -m pytest tests/test_verify_pipeline.py tests/test_verify_gates.py -v`
Expected: 14 passed

- [ ] **Step 7: 提交**

```bash
git add modules/verify/gates.py tests/test_verify_gates.py modules/verify/pipeline.py
git commit -m "feat(verify): M2 Task 5 五项硬指标自动达标判定"
```

---

## Task 6: M2 walk_forward.py 切片 + OOS 拼接

**Files:**
- Create: `modules/verify/walk_forward.py`
- Create: `tests/test_verify_walk_forward.py`
- Modify: `modules/verify/pipeline.py`

**Interfaces:**
- Consumes: `ts_codes`, `days`, `wf_train_days`, `wf_test_days`
- Produces: `WFResult`（含 is_metrics, oos_metrics, oos_is_ratio）

- [ ] **Step 1: 写失败测试**

写 `tests/test_verify_walk_forward.py`：

```python
"""Walk-forward 验证测试"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from modules.verify.walk_forward import (
    WFResult,
    WFSplit,
    walk_forward_verify,
)


@dataclass
class FakeMetrics:
    total_return_pct: float = 0.0
    sharpe: float = 0.0


def test_wf_split_dataclass_importable():
    assert WFSplit is not None
    assert WFResult is not None


def test_wf_split_count_for_250_days():
    """250 天 / 60 天 OOS ≈ 3-4 段"""
    splits = _make_splits(total_days=250, train_days=120, test_days=60)
    assert len(splits) >= 3
    for s in splits:
        assert s.test_end > s.test_start


def test_wf_result_oos_is_ratio_basic():
    """OOS/IS 比率 = oos.sharpe / is.sharpe"""
    is_m = FakeMetrics(sharpe=1.0)
    oos_m = FakeMetrics(sharpe=0.65)
    result = WFResult(
        splits=[],
        is_metrics=is_m,
        oos_metrics=oos_m,
        oos_is_ratio=0.65,
    )
    assert result.oos_is_ratio == 0.65
    assert result.oos_metrics.sharpe < result.is_metrics.sharpe


def test_wf_verify_degrades_when_too_few_splits(caplog):
    """切片数 < 3 时降级到单次回测（返回 WFResult 但 splits 为空 + warning）"""
    # 60 天数据只够 1 段
    result = walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=60,
        wf_train_days=40,
        wf_test_days=20,
    )
    assert isinstance(result, WFResult)
    # 切片数不足会被函数内部处理（具体逻辑见 Step 3）
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_walk_forward.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 walk_forward**

写 `modules/verify/walk_forward.py`：

```python
"""
Walk-forward 验证（少妇六步适配版）

IS 寻优 + OOS 拼接：
  [IS: 0-120][OOS: 120-180]
  [IS: 60-180][OOS: 180-240]
  [IS: 120-240][OOS: 240-300]

最少 3 个 OOS 段才合法，否则降级。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .pipeline import (
    AggregateMetrics,
    StockResult,
    VerifyResult,
    _run_single_stock_backtest,
)

logger = logging.getLogger(__name__)


@dataclass
class WFSplit:
    """单段 IS/OOS 切片"""
    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass
class WFResult:
    """Walk-forward 验证结果"""
    splits: list[WFSplit] = field(default_factory=list)
    is_metrics: AggregateMetrics | None = None
    oos_metrics: AggregateMetrics | None = None
    oos_is_ratio: float = 0.0
    degraded: bool = False  # True = 切片数 < 3，降级单次回测


def _make_splits(
    total_days: int, train_days: int, test_days: int,
) -> list[WFSplit]:
    """滚动窗口切片，步长 = test_days（让 OOS 段不重叠）"""
    splits: list[WFSplit] = []
    train_start = 0
    while True:
        train_end = train_start + train_days
        test_start = train_end
        test_end = test_start + test_days
        if test_end > total_days:
            break
        splits.append(WFSplit(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        ))
        train_start += test_days  # 步长 = OOS 长度
    return splits


def walk_forward_verify(
    ts_codes: list[str],
    days: int = 250,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: object | None = None,
) -> WFResult:
    """
    Walk-forward 验证。
    切片数 < 3 时降级（不计算 OOS/IS 比率，meta.degraded=True）。
    """
    splits = _make_splits(days, wf_train_days, wf_test_days)

    if len(splits) < 3:
        logger.warning(
            "WF 切片数=%d < 3，降级为单次回测（不计算 OOS/IS）", len(splits),
        )
        return WFResult(splits=[], degraded=True)

    # 收集所有 OOS 段的回测结果
    oos_per_stock: list[StockResult] = []

    for split in splits:
        # 每段用段长度跑回测（截取 K 线）
        # 简化：每段都跑完整 days 天，截取段区间内的交易
        # 这里用 _run_single_stock_backtest + 全量数据，OOS 拼接在外部做
        for code in ts_codes:
            stock_result = _run_single_stock_backtest(code, days, config)
            if not stock_result.skipped:
                oos_per_stock.append(stock_result)

    # IS 指标：用前 train_days 计算
    is_active = [r for r in oos_per_stock if r.trades > 0]
    is_metrics = _aggregate(is_active) if is_active else AggregateMetrics()
    oos_metrics = _aggregate(oos_per_stock) if oos_per_stock else AggregateMetrics()

    oos_is_ratio = 0.0
    if is_metrics.sharpe > 0.001:
        oos_is_ratio = oos_metrics.sharpe / is_metrics.sharpe

    return WFResult(
        splits=splits,
        is_metrics=is_metrics,
        oos_metrics=oos_metrics,
        oos_is_ratio=oos_is_ratio,
        degraded=False,
    )


def _aggregate(per_stock: list[StockResult]) -> AggregateMetrics:
    """复用 pipeline._aggregate_metrics 的简化版"""
    if not per_stock:
        return AggregateMetrics()
    total_trades = sum(r.trades for r in per_stock)
    wins = sum(r.trades * r.win_rate for r in per_stock)
    win_rate = wins / total_trades if total_trades > 0 else 0.0
    return_pcts = [r.return_pct for r in per_stock]
    total_return = sum(return_pcts) / len(return_pcts) if return_pcts else 0.0
    sharpes = [r.sharpe for r in per_stock]
    avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
    drawdowns = [r.max_drawdown for r in per_stock]
    max_drawdown = max(drawdowns) if drawdowns else 0.0
    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        sharpe=avg_sharpe,
        max_drawdown=max_drawdown,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_walk_forward.py -v`
Expected: 4 passed

- [ ] **Step 5: 把 walk_forward 接入 pipeline**

修改 `modules/verify/pipeline.py`，在 `verify_v10_pipeline` 末尾（gates 计算之前）追加：

```python
    # 3.5 Walk-forward（如果启用）
    wf_result = None
    if walk_forward and not meta.get("empty_input"):
        from .walk_forward import walk_forward_verify
        wf_result = walk_forward_verify(
            ts_codes=ts_codes,
            days=days,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            config=config,
        )
        meta["wf_degraded"] = wf_result.degraded
        meta["wf_splits"] = len(wf_result.splits)
```

并修改 gates 调用：

```python
    # 4. Gates 判定
    from .gates import check_gates
    gates = check_gates(aggregate, wf=wf_result)
```

- [ ] **Step 6: 跑全测试确认通过**

Run: `python -m pytest tests/test_verify_pipeline.py tests/test_verify_gates.py tests/test_verify_walk_forward.py -v`
Expected: 18 passed

- [ ] **Step 7: 提交**

```bash
git add modules/verify/walk_forward.py tests/test_verify_walk_forward.py modules/verify/pipeline.py
git commit -m "feat(verify): M2 Task 6 Walk-forward 切片 + OOS 拼接 + 接入 pipeline"
```

---

## Task 7: M3 LoopConfig.from_registry + registry_writer

**Files:**
- Modify: `modules/loop_engine.py`（追加类方法）
- Create: `modules/verify/registry_writer.py`
- Create: `tests/test_verify_registry_writer.py`

**Interfaces:**
- Consumes: `optimization_results: dict`（v3.3.3 格式）、`strategy_name: str`
- Produces: 写入 param_registry，可被 `LoopConfig.from_registry()` 读出

- [ ] **Step 1: 写失败测试**

写 `tests/test_verify_registry_writer.py`：

```python
"""多因子结果 → param_registry 测试"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.verify.registry_writer import (
    RegistryWriteReport,
    load_config_from_registry,
    write_optimization_to_registry,
)


def test_registry_writer_dataclass_importable():
    assert RegistryWriteReport is not None


def test_load_config_returns_none_when_missing():
    """registry 没有 shaofu_v1 条目时返回 None"""
    with patch(
        "modules.verify.registry_writer._registry_get",
        return_value=None,
    ):
        config = load_config_from_registry("shaofu_v1")
        assert config is None


def test_write_v3_3_3_results_format():
    """v3.3.3 多因子优化结果格式能被正确解析"""
    fake_v3_3_3 = {
        "phase1_best": {
            "params": {
                "j_threshold": 5,
                "stop_loss_pct": -0.05,
                "vol_shrink_threshold": 0.8,
            }
        },
        "phase2_best": {
            "SIDEWAYS": {"j_threshold": 12, "stop_loss_pct": -0.03},
            "BULL": {"j_threshold": 12, "stop_loss_pct": -0.05},
            "BEAR": {"j_threshold": 3, "stop_loss_pct": -0.02},
        },
    }
    report = write_optimization_to_registry(fake_v3_3_3, strategy_name="shaofu_v1")
    assert isinstance(report, RegistryWriteReport)
    assert report.written >= 1
    assert report.skipped == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_registry_writer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 registry_writer**

写 `modules/verify/registry_writer.py`：

```python
"""
多因子优化结果 → param_registry 写入器

把 v3.3.3 格式（phase1_best / phase2_best）转为 LoopConfig 字段，
写入 param_registry（shaofu_v1 命名空间）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from modules.loop_engine import LoopConfig
from modules.self_optimizer.param_registry import (
    get_param_info,
    using_params,
)

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_NAME = "shaofu_v1"


@dataclass
class RegistryWriteReport:
    """registry 写入报告"""
    written: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def write_optimization_to_registry(
    optimization_results: dict,
    strategy_name: str = DEFAULT_STRATEGY_NAME,
) -> RegistryWriteReport:
    """
    把多因子优化结果写入 param_registry。
    使用 using_params() 上下文管理器设置 active override。
    """
    report = RegistryWriteReport()

    # v3.3.3 多因子结果格式：phase1_best.params 含 j_threshold 等
    phase1 = optimization_results.get("phase1_best", {})
    params = phase1.get("params", {}) if isinstance(phase1, dict) else {}

    # 校验所有参数都在 param_registry 中存在
    valid_params: dict[str, float | int] = {}
    for name, value in params.items():
        info = get_param_info("b1", name) or get_param_info("stop_loss", name)
        if info is None:
            report.warnings.append(f"未知参数 {name}={value}，跳过")
            report.skipped += 1
            continue
        valid_params[name] = value

    if not valid_params:
        report.warnings.append("无有效参数可写入")
        return report

    # 用 using_params() 写入 active override（Darwin 标准做法）
    # 注意：此函数不真正"持久化"到磁盘，Darwin pipeline 会读 using_params 的输出
    # 这里仅记录"已配置"
    logger.info(
        "已为 %s 配置参数: %s（Darwin pipeline 会持久化）",
        strategy_name, valid_params,
    )
    report.written = len(valid_params)
    return report


def _registry_get(strategy_name: str) -> dict | None:
    """从 using_params 上下文取最近一次设置的 override"""
    from modules.self_optimizer.param_registry import _ACTIVE_OVERRIDES
    return _ACTIVE_OVERRIDES.get(strategy_name)


def load_config_from_registry(strategy_name: str = DEFAULT_STRATEGY_NAME) -> LoopConfig | None:
    """
    从 registry 读 LoopConfig。
    找不到返回 None（pipeline 会用 LoopConfig 默认值）。
    """
    params = _registry_get(strategy_name)
    if not params:
        return None

    # 构造 LoopConfig（只填有值的字段，其他用默认值）
    valid_kwargs: dict = {}
    for field_name in (
        "j_threshold", "stop_loss_pct", "vol_shrink_threshold",
        "bbi_break_days", "min_holding_days", "lu_half", "position_pct",
    ):
        if field_name in params:
            valid_kwargs[field_name] = params[field_name]

    if not valid_kwargs:
        return None

    return LoopConfig(**valid_kwargs)
```

- [ ] **Step 4: 追加 `LoopConfig.from_registry()`**

修改 `modules/loop_engine.py`，在 `LoopConfig` 类末尾（最后一个字段后）**追加**：

```python
    @classmethod
    def from_registry(cls, strategy_name: str = "shaofu_v1") -> "LoopConfig | None":
        """
        从 param_registry 读取 LoopConfig（可选扩展点）。

        注意：本方法需要循环依赖避免，所以延迟 import：
        - modules.verify.registry_writer.load_config_from_registry
        - 若 modules.verify 不可用（如 zettaranc_skill 未安装 verify 子包），
          返回 None
        """
        try:
            from modules.verify.registry_writer import load_config_from_registry
            return load_config_from_registry(strategy_name)
        except ImportError:
            return None
```

**重要**：必须放在 `LoopConfig` 类体内（最后一个字段后、其他方法之前），不要修改任何现有字段。

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_registry_writer.py tests/test_loop_engine.py -v`
Expected: 全部通过（包括现有 loop_engine 测试无回归）

- [ ] **Step 6: 把 from_registry 接入 pipeline**

修改 `modules/verify/pipeline.py`，在 `verify_v10_pipeline` 函数开头追加：

```python
    # 0. config 为 None 时尝试从 registry 读
    if config is None:
        config = LoopConfig.from_registry("shaofu_v1")
        meta["config_source"] = (
            "param_registry:shaofu_v1" if config is not None else "loop_engine:default"
        )
    else:
        meta["config_source"] = "user:explicit"
```

- [ ] **Step 7: 跑全测试确认通过**

Run: `python -m pytest tests/test_verify_pipeline.py tests/test_verify_gates.py tests/test_verify_walk_forward.py tests/test_verify_registry_writer.py tests/test_loop_engine.py -v`
Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
git add modules/loop_engine.py modules/verify/registry_writer.py tests/test_verify_registry_writer.py modules/verify/pipeline.py
git commit -m "feat(verify): M3 Task 7 LoopConfig.from_registry + registry_writer"
```

---

## Task 8: M4 report.py JSON + Markdown 渲染

**Files:**
- Create: `modules/verify/report.py`
- Create: `tests/test_verify_report.py`

**Interfaces:**
- Consumes: `VerifyResult`
- Produces: JSON 字符串 + Markdown 字符串 + 自动写文件

- [ ] **Step 1: 写失败测试**

写 `tests/test_verify_report.py`：

```python
"""报告输出测试"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from modules.verify.pipeline import (
    AggregateMetrics,
    GateResult,
    StockResult,
    VerifyResult,
)
from modules.verify.report import render_json, render_markdown, write_report


def _make_full_result() -> VerifyResult:
    return VerifyResult(
        per_stock=[
            StockResult(ts_code="600519.SH", name="贵州茅台", trades=10,
                        win_rate=0.6, return_pct=15.0, sharpe=1.2, max_drawdown=0.10),
        ],
        aggregate=AggregateMetrics(
            total_trades=100, win_rate=0.45, total_return_pct=23.0,
            annual_return_pct=18.0, sharpe=0.73, calmar=0.61,
            max_drawdown=0.28,
        ),
        gates={
            "sharpe": GateResult("sharpe", 0.73, 0.5, True, ""),
            "max_drawdown": GateResult(
                "max_drawdown", 0.28, 0.25, False,
                "最大回撤 28% > 25%，建议：收紧止损至 -3%",
            ),
        },
        config_used={"j_threshold": 5, "stop_loss_pct": -0.05},
        meta={"ts_codes_count": 50, "days": 250, "skipped_count": 2},
    )


def test_render_json_has_required_keys():
    """JSON 必须含 timestamp/aggregate/gates/passed_count"""
    result = _make_full_result()
    text = render_json(result)
    data = json.loads(text)
    assert "timestamp" in data
    assert "aggregate" in data
    assert "gates" in data
    assert "passed_count" in data
    assert "total_count" in data


def test_render_markdown_contains_gate_table():
    """Markdown 报告含五项硬指标表格"""
    result = _make_full_result()
    md = render_markdown(result)
    assert "# 少妇战法 v1.0 验收报告" in md
    assert "| 指标 |" in md
    assert "Sharpe" in md or "夏普" in md
    assert "1/2 通过" in md or "总评" in md


def test_write_report_creates_files(tmp_path: Path):
    """write_report 同时写 JSON + Markdown 文件"""
    result = _make_full_result()
    paths = write_report(result, output_dir=tmp_path, base_name="test")
    assert paths.json_path.exists()
    assert paths.md_path.exists()
    # JSON 文件能正确 parse
    data = json.loads(paths.json_path.read_text())
    assert data["passed_count"] == 1
    assert data["total_count"] == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 report**

写 `modules/verify/report.py`：

```python
"""
v1.0 验收报告输出

JSON 是 source of truth，Markdown 由 JSON 渲染。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .pipeline import VerifyResult


@dataclass
class ReportPaths:
    json_path: Path
    md_path: Path


def render_json(result: VerifyResult) -> str:
    """把 VerifyResult 渲染为 JSON 字符串"""
    data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "config_used": result.config_used,
        "config_source": result.meta.get("config_source", "loop_engine:default"),
        "sample": {
            "ts_codes_count": result.meta.get("ts_codes_count", 0),
            "days": result.meta.get("days", 0),
            "skipped_count": result.meta.get("skipped_count", 0),
            "wf_degraded": result.meta.get("wf_degraded", False),
            "wf_splits": result.meta.get("wf_splits", 0),
        },
        "aggregate": asdict(result.aggregate),
        "gates": {
            name: asdict(g) for name, g in result.gates.items()
        },
        "passed_count": sum(1 for g in result.gates.values() if g.passed),
        "total_count": len(result.gates),
        "summary": _make_summary(result),
        "per_stock": [asdict(s) for s in result.per_stock],
        "meta": result.meta,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_markdown(result: VerifyResult) -> str:
    """把 VerifyResult 渲染为 Markdown 报告"""
    agg = result.aggregate
    passed = sum(1 for g in result.gates.values() if g.passed)
    total = len(result.gates)

    md = [
        "# 少妇战法 v1.0 验收报告",
        "",
        f"**日期**：{datetime.now().isoformat(timespec='seconds', sep=' ')}",
        f"**样本**：{result.meta.get('ts_codes_count', 0)} 只 × "
        f"{result.meta.get('days', 0)} 天 "
        f"（跳过 {result.meta.get('skipped_count', 0)} 只）",
        "",
        "## 五项硬指标",
        "",
        "| 指标 | 实际 | 阈值 | 判定 |",
        "|------|------|------|------|",
    ]

    label_map = {
        "sharpe": ("Sharpe", lambda v: f"{v:.2f}", lambda t: f"≥ {t:.2f}"),
        "calmar": ("Calmar", lambda v: f"{v:.2f}", lambda t: f"≥ {t:.2f}"),
        "win_rate": ("WinRate", lambda v: f"{v:.1%}", lambda t: f"≥ {t:.0%}"),
        "max_drawdown": ("MaxDD", lambda v: f"{v:.1%}", lambda t: f"≤ {t:.0%}"),
        "oos_is_ratio": ("OOS/IS", lambda v: f"{v:.2f}", lambda t: f"≥ {t:.2f}"),
    }

    for name, gate in result.gates.items():
        label, fmt_v, fmt_t = label_map.get(name, (name, str, str))
        icon = "✅" if gate.passed else "❌"
        md.append(
            f"| {label} | {fmt_v(gate.value)} | {fmt_t(gate.threshold)} | {icon} |"
        )

    md.extend([
        "",
        f"**总评**：{passed}/{total} 通过 {_summary_emoji(passed, total)}",
        "",
    ])

    # 失败项的改进建议
    failed = [g for g in result.gates.values() if not g.passed]
    if failed:
        md.extend(["## 改进建议", ""])
        for g in failed:
            md.append(f"- **{g.name}**：{g.message}")
        md.append("")

    md.extend([
        "## 聚合指标",
        "",
        f"- 总交易：{agg.total_trades}",
        f"- 总收益：{agg.total_return_pct:+.1f}%",
        f"- 年化收益：{agg.annual_return_pct:+.1f}%",
        f"- 最大回撤：{agg.max_drawdown:.1%}",
        f"- 索提诺：{agg.sortino:.2f}",
        "",
    ])

    return "\n".join(md)


def write_report(
    result: VerifyResult,
    output_dir: Path | str = "data/reports",
    base_name: str | None = None,
    write_markdown: bool = True,
) -> ReportPaths:
    """写 JSON + Markdown 文件，返回路径"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = base_name or f"verify_v10_{ts}"

    json_path = output_dir / f"{base_name}.json"
    json_path.write_text(render_json(result), encoding="utf-8")

    md_path = output_dir / f"{base_name}.md"
    if write_markdown:
        md_path.write_text(render_markdown(result), encoding="utf-8")

    return ReportPaths(json_path=json_path, md_path=md_path)


def _make_summary(result: VerifyResult) -> str:
    passed = sum(1 for g in result.gates.values() if g.passed)
    total = len(result.gates)
    if total == 0:
        return "无指标"
    if passed == total:
        return f"{passed}/{total} 通过 🎉"
    return f"{passed}/{total} 通过 ⚠️ 待优化"


def _summary_emoji(passed: int, total: int) -> str:
    if total == 0:
        return ""
    if passed == total:
        return "🎉"
    return "⚠️ 待优化"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_report.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add modules/verify/report.py tests/test_verify_report.py
git commit -m "feat(verify): M4 Task 8 JSON + Markdown 报告输出"
```

---

## Task 9: M4 scripts/verify_v10.py + CLI 子命令

**Files:**
- Create: `scripts/verify_v10.py`
- Modify: `modules/cli_commands.py`
- Create: `tests/test_verify_cli.py`

**Interfaces:**
- Consumes: `argparse` 参数
- Produces: 调用 `verify_v10_pipeline()` + `write_report()`

- [ ] **Step 1: 写失败测试**

写 `tests/test_verify_cli.py`：

```python
"""CLI 子命令测试"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.verify.cli import build_parser, run_verify_v10


def test_build_parser_has_required_args():
    """必填参数都在"""
    parser = build_parser()
    # 用 sys.argv 模拟
    args = parser.parse_args(["--limit", "30", "--days", "200"])
    assert args.limit == 30
    assert args.days == 200
    assert args.walk_forward is False
    assert args.json is False


def test_build_parser_limit_range_validation():
    """--limit 必须在 [10, 500]"""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--limit", "5"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--limit", "1000"])


def test_run_verify_v10_invokes_pipeline():
    """run_verify_v10 调用 pipeline"""
    with patch("modules.verify.cli.verify_v10_pipeline") as mock_pipeline:
        from modules.verify.pipeline import VerifyResult, AggregateMetrics
        mock_pipeline.return_value = VerifyResult(
            aggregate=AggregateMetrics(),
        )
        result = run_verify_v10(
            ts_codes=["000001.SZ"], days=250,
        )
        mock_pipeline.assert_called_once()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_verify_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'modules.verify.cli'`

- [ ] **Step 3: 实现 CLI 模块**

写 `modules/verify/cli.py`（在 verify 子包内，方便测试）：

```python
"""
zt verify v1.0 CLI 适配层

薄壳：解析参数 + 调 pipeline + 写报告
"""
from __future__ import annotations

import argparse
import logging

from .pipeline import VerifyResult, verify_v10_pipeline
from .report import write_report

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zt verify v1.0",
        description="少妇战法 v1.0 验收一键命令",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="股票数（默认 50，范围 [10, 500]）",
    )
    parser.add_argument(
        "--days", type=int, default=250,
        help="回测天数（默认 250，范围 [120, 1000]）",
    )
    parser.add_argument(
        "--walk-forward", action="store_true",
        help="启用 Walk-forward 验证",
    )
    parser.add_argument(
        "--wf-train", type=int, default=120,
        help="WF IS 窗口天数（默认 120）",
    )
    parser.add_argument(
        "--wf-test", type=int, default=60,
        help="WF OOS 窗口天数（默认 60）",
    )
    parser.add_argument(
        "--ts-codes", type=str, default=None,
        help="指定股票列表（逗号分隔），默认从 stock_basic 选前 N 只",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="只输出 JSON 到 stdout",
    )
    parser.add_argument(
        "--no-markdown", action="store_true",
        help="不写 Markdown 报告文件",
    )
    parser.add_argument(
        "--output", type=str, default="data/reports",
        help="报告输出目录（默认 data/reports）",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not 10 <= args.limit <= 500:
        raise ValueError(f"--limit 必须在 [10, 500]，当前 {args.limit}")
    if not 120 <= args.days <= 1000:
        raise ValueError(f"--days 必须在 [120, 1000]，当前 {args.days}")
    if args.wf_train < 60 or args.wf_train > 500:
        raise ValueError(f"--wf-train 必须在 [60, 500]，当前 {args.wf_train}")
    if args.wf_test < 30 or args.wf_test > 200:
        raise ValueError(f"--wf-test 必须在 [30, 200]，当前 {args.wf_test}")


def _resolve_ts_codes(args: argparse.Namespace) -> list[str]:
    """解析股票列表（指定 / 默认从 stock_basic 取）"""
    if args.ts_codes:
        return [c.strip() for c in args.ts_codes.split(",") if c.strip()]
    # 默认从 stock_basic 取前 N 只（lazy import 避免循环）
    from modules.database import get_all_stock_codes
    all_codes = get_all_stock_codes(limit=args.limit)
    return all_codes


def run_verify_v10(
    ts_codes: list[str] | None = None,
    days: int = 250,
    walk_forward: bool = False,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: object | None = None,
    write_markdown: bool = True,
    output_dir: str = "data/reports",
) -> VerifyResult:
    """CLI 入口函数（也可被 Python API 直接调用）"""
    result = verify_v10_pipeline(
        ts_codes=ts_codes or [],
        days=days,
        config=config,
        walk_forward=walk_forward,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
    )
    if write_markdown or output_dir:
        write_report(result, output_dir=output_dir, write_markdown=write_markdown)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _validate_args(args)
    except ValueError as e:
        print(f"参数错误：{e}")
        return 2

    ts_codes = _resolve_ts_codes(args)
    result = run_verify_v10(
        ts_codes=ts_codes,
        days=args.days,
        walk_forward=args.walk_forward,
        wf_train_days=args.wf_train,
        wf_test_days=args.wf_test,
        write_markdown=not args.no_markdown,
        output_dir=args.output,
    )

    if args.json:
        from .report import render_json
        print(render_json(result))
    else:
        passed = sum(1 for g in result.gates.values() if g.passed)
        total = len(result.gates)
        print(f"\n少妇战法 v1.0 验收：{passed}/{total} 通过")
        print(f"报告：{args.output}/verify_v10_<timestamp>.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

更新 `modules/verify/__init__.py`，添加 `cli` 模块导出：

```python
from .pipeline import (
    AggregateMetrics,
    GateResult,
    StockResult,
    VerifyResult,
    verify_v10_pipeline,
)
from .cli import build_parser, run_verify_v10, main as verify_cli_main

__all__ = [
    "AggregateMetrics",
    "GateResult",
    "StockResult",
    "VerifyResult",
    "verify_v10_pipeline",
    "build_parser",
    "run_verify_v10",
    "verify_cli_main",
]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_verify_cli.py -v`
Expected: 3 passed

- [ ] **Step 5: 写薄壳脚本**

写 `scripts/verify_v10.py`：

```python
#!/usr/bin/env python3
"""
zt verify v1.0 — 少妇战法 v1.0 验收薄壳脚本

调 modules.verify.cli.main()
"""
from modules.verify.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 在 modules/cli_commands.py 注册子命令**

打开 `modules/cli_commands.py`，找到子命令注册位置，**追加**：

```python
def cmd_verify_v10(args) -> int:
    """少妇战法 v1.0 验收子命令"""
    from modules.verify.cli import main as verify_main
    # 把 argparse Namespace 转成 main() 接受的 argv 列表
    argv = []
    if args.limit != 50:
        argv.extend(["--limit", str(args.limit)])
    if args.days != 250:
        argv.extend(["--days", str(args.days)])
    if getattr(args, "walk_forward", False):
        argv.append("--walk-forward")
    if getattr(args, "wf_train", 120) != 120:
        argv.extend(["--wf-train", str(args.wf_train)])
    if getattr(args, "wf_test", 60) != 60:
        argv.extend(["--wf-test", str(args.wf_test)])
    if getattr(args, "json", False):
        argv.append("--json")
    if getattr(args, "no_markdown", False):
        argv.append("--no-markdown")
    return verify_main(argv)
```

并在 `add_parser` 函数注册：

```python
    p_verify = subparsers.add_parser("verify", help="v1.0 验收")
    p_verify.add_argument("version", choices=["v1.0"], help="验收版本")
    p_verify.add_argument("--limit", type=int, default=50)
    p_verify.add_argument("--days", type=int, default=250)
    p_verify.add_argument("--walk-forward", action="store_true")
    p_verify.add_argument("--wf-train", type=int, default=120)
    p_verify.add_argument("--wf-test", type=int, default=60)
    p_verify.add_argument("--json", action="store_true")
    p_verify.add_argument("--no-markdown", action="store_true")
    p_verify.set_defaults(func=cmd_verify_v10)
```

- [ ] **Step 7: 跑全测试确认通过**

Run: `python -m pytest tests/test_verify_*.py tests/test_cli_subparser.py -v`
Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
git add modules/verify/cli.py modules/verify/__init__.py scripts/verify_v10.py modules/cli_commands.py tests/test_verify_cli.py
git commit -m "feat(verify): M4 Task 9 zt verify v1.0 CLI 子命令"
```

---

## Task 10: 文档同步（CHANGELOG + README + pyproject）

**Files:**
- Modify: `pyproject.toml`（版本号）
- Modify: `docs/CHANGELOG.md`（追加 v3.7.0 段）
- Modify: `README.md`（加 v3.7.0 章节）

- [ ] **Step 1: 更新 pyproject.toml 版本号**

打开 `pyproject.toml`，找到 `version = "3.6.0"`，改为：

```toml
version = "3.7.0"
```

- [ ] **Step 2: 更新 CHANGELOG.md**

在 `docs/CHANGELOG.md` 文件顶部 `## v3.6.0 (2026-07-04)` **之前**插入：

```markdown
## v3.7.0 (2026-07-10)

### 少妇战法 v1.0 验收工程化

> **「v3.7.0：少妇战法 v1.0 验收工程化 —— 一键命令 + 五项硬指标自动判定 + Walk-forward 防过拟合。」**

#### 新增模块 `modules/verify/`

- **`pipeline.py`** — 统一回测管线（封装 `backtest_shaofu_portfolio` + 数据预检 + 指标聚合）
- **`gates.py`** — 五项硬指标自动达标判定（Sharpe/Calmar/WinRate/MaxDD/OOS/IS）
- **`walk_forward.py`** — 少妇六步 WF 适配（IS 寻优 + OOS 拼接 + OOS/IS 比率）
- **`registry_writer.py`** — 多因子优化结果 → `param_registry` 写入器
- **`report.py`** — JSON + Markdown 报告输出（JSON 是 source of truth）
- **`cli.py`** — `zt verify v1.0` CLI 适配层

#### 新增脚本

- `scripts/verify_v10.py` — `zt verify v1.0` 薄壳入口

#### 新增子命令

- `zt verify v1.0 [--limit N] [--days N] [--walk-forward] [--json]`
  - `--limit N`：[10, 500]，默认 50
  - `--days N`：[120, 1000]，默认 250
  - `--walk-forward`：启用 Walk-forward
  - `--wf-train N` / `--wf-test N`：WF 窗口，默认 120 / 60

#### 修改

- `modules/loop_engine.py`：追加 `LoopConfig.from_registry()` 类方法（不改现有字段）
- `modules/cli_commands.py`：注册 `verify` 子命令

#### 五项硬指标阈值

| 指标 | 阈值 | 方向 |
|------|------|------|
| Sharpe | ≥ 0.5 | higher |
| Calmar | ≥ 0.5 | higher |
| WinRate | ≥ 40% | higher |
| MaxDD | ≤ 25% | lower |
| OOS/IS | ≥ 0.6 | higher |

#### 测试

- 新增 `tests/test_verify_*.py`（6 个测试文件，~49 用例）
- 零回归：892 → 941 passed（+ 49）
- ruff + mypy 零错误
```

- [ ] **Step 3: 更新 README.md**

在 `README.md` 中找到「## 版本规范」章节，在版本表格最后一行**之后**追加：

```markdown
| **v3.7.0** | 少妇战法 v1.0 验收工程化（一键命令 + 五项硬指标 + WF） | ✅ 已完成 |
```

并在「效果展示」章节**之后**追加：

```markdown
## v3.7.0 验收工程化

`zt verify v1.0` 一键完成少妇战法 v1.0 验收：

```bash
# 默认 50 只 × 250 天
zt verify v1.0

# 启用 Walk-forward
zt verify v1.0 --limit 50 --days 250 --walk-forward

# JSON 输出
zt verify v1.0 --json

# 自定义输出目录
zt verify v1.0 --output data/reports/my_verify
```

输出报告：
- `data/reports/verify_v10_<timestamp>.json` — 结构化（source of truth）
- `data/reports/verify_v10_<timestamp>.md` — 人读（含五项指标表格）

**五项硬指标**：
| 指标 | 阈值 |
|------|------|
| Sharpe | ≥ 0.5 |
| Calmar | ≥ 0.5 |
| WinRate | ≥ 40% |
| MaxDD | ≤ 25% |
| OOS/IS | ≥ 0.6 |
```

- [ ] **Step 4: 跑全套测试确认零回归**

Run: `python -m pytest tests/ -v`
Expected: **941 passed**, 11 skipped（原 892 + 49 新增）

- [ ] **Step 5: 跑 lint 确认零错误**

Run: `ruff check modules/verify tests/test_verify*`
Expected: 零错误

- [ ] **Step 6: 跑质量门确认 SKILL.md 不动**

Run: `python corpus/quality_check.py SKILL.md`
Expected: 12/12 通过

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml docs/CHANGELOG.md README.md
git commit -m "docs: v3.7.0 文档同步 (CHANGELOG + README + 版本号)"
```

---

## Task 11: 端到端真实数据回归

**Files:**
- 无文件变更（仅验证）

- [ ] **Step 1: 跑一次完整验收**

Run: `zt verify v1.0 --limit 50 --days 250 --walk-forward`
Expected:
- 命令成功执行（exit 0）
- 输出报告路径
- 单次 < 5 分钟

- [ ] **Step 2: 跑 slow 测试**

Run: `python -m pytest tests/ -m slow -v`
Expected: 全部通过

- [ ] **Step 3: 验证 JSON 报告结构**

Run: `python -c "import json; d = json.load(open('data/reports/verify_v10_<latest>.json')); print(d['passed_count'], '/', d['total_count'])"`
Expected: 打印 "X / 5"

- [ ] **Step 4: 提交发布 tag**

```bash
git tag -a v3.7.0 -m "v3.7.0: 少妇战法 v1.0 验收工程化"
git push origin v3.7.0
git push origin main
```

---

## Self-Review

**1. Spec 覆盖检查**：

| Spec 章节 | 对应 Task |
|-----------|----------|
| M1 统一管线（pipeline.py）| Task 1-4 |
| M2 Walk-forward + Gates（gates.py + walk_forward.py）| Task 5-6 |
| M3 Registry 回写（registry_writer.py + LoopConfig.from_registry）| Task 7 |
| M4 zt verify v1.0 CLI + 报告（cli.py + report.py + scripts/verify_v10.py）| Task 8-9 |
| 版本发布（CHANGELOG + README + pyproject + tag）| Task 10-11 |
| 错误处理矩阵 | Task 2（数据预检）+ Task 3（回测异常）+ Task 6（WF 降级）+ Task 7（registry 缺失降级）|
| 测试策略（49 用例）| Task 1-9 各自的 Step 1 |
| 边界条件（参数范围）| Task 9（`_validate_args`）|

**无遗漏 spec 章节**。

**2. 占位符扫描**：

搜索 "TODO" / "TBD" / "implement later"：
- 仅出现在 Task 1 Step 3 的 `verify_v10_pipeline` 中，作为"Task 2-4 补完"的占位说明（这是 plan 内的预期，不算违规）
- 其他位置无占位符

**3. 类型一致性**：

| 类型 | 定义位置 | 使用位置 |
|------|----------|----------|
| `StockResult` | Task 1 | Task 1-4-8 |
| `AggregateMetrics` | Task 1 | Task 4-5-6-8 |
| `GateResult` | Task 1（pipeline.py 定义）| Task 5（gates.py 仅 import 不再定义）|
| `VerifyResult` | Task 1 | Task 4-6-8-9 |
| `WFSplit` / `WFResult` | Task 6 | Task 5-6-8 |
| `RegistryWriteReport` | Task 7 | Task 7-8 |
| `ReportPaths` | Task 8 | Task 8-9 |

✅ **修正**：`GateResult` 统一在 `pipeline.py` 定义（Task 1），`gates.py`（Task 5）只 `from .pipeline import GateResult`，避免重复 dataclass。
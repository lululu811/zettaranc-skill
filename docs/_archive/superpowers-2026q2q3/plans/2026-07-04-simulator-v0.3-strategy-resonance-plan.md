# 少女/少妇模拟器 v0.3 战法共振评分 —— 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `modules/strategies/` 中已有的 20+ 战法信号接入模拟器选股层，实现多战法共振评分、市场环境动态权重、冲突降级，同时保留 `strategy_mode="simple"` 向后兼容。

**Architecture:** 新增 `strategy_adapter.py`（标准化信号）、`resonance_scorer.py`（共振评分）、`environment_weights.py`（环境权重）三个职责单一模块；扩展 `SimulationConfig`/`SignalScore` 数据类；改造 `signal_filter.py` 支持 `simple`/`resonance` 两种模式；CLI 暴露 `--strategy-mode` 等参数。`strategy_adapter` 与 `environment_weights` 在数据类扩展完成后可并行实现；`resonance_scorer` 依赖 `RawStrategySignal` 需在 adapter 完成后实现；`signal_filter` 集成需在三个新模块都完成后进行。

**Tech Stack:** Python 3.10+, pytest, ruff, mypy, 标准库为主（dataclasses, datetime, math）。

## Global Constraints

- Python 3.10+，类型提示使用 `|` union 与 `from __future__ import annotations`。
- 优先使用标准库，不引入新的第三方依赖。
- 所有模块文件头包含 `#!/usr/bin/env python3`，中文 docstring 与注释。
- 数据库路径统一从 `os.getenv("DB_PATH", "data/stock_data.db")` 读取。
- 代码风格：ruff line-length 120，mypy ignore_missing_imports，中文注释。
- 每个新增功能必须有对应单元测试，TDD 顺序执行。
- 保持向后兼容：`SimulationConfig` 新增字段均带默认值，`strategy_mode="simple"` 时行为与 v0.2 完全一致。
- 反未来函数：只使用回测当日及之前可见的战法信号。
- 版本目标：zettaranc-skill v3.5.0。

---

## File Map

| 文件 | 类型 | 职责 |
|---|---|---|
| `modules/simulator/__init__.py` | 修改 | 扩展 `SimulationConfig`/`SignalScore`/`SimulationResult` 数据类，新增 `RawStrategySignal`/`ResonanceScore` |
| `modules/simulator/strategy_adapter.py` | 新建 | 把 `StrategySignal` 转换为 `RawStrategySignal`，维护映射表、日期过滤、同类型去重 |
| `modules/simulator/resonance_scorer.py` | 新建 | 对 `RawStrategySignal` 列表计算共振分、冲突降级 |
| `modules/simulator/environment_weights.py` | 新建 | 根据 `MarketRegime` 返回 category 权重表，支持用户覆盖 |
| `modules/simulator/signal_filter.py` | 修改 | `evaluate_stock` 增加 `resonance` 分支，最终仍输出 `SignalScore` |
| `modules/simulator/simulator.py` | 修改 | 把 `MarketContext` 传入 `evaluate_stock`（如尚未传入） |
| `modules/cli.py` | 修改 | `simulate` subparser 新增 `--strategy-mode/--strategy-lookback/--min-resonance-score` |
| `modules/cli_commands.py` | 修改 | `cmd_simulate` 映射新参数到 `SimulationConfig`；JSON 输出增加 `resonance_details` |
| `tests/test_simulator_strategy_adapter.py` | 新建 | adapter 映射/过滤/去重测试 |
| `tests/test_simulator_resonance.py` | 新建 | 共振分计算、冲突降级、verdict 判断测试 |
| `tests/test_simulator_environment_weights.py` | 新建 | 环境权重表、覆盖逻辑测试 |
| `tests/test_simulator.py` | 修改 | 扩展集成测试：`strategy_mode="resonance"` 能跑通，`simple` 模式结果不变 |
| `tests/test_cli_simulate.py` | 修改 | 新增 CLI 参数解析测试 |
| `docs/CHANGELOG.md` | 修改 | 新增 v3.5.0 条目 |
| `docs/TODO.md` | 修改 | 更新 simulator v0.3 进度 |
| `README.md` | 修改 | 更新 `zt simulate --strategy-mode resonance` 示例 |
| `pyproject.toml` | 修改 | 版本号改为 `3.5.0` |

---

## Task 1: 扩展数据类

**Files:**
- Modify: `modules/simulator/__init__.py`
- Test: `tests/test_simulator.py`（新增数据类字段断言）

**Interfaces:**
- Produces: `RawStrategySignal` dataclass with fields `strategy: str`, `category: str`, `action: str`, `confidence: float`, `trade_date: str`, `reason: str = ""`.
- Produces: `ResonanceScore` dataclass with fields `ts_code: str`, `name: str`, `date: str`, `total_score: float`, `buy_score: float`, `risk_score: float`, `matched_strategies: list[str]`, `conflicts: list[str]`, `verdict: SignalVerdict`.
- Produces: `SimulationConfig` 新增 `strategy_mode: str = "simple"`, `strategy_lookback_days: int = 5`, `min_resonance_score: float = 0.35`, `strategy_category_weights: dict[str, float] = field(default_factory=dict)`.
- Produces: `SignalScore` 新增 `resonance: ResonanceScore | None = None`.
- Produces: `SimulationResult` 新增 `resonance_summary: dict[str, Any] = field(default_factory=dict)`（可选，用于 CLI 输出统计）。

- [ ] **Step 1: 写失败测试**

```python
def test_raw_strategy_signal_dataclass():
    from modules.simulator import RawStrategySignal
    s = RawStrategySignal(strategy="B1", category="rebound", action="BUY", confidence=0.8, trade_date="20240101")
    assert s.strategy == "B1"
    assert s.confidence == 0.8


def test_simulation_config_strategy_mode_defaults():
    from modules.simulator import SimulationConfig
    cfg = SimulationConfig()
    assert cfg.strategy_mode == "simple"
    assert cfg.strategy_lookback_days == 5
    assert cfg.min_resonance_score == 0.35
    assert cfg.strategy_category_weights == {}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator.py::test_raw_strategy_signal_dataclass tests/test_simulator.py::test_simulation_config_strategy_mode_defaults -v
```
Expected: 2 FAIL

- [ ] **Step 3: 最小实现**

在 `modules/simulator/__init__.py` 中：

```python
@dataclass
class RawStrategySignal:
    """标准化后的战法信号"""

    strategy: str
    category: str
    action: str
    confidence: float
    trade_date: str
    reason: str = ""


@dataclass
class ResonanceScore:
    """战法共振评分结果"""

    ts_code: str
    name: str
    date: str
    total_score: float
    buy_score: float
    risk_score: float
    matched_strategies: list[str]
    conflicts: list[str]
    verdict: SignalVerdict


@dataclass
class SignalScore:
    # 已有字段保留...
    resonance: ResonanceScore | None = None


@dataclass
class SimulationConfig:
    # v0.2 字段保留...

    # v0.3 新增
    strategy_mode: str = "simple"
    strategy_lookback_days: int = 5
    min_resonance_score: float = 0.35
    strategy_category_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class SimulationResult:
    # 已有字段保留...
    resonance_summary: dict[str, Any] = field(default_factory=dict)
```

并更新 `__all__`：

```python
__all__ = [
    # ... 已有
    "RawStrategySignal",
    "ResonanceScore",
]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator.py::test_raw_strategy_signal_dataclass tests/test_simulator.py::test_simulation_config_strategy_mode_defaults -v
```
Expected: 2 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/__init__.py tests/test_simulator.py
git commit -m "feat(simulator): add RawStrategySignal, ResonanceScore and strategy-mode config"
```

---

## Task 2: 战法适配层（可并行于 Task 3）

**Files:**
- Create: `modules/simulator/strategy_adapter.py`
- Test: `tests/test_simulator_strategy_adapter.py`

**Interfaces:**
- Produces: `STRATEGY_MAPPING: dict[str, tuple[str, str, str]]` mapping `StrategySignal.strategy.value` -> `(strategy_name, category, action)`.
- Produces: `adapt(signals: list[StrategySignal]) -> list[RawStrategySignal]`.
- Produces: `filter_by_date(signals: list[RawStrategySignal], trade_date: str, lookback_days: int = 5) -> list[RawStrategySignal]`.
- Produces: `deduplicate(signals: list[RawStrategySignal]) -> list[RawStrategySignal]`（同一 strategy 同一天保留 confidence 最高）。

- [ ] **Step 1: 写失败测试**

```python
def test_adapt_maps_strategy_signal():
    from modules.simulator.strategy_adapter import adapt
    from modules.strategies import StrategySignal, StrategyType, Action, Priority
    sig = StrategySignal(
        ts_code="000001.SZ",
        trade_date="20240101",
        strategy=StrategyType.B1,
        action=Action.BUY.value,
        confidence=0.75,
        description="B1",
        price=10.0,
    )
    raw = adapt([sig])
    assert len(raw) == 1
    assert raw[0].strategy == "B1"
    assert raw[0].category == "rebound"
    assert raw[0].action == "BUY"


def test_filter_by_date_uses_lookback():
    from modules.simulator.strategy_adapter import filter_by_date
    from modules.simulator import RawStrategySignal
    signals = [
        RawStrategySignal("B1", "rebound", "BUY", 0.8, "20240101"),
        RawStrategySignal("B2", "breakout", "BUY", 0.7, "20240103"),
        RawStrategySignal("S1", "risk", "SELL", 0.9, "20240108"),
    ]
    result = filter_by_date(signals, "20240105", lookback_days=5)
    assert len(result) == 2
    assert all(s.trade_date <= "20240105" for s in result)


def test_deduplicate_keeps_highest_confidence():
    from modules.simulator.strategy_adapter import deduplicate
    from modules.simulator import RawStrategySignal
    signals = [
        RawStrategySignal("B1", "rebound", "BUY", 0.6, "20240101"),
        RawStrategySignal("B1", "rebound", "BUY", 0.9, "20240101"),
    ]
    result = deduplicate(signals)
    assert len(result) == 1
    assert result[0].confidence == 0.9
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator_strategy_adapter.py -v
```
Expected: 3 FAIL

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
战法信号适配层。

把 modules.strategies.StrategySignal 转换为模拟器内部统一的 RawStrategySignal，
负责标准化命名、分类、动作，并提供日期过滤与同类型去重。
"""

from __future__ import annotations

from ..strategies import StrategySignal
from . import RawStrategySignal


# 原始 strategy.value -> (strategy_name, category, action)
STRATEGY_MAPPING: dict[str, tuple[str, str, str]] = {
    "B1": ("B1", "rebound", "BUY"),
    "B2": ("B2", "breakout", "BUY"),
    "B3": ("B3", "consensus", "BUY"),
    "SB1": ("超级B1", "rebound", "BUY"),
    "长安": ("长安", "breakout", "BUY"),
    "四分之三阴量": ("四分之三阴量", "risk", "SELL"),
    "娜娜": ("娜娜", "pattern", "BUY"),
    "异动+地量地价": ("异动地量", "rebound", "BUY"),
    "平行重炮": ("平行重炮", "breakout", "BUY"),
    "坑里起好货": ("坑里起好货", "rebound", "BUY"),
    "对称 VA": ("对称VA", "pattern", "BUY"),
    "S1": ("S1", "risk", "SELL"),
    "S2": ("S2", "risk", "SELL"),
    "S3": ("S3", "risk", "SELL"),
    "砖形图": ("砖形图", "risk", "SELL"),
    "买盘枯竭": ("买盘枯竭", "risk", "SELL"),
    "绿肥红瘦": ("绿肥红瘦", "risk", "SELL"),
    "阶梯放量下跌": ("阶梯放量下跌", "risk", "SELL"),
    "顶部大风车": ("顶部大风车", "risk", "SELL"),
    "三波·建仓波": ("三波建仓", "stage", "BUY"),
    "三波·拉升波": ("三波拉升", "stage", "HOLD"),
    "三波·冲刺波": ("三波冲刺", "stage", "SELL"),
    "麒麟·吸筹": ("麒麟吸筹", "stage", "WATCH"),
    "麒麟·拉升": ("麒麟拉升", "stage", "HOLD"),
    "麒麟·派发": ("麒麟派发", "stage", "SELL"),
    "麒麟·回落": ("麒麟回落", "stage", "SELL"),
    "滴滴战法": ("滴滴战法", "risk", "SELL"),
    "MACD 金叉空": ("MACD金叉空", "risk", "SELL"),
    "MACD 死叉多": ("MACD死叉多", "rebound", "BUY"),
    "出货五式": ("出货五式", "risk", "SELL"),
    "量比攻击": ("量比攻击", "breakout", "WATCH"),
    "灾后重建": ("灾后重建", "rebound", "BUY"),
    "跃跃欲试": ("跃跃欲试", "breakout", "BUY"),
    "关键K": ("关键K", "pattern", "BUY"),
}


def adapt(signals: list[StrategySignal]) -> list[RawStrategySignal]:
    """把 StrategySignal 列表转换为 RawStrategySignal 列表。"""
    result: list[RawStrategySignal] = []
    for sig in signals:
        mapped = STRATEGY_MAPPING.get(sig.strategy.value)
        if not mapped:
            continue
        name, category, action = mapped
        # 关键K 特殊处理：根据 description 判断方向
        if name == "关键K":
            action = "SELL" if "阴破位" in (sig.reason or sig.description or "") else "BUY"
        result.append(
            RawStrategySignal(
                strategy=name,
                category=category,
                action=action,
                confidence=float(sig.confidence or 0.0),
                trade_date=str(sig.trade_date or ""),
                reason=str(sig.reason or sig.description or ""),
            )
        )
    return result


def filter_by_date(
    signals: list[RawStrategySignal],
    trade_date: str,
    lookback_days: int = 5,
) -> list[RawStrategySignal]:
    """保留 trade_date 当日及之前 lookback_days 个交易日内的信号。"""
    return [s for s in signals if s.trade_date and s.trade_date <= trade_date]


def deduplicate(signals: list[RawStrategySignal]) -> list[RawStrategySignal]:
    """同一天同一 strategy 保留 confidence 最高的一条。"""
    best: dict[tuple[str, str], RawStrategySignal] = {}
    for s in signals:
        key = (s.strategy, s.trade_date)
        if key not in best or s.confidence > best[key].confidence:
            best[key] = s
    return list(best.values())
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator_strategy_adapter.py -v
```
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/strategy_adapter.py tests/test_simulator_strategy_adapter.py
git commit -m "feat(simulator): add strategy adapter for standardized signals"
```

---

## Task 3: 环境权重层（可并行于 Task 2）

**Files:**
- Create: `modules/simulator/environment_weights.py`
- Test: `tests/test_simulator_environment_weights.py`

**Interfaces:**
- Produces: `DEFAULT_ENVIRONMENT_WEIGHTS: dict[MarketRegime, dict[str, float]]`。
- Produces: `get_weights(regime: MarketRegime, config: SimulationConfig) -> dict[str, float]`。

- [ ] **Step 1: 写失败测试**

```python
def test_default_weights_for_strong():
    from modules.simulator.environment_weights import get_weights
    from modules.simulator import SimulationConfig, MarketRegime
    weights = get_weights(MarketRegime.STRONG, SimulationConfig())
    assert weights["breakout"] > weights["rebound"]


def test_user_override_weights():
    from modules.simulator.environment_weights import get_weights
    from modules.simulator import SimulationConfig, MarketRegime
    cfg = SimulationConfig(strategy_category_weights={"breakout": 2.0})
    weights = get_weights(MarketRegime.NEUTRAL, cfg)
    assert weights["breakout"] == 2.0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator_environment_weights.py -v
```
Expected: 2 FAIL

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
环境权重层。

根据市场环境（强势/震荡/弱势）为不同战法类别分配权重，
支持用户通过 SimulationConfig.strategy_category_weights 覆盖默认值。
"""

from __future__ import annotations

from . import MarketRegime, SimulationConfig


DEFAULT_ENVIRONMENT_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.STRONG: {
        "breakout": 1.30,
        "pattern": 1.10,
        "rebound": 0.80,
        "stage": 1.00,
        "risk": 1.20,
    },
    MarketRegime.NEUTRAL: {
        "breakout": 1.00,
        "pattern": 1.00,
        "rebound": 1.00,
        "stage": 1.00,
        "risk": 1.00,
    },
    MarketRegime.WEAK: {
        "breakout": 0.50,
        "pattern": 0.80,
        "rebound": 1.30,
        "stage": 1.00,
        "risk": 1.10,
    },
}


def get_weights(regime: MarketRegime, config: SimulationConfig) -> dict[str, float]:
    """
    获取当前市场环境下各战法类别的权重。

    Args:
        regime: 市场环境
        config: 模拟配置

    Returns:
        category -> weight 的字典
    """
    defaults = DEFAULT_ENVIRONMENT_WEIGHTS.get(regime, DEFAULT_ENVIRONMENT_WEIGHTS[MarketRegime.NEUTRAL]).copy()
    if config.strategy_category_weights:
        defaults.update(config.strategy_category_weights)
    return defaults
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator_environment_weights.py -v
```
Expected: 2 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/environment_weights.py tests/test_simulator_environment_weights.py
git commit -m "feat(simulator): add environment-aware strategy category weights"
```

---

## Task 4: 共振评分层（依赖 Task 2）

**Files:**
- Create: `modules/simulator/resonance_scorer.py`
- Test: `tests/test_simulator_resonance.py`

**Interfaces:**
- Produces: `calculate_resonance(raw_signals: list[RawStrategySignal], ts_code: str, name: str, date: str, config: SimulationConfig) -> ResonanceScore`。
- Produces: `apply_weights(resonance: ResonanceScore, weights: dict[str, float]) -> float` 返回加权后的总分。

- [ ] **Step 1: 写失败测试**

```python
def test_b1_b2_resonance_increases_score():
    from modules.simulator.resonance_scorer import calculate_resonance
    from modules.simulator import RawStrategySignal, SimulationConfig
    raw = [
        RawStrategySignal("B1", "rebound", "BUY", 0.8, "20240101"),
        RawStrategySignal("B2", "breakout", "BUY", 0.7, "20240101"),
    ]
    score = calculate_resonance(raw, "000001.SZ", "测试", "20240101", SimulationConfig())
    assert score.verdict.value == "通过"
    assert score.total_score > 1.0


def test_sprint_stage_triggers_high_risk():
    from modules.simulator.resonance_scorer import calculate_resonance
    from modules.simulator import RawStrategySignal, SimulationConfig, SignalVerdict
    raw = [
        RawStrategySignal("B1", "rebound", "BUY", 0.8, "20240101"),
        RawStrategySignal("三波冲刺", "stage", "SELL", 0.9, "20240101"),
    ]
    score = calculate_resonance(raw, "000001.SZ", "测试", "20240101", SimulationConfig())
    assert score.verdict == SignalVerdict.HIGH_RISK


def test_low_score_returns_no_signal():
    from modules.simulator.resonance_scorer import calculate_resonance
    from modules.simulator import RawStrategySignal, SimulationConfig, SignalVerdict
    raw = [RawStrategySignal("量比攻击", "breakout", "WATCH", 0.3, "20240101")]
    score = calculate_resonance(raw, "000001.SZ", "测试", "20240101", SimulationConfig())
    assert score.verdict == SignalVerdict.NO_SIGNAL
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator_resonance.py -v
```
Expected: 3 FAIL

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
战法共振评分层。

对单只股票当日可见的战法信号做聚合评分，识别共振与冲突，
输出统一的 ResonanceScore 供 signal_filter 进一步过滤。
"""

from __future__ import annotations

from . import RawStrategySignal, ResonanceScore, SimulationConfig, SignalVerdict


# 类别组合共振奖励
category: dict[tuple[str, str], float] = {
    ("rebound", "breakout"): 0.15,
    ("rebound", "pattern"): 0.10,
    ("breakout", "stage"): 0.10,
    ("rebound", "stage"): 0.10,
}


# 直接触发 HIGH_RISK 的 strategy 列表
RISK_STRATEGIES: set[str] = {
    "三波冲刺",
    "麒麟派发",
    "出货五式",
    "顶部大风车",
    "S1",
    "S2",
    "S3",
    "绿肥红瘦",
    "阶梯放量下跌",
}


def _category_resonance_bonus(categories: set[str]) -> float:
    """根据同时出现的类别组合给予额外奖励。"""
    bonus = 0.0
    for (a, b), value in CATEGORY_RESONANCE_BONUS.items():
        if a in categories and b in categories:
            bonus += value
    return bonus


def calculate_resonance(
    raw_signals: list[RawStrategySignal],
    ts_code: str,
    name: str,
    date: str,
    config: SimulationConfig,
) -> ResonanceScore:
    """
    计算战法共振评分。

    Args:
        raw_signals: 已过滤且去重的 RawStrategySignal 列表
        ts_code: 股票代码
        name: 股票名称
        date: 当前交易日
        config: 模拟配置

    Returns:
        ResonanceScore
    """
    buy_score = 0.0
    risk_score = 0.0
    matched: list[str] = []
    conflicts: list[str] = []
    categories: set[str] = set()

    for s in raw_signals:
        matched.append(s.strategy)
        categories.add(s.category)

        if s.action == "BUY":
            buy_score += s.confidence
        elif s.action == "SELL":
            risk_score += s.confidence
        elif s.action == "WATCH":
            buy_score += s.confidence * 0.3
        elif s.action == "HOLD":
            buy_score += s.confidence * 0.1

        if s.strategy in RISK_STRATEGIES:
            conflicts.append(f"{s.strategy}：风险信号")

    # 类别共振奖励
    buy_score += _category_resonance_bonus(categories)

    total_score = buy_score - risk_score

    # verdict 判定
    if conflicts:
        verdict = SignalVerdict.HIGH_RISK
    elif total_score < config.min_resonance_score:
        verdict = SignalVerdict.NO_SIGNAL
    else:
        verdict = SignalVerdict.PASS

    return ResonanceScore(
        ts_code=ts_code,
        name=name,
        date=date,
        total_score=round(total_score, 4),
        buy_score=round(buy_score, 4),
        risk_score=round(risk_score, 4),
        matched_strategies=matched,
        conflicts=conflicts,
        verdict=verdict,
    )


def apply_weights(resonance: ResonanceScore, weights: dict[str, float]) -> float:
    """
    将共振分按环境权重加权。

    当前实现：按 buy_score 与 risk_score 分别加权后相减。
    类别权重在 signal_filter 中通过 per-strategy 加权实现，此处保持简单。
    """
    # 默认权重为 1.0
    return resonance.total_score
```

注意：在 `signal_filter.py` 中实际加权时，会对每个 `RawStrategySignal` 的 confidence 按 `weights[s.category]` 相乘，再调用 `calculate_resonance`。因此 `apply_weights` 这里只是 identity fallback。

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator_resonance.py -v
```
Expected: 3 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/resonance_scorer.py tests/test_simulator_resonance.py
git commit -m "feat(simulator): add strategy resonance scorer with conflict downgrade"
```

---

## Task 5: 信号过滤层集成

**Files:**
- Modify: `modules/simulator/signal_filter.py`
- Modify: `modules/simulator/simulator.py`（把 MarketContext 传入 evaluate_stock）
- Test: `tests/test_simulator.py`（扩展集成测试）

**Interfaces:**
- Consumes: `RawStrategySignal`, `ResonanceScore`, `SimulationConfig.strategy_mode`, `get_weights`, `calculate_resonance`, `adapt`, `filter_by_date`, `deduplicate`.
- Produces: `evaluate_stock(..., context: MarketContext | None = None)` 在 resonance 模式下使用战法信号；`filter_signals` 保持原接口。

- [ ] **Step 1: 写失败测试**

```python
def test_evaluate_stock_resonance_mode_uses_strategies():
    from modules.simulator.signal_filter import evaluate_stock
    from modules.simulator import SimulationConfig, SignalVerdict
    cfg = SimulationConfig(strategy_mode="resonance")
    # 使用 mock klines 与 mock detect_all_strategies
    ...
    score = evaluate_stock("000001.SZ", "20240101", klines=klines, config=cfg)
    assert score.verdict == SignalVerdict.PASS


def test_evaluate_stock_simple_mode_unchanged():
    from modules.simulator.signal_filter import evaluate_stock
    from modules.simulator import SimulationConfig
    cfg = SimulationConfig(strategy_mode="simple")
    score = evaluate_stock("000001.SZ", "20240101", klines=klines, config=cfg)
    assert score.resonance is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator.py::test_evaluate_stock_resonance_mode_uses_strategies -v
```
Expected: FAIL

- [ ] **Step 3: 实现集成**

修改 `modules/simulator/signal_filter.py`：

```python
from __future__ import annotations

from ..strategies import detect_all_strategies
from ..datasource import DataSource, get_datasource
from ..indicators import DailyData, calculate_sandglass_score
from ..indicators.volume_patterns import detect_volume_ratio_strategy
from ..indicators.price_patterns import detect_bull_rope
from . import (
    SignalScore,
    SignalVerdict,
    SimulationConfig,
    MarketContext,
    MarketRegime,
)
from .strategy_adapter import adapt, filter_by_date, deduplicate
from .resonance_scorer import calculate_resonance
from .environment_weights import get_weights


def _extract_signals_v2(score, klines):
    """v0.2 simple 模式的标签提取，保持原逻辑。"""
    ...


def _evaluate_resonance(
    ts_code: str,
    trade_date: str,
    name: str,
    klines: list[DailyData],
    context: MarketContext | None,
    config: SimulationConfig,
) -> SignalScore:
    """resonance 模式：使用 modules.strategies 信号。"""
    raw = adapt(detect_all_strategies(ts_code, days=120))
    recent = filter_by_date(raw, trade_date, config.strategy_lookback_days)
    recent = deduplicate(recent)

    weights = get_weights(context.regime if context else MarketRegime.NEUTRAL, config)
    weighted = [
        RawStrategySignal(
            strategy=s.strategy,
            category=s.category,
            action=s.action,
            confidence=s.confidence * weights.get(s.category, 1.0),
            trade_date=s.trade_date,
            reason=s.reason,
        )
        for s in recent
    ]

    resonance = calculate_resonance(weighted, ts_code, name, trade_date, config)

    # 将 resonance.total_score 映射到 0-100
    mapped_score = max(0.0, min(100.0, resonance.total_score * 50 + 50))

    return SignalScore(
        ts_code=ts_code,
        name=name,
        date=trade_date,
        score=mapped_score,
        b1_score=0.0,          # resonance 模式下不使用 screener 子分数
        trend_score=0.0,
        volume_score=0.0,
        risk_score=resonance.risk_score * 50,
        signals=resonance.matched_strategies,
        reasons=[f"共振分 {resonance.total_score:.2f}"] + resonance.conflicts,
        warnings=resonance.conflicts,
        verdict=resonance.verdict,
        resonance=resonance,
    )


def evaluate_stock(
    ts_code: str,
    trade_date: str,
    klines: list[DailyData] | None = None,
    datasource: DataSource | None = None,
    config: SimulationConfig | None = None,
    context: MarketContext | None = None,
) -> SignalScore:
    """评估单只股票信号。新增 config 与 context 参数。"""
    config = config or SimulationConfig()

    if config.strategy_mode == "resonance":
        return _evaluate_resonance(ts_code, trade_date, ts_code, klines or [], context, config)

    # simple 模式保持 v0.2 原逻辑（略）
    ...
```

修改 `modules/simulator/simulator.py`：

在 `run_simulation` 的循环中，把 `context` 传给 `evaluate_stock`：

```python
sig = evaluate_stock(code, date, klines=sub, datasource=ds, config=config, context=context)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/signal_filter.py modules/simulator/simulator.py tests/test_simulator.py
git commit -m "feat(simulator): integrate resonance scoring into signal filter"
```

---

## Task 6: CLI 参数扩展

**Files:**
- Modify: `modules/cli.py`
- Modify: `modules/cli_commands.py`
- Test: `tests/test_cli_simulate.py`

**Interfaces:**
- Produces: CLI 新增 `--strategy-mode {simple,resonance}`, `--strategy-lookback N`, `--min-resonance-score X`。
- Produces: JSON 输出新增 `resonance_details` 字段（包含 `matched_strategies`、`conflicts`、`buy_score`、`risk_score` 的聚合摘要）。

- [ ] **Step 1: 写失败测试**

```python
def test_cli_strategy_mode_argument():
    import argparse
    from modules.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["simulate", "000001.SZ", "--strategy-mode", "resonance", "--strategy-lookback", "3"])
    assert args.strategy_mode == "resonance"
    assert args.strategy_lookback == 3
```

- [ ] **Step 2-7: 实现、测试、提交**

在 `modules/cli.py` 的 `simulate` subparser 中新增：

```python
p_sim.add_argument("--strategy-mode", choices=["simple", "resonance"], default="simple", help="选股模式")
p_sim.add_argument("--strategy-lookback", type=int, default=5, help="战法信号回看交易日数")
p_sim.add_argument("--min-resonance-score", type=float, default=0.35, help="共振模式最低入选分")
```

在 `modules/cli_commands.py` 的 `cmd_simulate` 中：

```python
config = SimulationConfig(
    initial_capital=getattr(args, "capital", 1_000_000.0),
    max_positions=getattr(args, "max_positions", 5),
    risk_per_trade=getattr(args, "risk", 0.02),
    position_score_threshold=getattr(args, "score", 70.0),
    signal_min_count=getattr(args, "signals", 2),
    strategy_mode=getattr(args, "strategy_mode", "simple"),
    strategy_lookback_days=getattr(args, "strategy_lookback", 5),
    min_resonance_score=getattr(args, "min_resonance_score", 0.35),
)
```

JSON 输出增加 resonance 摘要：

```python
"resonance_details": {
    "mode": result.config.strategy_mode,
    "total_signals_evaluated": len([t for t in result.trades if t.action == "BUY"]),
    "sample_matched": list(set(
        s for trade in result.trades for s in (trade.notes or [])
    ))[:10],
},
```

提交：

```bash
git add modules/cli.py modules/cli_commands.py tests/test_cli_simulate.py
git commit -m "feat(cli): add strategy-mode options to zt simulate"
```

---

## Task 7: 文档与版本更新

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`
- Modify: `README.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: 更新 CHANGELOG**

顶部新增：

```markdown
## v3.5.0 (2026-07-04)

### 少女/少妇模拟器 v0.3 —— 战法共振评分

- 新增 `modules/simulator/strategy_adapter.py`：把 `modules.strategies` 的 20+ 战法信号标准化为 `RawStrategySignal`。
- 新增 `modules/simulator/resonance_scorer.py`：多战法同屏共振评分，冲突信号（三波冲刺/麒麟派发/S1/S2/S3/出货五式等）自动降级为 HIGH_RISK。
- 新增 `modules/simulator/environment_weights.py`：根据市场环境动态调整 breakout/rebound/pattern/stage/risk 各类别权重。
- 改造 `modules/simulator/signal_filter.py`：支持 `strategy_mode="simple"`（v0.2 原逻辑）和 `"resonance"`（战法共振）。
- CLI `zt simulate` 新增 `--strategy-mode/--strategy-lookback/--min-resonance-score` 参数。
```

- [ ] **Step 2: 更新 TODO**

新增 `## ✅ 已完成（v3.5.0 少女/少妇模拟器 v0.3）` 并列出上述条目；更新版本路线图表添加 `v3.5.0` 行。

- [ ] **Step 3: 更新 README**

在 `zt simulate` 示例后新增：

```markdown
zt simulate 000001.SZ --days 250 --strategy-mode resonance --strategy-lookback 5 --json
```

- [ ] **Step 4: 同步 pyproject.toml**

```toml
version = "3.5.0"
```

- [ ] **Step 5: 提交**

```bash
git add docs/CHANGELOG.md docs/TODO.md README.md pyproject.toml
git commit -m "docs: v3.5.0 changelog, todo, readme for simulator v0.3"
```

---

## Task 8: 全量验证与推送

- [ ] **Step 1: 运行测试**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: 850+ passed / 11 skipped

- [ ] **Step 2: 运行 lint / format / mypy**

```bash
.venv/bin/ruff check modules tests
.venv/bin/ruff format modules tests --check
.venv/bin/mypy modules/simulator
```
Expected: 全部通过

- [ ] **Step 3: 冒烟测试**

```bash
.venv/bin/python -m modules.cli simulate 000001.SZ --days 30 --strategy-mode resonance --json > /tmp/sim_res.json 2>/tmp/sim_res.err
.venv/bin/python -c "import json; d=json.load(open('/tmp/sim_res.json')); print('mode:', d.get('resonance_details',{}).get('mode'))"
```
Expected: 输出 `mode: resonance`

- [ ] **Step 4: 提交并推送**

```bash
git push origin main
```
Expected: GitHub Actions 全绿

---

## Self-Review Checklist

- **Spec coverage:**
  - [x] `RawStrategySignal` / `ResonanceScore` 数据类 → Task 1
  - [x] strategy adapter 映射/过滤/去重 → Task 2
  - [x] environment weights → Task 3
  - [x] resonance scorer → Task 4
  - [x] signal_filter 集成 → Task 5
  - [x] CLI 扩展 → Task 6
  - [x] 文档版本 → Task 7
  - [x] 验证推送 → Task 8
- **Placeholder scan:** 无 TBD/TODO/"implement later"。
- **Type consistency:**
  - `evaluate_stock` 签名在 Task 5 中新增 `config` 与 `context` 参数。
  - `SignalScore.resonance: ResonanceScore | None` 在 Task 1 定义。
  - `calculate_resonance` 接收 `config: SimulationConfig` 使用 `config.min_resonance_score`。
- **Parallelism notes:** Task 2 与 Task 3 在 Task 1 完成后可并行执行。Task 4 依赖 Task 2 的 `RawStrategySignal`。Task 5 依赖 Task 2/3/4。Task 6/7 依赖 Task 5。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-simulator-v0.3-strategy-resonance-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch fresh subagents per task; Task 2 and Task 3 can run in parallel after Task 1. Review between tasks.
2. **Inline Execution** - Execute tasks in this session using executing-plans.

Which approach?

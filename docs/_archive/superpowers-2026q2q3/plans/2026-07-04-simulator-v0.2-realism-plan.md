# 少女/少妇模拟器 v0.2 真实感增强 —— 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `modules/simulator/` 中实现 A 股真实交易约束、真实成本模型、动态滑点、ATR 仓位、专业回测指标，使模拟器从 v0.1 概念验证升级到接近实盘回测水平。

**Architecture:** 新增 `execution_constraints.py`、`cost_model.py`、`slippage_model.py`、`metrics.py` 四个职责单一模块；扩展 `SimulationConfig/Position/TradeRecord/SimulationResult` 数据类；修改 `execution_engine.py`、`position_sizer.py`、`exit_manager.py`、`simulator.py` 消费新能力；新增 4 个测试文件覆盖边界规则；CLI 新增可选参数但保持默认行为不变。

**Tech Stack:** Python 3.10+, pytest, ruff, mypy, 标准库为主（dataclasses, datetime, statistics, math）。

## Global Constraints

- Python 3.10+，类型提示使用 `|` union 与 `from __future__ import annotations`。
- 优先使用标准库，不引入新的第三方依赖。
- 所有模块文件头包含 `#!/usr/bin/env python3`，中文 docstring 与注释。
- 数据库路径统一从 `os.getenv("DB_PATH", "data/stock_data.db")` 读取。
- 代码风格：ruff line-length 120，mypy ignore_missing_imports，中文注释。
- 每个新增功能必须有对应单元测试，TDD 顺序执行。
- 保持向后兼容：`SimulationConfig` 新增字段均带默认值，旧 CLI 调用行为不变。
- 反未来函数：决策只能使用当日收盘前可见信息，买入成交价为次日开盘价，卖出成交价为当日收盘价。
- 版本目标：zettaranc-skill v3.4.0。

---

## File Map

| 文件 | 类型 | 职责 |
|---|---|---|
| `modules/simulator/execution_constraints.py` | 新建 | A 股交易约束：T+1、涨跌停、停牌、ST、科创板/创业板 20%、北交所预留 |
| `modules/simulator/cost_model.py` | 新建 | 真实成本模型：佣金最低 5 元、印花税卖出单向、过户费 |
| `modules/simulator/slippage_model.py` | 新建 | 动态滑点：基于 ATR 与流动性，保留固定滑点兼容 |
| `modules/simulator/metrics.py` | 新建 | 专业回测指标：年化、夏普、Calmar、索提诺、基准对比、连胜连亏、回撤恢复时间 |
| `modules/simulator/__init__.py` | 修改 | 扩展 `SimulationConfig`/`Position`/`TradeRecord`/`SimulationResult` 数据类 |
| `modules/simulator/execution_engine.py` | 修改 | 使用 `CostModel` + `SlippageModel` 计算成交价与费用明细 |
| `modules/simulator/position_sizer.py` | 修改 | 支持 ATR 波动率仓位、最大单笔上限、现金利用率上限 |
| `modules/simulator/exit_manager.py` | 修改 | 集成 T+1 约束与跌停顺延卖出 |
| `modules/simulator/market_context.py` | 修改 | 增加恐慌/贪婪指数（涨跌停家数比、成交额趋势） |
| `modules/simulator/simulator.py` | 修改 | 在买入/卖出处调用约束层，使用 `metrics.py` 计算最终指标 |
| `modules/cli_commands.py` | 修改 | `cmd_simulate` 新增 `--cost-model/--slippage/--atr-sizing/--max-position-pct/--no-st/--benchmark` 等参数 |
| `tests/test_simulator_constraints.py` | 新建 | 约束层测试 |
| `tests/test_simulator_cost.py` | 新建 | 成本模型测试 |
| `tests/test_simulator_sizing.py` | 新建 | 仓位管理测试 |
| `tests/test_simulator_metrics.py` | 新建 | 回测指标测试 |
| `tests/test_simulator.py` | 修改 | 回归 v0.1 用例，补充数据类新字段断言 |
| `docs/CHANGELOG.md` | 修改 | 新增 v3.4.0 条目 |
| `docs/TODO.md` | 修改 | 更新 simulator v0.2 进度 |
| `README.md` | 修改 | 更新 `zt simulate` 示例 |

---

## Task 1: 扩展数据类（`__init__.py`）

**Files:**
- Modify: `modules/simulator/__init__.py`
- Test: `tests/test_simulator.py`（新增/修改数据类字段断言）

**Interfaces:**
- Produces: `SimulationConfig` 新增 `cost_model`, `slippage_model`, `use_dynamic_slippage`, `use_atr_sizing`, `atr_window`, `max_position_pct`, `cash_utilization_limit`, `allow_st`, `t1_lock`, `benchmark_code`, `apply_price_limit`, `apply_halt_filter`。
- Produces: `Position` 新增 `can_sell_date`, `entry_commission`, `is_st`。
- Produces: `TradeRecord` 新增 `stamp_duty`, `transfer_fee`, `notes`。
- Produces: `SimulationResult` 新增 `metrics: PerformanceMetrics | None`, `benchmark_curve`, `rejected_entries`。

- [ ] **Step 1: 写失败测试**

```python
def test_simulation_config_default_fields():
    from modules.simulator import SimulationConfig, CostModel, SlippageModel
    cfg = SimulationConfig()
    assert cfg.t1_lock is True
    assert cfg.apply_price_limit is True
    assert cfg.benchmark_code == "000300.SH"
    assert cfg.max_position_pct == 0.20
    assert cfg.cost_model.min_commission == 5.0
    assert cfg.slippage_model.base_slippage == 0.001
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_simulator.py::test_simulation_config_default_fields -v
```
Expected: FAIL, AttributeError

- [ ] **Step 3: 最小实现**

在 `modules/simulator/__init__.py` 中新增/修改：

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MarketRegime(Enum):
    STRONG = "强势"
    NEUTRAL = "震荡"
    WEAK = "弱势"


class SignalVerdict(Enum):
    PASS = "通过"
    NO_SIGNAL = "无信号"
    LOW_SCORE = "评分不足"
    HIGH_RISK = "风险过高"
    BAD_STAGE = "阶段不利"


@dataclass
class CostModel:
    """真实交易成本模型"""
    commission_rate: float = 0.00025
    min_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    apply_stamp_duty_on_sell: bool = True


@dataclass
class SlippageModel:
    """动态滑点模型"""
    base_slippage: float = 0.001
    volatility_multiplier: float = 0.5
    volume_penalty: float = 0.001


@dataclass
class MarketContext:
    date: str
    regime: MarketRegime
    index_trend: float
    breadth: float
    moneyflow_score: float
    notes: list[str] = field(default_factory=list)


@dataclass
class SignalScore:
    ts_code: str
    name: str
    date: str
    score: float
    b1_score: float
    trend_score: float
    volume_score: float
    risk_score: float
    signals: list[str]
    reasons: list[str]
    warnings: list[str]
    verdict: SignalVerdict = SignalVerdict.NO_SIGNAL


@dataclass
class Position:
    ts_code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    stop_loss: float
    take_profit: float
    risk_amount: float
    partial_exited: bool = False
    can_sell_date: str = ""
    entry_commission: float = 0.0
    is_st: bool = False


@dataclass
class TradeRecord:
    ts_code: str
    name: str
    action: str
    date: str
    price: float
    shares: int
    pnl: float = 0
    pnl_pct: float = 0
    reason: str = ""
    fee: float = 0
    stamp_duty: float = 0.0
    transfer_fee: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class SimulationConfig:
    initial_capital: float = 1_000_000.0
    start_date: str = ""
    end_date: str = ""
    max_positions: int = 5
    risk_per_trade: float = 0.02
    risk_per_trade_min: float = 0.01
    commission_rate: float = 0.0003
    slippage: float = 0.001
    position_score_threshold: float = 70.0
    signal_min_count: int = 2
    partial_take_profit_rr: float = 2.0
    trailing_ma_days: int = 20
    allow_short: bool = False
    market_neutral_max_positions: int = 2
    # v0.2 新增
    cost_model: CostModel = field(default_factory=CostModel)
    slippage_model: SlippageModel = field(default_factory=SlippageModel)
    use_dynamic_slippage: bool = False
    use_atr_sizing: bool = False
    atr_window: int = 20
    max_position_pct: float = 0.20
    cash_utilization_limit: float = 0.95
    allow_st: bool = False
    t1_lock: bool = True
    benchmark_code: str = "000300.SH"
    apply_price_limit: bool = True
    apply_halt_filter: bool = True


@dataclass
class SimulationResult:
    config: SimulationConfig
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    initial_capital: float = 0
    final_value: float = 0
    total_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    win_rate: float = 0
    profit_factor: float = 0
    total_trades: int = 0
    avg_holding_days: float = 0
    # v0.2 新增
    metrics: Any | None = None
    benchmark_curve: list[dict[str, Any]] = field(default_factory=list)
    rejected_entries: list[dict[str, Any]] = field(default_factory=list)


__all__ = [
    "MarketRegime",
    "SignalVerdict",
    "MarketContext",
    "SignalScore",
    "Position",
    "TradeRecord",
    "SimulationConfig",
    "SimulationResult",
    "CostModel",
    "SlippageModel",
]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_simulator.py::test_simulation_config_default_fields -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/__init__.py tests/test_simulator.py
git commit -m "feat(simulator): extend data classes for v0.2 realism"
```

---

## Task 2: 交易约束层（`execution_constraints.py`）

**Files:**
- Create: `modules/simulator/execution_constraints.py`
- Test: `tests/test_simulator_constraints.py`

**Interfaces:**
- Produces: `TradeConstraints` dataclass, `get_trade_constraints(ts_code, kline, prev_kline, name="", allow_st=False) -> TradeConstraints`, `is_price_limit_hit(kline, prev_close, ts_code) -> tuple[bool, str]`, `next_trading_date(dates: list[str], current: str) -> str`。
- Consumes: `DailyData` from `modules.indicators`。

- [ ] **Step 1: 写失败测试**

```python
def test_main_board_price_limit():
    from modules.simulator.execution_constraints import get_trade_constraints
    from modules.indicators import DailyData
    prev = DailyData(ts_code="000001.SZ", trade_date="20240101", open=10, high=11, low=9, close=10, vol=1000, amount=10000, pct_chg=0)
    kline = DailyData(ts_code="000001.SZ", trade_date="20240102", open=11.1, high=11.1, low=11.0, close=11.0, vol=1000, amount=10000, pct_chg=10)
    c = get_trade_constraints("000001.SZ", kline, prev)
    assert c.can_buy is False
    assert "涨停" in c.reason


def test_kcb_20pct_limit():
    from modules.simulator.execution_constraints import get_trade_constraints
    from modules.indicators import DailyData
    prev = DailyData(ts_code="688001.SH", trade_date="20240101", open=10, high=11, low=9, close=10, vol=1000, amount=10000, pct_chg=0)
    kline = DailyData(ts_code="688001.SH", trade_date="20240102", open=12.1, high=12.1, low=12.0, close=12.0, vol=1000, amount=10000, pct_chg=20)
    c = get_trade_constraints("688001.SH", kline, prev)
    assert c.can_buy is False


def test_st_filter_and_5pct():
    from modules.simulator.execution_constraints import get_trade_constraints
    from modules.indicators import DailyData
    prev = DailyData(ts_code="000002.SZ", trade_date="20240101", open=5, high=5.5, low=4.5, close=5, vol=1000, amount=10000, pct_chg=0)
    kline = DailyData(ts_code="000002.SZ", trade_date="20240102", open=5.26, high=5.26, low=5.25, close=5.25, vol=1000, amount=10000, pct_chg=5)
    c = get_trade_constraints("000002.SZ", kline, prev, name="*ST 测试", allow_st=False)
    assert c.is_st is True
    assert c.can_buy is False


def test_halted_stock():
    from modules.simulator.execution_constraints import get_trade_constraints
    from modules.indicators import DailyData
    prev = DailyData(ts_code="000003.SZ", trade_date="20240101", open=10, high=10, low=10, close=10, vol=1000, amount=10000, pct_chg=0)
    kline = DailyData(ts_code="000003.SZ", trade_date="20240102", open=10, high=10, low=10, close=10, vol=0, amount=0, pct_chg=0)
    c = get_trade_constraints("000003.SZ", kline, prev)
    assert c.is_halted is True
    assert c.can_sell is False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_simulator_constraints.py -v
```
Expected: 4 FAIL（ImportError / function not defined）

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
A 股交易约束层。

判断某只股票在指定交易日是否允许买入/卖出，包括：
- T+1：买入当日不可卖出
- 涨跌停：主板 ±10%，科创/创业板 ±20%，ST ±5%
- 停牌：成交量与成交额均为 0 且价格无变化
- ST 过滤：默认不允许买入 ST/*ST/退市
"""

from __future__ import annotations

from dataclasses import dataclass

from ..indicators import DailyData


@dataclass
class TradeConstraints:
    """某股票在某交易日的交易约束快照"""

    can_buy: bool
    can_sell: bool
    reason: str
    price_limit: float | None = None
    price_floor: float | None = None
    is_st: bool = False
    is_halted: bool = False


def _is_st_name(name: str | None) -> bool:
    """通过名称判断是否 ST/*ST/退市。"""
    if not name:
        return False
    upper = name.upper()
    return "ST" in upper or "退" in name


def _limit_pct(ts_code: str, is_st: bool) -> float:
    """返回涨跌停幅度。"""
    if is_st:
        return 0.05
    if ts_code.startswith("688") or ts_code.startswith("300") or ts_code.startswith("301"):
        return 0.20
    # 主板默认
    return 0.10


def _price_limits(prev_close: float, ts_code: str, is_st: bool) -> tuple[float, float]:
    """基于上一交易日收盘价计算涨停价与跌停价。"""
    pct = _limit_pct(ts_code, is_st)
    limit = round(prev_close * (1 + pct), 2)
    floor = round(prev_close * (1 - pct), 2)
    return limit, floor


def _is_halted(kline: DailyData, prev_kline: DailyData | None) -> bool:
    """
    判断当日是否停牌。

     heuristic：成交量与成交额均为 0，且开高低收与昨收相同。
    """
    if kline.vol == 0 and kline.amount == 0:
        return True
    if prev_kline is None:
        return False
    return (
        kline.vol == 0
        and kline.amount == 0
        and kline.open == prev_kline.close
        and kline.close == prev_kline.close
    )


def get_trade_constraints(
    ts_code: str,
    kline: DailyData,
    prev_kline: DailyData | None,
    name: str = "",
    allow_st: bool = False,
) -> TradeConstraints:
    """
    判断给定股票在当日的交易约束。

    Args:
        ts_code: 股票代码
        kline: 当日 K 线
        prev_kline: 上一交易日 K 线，用于计算涨跌停价；None 时跳过涨跌停判断
        name: 股票名称，用于 ST 判断
        allow_st: 是否允许交易 ST 股票

    Returns:
        TradeConstraints
    """
    is_st = _is_st_name(name)
    is_halted = _is_halted(kline, prev_kline)

    if is_halted:
        return TradeConstraints(
            can_buy=False,
            can_sell=False,
            reason="停牌",
            is_st=is_st,
            is_halted=True,
        )

    if is_st and not allow_st:
        return TradeConstraints(
            can_buy=False,
            can_sell=True,
            reason="ST 标的默认被过滤",
            is_st=True,
        )

    if prev_kline is None:
        return TradeConstraints(
            can_buy=True,
            can_sell=True,
            reason="无上一日数据，跳过涨跌停判断",
        )

    prev_close = prev_kline.close
    limit, floor = _price_limits(prev_close, ts_code, is_st)

    # 买入：若开盘价 >= 涨停价，视为无法买入
    can_buy = kline.open < limit
    buy_reason = "" if can_buy else f"开盘涨停（涨停价 {limit:.2f}）"

    # 卖出：若收盘价 <= 跌停价，视为当日无法卖出，需顺延
    can_sell = kline.close > floor
    sell_reason = "" if can_sell else f"收盘跌停（跌停价 {floor:.2f}）"

    if not can_buy and not can_sell:
        reason = f"{buy_reason}；{sell_reason}"
    elif not can_buy:
        reason = buy_reason
    elif not can_sell:
        reason = sell_reason
    else:
        reason = "正常交易"

    return TradeConstraints(
        can_buy=can_buy,
        can_sell=can_sell,
        reason=reason,
        price_limit=limit,
        price_floor=floor,
        is_st=is_st,
        is_halted=False,
    )


def next_trading_date(dates: list[str], current: str) -> str:
    """
    返回 current 日期之后的下一个交易日。

    Args:
        dates: 已排序的交易日字符串列表（YYYYMMDD）
        current: 当前日期

    Returns:
        下一交易日；若不存在则返回空字符串
    """
    for d in dates:
        if d > current:
            return d
    return ""
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_simulator_constraints.py -v
```
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/execution_constraints.py tests/test_simulator_constraints.py
git commit -m "feat(simulator): add A-share trade constraints (limit, halt, ST, T+1 prep)"
```

---

## Task 3: 真实成本模型（`cost_model.py`）

**Files:**
- Create: `modules/simulator/cost_model.py`
- Modify: `modules/simulator/execution_engine.py`
- Test: `tests/test_simulator_cost.py`

**Interfaces:**
- Produces: `calculate_costs(amount: float, action: str, cost_model: CostModel) -> dict[str, float]` 返回 `{"commission": float, "stamp_duty": float, "transfer_fee": float, "total": float}`。

- [ ] **Step 1: 写失败测试**

```python
def test_buy_cost_with_min_commission():
    from modules.simulator.cost_model import calculate_costs
    from modules.simulator import CostModel
    costs = calculate_costs(10000.0, "BUY", CostModel())
    assert costs["commission"] == 5.0
    assert costs["stamp_duty"] == 0.0
    assert costs["total"] == 5.0 + 0.1


def test_sell_cost_includes_stamp_duty():
    from modules.simulator.cost_model import calculate_costs
    from modules.simulator import CostModel
    costs = calculate_costs(20000.0, "SELL", CostModel())
    assert costs["stamp_duty"] == 20000.0 * 0.0005
    assert costs["total"] == max(20000.0 * 0.00025, 5.0) + costs["stamp_duty"] + 0.2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_simulator_cost.py -v
```
Expected: 2 FAIL

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
真实交易成本模型。

- 佣金：双向收取，最低 5 元
- 印花税：卖出方单向收取，默认千 0.5
- 过户费：双向万 0.1（沪市标准简化）
"""

from __future__ import annotations

from . import CostModel


def calculate_costs(amount: float, action: str, cost_model: CostModel) -> dict[str, float]:
    """
    计算单笔交易成本。

    Args:
        amount: 成交金额
        action: "BUY" / "SELL" / "PARTIAL_SELL"
        cost_model: 成本模型

    Returns:
        {"commission": 佣金, "stamp_duty": 印花税, "transfer_fee": 过户费, "total": 总费用}
    """
    commission = max(amount * cost_model.commission_rate, cost_model.min_commission)
    transfer_fee = amount * cost_model.transfer_fee_rate

    stamp_duty = 0.0
    if action in ("SELL", "PARTIAL_SELL") and cost_model.apply_stamp_duty_on_sell:
        stamp_duty = amount * cost_model.stamp_duty_rate

    return {
        "commission": round(commission, 2),
        "stamp_duty": round(stamp_duty, 2),
        "transfer_fee": round(transfer_fee, 2),
        "total": round(commission + stamp_duty + transfer_fee, 2),
    }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_simulator_cost.py -v
```
Expected: 2 PASS

- [ ] **Step 5: 修改 `execution_engine.py` 使用成本模型**

```python
from .cost_model import calculate_costs


def execute_buy(position, kline, config):
    fill_price = _apply_slippage_buy(kline.open, config.slippage)
    amount = fill_price * position.shares
    costs = calculate_costs(amount, "BUY", config.cost_model)
    return TradeRecord(
        ts_code=position.ts_code,
        name=position.name,
        action="BUY",
        date=kline.trade_date,
        price=round(fill_price, 3),
        shares=position.shares,
        reason=f"B1信号入场，止损{position.stop_loss:.2f}",
        fee=costs["total"],
        stamp_duty=costs["stamp_duty"],
        transfer_fee=costs["transfer_fee"],
        notes=["买入成交"],
    )
```

`execute_sell` 与 `execute_partial_sell` 同理，action 为 "SELL" / "PARTIAL_SELL"。

- [ ] **Step 6: 运行相关测试**

```bash
pytest tests/test_simulator.py tests/test_simulator_cost.py -v
```
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add modules/simulator/cost_model.py modules/simulator/execution_engine.py tests/test_simulator_cost.py
git commit -m "feat(simulator): realistic cost model with stamp duty and min commission"
```

---

## Task 4: 动态滑点模型（`slippage_model.py`）

**Files:**
- Create: `modules/simulator/slippage_model.py`
- Modify: `modules/simulator/execution_engine.py`
- Test: `tests/test_simulator_cost.py`（新增动态滑点用例）

**Interfaces:**
- Produces: `calculate_slippage(kline: DailyData, klines: list[DailyData], action: str, config: SimulationConfig) -> float`。

- [ ] **Step 1: 写失败测试**

```python
def test_dynamic_slippage_increases_with_atr():
    from modules.simulator.slippage_model import calculate_slippage
    from modules.simulator import SimulationConfig, SlippageModel
    from modules.indicators import DailyData
    klines = [
        DailyData(ts_code="000001.SZ", trade_date="20240101", open=10, high=12, low=9, close=10, vol=1000, amount=10000, pct_chg=0),
        DailyData(ts_code="000001.SZ", trade_date="20240102", open=10, high=12, low=9, close=10, vol=1000, amount=10000, pct_chg=0),
    ] * 20
    kline = klines[-1]
    cfg = SimulationConfig(use_dynamic_slippage=True, slippage_model=SlippageModel(base_slippage=0.001))
    s = calculate_slippage(kline, klines, "BUY", cfg)
    assert s > 0.001
```

- [ ] **Step 2-7: 实现、测试、提交**

实现逻辑：

```python
from ..indicators import DailyData
from . import SimulationConfig


def _atr(klines: list[DailyData], window: int = 20) -> float:
    if len(klines) < window + 1:
        return 0.0
    trs = []
    for i in range(1, window + 1):
        k = klines[-i]
        prev = klines[-i - 1]
        tr = max(k.high - k.low, abs(k.high - prev.close), abs(k.low - prev.close))
        trs.append(tr)
    return sum(trs) / len(trs)


def calculate_slippage(kline: DailyData, klines: list[DailyData], action: str, config: SimulationConfig) -> float:
    if not config.use_dynamic_slippage:
        return config.slippage

    base = config.slippage_model.base_slippage
    atr_value = _atr(klines, config.atr_window)
    price = kline.close or kline.open
    volatility_component = (atr_value / price) * config.slippage_model.volatility_multiplier if price else 0.0

    # 量比惩罚：成交量低于 20 日均量 50%
    if len(klines) >= 21:
        avg_vol = sum(k.vol for k in klines[-21:-1]) / 20
        if avg_vol > 0 and kline.vol / avg_vol < 0.5:
            volatility_component += config.slippage_model.volume_penalty

    return base + volatility_component
```

提交命令：

```bash
git add modules/simulator/slippage_model.py modules/simulator/execution_engine.py tests/test_simulator_cost.py
git commit -m "feat(simulator): dynamic slippage based on ATR and volume"
```

---

## Task 5: 仓位管理升级（`position_sizer.py`）

**Files:**
- Modify: `modules/simulator/position_sizer.py`
- Test: `tests/test_simulator_sizing.py`

**Interfaces:**
- Consumes: `SimulationConfig` 新增字段。
- Produces: `build_position` 返回的 `Position` 包含 `can_sell_date`、`entry_commission`、`is_st`。

- [ ] **Step 1: 写失败测试**

```python
def test_atr_sizing_caps_max_position_pct():
    from modules.simulator.position_sizer import build_position
    from modules.simulator import SimulationConfig
    cfg = SimulationConfig(use_atr_sizing=True, max_position_pct=0.10, risk_per_trade=0.02)
    pos = build_position("000001.SZ", "测试", "20240101", 100.0, 95.0, 110.0, cash=1_000_000, equity=1_000_000, config=cfg)
    assert pos is not None
    assert pos.shares * 100 <= 1_000_000 * 0.10
```

- [ ] **Step 2-7: 实现、测试、提交**

实现要点：

1. 在 `calculate_position_size` 中增加 ATR 路径：
   - 若 `config.use_atr_sizing` 且 klines 足够，风险每股 = max(entry - stop_loss, ATR(window) * 0.5)。
   - 否则使用固定止损。
2. 买入股数计算后增加 `max_position_pct` 截断：
   - `max_value = equity * config.max_position_pct`
   - `max_shares_by_value = int(max_value / entry_price / 100) * 100`
   - 最终 shares = min(原有 shares, max_shares_by_value, cash 限制 shares)
3. `build_position` 需要新增参数 `klines`（可选）与 `can_sell_date`。
4. 设置 `Position.entry_commission` 为预估佣金，便于 PnL 计算。

```python
def build_position(..., klines=None, can_sell_date="", is_st=False):
    shares, risk_amount = calculate_position_size(..., klines=klines)
    if shares <= 0:
        return None
    return Position(
        ...,
        can_sell_date=can_sell_date,
        entry_commission=round(shares * entry_price * config.cost_model.commission_rate, 2),
        is_st=is_st,
    )
```

提交：

```bash
git add modules/simulator/position_sizer.py tests/test_simulator_sizing.py
git commit -m "feat(simulator): ATR-based sizing and max position cap"
```

---

## Task 6: 退出管理增强（`exit_manager.py`）

**Files:**
- Modify: `modules/simulator/exit_manager.py`
- Test: `tests/test_simulator_constraints.py`（T+1 与跌停顺延用例）

**Interfaces:**
- Consumes: `Position.can_sell_date`, `TradeConstraints.can_sell`。
- Produces: `check_exit` 新增返回 "HOLD_T1" / "HOLD_LIMIT" 语义（action 仍为 HOLD，但 notes 记录原因）。

- [ ] **Step 1: 写失败测试**

```python
def test_t1_blocks_sell():
    from modules.simulator.exit_manager import check_exit
    from modules.simulator import Position, SimulationConfig
    from modules.indicators import DailyData
    pos = Position(ts_code="000001.SZ", name="测试", entry_date="20240101", entry_price=100, shares=100, stop_loss=95, take_profit=110, risk_amount=1000, can_sell_date="20240102")
    klines = [DailyData(ts_code="000001.SZ", trade_date="20240101", open=100, high=100, low=94, close=94, vol=100, amount=1000, pct_chg=-6)]
    action, _ = check_exit(pos, klines, SimulationConfig(t1_lock=True))
    assert action == "HOLD"
```

- [ ] **Step 2-7: 实现、测试、提交**

实现要点：

1. `check_exit` 签名改为 `check_exit(position, klines, config, constraints=None)`。
2. 止损/止盈判断前检查 `t1_lock` 与 `can_sell_date`：
   - 若当前日期 < `can_sell_date`，返回 `("HOLD", 0)`，但支持调用方通过返回的 action 或日志识别。
3. 若 `constraints` 存在且 `constraints.can_sell is False`，返回 `("HOLD", 0)`，并在 `position.notes` 或外部记录跌停顺延。

提交：

```bash
git add modules/simulator/exit_manager.py tests/test_simulator_constraints.py
git commit -m "feat(simulator): T+1 lock and limit-down deferral in exit manager"
```

---

## Task 7: 市场环境增强（`market_context.py`）

**Files:**
- Modify: `modules/simulator/market_context.py`
- Test: `tests/test_simulator.py`（市场环境相关用例）

**Interfaces:**
- Produces: `MarketContext.notes` 增加恐慌/贪婪描述。

- [ ] **Step 1: 写失败测试**

```python
def test_market_context_includes_breadth_notes():
    from modules.simulator.market_context import get_market_context
    ctx = get_market_context("20240115")
    assert any("涨停" in n or "跌停" in n for n in ctx.notes)
```

- [ ] **Step 2-7: 实现、测试、提交**

实现要点：

1. 在 `get_market_context` 中尝试查询 `daily_kline` 全市场当日数据，统计涨停家数、跌停家数。
2. 计算 `panic_greed_ratio = limit_up_count / max(limit_down_count, 1)`。
3. 若 ratio > 10 且成交额趋势向上 → 在 notes 中标记“情绪贪婪”；若 ratio < 0.5 或跌停 > 100 → 标记“情绪恐慌”。
4. 空数据时保持原有默认行为。

提交：

```bash
git add modules/simulator/market_context.py tests/test_simulator.py
git commit -m "feat(simulator): add market breadth panic/greed index"
```

---

## Task 8: 专业回测指标（`metrics.py`）

**Files:**
- Create: `modules/simulator/metrics.py`
- Modify: `modules/simulator/simulator.py`
- Test: `tests/test_simulator_metrics.py`

**Interfaces:**
- Produces: `PerformanceMetrics` dataclass, `calculate_metrics(equity_curve, benchmark_curve, trades) -> PerformanceMetrics`。

- [ ] **Step 1: 写失败测试**

```python
def test_calculate_metrics_basic():
    from modules.simulator.metrics import calculate_metrics, PerformanceMetrics
    equity_curve = [
        {"date": "20240101", "equity": 1000000},
        {"date": "20240102", "equity": 1100000},
        {"date": "20240103", "equity": 1050000},
    ]
    benchmark_curve = [
        {"date": "20240101", "close": 100},
        {"date": "20240102", "close": 102},
        {"date": "20240103", "close": 101},
    ]
    trades = []
    m = calculate_metrics(equity_curve, benchmark_curve, trades)
    assert isinstance(m, PerformanceMetrics)
    assert m.total_return == 0.05
    assert m.max_drawdown > 0
```

- [ ] **Step 2-7: 实现、测试、提交**

实现要点：

```python
@dataclass
class PerformanceMetrics:
    total_return: float = 0.0
    annualized_return: float = 0.0
    benchmark_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    gain_loss_ratio: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    volatility_annual: float = 0.0
```

函数 `calculate_metrics`：
1. 从 `equity_curve` 计算日收益率序列。
2. 年化收益 = (final/initial)^(252/N) - 1。
3. 夏普 = (mean(ret) / std(ret)) * sqrt(252)。
4. 索提诺 = (mean(ret) / std(negative rets)) * sqrt(252)。
5. 最大回撤与持续时间。
6. Calmar = annualized_return / max_drawdown（取绝对值）。
7. Beta / Alpha：对基准日收益做线性回归。
8. 交易统计：胜率、盈亏比、平均盈亏、最大连胜/连亏。

提交：

```bash
git add modules/simulator/metrics.py tests/test_simulator_metrics.py
git commit -m "feat(simulator): professional backtest metrics module"
```

---

## Task 9: 编排器集成（`simulator.py`）

**Files:**
- Modify: `modules/simulator/simulator.py`
- Test: `tests/test_simulator.py`（端到端回归）

**Interfaces:**
- Consumes: 上述所有新模块。
- Produces: `SimulationResult` 包含 `metrics`、`benchmark_curve`、`rejected_entries`。

- [ ] **Step 1: 写失败测试**

```python
def test_run_simulation_returns_metrics():
    from modules.simulator.simulator import run_simulation
    from modules.simulator import SimulationConfig
    result = run_simulation(ts_codes=["000001.SZ"], days=30, config=SimulationConfig())
    assert result.metrics is not None
```

- [ ] **Step 2-7: 实现、测试、提交**

实现要点：

1. `_run_single_day` 买入前调用 `get_trade_constraints`，记录 `rejected_entries`。
2. 买入成功后设置 `Position.can_sell_date = next_trading_date(dates, date)`。
3. 卖出前传入 `TradeConstraints`，T+1 或跌停时 HOLD。
4. 每日收盘后 `state.equity = _portfolio_value(...)`，并记录 `benchmark_curve`。
5. `_build_result` 中调用 `calculate_metrics`。
6. `summary_text` 扩展显示年化、Calmar、索提诺、基准收益、胜率、盈亏比。

提交：

```bash
git add modules/simulator/simulator.py tests/test_simulator.py
git commit -m "feat(simulator): integrate constraints, costs, sizing, and metrics into orchestrator"
```

---

## Task 10: CLI 参数扩展

**Files:**
- Modify: `modules/cli_commands.py`
- Modify: `modules/cli.py`（参数注册）
- Test: `tests/test_cli_subparser.py` 或新增 `tests/test_cli_simulate.py`

**Interfaces:**
- Produces: CLI 新增参数 `--benchmark`, `--cost-model`, `--slippage`, `--atr-sizing`, `--max-position-pct`, `--no-st`, `--t1-lock/--no-t1-lock`。

- [ ] **Step 1: 写失败测试**

```python
def test_cli_simulate_arguments_parsed():
    import argparse
    from modules.cli import build_parser  # 需确认 parser 是否可导入
    parser = build_parser()
    args = parser.parse_args(["simulate", "000001.SZ", "--atr-sizing", "--max-position-pct", "0.15"])
    assert args.atr_sizing is True
    assert args.max_position_pct == 0.15
```

- [ ] **Step 2-7: 实现、测试、提交**

实现要点：

1. 在 `modules/cli.py` 的 `simulate` subparser 中新增参数。
2. 在 `modules/cli_commands.py` 的 `cmd_simulate` 中读取参数并设置到 `SimulationConfig`。
3. JSON 输出增加 `metrics`、`benchmark_curve_sample`。

提交：

```bash
git add modules/cli.py modules/cli_commands.py tests/test_cli_simulate.py
git commit -m "feat(cli): extend zt simulate with v0.2 options"
```

---

## Task 11: 文档与版本更新

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`
- Modify: `README.md`
- Modify: `pyproject.toml`（version 字段）

- [ ] **Step 1: 更新 CHANGELOG**

在 `docs/CHANGELOG.md` 顶部新增：

```markdown
## v3.4.0 (2026-07-04)

### 少女/少妇模拟器 v0.2 —— 真实感增强

- A 股交易约束层：T+1、涨跌停（主板 ±10%、科创/创业板 ±20%、ST ±5%）、停牌、ST 过滤。
- 真实成本模型：佣金最低 5 元、印花税卖出单向、过户费双向。
- 动态滑点：基于 ATR 与流动性的自适应滑点，保留固定滑点兼容。
- ATR 仓位管理：波动率仓位 + 单笔最大净值占比 + 现金利用率上限。
- 专业回测指标：年化收益、夏普、Calmar、索提诺、基准对比、胜率、盈亏比、最大连胜/连亏、回撤恢复时间。
- 市场环境增强：涨跌停家数比、成交额趋势。
- CLI `zt simulate` 新增 `--benchmark/--cost-model/--slippage/--atr-sizing/--max-position-pct/--no-st` 等参数。
```

- [ ] **Step 2: 更新 TODO**

将 TODO 中 simulator v0.1 的进行中项改为已完成，新增 v0.2 项：

```markdown
## ✅ 已完成（v3.4.0 少女/少妇模拟器 v0.2）
- [x] A 股真实交易约束、成本模型、动态滑点、ATR 仓位、专业指标
```

- [ ] **Step 3: 更新 README**

在 `zt simulate` 示例段落后新增：

```markdown
zt simulate 000001.SZ --days 250 --atr-sizing --max-position-pct 0.15 --json
```

- [ ] **Step 4: 同步 pyproject.toml**

```toml
version = "3.4.0"
```

- [ ] **Step 5: 提交**

```bash
git add docs/CHANGELOG.md docs/TODO.md README.md pyproject.toml
git commit -m "docs: v3.4.0 changelog, todo, readme for simulator v0.2"
```

---

## Task 12: 全量验证与推送

- [ ] **Step 1: 运行测试**

```bash
python -m pytest tests/ -v
```
Expected: 791+ passed / 11 skipped

- [ ] **Step 2: 运行 lint / format**

```bash
ruff check modules/simulator tests/test_simulator*.py
ruff format modules/simulator tests/test_simulator*.py --check
```
Expected: 0 errors

- [ ] **Step 3: 运行 type check**

```bash
mypy modules/simulator
```
Expected: 0 errors

- [ ] **Step 4: 真实数据冒烟测试**

```bash
zt simulate 000001.SZ --days 250 --json | head -c 2000
```
Expected: 输出包含 `metrics` 字段且无异常

- [ ] **Step 5: 提交并推送**

```bash
git push origin main
```
Expected: GitHub Actions 全绿

---

## Self-Review Checklist

- **Spec coverage:**
  - [x] T+1 → Task 6
  - [x] 涨跌停/停牌/ST → Task 2 + Task 6
  - [x] 真实成本模型 → Task 3
  - [x] 动态滑点 → Task 4
  - [x] ATR 仓位 → Task 5
  - [x] 市场环境增强 → Task 7
  - [x] 专业指标 → Task 8
  - [x] CLI 扩展 → Task 10
  - [x] 文档更新 → Task 11
- **Placeholder scan:** 无 TBD/TODO/"implement later"。
- **Type consistency:** `Position.can_sell_date`、`TradeRecord.notes`、`SimulationResult.metrics` 在各任务中一致。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-simulator-v0.2-realism-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — 每个 Task 派一个 fresh subagent，我在每轮 review 后继续。
2. **Inline Execution** — 在当前会话中按 Task 顺序直接实现，关键 checkpoint 停下来 review。

Which approach?

# 少女/少妇模拟器 v0.2 —— 真实感增强设计文档

> 作者：Kimi Code Agent  
> 日期：2026-07-04  
> 版本：v0.2  
> 状态：设计待审  
> 关联版本：zettaranc-skill v3.4.0

---

## 1. 背景与目标

### 1.1 当前状态（v0.1）

`modules/simulator/` 已实现端到端日频回测：

- `market_context.py`：基于大盘指数三维度判定市场环境（强势/震荡/弱势）。
- `signal_filter.py`：调用 `screener.analyze_stock` 与价格/量能战法标签做共振过滤。
- `position_sizer.py`：按单笔风险金额与止损幅度计算买入股数，支持 A 股 100 股整数。
- `execution_engine.py`：开盘价买入、收盘价卖出，固定手续费 + 滑点。
- `exit_manager.py`：止损、2R 卤煮减半、移动止盈（跌破 20MA 或白线死叉黄线）。
- `simulator.py`：逐日 orchestrator，输出资金曲线与基础统计指标。
- CLI：`zt simulate`，支持 `--days/--capital/--max-positions/--risk/--score/--signals/--json`。
- 测试：`tests/test_simulator.py` 19 个用例覆盖核心路径。

### 1.2 v0.2 目标

在保持模块边界清晰、测试驱动、不引入外部新依赖的前提下，把模拟器从“概念验证级”提升到“接近 A 股实盘约束级”。

核心衡量标准：

1. 成交约束符合 A 股规则（T+1、涨跌停、停牌、ST、科创板/创业板 20%）。
2. 成本模型更真实（印花税单向、过户费、佣金最低 5 元、动态滑点）。
3. 风险/仓位模型更稳健（ATR 波动率仓位、最大单笔仓位上限、现金利用率上限）。
4. 输出指标更接近专业回测（基准对比、年化收益、夏普、Calmar、索提诺、胜率、盈亏比、最大连胜/连亏、回撤恢复时间）。
5. 反未来函数：所有决策必须基于当日收盘前可见信息，成交价为次日开盘价或当日收盘价，不可使用更高频数据。

---

## 2. 设计原则

1. **只做规则执行，不做预测**：不引入新模型，只利用已有 `modules/strategies/`、`modules/indicators/`、`modules/screener/` 的信号。
2. **最小侵入**：修改集中在 `modules/simulator/` 内，不破坏已有 CLI 参数默认值。
3. **测试先行**：每个新增真实感规则必须配套单元测试与边界用例。
4. **向后兼容**：`SimulationConfig` 新增字段均带默认值，旧 CLI 调用行为不变。
5. **数据可解释**：所有过滤、拒绝成交、仓位调整都要有 `reason` 或 `notes` 返回。

---

## 3. 组件级设计

### 3.1 交易约束层：`execution_constraints.py`（新增）

集中处理 A 股成交规则判断，返回“是否可买入/可卖出”及原因。

```python
@dataclass
class TradeConstraints:
    can_buy: bool
    can_sell: bool
    reason: str
    price_limit: float | None  # 当日涨停价
    price_floor: float | None  # 当日跌停价
    is_st: bool
    is_halted: bool
```

#### 3.1.1 T+1 约束

- 买入日期当日不可卖出，下一交易日方可卖出。
- `Position` 已含 `entry_date`，`exit_manager.check_exit` 在调用卖出前检查。
- `Position.can_sell_date` 记录可卖出日期（通常为 `entry_date` 的下一交易日）。
- 若当前日期早于 `can_sell_date`，即使触发止损也强制 `HOLD`，并在运行日志中记录“T+1 锁定”。

#### 3.1.2 涨跌停过滤

- 主板：±10%。
- 科创板/创业板（688/300/301 开头）：±20%。
- ST/*ST：±5%。
- 北交所：±30%（本版本暂不纳入，标记为 TODO）。

涨停价/跌停价基于 **上一交易日收盘价** 计算。买入日若开盘价 >= 涨停价，则无法买入；卖出日若开盘价 <= 跌停价，则无法卖出。收盘价触发卖出信号时，若当日跌停，则顺延到下一交易日开盘处理。

#### 3.1.3 停牌剔除

- 若某只股票当日 `vol == 0` 或 `amount == 0` 且价格无变化，视为停牌。
- 停牌日不可买入、不可卖出；已有持仓在停牌日无法平仓，顺延至复牌后按触发条件处理。

#### 3.1.4 ST 标记

- 通过 `stock_basic` 表 `name` 字段判断是否包含 "ST" / "*ST" / "退"。
- ST 标的涨跌停幅度为 ±5%，且默认不参与选股（可通过 `SimulationConfig.allow_st = True` 打开）。

### 3.2 成本模型：`cost_model.py`（新增）

替换 `execution_engine.py` 中简单的 `commission_rate` 双向收取逻辑。

```python
@dataclass
class CostModel:
    commission_rate: float = 0.00025      # 券商佣金，默认万 2.5
    min_commission: float = 5.0           # 最低佣金 5 元
    stamp_duty_rate: float = 0.0005       # 印花税卖出方千 0.5
    transfer_fee_rate: float = 0.00001    # 过户费双向万 0.1（沪市）
    apply_stamp_duty_on_sell: bool = True
```

- 买入费用 = max(成交金额 × commission_rate, min_commission) + 过户费。
- 卖出费用 = max(成交金额 × commission_rate, min_commission) + 印花税 + 过户费。
- 过户费按沪市标准双向万 0.1 简化处理，不区分沪/深。
- 保持 `SimulationConfig.commission_rate` 作为兼容字段，内部转换为 `CostModel`。

### 3.3 动态滑点：`slippage_model.py`（新增）

基于波动率与流动性动态调整滑点，替代固定 `slippage`。

```python
@dataclass
class SlippageModel:
    base_slippage: float = 0.001
    volatility_multiplier: float = 0.5     # ATR/price 每增加 1%，滑点增加多少
    volume_penalty: float = 0.001          # 量比 < 0.5 时额外滑点
```

- 动态滑点 = base_slippage + ATR(20) / close × volatility_multiplier + 流动性惩罚。
- 若买入价接近涨停（如开盘价 ≥ 涨停价 × 0.995），额外增加 0.1% 滑点以模拟排队成交成本。
- 若卖出价接近跌停（如收盘价 ≤ 跌停价 × 1.005），额外增加 0.1% 滑点。
- 保留固定滑点模式，通过 `SimulationConfig.use_dynamic_slippage = False` 切换。

### 3.4 仓位管理升级：`position_sizer.py` 扩展

新增两种可选仓位模式：

#### 3.4.1 ATR 波动率仓位

```python
atr_window: int = 20
max_position_pct: float = 0.20           # 单标的不超过净值 20%
```

- 单笔风险金额仍为 `equity × risk_per_trade`。
- 风险每股 = max(entry_price - stop_loss, ATR(20) × 0.5)。
- 买入股数 = risk_amount / 风险每股，按 100 股取整。
- 最终市值不超过 `equity × max_position_pct`。

#### 3.4.2 现金利用率上限

```python
cash_utilization_limit: float = 0.95       # 现金最多使用 95%，预留手续费
```

买入时 `max_cost = cash × cash_utilization_limit`，避免手续费导致现金透支。

### 3.5 市场环境增强：`market_context.py` 扩展

新增恐慌/贪婪指数：

- 全市场涨跌停家数比（基于 `daily_kline` 全表当日统计）。
- 成交额 20 日趋势。
- 北向资金净流入（若本地 `moneyflow` 表有数据则使用，否则跳过）。

判定规则扩展：

- 涨停家数 / 跌停家数 > 10 且成交额放大 → STRONG 确认。
- 跌停家数 > 100 或涨停/跌停 < 0.5 → 即使趋势得分高也降级为 NEUTRAL 或 WEAK。

### 3.6 统计指标升级：`simulator.py` 与 `metrics.py`（新增）

新增 `modules/simulator/metrics.py` 统一计算回测指标：

```python
@dataclass
class PerformanceMetrics:
    total_return: float
    annualized_return: float
    benchmark_return: float
    alpha: float
    beta: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # 交易日数
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    gain_loss_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    volatility_annual: float
```

- 基准默认使用沪深 300（000300.SH），可通过 `SimulationConfig.benchmark_code` 调整。
- 年化按 252 个交易日计算。
- Beta / Alpha 用日收益对基准日收益做线性回归。
- 最大回撤持续时间为“创新高到再次创新高”的最大交易日数。

### 3.7 CLI 参数扩展

保持现有参数不变，新增：

```bash
zt simulate --benchmark 000300.SH \
            --cost-model advanced \
            --slippage dynamic \
            --atr-sizing \
            --max-position-pct 0.20 \
            --no-st \
            --t1-lock
```

- `--cost-model advanced` 启用印花税/过户费/最低佣金。
- `--slippage dynamic` 启用 ATR/流动性滑点。
- `--atr-sizing` 启用 ATR 仓位。
- `--no-st` 剔除 ST（默认已剔除）。
- `--t1-lock` 显式启用 T+1（默认已启用）。

---

## 4. 数据流与接口变更

### 4.1 `SimulationConfig` 新增字段

```python
@dataclass
class SimulationConfig:
    # v0.1 已有字段保留...

    # v0.2 新增
    cost_model: CostModel = field(default_factory=CostModel)
    slippage_model: SlippageModel = field(default_factory=SlippageModel)
    use_dynamic_slippage: bool = False
    use_atr_sizing: bool = False
    atr_window: int = 20
    max_position_pct: float = 0.20
    cash_utilization_limit: float = 0.95
    allow_st: bool = False
    allow_short: bool = False            # v0.1 已有，语义不变
    t1_lock: bool = True
    benchmark_code: str = "000300.SH"
    apply_price_limit: bool = True
    apply_halt_filter: bool = True
```

### 4.2 `Position` 新增字段

```python
@dataclass
class Position:
    # v0.1 已有字段保留...

    can_sell_date: str = ""              # T+1 后可卖出日期
    entry_commission: float = 0.0
    is_st: bool = False
```

### 4.3 `TradeRecord` 新增字段

```python
@dataclass
class TradeRecord:
    # v0.1 已有字段保留...

    stamp_duty: float = 0.0
    transfer_fee: float = 0.0
    notes: list[str] = field(default_factory=list)
```

### 4.4 `SimulationResult` 新增字段

```python
@dataclass
class SimulationResult:
    # v0.1 已有字段保留...

    metrics: PerformanceMetrics | None = None
    benchmark_curve: list[dict[str, Any]] = field(default_factory=list)
    rejected_entries: list[dict[str, Any]] = field(default_factory=list)
```

---

## 5. 关键算法伪代码

### 5.1 买入过滤流程

```text
for candidate in filtered_candidates:
    加载 candidate 当日 K 线
    constraints = get_constraints(candidate, current_kline, prev_close)
    if not constraints.can_buy:
        record_rejected(candidate, constraints.reason)
        continue
    if not allow_st and constraints.is_st:
        record_rejected(candidate, "ST 标的被过滤")
        continue
    计算仓位（ATR 或固定风险）
    检查现金与最大仓位上限
    执行买入，记录费用明细
```

### 5.2 卖出过滤流程

```text
for position in positions:
    action, shares = check_exit(position, klines, config)
    if action == HOLD: continue
    if t1_lock and current_date < position.can_sell_date:
        record_note(position, "T+1 锁定")
        continue
    if action 需要卖出 and 当日跌停:
        record_note(position, "跌停无法卖出，顺延")
        continue
    执行卖出，记录费用明细
```

### 5.3 最大回撤持续时间

```text
peak_date = equity_curve[0].date
max_duration = 0
for point in equity_curve:
    if point.equity >= peak:
        peak = point.equity
        duration = point.date - peak_date
        max_duration = max(max_duration, duration)
        peak_date = point.date
return max_duration
```

---

## 6. 测试策略

### 6.1 新增测试文件

- `tests/test_simulator_constraints.py`：涨跌停、T+1、停牌、ST 过滤。
- `tests/test_simulator_cost.py`：成本模型、最低佣金、印花税方向。
- `tests/test_simulator_metrics.py`：夏普、Calmar、胜率、连胜连亏、基准对比。
- `tests/test_simulator_sizing.py`：ATR 仓位、最大仓位上限、现金利用率。

### 6.2 关键边界用例

1. 买入日涨停：买入失败，资金不变。
2. 卖出日跌停：信号触发但成交顺延。
3. 买入次日触发止损：因 T+1 无法卖出，第三日才执行。
4. ST 标的 ±5% 涨跌停与默认过滤。
5. 科创板 688 标的 20% 涨跌停。
6. 佣金低于 5 元按 5 元收取。
7. 印花税只在卖出时收取。
8. 单笔仓位超过 `max_position_pct` 被截断。

### 6.3 回归测试

- 原有 `tests/test_simulator.py` 19 个用例全部保留。
- 全量 pytest 目标：791+ passed / 11 skipped 无回归。
- ruff / mypy 零错误。

---

## 7. 风险与回退方案

| 风险 | 影响 | 回退方案 |
|---|---|---|
| 涨跌停数据不足（科创板历史） | 部分标的过滤过严 | 默认按主板 ±10% 处理，有明确代码段时按实际规则 |
| 停牌判断误判 | 错过买入机会或无法卖出 | 同时检查 `vol == 0` 与 `amount == 0` 连续两日才判定停牌 |
| 动态滑点引入过拟合 | 历史收益被美化 | 默认关闭动态滑点，仅通过 CLI/Config 显式开启 |
| ATR 仓位在次新股上失真 | 仓位过大 | ATR 窗口不足 20 日时回退到固定止损模式 |
| 基准数据缺失 | metrics 中 benchmark 字段为空 | `get_market_context` 已有空数据回退，metrics 计算时跳过 beta/alpha |

---

## 8. 版本与文档

- 版本号：zettaranc-skill **v3.4.0**。
- `docs/CHANGELOG.md`：新增 v3.4.0 条目，列出真实感增强内容。
- `docs/TODO.md`：将 simulator v0.2 标记为进行中。
- `README.md`：更新 `zt simulate` 命令示例，说明新增参数。
- `SKILL.md`：在工具链/回测相关段落可提及 simulator v0.2 支持 A 股真实约束，不展开细节。

---

## 9. 验收标准

- [ ] 新增 4 个测试文件，合计不少于 40 个新用例。
- [ ] 全部测试通过：791+ passed / 11 skipped。
- [ ] ruff / mypy 零错误。
- [ ] `zt simulate --json` 输出包含 `metrics` 与 `benchmark_curve`。
- [ ] 运行一次真实数据回测（如 2024 全年），输出年化/夏普/最大回撤。
- [ ] 文档（README/CHANGELOG/TODO）同步更新。

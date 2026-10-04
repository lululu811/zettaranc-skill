# 少女/少妇模拟器 v0.3 —— 战法共振评分设计文档

> 作者：Kimi Code Agent  
> 日期：2026-07-04  
> 版本：v0.3  
> 状态：设计待审  
> 关联版本：zettaranc-skill v3.5.0

---

## 1. 背景与目标

### 1.1 当前状态（v0.2）

`modules/simulator/` v0.2 已完成：

- A 股真实交易约束（T+1、涨跌停、停牌、ST 过滤）
- 真实成本模型（佣金最低 5 元、印花税、过户费）
- 动态滑点（ATR + 流动性）
- ATR 仓位管理 + 最大单笔上限 + 现金利用率上限
- 专业回测指标（年化、夏普、Calmar、索提诺、基准对比等）
- 市场环境恐慌/贪婪指数
- CLI `zt simulate` 扩展参数

v0.2 的选股信号仍依赖 `modules/screener.analyze_stock` 与 `signal_filter.py` 中对 reason/warning 字符串的推断，战法标签的识别脆弱且不完整。

### 1.2 v0.3 目标

把 `modules/strategies/` 中已有的 20+ 战法信号系统性地接入模拟器选股层，实现：

1. 多战法信号同屏共振评分。
2. 市场环境（强势/震荡/弱势）动态调整不同战法类别的入选权重。
3. 冲突信号（如 B1 + 冲刺波/派发）自动降级或过滤。
4. 保留 v0.2 所有真实约束与 CLI 行为，`strategy_mode="simple"` 时完全向后兼容。

---

## 2. 设计原则

1. **不重复造信号**：直接复用 `modules.strategies.detect_all_strategies`，只在其上做适配与评分。
2. **职责单一**：adapter 负责标准化，scorer 负责共振分，weights 负责环境权重，signal_filter 负责最终过滤。
3. **向后兼容**：新增 `strategy_mode` 配置，`simple` 模式保留 v0.2 原逻辑；`resonance` 模式启用新能力。
4. **测试驱动**：adapter、scorer、weights、集成四个层次分别测试。
5. **反未来函数**：只使用回测当日及之前可见的战法信号。

---

## 3. 组件级设计

### 3.1 战法适配层：`strategy_adapter.py`（新增）

把 `StrategySignal` 转换为模拟器内部可理解的 `RawStrategySignal`。

```python
@dataclass
class RawStrategySignal:
    """标准化后的战法信号"""

    strategy: str        # 如 "B1", "B2", "长安", "三波建仓", "麒麟吸筹"
    category: str        # 如 "breakout", "rebound", "risk", "stage"
    action: str          # "BUY" / "SELL" / "HOLD" / "WATCH"
    confidence: float    # 0.0 ~ 1.0
    trade_date: str      # YYYYMMDD
    reason: str = ""     # 原始描述
```

#### 3.1.1 战法名称映射表

| 原始 StrategyType | 标准化 strategy | category | 默认 action |
|---|---|---|---|
| B1 | B1 | rebound | BUY |
| B2 | B2 | breakout | BUY |
| B3 | B3 | consensus | BUY |
| SB1 | 超级B1 | rebound | BUY |
| 长安 | 长安 | breakout | BUY |
| 四分之三阴量 | 四分之三阴量 | risk | SELL |
| 娜娜 | 娜娜 | pattern | BUY |
| 异动+地量地价 | 异动地量 | rebound | BUY |
| 平行重炮 | 平行重炮 | breakout | BUY |
| 坑里起好货 | 坑里起好货 | rebound | BUY |
| 对称 VA | 对称VA | pattern | BUY |
| S1 | S1 | risk | SELL |
| S2 | S2 | risk | SELL |
| S3 | S3 | risk | SELL |
| 砖形图 | 砖形图 | risk | SELL |
| 买盘枯竭 | 买盘枯竭 | risk | SELL |
| 绿肥红瘦 | 绿肥红瘦 | risk | SELL |
| 阶梯放量下跌 | 阶梯放量下跌 | risk | SELL |
| 顶部大风车 | 顶部大风车 | risk | SELL |
| 三波·建仓波 | 三波建仓 | stage | BUY |
| 三波·拉升波 | 三波拉升 | stage | HOLD |
| 三波·冲刺波 | 三波冲刺 | stage | SELL |
| 麒麟·吸筹 | 麒麟吸筹 | stage | WATCH |
| 麒麟·拉升 | 麒麟拉升 | stage | HOLD |
| 麒麟·派发 | 麒麟派发 | stage | SELL |
| 麒麟·回落 | 麒麟回落 | stage | SELL |
| 滴滴战法 | 滴滴战法 | risk | SELL |
| MACD 金叉空 | MACD金叉空 | risk | SELL |
| MACD 死叉多 | MACD死叉多 | rebound | BUY |
| 出货五式 | 出货五式 | risk | SELL |
| 量比攻击 | 量比攻击 | breakout | WATCH |
| 灾后重建 | 灾后重建 | rebound | BUY |
| 跃跃欲试 | 跃跃欲试 | breakout | BUY |
| 关键K | 关键K | pattern | BUY/SELL |

未在映射表中的 StrategyType 被忽略，并记录 debug 日志。

#### 3.1.2 日期过滤

```python
def filter_by_date(
    signals: list[RawStrategySignal],
    trade_date: str,
    lookback_days: int = 5,
) -> list[RawStrategySignal]:
    """保留 trade_date 当日及前 lookback_days 个交易日内的信号。"""
```

反未来函数：只取 `trade_date` 及之前的信号；未来信号即使已计算也不使用。

#### 3.1.3 同类型去重

同一天同一 `strategy` 若出现多条，保留置信度最高的一条。

### 3.2 共振评分层：`resonance_scorer.py`（新增）

对单只股票当日可见的所有 `RawStrategySignal` 计算共振分。

```python
@dataclass
class ResonanceScore:
    """单只股票战法共振评分结果"""

    ts_code: str
    name: str
    date: str
    total_score: float          # 加权后的共振分，范围约 -2.0 ~ +2.0
    buy_score: float            # 买入类信号加权分
    risk_score: float           # 风险类信号加权分
    matched_strategies: list[str]   # 命中的 strategy 名称列表
    conflicts: list[str]        # 冲突说明
    verdict: SignalVerdict      # PASS / HIGH_RISK / NO_SIGNAL
```

#### 3.2.1 基础置信度聚合

对每一个 `RawStrategySignal`：

- `action == "BUY"`：贡献 `+confidence` 到 `buy_score`
- `action == "SELL"`：贡献 `+confidence` 到 `risk_score`
- `action == "WATCH"`：贡献 `+confidence * 0.3` 到 `buy_score`（观望偏机会）
- `action == "HOLD"`：贡献 `+confidence * 0.1` 到 `buy_score`（持有中性）

#### 3.2.2 类别加分

当多个不同 category 同时存在时，给予额外共振奖励：

```python
CATEGORY_RESONANCE_BONUS = {
    ("rebound", "breakout"): 0.15,
    ("rebound", "pattern"): 0.10,
    ("breakout", "stage"): 0.10,
    ("rebound", "stage"): 0.10,
}
```

#### 3.2.3 冲突降级规则

若 `risk_score` 中存在以下任一信号，直接触发 `SignalVerdict.HIGH_RISK`：

- 三波冲刺
- 麒麟派发
- 出货五式
- 顶部大风车
- S1 / S2 / S3（任意一个）
- 绿肥红瘦
- 阶梯放量下跌

若 `buy_score - risk_score < config.min_resonance_score`，判为 `NO_SIGNAL`。

#### 3.2.4 输出 verdict

```python
def calculate_resonance(
    raw_signals: list[RawStrategySignal],
    config: SimulationConfig,
) -> ResonanceScore:
    ...
```

### 3.3 环境权重层：`environment_weights.py`（新增）

根据 `MarketRegime` 返回各 category 的权重。

```python
DEFAULT_ENVIRONMENT_WEIGHTS: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.STRONG: {
        "breakout": 1.30,
        "pattern": 1.10,
        "rebound": 0.80,
        "stage": 1.00,
        "risk": 1.20,        # 风险信号权重更高，更容易触发过滤
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
```

用户可通过 `SimulationConfig.strategy_category_weights` 覆盖默认权重。

### 3.4 信号过滤层改造：`signal_filter.py`

在 `evaluate_stock` 中增加分支：

```python
if config.strategy_mode == "resonance":
    raw = strategy_adapter.adapt(
        detect_all_strategies(ts_code, days=120), trade_date
    )
    filtered_by_date = strategy_adapter.filter_by_date(
        raw, trade_date, config.strategy_lookback_days
    )
    resonance = resonance_scorer.calculate_resonance(filtered_by_date, config)
    weights = environment_weights.get_weights(context.regime, config)
    final_score = apply_weights(resonance, weights)
    ...
else:
    # 保留 v0.2 原逻辑
    ...
```

`SignalScore.score` 由 `final_score` 线性映射到 0-100 区间（例如 `score = min(100, max(0, final_score * 50 + 50))`），便于与 v0.2 阈值体系兼容。

### 3.5 配置扩展

```python
@dataclass
class SimulationConfig:
    # v0.2 字段保留...

    # v0.3 新增
    strategy_mode: str = "simple"          # "simple" / "resonance"
    strategy_lookback_days: int = 5
    min_resonance_score: float = 0.35
    strategy_category_weights: dict[str, float] = field(default_factory=dict)
```

---

## 4. 数据流

```text
run_simulation 逐日循环
  ├─ context = get_market_context(date)
  ├─ for each ts_code:
  │    └─ evaluate_stock(ts_code, date, klines, datasource, config, context)
  │         ├─ if resonance mode:
  │         │    ├─ signals = detect_all_strategies(ts_code, days=120)
  │         │    ├─ raw = strategy_adapter.adapt(signals)
  │         │    ├─ recent = strategy_adapter.filter_by_date(raw, date, lookback)
  │         │    ├─ resonance = resonance_scorer.calculate_resonance(recent, config)
  │         │    ├─ weights = environment_weights.get_weights(context.regime, config)
  │         │    ├─ final = apply_weights(resonance, weights)
  │         │    └─ build SignalScore from final
  │         └─ else:
  │              └─ use existing screener-based extraction
  └─ filter_signals(...) 保持不变
```

---

## 5. 测试策略

### 5.1 新增测试文件

- `tests/test_simulator_strategy_adapter.py`
  - 名称映射、日期过滤、同类型去重、未知类型忽略
- `tests/test_simulator_resonance.py`
  - 基础分计算、类别共振奖励、冲突降级、verdict 判断
- `tests/test_simulator_environment_weights.py`
  - 默认权重表、用户覆盖、regime 映射
- `tests/test_simulator_integration.py`（扩展）
  - `strategy_mode="resonance"` 跑通 `run_simulation`
  - `strategy_mode="simple"` 与 v0.2 结果一致

### 5.2 关键边界用例

1. B1 + B2 同日出现 → 共振分提升。
2. B1 + 三波冲刺 → verdict 为 HIGH_RISK。
3. STRONG 市场：B2/长安/娜娜权重提升，B1 权重下降。
4. WEAK 市场：B1/超跌/吸筹权重提升，breakout 权重下降。
5. `strategy_mode="simple"` 时，不调用 `detect_all_strategies`，避免额外计算开销。

### 5.3 回归目标

- 全量测试：`850+ passed / 11 skipped`
- ruff / mypy 零错误
- `zt simulate --strategy-mode simple` 行为与 v0.2 一致
- `zt simulate --strategy-mode resonance` 输出包含 `resonance_details`

---

## 6. 风险与回退方案

| 风险 | 影响 | 回退方案 |
|---|---|---|
| `detect_all_strategies` 计算开销大 | 回测变慢 | 默认保留 `simple` 模式；resonance 模式可缓存信号 |
| 战法映射表遗漏新 StrategyType | 信号被忽略 | adapter 输出 debug 日志，定期同步映射表 |
| 权重参数过拟合 | 历史收益美化 | 默认权重保守，用户可覆盖但需自行验证 |
| 冲突规则过严 | 错过机会 | 通过 `min_resonance_score` 和权重覆盖可调 |

---

## 7. 版本与文档

- 版本号：zettaranc-skill **v3.5.0**
- `docs/CHANGELOG.md`：新增 v3.5.0 条目
- `docs/TODO.md`：更新 simulator v0.3 进度
- `README.md`：更新 `zt simulate --strategy-mode resonance` 示例
- `pyproject.toml`：同步版本号

---

## 8. 验收标准

- [ ] 新增 4 个测试文件，合计不少于 40 个新用例。
- [ ] 全量测试通过：`850+ passed / 11 skipped`。
- [ ] ruff / mypy 零错误。
- [ ] `zt simulate --strategy-mode resonance --json` 输出包含 `resonance_details`。
- [ ] `zt simulate --strategy-mode simple --json` 与 v0.2 输出一致。
- [ ] 文档（README/CHANGELOG/TODO）同步更新至 v3.5.0。

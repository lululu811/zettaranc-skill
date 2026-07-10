# 少妇战法 v1.0 验收工程化 设计 Spec

> **目标**：把少妇战法（一条线）的 v1.0 验收从"分散的优化脚本 + 人工对比指标"升级为"一键命令 + 五项硬指标自动判定 + Walk-forward 防过拟合"。
>
> **版本**：v3.7.0（继 v3.6.0 模拟器 v0.4 之后的下一版本）
>
> **撰写日期**：2026-07-10
>
> **范围**：仅涉及"少妇战法"一条线，不动通用模拟器 / 战法共振 / 自我改进等模块。

---

## Context

### 现状

zettaranc-skill 已经是一个相当成熟的混合系统：

- **数据层**：Tushare + bridge + SQLite 三级降级，60+ 指标，30+ 战法
- **量化层**：`modules/loop_engine.py`（747 行）+ `modules/loop_engine_enhanced.py`（474 行）+ `modules/backtest_six_step.py`（879 行）+ `modules/simulator/`（17 个文件、3400 行）
- **优化层**：`scripts/optimization_v2.py` / `multifactor.py` / `walk_forward_validation*.py`，v3.3.3 已跑通 200 只股票 × 500 天的多因子优化（收益 +10778%、回撤 60%）
- **LLM 层**：SKILL.md（598 行）+ 29 篇 knowledge 文件，4 类意图路由（stock/career/life/chat）
- **测试**：892 passed / 11 skipped，质量门 12/12

### 问题

`docs/TODO.md` 中 v1.0 验收（v4.0.0）的硬指标写得很清楚：

| 指标 | 阈值 |
|------|------|
| 夏普比率 | > 0.5 |
| 最大回撤 | < 15% |
| 跑赢沪深 300 | ✅ |
| 胜率 | > 40% |
| Walk-forward OOS/IS | > 0.6 |

但**当前没有任何工程链路能一键完成这个验收**：

1. **三条路径各自独立**：多因子优化在 `optimization_multifactor.py`，少妇回测在 `backtest_six_step.py`，Walk-forward 在 `simulator/walk_forward.py`，参数没有打通
2. **没有自动达标判定**：v3.3.3 报告里写"夏普 0.61 / 胜率 38.7%"是人工对比，没人写"✅ / ❌"
3. **Walk-forward 只在模拟器里，少妇六步没有适配**：少妇六步的 Walk-forward 是 `walk_forward_validation_v2.py`，但它和回测结果没有自动关联
4. **多因子优化结果没有回写 param_registry**：v3.3.3 的最优参数 (J=5, SL=-5%, vol_shrink=0.8) 还是临时写在 JSON 报告里
5. **缺统一 CLI**：需要新增 `zt verify v1.0`，否则每次验收要写脚本

### 用户确认的优先级

通过 brainstorming 流程（2026-07-10）确认：

- **主目标**：把量化能力做到 v1.0 验收（AI 体验 / Web SaaS / 横向扩场景均推迟）
- **硬指标优先级**：**夏普 / Calmar / 胜率**三项为主，回撤可放宽至 ~25%
- **样本规模**：**50 只 × 250 天**，快速迭代优先（不是全市场验收）
- **策略主体**：**只走少妇战法一条线**（不引入战法共振、不引入通用模拟器）
- **首选路线 A**：少妇战法 v1.0 验收工程化（6-7 周）

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│  zt verify v1.0 [options]                ← CLI 入口         │
│      │                                                      │
│      ▼                                                      │
│  scripts/verify_v10.py (薄壳脚本)                           │
│      │                                                      │
│      ▼                                                      │
│  modules/verify/                ← 新建子包（v3.7.0）        │
│  ├─ pipeline.py                  统一回测管线                │
│  ├─ gates.py                     五项硬指标自动达标判定       │
│  ├─ walk_forward.py             少妇六步 WF 适配层          │
│  ├─ registry_writer.py           多因子最优参数 → param_registry │
│  └─ report.py                    JSON + Markdown 报告输出   │
│      │                                                      │
│      ▼                                                      │
│  现有模块（不修改核心逻辑）：                               │
│  ├─ modules/loop_engine.py       少妇六步状态机             │
│  ├─ modules/backtest_six_step.py 单股/组合回测              │
│  ├─ modules/simulator/metrics.py Sharpe/Calmar/WinRate     │
│  ├─ modules/self_optimizer/      param_registry             │
│  └─ scripts/optimization_*.py    多因子优化（只读数据源）   │
└─────────────────────────────────────────────────────────────┘
```

**关键设计原则**：

1. **不修改核心逻辑**：`loop_engine.py` / `backtest_six_step.py` / `simulator/` 一行不动
2. **新建薄壳包**：`modules/verify/` 是 100% 新增代码（约 800-1000 行），调用现有 API
3. **数据流单向**：optimization → param_registry → verify pipeline（解耦）
4. **CLI 一键化**：`zt verify v1.0` 一个命令出结果
5. **测试覆盖**：~49 个新用例，零回归

---

## 模块设计

### M1 — 统一回测管线（`modules/verify/pipeline.py`）

**目标**：把"单股回测 + 组合回测 + 多因子优化"三条独立路径合并成一个 `verify_v10_pipeline()` 函数。

```python
@dataclass
class VerifyResult:
    """v1.0 验收结果聚合"""
    per_stock: list[StockResult]           # 单股明细
    aggregate: AggregateMetrics            # 组合级指标
    gates: dict[str, GateResult]           # 五项硬指标 ✅/❌
    config_used: dict                      # 实际使用的参数
    meta: dict                             # 元信息（样本数、耗时、数据截止）


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
    skipped: bool = False                  # 数据不足时 True
    skip_reason: str = ""


def verify_v10_pipeline(
    ts_codes: list[str],
    days: int = 250,
    config: LoopConfig | None = None,      # None → 从 param_registry 读
    walk_forward: bool = False,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
) -> VerifyResult:
    """
    一键 v1.0 验收流水线：
    1. 加载 K 线（datasource 自动降级：Tushare → bridge → SQLite）
    2. 数据预检（跳过 < 60 天的股票）
    3. 跑回测（backtest_shaofu_portfolio）
    4. 算五项硬指标
    5. 走 gates 判定
    6. 返回 VerifyResult

    Raises:
        VerifyDataError: 所有股票都数据不足
    """
```

**依赖模块（仅读取，不修改）**：
- `modules/backtest_six_step.py::backtest_shaofu_portfolio`
- `modules/simulator/metrics.py`（复用 Sharpe/Calmar/WinRate 计算）
- `modules/loop_engine.py::LoopConfig`

**测试覆盖**（`tests/test_verify_pipeline.py`，~15 用例）：
- 基本流程：50 只股票正常回测
- 数据不足：某只股票 < 60 天，自动跳过
- 空回测：所有股票都没有 B1 信号
- config=None：自动从 param_registry 读取
- datasource 降级路径

---

### M2 — Walk-forward + 自动达标判定（`modules/verify/walk_forward.py` + `gates.py`）

**目标**：少妇六步加 Walk-forward（IS 寻优 → OOS 拼接），输出 Sharpe/Calmar/WinRate/Drawdown/Return 五项硬指标的 ✅/❌。

#### Walk-forward 实现（`walk_forward.py`）

**切片规则**：
```
[250 天数据]
    ↓ 按 wf_train_days=120, wf_test_days=60 切
[IS: 0-120]   [OOS: 120-180]
[IS: 60-180]  [OOS: 180-240]
[IS: 120-240] [OOS: 240-300]   ← 超出范围，跳过

最少 3 个 OOS 段才合法，否则降级单次回测
```

```python
@dataclass
class WFSplit:
    train_start: str
    train_end: str
    test_start: str
    test_end: str

@dataclass
class WFResult:
    splits: list[WFSplit]
    is_metrics: AggregateMetrics      # 样本内
    oos_metrics: AggregateMetrics     # 样本外（拼接）
    oos_is_ratio: float               # OOS/IS 关键比率


def walk_forward_verify(
    ts_codes: list[str],
    days: int = 250,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    param_space: dict | None = None,  # None 用 LoopConfig 默认
) -> WFResult:
    """
    滚动窗口 WF 验证：
    1. 按 wf_train_days / wf_test_days 切数据
    2. 每个 IS 窗口跑多因子优化找最优参数
    3. 用最优参数在 OOS 窗口跑回测
    4. 拼接所有 OOS 结果算 OOS_metrics
    5. 算 OOS/IS 比率

    切片数 < 3 时降级为单次回测（警告）
    """
```

#### 五项硬指标自动判定（`gates.py`）

```python
# 五项硬指标阈值（集中化，便于调整）
THRESHOLDS = {
    "sharpe":      {"min": 0.5,  "direction": "higher"},   # 夏普
    "calmar":      {"min": 0.5,  "direction": "higher"},   # Calmar = 年化收益/最大回撤
    "win_rate":    {"min": 0.40, "direction": "higher"},   # 胜率
    "max_drawdown":{"max": 0.25, "direction": "lower"},    # 最大回撤上限
    "oos_is_ratio":{"min": 0.60, "direction": "higher"},   # 防过拟合
}


@dataclass
class GateResult:
    name: str
    value: float
    threshold: float
    passed: bool
    message: str                       # 失败时的改进建议


def check_gates(metrics: AggregateMetrics, wf: WFResult | None = None) -> dict[str, GateResult]:
    """
    五项硬指标自动判定：
    - 如果 wf is None，跳过 oos_is_ratio
    - 失败时给改进建议（如"回撤过大，建议收紧止损至 -3%"）
    """
```

**判定输出示例**：
```
========================================
少妇战法 v1.0 验收结果（50 只 × 250 天）
========================================
✅ Sharpe   : 0.73   (≥ 0.50)
✅ Calmar   : 0.61   (≥ 0.50)
✅ WinRate  : 42.3%  (≥ 40.0%)
❌ MaxDD    : 28.4%  (≤ 25.0%)   ← 需收紧止损
✅ OOS/IS   : 0.68   (≥ 0.60)

总评: 4/5 通过 ⚠️  待 MaxDD 优化
========================================
```

**测试覆盖**（~18 用例）：
- `tests/test_verify_gates.py`（10）：5 项指标各 2 个用例（pass / fail）
- `tests/test_verify_walk_forward.py`（8）：基本切片、OOS 拼接、降级、IS/OOS 比率

---

### M3 — 多因子优化结果回写 param_registry（`modules/verify/registry_writer.py`）

**目标**：v3.3.3 多因子优化的最优参数走 Darwin 自优化管线进入 `param_registry`，少妇回测优先读 registry 而不是用 LoopConfig 默认值。

```python
@dataclass
class RegistryWriteReport:
    written: int
    skipped: int
    warnings: list[str]


def write_optimization_to_registry(
    optimization_results: dict,          # v3.3.3 的 JSON 输出格式
    strategy_name: str = "shaofu_v1",
) -> RegistryWriteReport:
    """
    把多因子优化结果转成 Darwin param_registry 格式，写入。
    输入: optimization_multifactor_results.json
    输出: param_registry 新增条目 'shaofu_v1'
    """


def load_config_from_registry(strategy_name: str = "shaofu_v1") -> LoopConfig | None:
    """
    从 param_registry 读出 LoopConfig
    找不到返回 None（pipeline 会用默认值）
    """
```

**LoopConfig 扩展**（仅新增类方法，不改现有字段）：
```python
# modules/loop_engine.py（追加，不修改现有代码）
@dataclass
class LoopConfig:
    # ... 现有字段保持不变 ...

    @classmethod
    def from_registry(cls, strategy_name: str = "shaofu_v1") -> "LoopConfig | None":
        """从 Darwin param_registry 读取，无记录时返回 None"""
```

**测试覆盖**（~6 用例，`tests/test_verify_registry_writer.py`）：
- 写入 v3.3.3 结果
- 读出 LoopConfig
- 找不到时返回 None
- 重复写入（覆盖 vs 跳过策略）

---

### M4 — `zt verify v1.0` CLI + 报告输出（`modules/verify/report.py` + `scripts/verify_v10.py`）

**目标**：一键命令，输出 JSON + Markdown 报告。

#### CLI 设计

```bash
# 默认：50 只 × 250 天
zt verify v1.0

# 自定义样本
zt verify v1.0 --limit 50 --days 250

# 启用 Walk-forward
zt verify v1.0 --limit 50 --days 250 --walk-forward

# Walk-forward 自定义窗口
zt verify v1.0 --walk-forward --wf-train 120 --wf-test 60

# JSON 输出（宿主页面用）
zt verify v1.0 --json

# 指定输出路径
zt verify v1.0 --output data/reports/my_verify.json

# 只 JSON 不 Markdown
zt verify v1.0 --json --no-markdown
```

**参数范围**：
- `--limit N`：[10, 500]，默认 50
- `--days N`：[120, 1000]，默认 250
- `--wf-train N`：[60, 500]，默认 120
- `--wf-test N`：[30, 200]，默认 60

#### 报告输出（`modules/verify/report.py`）

**输出文件**：
```
data/reports/verify_v10_<timestamp>.json    # 结构化（source of truth）
data/reports/verify_v10_<timestamp>.md      # 人读（含五项指标表格）
```

**JSON Schema（简化）**：
```json
{
  "timestamp": "2026-07-10T15:30:00",
  "config_used": {"j_threshold": 5, "stop_loss_pct": -0.05, "vol_shrink": 0.8},
  "config_source": "param_registry:shaofu_v1",
  "sample": {"ts_codes": [...50 stocks...], "days": 250},
  "walk_forward": {
    "enabled": true,
    "train_days": 120,
    "test_days": 60,
    "splits": 3,
    "is_metrics": {...},
    "oos_metrics": {...},
    "oos_is_ratio": 0.68
  },
  "aggregate": {
    "total_trades": 335,
    "win_rate": 0.423,
    "total_return_pct": 23.7,
    "annual_return_pct": 18.4,
    "sharpe": 0.73,
    "calmar": 0.61,
    "max_drawdown": 0.284,
    "sortino": 1.05
  },
  "gates": {
    "sharpe": {"value": 0.73, "threshold": 0.5, "passed": true},
    "calmar": {"value": 0.61, "threshold": 0.5, "passed": true},
    "win_rate": {"value": 0.423, "threshold": 0.4, "passed": true},
    "max_drawdown": {"value": 0.284, "threshold": 0.25, "passed": false, "message": "..."},
    "oos_is_ratio": {"value": 0.68, "threshold": 0.6, "passed": true}
  },
  "passed_count": 4,
  "total_count": 5,
  "summary": "4/5 通过 ⚠️  MaxDD 待优化",
  "per_stock": [...] 
}
```

**Markdown 模板**（简化）：
```markdown
# 少妇战法 v1.0 验收报告

**日期**：2026-07-10  
**样本**：50 只 × 250 天  
**耗时**：42.3 秒

## 五项硬指标

| 指标 | 实际 | 阈值 | 判定 |
|------|------|------|------|
| 夏普 | 0.73 | ≥ 0.50 | ✅ |
| Calmar | 0.61 | ≥ 0.50 | ✅ |
| 胜率 | 42.3% | ≥ 40.0% | ✅ |
| 最大回撤 | 28.4% | ≤ 25.0% | ❌ |
| OOS/IS | 0.68 | ≥ 0.60 | ✅ |

**总评**：4/5 通过 ⚠️ 待 MaxDD 优化

## 改进建议

- 回撤过大 → 建议收紧止损至 -3%（当前 -5%）
```

**测试覆盖**（~10 用例）：
- `tests/test_verify_cli.py`（5）：CLI 子命令分发、参数解析
- `tests/test_verify_report.py`（5）：JSON 结构、Markdown 渲染、时间戳

---

## 数据契约

### 输入

```python
@dataclass
class VerifyInput:
    ts_codes: list[str]            # 股票代码列表
    days: int = 250                # 回测天数
    config: LoopConfig | None      # None → 读 registry
    walk_forward: bool = False
    wf_train_days: int = 120
    wf_test_days: int = 60
    datasource: DataSource | None  # None → get_datasource("auto")
```

### 输出

```python
@dataclass
class VerifyResult:
    per_stock: list[StockResult]
    aggregate: AggregateMetrics
    gates: dict[str, GateResult]
    config_used: dict
    meta: dict
```

### param_registry 条目格式

```python
{
    "strategy_name": "shaofu_v1",
    "params": {
        "j_threshold": 5,
        "stop_loss_pct": -0.05,
        "vol_shrink_threshold": 0.8,
        "bbi_break_days": 2,
        "min_holding_days": 3,
        "lu_half": True,
        "position_pct": 0.3
    },
    "source": "optimization_multifactor_v3.3.3",
    "created_at": "2026-07-10T15:30:00",
    "tags": ["v3.7.0", "auto-generated"]
}
```

---

## 错误处理矩阵

| 失败场景 | 检测点 | 处理方式 |
|---------|--------|----------|
| **数据不足** | 某只股票 K 线 < 60 天 | 跳过该股，报告中标注"数据不足，跳过 N 只" |
| **Tushare API 超限** | rate_limiter 抛 `RateLimitExceeded` | 自动重试 3 次（已有），失败则在报告中标注 |
| **空回测** | 全部股票都没有 B1 信号 | 报告输出"零交易"，不抛异常 |
| **Walk-forward 切片失败** | 切片数 < 3 | 自动降级到单次回测，标注"WF 不可用" |
| **param_registry 不存在** | 读不到 `shaofu_v1` 条目 | 降级用 LoopConfig 默认值，warning |
| **超耗时** | 单股回测 > 60 秒 | 记录 slow_stocks 列表，输出警告（不中断） |
| **pytest 真实数据缺失** | 无 TUSHARE_TOKEN | 跳过，标记 `@pytest.mark.realdata` |

---

## 测试策略

```
tests/
├─ test_verify_pipeline.py           (~15 用例)
│  ├─ test_pipeline_basic_50_stocks
│  ├─ test_pipeline_with_registry_config
│  ├─ test_pipeline_data_shortage_skip
│  ├─ test_pipeline_zero_trades
│  ├─ test_pipeline_datasource_degradation
│  └─ ...
├─ test_verify_gates.py              (~10 用例)
│  ├─ test_sharpe_threshold_pass
│  ├─ test_sharpe_threshold_fail
│  ├─ test_calmar_threshold
│  ├─ test_winrate_threshold
│  ├─ test_drawdown_threshold
│  ├─ test_oos_is_ratio
│  └─ ...
├─ test_verify_walk_forward.py       (~8 用例)
│  ├─ test_wf_split_basic
│  ├─ test_wf_oos_concat
│  ├─ test_wf_degrade_to_single
│  └─ ...
├─ test_verify_registry_writer.py    (~6 用例)
│  ├─ test_write_v3_3_3_results
│  ├─ test_read_back_from_registry
│  ├─ test_duplicate_write_strategy
│  └─ ...
├─ test_verify_cli.py                (~5 用例)
│  ├─ test_cli_basic
│  ├─ test_cli_walk_forward
│  ├─ test_cli_json_output
│  └─ ...
└─ test_verify_report.py             (~5 用例)
   ├─ test_json_structure
   ├─ test_markdown_rendering
   └─ ...
```

**验证标准**：

- `pytest tests/ -v` → **941 passed**, 11 skipped（892 + 49 新增）
- `ruff check modules/verify tests/test_verify*` → 零错误
- `corpus/quality_check.py SKILL.md` → 12/12（SKILL.md 不动）
- 真实数据回归：`pytest tests/ -m slow -v` → 通过
- `zt verify v1.0 --limit 50 --days 250 --walk-forward` → 单次 < 5 分钟

---

## 边界条件

1. **股票数上下限**：`--limit` 范围 [10, 500]，默认 50
2. **天数上下限**：`--days` 范围 [120, 1000]，默认 250
3. **Walk-forward 切片数**：最少 3 段（IS + OOS × 3 = 360 天），否则警告并降级
4. **五项硬指标阈值**集中放在 `modules/verify/gates.py::THRESHOLDS`，方便后续调整
5. **CLI 输出格式**：JSON 是 source of truth，Markdown 由 JSON 渲染
6. **param_registry 命名规范**：`shaofu_v1` 为默认 strategy_name，避免与现有 Darwin 条目冲突

---

## 安全边界（对齐 SKILL.md Safety Surface）

- `verify` 命令**只是离线分析工具**，不在 Skill 路由表里暴露给宿主
- 报告里出现的交易记录是**历史回测**，不构成投资建议（与 SKILL.md 一致）
- 所有参数变更**只写本地 SQLite + param_registry**，不推送、不外传
- 新增的 `LoopConfig.from_registry()` 是类方法，**不破坏现有 dataclass 行为**

---

## 实施顺序

```
M1 统一管线 (2-3 周)        ← 基础，pipeline 是后续依赖
   ↓
M2 Walk-forward + Gates (2 周)  ← M1 完成后立刻做
   ↓
M3 Registry 回写 (1 周)     ← 可以和 M2 并行
   ↓
M4 CLI + 报告 (1 周)        ← 最后整合
```

**总体时间估算**：6-7 周（每周按 5 个工作日、单人工作量算）

---

## 版本发布

| 版本 | 主题 | 验收 |
|------|------|------|
| **v3.7.0** | 少妇战法 v1.0 验收工程化 | M1+M2+M3+M4 全过 |

**发布清单**：

- [ ] `docs/CHANGELOG.md` 加 v3.7.0 段（≥ 4 项 added/changed）
- [ ] `pyproject.toml` 同步 3.7.0
- [ ] `README.md` 加 v3.7.0 章节 + 使用示例
- [ ] 跑一次完整 `zt verify v1.0 --limit 50 --days 250 --walk-forward`，把结果截图/JSON 贴到 release notes
- [ ] Git tag `v3.7.0`，push 到 GitHub

---

## 风险与权衡

| 风险 | 应对 |
|------|------|
| **M1 复用现有 API 时遇到接口不顺** | 优先在 `modules/verify/` 内部做适配层，不动 `backtest_six_step.py` |
| **Walk-forward 在 50 只 × 250 天耗时过长** | wf_train_days 默认 120、最少 3 切片；若单次 > 5 分钟，自动降级 |
| **五项硬指标长期不达标** | gates.py 的建议消息给出具体改进方向（止损收紧、j_threshold 调整） |
| **param_registry 与 Darwin 自优化冲突** | 用独立 strategy_name (`shaofu_v1`) 区分；不修改 Darwin 既有数据 |
| **新代码量较大（~800-1000 行 + ~49 用例）** | 严格分 M 提交，每个 M 独立 review |

---

## 不在本 Spec 范围

明确**不做**（避免 scope creep）：

- ❌ 战法共振模式（`loop_engine_enhanced.py`）—— TODO v0.8 再说
- ❌ 通用模拟器改造（`modules/simulator/`）—— 已经 v0.4，下一版本再迭代
- ❌ 全市场（5000+）验收 —— 当前 50 只够了
- ❌ Web 看板 / SaaS / 多用户 / 付费
- ❌ LLM 点评版报告（TODO v0.8）
- ❌ 实盘对接 / 真实下单（SKILL.md 红线）
- ❌ life/career/business 三个意图深化
- ❌ 自优化 Darwin 管线改造

---

## 参考资料

- `docs/TODO.md` — v4.0.0 验收标准（夏普>0.5 / 回撤<15% 等）
- `reports/OPTIMIZATION_COMPARISON_50vs200.md` — v3.3.3 多因子优化对比
- `reports/FINAL_MULTIFACTOR_OPTIMIZATION_REPORT.md` — 完整 4 phase 优化结果
- `modules/loop_engine.py` — 少妇六步状态机（基础）
- `modules/loop_engine_enhanced.py` — 战法共振（仅参考，不引入）
- `modules/backtest_six_step.py` — 单股/组合回测（只读）
- `modules/simulator/metrics.py` — Sharpe/Calmar/WinRate 计算（复用）
- `modules/simulator/walk_forward.py` — 模拟器 WF（参考但不直接复用）
- `scripts/optimization_multifactor.py` — 多因子优化（只读数据源）

---

**Spec 撰写**：AI Assistant  
**审核**：Z 哥（万千）思维框架 · 用户（chenleiitaz）  
**版本**：v3.7.0 设计稿  
**日期**：2026-07-10
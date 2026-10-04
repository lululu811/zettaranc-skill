# 少女/少妇模拟器 v0.4 —— Walk-forward 参数寻优设计文档

> 作者：Kimi Code Agent  
> 日期：2026-07-04  
> 版本：v0.4  
> 状态：设计待审  
> 关联版本：zettaranc-skill v3.6.0

---

## 1. 背景与目标

### 1.1 当前状态（v0.3）

`modules/simulator/` v0.3 已完成：

- A 股真实交易约束（T+1、涨跌停、停牌、ST 过滤）
- 真实成本模型（佣金最低 5 元、印花税、过户费）
- 动态滑点（ATR + 流动性）
- ATR 仓位管理 + 最大单笔上限 + 现金利用率上限
- 专业回测指标（年化、夏普、Calmar、索提诺、基准对比等）
- 市场环境恐慌/贪婪指数
- 战法共振评分（20+ 战法信号标准化、多战法共振、冲突降级）
- 环境动态权重（STRONG/NEUTRAL/WEAK 下 breakout/rebound/pattern/stage/risk 权重）
- CLI `zt simulate` 扩展参数（`--strategy-mode/--strategy-lookback/--min-resonance-score` 等）

v0.3 的选股与仓位参数仍依赖用户手动指定或默认值，缺乏科学的样本外验证机制，容易过拟合。

### 1.2 v0.4 目标

引入**滚动样本内训练 + 样本外验证**的自动化参数寻优，实现：

1. 对 `SimulationConfig` 中一组可调参数定义搜索空间。
2. 将历史数据切成多个滚动窗口：每个窗口前 N 天为 IS（训练），后 M 天为 OOS（验证）。
3. 在每个窗口内对所有参数组合运行 `run_simulation`，按目标函数选出最佳参数。
4. 用该窗口选出的最佳参数跑下一个 OOS 窗口，拼接成全 OOS 资金曲线。
5. 输出：每个窗口的最佳参数、全 OOS 统计指标、过拟合检查（IS vs OOS 差距）。

---

## 2. 设计原则

1. **不重复造回测引擎**：复用 `run_simulation`，只在其上做窗口切分与参数搜索。
2. **职责单一**：参数空间定义、walk-forward 执行、报告输出三个模块分离。
3. **向后兼容**：新增 `--walk-forward` CLI 参数，默认关闭；原有 `zt simulate` 行为不变。
4. **测试驱动**：参数空间、walk-forward 执行、报告输出、集成四个层次分别测试。
5. **反未来函数**：每个窗口只使用 IS 数据选参数，OOS 数据完全不参与参数选择。

---

## 3. 组件级设计

### 3.1 参数空间层：`param_space.py`（新增）

定义参数搜索空间与网格生成。

```python
@dataclass
class ParamDimension:
    """参数维度定义"""

    name: str                # SimulationConfig 字段名
    param_type: str          # "float" | "int" | "choice"
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: list[Any] = field(default_factory=list)


def generate_grid(dimensions: list[ParamDimension]) -> list[dict[str, Any]]:
    """
    生成参数网格。

    Args:
        dimensions: 参数维度列表

    Returns:
        所有参数组合的列表
    """
    ...
```

#### 3.1.1 默认参数空间

```python
DEFAULT_PARAM_SPACE: list[ParamDimension] = [
    ParamDimension("min_resonance_score", "float", 0.15, 0.55, 0.10),
    ParamDimension("risk_per_trade", "float", 0.01, 0.03, 0.01),
    ParamDimension("position_score_threshold", "float", 60.0, 80.0, 10.0),
    ParamDimension("max_position_pct", "float", 0.10, 0.30, 0.10),
]
```

用户可通过 CLI 参数 `--param-*` 覆盖默认范围。

### 3.2 Walk-forward 执行层：`walk_forward.py`（新增）

执行滚动窗口切分、参数搜索、OOS 拼接。

```python
@dataclass
class WalkForwardConfig:
    """Walk-forward 配置"""

    train_days: int = 120
    test_days: int = 60
    objective: str = "calmar"  # "calmar" | "sharpe" | "sortino" | "total_return"
    param_space: list[ParamDimension] = field(default_factory=lambda: DEFAULT_PARAM_SPACE)
    anchored: bool = False  # True = 训练窗口从起点固定增长；False = 固定长度滑动


@dataclass
class WalkForwardWindow:
    """单个窗口的 IS/OOS 结果"""

    window_index: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str
    best_params: dict[str, Any]
    is_score: float
    oos_score: float
    is_result: SimulationResult
    oos_result: SimulationResult


@dataclass
class WalkForwardResult:
    """Walk-forward 完整结果"""

    config: WalkForwardConfig
    windows: list[WalkForwardWindow]
    oos_equity_curve: list[dict[str, Any]]
    oos_metrics: PerformanceMetrics
    overfit_ratio: float  # IS 平均收益 / OOS 平均收益


def run_walk_forward(
    ts_codes: list[str] | None,
    total_days: int,
    wf_config: WalkForwardConfig,
    base_config: SimulationConfig,
    datasource: DataSource | None = None,
) -> WalkForwardResult:
    """
    执行 walk-forward 参数寻优。

    Args:
        ts_codes: 股票池
        total_days: 总回测天数
        wf_config: walk-forward 配置
        base_config: 基础模拟配置（不含待优化参数）
        datasource: 数据源

    Returns:
        WalkForwardResult
    """
    ...
```

#### 3.2.1 窗口切分算法

```python
def _split_windows(
    dates: list[str],
    train_days: int,
    test_days: int,
    anchored: bool,
) -> list[tuple[int, int, int]]:
    """
    切分窗口。

    Returns:
        [(is_start_idx, is_end_idx, oos_end_idx), ...]
    """
    windows = []
    step = test_days
    for oos_end_idx in range(train_days + test_days, len(dates) + 1, step):
        oos_start_idx = oos_end_idx - test_days
        if anchored:
            is_start_idx = 0
        else:
            is_start_idx = oos_start_idx - train_days
        if is_start_idx < 0:
            break
        windows.append((is_start_idx, oos_start_idx, oos_end_idx))
    return windows
```

#### 3.2.2 目标函数

```python
def _evaluate(result: SimulationResult, objective: str) -> float:
    """根据目标函数计算得分。"""
    if objective == "calmar":
        return result.metrics.calmar_ratio if result.metrics else 0.0
    elif objective == "sharpe":
        return result.metrics.sharpe_ratio if result.metrics else 0.0
    elif objective == "sortino":
        return result.metrics.sortino_ratio if result.metrics else 0.0
    elif objective == "total_return":
        return result.metrics.total_return if result.metrics else 0.0
    else:
        return 0.0
```

#### 3.2.3 参数组合运行

```python
def _run_with_params(
    ts_codes: list[str] | None,
    dates: list[str],
    is_start_idx: int,
    is_end_idx: int,
    params: dict[str, Any],
    base_config: SimulationConfig,
    datasource: DataSource,
) -> SimulationResult:
    """用指定参数在指定日期范围内运行回测。"""
    config = SimulationConfig(**{**base_config.__dict__, **params})
    # 截取日期范围
    start_date = dates[is_start_idx]
    end_date = dates[is_end_idx - 1]
    return run_simulation(
        ts_codes=ts_codes,
        days=is_end_idx - is_start_idx,
        config=config,
        datasource=datasource,
    )
```

### 3.3 报告输出层：`optimizer_report.py`（新增）

输出 walk-forward 报告（文本/JSON）。

```python
def summary_text(result: WalkForwardResult) -> str:
    """格式化 walk-forward 结果为可读文本。"""
    lines = [
        f"{'=' * 60}",
        "Walk-forward 参数寻优结果",
        f"{'=' * 60}",
        f"窗口数:       {len(result.windows)}",
        f"训练天数:     {result.config.train_days}",
        f"验证天数:     {result.config.test_days}",
        f"目标函数:     {result.config.objective}",
        f"过拟合比率:   {result.overfit_ratio:.2f} (接近 1 表示不过拟合)",
        f"{'=' * 60}",
        "",
        "OOS 统计指标:",
        f"  年化收益:   {result.oos_metrics.annualized_return:+.2%}",
        f"  夏普比率:   {result.oos_metrics.sharpe_ratio:.2f}",
        f"  Calmar:     {result.oos_metrics.calmar_ratio:.2f}",
        f"  最大回撤:   {result.oos_metrics.max_drawdown:.2%}",
        f"  胜率:       {result.oos_metrics.win_rate:.1%}",
        "",
        "各窗口最佳参数:",
    ]
    for w in result.windows:
        lines.append(f"  窗口 {w.window_index}: IS={w.is_score:.2f}, OOS={w.oos_score:.2f}")
        for k, v in w.best_params.items():
            lines.append(f"    {k} = {v}")
    lines.append(f"{'=' * 60}")
    return "\n".join(lines)
```

### 3.4 配置扩展

```python
@dataclass
class SimulationConfig:
    # v0.3 字段保留...

    # v0.4 新增
    walk_forward: bool = False
    wf_config: WalkForwardConfig | None = None
```

### 3.5 CLI 扩展

```bash
zt simulate 000001.SZ \
    --days 500 \
    --walk-forward \
    --wf-train-days 120 \
    --wf-test-days 60 \
    --wf-objective calmar \
    --param-min-resonance-score "0.15:0.55:0.1" \
    --param-risk-per-trade "0.01:0.03:0.01" \
    --strategy-mode resonance \
    --json
```

CLI 参数解析：

- `--walk-forward`：启用 walk-forward 模式
- `--wf-train-days N`：训练窗口天数（默认 120）
- `--wf-test-days N`：验证窗口天数（默认 60）
- `--wf-objective {calmar,sharpe,sortino,total_return}`：目标函数（默认 calmar）
- `--param-* "low:high:step"`：覆盖默认参数范围

---

## 4. 数据流

```text
run_walk_forward(ts_codes, total_days, wf_config, base_config)
  ├─ 获取总日期序列 dates
  ├─ windows = _split_windows(dates, train_days, test_days, anchored)
  ├─ param_grid = generate_grid(wf_config.param_space)
  ├─ for each window:
  │    ├─ best_params = None, best_score = -inf
  │    ├─ for each param_combo in param_grid:
  │    │    ├─ result = _run_with_params(..., is_start, is_end, param_combo)
  │    │    ├─ score = _evaluate(result, objective)
  │    │    └─ if score > best_score: best_score = score, best_params = param_combo
  │    ├─ oos_result = _run_with_params(..., oos_start, oos_end, best_params)
  │    └─ record WalkForwardWindow
  ├─ 拼接所有 oos_result.equity_curve → oos_equity_curve
  ├─ 计算 oos_metrics = calculate_metrics(oos_equity_curve, ...)
  ├─ 计算 overfit_ratio = mean(IS scores) / mean(OOS scores)
  └─ 返回 WalkForwardResult
```

---

## 5. 测试策略

### 5.1 新增测试文件

- `tests/test_simulator_param_space.py`
  - 参数空间解析、网格生成、边界值
- `tests/test_simulator_walk_forward.py`
  - 窗口切分（rolling/anchored）、参数搜索、结果拼接、目标函数
- `tests/test_simulator_optimizer_report.py`
  - 报告格式化、JSON 输出
- `tests/test_simulator.py`（扩展）
  - `--walk-forward` CLI 参数能跑通并输出 `walk_forward` 字段

### 5.2 关键边界用例

1. 训练窗口不足时返回空结果。
2. 参数网格为空时使用默认参数。
3. 所有窗口 OOS 收益为负时，overfit_ratio 计算不报错。
4. anchored 模式下训练窗口从起点固定增长。
5. rolling 模式下训练窗口固定长度滑动。

### 5.3 回归目标

- 全量测试：`900+ passed / 11 skipped`
- ruff / mypy 零错误
- `zt simulate --walk-forward --json` 输出包含 `walk_forward` 字段
- `zt simulate` 默认行为与 v0.3 一致

---

## 6. 风险与回退方案

| 风险 | 影响 | 回退方案 |
|---|---|---|
| 参数网格过大导致计算时间过长 | 回测变慢 | 默认参数空间较小（4 维 × 3-5 值 = 81-500 组合）；用户可自定义范围 |
| `run_simulation` 不支持显式日期范围 | 窗口切分失效 | 在 Task 1 中扩展 `run_simulation` 支持 `start_date`/`end_date` 参数 |
| 过拟合比率计算异常 | 报告不可靠 | 使用 `mean(IS) / max(mean(OOS), 1e-6)` 避免除零 |
| 目标函数与 `PerformanceMetrics` 不匹配 | 评分错误 | 在 `_evaluate` 中做防御性检查，缺失 metrics 时返回 0.0 |

---

## 7. 版本与文档

- 版本号：zettaranc-skill **v3.6.0**
- `docs/CHANGELOG.md`：新增 v3.6.0 条目
- `docs/TODO.md`：更新 simulator v0.4 进度
- `README.md`：更新 `zt simulate --walk-forward` 示例
- `pyproject.toml`：同步版本号

---

## 8. 验收标准

- [ ] 新增 3 个测试文件，合计不少于 30 个新用例。
- [ ] 全量测试通过：`900+ passed / 11 skipped`。
- [ ] ruff / mypy 零错误。
- [ ] `zt simulate --walk-forward --json` 输出包含 `walk_forward` 字段，含 `windows`、`oos_equity_curve`、`oos_metrics`、`overfit_ratio`。
- [ ] `zt simulate` 默认行为与 v0.3 输出一致。
- [ ] 文档（README/CHANGELOG/TODO）同步更新至 v3.6.0。

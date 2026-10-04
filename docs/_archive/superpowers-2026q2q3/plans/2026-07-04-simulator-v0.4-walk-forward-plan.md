# 少女/少妇模拟器 v0.4 Walk-forward 参数寻优实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为模拟器引入滚动样本内训练 + 样本外验证的自动化参数寻优机制，避免过拟合。

**Architecture:** 新增三个模块：`param_space.py`（参数空间定义与网格生成）、`walk_forward.py`（滚动窗口切分与参数搜索）、`optimizer_report.py`（报告输出）。扩展现有 `run_simulation` 支持显式日期范围，扩展 `SimulationConfig` 支持 walk-forward 配置，扩展 CLI 支持 `--walk-forward` 参数。

**Tech Stack:** Python 3.10+, pytest, ruff, mypy, dataclasses, standard library

## Global Constraints

- Python 3.10+, 使用 `from __future__ import annotations` 和 `|` union 语法
- 优先使用标准库，不引入新的第三方依赖
- 所有模块文件头包含 `#!/usr/bin/env python3`，中文 docstring 与注释
- 代码风格：ruff line-length 120，mypy ignore_missing_imports，中文注释
- 每个新增功能必须有对应单元测试，TDD 顺序执行
- 保持向后兼容：新增 CLI 参数默认关闭，原有 `zt simulate` 行为不变
- 反未来函数：每个窗口只使用 IS 数据选参数，OOS 数据完全不参与参数选择
- 版本目标：zettaranc-skill v3.6.0

---

## Task 1: 扩展 `run_simulation` 支持显式日期范围

**Files:**
- Modify: `modules/simulator/simulator.py:62-65, 219-271`
- Test: `tests/test_simulator.py`（新增日期范围测试）

**Interfaces:**
- Modifies: `run_simulation(ts_codes, days, config, datasource)` → `run_simulation(ts_codes, days, config, datasource, start_date=None, end_date=None)`
- Produces: 当 `start_date` 和 `end_date` 都提供时，只在该日期范围内运行回测

- [ ] **Step 1: 写失败测试**

```python
def test_run_simulation_with_explicit_date_range():
    """测试显式日期范围参数"""
    from modules.simulator.simulator import run_simulation
    from modules.simulator import SimulationConfig
    from modules.datasource import get_datasource
    
    ds = get_datasource()
    config = SimulationConfig(initial_capital=1_000_000)
    
    # 使用显式日期范围
    result = run_simulation(
        ts_codes=["000001.SZ"],
        days=60,
        config=config,
        datasource=ds,
        start_date="20240101",
        end_date="20240301",
    )
    
    # 验证结果不为空
    assert result is not None
    assert len(result.equity_curve) > 0
    
    # 验证日期范围在指定范围内
    dates = [point["date"] for point in result.equity_curve]
    assert all("20240101" <= d <= "20240301" for d in dates)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator.py::test_run_simulation_with_explicit_date_range -v
```
Expected: FAIL - `run_simulation() got an unexpected keyword argument 'start_date'`

- [ ] **Step 3: 最小实现**

修改 `modules/simulator/simulator.py`：

```python
def run_simulation(
    ts_codes: list[str] | None,
    days: int,
    config: SimulationConfig,
    datasource: DataSource | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> SimulationResult:
    """
    运行回测。

    Args:
        ts_codes: 股票池，None 则使用默认池
        days: 回测天数（当 start_date/end_date 未提供时使用）
        config: 模拟配置
        datasource: 数据源
        start_date: 起始日期 YYYYMMDD（可选）
        end_date: 结束日期 YYYYMMDD（可选）

    Returns:
        SimulationResult
    """
    ds = datasource or get_datasource()
    
    # 获取日期序列
    if start_date and end_date:
        # 使用显式日期范围
        first_code = ts_codes[0] if ts_codes else "000001.SZ"
        all_dates = _available_dates(first_code, days=500, datasource=ds)
        dates = [d for d in all_dates if start_date <= d <= end_date]
    else:
        # 使用原有逻辑
        first_code = ts_codes[0] if ts_codes else "000001.SZ"
        dates = _available_dates(first_code, days, datasource=ds)
    
    if not dates:
        return SimulationResult(config=config, initial_capital=config.initial_capital)
    
    # ... 后续代码保持不变
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator.py::test_run_simulation_with_explicit_date_range -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/simulator.py tests/test_simulator.py
git commit -m "feat(simulator): support explicit date range in run_simulation"
```

---

## Task 2: 创建参数空间模块 `param_space.py`

**Files:**
- Create: `modules/simulator/param_space.py`
- Test: `tests/test_simulator_param_space.py`

**Interfaces:**
- Produces: `ParamDimension` dataclass, `generate_grid(dimensions) -> list[dict]`, `DEFAULT_PARAM_SPACE`

- [ ] **Step 1: 写失败测试**

```python
def test_param_dimension_creation():
    """测试参数维度创建"""
    from modules.simulator.param_space import ParamDimension
    
    dim = ParamDimension(
        name="risk_per_trade",
        param_type="float",
        low=0.01,
        high=0.03,
        step=0.01,
    )
    
    assert dim.name == "risk_per_trade"
    assert dim.param_type == "float"
    assert dim.low == 0.01
    assert dim.high == 0.03
    assert dim.step == 0.01


def test_generate_grid_single_dimension():
    """测试单维度网格生成"""
    from modules.simulator.param_space import ParamDimension, generate_grid
    
    dim = ParamDimension("risk", "float", 0.01, 0.03, 0.01)
    grid = generate_grid([dim])
    
    assert len(grid) == 3
    assert grid[0] == {"risk": 0.01}
    assert grid[1] == {"risk": 0.02}
    assert grid[2] == {"risk": 0.03}


def test_generate_grid_multiple_dimensions():
    """测试多维度网格生成（笛卡尔积）"""
    from modules.simulator.param_space import ParamDimension, generate_grid
    
    dim1 = ParamDimension("a", "float", 1.0, 2.0, 1.0)
    dim2 = ParamDimension("b", "int", 10, 20, 10)
    
    grid = generate_grid([dim1, dim2])
    
    assert len(grid) == 4  # 2 × 2
    assert {"a": 1.0, "b": 10} in grid
    assert {"a": 1.0, "b": 20} in grid
    assert {"a": 2.0, "b": 10} in grid
    assert {"a": 2.0, "b": 20} in grid


def test_generate_grid_with_choices():
    """测试使用 choices 的网格生成"""
    from modules.simulator.param_space import ParamDimension, generate_grid
    
    dim = ParamDimension("mode", "choice", choices=["simple", "resonance"])
    grid = generate_grid([dim])
    
    assert len(grid) == 2
    assert {"mode": "simple"} in grid
    assert {"mode": "resonance"} in grid
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator_param_space.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
参数空间定义与网格生成。

为 walk-forward 参数寻优提供参数维度定义和网格生成功能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import itertools


@dataclass
class ParamDimension:
    """参数维度定义"""

    name: str                # SimulationConfig 字段名
    param_type: str          # "float" | "int" | "choice"
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: list[Any] = field(default_factory=list)

    def generate_values(self) -> list[Any]:
        """生成该维度的所有可能值"""
        if self.param_type == "choice":
            return self.choices.copy()
        
        if self.low is None or self.high is None or self.step is None:
            raise ValueError(f"维度 {self.name} 缺少 low/high/step")
        
        values = []
        current = self.low
        while current <= self.high + 1e-9:  # 浮点精度容差
            if self.param_type == "int":
                values.append(int(round(current)))
            else:
                values.append(round(current, 10))  # 避免浮点误差
            current += self.step
        
        return values


def generate_grid(dimensions: list[ParamDimension]) -> list[dict[str, Any]]:
    """
    生成参数网格（笛卡尔积）。

    Args:
        dimensions: 参数维度列表

    Returns:
        所有参数组合的列表
    """
    if not dimensions:
        return [{}]
    
    # 生成每个维度的值列表
    value_lists = [dim.generate_values() for dim in dimensions]
    
    # 计算笛卡尔积
    grid = []
    for combo in itertools.product(*value_lists):
        params = {dim.name: value for dim, value in zip(dimensions, combo)}
        grid.append(params)
    
    return grid


# 默认参数空间
DEFAULT_PARAM_SPACE: list[ParamDimension] = [
    ParamDimension("min_resonance_score", "float", 0.15, 0.55, 0.10),
    ParamDimension("risk_per_trade", "float", 0.01, 0.03, 0.01),
    ParamDimension("position_score_threshold", "float", 60.0, 80.0, 10.0),
    ParamDimension("max_position_pct", "float", 0.10, 0.30, 0.10),
]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator_param_space.py -v
```
Expected: 4 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/param_space.py tests/test_simulator_param_space.py
git commit -m "feat(simulator): add param_space module for walk-forward optimization"
```

---

## Task 3: 创建 Walk-forward 执行模块 `walk_forward.py`

**Files:**
- Create: `modules/simulator/walk_forward.py`
- Test: `tests/test_simulator_walk_forward.py`

**Interfaces:**
- Consumes: `ParamDimension`, `generate_grid`, `SimulationConfig`, `SimulationResult`, `run_simulation`
- Produces: `WalkForwardConfig`, `WalkForwardWindow`, `WalkForwardResult`, `run_walk_forward()`

- [ ] **Step 1: 写失败测试**

```python
def test_walk_forward_config_defaults():
    """测试 WalkForwardConfig 默认值"""
    from modules.simulator.walk_forward import WalkForwardConfig
    
    config = WalkForwardConfig()
    
    assert config.train_days == 120
    assert config.test_days == 60
    assert config.objective == "calmar"
    assert config.anchored is False


def test_split_windows_rolling():
    """测试滚动窗口切分"""
    from modules.simulator.walk_forward import _split_windows
    
    dates = [f"2024010{i}" for i in range(1, 10)]  # 9 天
    windows = _split_windows(dates, train_days=3, test_days=2, anchored=False)
    
    # 应该有多个窗口
    assert len(windows) > 0
    
    # 第一个窗口：IS=[0:3], OOS=[3:5]
    is_start, oos_start, oos_end = windows[0]
    assert is_start == 0
    assert oos_start == 3
    assert oos_end == 5


def test_split_windows_anchored():
    """测试锚定窗口切分"""
    from modules.simulator.walk_forward import _split_windows
    
    dates = [f"2024010{i}" for i in range(1, 10)]  # 9 天
    windows = _split_windows(dates, train_days=3, test_days=2, anchored=True)
    
    # 所有窗口的 is_start 都应该是 0
    for is_start, oos_start, oos_end in windows:
        assert is_start == 0


def test_evaluate_calmar():
    """测试 Calmar 目标函数"""
    from modules.simulator.walk_forward import _evaluate
    from modules.simulator import SimulationResult, SimulationConfig
    from modules.simulator.metrics import PerformanceMetrics
    
    config = SimulationConfig()
    metrics = PerformanceMetrics(
        calmar_ratio=2.5,
        sharpe_ratio=1.0,
        sortino_ratio=1.5,
        total_return=0.20,
    )
    result = SimulationResult(config=config, metrics=metrics)
    
    score = _evaluate(result, "calmar")
    assert score == 2.5


def test_run_walk_forward_basic():
    """测试基本的 walk-forward 执行"""
    from modules.simulator.walk_forward import run_walk_forward, WalkForwardConfig
    from modules.simulator import SimulationConfig
    from modules.datasource import get_datasource
    
    ds = get_datasource()
    base_config = SimulationConfig(initial_capital=1_000_000)
    wf_config = WalkForwardConfig(
        train_days=60,
        test_days=30,
        objective="calmar",
    )
    
    result = run_walk_forward(
        ts_codes=["000001.SZ"],
        total_days=180,
        wf_config=wf_config,
        base_config=base_config,
        datasource=ds,
    )
    
    # 验证结果结构
    assert result is not None
    assert len(result.windows) > 0
    assert result.oos_metrics is not None
    assert result.overfit_ratio > 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator_walk_forward.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
Walk-forward 参数寻优执行层。

实现滚动窗口切分、参数搜索、OOS 拼接。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import statistics

from . import SimulationConfig, SimulationResult
from .param_space import ParamDimension, generate_grid, DEFAULT_PARAM_SPACE
from .simulator import run_simulation
from .metrics import PerformanceMetrics
from ..datasource import DataSource, get_datasource


@dataclass
class WalkForwardConfig:
    """Walk-forward 配置"""

    train_days: int = 120
    test_days: int = 60
    objective: str = "calmar"  # "calmar" | "sharpe" | "sortino" | "total_return"
    param_space: list[ParamDimension] = field(default_factory=lambda: DEFAULT_PARAM_SPACE.copy())
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


def _split_windows(
    dates: list[str],
    train_days: int,
    test_days: int,
    anchored: bool,
) -> list[tuple[int, int, int]]:
    """
    切分窗口。

    Returns:
        [(is_start_idx, oos_start_idx, oos_end_idx), ...]
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


def _evaluate(result: SimulationResult, objective: str) -> float:
    """根据目标函数计算得分。"""
    if not result.metrics:
        return 0.0
    
    if objective == "calmar":
        return result.metrics.calmar_ratio
    elif objective == "sharpe":
        return result.metrics.sharpe_ratio
    elif objective == "sortino":
        return result.metrics.sortino_ratio
    elif objective == "total_return":
        return result.metrics.total_return
    else:
        return 0.0


def _run_with_params(
    ts_codes: list[str] | None,
    dates: list[str],
    start_idx: int,
    end_idx: int,
    params: dict[str, Any],
    base_config: SimulationConfig,
    datasource: DataSource,
) -> SimulationResult:
    """用指定参数在指定日期范围内运行回测。"""
    # 合并参数
    config_dict = base_config.__dict__.copy()
    config_dict.update(params)
    config = SimulationConfig(**config_dict)
    
    # 截取日期范围
    start_date = dates[start_idx]
    end_date = dates[end_idx - 1]
    
    return run_simulation(
        ts_codes=ts_codes,
        days=end_idx - start_idx,
        config=config,
        datasource=datasource,
        start_date=start_date,
        end_date=end_date,
    )


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
    ds = datasource or get_datasource()
    
    # 获取总日期序列
    first_code = ts_codes[0] if ts_codes else "000001.SZ"
    from .simulator import _available_dates
    dates = _available_dates(first_code, days=total_days, datasource=ds)
    
    if len(dates) < wf_config.train_days + wf_config.test_days:
        # 数据不足，返回空结果
        return WalkForwardResult(
            config=wf_config,
            windows=[],
            oos_equity_curve=[],
            oos_metrics=PerformanceMetrics(),
            overfit_ratio=1.0,
        )
    
    # 切分窗口
    windows_spec = _split_windows(dates, wf_config.train_days, wf_config.test_days, wf_config.anchored)
    
    # 生成参数网格
    param_grid = generate_grid(wf_config.param_space)
    
    # 执行每个窗口
    windows: list[WalkForwardWindow] = []
    all_oos_curves: list[dict[str, Any]] = []
    is_scores: list[float] = []
    oos_scores: list[float] = []
    
    for window_idx, (is_start_idx, oos_start_idx, oos_end_idx) in enumerate(windows_spec):
        # 在 IS 上搜索最佳参数
        best_params = None
        best_score = float("-inf")
        
        for params in param_grid:
            result = _run_with_params(
                ts_codes, dates, is_start_idx, oos_start_idx,
                params, base_config, ds
            )
            score = _evaluate(result, wf_config.objective)
            
            if score > best_score:
                best_score = score
                best_params = params
        
        # 用最佳参数在 OOS 上验证
        oos_result = _run_with_params(
            ts_codes, dates, oos_start_idx, oos_end_idx,
            best_params or {}, base_config, ds
        )
        oos_score = _evaluate(oos_result, wf_config.objective)
        
        # 记录窗口结果
        is_result = _run_with_params(
            ts_codes, dates, is_start_idx, oos_start_idx,
            best_params or {}, base_config, ds
        )
        
        windows.append(WalkForwardWindow(
            window_index=window_idx,
            is_start=dates[is_start_idx],
            is_end=dates[oos_start_idx - 1],
            oos_start=dates[oos_start_idx],
            oos_end=dates[oos_end_idx - 1],
            best_params=best_params or {},
            is_score=best_score,
            oos_score=oos_score,
            is_result=is_result,
            oos_result=oos_result,
        ))
        
        # 拼接 OOS 资金曲线
        all_oos_curves.extend(oos_result.equity_curve)
        is_scores.append(best_score)
        oos_scores.append(oos_score)
    
    # 计算 OOS 统计指标
    from .metrics import calculate_metrics
    oos_metrics = calculate_metrics(all_oos_curves, [], [])
    
    # 计算过拟合比率
    mean_is = statistics.mean(is_scores) if is_scores else 0.0
    mean_oos = statistics.mean(oos_scores) if oos_scores else 0.0
    overfit_ratio = mean_is / max(mean_oos, 1e-6)
    
    return WalkForwardResult(
        config=wf_config,
        windows=windows,
        oos_equity_curve=all_oos_curves,
        oos_metrics=oos_metrics,
        overfit_ratio=overfit_ratio,
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator_walk_forward.py -v
```
Expected: 5 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/walk_forward.py tests/test_simulator_walk_forward.py
git commit -m "feat(simulator): add walk_forward module for parameter optimization"
```

---

## Task 4: 创建报告输出模块 `optimizer_report.py`

**Files:**
- Create: `modules/simulator/optimizer_report.py`
- Test: `tests/test_simulator_optimizer_report.py`

**Interfaces:**
- Consumes: `WalkForwardResult`
- Produces: `summary_text(result) -> str`, `to_dict(result) -> dict`

- [ ] **Step 1: 写失败测试**

```python
def test_summary_text_format():
    """测试文本报告格式"""
    from modules.simulator.optimizer_report import summary_text
    from modules.simulator.walk_forward import WalkForwardResult, WalkForwardConfig, WalkForwardWindow
    from modules.simulator import SimulationResult, SimulationConfig
    from modules.simulator.metrics import PerformanceMetrics
    
    config = WalkForwardConfig(train_days=120, test_days=60, objective="calmar")
    metrics = PerformanceMetrics(
        annualized_return=0.25,
        sharpe_ratio=1.5,
        calmar_ratio=2.0,
        max_drawdown=0.15,
        win_rate=0.55,
    )
    
    window = WalkForwardWindow(
        window_index=0,
        is_start="20240101",
        is_end="20240430",
        oos_start="20240501",
        oos_end="20240630",
        best_params={"risk_per_trade": 0.02},
        is_score=2.5,
        oos_score=1.8,
        is_result=SimulationResult(config=SimulationConfig()),
        oos_result=SimulationResult(config=SimulationConfig()),
    )
    
    result = WalkForwardResult(
        config=config,
        windows=[window],
        oos_equity_curve=[],
        oos_metrics=metrics,
        overfit_ratio=1.39,
    )
    
    text = summary_text(result)
    
    assert "Walk-forward 参数寻优结果" in text
    assert "窗口数:       1" in text
    assert "训练天数:     120" in text
    assert "验证天数:     60" in text
    assert "目标函数:     calmar" in text
    assert "过拟合比率:   1.39" in text
    assert "年化收益:   +25.00%" in text
    assert "夏普比率:   1.50" in text
    assert "窗口 0: IS=2.50, OOS=1.80" in text
    assert "risk_per_trade = 0.02" in text


def test_to_dict_structure():
    """测试 JSON 输出结构"""
    from modules.simulator.optimizer_report import to_dict
    from modules.simulator.walk_forward import WalkForwardResult, WalkForwardConfig, WalkForwardWindow
    from modules.simulator import SimulationResult, SimulationConfig
    from modules.simulator.metrics import PerformanceMetrics
    
    config = WalkForwardConfig()
    metrics = PerformanceMetrics()
    
    result = WalkForwardResult(
        config=config,
        windows=[],
        oos_equity_curve=[{"date": "20240101", "equity": 1000000}],
        oos_metrics=metrics,
        overfit_ratio=1.0,
    )
    
    data = to_dict(result)
    
    assert "config" in data
    assert "windows" in data
    assert "oos_equity_curve" in data
    assert "oos_metrics" in data
    assert "overfit_ratio" in data
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator_optimizer_report.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 实现模块**

```python
#!/usr/bin/env python3
"""
Walk-forward 参数寻优报告输出。

提供文本和 JSON 格式的报告生成。
"""

from __future__ import annotations

from typing import Any
from dataclasses import asdict

from .walk_forward import WalkForwardResult


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


def to_dict(result: WalkForwardResult) -> dict[str, Any]:
    """将 WalkForwardResult 转换为可序列化的字典。"""
    return {
        "config": {
            "train_days": result.config.train_days,
            "test_days": result.config.test_days,
            "objective": result.config.objective,
            "anchored": result.config.anchored,
        },
        "windows": [
            {
                "window_index": w.window_index,
                "is_start": w.is_start,
                "is_end": w.is_end,
                "oos_start": w.oos_start,
                "oos_end": w.oos_end,
                "best_params": w.best_params,
                "is_score": w.is_score,
                "oos_score": w.oos_score,
            }
            for w in result.windows
        ],
        "oos_equity_curve": result.oos_equity_curve,
        "oos_metrics": asdict(result.oos_metrics),
        "overfit_ratio": result.overfit_ratio,
    }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator_optimizer_report.py -v
```
Expected: 2 PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/optimizer_report.py tests/test_simulator_optimizer_report.py
git commit -m "feat(simulator): add optimizer_report module for walk-forward output"
```

---

## Task 5: 扩展 `SimulationConfig` 支持 walk-forward 配置

**Files:**
- Modify: `modules/simulator/__init__.py`
- Test: `tests/test_simulator.py`（新增 walk-forward 配置测试）

**Interfaces:**
- Modifies: `SimulationConfig` 新增 `walk_forward: bool = False` 和 `wf_config: WalkForwardConfig | None = None`

- [ ] **Step 1: 写失败测试**

```python
def test_simulation_config_walk_forward_fields():
    """测试 SimulationConfig 的 walk-forward 字段"""
    from modules.simulator import SimulationConfig
    from modules.simulator.walk_forward import WalkForwardConfig
    
    # 默认值
    config = SimulationConfig()
    assert config.walk_forward is False
    assert config.wf_config is None
    
    # 设置 walk-forward 配置
    wf_config = WalkForwardConfig(train_days=120, test_days=60)
    config = SimulationConfig(walk_forward=True, wf_config=wf_config)
    assert config.walk_forward is True
    assert config.wf_config.train_days == 120
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_simulator.py::test_simulation_config_walk_forward_fields -v
```
Expected: FAIL - AttributeError

- [ ] **Step 3: 最小实现**

修改 `modules/simulator/__init__.py`：

```python
from .walk_forward import WalkForwardConfig

@dataclass
class SimulationConfig:
    # ... 现有字段 ...
    
    # v0.4 新增
    walk_forward: bool = False
    wf_config: WalkForwardConfig | None = None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_simulator.py::test_simulation_config_walk_forward_fields -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/simulator/__init__.py tests/test_simulator.py
git commit -m "feat(simulator): extend SimulationConfig with walk-forward fields"
```

---

## Task 6: 扩展 CLI 支持 `--walk-forward` 参数

**Files:**
- Modify: `modules/cli.py:784-794`
- Modify: `modules/cli_commands.py:673-732`
- Test: `tests/test_cli_simulate.py`（新增 walk-forward 参数测试）

**Interfaces:**
- Produces: CLI 新增 `--walk-forward`, `--wf-train-days`, `--wf-test-days`, `--wf-objective`, `--param-*` 参数

- [ ] **Step 1: 写失败测试**

```python
def test_cli_walk_forward_arguments():
    """测试 walk-forward CLI 参数解析"""
    import argparse
    from modules.cli import build_parser
    
    parser = build_parser()
    args = parser.parse_args([
        "simulate", "000001.SZ",
        "--walk-forward",
        "--wf-train-days", "120",
        "--wf-test-days", "60",
        "--wf-objective", "calmar",
    ])
    
    assert args.walk_forward is True
    assert args.wf_train_days == 120
    assert args.wf_test_days == 60
    assert args.wf_objective == "calmar"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_cli_simulate.py::test_cli_walk_forward_arguments -v
```
Expected: FAIL - argparse.ArgumentError

- [ ] **Step 3: 实现 CLI 扩展**

修改 `modules/cli.py`：

```python
# 在 simulate subparser 中添加
p_sim.add_argument("--walk-forward", action="store_true", help="启用 walk-forward 参数寻优")
p_sim.add_argument("--wf-train-days", type=int, default=120, help="训练窗口天数")
p_sim.add_argument("--wf-test-days", type=int, default=60, help="验证窗口天数")
p_sim.add_argument("--wf-objective", choices=["calmar", "sharpe", "sortino", "total_return"], default="calmar", help="目标函数")
```

修改 `modules/cli_commands.py`：

```python
def cmd_simulate(args):
    from .simulator.simulator import run_simulation
    from .simulator.walk_forward import run_walk_forward, WalkForwardConfig
    from .simulator.optimizer_report import summary_text, to_dict
    from .simulator import SimulationConfig
    
    use_json = getattr(args, "json", False)
    days = getattr(args, "days", 250)
    codes_str = getattr(args, "codes", None)
    
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
    
    ts_codes = None
    if codes_str:
        ts_codes = [c.strip() for c in codes_str.split(",") if c.strip()]
    
    # 检查是否启用 walk-forward
    if getattr(args, "walk_forward", False):
        wf_config = WalkForwardConfig(
            train_days=getattr(args, "wf_train_days", 120),
            test_days=getattr(args, "wf_test_days", 60),
            objective=getattr(args, "wf_objective", "calmar"),
        )
        
        result = run_walk_forward(
            ts_codes=ts_codes,
            total_days=days,
            wf_config=wf_config,
            base_config=config,
        )
        
        if use_json:
            _json_output(to_dict(result))
        else:
            print(summary_text(result))
    else:
        # 原有逻辑
        result = run_simulation(ts_codes=ts_codes, days=days, config=config)
        # ... 原有输出逻辑
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_cli_simulate.py::test_cli_walk_forward_arguments -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/cli.py modules/cli_commands.py tests/test_cli_simulate.py
git commit -m "feat(cli): add --walk-forward parameters to zt simulate"
```

---

## Task 7: 更新文档和版本号

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TODO.md`
- Modify: `README.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: 更新 CHANGELOG**

在 `docs/CHANGELOG.md` 顶部新增：

```markdown
## v3.6.0 (2026-07-04)

### 少女/少妇模拟器 v0.4 —— Walk-forward 参数寻优

- 新增 `modules/simulator/param_space.py`：参数空间定义与网格生成。
- 新增 `modules/simulator/walk_forward.py`：滚动窗口切分、参数搜索、OOS 拼接。
- 新增 `modules/simulator/optimizer_report.py`：walk-forward 报告输出（文本/JSON）。
- 扩展 `run_simulation` 支持显式日期范围（`start_date`/`end_date`）。
- 扩展 `SimulationConfig` 支持 `walk_forward` 模式和 `wf_config` 配置。
- CLI `zt simulate` 新增 `--walk-forward/--wf-train-days/--wf-test-days/--wf-objective` 参数。
```

- [ ] **Step 2: 更新 TODO**

在 `docs/TODO.md` 中新增：

```markdown
## ✅ 已完成（v3.6.0 少女/少妇模拟器 v0.4）

- [x] Walk-forward 参数寻优：滚动样本内训练 + 样本外验证
- [x] 参数空间定义与网格生成
- [x] 多目标函数支持（Calmar/Sharpe/Sortino/Total Return）
- [x] 过拟合检查（IS vs OOS 比率）
- [x] CLI 集成与报告输出
```

- [ ] **Step 3: 更新 README**

在 `README.md` 的 `zt simulate` 示例后新增：

```markdown
# Walk-forward 参数寻优
zt simulate 000001.SZ --days 500 --walk-forward --wf-train-days 120 --wf-test-days 60 --wf-objective calmar --json
```

- [ ] **Step 4: 更新版本号**

修改 `pyproject.toml`：

```toml
version = "3.6.0"
```

- [ ] **Step 5: 提交**

```bash
git add docs/CHANGELOG.md docs/TODO.md README.md pyproject.toml
git commit -m "docs: bump version to v3.6.0 for simulator v0.4"
```

---

## Task 8: 全量验证与推送

- [ ] **Step 1: 运行全量测试**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: `900+ passed / 11 skipped`

- [ ] **Step 2: 运行 lint 和类型检查**

```bash
.venv/bin/ruff check modules/simulator tests/test_simulator_*.py
.venv/bin/ruff format modules/simulator tests/test_simulator_*.py --check
.venv/bin/mypy modules/simulator
```
Expected: 全部通过

- [ ] **Step 3: 冒烟测试**

```bash
.venv/bin/python -m modules.cli simulate 000001.SZ --days 180 --walk-forward --wf-train-days 60 --wf-test-days 30 --json | head -c 2000
```
Expected: 输出包含 `walk_forward` 字段，含 `windows`、`oos_equity_curve`、`oos_metrics`、`overfit_ratio`

- [ ] **Step 4: 提交并推送**

```bash
git push origin main
```
Expected: GitHub Actions 全绿

---

## Self-Review Checklist

- **Spec coverage:**
  - [x] 参数空间定义 → Task 2
  - [x] Walk-forward 执行 → Task 3
  - [x] 报告输出 → Task 4
  - [x] 配置扩展 → Task 5
  - [x] CLI 扩展 → Task 6
  - [x] 文档更新 → Task 7
  - [x] 验证推送 → Task 8
- **Placeholder scan:** 无 TBD/TODO/"implement later"
- **Type consistency:** 
  - `run_simulation` 签名在 Task 1 中扩展，Task 3 中调用
  - `SimulationConfig` 在 Task 5 中扩展，Task 6 中使用
  - `WalkForwardConfig`/`WalkForwardResult` 在 Task 3 中定义，Task 4/6 中使用

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-simulator-v0.4-walk-forward-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - 每个 Task 派一个 fresh subagent，我在每轮 review 后继续。
2. **Inline Execution** - 在当前会话中按 Task 顺序直接实现，关键 checkpoint 停下来 review。

Which approach?

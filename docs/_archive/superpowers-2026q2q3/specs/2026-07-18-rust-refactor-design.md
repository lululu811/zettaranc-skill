# zettaranc-skill Rust 重构设计

> **状态**：Draft v1 · 待用户复核
> **创建日期**：2026-07-18
> **作者**：Claude (brainstorming with chenlei)
> **目标分支**：`feature/rust-core-compute`（从 `main` 拉出）
> **预计工作量**：M0–M6 共 6 个里程碑，预计 6–10 周

---

## 1. 背景与目标

### 1.1 现状

zettaranc-skill 是一个 A 股量化交易/选股项目，Python 3.10+ 单仓实现，包含 79 个测试文件。

**核心模块（计算密集，性能瓶颈）**：

| 模块 | 性能现状 | 痛点 |
|---|---|---|
| `modules/backtest/portfolio.py` | 100 只 × 1000 天 ~30s | 双层循环，无并行 |
| `modules/simulator/simulator.py` | 单次回测分钟级 | 逐日撮合 + 多种子扫描 |
| `modules/verify/walk_forward.py` | 50 参数 × 5 窗口 ~30 min | 二维笛卡尔积串行 |
| `modules/screener/engine.py` | 5000 只 × 14 条件 ~2 min | `ProcessPoolExecutor` + pickle 开销 |
| `modules/core/atr.py` 等指标 | 全市场计算 ~5 min | 行存 + Python 对象开销 |
| `scripts/optimize_for_v10_verify.py` | 单次 ~45 min | 串行网格搜索 |

**已识别的高 ROI 改造点**（用户确认）：
- 回测/模拟撮合
- 参数网格搜索
- 选股/筛选
- 指标批量计算

### 1.2 重构目标

1. **性能**：核心计算链路提速 5–50×（网格搜索场景预期从 30 min → 1 min）
2. **零侵入**：保留 79 个 Python 测试用例**零修改通过**，CLI 不变，CLI 子命令不变
3. **可回滚**：环境变量秒级切换 Rust / Python 实现
4. **范围聚焦**：只重写计算密集域；CLI、LLM、self_optimizer、数据源客户端、SQLite 读写保持 Python

### 1.3 非目标（YAGNI）

- ❌ 重写 CLI
- ❌ 重写数据源客户端（Tushare / Indevs / Bridge）
- ❌ 重写 SQLite 读写层
- ❌ 重写 LLM 集成 / self_optimizer
- ❌ 引入 tokio / async（CPU bound 用 rayon 足够）
- ❌ 分布式部署（单机 rayon 满了再说）

---

## 2. 架构总览

### 2.1 核心思想

**Rust 内核 + Python 业务胶水（PyO3 混合架构）**：

```
┌─────────────────────────────────────────────────────────┐
│                    Python 业务层（不变）                   │
│  CLI · LLM 编排 · self_optimizer · 数据源客户端 · SQLite  │
│                          │                              │
│                          ▼                              │
│            ┌──────────────────────────┐                 │
│            │  compat shim（环境变量切换）│                 │
│            └──────────────────────────┘                 │
│                          │                              │
│                          ▼                              │
│              ┌─────────────────────┐                    │
│              │   _core_compute.so  │  ← PyO3 绑定        │
│              │   (Rust workspace)  │                    │
│              └─────────────────────┘                    │
│                          │                              │
│            ┌─────────────┼─────────────┐                │
│            ▼             ▼             ▼                │
│       indicators   backtest_engine  grid_search         │
│                            + screener                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 工作区结构

在项目根新建 `rust/` 目录作为 Rust workspace，Python 侧用 maturin 引入编译产物。

```
zettaranc-skill/
├── pyproject.toml                 # 增加 maturin 依赖 + _core_compute 包入口
├── modules/                       # Python 业务层（CLI/LLM/数据源编排保留）
│   ├── backtest/                  # 业务编排保留，调 Rust
│   ├── simulator/                 # 业务编排保留，调 Rust
│   ├── verify/                    # 业务编排保留，调 Rust
│   ├── screener/                  # 业务编排保留，调 Rust
│   ├── core/                      # 部分指标迁 Rust，paths/errors 留 Python
│   ├── strategies/                # 留 Python（轻量）
│   ├── self_optimizer/            # 留 Python（重度依赖 LLM）
│   └── ...
├── rust/                          # 新增，Rust workspace
│   ├── Cargo.toml                 # workspace 根
│   ├── crates/
│   │   ├── core_types/            # DailyData、KLine、Trade + Arrow schema
│   │   ├── indicators/            # ATR、均线、KDJ/MACD/BBI/RSI、主力阶段
│   │   ├── backtest_engine/       # PortfolioBacktestEngine + simulator 撮合
│   │   ├── grid_search/           # Walk-forward + 参数网格（rayon）
│   │   ├── screener/              # 选股评分引擎
│   │   └── bindings/              # PyO3 绑定 → _core_compute.so
│   └── tests/                     # Rust 单元测试 + golden file
├── data/                          # SQLite 不动
└── tests/                         # Python 测试保留，作为 oracle
```

**Rust crate 间依赖关系**（避免循环依赖）：

```
core_types ← indicators ← backtest_engine ← grid_search
                         ← screener
所有 crate → bindings (PyO3)
```

### 2.3 Python 侧 import 变化

```python
# 旧
from modules.backtest.portfolio import PortfolioBacktestEngine

# 新（仅文件内引用，CLI 不变）
from _core_compute import PortfolioBacktestEngine  # Rust 实现
```

---

## 3. 跨语言数据通道

### 3.1 方案选型

| 方案 | 数据格式 | 零拷贝 | 现状契合度 | 决策 |
|---|---|---|---|---|
| **A. Polars 全链路** | Apache Arrow 列存 | ✅ | ⭐⭐⭐⭐⭐ | **采用** |
| B. Arrow 原生 | RecordBatch | ✅ | ⭐⭐⭐⭐ | 备选 |
| C. NumPy 通道 | ndarray | ✅（部分） | ⭐⭐⭐ | 否决 |
| D. 自定义 FFI struct | packed C struct | ❌ | ⭐⭐ | 否决 |

**采用 Polars 全链路的理由**：
1. Polars 是 Rust 数据栈事实标准，query engine、expression DSL、SIMD、向量化全有
2. `pyo3-polars` 直接把 `polars::DataFrame` 暴露成 Python `polars.DataFrame`，**零拷贝**
3. pandas ↔ polars 互转共享 Arrow buffer，几乎零开销
4. polars expression 极适合 screener / grid search
5. 依赖成本可控（~30MB）

### 3.2 双层 API 设计

**关键决策**：在 PyO3 边界暴露**两层 API**，让 Python 业务层自己选择。

**高层 API**（默认）：保持现有 Python 类型，零侵入。

```rust
#[pyfunction]
fn compute_atr(klines: Vec<DailyData>, window: usize) -> Vec<f64> { ... }

#[pyclass]
struct PortfolioBacktestEngine { ... }
#[pymethods]
impl PortfolioBacktestEngine {
    fn run(&self, klines_dict: HashMap<String, Vec<DailyData>>, days: usize)
        -> PortfolioBacktestResult { ... }
}
```

**低层 API**（热路径）：直接传 `polars.DataFrame`，零拷贝。

```rust
#[pyfunction]
fn compute_atr_polars(df: PyDataFrame, window: usize) -> PyDataFrame { ... }

#[pyfunction]
fn run_portfolio_backtest_polars(
    klines_by_code: PyDataFrame,
    config: PortfolioConfig,
) -> PyDataFrame { ... }
```

**Python 侧调用模式**：

```python
# 普通调用：保留现有类型，迁移成本为零
from _core_compute import compute_atr
atr = compute_atr(klines, window=14)

# 热路径调用：直接传 polars.DataFrame
import polars as pl
from _core_compute import run_portfolio_backtest_polars
df = pl.from_dicts(klines_dict)
result = run_portfolio_backtest_polars(df, config)
```

**首次启动策略**：
- 默认只暴露高层 API
- 给 walk-forward 网格搜索和 screener 写**新的 polars 路径**
- benchmark 显示 ≥3× 加速比才合并到默认路径

### 3.3 Arrow Schema（一次性定义，Rust/Python 共享）

```rust
// core_types/src/schema.rs
pub fn kline_schema() -> SchemaRef {
    Arc::new(Schema::from_iter(vec![
        Field::new("ts_code", DataType::String),
        Field::new("trade_date", DataType::Date32),
        Field::new("open", DataType::Float64),
        Field::new("high", DataType::Float64),
        Field::new("low", DataType::Float64),
        Field::new("close", DataType::Float64),
        Field::new("vol", DataType::Float64),
        Field::new("amount", DataType::Float64),
        Field::new("pct_chg", DataType::Float64),
        Field::new("vol_ratio", DataType::Float64),
        Field::new("is_limit_up", DataType::Boolean),
        Field::new("is_limit_down", DataType::Boolean),
    ]))
}
```

---

## 4. 错误处理

### 4.1 Rust 侧：`thiserror` + 统一枚举

```rust
// core_types/src/error.rs
use thiserror::Error;

#[derive(Error, Debug)]
pub enum CoreError {
    #[error("invalid K-line data: {0}")]
    InvalidKLine(String),

    #[error("missing required column: {0}")]
    MissingColumn(String),

    #[error("insufficient data: need {need} rows, got {got}")]
    InsufficientData { need: usize, got: usize },

    #[error("date range empty: {start} -> {end}")]
    EmptyDateRange { start: String, end: String },

    #[error("parameter out of range: {field}={value}, expected {constraint}")]
    InvalidParameter { field: String, value: f64, constraint: String },

    #[error("walk-forward split invalid: {0}")]
    InvalidWalkForward(String),

    #[error("database: {0}")]
    Database(String),  // 暂时透传，等 Rust 接管 DB 再细化

    #[error(transparent)]
    Polars(#[from] polars::error::PolarsError),

    #[error(transparent)]
    Arrow(#[from] arrow::error::ArrowError),
}
```

### 4.2 PyO3 映射规则

| Rust 错误 | Python 异常类型 |
|---|---|
| `InvalidKLine` / `InsufficientData` / `EmptyDateRange` / `InvalidParameter` / `InvalidWalkForward` | `ValueError` |
| `MissingColumn` | `KeyError` |
| `Database` / `Polars` / `Arrow` | `RuntimeError` |

**原则**：
- 业务可恢复错误 → `ValueError` / `KeyError`
- 基础设施错误 → `RuntimeError`
- 不引入自定义 Python 异常类型（避免迁移期类型抖动）
- `tracing` crate 打结构化日志，自动透传到 Python `logging`

---

## 5. 并行化策略

**复用 Python 现有 `ProcessPoolExecutor` 的并行模式**，Rust 侧用 `rayon` 直接对齐。

| 模块 | Python 当前并行 | Rust 并行策略 | 预期加速比 |
|---|---|---|---|
| `screener` | `ProcessPoolExecutor`（阈值 50 只） | `rayon::par_iter` + `into_par_iter()` | 5–10× |
| `backtest` 单策略 | 无 | 单策略内 `par_iter` 扫股票 | 5–20× |
| `backtest` portfolio | 无 | portfolio 内并行扫描多策略 | 8–15× |
| `grid_search` | 进程池 | `par_iter` 跨 (walk_forward_window × param_combo) 二维笛卡尔积 | **30–100×** |
| `walk_forward` | 顺序切片 | 各 OOS 段 `par_iter` 并行 | 3–8× |
| 指标批量计算 | 进程池 | `polars` 内部 SIMD + 列并行 | 5–15× |

**示例代码**（grid_search 核心）：

```rust
use rayon::prelude::*;

pub fn run_grid_search(
    splits: &[WalkForwardSplit],
    param_grid: &[ParamSet],
    metric_fn: impl Fn(&ParamSet, &WalkForwardSplit) -> f64 + Sync + Send,
) -> Vec<(ParamSet, f64)> {
    splits.par_iter()
        .flat_map(|split| param_grid.par_iter().map(move |p| (p.clone(), split)))
        .map(|(p, s)| {
            let score = metric_fn(&p, s);
            (p, score)
        })
        .collect()
}
```

**Rust 侧不需要 tokio**——纯 CPU bound 同步任务，rayon 即可。

**关键约束**：
- rayon's 默认线程池大小尊重 `RAYON_NUM_THREADS` 环境变量
- 第一次启动输出 `Rayon: N threads` 方便排错
- Python 侧的 `multiprocessing.cpu_count()` / NUMA 亲和设置不受影响（业务层在 Python）

---

## 6. 测试与迁移策略

### 6.1 三层测试金字塔

```
                ▲
               ╱ ╲
              ╱   ╲           E2E：原 79 个 Python 测试（仅改 import 路径）
             ╱─────╲
            ╱       ╲         集成：Rust 端 property tests + golden file 对比
           ╱─────────╲
          ╱           ╲       单元：Rust 单元测试（每 crate 内）
         ╱─────────────╲
```

### 6.2 M1：Golden File 工具

**思路**：先用 Python 实现跑真实输入，把输入/输出序列化到 `tests/golden/*.json`。Rust 端读取同一份 JSON，跑相同逻辑，断言数值相等（容差 1e-9）。

```rust
// crates/backtest_engine/tests/golden_test.rs
use approx::assert_abs_diff_eq;

#[test]
fn portfolio_backtest_matches_python() {
    for case in GoldenBacktest::load_all("tests/golden/backtest/*.json") {
        let result = run_portfolio_backtest(&case.input.klines, &case.input.config);
        for (i, (got, want)) in result.net_values.iter()
            .zip(case.expected.net_values.iter()).enumerate()
        {
            assert_abs_diff_eq!(got, want, epsilon = 1e-9,
                "net_values[{i}] mismatch on case {}", case.name);
        }
    }
}
```

**生成 golden 文件的命令**：
```bash
python scripts/generate_golden.py --module backtest --output tests/golden/backtest/
```

### 6.3 M2：Property-Based Testing

针对纯数学逻辑，用 `proptest` 跑数千个随机用例，验证不变量：

```rust
proptest! {
    #[test]
    fn atr_is_non_negative(klines in arb_klines(50..200)) {
        let atr = compute_atr(&klines, 14).unwrap();
        prop_assert!(atr.iter().all(|&v| v >= 0.0));
    }

    #[test]
    fn walk_forward_splits_cover_all_dates(
        total_days in 100usize..2000,
        train in 30usize..200,
        test in 10usize..100,
    ) {
        let splits = make_walk_forward_splits(total_days, train, test);
        let covered: HashSet<_> = splits.iter().flat_map(|s| s.test_range()).collect();
        let all_dates: HashSet<_> = (0..total_days).collect();
        prop_assert_eq!(covered, all_dates, "splits must cover every date exactly once");
    }
}
```

### 6.4 M3：双跑对比（Shadow Mode）

每个 Rust 函数上线前，CI 加 shadow job：

```bash
# .github/workflows/shadow.yml
- name: Shadow compare
  run: |
    python scripts/shadow_runner.py --module backtest --samples 50 \
      --python modules.backtest.portfolio:PortfolioBacktestEngine \
      --rust _core_compute:PortfolioBacktestEngine \
      --max-diff 1e-9
```

**标准**：连续 5 个 PR 全绿才认为 Rust 实现稳定。

### 6.5 迁移开关（安全网）

**业务代码完全无感**，通过环境变量切换：

```python
# modules/core/backtest_compat.py  （薄兼容层）
import os

def get_backtest_engine():
    impl = os.getenv("ZETTARANC_BACKTEST_IMPL", "rust")
    if impl == "rust":
        from _core_compute import PortfolioBacktestEngine
        return PortfolioBacktestEngine
    elif impl == "python":
        from modules.backtest.portfolio import PortfolioBacktestEngine
        return PortfolioBacktestEngine
    else:
        raise ValueError(f"unknown impl: {impl}")
```

**默认 `rust`**；出问题时 `ZETTARANC_BACKTEST_IMPL=python` 秒级回滚。

---

## 7. 里程碑

### 7.1 6 个里程碑总览

| M | 目标 | 关键产物 | 验收标准 |
|---|---|---|---|
| **M0** | 工具链跑通 | rust workspace + `bindings` crate 编出 `_core_compute.so` + 一个空的 `compute_atr` 函数 + GitHub Actions CI | `import _core_compute; _core_compute.compute_atr([], 14)` 不报错 |
| **M1** | 指标迁移 | `compute_atr` / `compute_atr_polars` 全实现 + golden test 全绿 + shadow 对比 5 PR 全绿 | ATR 计算结果与 Python byte-equal；单股 5000 根 K 线计算 ≥ 5× 加速 |
| **M2** | 单策略回测 | `run_single_strategy_backtest` + 既有 `test_backtest.py` / `test_backtest_six_step.py` 零修改通过 | 100 只股 × 1000 天回测 ≥ 8× 加速 |
| **M3** | 组合回测 | `PortfolioBacktestEngine`（Rust 版）+ `test_backtest_portfolio.py` 零修改通过 + 现有 `backtest portfolio` CLI 改走 Rust | 100 只股 × 1000 天组合回测 ≥ 10× 加速 |
| **M4** | **网格搜索 + Walk-forward**（最大收益点） | `grid_search` crate + `verify/walk_forward.py` 业务逻辑保留（调 Rust） + shadow 对比 | **50 参数 × 5 walk-forward 窗口 ≥ 30× 加速**（预期 30 min → 1 min） |
| **M5** | 选股引擎 | `screener` crate + 多因子评分 polars expression | 5000 只股 × 14 条件筛选 ≥ 5× 加速 |
| **M6** | 清理 | 删 Python 旧实现 / 删 compat 层 / 文档更新 / CHANGELOG | Python 测试 100% 通过；旧代码 0 引用；release notes 写清 |

### 7.2 每个 M 的退出标准

1. **正确性**：原 Python 测试零修改通过 + shadow diff 全绿
2. **性能**：benchmark 脚本产出加速比数字，写进 `docs/BENCHMARKS.md`
3. **可回滚**：`ZETTARANC_BACKTEST_IMPL=python` 验证秒级回退成功

### 7.3 性能验收环境

- macOS M2 + Linux x86_64（CI 两个都跑）
- 数据集固定：`tests/fixtures/real_klines_2024.parquet`（约 100 只股 × 1000 天）
- benchmark 脚本：`scripts/bench_rust_vs_python.py`，输出 markdown 表格

---

## 8. 风险与缓解

| 风险 | 等级 | 缓解策略 |
|---|---|---|
| Rust 实现与 Python 数值不一致 | 高 | golden file + shadow mode + byte-equal 断言（容差 1e-9） |
| 浮点累加顺序差异导致舍入误差 | 中 | 用 `polars` 内部 SIMD/向量化保证顺序一致；shadow 模式覆盖 |
| 迁移过程中 Python / Rust 双实现不一致 | 高 | compat shim 默认 Rust；Python 路径留作 fallback；M6 才删除 |
| maturin / PyO3 跨平台编译问题 | 中 | M0 即在 macOS + Linux CI 验证；Windows 暂不承诺 |
| polars Python 依赖膨胀（~30MB） | 低 | 用户已接受；polars 是 Rust 数据栈标准 |
| Rust 学习曲线 | 极低 | 用户为资深 Rust 开发者 |
| 重构引入回归破坏 79 个测试 | 高 | 每次 PR 都跑全套 Python 测试；compat shim 秒级回滚 |

---

## 9. 关联文档

- `docs/CHANGELOG.md` — 版本变更记录
- `docs/ROADMAP.md` — 产品路线图
- `docs/CONFIG_GUIDE.md` — 配置说明（包含新增环境变量）
- `docs/USER_GUIDE.md` — 用户使用说明
- `docs/superpowers/plans/` — 实施计划（待 writing-plans skill 输出）

---

## 10. 待用户确认事项

- [ ] 仓库根新建 `rust/` 子目录（不影响 Python 包结构），OK？
- [ ] SQLAlchemy/SQLite 读写层保持 Python，OK？
- [ ] 双层 API（高层保兼容 + 低层零拷贝）设计，OK？
- [ ] 默认 Rust + 环境变量回滚，OK？
- [ ] 6 个里程碑顺序（M0 → M6），OK？
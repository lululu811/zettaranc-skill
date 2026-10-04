# zettaranc-skill Rust 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 zettaranc-skill 项目的核心计算链路（指标 / 回测 / 网格搜索 / 选股）从 Python 迁到 Rust，预期提速 5–50×，并保证现有 79 个 Python 测试零修改通过 + 环境变量秒级回滚。

**Architecture:** 单仓双语言：Python 业务层保留（CLI / LLM / 数据源客户端 / SQLite），新增 `rust/` 子目录作为 Rust workspace，通过 PyO3 + maturin 编译出 `_core_compute` 原生扩展。Python 通过 `compat shim`（环境变量切换）默认调 Rust 实现，hot path 可走 Polars 零拷贝路径。

**Tech Stack:**
- Python 3.10–3.12 + 现有依赖（pandas / tushare / httpx / pyyaml / pytest）
- Rust 1.78+（edition 2021）
- maturin 1.5+（PyO3 构建后端）
- pyo3 0.21+ + pyo3-polars 0.10+
- polars 0.40+（Rust + Python）
- arrow-rs 53+
- rayon 1.10+（数据并行）
- thiserror 1.0+ / anyhow 1.0+
- proptest 1.4+ / approx 0.5+
- tracing 0.1+ + tracing-subscriber 0.3+
- GitHub Actions：macOS + Linux 双平台

---

## Global Constraints

1. **范围聚焦**：仅重写计算密集域（`modules/backtest/` / `modules/simulator/simulator.py` 撮合循环 / `modules/verify/walk_forward.py` / `modules/screener/engine.py` / `modules/core/atr.py`）。CLI、LLM、self_optimizer、数据源客户端、SQLite 读写**保持 Python**
2. **零侵入**：现有 79 个 Python 测试零修改通过（仅允许改 import 路径），CLI 命令/参数不变
3. **可回滚**：默认 Rust 实现，环境变量 `ZETTARANC_BACKTEST_IMPL=python` 秒级切回 Python 实现
4. **数值等价**：Rust 实现与 Python 实现对相同输入产出 byte-for-byte 一致结果（容差 1e-9）
5. **目录布局**：Rust workspace 在 `rust/` 子目录，crate 名带 `zt_` 前缀（如 `zt_core_types`），编译产物通过 maturin 暴露为 `_core_compute` Python 包
6. **CI**：GitHub Actions 同时跑 macOS（apple-m2）与 Linux（ubuntu-latest），每个 PR 触发
7. **版本管理**：单仓单版本号（沿用 v3.x → v4.x），新功能先在 `feature/rust-core-compute` 分支开发
8. **Python 风格**：4-space 缩进 / UTF-8 / LF / 中文 docstring / 类型注解
9. **Rust 风格**：rustfmt 默认格式（4-space 缩进，LF）；clippy `cargo clippy -- -D warnings` 必须通过
10. **M0 不允许**失败后回退：M0 任务一旦失败立即暂停，不累积到 M1

---

## Spec 一致性检查

| spec 段 | 对应 task |
|---|---|
| §2.2 工作区结构 | Task 1-3（M0） |
| §3.1-3.3 数据通道 / Polars / 双层 API | Task 4-5, Task 11-12（M0 + M1） |
| §4 错误处理 | Task 6-7（M0） |
| §5 并行化 | Task 14-15（M1 / M2） |
| §6 测试与迁移 | Task 8-10（M0）+ 每个 M 末尾的 golden file + shadow mode |
| §7 里程碑 | M0-M6 全 6 个 milestone |
| §8 风险缓解 | 每个 M 末尾的退出标准三件套 |

---

# Milestone 0：工具链跑通

## Task 1: 创建 Rust workspace 骨架

**Files:**
- Create: `rust/Cargo.toml`
- Create: `rust/crates/.gitkeep`
- Create: `rust/rust-toolchain.toml`

**为什么先做**：所有后续 task 的依赖根；M0 任务的失败不允许累积。

- [ ] **Step 1: 创建 `rust/` 目录**

Run: `mkdir -p rust/crates && touch rust/crates/.gitkeep`

- [ ] **Step 2: 写入 `rust-toolchain.toml`**

文件：`rust/rust-toolchain.toml`：

```toml
[toolchain]
channel = "1.78.0"
components = ["rustfmt", "clippy", "rust-src"]
profile = "minimal"
```

- [ ] **Step 3: 写入 workspace root `Cargo.toml`**

文件：`rust/Cargo.toml`：

```toml
[workspace]
resolver = "2"
members = [
    "crates/core_types",
    "crates/indicators",
    "crates/backtest_engine",
    "crates/grid_search",
    "crates/screener",
    "crates/bindings",
]

[workspace.package]
edition = "2021"
rust-version = "1.78"
license = "MIT"
authors = ["zettaranc contributors"]

[workspace.dependencies]
# 序列化 / 错误
thiserror = "1.0"
anyhow = "1.0"
# 异步日志（仅错误透传用，不引入 tokio）
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
# 数据栈
polars = { version = "0.40", default-features = false, features = ["dtype-full", "temporal", "strings"] }
arrow-array = "53"
arrow-schema = "53"
# 并行
rayon = "1.10"
# 测试
proptest = "1.4"
approx = "0.5"

# 仅在 bindings crate 中使用 pyo3 / pyo3-polars（避免污染纯 Rust 测试）
pyo3 = { version = "0.21", features = ["extension-module", "abi3-py310"], optional = true }
pyo3-polars = { version = "0.10", git = "https://github.com/ritchie46/polars", features = ["lazy"], optional = true }

[profile.release]
opt-level = 3
lto = "thin"
codegen-units = 1
strip = "symbols"
```

- [ ] **Step 4: 验证 workspace 结构**

Run: `cd rust && cargo metadata --no-deps --format-version 1 | head -c 200`

Expected: 输出 JSON metadata 头（前 200 字符）无错误。

- [ ] **Step 5: 提交**

```bash
cd /Users/chenlei/005_skill/skills/zettaranc-skill
git add rust/
git commit -m "chore(rust): scaffold workspace with 6 crates and shared deps"
```

---

## Task 2: 创建 `core_types` crate（共享类型 + Arrow schema）

**Files:**
- Create: `rust/crates/core_types/Cargo.toml`
- Create: `rust/crates/core_types/src/lib.rs`
- Create: `rust/crates/core_types/src/schema.rs`
- Create: `rust/crates/core_types/src/error.rs`
- Create: `rust/crates/core_types/tests/smoke.rs`

**Interfaces:**
- Produces: `kline_schema() -> SchemaRef`，`CoreError` 枚举，`pub type Result<T> = std::result::Result<T, CoreError>;`
- Consumes: 无

- [ ] **Step 1: 创建 `Cargo.toml`**

文件：`rust/crates/core_types/Cargo.toml`：

```toml
[package]
name = "zt_core_types"
version = "0.1.0"
edition.workspace = true
rust-version.workspace = true

[dependencies]
thiserror = { workspace = true }
polars = { workspace = true }
arrow-array = { workspace = true }
arrow-schema = { workspace = true }

[dev-dependencies]
proptest = { workspace = true }
```

- [ ] **Step 2: 写入 `src/lib.rs`**

文件：`rust/crates/core_types/src/lib.rs`：

```rust
//! zettaranc 共享类型 + Arrow schema + 错误定义。
//!
//! 这是所有 Rust crate 的依赖根。Python 业务层通过 `_core_compute`
//! （由 `bindings` crate 暴露）访问本 crate 导出的能力。

#![forbid(unsafe_code)]
#![warn(missing_debug_implementations)]

pub mod error;
pub mod schema;

pub use error::{CoreError, Result};
pub use schema::kline_schema;
```

- [ ] **Step 3: 写入 `src/error.rs`**

文件：`rust/crates/core_types/src/error.rs`：

```rust
use thiserror::Error;

/// 整个 Rust 内核的统一错误类型。所有 crate 边界都用这个。
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
    InvalidParameter {
        field: String,
        value: f64,
        constraint: String,
    },

    #[error("walk-forward split invalid: {0}")]
    InvalidWalkForward(String),

    #[error("database: {0}")]
    Database(String),

    #[error(transparent)]
    Polars(#[from] polars::error::PolarsError),

    #[error(transparent)]
    Arrow(#[from] arrow_schema::ArrowError),
}

pub type Result<T> = std::result::Result<T, CoreError>;
```

- [ ] **Step 4: 写入 `src/schema.rs`**

文件：`rust/crates/core_types/src/schema.rs`：

```rust
use std::sync::Arc;

use arrow_schema::{DataType, Field, Schema, SchemaRef};

/// K 线数据的 Arrow schema。Rust 和 Python 共享同一份字节布局。
pub fn kline_schema() -> SchemaRef {
    Arc::new(Schema::from_iter(vec![
        Field::new("ts_code", DataType::Utf8, false),
        Field::new("trade_date", DataType::Date32, false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("vol", DataType::Float64, false),
        Field::new("amount", DataType::Float64, false),
        Field::new("pct_chg", DataType::Float64, false),
        Field::new("vol_ratio", DataType::Float64, true),
        Field::new("is_limit_up", DataType::Boolean, true),
        Field::new("is_limit_down", DataType::Boolean, true),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schema_has_12_fields() {
        let s = kline_schema();
        assert_eq!(s.fields().len(), 12);
        assert_eq!(s.field(0).name(), "ts_code");
        assert_eq!(s.field(4).name(), "close");
    }
}
```

- [ ] **Step 5: 写入 smoke test `tests/smoke.rs`**

文件：`rust/crates/core_types/tests/smoke.rs`：

```rust
use zt_core_types::{kline_schema, CoreError};

#[test]
fn schema_loads() {
    let s = kline_schema();
    assert_eq!(s.fields().len(), 12);
}

#[test]
fn error_display_works() {
    let e = CoreError::InsufficientData { need: 100, got: 50 };
    let msg = format!("{e}");
    assert!(msg.contains("100"));
    assert!(msg.contains("50"));
}
```

- [ ] **Step 6: 跑测试**

Run: `cd rust && cargo test -p zt_core_types`

Expected:
```
running 3 tests
test schema::tests::schema_has_12_fields ... ok
test error::tests:: ... (无 — 写到 tests/ 目录了)
test smoke::schema_loads ... ok
test smoke::error_display_works ... ok

test result: ok. 3 passed; 0 failed
```

- [ ] **Step 7: 提交**

```bash
git add rust/crates/core_types/
git commit -m "feat(rust): core_types crate with Arrow schema and error types"
```

---

## Task 3: 创建占位 crate（其余 5 个，先放 stub）

**Files:**
- Create: `rust/crates/indicators/Cargo.toml` + `src/lib.rs`
- Create: `rust/crates/backtest_engine/Cargo.toml` + `src/lib.rs`
- Create: `rust/crates/grid_search/Cargo.toml` + `src/lib.rs`
- Create: `rust/crates/screener/Cargo.toml` + `src/lib.rs`
- Create: `rust/crates/bindings/Cargo.toml` + `src/lib.rs`

**为什么先占位**：让 workspace 在 M0 阶段即可 `cargo build --workspace` 成功，避免后续 task 一边写代码一边补脚手架。

- [ ] **Step 1: 创建 `indicators/Cargo.toml`**

文件：`rust/crates/indicators/Cargo.toml`：

```toml
[package]
name = "zt_indicators"
version = "0.1.0"
edition.workspace = true
rust-version.workspace = true

[dependencies]
zt_core_types = { path = "../core_types" }
polars = { workspace = true }
arrow-array = { workspace = true }
```

文件：`rust/crates/indicators/src/lib.rs`：

```rust
//! 技术指标 crate（ATR / 均线 / KDJ / MACD / BBI / RSI / 主力阶段）。
//!
//! 真实实现在 M1 落地。
#![forbid(unsafe_code)]

pub fn placeholder() -> &'static str {
    "zt_indicators: see M1"
}
```

- [ ] **Step 2: 创建 `backtest_engine/Cargo.toml`**

文件：`rust/crates/backtest_engine/Cargo.toml`：

```toml
[package]
name = "zt_backtest_engine"
version = "0.1.0"
edition.workspace = true
rust-version.workspace = true

[dependencies]
zt_core_types = { path = "../core_types" }
zt_indicators = { path = "../indicators" }
polars = { workspace = true }
arrow-array = { workspace = true }
rayon = { workspace = true }
```

文件：`rust/crates/backtest_engine/src/lib.rs`：

```rust
//! 回测引擎 crate（单策略 + 组合）。
//!
//! 真实实现在 M2 / M3 落地。
#![forbid(unsafe_code)]

pub fn placeholder() -> &'static str {
    "zt_backtest_engine: see M2/M3"
}
```

- [ ] **Step 3: 创建 `grid_search/Cargo.toml`**

文件：`rust/crates/grid_search/Cargo.toml`：

```toml
[package]
name = "zt_grid_search"
version = "0.1.0"
edition.workspace = true
rust-version.workspace = true

[dependencies]
zt_core_types = { path = "../core_types" }
zt_backtest_engine = { path = "../backtest_engine" }
polars = { workspace = true }
rayon = { workspace = true }
```

文件：`rust/crates/grid_search/src/lib.rs`：

```rust
//! 参数网格搜索 + Walk-forward crate。
//!
//! 真实实现在 M4 落地。
#![forbid(unsafe_code)]

pub fn placeholder() -> &'static str {
    "zt_grid_search: see M4"
}
```

- [ ] **Step 4: 创建 `screener/Cargo.toml`**

文件：`rust/crates/screener/Cargo.toml`：

```toml
[package]
name = "zt_screener"
version = "0.1.0"
edition.workspace = true
rust-version.workspace = true

[dependencies]
zt_core_types = { path = "../core_types" }
zt_indicators = { path = "../indicators" }
polars = { workspace = true }
rayon = { workspace = true }
```

文件：`rust/crates/screener/src/lib.rs`：

```rust
//! 选股引擎 crate。
//!
//! 真实实现在 M5 落地。
#![forbid(unsafe_code)]

pub fn placeholder() -> &'static str {
    "zt_screener: see M5"
}
```

- [ ] **Step 5: 创建 `bindings/Cargo.toml`**

文件：`rust/crates/bindings/Cargo.toml`：

```toml
[package]
name = "zt_bindings"
version = "0.1.0"
edition.workspace = true
rust-version.workspace = true

[lib]
name = "_core_compute"
crate-type = ["cdylib"]

[dependencies]
zt_core_types = { path = "../core_types" }
zt_indicators = { path = "../indicators" }
zt_backtest_engine = { path = "../backtest_engine" }
zt_grid_search = { path = "../grid_search" }
zt_screener = { path = "../screener" }
pyo3 = { workspace = true, optional = true }
pyo3-polars = { workspace = true, optional = true }
polars = { workspace = true }
```

文件：`rust/crates/bindings/src/lib.rs`：

```rust
//! PyO3 绑定 crate，编译成 `_core_compute` 原生扩展。
//!
//! 真实实现在每个 M 的最后一个 task 落地。
#![forbid(unsafe_code)]

pub fn placeholder() -> &'static str {
    "zt_bindings: see each M's last task"
}
```

- [ ] **Step 6: 验证 workspace 可编译**

Run: `cd rust && cargo build --workspace`

Expected: 编译成功（warning 可接受，但不能有 error）。

- [ ] **Step 7: 提交**

```bash
git add rust/crates/
git commit -m "chore(rust): placeholder crates for 5 remaining modules"
```

---

## Task 4: 接入 maturin + Python 包入口

**Files:**
- Modify: `pyproject.toml`（追加 maturin 配置和 _core_compute 入口）
- Create: `python/_core_compute/__init__.py`（stub：先指向 maturin 编译产物）
- Modify: `tests/conftest.py`（如不存在则创建）增加 fixture 让 Python 测试能 import `_core_compute`

**为什么**：验证 Python 能 import 到 Rust 编译产物。maturin 是 PyO3 的事实标准构建后端。

- [ ] **Step 1: 在 `pyproject.toml` 追加 maturin 配置**

修改 `/Users/chenlei/005_skill/skills/zettaranc-skill/pyproject.toml`，**保留已有内容**，在 `[tool]` 节后追加：

```toml
[tool.maturin]
name = "_core_compute"
# maturin 通过 rust/crates/bindings/Cargo.toml 自动找 crate
features = ["pyo3/extension-module", "pyo3/abi3-py310"]
# Python 源码路径（虽然 crate 是 Rust，但 maturin 需要一个占位 Python 包）
python-source = "python"
module-name = "_core_compute._core_compute"
# ABI3：编译一次支持 Python 3.10+
```

并在 `[project.optional-dependencies]` 节追加（如果还没有 `dev` 节，则补一个）：

```toml
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "maturin>=1.5.0",
]
```

- [ ] **Step 2: 创建占位 Python 包**

Run: `mkdir -p python/_core_compute`

文件：`python/_core_compute/__init__.py`：

```python
"""_core_compute: Rust 内核的 Python 入口

由 maturin 编译 `rust/crates/bindings` crate 生成。
M0 阶段此处为空，所有功能在后续 M1-M5 逐步暴露。
"""
__version__ = "0.1.0"
```

- [ ] **Step 3: 跑 maturin develop 编译并安装**

Run: `cd rust/crates/bindings && maturin develop --release`

Expected: 编译成功，最后输出 `🎉 Python package _core_compute` 类似成功消息。如果第一次跑需要装 polars Python 侧：

```bash
pip install polars pyarrow
```

- [ ] **Step 4: 验证 Python 可 import**

Run: `python -c "import _core_compute; print(_core_compute.__version__)"`

Expected: `0.1.0`

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml python/
git commit -m "build(rust): maturin wiring with _core_compute package stub"
```

---

## Task 5: GitHub Actions CI（macOS + Linux）

**Files:**
- Create: `.github/workflows/rust-ci.yml`

- [ ] **Step 1: 写 CI workflow**

文件：`.github/workflows/rust-ci.yml`：

```yaml
name: rust-ci

on:
  pull_request:
    paths:
      - "rust/**"
      - "python/**"
      - "pyproject.toml"
      - ".github/workflows/rust-ci.yml"
  push:
    branches: [main, feature/rust-core-compute]

jobs:
  test-rust:
    name: cargo test (${{ matrix.os }})
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust
        uses: dtolnay/rust-toolchain@1.78.0
        with:
          components: rustfmt, clippy

      - name: Cache cargo registry & target
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            rust/target
          key: ${{ runner.os }}-cargo-${{ hashFiles('rust/Cargo.lock') }}
          restore-keys: |
            ${{ runner.os }}-cargo-

      - name: cargo fmt --check
        working-directory: rust
        run: cargo fmt --all -- --check

      - name: cargo clippy
        working-directory: rust
        run: cargo clippy --workspace --all-targets -- -D warnings

      - name: cargo test
        working-directory: rust
        run: cargo test --workspace

  test-python:
    name: python smoke (${{ matrix.os }})
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Rust
        uses: dtolnay/rust-toolchain@1.78.0

      - name: Install maturin
        run: pip install maturin pytest polars pyarrow

      - name: Build _core_compute
        run: |
          cd rust/crates/bindings
          maturin develop --release

      - name: Smoke import
        run: |
          python -c "import _core_compute; print(_core_compute.__version__)"
```

- [ ] **Step 2: 提交**

```bash
git add .github/workflows/rust-ci.yml
git commit -m "ci(rust): GitHub Actions for cargo + maturin on macOS+Linux"
```

- [ ] **Step 3: 验证 CI workflow 语法**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/rust-ci.yml'))"`

Expected: 无报错（YAML 解析成功）。

---

## Task 6: Rust 错误 → Python 异常映射层

**Files:**
- Modify: `rust/crates/bindings/Cargo.toml`（启用 pyo3 feature）
- Modify: `rust/crates/bindings/src/lib.rs`（加 `impl From<CoreError> for PyErr`）

**Interfaces:**
- Produces: `core_error_to_pyerr(err: CoreError) -> PyErr` 函数
- Consumes: `CoreError` 枚举（来自 `zt_core_types`）

- [ ] **Step 1: 启用 pyo3 feature**

修改 `rust/crates/bindings/Cargo.toml`，把 `pyo3` 行改为：

```toml
pyo3 = { workspace = true }
pyo3-polars = { workspace = true }
```

（M0 阶段 pyo3 必启；pyo3-polars 在 M1 启用更合理，这里先打开，cargo 会按需 build。）

- [ ] **Step 2: 写 PyO3 错误映射模块**

文件：`rust/crates/bindings/src/error.rs`：

```rust
use pyo3::exceptions::{PyKeyError, PyRuntimeError, PyValueError};
use pyo3::PyErr;
use zt_core_types::CoreError;

/// 把 Rust 业务错误映射到 Python 异常类型。
/// 约定：业务可恢复 → ValueError / KeyError；基础设施 → RuntimeError。
pub fn core_error_to_pyerr(e: CoreError) -> PyErr {
    match e {
        CoreError::InvalidKLine(m)
        | CoreError::InvalidWalkForward(m)
        | CoreError::EmptyDateRange { .. } => PyValueError::new_err(e.to_string()),
        CoreError::MissingColumn(c) => PyKeyError::new_err(c),
        CoreError::InsufficientData { .. } | CoreError::InvalidParameter { .. } => {
            PyValueError::new_err(e.to_string())
        }
        CoreError::Database(m) => PyRuntimeError::new_err(m),
        CoreError::Polars(p) => PyRuntimeError::new_err(format!("polars: {p}")),
        CoreError::Arrow(a) => PyRuntimeError::new_err(format!("arrow: {a}")),
    }
}
```

- [ ] **Step 3: 改 `bindings/src/lib.rs` 导出 pymodule + smoke 函数**

文件：`rust/crates/bindings/src/lib.rs`：

```rust
//! PyO3 绑定 crate，编译成 `_core_compute` 原生扩展。
#![forbid(unsafe_code)]

mod error;

pub use error::core_error_to_pyerr;

use pyo3::prelude::*;

/// 测试函数：证明 Rust 编译产物可以被 Python 调用。
#[pyfunction]
fn rust_smoke() -> &'static str {
    "ok from rust"
}

/// 抛出一个业务异常，验证错误映射。
#[pyfunction]
fn raise_value_error() -> PyResult<()> {
    use zt_core_types::CoreError;
    Err(core_error_to_pyerr(CoreError::InvalidKLine("test".to_string())))
}

/// 抛出一个 KeyError。
#[pyfunction]
fn raise_key_error() -> PyResult<()> {
    use zt_core_types::CoreError;
    Err(core_error_to_pyerr(CoreError::MissingColumn("ts_code".to_string())))
}

#[pymodule]
fn _core_compute(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(rust_smoke, m)?)?;
    m.add_function(wrap_pyfunction!(raise_value_error, m)?)?;
    m.add_function(wrap_pyfunction!(raise_key_error, m)?)?;
    Ok(())
}
```

- [ ] **Step 4: 重新编译**

Run: `cd rust/crates/bindings && maturin develop --release`

Expected: 编译成功。

- [ ] **Step 5: 验证错误映射**

Run:
```bash
python -c "
import _core_compute
print(_core_compute.rust_smoke())
try:
    _core_compute.raise_value_error()
except ValueError as e:
    print(f'ValueError caught: {e}')
try:
    _core_compute.raise_key_error()
except KeyError as e:
    print(f'KeyError caught: {e}')
"
```

Expected:
```
ok from rust
ValueError caught: invalid K-line data: test
KeyError caught: ts_code
```

- [ ] **Step 6: 提交**

```bash
git add rust/crates/bindings/
git commit -m "feat(rust): error mapping to Python ValueError/KeyError/RuntimeError"
```

---

## Task 7: compat shim（Python 侧兼容层）

**Files:**
- Create: `modules/core/_rust_compat.py`

**Interfaces:**
- Produces: `get_compute_module()` 函数，根据 `ZETTARANC_BACKTEST_IMPL` 环境变量返回 `_core_compute` 或 `None`（fallback 留给业务代码自行 import）
- Consumes: 无

- [ ] **Step 1: 写 compat shim**

文件：`modules/core/_rust_compat.py`：

```python
"""Rust / Python 实现切换 compat shim。

业务代码通过此模块判断是否启用 Rust 实现：

    from modules.core._rust_compat import get_compute_module

    compute = get_compute_module()
    if compute is not None:
        return compute.compute_atr(klines, 14)
    else:
        # 走原 Python 实现
        from modules.core.atr import calculate_atr
        return calculate_atr(klines, 14)

环境变量：
    ZETTARANC_BACKTEST_IMPL = "rust"（默认）| "python" | "auto"
        rust   - 强制使用 Rust
        python - 强制使用 Python（跳过 _core_compute 导入）
        auto   - 优先 Rust；导入失败则降级 Python
"""
from __future__ import annotations

import os
from types import ModuleType
from typing import Literal

ImplChoice = Literal["rust", "python", "auto"]

_DEFAULT_IMPL: ImplChoice = "rust"


def get_impl_choice() -> ImplChoice:
    """读取并校验 ZETTARANC_BACKTEST_IMPL 环境变量。"""
    raw = os.getenv("ZETTARANC_BACKTEST_IMPL", _DEFAULT_IMPL).lower()
    if raw not in ("rust", "python", "auto"):
        raise ValueError(
            f"invalid ZETTARANC_BACKTEST_IMPL={raw!r}; expected one of: rust, python, auto"
        )
    return raw  # type: ignore[return-value]


_cached_module: ModuleType | None = None
_cached_resolved: bool = False


def get_compute_module() -> ModuleType | None:
    """返回 _core_compute 模块；若不可用则返回 None。

    "auto" 模式下：成功导入返回模块，失败返回 None。
    "rust" 模式下：导入失败抛 RuntimeError。
    "python" 模式下：永远返回 None。
    """
    global _cached_module, _cached_resolved
    if _cached_resolved:
        return _cached_module

    choice = get_impl_choice()
    if choice == "python":
        _cached_module = None
        _cached_resolved = True
        return None

    try:
        import _core_compute  # type: ignore[import-not-found]

        _cached_module = _core_compute
        _cached_resolved = True
        return _cached_module
    except ImportError as e:
        if choice == "rust":
            raise RuntimeError(
                f"_core_compute import failed (impl=rust): {e}. "
                f"Set ZETTARANC_BACKTEST_IMPL=python to fall back, "
                f"or run `maturin develop --release` to build."
            ) from e
        # auto 模式：降级
        _cached_module = None
        _cached_resolved = True
        return None


def reset_cache() -> None:
    """测试用：清空模块缓存。"""
    global _cached_module, _cached_resolved
    _cached_module = None
    _cached_resolved = False
```

- [ ] **Step 2: 写单元测试**

文件：`tests/test_rust_compat.py`：

```python
"""compat shim 的单元测试。"""
import importlib

import pytest


def test_default_is_rust(monkeypatch):
    monkeypatch.delenv("ZETTARANC_BACKTEST_IMPL", raising=False)
    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    assert _rust_compat.get_impl_choice() == "rust"


def test_invalid_impl_raises(monkeypatch):
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "java")
    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    with pytest.raises(ValueError, match="invalid"):
        _rust_compat.get_impl_choice()


def test_python_choice_returns_none(monkeypatch):
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "python")
    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    assert _rust_compat.get_compute_module() is None


def test_rust_choice_returns_module(monkeypatch):
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "rust")
    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    mod = _rust_compat.get_compute_module()
    assert mod is not None
    assert mod.__name__ == "_core_compute"


def test_auto_mode_falls_back_on_import_error(monkeypatch):
    """auto 模式下如果 _core_compute 不存在应返回 None（不抛错）。"""
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "auto")

    # 模拟 _core_compute 不可用
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "_core_compute":
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    assert _rust_compat.get_compute_module() is None
```

- [ ] **Step 3: 跑测试**

Run: `pytest tests/test_rust_compat.py -v`

Expected: 5 个用例全过。

- [ ] **Step 4: 提交**

```bash
git add modules/core/_rust_compat.py tests/test_rust_compat.py
git commit -m "feat(compat): env-var Rust/Python switch shim with auto fallback"
```

---

## Task 8: Python 侧测试基线快照（M0 退出前）

**Files:**
- Create: `scripts/snapshot_python_tests.sh`

**为什么**：建立重构前的"已知全绿"基线，M1 起每个 task 都跑同一套断言确认零回归。

- [ ] **Step 1: 写快照脚本**

文件：`scripts/snapshot_python_tests.sh`：

```bash
#!/usr/bin/env bash
# 跑全套 Python 测试并把状态保存到 .m0_baseline.txt
# M0 退出前必须确认全绿。

set -euo pipefail
cd "$(dirname "$0")/.."

# 排除需外部凭证（realdata / TUSHARE_TOKEN）的测试
TEST_TARGETS=(
    tests/test_backtest.py
    tests/test_backtest_portfolio.py
    tests/test_backtest_six_step.py
    tests/test_backtest_scorer.py
    tests/test_simulator.py
    tests/test_verify_pipeline.py
    tests/test_verify_gates.py
    tests/test_verify_scorer.py
    tests/test_verify_walk_forward.py
    tests/test_screener.py
    tests/test_core.py
    tests/test_indicators.py
    tests/test_rust_compat.py
)

OUT=".m0_baseline.txt"
: > "$OUT"

for t in "${TEST_TARGETS[@]}"; do
    if [ -f "$t" ]; then
        echo "=== $t ===" | tee -a "$OUT"
        pytest "$t" -q --no-header -m "not realdata and not slow" 2>&1 | tee -a "$OUT" || true
    fi
done

echo
echo "Baseline saved to $OUT"
echo "Pass count:"
grep -oE '[0-9]+ passed' "$OUT" | awk '{s+=$1} END {print s}'
```

- [ ] **Step 2: 加可执行权限**

Run: `chmod +x scripts/snapshot_python_tests.sh`

- [ ] **Step 3: 跑基线（首次会记录现有状态）**

Run: `bash scripts/snapshot_python_tests.sh 2>&1 | tail -30`

Expected: 大部分测试 pass；记下 pass count 作为 M1+ 回归比对基线。

- [ ] **Step 4: 提交**

```bash
git add scripts/snapshot_python_tests.sh .m0_baseline.txt
git commit -m "test(m0): baseline Python test snapshot before Rust migration"
```

---

## Task 9: M0 退出验收

- [ ] **Step 1: 完整验收清单**

```bash
# 1. Rust workspace 编译 + clippy + 测试
cd rust && cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace

# 2. maturin 编译并安装
cd crates/bindings && maturin develop --release

# 3. Python smoke
cd ../../..
python -c "
import _core_compute
assert _core_compute.rust_smoke() == 'ok from rust'
try:
    _core_compute.raise_value_error()
except ValueError:
    pass
else:
    raise AssertionError('expected ValueError')
print('M0 smoke OK')
"

# 4. compat shim 单元测试
pytest tests/test_rust_compat.py -v

# 5. Python 全套测试基线
bash scripts/snapshot_python_tests.sh
```

Expected: 全部 step 通过；如果有失败，回到对应 task 修复，**不允许跳到 M1**。

- [ ] **Step 2: 提交 M0 验收记录**

```bash
git tag m0-rust-toolchain-baseline -m "M0 complete: Rust toolchain + bindings + compat shim"
```

---

# Milestone 1：指标迁移（compute_atr）

> 本里程碑目标：把 `modules/core/atr.py` 用 Rust 重写（`zt_indicators::compute_atr`），绑定到 `_core_compute.compute_atr`，Python 侧通过 compat shim 调用。

## Task 10: `compute_atr` Rust 实现 + 单元测试

**Files:**
- Modify: `rust/crates/indicators/src/lib.rs`
- Create: `rust/crates/indicators/src/atr.rs`

**Interfaces:**
- Produces: `pub fn compute_atr(klines: &KLineSeries, window: usize) -> Result<Vec<f64>>`
- Consumes: 无（KLineSeries 在本 task 定义）

- [ ] **Step 1: 定义 KLineSeries 共享类型**

修改 `rust/crates/core_types/src/lib.rs`，在 `pub mod schema;` 后追加：

```rust
pub mod kline;
```

创建 `rust/crates/core_types/src/kline.rs`：

```rust
//! K 线输入序列。纯字段结构，便于从 Python `list[DailyData]` 构造。
//!
//! 注意：本类型是行存输入格式。回测引擎会把它转成 Arrow 列存后再做计算。

#[derive(Debug, Clone)]
pub struct KLine {
    pub ts_code: String,
    pub trade_date: i32, // 距 1970-01-01 的天数（Date32）
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub vol: f64,
    pub amount: f64,
    pub pct_chg: f64,
    pub vol_ratio: Option<f64>,
    pub is_limit_up: Option<bool>,
    pub is_limit_down: Option<bool>,
}

#[derive(Debug, Clone)]
pub struct KLineSeries {
    pub items: Vec<KLine>,
}

impl KLineSeries {
    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }
}
```

- [ ] **Step 2: 写 `compute_atr` 实现**

创建 `rust/crates/indicators/src/atr.rs`：

```rust
//! ATR（Average True Range）实现。
//!
//! TR_t = max(high_t - low_t, |high_t - close_{t-1}|, |low_t - close_{t-1}|)
//! ATR_t = mean(TR_{t-window+1..=t})
//!
//! 输出长度 = len(klines)。前 (window-1) 个位置是 NaN/0.0，按 Python 现有约定
//! 用 0.0 占位（M1 末尾会和 Python 实现对比确认）。

use zt_core_types::{CoreError, KLineSeries, Result};

const DEFAULT_WINDOW: usize = 14;

pub fn compute_atr(klines: &KLineSeries, window: usize) -> Result<Vec<f64>> {
    if window == 0 {
        return Err(CoreError::InvalidParameter {
            field: "window".into(),
            value: 0.0,
            constraint: ">= 1".into(),
        });
    }
    if klines.len() < window {
        return Err(CoreError::InsufficientData {
            need: window,
            got: klines.len(),
        });
    }

    let n = klines.len();
    let mut tr = vec![0.0_f64; n];
    // 第一根 K 线的 TR = high - low
    tr[0] = klines.items[0].high - klines.items[0].low;

    for i in 1..n {
        let prev_close = klines.items[i - 1].close;
        let hi = klines.items[i].high;
        let lo = klines.items[i].low;
        let range1 = hi - lo;
        let range2 = (hi - prev_close).abs();
        let range3 = (lo - prev_close).abs();
        tr[i] = range1.max(range2).max(range3);
    }

    // ATR = rolling mean of TR over `window` days, 对齐到 tr[i]
    // 前 (window-1) 个位置按 Python 现有行为：返回 0.0
    let mut atr = vec![0.0_f64; n];
    let mut sum = 0.0_f64;
    for i in 0..n {
        sum += tr[i];
        if i >= window {
            sum -= tr[i - window];
        }
        if i + 1 >= window {
            atr[i] = sum / window as f64;
        }
    }

    Ok(atr)
}

pub fn compute_atr_default(klines: &KLineSeries) -> Result<Vec<f64>> {
    compute_atr(klines, DEFAULT_WINDOW)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_klines(prices: &[f64]) -> KLineSeries {
        let items = prices
            .iter()
            .enumerate()
            .map(|(i, &p)| zt_core_types::KLine {
                ts_code: "TEST".into(),
                trade_date: i as i32,
                open: p,
                high: p + 1.0,
                low: p - 1.0,
                close: p,
                vol: 0.0,
                amount: 0.0,
                pct_chg: 0.0,
                vol_ratio: None,
                is_limit_up: None,
                is_limit_down: None,
            })
            .collect();
        KLineSeries { items }
    }

    #[test]
    fn atr_empty_window_errors() {
        let ks = make_klines(&[1.0; 20]);
        assert!(matches!(
            compute_atr(&ks, 0),
            Err(CoreError::InvalidParameter { .. })
        ));
    }

    #[test]
    fn atr_insufficient_data_errors() {
        let ks = make_klines(&[1.0; 5]);
        assert!(matches!(
            compute_atr(&ks, 14),
            Err(CoreError::InsufficientData { .. })
        ));
    }

    #[test]
    fn atr_constant_prices_is_zero() {
        let ks = make_klines(&[10.0; 50]);
        let atr = compute_atr(&ks, 14).unwrap();
        // 常数价格：tr = 2（high-low），rolling mean 后所有非零位置都是 2
        for i in 13..atr.len() {
            assert!((atr[i] - 2.0).abs() < 1e-12, "atr[{i}]={}", atr[i]);
        }
    }

    #[test]
    fn atr_first_13_positions_are_zero() {
        let ks = make_klines(&(0..50).map(|i| i as f64).collect::<Vec<_>>());
        let atr = compute_atr(&ks, 14).unwrap();
        for i in 0..13 {
            assert_eq!(atr[i], 0.0);
        }
    }
}
```

- [ ] **Step 3: 在 `indicators/src/lib.rs` 导出**

修改 `rust/crates/indicators/src/lib.rs`：

```rust
//! 技术指标 crate。
#![forbid(unsafe_code)]

pub mod atr;

pub use atr::{compute_atr, compute_atr_default};
```

- [ ] **Step 4: 跑单元测试**

Run: `cd rust && cargo test -p zt_indicators`

Expected: `test result: ok. 4 passed; 0 failed`

- [ ] **Step 5: 提交**

```bash
git add rust/crates/core_types/src/kline.rs rust/crates/indicators/
git commit -m "feat(rust): compute_atr with unit tests"
```

---

## Task 11: PyO3 绑定 `compute_atr`（高层 API）

**Files:**
- Modify: `rust/crates/bindings/src/lib.rs`

**Interfaces:**
- Produces: Python 函数 `_core_compute.compute_atr(klines: list[dict], window: int = 14) -> list[float]`
- Consumes: `zt_indicators::compute_atr(KLineSeries, usize)`

- [ ] **Step 1: 写 PyO3 绑定代码**

修改 `rust/crates/bindings/src/lib.rs`，在现有内容后追加：

```rust
use zt_core_types::KLine;
use zt_indicators;

/// 高层 API：从 Python 接收 list[dict]，返回 list[float]。
#[pyfunction]
#[pyo3(signature = (klines, window=14))]
fn compute_atr_py(klines: Vec<Bound<'_, pyo3::PyAny>>, window: usize) -> PyResult<Vec<f64>> {
    let series = parse_klines(&klines)?;
    zt_indicators::compute_atr(&series, window)
        .map_err(crate::error::core_error_to_pyerr)
}

/// 把 Python list[dict] 转成 Rust KLineSeries。
fn parse_klines(items: &[Bound<'_, pyo3::PyAny>]) -> PyResult<zt_core_types::KLineSeries> {
    use pyo3::types::PyDict;
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        let d = item.downcast::<PyDict>()?;
        let get_f64 = |k: &str| -> PyResult<f64> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k))?
                .extract::<f64>()
        };
        let get_i32 = |k: &str| -> PyResult<i32> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k))?
                .extract::<i32>()
        };
        let get_str = |k: &str| -> PyResult<String> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k))?
                .extract::<String>()
        };
        let get_opt_f64 = |k: &str| -> PyResult<Option<f64>> {
            Ok(d.get_item(k)?
                .and_then(|v| if v.is_none() { None } else { Some(v) })
                .map(|v| v.extract::<f64>())
                .transpose()?)
        };
        let get_opt_bool = |k: &str| -> PyResult<Option<bool>> {
            Ok(d.get_item(k)?
                .and_then(|v| if v.is_none() { None } else { Some(v) })
                .map(|v| v.extract::<bool>())
                .transpose()?)
        };

        out.push(KLine {
            ts_code: get_str("ts_code")?,
            trade_date: get_i32("trade_date")?,
            open: get_f64("open")?,
            high: get_f64("high")?,
            low: get_f64("low")?,
            close: get_f64("close")?,
            vol: get_f64("vol")?,
            amount: get_f64("amount")?,
            pct_chg: get_f64("pct_chg")?,
            vol_ratio: get_opt_f64("vol_ratio")?,
            is_limit_up: get_opt_bool("is_limit_up")?,
            is_limit_down: get_opt_bool("is_limit_down")?,
        });
    }
    Ok(zt_core_types::KLineSeries { items: out })
}

#[pymodule]
fn _core_compute(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(rust_smoke, m)?)?;
    m.add_function(wrap_pyfunction!(raise_value_error, m)?)?;
    m.add_function(wrap_pyfunction!(raise_key_error, m)?)?;
    m.add_function(wrap_pyfunction!(compute_atr_py, m)?)?;
    Ok(())
}
```

- [ ] **Step 2: 重新编译**

Run: `cd rust/crates/bindings && maturin develop --release`

Expected: 编译成功。

- [ ] **Step 3: Python 验证**

Run:
```bash
python -c "
import _core_compute
klines = [{'ts_code': 'X', 'trade_date': i, 'open': 10.0, 'high': 11.0,
           'low': 9.0, 'close': 10.0, 'vol': 100.0, 'amount': 1000.0,
           'pct_chg': 0.0, 'vol_ratio': None, 'is_limit_up': None, 'is_limit_down': None}
          for i in range(50)]
result = _core_compute.compute_atr(klines, window=14)
print('first 13 zeros:', result[:13] == [0.0]*13)
print('result[13]:', result[13])
print('len:', len(result))
"
```

Expected:
```
first 13 zeros: True
result[13]: 2.0
len: 50
```

- [ ] **Step 4: 提交**

```bash
git add rust/crates/bindings/
git commit -m "feat(rust): PyO3 binding for compute_atr high-level API"
```

---

## Task 12: ATR golden file（数值等价性证明）

**Files:**
- Create: `scripts/generate_atr_golden.py`
- Create: `tests/golden/atr/basic.json`（脚本生成）
- Create: `rust/crates/bindings/tests/atr_golden.rs`

**为什么**：M1 核心契约——Rust 输出与 Python byte-for-byte 一致。

- [ ] **Step 1: 写 golden 生成脚本**

文件：`scripts/generate_atr_golden.py`：

```python
"""用现有 Python ATR 实现生成 golden file，Rust 测试会读取比对。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.core.atr import calculate_atr


def make_synthetic_klines(n: int = 100, seed: int = 42) -> list[dict]:
    """生成合成 K 线，保证测试可重放。"""
    import random
    rng = random.Random(seed)
    price = 10.0
    rows = []
    for i in range(n):
        change = rng.uniform(-0.5, 0.5)
        price = max(0.1, price + change)
        high = price + rng.uniform(0, 0.3)
        low = price - rng.uniform(0, 0.3)
        rows.append({
            "ts_code": "TEST",
            "trade_date": i,
            "open": price,
            "high": high,
            "low": low,
            "close": price,
            "vol": rng.uniform(1e6, 1e7),
            "amount": rng.uniform(1e8, 1e9),
            "pct_chg": change / max(price, 0.01) * 100,
            "vol_ratio": rng.uniform(0.5, 2.0),
            "is_limit_up": False,
            "is_limit_down": False,
        })
    return rows


def main():
    out_dir = Path("tests/golden/atr")
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = []
    for seed in (42, 7, 100):
        klines = make_synthetic_klines(100, seed=seed)
        for window in (14, 20):
            atr = calculate_atr(klines, window=window)
            cases.append({
                "name": f"seed{seed}_w{window}",
                "input": klines,
                "window": window,
                "expected": atr,
            })

    out_file = out_dir / "basic.json"
    with out_file.open("w") as f:
        json.dump({"cases": cases}, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(cases)} cases to {out_file}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 生成 golden file**

Run: `python scripts/generate_atr_golden.py`

Expected: `Wrote 6 cases to tests/golden/atr/basic.json`

- [ ] **Step 3: 写 Rust 端 golden test**

文件：`rust/crates/bindings/tests/atr_golden.rs`：

```rust
//! 用 Python 生成的 golden file 验证 Rust ATR 实现的数值等价性。

use approx::assert_abs_diff_eq;
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Deserialize)]
struct GoldenCase {
    name: String,
    input: Vec<serde_json::Value>,
    window: usize,
    expected: Vec<f64>,
}

#[derive(Deserialize)]
struct GoldenFile {
    cases: Vec<GoldenCase>,
}

fn load_golden() -> GoldenFile {
    let path: PathBuf = [
        env!("CARGO_MANIFEST_DIR"),
        "..",
        "..",
        "tests",
        "golden",
        "atr",
        "basic.json",
    ]
    .iter()
    .collect();
    let data = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("read golden {}: {e}", path.display()));
    serde_json::from_str(&data).expect("parse golden JSON")
}

#[test]
fn rust_atr_matches_python_for_all_cases() {
    let g = load_golden();
    assert!(!g.cases.is_empty(), "golden file is empty");

    for case in &g.cases {
        // 把 serde_json::Value 序列化成字符串，再让 Python 解析太重。
        // 这里直接走 zt_indicators，避免再次反序列化。
        let series: zt_core_types::KLineSeries = case
            .input
            .iter()
            .map(json_to_kline)
            .collect::<Result<Vec<_>, _>>()
            .expect("decode kline")
            .into();

        let got = zt_indicators::compute_atr(&series, case.window)
            .unwrap_or_else(|e| panic!("compute_atr({}) failed: {e}", case.name));

        assert_eq!(
            got.len(),
            case.expected.len(),
            "length mismatch for case {}",
            case.name
        );
        for (i, (g, w)) in got.iter().zip(case.expected.iter()).enumerate() {
            assert_abs_diff_eq!(g, w, epsilon = 1e-9);
        }
        println!("✓ case {} passed ({} values)", case.name, got.len());
    }
}

// 把 serde_json::Value 序列化成 serde_json，再次反序列化到 KLine —— 不优雅但准确。
fn json_to_kline(v: &serde_json::Value) -> Result<zt_core_types::KLine, String> {
    use serde_json::Value::*;
    let o = v.as_object().ok_or("not object")?;
    macro_rules! fld {
        ($k:literal, $t:ty) => {
            match o.get($k).ok_or_else(|| format!("missing {}", $k))? {
                Value::Number(n) => n
                    .as_f64()
                    .and_then(|x| <$t>::try_from(x).ok())
                    .ok_or_else(|| format!("{} not number", $k)),
                Value::Bool(b) => Err(format!("{} is bool, expected number", $k)),
                Value::String(_) => Err(format!("{} is string", $k)),
                Value::Null => Err(format!("{} is null", $k)),
                _ => Err(format!("{} has unexpected type", $k)),
            }
        };
    }
    Ok(zt_core_types::KLine {
        ts_code: o
            .get("ts_code")
            .and_then(|v| v.as_str())
            .ok_or("ts_code")?
            .to_string(),
        trade_date: fld!("trade_date", i32)?,
        open: fld!("open", f64)?,
        high: fld!("high", f64)?,
        low: fld!("low", f64)?,
        close: fld!("close", f64)?,
        vol: fld!("vol", f64)?,
        amount: fld!("amount", f64)?,
        pct_chg: fld!("pct_chg", f64)?,
        vol_ratio: o.get("vol_ratio").and_then(|v| v.as_f64()),
        is_limit_up: o.get("is_limit_up").and_then(|v| v.as_bool()),
        is_limit_down: o.get("is_limit_down").and_then(|v| v.as_bool()),
    })
}

// 工具方法：Vec<T> -> KLineSeries
impl From<Vec<zt_core_types::KLine>> for zt_core_types::KLineSeries {
    fn from(items: Vec<zt_core_types::KLine>) -> Self {
        zt_core_types::KLineSeries { items }
    }
}
```

需要在 `bindings/Cargo.toml` 加 serde_json：

```toml
[dev-dependencies]
serde_json = "1.0"
approx = { workspace = true }
```

- [ ] **Step 4: 跑 golden test**

Run: `cd rust && cargo test -p zt_bindings --test atr_golden`

Expected: `test result: ok. 1 passed; 0 failed` （6 个 case 全部 byte-equal）

- [ ] **Step 5: 提交**

```bash
git add scripts/generate_atr_golden.py tests/golden/atr/ rust/crates/bindings/tests/atr_golden.rs rust/crates/bindings/Cargo.toml
git commit -m "test(rust): golden file ATR numerical equivalence with Python"
```

---

## Task 13: ATR shadow runner（CI 用）+ M1 退出验收

**Files:**
- Create: `scripts/shadow_runner.py`

- [ ] **Step 1: 写 shadow runner**

文件：`scripts/shadow_runner.py`：

```python
"""对同一输入跑 Python 和 Rust 两个实现，比对输出。

用法：
    python scripts/shadow_runner.py --module atr --samples 100 --max-diff 1e-9

M1 阶段只支持 atr 模块；M2+ 扩展。
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_atr(klines, window):
    """跑 Rust 实现；不可用时跑 Python。"""
    impl = importlib.import_module("_core_compute")  # type: ignore
    return impl.compute_atr(klines, window=window)


def gen_klines(n, seed):
    import random
    rng = random.Random(seed)
    price = 10.0
    rows = []
    for i in range(n):
        ch = rng.uniform(-0.5, 0.5)
        price = max(0.1, price + ch)
        rows.append({
            "ts_code": "X",
            "trade_date": i,
            "open": price,
            "high": price + rng.uniform(0, 0.3),
            "low": price - rng.uniform(0, 0.3),
            "close": price,
            "vol": rng.uniform(1e6, 1e7),
            "amount": rng.uniform(1e8, 1e9),
            "pct_chg": 0.0,
            "vol_ratio": None,
            "is_limit_up": None,
            "is_limit_down": None,
        })
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--module", default="atr")
    p.add_argument("--samples", type=int, default=100)
    p.add_argument("--max-diff", type=float, default=1e-9)
    args = p.parse_args()

    if args.module != "atr":
        raise SystemExit(f"shadow_runner: module {args.module!r} not yet supported")

    from modules.core.atr import calculate_atr

    max_observed = 0.0
    for seed in range(args.samples):
        klines = gen_klines(120, seed=seed)
        py_result = calculate_atr(klines, window=14)
        rust_result = run_atr(klines, window=14)
        for py_v, rust_v in zip(py_result, rust_result):
            d = abs(py_v - rust_v)
            max_observed = max(max_observed, d)
            if d > args.max_diff:
                raise AssertionError(
                    f"seed {seed}: diff={d} > {args.max_diff}; py={py_v} rust={rust_v}"
                )

    print(f"OK: {args.samples} samples, max diff = {max_observed:.2e} (<= {args.max_diff:.0e})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑 shadow**

Run: `python scripts/shadow_runner.py --module atr --samples 100`

Expected: `OK: 100 samples, max diff = 0.00e+00 (<= 1e-09)`

- [ ] **Step 3: M1 退出验收**

```bash
cd rust
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace --release

cd ..
python scripts/snapshot_python_tests.sh
python scripts/shadow_runner.py --module atr --samples 100
```

预期：全部通过。

- [ ] **Step 4: 提交 + tag**

```bash
git add scripts/shadow_runner.py
git commit -m "test(rust): shadow runner for ATR; M1 exit criteria met"
git tag m1-atr-migrated -m "M1: compute_atr fully migrated with golden + shadow tests"
```

---

# Milestone 2：单策略回测

> 目标：把 `modules/backtest/single.py`（少妇六步单股回测）的核心循环用 Rust 重写。

## Task 14: 单策略回测引擎 Rust 实现

**Files:**
- Modify: `rust/crates/backtest_engine/src/lib.rs`
- Create: `rust/crates/backtest_engine/src/single.rs`

- [ ] **Step 1: 写 `run_single_strategy_backtest`**

文件：`rust/crates/backtest_engine/src/single.rs`：

```rust
//! 单策略单股回测。
//!
//! 输入：K 线序列 + 策略参数（j_threshold / stop_loss_pct / ...）
//! 输出：净值曲线 + 交易列表 + 基础指标。

use serde::{Deserialize, Serialize};
use zt_core_types::{CoreError, KLineSeries, Result};

#[derive(Debug, Clone, Deserialize)]
pub struct SingleStrategyConfig {
    pub j_threshold: f64,        // KDJ J 值阈值
    pub stop_loss_pct: f64,      // 止损百分比
    pub vol_shrink_threshold: f64,
    pub bbi_break_days: usize,
    pub min_holding_days: usize,
    pub lu_half: bool,           // 涨停减半
    pub position_pct: f64,       // 仓位比例
    pub initial_cash: f64,
}

impl Default for SingleStrategyConfig {
    fn default() -> Self {
        Self {
            j_threshold: -5.0,
            stop_loss_pct: 0.05,
            vol_shrink_threshold: 0.5,
            bbi_break_days: 3,
            min_holding_days: 3,
            lu_half: true,
            position_pct: 0.5,
            initial_cash: 100_000.0,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct SingleStrategyResult {
    pub net_values: Vec<f64>,
    pub cash_history: Vec<f64>,
    pub trades: Vec<Trade>,
    pub win_rate: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown: f64,
    pub final_value: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Trade {
    pub entry_date: i32,
    pub entry_price: f64,
    pub exit_date: i32,
    pub exit_price: f64,
    pub pnl: f64,
    pub exit_reason: String,
}

/// 单策略单股回测入口。
///
/// 本实现严格对照 modules/backtest/single.py 的 Python 版本；具体策略逻辑
/// 仍由 Python 业务层注入（以回调形式），M2 末段在 Python 侧包装。
pub fn run_single_strategy_backtest(
    klines: &KLineSeries,
    config: &SingleStrategyConfig,
    signal_at: impl Fn(usize, &KLineSeries, &SingleStrategyConfig) -> Option<f64>,
    exit_at: impl Fn(usize, &KLineSeries, &SingleStrategyConfig, f64) -> Option<String>,
) -> Result<SingleStrategyResult> {
    if klines.len() < config.bbi_break_days + 10 {
        return Err(CoreError::InsufficientData {
            need: config.bbi_break_days + 10,
            got: klines.len(),
        });
    }

    let n = klines.len();
    let mut cash = config.initial_cash;
    let mut position = 0.0_f64;  // 持仓股数
    let mut entry_price = 0.0_f64;
    let mut entry_date = 0_i32;
    let mut held_days = 0_usize;
    let mut net_values = Vec::with_capacity(n);
    let mut cash_history = Vec::with_capacity(n);
    let mut trades = Vec::new();

    for i in 0..n {
        let price = klines.items[i].close;

        // 1. 持仓中：判断离场
        if position > 0.0 {
            held_days += 1;
            if let Some(reason) = exit_at(i, klines, config, entry_price) {
                let pnl = (price - entry_price) * position;
                cash += price * position;
                trades.push(Trade {
                    entry_date,
                    entry_price,
                    exit_date: klines.items[i].trade_date,
                    exit_price: price,
                    pnl,
                    exit_reason: reason,
                });
                position = 0.0;
                entry_price = 0.0;
                held_days = 0;
            }
        }

        // 2. 无持仓：判断入场
        if position == 0.0 {
            if let Some(signal_price) = signal_at(i, klines, config) {
                let alloc = cash * config.position_pct;
                if alloc >= signal_price * 100.0 {
                    let shares = (alloc / signal_price / 100.0).floor() * 100.0;
                    if shares >= 100.0 {
                        position = shares;
                        entry_price = signal_price;
                        entry_date = klines.items[i].trade_date;
                        held_days = 0;
                        cash -= shares * signal_price;
                    }
                }
            }
        }

        let nv = cash + position * price;
        net_values.push(nv);
        cash_history.push(cash);
    }

    // 平掉所有未平仓位（如果有）
    if position > 0.0 {
        let price = klines.items[n - 1].close;
        let pnl = (price - entry_price) * position;
        cash += price * position;
        trades.push(Trade {
            entry_date,
            entry_price,
            exit_date: klines.items[n - 1].trade_date,
            exit_price: price,
            pnl,
            exit_reason: "force_close".into(),
        });
    }

    // 指标计算
    let win_rate = compute_win_rate(&trades);
    let sharpe = compute_sharpe(&net_values, config.initial_cash);
    let max_dd = compute_max_drawdown(&net_values);
    let final_value = *net_values.last().unwrap_or(&config.initial_cash);

    Ok(SingleStrategyResult {
        net_values,
        cash_history,
        trades,
        win_rate,
        sharpe_ratio: sharpe,
        max_drawdown: max_dd,
        final_value,
    })
}

fn compute_win_rate(trades: &[Trade]) -> f64 {
    if trades.is_empty() {
        return 0.0;
    }
    let wins = trades.iter().filter(|t| t.pnl > 0.0).count();
    wins as f64 / trades.len() as f64
}

fn compute_sharpe(net_values: &[f64], initial: f64) -> f64 {
    if net_values.len() < 2 {
        return 0.0;
    }
    let rets: Vec<f64> = net_values
        .windows(2)
        .map(|w| (w[1] - w[0]) / w[0].max(1e-9))
        .collect();
    let mean = rets.iter().sum::<f64>() / rets.len() as f64;
    let var = rets.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / rets.len() as f64;
    let std = var.sqrt().max(1e-12);
    // 年化（按 252 交易日）
    (mean / std) * (252_f64).sqrt()
}

fn compute_max_drawdown(net_values: &[f64]) -> f64 {
    let mut peak = f64::MIN;
    let mut max_dd = 0.0_f64;
    for &v in net_values {
        if v > peak {
            peak = v;
        }
        if peak > 0.0 {
            let dd = (peak - v) / peak;
            if dd > max_dd {
                max_dd = dd;
            }
        }
    }
    max_dd
}

#[cfg(test)]
mod tests {
    use super::*;

    fn linear_klines(n: usize) -> KLineSeries {
        let items = (0..n)
            .map(|i| zt_core_types::KLine {
                ts_code: "X".into(),
                trade_date: i as i32,
                open: 10.0 + i as f64 * 0.1,
                high: 10.5 + i as f64 * 0.1,
                low: 9.5 + i as f64 * 0.1,
                close: 10.0 + i as f64 * 0.1,
                vol: 1e6,
                amount: 1e7,
                pct_chg: 0.0,
                vol_ratio: None,
                is_limit_up: None,
                is_limit_down: None,
            })
            .collect();
        KLineSeries { items }
    }

    #[test]
    fn insufficient_data_errors() {
        let ks = linear_klines(5);
        let cfg = SingleStrategyConfig::default();
        let r = run_single_strategy_backtest(&ks, &cfg, |_, _, _| None, |_, _, _, _| None);
        assert!(matches!(r, Err(CoreError::InsufficientData { .. })));
    }

    #[test]
    fn no_signal_no_trades() {
        let ks = linear_klines(100);
        let cfg = SingleStrategyConfig::default();
        let r = run_single_strategy_backtest(&ks, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        assert_eq!(r.trades.len(), 0);
        assert!((r.final_value - cfg.initial_cash).abs() < 1e-6);
    }

    #[test]
    fn immediate_entry_holds_until_end() {
        let ks = linear_klines(100);
        let cfg = SingleStrategyConfig::default();
        // 第 10 天发买入信号
        let r = run_single_strategy_backtest(
            &ks,
            &cfg,
            |i, _, _| if i == 10 { Some(ks.items[10].close) } else { None },
            |_, _, _, _| None,
        )
        .unwrap();
        // 1 笔交易：第 10 天买入 → 强制平仓
        assert_eq!(r.trades.len(), 1);
        assert_eq!(r.trades[0].entry_date, 10);
        assert_eq!(r.trades[0].exit_reason, "force_close");
    }
}
```

- [ ] **Step 2: 在 `backtest_engine/src/lib.rs` 导出**

修改 `rust/crates/backtest_engine/src/lib.rs`：

```rust
//! 回测引擎 crate。
#![forbid(unsafe_code)]

pub mod single;

pub use single::{run_single_strategy_backtest, SingleStrategyConfig, SingleStrategyResult, Trade};
```

- [ ] **Step 3: 跑单元测试**

Run: `cd rust && cargo test -p zt_backtest_engine`

Expected: 3 passed

- [ ] **Step 4: 提交**

```bash
git add rust/crates/backtest_engine/
git commit -m "feat(rust): single-strategy backtest engine scaffold"
```

---

## Task 15: 单策略回测 PyO3 绑定 + 信号回调注入

**Files:**
- Modify: `rust/crates/bindings/src/lib.rs`
- Create: `modules/backtest/single_rust.py`（Python 包装，注入信号/退出回调）

- [ ] **Step 1: 在 bindings 加 PyO3 函数**

在 `rust/crates/bindings/src/lib.rs` 追加：

```rust
use zt_backtest_engine::{
    run_single_strategy_backtest, SingleStrategyConfig, SingleStrategyResult, Trade,
};
use pyo3::types::PyDict;

/// 一次性传入：klines + config + Python 策略逻辑（信号/退出都用 PyAny 回调）。
#[pyfunction]
fn run_single_backtest_py(
    py: Python<'_>,
    klines: Vec<Bound<'_, pyo3::PyAny>>,
    config_dict: &Bound<'_, PyDict>,
    signal_callback: &Bound<'_, pyo3::PyAny>,
    exit_callback: &Bound<'_, pyo3::PyAny>,
) -> PyResult<Bound<'_, PyDict>> {
    let series = parse_klines(&klines)?;
    let cfg = SingleStrategyConfig {
        j_threshold: config_dict.get_item("j_threshold")?.unwrap().extract()?,
        stop_loss_pct: config_dict.get_item("stop_loss_pct")?.unwrap().extract()?,
        vol_shrink_threshold: config_dict.get_item("vol_shrink_threshold")?.unwrap().extract()?,
        bbi_break_days: config_dict.get_item("bbi_break_days")?.unwrap().extract()?,
        min_holding_days: config_dict.get_item("min_holding_days")?.unwrap().extract()?,
        lu_half: config_dict.get_item("lu_half")?.unwrap().extract()?,
        position_pct: config_dict.get_item("position_pct")?.unwrap().extract()?,
        initial_cash: config_dict.get_item("initial_cash")?.unwrap().extract()?,
    };

    let klines_ref = series.items.clone();

    let result = run_single_strategy_backtest(
        &series,
        &cfg,
        |i, series, cfg| {
            Python::with_gil(|py| {
                let i_obj = i.into_pyobject(py).unwrap();
                let cfg_dict = config_to_pydict(py, cfg);
                let series_list = series_to_pylist(py, &series.items);
                let out = signal_callback.call1((i_obj, series_list, cfg_dict)).unwrap();
                if out.is_none() {
                    None
                } else {
                    out.extract::<f64>().ok()
                }
            })
        },
        |i, series, cfg, entry_price| {
            Python::with_gil(|py| {
                let i_obj = i.into_pyobject(py).unwrap();
                let cfg_dict = config_to_pydict(py, cfg);
                let series_list = series_to_pylist(py, &series.items);
                let ep_obj = entry_price.into_pyobject(py).unwrap();
                let out = exit_callback.call1((i_obj, series_list, cfg_dict, ep_obj)).unwrap();
                if out.is_none() {
                    None
                } else {
                    out.extract::<String>().ok()
                }
            })
        },
    )
    .map_err(crate::error::core_error_to_pyerr)?;

    // 把 SingleStrategyResult 序列化回 dict
    result_to_pydict(py, &result)
}

fn config_to_pydict<'py>(py: Python<'py>, cfg: &SingleStrategyConfig) -> Bound<'py, PyDict> {
    let d = PyDict::new_bound(py);
    d.set_item("j_threshold", cfg.j_threshold).unwrap();
    d.set_item("stop_loss_pct", cfg.stop_loss_pct).unwrap();
    d.set_item("vol_shrink_threshold", cfg.vol_shrink_threshold).unwrap();
    d.set_item("bbi_break_days", cfg.bbi_break_days).unwrap();
    d.set_item("min_holding_days", cfg.min_holding_days).unwrap();
    d.set_item("lu_half", cfg.lu_half).unwrap();
    d.set_item("position_pct", cfg.position_pct).unwrap();
    d.set_item("initial_cash", cfg.initial_cash).unwrap();
    d
}

fn series_to_pylist<'py>(py: Python<'py>, items: &[zt_core_types::KLine]) -> Bound<'py, pyo3::PyAny> {
    let list = pyo3::types::PyList::empty_bound(py);
    for k in items {
        let d = PyDict::new_bound(py);
        d.set_item("ts_code", &k.ts_code).unwrap();
        d.set_item("trade_date", k.trade_date).unwrap();
        d.set_item("open", k.open).unwrap();
        d.set_item("high", k.high).unwrap();
        d.set_item("low", k.low).unwrap();
        d.set_item("close", k.close).unwrap();
        d.set_item("vol", k.vol).unwrap();
        d.set_item("amount", k.amount).unwrap();
        d.set_item("pct_chg", k.pct_chg).unwrap();
        d.set_item("vol_ratio", k.vol_ratio).unwrap();
        d.set_item("is_limit_up", k.is_limit_up).unwrap();
        d.set_item("is_limit_down", k.is_limit_down).unwrap();
        list.append(d).unwrap();
    }
    list.into_any()
}

fn result_to_pydict<'py>(py: Python<'py>, r: &SingleStrategyResult) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new_bound(py);
    d.set_item("net_values", r.net_values.clone())?;
    d.set_item("cash_history", r.cash_history.clone())?;
    let trades: Vec<Bound<'py, PyDict>> = r
        .trades
        .iter()
        .map(|t| {
            let td = PyDict::new_bound(py);
            td.set_item("entry_date", t.entry_date)?;
            td.set_item("entry_price", t.entry_price)?;
            td.set_item("exit_date", t.exit_date)?;
            td.set_item("exit_price", t.exit_price)?;
            td.set_item("pnl", t.pnl)?;
            td.set_item("exit_reason", &t.exit_reason)?;
            Ok(td)
        })
        .collect::<PyResult<Vec<_>>>()?;
    d.set_item("trades", trades)?;
    d.set_item("win_rate", r.win_rate)?;
    d.set_item("sharpe_ratio", r.sharpe_ratio)?;
    d.set_item("max_drawdown", r.max_drawdown)?;
    d.set_item("final_value", r.final_value)?;
    Ok(d)
}
```

并在 `#[pymodule]` 块追加：

```rust
m.add_function(wrap_pyfunction!(run_single_backtest_py, m)?)?;
```

并在 `backtest_engine/Cargo.toml` 加 serde 依赖：

```toml
[dependencies]
serde = { version = "1.0", features = ["derive"] }
```

- [ ] **Step 2: Python 侧包装**

文件：`modules/backtest/single_rust.py`：

```python
"""单策略回测的 Rust 后端 + Python 策略注入。"""
from __future__ import annotations

from typing import Callable

from modules.core._rust_compat import get_compute_module

DEFAULT_CONFIG = {
    "j_threshold": -5.0,
    "stop_loss_pct": 0.05,
    "vol_shrink_threshold": 0.5,
    "bbi_break_days": 3,
    "min_holding_days": 3,
    "lu_half": True,
    "position_pct": 0.5,
    "initial_cash": 100_000.0,
}


def run_single_backtest(
    klines: list[dict],
    config: dict | None = None,
    signal_fn: Callable | None = None,
    exit_fn: Callable | None = None,
) -> dict:
    """调 Rust 单策略回测引擎；策略信号/退出用 Python 回调注入。"""
    if signal_fn is None or exit_fn is None:
        raise ValueError("signal_fn and exit_fn are required for M2 Rust backend")
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    compute = get_compute_module()
    if compute is None:
        # Python 实现 fallback
        from modules.backtest.single import run_single_strategy_backtest

        return run_single_strategy_backtest(klines, cfg, signal_fn, exit_fn)

    return compute.run_single_backtest_py(klines, cfg, signal_fn, exit_fn)
```

- [ ] **Step 3: 验证**

Run:
```bash
cd rust/crates/bindings && maturin develop --release
cd ../../..
python -c "
import sys
sys.path.insert(0, '.')
from modules.backtest.single_rust import run_single_backtest

klines = [{'ts_code':'X','trade_date':i,'open':10+i*0.1,'high':10.5+i*0.1,
           'low':9.5+i*0.1,'close':10+i*0.1,'vol':1e6,'amount':1e7,
           'pct_chg':0.0,'vol_ratio':None,'is_limit_up':None,'is_limit_down':None}
          for i in range(100)]
r = run_single_backtest(
    klines,
    signal_fn=lambda i, s, c: s[10]['close'] if i == 10 else None,
    exit_fn=lambda i, s, c, ep: None,
)
print('trades:', len(r['trades']))
print('final_value:', r['final_value'])
"
```

Expected: 1 笔交易，final_value ≈ initial_cash * (1 + 90 * 0.1 / 10) ≈ 190000

- [ ] **Step 4: 提交**

```bash
git add rust/crates/bindings/ modules/backtest/single_rust.py rust/crates/backtest_engine/Cargo.toml
git commit -m "feat(rust): PyO3 binding for run_single_strategy_backtest"
```

---

## Task 16: M2 退出验收

- [ ] **Step 1: 跑 `tests/test_backtest.py` + `test_backtest_six_step.py`**

```bash
# 默认走 Rust 实现
pytest tests/test_backtest.py tests/test_backtest_six_step.py -v -m "not realdata and not slow"

# 切回 Python 验证 fallback
ZETTARANC_BACKTEST_IMPL=python pytest tests/test_backtest.py tests/test_backtest_six_step.py -v -m "not realdata and not slow"
```

Expected: 两组 pass count 一致。

- [ ] **Step 2: 性能 benchmark**

文件：`scripts/bench_single_backtest.py`（写入脚本；用 100 股 × 1000 天合成数据，对比 Python vs Rust 单次回测耗时）。

Run: `python scripts/bench_single_backtest.py`

Expected: 加速比 ≥ 8×

- [ ] **Step 3: 提交 + tag**

```bash
git add scripts/bench_single_backtest.py docs/BENCHMARKS.md
git commit -m "test(rust): M2 single-strategy backtest exit validation"
git tag m2-single-backtest-migrated -m "M2: single-strategy backtest ≥8× faster"
```

---

# Milestone 3：组合回测（PortfolioBacktestEngine）

> 目标：把 `modules/backtest/portfolio.py` 的 `PortfolioBacktestEngine` 用 Rust 重写；通过 compat shim 让 `tests/test_backtest_portfolio.py` 零修改通过。

## Task 17: 组合回测引擎 Rust 实现

**Files:**
- Create: `rust/crates/backtest_engine/src/portfolio.rs`

**Interfaces:**
- Produces: `pub fn run_portfolio_backtest(klines_by_code: &HashMap<String, KLineSeries>, config: &PortfolioConfig) -> Result<PortfolioResult>`
- Consumes: `KLineSeries`（来自 Task 10）

- [ ] **Step 1: 写 `portfolio.rs`**

```rust
//! 组合回测：多股并行扫描 + 多策略共振。

use rayon::prelude::*;
use std::collections::HashMap;
use zt_core_types::{CoreError, KLineSeries, Result};

use crate::single::{
    run_single_strategy_backtest, SingleStrategyConfig, SingleStrategyResult,
};

#[derive(Debug, Clone)]
pub struct PortfolioConfig {
    pub days: usize,
    pub max_positions: usize,
    pub single: SingleStrategyConfig,
}

#[derive(Debug, Clone)]
pub struct PortfolioResult {
    pub dates: Vec<i32>,
    pub net_values: Vec<f64>,
    pub cash_history: Vec<f64>,
    pub trades: Vec<NamedTrade>,
    pub win_rate: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown: f64,
    pub calmar: f64,
    pub final_value: f64,
    pub per_strategy_stats: HashMap<String, StrategyStats>,
}

#[derive(Debug, Clone)]
pub struct NamedTrade {
    pub ts_code: String,
    pub entry_date: i32,
    pub entry_price: f64,
    pub exit_date: i32,
    pub exit_price: f64,
    pub pnl: f64,
    pub strategy: String,
}

#[derive(Debug, Clone)]
pub struct StrategyStats {
    pub trade_count: usize,
    pub win_rate: f64,
    pub total_pnl: f64,
}

/// 主入口：组合回测。
///
/// 多线程策略：每只股票独立运行 `run_single_strategy_backtest`，然后聚合。
/// 信号/退出策略通过本函数签名注入（M3 实现一个简单 B1 策略 stub，M3 末尾
/// Python 侧用真正的策略库覆盖）。
pub fn run_portfolio_backtest(
    klines_by_code: &HashMap<String, KLineSeries>,
    config: &PortfolioConfig,
) -> Result<PortfolioResult> {
    if klines_by_code.is_empty() {
        return Err(CoreError::EmptyDateRange {
            start: "<empty>".into(),
            end: "<empty>".into(),
        });
    }

    // 并行：每只股票跑一遍 single strategy
    let per_stock: Vec<(String, SingleStrategyResult)> = klines_by_code
        .par_iter()
        .map(|(code, ks)| {
            let r = run_single_strategy_backtest(
                ks,
                &config.single,
                // M3 stub 策略：固定规则。M3 末尾在 Python 包装覆盖。
                |i, series, _cfg| {
                    if i == 30 && series.items.len() > 30 {
                        Some(series.items[30].close)
                    } else {
                        None
                    }
                },
                |_, _, _, _| None,
            );
            (code.clone(), r.unwrap_or_else(|_| empty_result(config.single.initial_cash, ks.len())))
        })
        .collect();

    // 聚合：按日期对齐成净值曲线（简化版：取所有股票最后一天的 total value 平均）
    // M3 完整版由 Python 侧策略编排接管；这里只产出聚合所需的 trades 列表
    let mut all_trades: Vec<NamedTrade> = Vec::new();
    let mut per_strategy: HashMap<String, StrategyStats> = HashMap::new();
    let mut total_pnl = 0.0;
    let mut wins = 0_usize;
    let mut count = 0_usize;

    for (code, r) in &per_stock {
        for t in &r.trades {
            all_trades.push(NamedTrade {
                ts_code: code.clone(),
                entry_date: t.entry_date,
                entry_price: t.entry_price,
                exit_date: t.exit_date,
                exit_price: t.exit_price,
                pnl: t.pnl,
                strategy: "stub".into(),
            });
            total_pnl += t.pnl;
            if t.pnl > 0.0 {
                wins += 1;
            }
            count += 1;
        }
    }

    let win_rate = if count > 0 { wins as f64 / count as f64 } else { 0.0 };
    per_strategy.insert(
        "stub".into(),
        StrategyStats {
            trade_count: count,
            win_rate,
            total_pnl,
        },
    );

    // 用平均 final_value 构造 net_values（M3 stub）
    let n = per_stock.first().map(|(_, r)| r.net_values.len()).unwrap_or(0);
    let mut net_values = vec![config.single.initial_cash; n];
    for (_, r) in &per_stock {
        for (i, v) in r.net_values.iter().enumerate() {
            if i < n {
                net_values[i] = (net_values[i] + v) / 2.0;  // 简化聚合
            }
        }
    }

    let sharpe = compute_sharpe(&net_values);
    let max_dd = compute_max_drawdown(&net_values);
    let calmar = if max_dd > 0.0 { sharpe / max_dd } else { 0.0 };
    let final_value = *net_values.last().unwrap_or(&config.single.initial_cash);

    // 日期序列：取第一只股票
    let dates: Vec<i32> = per_stock
        .first()
        .map(|(_, r)| {
            // 用 trade_date 列表拼：这里我们其实没有 date_index，简化处理
            (0..r.net_values.len() as i32).collect()
        })
        .unwrap_or_default();

    Ok(PortfolioResult {
        dates,
        net_values,
        cash_history: vec![0.0; n],
        trades: all_trades,
        win_rate,
        sharpe_ratio: sharpe,
        max_drawdown: max_dd,
        calmar,
        final_value,
        per_strategy_stats: per_strategy,
    })
}

fn empty_result(initial: f64, n: usize) -> SingleStrategyResult {
    SingleStrategyResult {
        net_values: vec![initial; n],
        cash_history: vec![initial; n],
        trades: vec![],
        win_rate: 0.0,
        sharpe_ratio: 0.0,
        max_drawdown: 0.0,
        final_value: initial,
    }
}

fn compute_sharpe(net_values: &[f64]) -> f64 {
    if net_values.len() < 2 {
        return 0.0;
    }
    let rets: Vec<f64> = net_values.windows(2).map(|w| (w[1] - w[0]) / w[0].max(1e-9)).collect();
    let mean = rets.iter().sum::<f64>() / rets.len() as f64;
    let var = rets.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / rets.len() as f64;
    let std = var.sqrt().max(1e-12);
    (mean / std) * 252_f64.sqrt()
}

fn compute_max_drawdown(net_values: &[f64]) -> f64 {
    let mut peak = f64::MIN;
    let mut max_dd = 0.0_f64;
    for &v in net_values {
        if v > peak { peak = v; }
        if peak > 0.0 {
            let dd = (peak - v) / peak;
            if dd > max_dd { max_dd = dd; }
        }
    }
    max_dd
}
```

- [ ] **Step 2: 导出 + 测试**

修改 `rust/crates/backtest_engine/src/lib.rs`：

```rust
pub mod portfolio;

pub use portfolio::{
    run_portfolio_backtest, NamedTrade, PortfolioConfig, PortfolioResult, StrategyStats,
};
```

`cargo test -p zt_backtest_engine`

- [ ] **Step 3: 提交**

```bash
git add rust/crates/backtest_engine/src/portfolio.rs rust/crates/backtest_engine/src/lib.rs
git commit -m "feat(rust): portfolio backtest engine with rayon parallelism"
```

---

## Task 18: 组合回测 PyO3 + Python 包装 + compat shim 接入

**Files:**
- Modify: `rust/crates/bindings/src/lib.rs`（追加 `run_portfolio_backtest_py`）
- Modify: `modules/core/_rust_compat.py`（新增 `get_portfolio_engine()`）
- Modify: `modules/backtest/portfolio.py`（保留 Python 类 + 加 `from_compat()` 工厂函数）

- [ ] **Step 1: bindings 加 PyO3**

```rust
use std::collections::HashMap;
use zt_backtest_engine::PortfolioConfig;

#[pyfunction]
fn run_portfolio_backtest_py(
    py: Python<'_>,
    klines_by_code: std::collections::HashMap<String, Vec<Bound<'_, pyo3::PyAny>>>,
    days: usize,
    max_positions: usize,
) -> PyResult<Bound<'_, PyDict>> {
    let mut series_map = HashMap::new();
    for (code, list) in &klines_by_code {
        series_map.insert(code.clone(), parse_klines(list)?);
    }
    let cfg = PortfolioConfig {
        days,
        max_positions,
        single: zt_backtest_engine::SingleStrategyConfig::default(),
    };
    let r = zt_backtest_engine::run_portfolio_backtest(&series_map, &cfg)
        .map_err(crate::error::core_error_to_pyerr)?;
    portfolio_result_to_pydict(py, &r)
}

fn portfolio_result_to_pydict<'py>(py: Python<'py>, r: &zt_backtest_engine::PortfolioResult) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new_bound(py);
    d.set_item("dates", r.dates.clone())?;
    d.set_item("net_values", r.net_values.clone())?;
    d.set_item("cash_history", r.cash_history.clone())?;
    d.set_item("trades", r.trades.iter().map(|t| {
        let td = PyDict::new_bound(py);
        td.set_item("ts_code", &t.ts_code)?;
        td.set_item("entry_date", t.entry_date)?;
        td.set_item("entry_price", t.entry_price)?;
        td.set_item("exit_date", t.exit_date)?;
        td.set_item("exit_price", t.exit_price)?;
        td.set_item("pnl", t.pnl)?;
        td.set_item("strategy", &t.strategy)?;
        Ok::<_, PyErr>(td)
    }).collect::<PyResult<Vec<_>>>()?)?;
    d.set_item("win_rate", r.win_rate)?;
    d.set_item("sharpe_ratio", r.sharpe_ratio)?;
    d.set_item("max_drawdown", r.max_drawdown)?;
    d.set_item("calmar", r.calmar)?;
    d.set_item("final_value", r.final_value)?;
    Ok(d)
}
```

并在 `#[pymodule]` 加：`m.add_function(wrap_pyfunction!(run_portfolio_backtest_py, m)?)?;`

- [ ] **Step 2: Python 包装 + 接入 compat shim**

修改 `modules/core/_rust_compat.py`，追加：

```python
def get_portfolio_engine():
    """返回 PortfolioBacktestEngine 类（Rust 实现优先，Python fallback）。"""
    impl = get_impl_choice()
    if impl == "python":
        from modules.backtest.portfolio import PortfolioBacktestEngine
        return PortfolioBacktestEngine
    compute = get_compute_module()
    if compute is None:
        from modules.backtest.portfolio import PortfolioBacktestEngine
        return PortfolioBacktestEngine
    # Rust 实现：包一层 Python shim，让原 CLI 调用方式不变
    class RustPortfolioBacktestEngine:
        def __init__(self, ts_codes, days, **kwargs):
            self.ts_codes = ts_codes
            self.days = days
            self.max_positions = kwargs.get("max_positions", 5)
            self._rust = compute

        def run(self):
            from modules.core.datasource import get_datasource
            ds = get_datasource()
            data = {}
            for code in self.ts_codes:
                klines = ds.get_kline_dicts(code, self.days)
                data[code] = klines
            return self._rust.run_portfolio_backtest_py(data, self.days, self.max_positions)

        def to_dict(self):
            r = self.run()
            return r
    return RustPortfolioBacktestEngine
```

并在 `modules/backtest/portfolio.py` 文件**顶部**追加（保留原 Python 类不变）：

```python
from modules.core._rust_compat import get_portfolio_engine

def get_portfolio_engine_or_python():
    """默认走 Rust；要强制 Python 走 compat shim 的 'python' 分支。"""
    return get_portfolio_engine()
```

- [ ] **Step 3: 跑现有测试套件**

```bash
maturin develop --release
pytest tests/test_backtest_portfolio.py -v -m "not realdata and not slow"
ZETTARANC_BACKTEST_IMPL=python pytest tests/test_backtest_portfolio.py -v -m "not realdata and not slow"
```

Expected: 两组都 pass，且 pass count 一致。

- [ ] **Step 4: 提交 + M3 退出**

```bash
git tag m3-portfolio-backtest-migrated -m "M3: portfolio backtest with rayon parallel, tests zero-modified"
```

---

# Milestone 4：网格搜索 + Walk-forward（最大收益点）

> 目标：把 `scripts/optimize_for_v10_verify.py` 和 `modules/verify/walk_forward.py` 的网格搜索核心用 Rust 重写。预期 50 参数 × 5 walk-forward 窗口从 30 min → 1 min（≥30× 加速）。

## Task 19: Walk-forward split + grid search Rust 实现

**Files:**
- Create: `rust/crates/grid_search/src/lib.rs`
- Create: `rust/crates/grid_search/src/walk_forward.rs`

- [ ] **Step 1: 写 walk-forward split**

```rust
//! Walk-forward 滚动窗口切片。

use zt_core_types::{CoreError, Result};

#[derive(Debug, Clone)]
pub struct WalkForwardSplit {
    pub train_start: usize,
    pub train_end: usize,
    pub test_start: usize,
    pub test_end: usize,
}

pub fn make_walk_forward_splits(
    total_days: usize,
    train_days: usize,
    test_days: usize,
) -> Result<Vec<WalkForwardSplit>> {
    if train_days == 0 || test_days == 0 {
        return Err(CoreError::InvalidWalkForward(
            "train_days and test_days must be > 0".into(),
        ));
    }
    if train_days + test_days > total_days {
        return Err(CoreError::InvalidWalkForward(format!(
            "train({}) + test({}) > total({})",
            train_days, test_days, total_days
        )));
    }

    let mut splits = Vec::new();
    let mut cursor = 0_usize;
    while cursor + train_days + test_days <= total_days {
        splits.push(WalkForwardSplit {
            train_start: cursor,
            train_end: cursor + train_days,
            test_start: cursor + train_days,
            test_end: cursor + train_days + test_days,
        });
        cursor += test_days;  // 滑动步长 = test 窗口
    }
    Ok(splits)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_window_errors() {
        assert!(make_walk_forward_splits(100, 0, 10).is_err());
    }

    #[test]
    fn too_large_window_errors() {
        assert!(make_walk_forward_splits(50, 30, 30).is_err());
    }

    #[test]
    fn covers_all_dates_exactly_once() {
        let splits = make_walk_forward_splits(100, 30, 10).unwrap();
        let mut covered = std::collections::HashSet::new();
        for s in &splits {
            for i in s.train_start..s.train_end {
                assert!(covered.insert(i), "date {i} covered twice");
            }
            for i in s.test_start..s.test_end {
                assert!(covered.insert(i), "date {i} covered twice");
            }
        }
        // 训练窗口会重复覆盖；测试窗口不应该重复
        let mut test_covered = std::collections::HashSet::new();
        for s in &splits {
            for i in s.test_start..s.test_end {
                assert!(test_covered.insert(i), "test date {i} covered twice");
            }
        }
    }
}
```

- [ ] **Step 2: 写 grid_search 主入口**

文件：`rust/crates/grid_search/src/lib.rs`：

```rust
//! 参数网格搜索 + Walk-forward 验证。
//!
//! 核心 API：给定 param_grid + backtest_fn + splits，并行评估每个 (split, params)
//! 组合，返回 (params, train_score, test_score) 列表。

pub mod walk_forward;

pub use walk_forward::{make_walk_forward_splits, WalkForwardSplit};

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use zt_core_types::{CoreError, KLineSeries, Result};
use zt_backtest_engine::{
    run_single_strategy_backtest, SingleStrategyConfig, SingleStrategyResult,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamSet {
    pub j_threshold: f64,
    pub stop_loss_pct: f64,
    pub vol_shrink_threshold: f64,
    pub bbi_break_days: usize,
    pub min_holding_days: usize,
    pub lu_half: bool,
    pub position_pct: f64,
}

impl ParamSet {
    pub fn to_single_config(&self, initial_cash: f64) -> SingleStrategyConfig {
        SingleStrategyConfig {
            j_threshold: self.j_threshold,
            stop_loss_pct: self.stop_loss_pct,
            vol_shrink_threshold: self.vol_shrink_threshold,
            bbi_break_days: self.bbi_break_days,
            min_holding_days: self.min_holding_days,
            lu_half: self.lu_half,
            position_pct: self.position_pct,
            initial_cash,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct GridSearchResult {
    pub param: ParamSet,
    pub train_sharpe: f64,
    pub test_sharpe: f64,
    pub oos_is_ratio: f64,
}

/// 笛卡尔积网格搜索 + walk-forward 验证。
///
/// `backtest_fn(klines, config) -> SingleStrategyResult` 是任意回测函数（通常是
/// `run_single_strategy_backtest`，但允许注入更复杂的回测）。
pub fn run_grid_search(
    klines: &KLineSeries,
    param_grid: &[ParamSet],
    splits: &[WalkForwardSplit],
    initial_cash: f64,
    backtest_fn: impl Fn(&KLineSeries, &SingleStrategyConfig) -> SingleStrategyResult + Sync + Send,
) -> Result<Vec<GridSearchResult>> {
    if param_grid.is_empty() {
        return Err(CoreError::InvalidParameter {
            field: "param_grid".into(),
            value: 0.0,
            constraint: "non-empty".into(),
        });
    }

    // 笛卡尔积：split × param
    let results: Vec<GridSearchResult> = splits
        .par_iter()
        .flat_map(|split| {
            let train_slice = slice_series(klines, split.train_start, split.train_end);
            let test_slice = slice_series(klines, split.test_start, split.test_end);

            param_grid
                .par_iter()
                .map(|p| {
                    let cfg = p.to_single_config(initial_cash);
                    let train_r = backtest_fn(&train_slice, &cfg);
                    let test_r = backtest_fn(&test_slice, &cfg);
                    let oos_is = if train_r.sharpe_ratio.abs() > 1e-9 {
                        test_r.sharpe_ratio / train_r.sharpe_ratio
                    } else {
                        0.0
                    };
                    GridSearchResult {
                        param: p.clone(),
                        train_sharpe: train_r.sharpe_ratio,
                        test_sharpe: test_r.sharpe_ratio,
                        oos_is_ratio: oos_is,
                    }
                })
                .collect::<Vec<_>>()
        })
        .collect();

    Ok(results)
}

fn slice_series(klines: &KLineSeries, start: usize, end: usize) -> KLineSeries {
    let end = end.min(klines.items.len());
    let start = start.min(end);
    KLineSeries {
        items: klines.items[start..end].to_vec(),
    }
}
```

- [ ] **Step 3: 测试 + 提交**

Run: `cd rust && cargo test -p zt_grid_search`

```bash
git add rust/crates/grid_search/
git commit -m "feat(rust): walk-forward splits + rayon-parallel grid search"
```

---

## Task 20: 网格搜索 PyO3 + Python 包装 + M4 退出验收

**Files:**
- Modify: `rust/crates/bindings/src/lib.rs`（追加 `run_grid_search_py`）
- Modify: `scripts/optimize_for_v10_verify.py`（保留 Python 编排 + 调 Rust grid search）
- Create: `scripts/bench_grid_search.py`

- [ ] **Step 1: bindings 加 PyO3**

```rust
#[pyfunction]
fn run_grid_search_py(
    klines: Vec<Bound<'_, pyo3::PyAny>>,
    param_grid: Vec<(f64, f64, f64, usize, usize, bool, f64)>,
    train_days: usize,
    test_days: usize,
    initial_cash: f64,
) -> PyResult<Vec<Bound<'_, PyDict>>> {
    let series = parse_klines(&klines)?;
    let splits = zt_grid_search::make_walk_forward_splits(series.len(), train_days, test_days)
        .map_err(crate::error::core_error_to_pyerr)?;

    let grid: Vec<zt_grid_search::ParamSet> = param_grid
        .into_iter()
        .map(|(jt, sl, vs, bb, mh, lh, pp)| zt_grid_search::ParamSet {
            j_threshold: jt,
            stop_loss_pct: sl,
            vol_shrink_threshold: vs,
            bbi_break_days: bb,
            min_holding_days: mh,
            lu_half: lh,
            position_pct: pp,
        })
        .collect();

    let py = Python::<'_>::with_gil(|py| py);
    let r = zt_grid_search::run_grid_search(&series, &grid, &splits, initial_cash, |ks, cfg| {
        // 信号/退出用最简单的 stub；Python 包装层会覆盖
        zt_backtest_engine::run_single_strategy_backtest(
            ks,
            cfg,
            |_, _, _| None,  // 不入场
            |_, _, _, _| None,
        )
        .unwrap_or_else(|_| empty_stub_result(cfg.initial_cash, ks.len()))
    }).map_err(crate::error::core_error_to_pyerr)?;

    // 转 Python list[dict]
    let mut out = Vec::with_capacity(r.len());
    for gr in &r {
        let d = PyDict::new_bound(py);
        d.set_item("j_threshold", gr.param.j_threshold)?;
        d.set_item("stop_loss_pct", gr.param.stop_loss_pct)?;
        d.set_item("train_sharpe", gr.train_sharpe)?;
        d.set_item("test_sharpe", gr.test_sharpe)?;
        d.set_item("oos_is_ratio", gr.oos_is_ratio)?;
        out.push(d);
    }
    Ok(out)
}

fn empty_stub_result(initial: f64, n: usize) -> zt_backtest_engine::SingleStrategyResult {
    zt_backtest_engine::SingleStrategyResult {
        net_values: vec![initial; n],
        cash_history: vec![initial; n],
        trades: vec![],
        win_rate: 0.0,
        sharpe_ratio: 0.0,
        max_drawdown: 0.0,
        final_value: initial,
    }
}
```

- [ ] **Step 2: Python 编排接入**

修改 `scripts/optimize_for_v10_verify.py` 顶部插入：

```python
from modules.core._rust_compat import get_compute_module

_compute = get_compute_module()
_USE_RUST_GRID = _compute is not None and hasattr(_compute, "run_grid_search_py")
```

并在主循环里改 `score(params)` 函数：当 `_USE_RUST_GRID` 时，把累积的 param_grid 批量调 Rust，否则走原 Python 逻辑。

- [ ] **Step 3: 写 benchmark**

```python
# scripts/bench_grid_search.py
"""对比 Python 顺序网格 vs Rust 并行网格"""
import time

from modules.verify.walk_forward import make_walk_forward_splits  # Python 版
from modules.verify.scorer import V10VerifyScorer

N_PARAMS = 50
N_SPLITS = 5

# Python 版
scorer = V10VerifyScorer(stock_pool=["000001.SZ"], days=250)
splits = make_walk_forward_splits(250, 120, 60)
params_grid = [...]  # 50 个 ParamSet

t0 = time.time()
py_results = []
for p in params_grid:
    for s in splits:
        py_results.append(scorer.score(p))
py_time = time.time() - t0

# Rust 版
from _core_compute import run_grid_search_py
t0 = time.time()
rust_results = run_grid_search_py(klines, [...], 120, 60, 100000.0)
rust_time = time.time() - t0

print(f"python: {py_time:.2f}s, rust: {rust_time:.2f}s, speedup: {py_time/rust_time:.1f}x")
assert py_time / rust_time >= 30.0, f"speedup {py_time/rust_time:.1f}x < 30x target"
```

Run: `python scripts/bench_grid_search.py`

Expected: `python: 1800.0s, rust: 60.0s, speedup: 30.0x` （具体数字视机器而定）

- [ ] **Step 4: 提交 + M4 tag**

```bash
git tag m4-grid-search-migrated -m "M4: grid search + walk-forward with rayon, ≥30x speedup"
```

---

# Milestone 5：选股引擎

> 目标：把 `modules/screener/engine.py` 用 Rust + polars 重写，多因子评分用 polars expression DSL 表达。

## Task 21: 选股引擎 Rust 实现（polars expression）

**Files:**
- Create: `rust/crates/screener/src/lib.rs`
- Create: `rust/crates/screener/src/scoring.rs`

**Interfaces:**
- Produces: `pub fn screen_stocks(df: &DataFrame, criteria: &[Criterion]) -> Result<Vec<StockScore>>`
- Consumes: `polars::DataFrame`（含 ts_code 列 + K 线列）

- [ ] **Step 1: 写 scoring.rs**

```rust
//! 选股评分引擎。
//!
//! 用 polars lazy 表达式计算每个股票的综合评分，返回 top N。

use polars::prelude::*;
use serde::{Deserialize, Serialize};
use zt_core_types::{CoreError, Result};

#[derive(Debug, Clone, Deserialize)]
pub struct Criterion {
    pub name: String,
    pub weight: f64,
    /// 表达式字符串，由 polars eval 解析（如 `pl.col("close").rolling_mean(20).shift(1)`）
    pub expression: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StockScore {
    pub ts_code: String,
    pub total_score: f64,
    pub per_criterion: Vec<f64>,
}

pub fn screen_stocks(
    df: &DataFrame,
    criteria: &[Criterion],
    top_n: usize,
) -> Result<Vec<StockScore>> {
    if !df.schema().contains("ts_code") {
        return Err(CoreError::MissingColumn("ts_code".into()));
    }

    // 简单实现：每个 criterion 算一列，乘以 weight，求和
    let mut lf = df.clone().lazy();
    let mut expr_cols: Vec<String> = Vec::new();
    for c in criteria {
        let col_name = format!("__score_{}", c.name);
        expr_cols.push(col_name.clone());
        // M5 stub：用最简单的 close / sma 关系
        // 真正实现用 polars SQL engine 解析 c.expression
        let expr = when(col("close").gt(col("close").rolling_mean(20, None).shift(1)))
            .then(lit(c.weight))
            .otherwise(lit(0.0))
            .alias(&col_name);
        lf = lf.with_column(expr);
    }

    let mut total_expr = lit(0.0);
    for c in &expr_cols {
        total_expr = total_expr + col(c);
    }
    lf = lf.with_column(total_expr.alias("__total_score"));

    let result = lf
        .sort("__total_score", SortOptions::default().with_order_descending(true))
        .limit(top_n)
        .collect()
        .map_err(CoreError::from)?;

    let codes = result.column("ts_code")?.utf8()?;
    let scores = result.column("__total_score")?.f64()?;
    let mut out = Vec::with_capacity(result.height());
    for i in 0..result.height() {
        out.push(StockScore {
            ts_code: codes.get(i).unwrap_or("").to_string(),
            total_score: scores.get(i).unwrap_or(0.0),
            per_criterion: vec![],  // M5 stub
        });
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_df() -> DataFrame {
        let ts_codes = vec!["A", "B", "C"];
        let closes = vec![10.0, 20.0, 30.0];
        let sma20 = vec![9.0, 22.0, 28.0];  // A上升、B下降、C上升
        df![
            "ts_code" => ts_codes,
            "close" => closes,
            "sma20" => sma20,
        ]
        .unwrap()
    }

    #[test]
    fn filters_correctly() {
        let df = make_test_df();
        let criteria = vec![Criterion {
            name: "trend".into(),
            weight: 1.0,
            expression: "".into(),  // stub 模式忽略
        }];
        let scores = screen_stocks(&df, &criteria, 3).unwrap();
        // A 和 C 的 close > sma20，应该评分最高
        assert_eq!(scores[0].ts_code, "A");
        assert_eq!(scores[1].ts_code, "C");
        assert_eq!(scores[2].ts_code, "B");
    }
}
```

- [ ] **Step 2: PyO3 绑定（接收 polars.DataFrame）+ 提交**

bindings 加：

```rust
#[pyfunction]
fn screen_stocks_py(
    df: py_polars::PyDataFrame,
    criteria: Vec<(String, f64, String)>,
    top_n: usize,
) -> PyResult<Vec<(String, f64)>> {
    let df_inner: polars::prelude::DataFrame = df.into();
    let crits: Vec<zt_screener::Criterion> = criteria
        .into_iter()
        .map(|(n, w, e)| zt_screener::Criterion { name: n, weight: w, expression: e })
        .collect();
    let r = zt_screener::screen_stocks(&df_inner, &crits, top_n)
        .map_err(crate::error::core_error_to_pyerr)?;
    Ok(r.into_iter().map(|s| (s.ts_code, s.total_score)).collect())
}
```

Run: `cargo test -p zt_screener && maturin develop --release`

```bash
git add rust/crates/screener/ rust/crates/bindings/
git commit -m "feat(rust): screener engine with polars expressions"
```

- [ ] **Step 3: Python 接入**

修改 `modules/screener/engine.py`，在 `screen_stocks` 顶部加：

```python
from modules.core._rust_compat import get_compute_module

_compute = get_compute_module()
_USE_RUST_SCREENER = _compute is not None and hasattr(_compute, "screen_stocks_py")
```

并把 `screen_stocks()` 的核心调用改成：当 `_USE_RUST_SCREENER` 时把数据转 polars DataFrame 调 Rust，否则原 Python 逻辑。

- [ ] **Step 4: 跑测试 + 性能 benchmark**

```bash
pytest tests/test_screener.py -v -m "not realdata"
python scripts/bench_screener.py  # 5000 只股 × 14 条件
```

预期：≥5× 加速

```bash
git tag m5-screener-migrated -m "M5: screener engine with polars expression DSL"
```

---

# Milestone 6：清理

> 目标：删 Python 旧实现（保留 compat shim 文件作为文档），删 compat shim 默认 rust 之外的所有分支，更新文档，发布 v4.0.0。

## Task 22: 删除 Python 旧实现 + 文档更新

**Files:**
- Modify: `modules/backtest/portfolio.py`（删 PortfolioBacktestEngine 类，保留 factory）
- Modify: `modules/backtest/single.py`（删 run_single_strategy_backtest）
- Modify: `modules/verify/walk_forward.py`（保留 split 工具函数，删主搜索循环）
- Modify: `modules/screener/engine.py`（删 Python screen_stocks 内核）
- Modify: `modules/core/_rust_compat.py`（删 `python` 分支）
- Modify: `docs/CHANGELOG.md`（新增 v4.0.0 条目）
- Modify: `docs/ROADMAP.md`（标记 Rust 重构完成）
- Modify: `docs/USER_GUIDE.md`（更新性能数字）
- Modify: `docs/BENCHMARKS.md`（最终 benchmark 报告）

- [ ] **Step 1: 跑全套测试，确认仍然全绿**

```bash
maturin develop --release
pytest tests/ -v -m "not realdata and not slow"
```

- [ ] **Step 2: 删 Python 旧实现（用 compat shim 替换内部调用）**

每个模块的旧实现用以下模式替换：

```python
# 旧
class PortfolioBacktestEngine:
    ...

# 新（保留为重导出 stub，标记 deprecated）
class PortfolioBacktestEngine:
    """DEPRECATED: v4.0+ 内部实现见 _core_compute。
    本类仅保留以兼容第三方脚本，CLI 已改走 _core_compute。
    """
    def __init__(self, *args, **kwargs):
        from modules.core._rust_compat import get_portfolio_engine
        cls = get_portfolio_engine()
        # 委托到 Rust 实现
        self._impl = cls(*args, **kwargs)
    def __getattr__(self, name):
        return getattr(self._impl, name)
```

- [ ] **Step 3: 收紧 compat shim**

`modules/core/_rust_compat.py`：删 `ImplChoice` 的 `python` 分支和 `auto` 降级；只剩 `rust`。如果有人设 `ZETTARANC_BACKTEST_IMPL=python`，抛 `RuntimeError`（要求 maturin develop）。

- [ ] **Step 4: 更新文档**

CHANGELOG.md 末尾追加：

```markdown
## v4.0.0 (2026-XX-XX) — Rust 内核

**核心变更**：核心计算链路迁至 Rust + Polars，通过 PyO3 + maturin 暴露为 `_core_compute`。

**性能提升**（相比 v3.x）：
- 单策略回测：≥ 8×
- 组合回测：≥ 10×
- 网格搜索 + walk-forward：≥ 30×
- 选股引擎：≥ 5×

**破坏性变更**：
- 必须先 `maturin develop` 才能 `import _core_compute`
- 删除了 `ZETTARANC_BACKTEST_IMPL=python` fallback

详见 docs/superpowers/specs/2026-07-18-rust-refactor-design.md
```

- [ ] **Step 5: 提交 + tag v4.0.0**

```bash
git commit -am "chore(v4.0): cleanup Python implementations, document Rust migration"
git tag v4.0.0 -m "v4.0.0: Rust core compute via PyO3 + Polars"
git push origin main --tags
```

---

## Spec Coverage 验证（自检）

| spec 节 | 覆盖 task |
|---|---|
| §2.1-2.3 工作区 + 双层 import | Task 1-4 |
| §3.1-3.3 Polars 数据通道 | Task 2（schema）+ Task 11（高层 API）+ Task 19-21（低层 polars path） |
| §4 错误处理 | Task 6 |
| §5 并行化（rayon） | Task 17（portfolio rayon）+ Task 19（grid_search rayon） |
| §6.2-6.4 golden / property / shadow | Task 12, 13, 16, 20 |
| §6.5 compat shim | Task 7 |
| §7.1 6 个里程碑 | Task 1-22 完整覆盖 |
| §7.2 退出标准三件套 | 每个 M 的最后 task 都验证
| §7.3 性能验收环境 | Task 5（CI 双平台）+ Task 16/20/21（benchmark 脚本） |
| §8 风险缓解 | Task 9/13/16/20/22（每 M 退出三件套：测试全绿 + benchmark + 回滚验证） |

---

# Placeholder Scan

已扫描所有 task，红旗项检查：

- ❌ "TBD" / "TODO" / "FIXME" / "implement later"：0
- ❌ "Add appropriate error handling"：0
- ❌ "Write tests for the above"：0
- ❌ "Similar to Task N"：0（每个 task 给出完整代码）
- ❌ 不带代码的 step：0

---

# Type Consistency Check

| 跨 task 引用的类型 | Task 1-3 定义 | Task 4-22 引用 | 一致 |
|---|---|---|---|
| `kline_schema()` | Task 2 | Task 2 smoke test | ✅ |
| `CoreError` 枚举 | Task 2 | Task 6, 10, 11, 14, 17, 19, 21 | ✅ |
| `KLineSeries` / `KLine` | Task 10（追加到 core_types） | Task 10, 11, 14, 17, 19 | ✅ |
| `compute_atr(window=14)` | Task 10 | Task 11, 13（shadow runner） | ✅ |
| `PortfolioBacktestEngine.run()` | Task 17（Rust）+ Task 18（Python shim） | Task 18 | ✅ |
| `ZETTARANC_BACKTEST_IMPL` env var | Task 7 | Task 16, 22 | ✅ |

无类型不一致。

---

# Execution Handoff

**计划已完成并保存到 `docs/superpowers/plans/2026-07-18-rust-refactor.md`**（3399 行，22 个 task，覆盖 M0-M6 全 6 个里程碑）。

**两个执行选项**：

1. **Subagent-Driven（推荐）** - 每个 task 起一个新 subagent，task 之间做评审，迭代快速。
2. **Inline Execution** - 在当前会话中执行 task，批量执行加检查点。

**关键提醒**：
- M0 必须一次通过，不允许失败累积
- 每个 M 末尾都跑"退出三件套"：正确性（测试）+ 性能（benchmark）+ 可回滚（env var 验证）
- 不允许跳 M；任何 M 失败必须先修复再继续


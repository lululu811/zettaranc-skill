//! PyO3 绑定 crate，编译成 `_core_compute` 原生扩展。
//!
//! 真实实现在每个 M 的最后一个 task 落地。
#![forbid(unsafe_code)]

use pyo3::prelude::*;

/// 测试函数：证明 Rust 编译产物可以被 Python 调用。
#[pyfunction]
fn rust_smoke() -> &'static str {
    "ok from rust"
}

/// 抛出一个 ValueError（验证错误映射，见 bindings::error）。
#[pyfunction]
fn raise_value_error() -> PyResult<()> {
    Err(pyo3::exceptions::PyValueError::new_err(
        "invalid K-line data: test",
    ))
}

/// 抛出一个 KeyError。
#[pyfunction]
fn raise_key_error() -> PyResult<()> {
    Err(pyo3::exceptions::PyKeyError::new_err("ts_code"))
}

#[pymodule]
fn _core_compute(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(rust_smoke, m)?)?;
    m.add_function(wrap_pyfunction!(raise_value_error, m)?)?;
    m.add_function(wrap_pyfunction!(raise_key_error, m)?)?;
    Ok(())
}
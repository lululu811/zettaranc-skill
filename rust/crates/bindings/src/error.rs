//! PyO3 错误映射：Rust CoreError → Python 异常类型。

use pyo3::exceptions::{PyKeyError, PyRuntimeError, PyValueError};
use pyo3::PyErr;
use zt_core_types::CoreError;

/// 把 Rust 业务错误映射到 Python 异常。
/// 约定：业务可恢复 → ValueError / KeyError；基础设施 → RuntimeError。
pub fn core_error_to_pyerr(e: CoreError) -> PyErr {
    match e {
        CoreError::InvalidKLine(m) => PyValueError::new_err(m),
        CoreError::MissingColumn(c) => PyKeyError::new_err(c),
        CoreError::InsufficientData { .. } => PyValueError::new_err(e.to_string()),
        CoreError::EmptyDateRange { .. } => PyValueError::new_err(e.to_string()),
        CoreError::InvalidParameter { .. } => PyValueError::new_err(e.to_string()),
        CoreError::InvalidWalkForward(m) => PyValueError::new_err(m),
        CoreError::Database(m) => PyRuntimeError::new_err(m),
        CoreError::Polars(p) => PyRuntimeError::new_err(format!("polars: {p}")),
        CoreError::Arrow(a) => PyRuntimeError::new_err(format!("arrow: {a}")),
    }
}

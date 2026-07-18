//! PyO3 bindings crate, compiled into the `_core_compute` Python extension.
//!
//! Architecture (see also `Cargo.toml`):
//!
//! ```text
//! crates/bindings/
//!   src/core.rs          <- pure Rust, no PyO3, cargo-testable
//!   src/lib.rs (this)    <- PyO3 wrappers, gated on `#[cfg(feature = "pyo3")]`
//! ```
//!
//! Cargo `[[test]]` cannot consume `cdylib` output directly, so we keep the
//! pure-Rust logic in `core` and only the Python adapter layer here. The
//! `pyo3` feature is on by default (so maturin works) and can be disabled
//! via `--no-default-features` to run cargo test without PyO3.

#![forbid(unsafe_code)]

// Pure-Rust core is always compiled; PyO3 wrappers are gated on `pyo3` feature.
pub mod core;

#[cfg(feature = "pyo3")]
mod backtest_bindings;
#[cfg(feature = "pyo3")]
mod error;

#[cfg(feature = "pyo3")]
use pyo3::prelude::*;

#[cfg(feature = "pyo3")]
use zt_core_types::KLine;

#[cfg(feature = "pyo3")]
use crate::core as _core_mod;

// ---------------------------------------------------------------------------
// PyO3 wrapper layer (only present when `pyo3` feature is enabled)
// ---------------------------------------------------------------------------

#[cfg(feature = "pyo3")]
#[pyfunction]
fn rust_smoke() -> &'static str {
    "ok from rust"
}

#[cfg(feature = "pyo3")]
#[pyfunction]
fn raise_value_error() -> PyResult<()> {
    Err(error::core_error_to_pyerr(
        zt_core_types::CoreError::InvalidKLine("test".to_string()),
    ))
}

#[cfg(feature = "pyo3")]
#[pyfunction]
fn raise_key_error() -> PyResult<()> {
    Err(error::core_error_to_pyerr(
        zt_core_types::CoreError::MissingColumn("ts_code".to_string()),
    ))
}

#[cfg(feature = "pyo3")]
#[pyfunction]
#[pyo3(signature = (klines, window=14))]
fn compute_atr_py(klines: Vec<Bound<'_, pyo3::PyAny>>, window: usize) -> PyResult<Vec<f64>> {
    let series = parse_klines(&klines)?;
    _core_mod::core_compute_atr(&series, window).map_err(error::core_error_to_pyerr)
}

#[cfg(feature = "pyo3")]
fn parse_klines(items: &[Bound<'_, pyo3::PyAny>]) -> PyResult<zt_core_types::KLineSeries> {
    use pyo3::types::PyDict;
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        let d = item.downcast::<PyDict>()?;
        let get_f64 = |k: &str| -> PyResult<f64> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
                .extract::<f64>()
        };
        let get_i32 = |k: &str| -> PyResult<i32> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
                .extract::<i32>()
        };
        let get_str = |k: &str| -> PyResult<String> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
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

#[cfg(feature = "pyo3")]
#[pymodule]
fn _core_compute(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(rust_smoke, m)?)?;
    m.add_function(wrap_pyfunction!(raise_value_error, m)?)?;
    m.add_function(wrap_pyfunction!(raise_key_error, m)?)?;
    m.add_function(wrap_pyfunction!(compute_atr_py, m)?)?;
    m.add_function(wrap_pyfunction!(
        backtest_bindings::run_single_strategy_backtest_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        backtest_bindings::run_portfolio_backtest_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(backtest_bindings::run_grid_search_py, m)?)?;
    Ok(())
}
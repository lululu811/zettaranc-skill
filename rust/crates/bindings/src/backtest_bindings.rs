//! PyO3 bindings: single-strategy / portfolio / grid-search wrappers.
//!
//! Layering (matches `lib.rs`):
//!
//! ```text
//! Python dict/list  --(parse)-->  serde_json::Value / Rust types
//!                                          |
//!                                          v
//!                                  crate::core::core_run_*(...)  <- pure Rust
//!                                          |
//!                                          v
//!                                  *View struct  --(serialize)-->  serde_json::Value
//!                                          |
//!                                          v
//!                                  Python dict
//! ```
//!
//! The actual computation lives in `crate::core` so it is cargo-testable
//! without PyO3.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value;

use zt_backtest_engine::SingleStrategyConfig;
use zt_core_types::KLineSeries;

use crate::core as core_api;
use crate::error::core_error_to_pyerr;

// ---------------------------------------------------------------------------
// Python <-> JSON conversion (PyO3 only; kept here so `core` stays PyO3-free)
// ---------------------------------------------------------------------------

fn pyany_to_json(obj: &Bound<'_, pyo3::PyAny>) -> PyResult<Value> {
    if obj.is_none() {
        Ok(Value::Null)
    } else if let Ok(b) = obj.extract::<bool>() {
        Ok(Value::Bool(b))
    } else if let Ok(i) = obj.extract::<i64>() {
        Ok(Value::Number(i.into()))
    } else if let Ok(f) = obj.extract::<f64>() {
        serde_json::Number::from_f64(f)
            .map(Value::Number)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("non-finite float"))
    } else if let Ok(s) = obj.extract::<String>() {
        Ok(Value::String(s))
    } else if let Ok(d) = obj.downcast::<PyDict>() {
        let mut map = serde_json::Map::new();
        for (k, v) in d.iter() {
            let key = k.extract::<String>()?;
            map.insert(key, pyany_to_json(&v)?);
        }
        Ok(Value::Object(map))
    } else if let Ok(seq) = obj.extract::<Vec<Bound<'_, pyo3::PyAny>>>() {
        let mut arr = Vec::with_capacity(seq.len());
        for item in &seq {
            arr.push(pyany_to_json(item)?);
        }
        Ok(Value::Array(arr))
    } else {
        Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "unsupported type for JSON conversion: {}",
            obj.get_type().name()?
        )))
    }
}

fn json_to_py<'py>(py: Python<'py>, v: &Value) -> PyResult<Bound<'py, pyo3::PyAny>> {
    use pyo3::conversion::ToPyObject;
    match v {
        Value::Null => Ok(py.None().into_bound(py)),
        Value::Bool(b) => Ok(b.to_object(py).into_bound(py)),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_object(py).into_bound(py))
            } else if let Some(u) = n.as_u64() {
                Ok(u.to_object(py).into_bound(py))
            } else if let Some(f) = n.as_f64() {
                Ok(f.to_object(py).into_bound(py))
            } else {
                Err(pyo3::exceptions::PyValueError::new_err("bad number"))
            }
        }
        Value::String(s) => Ok(s.to_object(py).into_bound(py)),
        Value::Array(arr) => {
            let list = PyList::empty_bound(py);
            for item in arr {
                list.append(json_to_py(py, item)?)?;
            }
            Ok(list.into_any())
        }
        Value::Object(map) => {
            let dict = PyDict::new_bound(py);
            for (k, vv) in map {
                dict.set_item(k, json_to_py(py, vv)?)?;
            }
            Ok(dict.into_any())
        }
    }
}

// ---------------------------------------------------------------------------
// Field readers (with defaults) — kept here because they're purely about
// Python dict shape, not about the Rust core.
// ---------------------------------------------------------------------------

fn read_f64(v: &Value, key: &str, default: f64) -> PyResult<f64> {
    match v.get(key) {
        Some(Value::Number(n)) => n
            .as_f64()
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("{key} not f64"))),
        Some(Value::Null) | None => Ok(default),
        Some(_) => Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "{key} must be number"
        ))),
    }
}

fn read_usize(v: &Value, key: &str, default: usize) -> PyResult<usize> {
    match v.get(key) {
        Some(Value::Number(n)) => n
            .as_u64()
            .map(|u| u as usize)
            .or_else(|| n.as_i64().map(|i| i as usize))
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("{key} not int"))),
        Some(Value::Null) | None => Ok(default),
        Some(_) => Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "{key} must be int"
        ))),
    }
}

fn read_bool(v: &Value, key: &str, default: bool) -> PyResult<bool> {
    match v.get(key) {
        Some(Value::Bool(b)) => Ok(*b),
        Some(Value::Null) | None => Ok(default),
        Some(_) => Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "{key} must be bool"
        ))),
    }
}

// ---------------------------------------------------------------------------
// *View -> serde_json::Value (output serialization, PyO3-only)
// ---------------------------------------------------------------------------

fn trade_view_to_value(t: &core_api::TradeView) -> Value {
    let mut m = serde_json::Map::new();
    m.insert("entry_date".into(), Value::from(t.entry_date));
    m.insert("exit_date".into(), Value::from(t.exit_date));
    m.insert("entry_price".into(), Value::from(t.entry_price));
    m.insert("exit_price".into(), Value::from(t.exit_price));
    m.insert("pnl".into(), Value::from(t.pnl));
    m.insert("return".into(), Value::from(t.return_pct));
    m.insert("exit_reason".into(), Value::String(t.exit_reason.clone()));
    Value::Object(m)
}

fn single_view_to_value(r: &core_api::SingleResultView) -> Value {
    let trades: Vec<Value> = r.trades.iter().map(trade_view_to_value).collect();
    let mut metrics = serde_json::Map::new();
    metrics.insert("total_return".into(), Value::from(r.total_return));
    metrics.insert("sharpe_ratio".into(), Value::from(r.sharpe_ratio));
    metrics.insert("max_drawdown".into(), Value::from(r.max_drawdown));
    metrics.insert("win_rate".into(), Value::from(r.win_rate));
    metrics.insert("final_value".into(), Value::from(r.final_value));
    metrics.insert("initial_cash".into(), Value::from(r.initial_cash));
    metrics.insert("total_trades".into(), Value::from(r.total_trades));

    let mut m = serde_json::Map::new();
    m.insert("trades".into(), Value::Array(trades));
    m.insert("metrics".into(), Value::Object(metrics));
    m.insert(
        "equity_curve".into(),
        Value::Array(r.equity_curve.iter().map(|v| Value::from(*v)).collect()),
    );
    m.insert(
        "cash_history".into(),
        Value::Array(r.cash_history.iter().map(|v| Value::from(*v)).collect()),
    );
    Value::Object(m)
}

fn parse_single_config(v: &Value) -> PyResult<SingleStrategyConfig> {
    Ok(SingleStrategyConfig {
        j_threshold: read_f64(v, "j_threshold", -5.0)?,
        stop_loss_pct: read_f64(v, "stop_loss_pct", 0.05)?,
        vol_shrink_threshold: read_f64(v, "vol_shrink_threshold", 0.5)?,
        bbi_break_days: read_usize(v, "bbi_break_days", 3)?,
        min_holding_days: read_usize(v, "min_holding_days", 3)?,
        lu_half: read_bool(v, "lu_half", true)?,
        position_pct: read_f64(v, "position_pct", 0.5)?,
        initial_cash: read_f64(v, "initial_cash", 100_000.0)?,
    })
}

fn parse_klines_series(items: &[Bound<'_, pyo3::PyAny>]) -> PyResult<KLineSeries> {
    crate::parse_klines(items)
}

#[pyfunction]
#[pyo3(signature = (config, klines))]
pub fn run_single_strategy_backtest_py(
    py: Python<'_>,
    config: &Bound<'_, pyo3::PyAny>,
    klines: Vec<Bound<'_, pyo3::PyAny>>,
) -> PyResult<PyObject> {
    let cfg_v = pyany_to_json(config)?;
    let cfg = parse_single_config(&cfg_v)?;
    let series = parse_klines_series(&klines)?;

    let view = core_api::core_run_single_strategy_backtest(
        &series,
        &cfg,
        |_: usize, _: &KLineSeries, _: &SingleStrategyConfig| None,
        |_: usize, _: &KLineSeries, _: &SingleStrategyConfig, _: f64| None,
    )
    .map_err(core_error_to_pyerr)?;

    let v = single_view_to_value(&view);
    Ok(json_to_py(py, &v)?.unbind())
}

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
use std::collections::HashMap;

use zt_backtest_engine::{PortfolioConfig, SingleStrategyConfig};
use zt_core_types::{CoreError, KLineSeries};
use zt_grid_search::{ParamSet, WalkForwardSplit};

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

fn named_trade_view_to_value(t: &core_api::NamedTradeView) -> Value {
    let mut m = serde_json::Map::new();
    m.insert("ts_code".into(), Value::String(t.ts_code.clone()));
    m.insert("entry_date".into(), Value::from(t.entry_date));
    m.insert("exit_date".into(), Value::from(t.exit_date));
    m.insert("entry_price".into(), Value::from(t.entry_price));
    m.insert("exit_price".into(), Value::from(t.exit_price));
    m.insert("pnl".into(), Value::from(t.pnl));
    m.insert("strategy".into(), Value::String(t.strategy.clone()));
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

fn portfolio_view_to_value(r: &core_api::PortfolioResultView) -> Value {
    let per_strategy_trades: serde_json::Map<String, Value> = r
        .per_strategy_trades
        .iter()
        .map(|(k, v)| {
            (
                k.clone(),
                Value::Array(v.iter().map(named_trade_view_to_value).collect()),
            )
        })
        .collect();

    let mut metrics = serde_json::Map::new();
    metrics.insert("total_return".into(), Value::from(r.total_return));
    metrics.insert("sharpe_ratio".into(), Value::from(r.sharpe_ratio));
    metrics.insert("max_drawdown".into(), Value::from(r.max_drawdown));
    metrics.insert("win_rate".into(), Value::from(r.win_rate));
    metrics.insert("calmar".into(), Value::from(r.calmar));
    metrics.insert("final_value".into(), Value::from(r.final_value));
    metrics.insert("initial_cash".into(), Value::from(r.initial_cash));
    metrics.insert("total_trades".into(), Value::from(r.total_trades));

    let mut m = serde_json::Map::new();
    m.insert("portfolio_metrics".into(), Value::Object(metrics));
    m.insert(
        "per_strategy_trades".into(),
        Value::Object(per_strategy_trades),
    );
    m.insert(
        "aggregate_equity_curve".into(),
        Value::Array(
            r.aggregate_equity_curve
                .iter()
                .map(|v| Value::from(*v))
                .collect(),
        ),
    );
    m.insert(
        "cash_history".into(),
        Value::Array(r.cash_history.iter().map(|v| Value::from(*v)).collect()),
    );
    Value::Object(m)
}

fn param_set_to_value(p: &ParamSet) -> Value {
    let mut m = serde_json::Map::new();
    m.insert("j_threshold".into(), Value::from(p.j_threshold));
    m.insert("stop_loss_pct".into(), Value::from(p.stop_loss_pct));
    m.insert(
        "vol_shrink_threshold".into(),
        Value::from(p.vol_shrink_threshold),
    );
    m.insert(
        "bbi_break_days".into(),
        Value::from(p.bbi_break_days as i64),
    );
    m.insert(
        "min_holding_days".into(),
        Value::from(p.min_holding_days as i64),
    );
    m.insert("lu_half".into(), Value::Bool(p.lu_half));
    m.insert("position_pct".into(), Value::from(p.position_pct));
    Value::Object(m)
}

fn grid_search_view_to_value(r: &core_api::GridSearchOutputView) -> Value {
    let mut out = serde_json::Map::new();
    out.insert(
        "all_results".into(),
        Value::Array(
            r.all_results
                .iter()
                .map(|gr| {
                    let mut m = serde_json::Map::new();
                    m.insert("params".into(), param_set_to_value(&gr.params));
                    m.insert("train_sharpe".into(), Value::from(gr.train_sharpe));
                    m.insert("test_sharpe".into(), Value::from(gr.test_sharpe));
                    m.insert("oos_is_ratio".into(), Value::from(gr.oos_is_ratio));
                    Value::Object(m)
                })
                .collect(),
        ),
    );
    out.insert("n_results".into(), Value::from(r.n_results));
    out.insert("best_score".into(), Value::from(r.best_score));
    out.insert("best_train_sharpe".into(), Value::from(r.best_train_sharpe));
    out.insert("best_oos_is_ratio".into(), Value::from(r.best_oos_is_ratio));
    if let Some(p) = &r.best_params {
        out.insert("best_params".into(), param_set_to_value(p));
    } else {
        out.insert("best_params".into(), Value::Object(serde_json::Map::new()));
    }
    Value::Object(out)
}

// ---------------------------------------------------------------------------
// Python dict -> Rust types
// ---------------------------------------------------------------------------

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

fn parse_portfolio_config(v: &Value) -> PyResult<PortfolioConfig> {
    let single_v = v
        .get("single")
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("single"))?;
    let single = parse_single_config(single_v)?;
    let days = read_usize(v, "days", 100)?;
    let max_positions = read_usize(v, "max_positions", 5)?;
    Ok(PortfolioConfig {
        days,
        max_positions,
        single,
    })
}

fn parse_param_grid(grid: Vec<HashMap<String, f64>>) -> PyResult<Vec<ParamSet>> {
    let mut out = Vec::with_capacity(grid.len());
    for (i, params) in grid.into_iter().enumerate() {
        let mut m = serde_json::Map::new();
        for (k, val) in params {
            m.insert(k, Value::from(val));
        }
        // 兜底字段
        m.entry("j_threshold".to_string())
            .or_insert(Value::from(-5.0_f64));
        m.entry("stop_loss_pct".to_string())
            .or_insert(Value::from(0.05_f64));
        m.entry("vol_shrink_threshold".to_string())
            .or_insert(Value::from(0.5_f64));
        m.entry("bbi_break_days".to_string())
            .or_insert(Value::from(3_i64));
        m.entry("min_holding_days".to_string())
            .or_insert(Value::from(3_i64));
        m.entry("lu_half".to_string()).or_insert(Value::Bool(true));
        m.entry("position_pct".to_string())
            .or_insert(Value::from(0.5_f64));

        let v = Value::Object(m);
        let p: ParamSet = serde_json::from_value(v).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("param_grid[{i}] deserialize: {e}"))
        })?;
        out.push(p);
    }
    Ok(out)
}

fn parse_walk_forward_splits(v: &Value) -> PyResult<Vec<WalkForwardSplit>> {
    let arr = v
        .as_array()
        .ok_or_else(|| pyo3::exceptions::PyTypeError::new_err("splits must be list"))?;
    let mut out = Vec::with_capacity(arr.len());
    for (i, item) in arr.iter().enumerate() {
        let obj = item
            .as_object()
            .ok_or_else(|| pyo3::exceptions::PyTypeError::new_err("split must be dict"))?;
        let get = |k: &str| -> PyResult<usize> {
            obj.get(k)
                .and_then(|v| v.as_u64())
                .map(|u| u as usize)
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(format!("splits[{i}].{k}")))
        };
        out.push(WalkForwardSplit {
            train_start: get("train_start")?,
            train_end: get("train_end")?,
            test_start: get("test_start")?,
            test_end: get("test_end")?,
        });
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// PyO3 entry points
// ---------------------------------------------------------------------------

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

#[pyfunction]
#[pyo3(signature = (config, klines_by_code))]
pub fn run_portfolio_backtest_py(
    py: Python<'_>,
    config: &Bound<'_, pyo3::PyAny>,
    klines_by_code: &Bound<'_, pyo3::PyAny>,
) -> PyResult<PyObject> {
    let cfg_v = pyany_to_json(config)?;
    let cfg = parse_portfolio_config(&cfg_v)?;

    let map_dict = klines_by_code.downcast::<PyDict>()?;
    let mut series_map: HashMap<String, KLineSeries> = HashMap::new();
    for (key, value) in map_dict.iter() {
        let code = key.extract::<String>()?;
        let seq = value
            .extract::<Vec<Bound<'_, pyo3::PyAny>>>()
            .map_err(|e| {
                pyo3::exceptions::PyTypeError::new_err(format!(
                    "klines_by_code[{code}] must be list: {e}"
                ))
            })?;
        let series = parse_klines_series(&seq)?;
        series_map.insert(code, series);
    }

    let view = core_api::core_run_portfolio_backtest(
        &series_map,
        &cfg,
        |_: usize, _: &KLineSeries, _: &SingleStrategyConfig| None,
        |_: usize, _: &KLineSeries, _: &SingleStrategyConfig, _: f64| None,
    )
    .map_err(core_error_to_pyerr)?;

    let v = portfolio_view_to_value(&view);
    Ok(json_to_py(py, &v)?.unbind())
}

#[pyfunction]
#[pyo3(signature = (base_config, param_grid, splits, klines))]
pub fn run_grid_search_py(
    py: Python<'_>,
    base_config: &Bound<'_, pyo3::PyAny>,
    param_grid: Vec<HashMap<String, f64>>,
    splits: &Bound<'_, pyo3::PyAny>,
    klines: Vec<Bound<'_, pyo3::PyAny>>,
) -> PyResult<PyObject> {
    let base_v = pyany_to_json(base_config)?;
    let initial_cash = read_f64(&base_v, "initial_cash", 100_000.0)?;
    let splits_v = pyany_to_json(splits)?;
    let splits_rust = parse_walk_forward_splits(&splits_v)?;
    let grid_rust = parse_param_grid(param_grid)?;
    let series = parse_klines_series(&klines)?;

    let view = core_api::core_run_grid_search(&series, &grid_rust, &splits_rust, initial_cash)
        .map_err(|e: CoreError| core_error_to_pyerr(e))?;

    let v = grid_search_view_to_value(&view);
    Ok(json_to_py(py, &v)?.unbind())
}

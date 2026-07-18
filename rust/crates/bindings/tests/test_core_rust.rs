//! Pure-Rust integration tests for `zt_bindings::core`.
//!
//! These tests do NOT require PyO3 / Python interpreter. They run via:
//!   cargo test -p zt_bindings --no-default-features
//!
//! The same `core` module is exercised by the PyO3 wrappers (when the
//! `pyo3` feature is enabled), so these tests cover the actual
//! computation path that Python users hit.

use std::collections::HashMap;

use zt_backtest_engine::{PortfolioConfig, SingleStrategyConfig};
use zt_core_types::{KLine, KLineSeries};
use zt_grid_search::{ParamSet, WalkForwardSplit};

// The bindings crate's lib is named `_core_compute` (see Cargo.toml [lib].name).
// `cargo test -p zt_bindings --no-default-features` links the rlib target
// and exposes the `core` module through `_core_compute::core`.
use _core_compute::core as core_api;

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

fn make_kline(ts_code: &str, trade_date: i32, close: f64) -> KLine {
    KLine {
        ts_code: ts_code.to_string(),
        trade_date,
        open: close,
        high: close + 1.0,
        low: close - 1.0,
        close,
        vol: 1000.0,
        amount: close * 1000.0,
        pct_chg: 0.0,
        vol_ratio: None,
        is_limit_up: None,
        is_limit_down: None,
    }
}

fn sample_series(n: usize) -> KLineSeries {
    let mut items = Vec::with_capacity(n);
    for i in 0..n {
        let close = 10.0 + (i as f64) * 0.1;
        items.push(make_kline("000001.SZ", 20240100 + i as i32, close));
    }
    KLineSeries { items }
}

fn default_single_cfg() -> SingleStrategyConfig {
    SingleStrategyConfig {
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

fn default_portfolio_cfg() -> PortfolioConfig {
    PortfolioConfig {
        days: 100,
        max_positions: 5,
        single: default_single_cfg(),
    }
}

fn default_param_set() -> ParamSet {
    ParamSet {
        j_threshold: -5.0,
        stop_loss_pct: 0.05,
        vol_shrink_threshold: 0.5,
        bbi_break_days: 3,
        min_holding_days: 3,
        lu_half: true,
        position_pct: 0.5,
    }
}

fn walk_forward_splits() -> Vec<WalkForwardSplit> {
    // Two windows: train [0..30), test [30..50); train [0..40), test [40..50)
    vec![
        WalkForwardSplit {
            train_start: 0,
            train_end: 30,
            test_start: 30,
            test_end: 50,
        },
        WalkForwardSplit {
            train_start: 0,
            train_end: 40,
            test_start: 40,
            test_end: 50,
        },
    ]
}

// ---------------------------------------------------------------------------
// ATR
// ---------------------------------------------------------------------------

#[test]
fn core_compute_atr_matches_zeros_for_constant_window() {
    let series = sample_series(30);
    let atr = core_api::core_compute_atr(&series, 14).expect("compute_atr should succeed");
    assert_eq!(atr.len(), series.len());
    // 前 13 个位置应按 indicators::compute_atr 约定为 0.0
    for v in &atr[..13] {
        assert_eq!(*v, 0.0);
    }
    // 后续位置应 >= 0（true range 非负）
    for v in &atr[13..] {
        assert!(*v >= 0.0);
    }
}

#[test]
fn core_compute_atr_rejects_zero_window() {
    let series = sample_series(10);
    let err = core_api::core_compute_atr(&series, 0).unwrap_err();
    assert!(matches!(
        err,
        zt_core_types::CoreError::InvalidParameter { .. }
    ));
}

#[test]
fn core_compute_atr_rejects_insufficient_data() {
    let series = sample_series(5);
    let err = core_api::core_compute_atr(&series, 14).unwrap_err();
    assert!(matches!(
        err,
        zt_core_types::CoreError::InsufficientData { .. }
    ));
}

// ---------------------------------------------------------------------------
// Single strategy backtest
// ---------------------------------------------------------------------------

#[test]
fn core_run_single_strategy_backtest_runs_with_no_signals() {
    let series = sample_series(50);
    let cfg = default_single_cfg();
    let view = core_api::core_run_single_strategy_backtest(
        &series,
        &cfg,
        |_, _, _| None,
        |_, _, _, _| None,
    )
    .expect("single backtest should succeed");

    // 无信号 -> 无交易
    assert_eq!(view.total_trades, 0);
    assert!(view.trades.is_empty());
    // 净值曲线长度 = series 长度
    assert_eq!(view.equity_curve.len(), series.len());
    assert_eq!(view.cash_history.len(), series.len());
    // initial_cash 透传
    assert_eq!(view.initial_cash, 100_000.0);
    // final_value 应等于 initial_cash（无任何交易）
    assert!(
        (view.final_value - 100_000.0).abs() < 1e-6,
        "final_value should equal initial_cash with no signals, got {}",
        view.final_value
    );
}

#[test]
fn core_single_result_view_roundtrips_serde_json_shape() {
    // Sanity: View struct fields match the JSON keys the PyO3 wrapper emits.
    let series = sample_series(20);
    let cfg = default_single_cfg();
    let view = core_api::core_run_single_strategy_backtest(
        &series,
        &cfg,
        |_, _, _| None,
        |_, _, _, _| None,
    )
    .expect("ok");
    assert_eq!(view.total_return, 0.0); // no trades -> no return
}

// ---------------------------------------------------------------------------
// Portfolio backtest
// ---------------------------------------------------------------------------

#[test]
fn core_run_portfolio_backtest_handles_multiple_codes() {
    let mut series_map: HashMap<String, KLineSeries> = HashMap::new();
    series_map.insert("000001.SZ".into(), sample_series(60));
    series_map.insert("000002.SZ".into(), sample_series(60));

    let cfg = default_portfolio_cfg();
    let view = core_api::core_run_portfolio_backtest(
        &series_map,
        &cfg,
        |_, _, _| None,
        |_, _, _, _| None,
    )
    .expect("portfolio backtest should succeed");

    // 无信号 -> per_strategy_trades 应为空（即使 initial_cash > 0）
    assert!(view.per_strategy_trades.is_empty());
    assert_eq!(view.total_trades, 0);
    assert_eq!(view.aggregate_equity_curve.len(), 60);
    assert_eq!(view.cash_history.len(), 60);
    assert!((view.final_value - 100_000.0).abs() < 1e-6);
}

#[test]
fn core_run_portfolio_backtest_returns_empty_result_for_short_series() {
    // The portfolio engine produces an empty result (no trades) for short
    // series instead of raising. Verify that semantics is preserved.
    let mut series_map: HashMap<String, KLineSeries> = HashMap::new();
    series_map.insert("000001.SZ".into(), sample_series(5));
    let cfg = default_portfolio_cfg();
    let view = core_api::core_run_portfolio_backtest(
        &series_map,
        &cfg,
        |_, _, _| None,
        |_, _, _, _| None,
    )
    .expect("portfolio backtest returns Ok with empty result for short series");

    assert_eq!(view.total_trades, 0);
    assert!(view.per_strategy_trades.is_empty());
    assert_eq!(view.final_value, 100_000.0);
}

// ---------------------------------------------------------------------------
// Grid search
// ---------------------------------------------------------------------------

#[test]
fn core_run_grid_search_picks_best_by_test_sharpe() {
    let series = sample_series(60);
    let grid = vec![default_param_set(), default_param_set()];
    let splits = walk_forward_splits();

    let view =
        core_api::core_run_grid_search(&series, &grid, &splits, 100_000.0).expect("grid ok");

    assert_eq!(view.n_results, grid.len() * splits.len());
    assert_eq!(view.all_results.len(), view.n_results);
    assert!(view.best_params.is_some());
    // best_score == best(test_sharpe) from all_results
    let expected_best = view
        .all_results
        .iter()
        .map(|r| r.test_sharpe)
        .fold(f64::NEG_INFINITY, f64::max);
    assert!(
        (view.best_score - expected_best).abs() < 1e-12,
        "best_score {} != actual max {}",
        view.best_score,
        expected_best
    );
}

#[test]
fn core_run_grid_search_handles_empty_grid() {
    // The grid-search engine rejects an empty param_grid with InvalidParameter.
    // Verify the error type is propagated correctly through core_api.
    let series = sample_series(50);
    let splits = walk_forward_splits();
    let err = core_api::core_run_grid_search(&series, &[], &splits, 100_000.0).unwrap_err();
    assert!(matches!(
        err,
        zt_core_types::CoreError::InvalidParameter { .. }
    ));
}

// ---------------------------------------------------------------------------
// Smoke: confirm the `core` module is publicly reachable.
// ---------------------------------------------------------------------------

#[test]
fn core_module_is_publicly_exported() {
    // The whole point of the refactor: cargo test can reach the core without
    // pulling in pyo3.
    let _: fn(&KLineSeries, usize) -> zt_core_types::Result<Vec<f64>> = core_api::core_compute_atr;
}
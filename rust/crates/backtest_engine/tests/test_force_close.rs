//! Regression tests for the force-close (loop tail) branch in
//! `run_single_strategy_backtest` and `run_portfolio_backtest`.
//!
//! These tests guard against the bug where the force-close block records a
//! `Trade { pnl }` and pushes it into `trades`, but the bookkeeping side
//! (cash + position) was not updated before `final_value` is computed.
//! As a result `final_value - initial_capital` did not equal `sum(trades.pnl)`
//! in some scenarios.

use std::collections::HashMap;

use zt_backtest_engine::{
    run_portfolio_backtest, run_single_strategy_backtest, PortfolioConfig,
    SingleStrategyConfig,
};
use zt_core_types::{KLine, KLineSeries};

fn linear_klines(n: usize, base: f64, step: f64) -> KLineSeries {
    let items = (0..n)
        .map(|i| KLine {
            ts_code: "X".into(),
            trade_date: i as i32,
            open: base + i as f64 * step,
            high: base + 0.5 + i as f64 * step,
            low: base - 0.5 + i as f64 * step,
            close: base + i as f64 * step,
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

fn default_config() -> SingleStrategyConfig {
    SingleStrategyConfig {
        j_threshold: -5.0,
        stop_loss_pct: 0.05,
        vol_shrink_threshold: 0.5,
        bbi_break_days: 3,
        min_holding_days: 3,
        lu_half: false,
        position_pct: 0.5,
        initial_cash: 100_000.0,
    }
}

/// Force-close on a rising series: enter at i=10, never exit, hold to last bar.
/// `final_value - initial_cash` must equal the single force-close trade's `pnl`.
#[test]
fn single_force_close_pnl_matches_final_value() {
    let n = 100;
    let ks = linear_klines(n, 10.0, 0.1);
    let cfg = default_config();
    let entry_px = ks.items[10].close;
    let r = run_single_strategy_backtest(
        &ks,
        &cfg,
        |i, _, _| if i == 10 { Some(entry_px) } else { None },
        |_, _, _, _| None,
    )
    .unwrap();

    // Sanity: exactly one trade and it is the force-close trade.
    assert_eq!(r.trades.len(), 1, "expected exactly 1 force-close trade");
    let t = &r.trades[0];
    assert_eq!(t.exit_reason, "force_close");

    // Reconstruct expected pnl from the public inputs.
    let last_px = ks.items[n - 1].close;
    let shares = (cfg.initial_cash * cfg.position_pct / entry_px / 100.0).floor() * 100.0;
    let expected_pnl = (last_px - entry_px) * shares;
    assert!(
        (t.pnl - expected_pnl).abs() < 1e-6,
        "trade.pnl = {}, expected {}",
        t.pnl,
        expected_pnl
    );

    // The key invariant: trades.pnl sum == final_value - initial_capital.
    let sum_pnl: f64 = r.trades.iter().map(|t| t.pnl).sum();
    let delta = r.final_value - cfg.initial_cash;
    assert!(
        (sum_pnl - delta).abs() < 1e-6,
        "sum(trades.pnl) = {}, final_value - initial_cash = {} (final_value = {})",
        sum_pnl,
        delta,
        r.final_value
    );
}

/// Force-close on a falling series: enter at i=10, never exit, hold to last bar.
/// Even when the trade is a loser, the invariant must still hold.
#[test]
fn single_force_close_loss_matches_final_value() {
    let n = 100;
    // Falling prices so the force-close trade has negative pnl.
    let ks = linear_klines(n, 20.0, -0.1);
    let cfg = default_config();
    let entry_px = ks.items[10].close;
    let r = run_single_strategy_backtest(
        &ks,
        &cfg,
        |i, _, _| if i == 10 { Some(entry_px) } else { None },
        |_, _, _, _| None,
    )
    .unwrap();

    assert_eq!(r.trades.len(), 1);
    assert_eq!(r.trades[0].exit_reason, "force_close");
    assert!(r.trades[0].pnl < 0.0, "expected losing trade");

    let sum_pnl: f64 = r.trades.iter().map(|t| t.pnl).sum();
    let delta = r.final_value - cfg.initial_cash;
    assert!(
        (sum_pnl - delta).abs() < 1e-6,
        "sum(trades.pnl) = {}, final_value - initial_cash = {}",
        sum_pnl,
        delta
    );
}

/// Two entries + one in-loop exit + one force-close at end.
/// (Entries do not produce trades; only exits do.) The two resulting trades'
/// pnl must sum to `final_value - initial_cash`.
#[test]
fn single_mixed_exits_and_force_close_consistent() {
    let n = 100;
    let ks = linear_klines(n, 10.0, 0.1);
    let cfg = default_config();

    // entry at i=10, in-loop exit at i=50, re-entry at i=60, hold to end.
    let r = run_single_strategy_backtest(
        &ks,
        &cfg,
        |i, ks, _| {
            if i == 10 || i == 60 {
                Some(ks.items[i].close)
            } else {
                None
            }
        },
        |i, _, _, _| {
            if i == 50 {
                Some("regular_exit".to_string())
            } else {
                None
            }
        },
    )
    .unwrap();

    // Only exits produce trades: 1 regular exit + 1 force-close = 2 trades.
    assert_eq!(r.trades.len(), 2, "expected 2 trades (entries are not trades)");
    assert_eq!(r.trades[0].exit_reason, "regular_exit");
    assert_eq!(r.trades[1].exit_reason, "force_close");

    let sum_pnl: f64 = r.trades.iter().map(|t| t.pnl).sum();
    let delta = r.final_value - cfg.initial_cash;
    assert!(
        (sum_pnl - delta).abs() < 1e-6,
        "sum(trades.pnl) = {}, final_value - initial_cash = {} (final_value = {})",
        sum_pnl,
        delta,
        r.final_value
    );
}

/// Portfolio must propagate the single-trade consistency: each stock's
/// force-close pnl is reflected in the aggregate `final_value`.
#[test]
fn portfolio_force_close_pnl_aggregated() {
    let mut map = HashMap::new();
    map.insert("000001.SZ".into(), linear_klines(100, 10.0, 0.1));
    map.insert("000002.SZ".into(), linear_klines(100, 10.0, 0.1));
    let cfg = PortfolioConfig {
        days: 100,
        max_positions: 5,
        single: default_config(),
    };

    // Both stocks: enter at i=10, never exit -> force-close at end.
    let r = run_portfolio_backtest(
        &map,
        &cfg,
        |i, ks, _| if i == 10 { Some(ks.items[10].close) } else { None },
        |_, _, _, _| None,
    )
    .unwrap();

    assert_eq!(r.trades.len(), 2);

    let sum_pnl: f64 = r.trades.iter().map(|t| t.pnl).sum();
    // Portfolio's net_values is the average of per-stock deltas, so the total
    // delta is the simple sum across stocks divided by 1 (each per-stock
    // delta is (v - initial)). So portfolio.delta == sum(pnl).
    let delta = r.final_value - cfg.single.initial_cash;
    assert!(
        (sum_pnl - delta).abs() < 1e-6,
        "sum(trades.pnl) = {}, final_value - initial_cash = {}",
        sum_pnl,
        delta
    );
}
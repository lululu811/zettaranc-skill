//! Pure-Rust core functions exposed by the bindings crate.
//!
//! These functions are **PyO3-free** and can be invoked from `cargo test`
//! without any Python interpreter. The PyO3 wrapper layer in `lib.rs`
//! delegates to these functions after parsing Python objects.
//!
//! The split exists because cargo's `[[test]]` target cannot consume
//! `cdylib` output directly, and PyO3 0.22's build script refuses
//! Python >= 3.14. By making `pyo3` an optional feature we let:
//!
//! - maturin path: build with default features (`pyo3` on) -> cdylib
//! - cargo test path: `--no-default-features` -> only rlib, no pyo3

use std::collections::HashMap;

use zt_backtest_engine::{
    run_portfolio_backtest, run_single_strategy_backtest, NamedTrade, PortfolioConfig,
    PortfolioResult, SingleStrategyConfig, SingleStrategyResult, Trade,
};
use zt_core_types::{CoreError, KLineSeries};
use zt_grid_search::{run_grid_search, GridSearchResult, ParamSet, WalkForwardSplit};

/// SingleStrategyResult -> serde-friendly plain struct.
///
/// We deliberately avoid serde derive so the pure-Rust layer stays
/// dependency-light; serde_json::Value construction is done by the
/// PyO3 wrapper layer.
#[derive(Debug, Clone, PartialEq)]
pub struct SingleResultView {
    pub trades: Vec<TradeView>,
    pub total_return: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown: f64,
    pub win_rate: f64,
    pub final_value: f64,
    pub initial_cash: f64,
    pub total_trades: usize,
    pub equity_curve: Vec<f64>,
    pub cash_history: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TradeView {
    pub entry_date: i32,
    pub exit_date: i32,
    pub entry_price: f64,
    pub exit_price: f64,
    pub pnl: f64,
    pub return_pct: f64,
    pub exit_reason: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NamedTradeView {
    pub ts_code: String,
    pub entry_date: i32,
    pub exit_date: i32,
    pub entry_price: f64,
    pub exit_price: f64,
    pub pnl: f64,
    pub strategy: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PortfolioResultView {
    pub per_strategy_trades: HashMap<String, Vec<NamedTradeView>>,
    pub total_return: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown: f64,
    pub win_rate: f64,
    pub calmar: f64,
    pub final_value: f64,
    pub initial_cash: f64,
    pub total_trades: usize,
    pub aggregate_equity_curve: Vec<f64>,
    pub cash_history: Vec<f64>,
}

#[derive(Debug, Clone)]
pub struct GridResultView {
    pub params: ParamSet,
    pub train_sharpe: f64,
    pub test_sharpe: f64,
    pub oos_is_ratio: f64,
}

#[derive(Debug, Clone)]
pub struct GridSearchOutputView {
    pub all_results: Vec<GridResultView>,
    pub n_results: usize,
    pub best_score: f64,
    pub best_train_sharpe: f64,
    pub best_oos_is_ratio: f64,
    pub best_params: Option<ParamSet>,
}

// ---------------------------------------------------------------------------
// Trade conversion helpers
// ---------------------------------------------------------------------------

fn return_pct(t: &Trade) -> f64 {
    if t.entry_price.abs() < 1e-12 {
        0.0
    } else {
        (t.exit_price - t.entry_price) / t.entry_price
    }
}

fn trade_to_view(t: &Trade) -> TradeView {
    TradeView {
        entry_date: t.entry_date,
        exit_date: t.exit_date,
        entry_price: t.entry_price,
        exit_price: t.exit_price,
        pnl: t.pnl,
        return_pct: return_pct(t),
        exit_reason: t.exit_reason.clone(),
    }
}

fn named_trade_to_view(t: &NamedTrade) -> NamedTradeView {
    NamedTradeView {
        ts_code: t.ts_code.clone(),
        entry_date: t.entry_date,
        exit_date: t.exit_date,
        entry_price: t.entry_price,
        exit_price: t.exit_price,
        pnl: t.pnl,
        strategy: t.strategy.clone(),
    }
}

fn single_result_to_view(r: &SingleStrategyResult, initial_cash: f64) -> SingleResultView {
    let total_return = if initial_cash.abs() > 1e-12 {
        (r.final_value - initial_cash) / initial_cash
    } else {
        0.0
    };
    SingleResultView {
        trades: r.trades.iter().map(trade_to_view).collect(),
        total_return,
        sharpe_ratio: r.sharpe_ratio,
        max_drawdown: r.max_drawdown,
        win_rate: r.win_rate,
        final_value: r.final_value,
        initial_cash,
        total_trades: r.trades.len(),
        equity_curve: r.net_values.clone(),
        cash_history: r.cash_history.clone(),
    }
}

fn portfolio_result_to_view(r: &PortfolioResult, initial_cash: f64) -> PortfolioResultView {
    let total_return = if initial_cash.abs() > 1e-12 {
        (r.final_value - initial_cash) / initial_cash
    } else {
        0.0
    };
    let mut by_strategy: HashMap<String, Vec<NamedTradeView>> = HashMap::new();
    for t in &r.trades {
        by_strategy
            .entry(t.strategy.clone())
            .or_default()
            .push(named_trade_to_view(t));
    }
    PortfolioResultView {
        per_strategy_trades: by_strategy,
        total_return,
        sharpe_ratio: r.sharpe_ratio,
        max_drawdown: r.max_drawdown,
        win_rate: r.win_rate,
        calmar: r.calmar,
        final_value: r.final_value,
        initial_cash,
        total_trades: r.trades.len(),
        aggregate_equity_curve: r.net_values.clone(),
        cash_history: r.cash_history.clone(),
    }
}

fn grid_result_to_view(r: &GridSearchResult) -> GridResultView {
    GridResultView {
        params: r.param.clone(),
        train_sharpe: r.train_sharpe,
        test_sharpe: r.test_sharpe,
        oos_is_ratio: r.oos_is_ratio,
    }
}

// ---------------------------------------------------------------------------
// Public entry points (PyO3-free)
// ---------------------------------------------------------------------------

/// Pure-Rust equivalent of `compute_atr_py`. Returns the ATR series.
pub fn core_compute_atr(series: &KLineSeries, window: usize) -> Result<Vec<f64>, CoreError> {
    zt_indicators::compute_atr(series, window)
}

/// Pure-Rust equivalent of `run_single_strategy_backtest_py`.
///
/// `signal_at` / `exit_at` callbacks are passed through unchanged so the
/// semantics remain identical to the PyO3 wrapper.
pub fn core_run_single_strategy_backtest<F, G>(
    series: &KLineSeries,
    cfg: &SingleStrategyConfig,
    signal_at: F,
    exit_at: G,
) -> Result<SingleResultView, CoreError>
where
    F: Fn(usize, &KLineSeries, &SingleStrategyConfig) -> Option<f64> + Sync + Send,
    G: Fn(usize, &KLineSeries, &SingleStrategyConfig, f64) -> Option<String> + Sync + Send,
{
    let initial_cash = cfg.initial_cash;
    let r = run_single_strategy_backtest(series, cfg, signal_at, exit_at)?;
    Ok(single_result_to_view(&r, initial_cash))
}

/// Pure-Rust equivalent of `run_portfolio_backtest_py`.
pub fn core_run_portfolio_backtest<F, G>(
    series_map: &HashMap<String, KLineSeries>,
    cfg: &PortfolioConfig,
    signal_at: F,
    exit_at: G,
) -> Result<PortfolioResultView, CoreError>
where
    F: Fn(usize, &KLineSeries, &SingleStrategyConfig) -> Option<f64> + Sync + Send,
    G: Fn(usize, &KLineSeries, &SingleStrategyConfig, f64) -> Option<String> + Sync + Send,
{
    let initial_cash = cfg.single.initial_cash;
    let r = run_portfolio_backtest(series_map, cfg, signal_at, exit_at)?;
    Ok(portfolio_result_to_view(&r, initial_cash))
}

/// Pure-Rust equivalent of `run_grid_search_py`.
pub fn core_run_grid_search(
    series: &KLineSeries,
    grid: &[ParamSet],
    splits: &[WalkForwardSplit],
    initial_cash: f64,
) -> Result<GridSearchOutputView, CoreError> {
    let results = run_grid_search(series, grid, splits, initial_cash)?;
    let best = results.iter().max_by(|a, b| {
        a.test_sharpe
            .partial_cmp(&b.test_sharpe)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let views: Vec<GridResultView> = results.iter().map(grid_result_to_view).collect();
    let (best_score, best_train_sharpe, best_oos_is_ratio, best_params) = if let Some(b) = best {
        (b.test_sharpe, b.train_sharpe, b.oos_is_ratio, Some(b.param.clone()))
    } else {
        (0.0, 0.0, 0.0, None)
    };
    Ok(GridSearchOutputView {
        n_results: results.len(),
        all_results: views,
        best_score,
        best_train_sharpe,
        best_oos_is_ratio,
        best_params,
    })
}
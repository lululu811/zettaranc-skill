//! 参数网格搜索 + Walk-forward 验证。
//!
//! 核心 API：给定 param_grid + splits，并行评估每个 (split, params) 组合。

pub mod walk_forward;

pub use walk_forward::{make_walk_forward_splits, WalkForwardSplit};

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use zt_backtest_engine::{
    run_single_strategy_backtest, SingleStrategyConfig, SingleStrategyResult,
};
use zt_core_types::{CoreError, KLineSeries, Result};

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

/// 笛卡尔积网格搜索 + walk-forward 验证（rayon 并行）。
pub fn run_grid_search(
    klines: &KLineSeries,
    param_grid: &[ParamSet],
    splits: &[WalkForwardSplit],
    initial_cash: f64,
) -> Result<Vec<GridSearchResult>> {
    if param_grid.is_empty() {
        return Err(CoreError::InvalidParameter {
            field: "param_grid".into(),
            value: 0.0,
            constraint: "non-empty".into(),
        });
    }

    let results: Vec<GridSearchResult> = splits
        .par_iter()
        .flat_map(|split| {
            let train_slice = slice_series(klines, split.train_start, split.train_end);
            let test_slice = slice_series(klines, split.test_start, split.test_end);

            param_grid
                .par_iter()
                .map(|p| {
                    let cfg = p.to_single_config(initial_cash);
                    let train_r = run_simple(&train_slice, &cfg);
                    let test_r = run_simple(&test_slice, &cfg);
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

fn run_simple(klines: &KLineSeries, cfg: &SingleStrategyConfig) -> SingleStrategyResult {
    run_single_strategy_backtest(klines, cfg, |_, _, _| None, |_, _, _, _| None).unwrap_or_else(
        |_| SingleStrategyResult {
            net_values: vec![cfg.initial_cash; klines.len()],
            cash_history: vec![cfg.initial_cash; klines.len()],
            trades: vec![],
            win_rate: 0.0,
            sharpe_ratio: 0.0,
            max_drawdown: 0.0,
            final_value: cfg.initial_cash,
        },
    )
}

fn slice_series(klines: &KLineSeries, start: usize, end: usize) -> KLineSeries {
    let end = end.min(klines.items.len());
    let start = start.min(end);
    KLineSeries {
        items: klines.items[start..end].to_vec(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use zt_core_types::KLine;

    fn make_klines(n: usize) -> KLineSeries {
        let items = (0..n)
            .map(|i| KLine {
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
    fn grid_search_returns_n_times_m_results() {
        let klines = make_klines(200);
        let splits = make_walk_forward_splits(200, 60, 30).unwrap();
        assert_eq!(splits.len(), 4);

        let grid: Vec<ParamSet> = (0..5)
            .map(|i| ParamSet {
                j_threshold: -10.0 + i as f64,
                stop_loss_pct: 0.05,
                vol_shrink_threshold: 0.5,
                bbi_break_days: 3,
                min_holding_days: 3,
                lu_half: true,
                position_pct: 0.5,
            })
            .collect();

        let results = run_grid_search(&klines, &grid, &splits, 100_000.0).unwrap();
        assert_eq!(results.len(), splits.len() * grid.len());
    }

    #[test]
    fn empty_grid_errors() {
        let klines = make_klines(100);
        let splits = make_walk_forward_splits(100, 30, 30).unwrap();
        assert!(run_grid_search(&klines, &[], &splits, 100_000.0).is_err());
    }
}

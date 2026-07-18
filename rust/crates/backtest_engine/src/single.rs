//! 单策略单股回测。
//!
//! 输入：K 线序列 + 策略参数（j_threshold / stop_loss_pct / ...）
//! 输出：净值曲线 + 交易列表 + 基础指标。

use serde::{Deserialize, Serialize};
use zt_core_types::{CoreError, KLineSeries, Result};

#[derive(Debug, Clone, Deserialize)]
pub struct SingleStrategyConfig {
    pub j_threshold: f64,
    pub stop_loss_pct: f64,
    pub vol_shrink_threshold: f64,
    pub bbi_break_days: usize,
    pub min_holding_days: usize,
    pub lu_half: bool,
    pub position_pct: f64,
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
/// 策略信号/退出用回调注入（Python 业务层包装时填入）。
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
    let mut position = 0.0_f64;
    let mut entry_price = 0.0_f64;
    let mut entry_date = 0_i32;
    let mut net_values = Vec::with_capacity(n);
    let mut cash_history = Vec::with_capacity(n);
    let mut trades = Vec::new();

    for i in 0..n {
        let price = klines.items[i].close;

        // 1. 持仓中：判断离场
        if position > 0.0 {
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
        trades.push(Trade {
            entry_date,
            entry_price,
            exit_date: klines.items[n - 1].trade_date,
            exit_price: price,
            pnl,
            exit_reason: "force_close".into(),
        });
    }

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

fn compute_sharpe(net_values: &[f64], _initial: f64) -> f64 {
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
    use zt_core_types::KLine;

    fn linear_klines(n: usize) -> KLineSeries {
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
        let entry_px = ks.items[10].close;
        let r = run_single_strategy_backtest(
            &ks,
            &cfg,
            |i, _, _| if i == 10 { Some(entry_px) } else { None },
            |_, _, _, _| None,
        )
        .unwrap();
        assert_eq!(r.trades.len(), 1);
        assert_eq!(r.trades[0].entry_date, 10);
        assert_eq!(r.trades[0].exit_reason, "force_close");
        assert!(r.final_value > cfg.initial_cash);
    }
}
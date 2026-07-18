//! 组合回测：多股并行扫描 + 多策略共振。

use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use zt_core_types::{CoreError, KLineSeries, Result};

use crate::single::{
    run_single_strategy_backtest, SingleStrategyConfig, SingleStrategyResult,
};

#[derive(Debug, Clone, Deserialize)]
pub struct PortfolioConfig {
    pub days: usize,
    pub max_positions: usize,
    pub single: SingleStrategyConfig,
}

#[derive(Debug, Clone, Serialize)]
pub struct PortfolioResult {
    pub net_values: Vec<f64>,
    pub cash_history: Vec<f64>,
    pub trades: Vec<NamedTrade>,
    pub win_rate: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown: f64,
    pub calmar: f64,
    pub final_value: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct NamedTrade {
    pub ts_code: String,
    pub entry_date: i32,
    pub entry_price: f64,
    pub exit_date: i32,
    pub exit_price: f64,
    pub pnl: f64,
    pub strategy: String,
}

/// 多策略组合回测：对每只股票并行跑 single 回测，再聚合。
///
/// 信号/退出策略以回调注入（M3 完整版由 Python 业务层传入真实策略）。
pub fn run_portfolio_backtest<F, G>(
    klines_by_code: &HashMap<String, KLineSeries>,
    config: &PortfolioConfig,
    signal_at: F,
    exit_at: G,
) -> Result<PortfolioResult>
where
    F: Fn(usize, &KLineSeries, &SingleStrategyConfig) -> Option<f64> + Sync + Send,
    G: Fn(usize, &KLineSeries, &SingleStrategyConfig, f64) -> Option<String> + Sync + Send,
{
    if klines_by_code.is_empty() {
        return Err(CoreError::EmptyDateRange {
            start: "<empty>".into(),
            end: "<empty>".into(),
        });
    }

    // 并行：每只股票独立跑 single 回测
    let per_stock: Vec<(String, SingleStrategyResult)> = klines_by_code
        .par_iter()
        .map(|(code, ks)| {
            let r = run_single_strategy_backtest(ks, &config.single, &signal_at, &exit_at);
            let result = r.unwrap_or_else(|_| empty_result(&config.single, ks.len()));
            (code.clone(), result)
        })
        .collect();

    // 聚合 trades
    let mut all_trades: Vec<NamedTrade> = Vec::new();
    let mut wins = 0_usize;
    let mut count = 0_usize;

    for (code, r) in &per_stock {
        for t in &r.trades {
            all_trades.push(NamedTrade {
                ts_code: code.clone(),
                entry_date: t.entry_date,
                entry_price: t.entry_price,
                exit_date: t.exit_date,
                exit_price: t.exit_price,
                pnl: t.pnl,
                strategy: "single".into(),
            });
            if t.pnl > 0.0 {
                wins += 1;
            }
            count += 1;
        }
    }

    let win_rate = if count > 0 {
        wins as f64 / count as f64
    } else {
        0.0
    };

    // 聚合净值：所有股票 net_values 的逐日平均
    let n = per_stock
        .iter()
        .map(|(_, r)| r.net_values.len())
        .max()
        .unwrap_or(0);
    let initial = config.single.initial_cash;
    let mut net_values = vec![initial; n];
    for (_, r) in &per_stock {
        for (i, v) in r.net_values.iter().enumerate() {
            if i < n {
                net_values[i] += (v - initial) / per_stock.len() as f64;
            }
        }
    }

    let sharpe = compute_sharpe(&net_values);
    let max_dd = compute_max_drawdown(&net_values);
    let calmar = if max_dd > 0.0 { sharpe / max_dd } else { 0.0 };
    let final_value = *net_values.last().unwrap_or(&initial);

    Ok(PortfolioResult {
        net_values,
        cash_history: vec![initial; n],
        trades: all_trades,
        win_rate,
        sharpe_ratio: sharpe,
        max_drawdown: max_dd,
        calmar,
        final_value,
    })
}

fn empty_result(cfg: &SingleStrategyConfig, n: usize) -> SingleStrategyResult {
    SingleStrategyResult {
        net_values: vec![cfg.initial_cash; n],
        cash_history: vec![cfg.initial_cash; n],
        trades: vec![],
        win_rate: 0.0,
        sharpe_ratio: 0.0,
        max_drawdown: 0.0,
        final_value: cfg.initial_cash,
    }
}

fn compute_sharpe(net_values: &[f64]) -> f64 {
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
    (mean / std) * 252_f64.sqrt()
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

    fn make_klines(n: usize, base_price: f64) -> KLineSeries {
        let items = (0..n)
            .map(|i| KLine {
                ts_code: "X".into(),
                trade_date: i as i32,
                open: base_price + i as f64 * 0.1,
                high: base_price + 0.5 + i as f64 * 0.1,
                low: base_price - 0.5 + i as f64 * 0.1,
                close: base_price + i as f64 * 0.1,
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
    fn empty_portfolio_errors() {
        let cfg = PortfolioConfig {
            days: 100,
            max_positions: 5,
            single: SingleStrategyConfig::default(),
        };
        let map: HashMap<String, KLineSeries> = HashMap::new();
        let r = run_portfolio_backtest(&map, &cfg, |_, _, _| None, |_, _, _, _| None);
        assert!(matches!(r, Err(CoreError::EmptyDateRange { .. })));
    }

    #[test]
    fn parallel_aggregation_correct() {
        let mut map = HashMap::new();
        map.insert("A".to_string(), make_klines(100, 10.0));
        map.insert("B".to_string(), make_klines(100, 20.0));
        let cfg = PortfolioConfig {
            days: 100,
            max_positions: 5,
            single: SingleStrategyConfig::default(),
        };
        let r =
            run_portfolio_backtest(&map, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        assert_eq!(r.net_values.len(), 100);
        // 没有信号，所有股票不交易，最终净值 = 初始资金
        assert!((r.final_value - cfg.single.initial_cash).abs() < 1e-6);
    }

    #[test]
    fn trades_aggregated_with_ts_code() {
        let mut map = HashMap::new();
        map.insert("000001.SZ".to_string(), make_klines(100, 10.0));
        map.insert("000002.SZ".to_string(), make_klines(100, 20.0));
        let cfg = PortfolioConfig {
            days: 100,
            max_positions: 5,
            single: SingleStrategyConfig::default(),
        };
        // 两只股票都在第 10 天入场
        let entry_px_a = map["000001.SZ"].items[10].close;
        let entry_px_b = map["000002.SZ"].items[10].close;
        let r = run_portfolio_backtest(
            &map,
            &cfg,
            |i, ks, _| if i == 10 { Some(ks.items[10].close) } else { None },
            |_, _, _, _| None,
        )
        .unwrap();
        // 2 笔交易，每只股票 1 笔
        assert_eq!(r.trades.len(), 2);
        let codes: Vec<&str> = r.trades.iter().map(|t| t.ts_code.as_str()).collect();
        assert!(codes.contains(&"000001.SZ"));
        assert!(codes.contains(&"000002.SZ"));
        // 验证入场价匹配
        let a_trade = r.trades.iter().find(|t| t.ts_code == "000001.SZ").unwrap();
        assert!((a_trade.entry_price - entry_px_a).abs() < 1e-9);
        let b_trade = r.trades.iter().find(|t| t.ts_code == "000002.SZ").unwrap();
        assert!((b_trade.entry_price - entry_px_b).abs() < 1e-9);
    }
}
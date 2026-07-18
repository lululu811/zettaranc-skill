//! proptest attribute tests for zt_backtest_engine.

use std::collections::HashMap;

use proptest::prelude::*;
use zt_backtest_engine::{
    run_portfolio_backtest, run_single_strategy_backtest, PortfolioConfig, SingleStrategyConfig,
};
use zt_core_types::{CoreError, KLine, KLineSeries};

fn make_klines(prices: &[f64], offset: f64) -> KLineSeries {
    let items = prices
        .iter()
        .enumerate()
        .map(|(i, &p)| KLine {
            ts_code: "X".into(),
            trade_date: i as i32,
            open: p,
            high: p + offset,
            low: p - offset,
            close: p,
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

fn default_single_config() -> SingleStrategyConfig {
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

fn rising_prices(n: usize, base: f64, step: f64) -> Vec<f64> {
    (0..n).map(|i| base + i as f64 * step).collect()
}

proptest! {
    #[test]
    fn single_insufficient_data_errors(
        n in 1usize..15,
        bbi in 3usize..10
    ) {
        prop_assume!(n < bbi + 10);
        let prices = vec![10.0_f64; n];
        let ks = make_klines(&prices, 1.0);
        let cfg = SingleStrategyConfig {
            bbi_break_days: bbi,
            ..default_single_config()
        };
        let r = run_single_strategy_backtest(&ks, &cfg, |_, _, _| None, |_, _, _, _| None);
        match r {
            Err(CoreError::InsufficientData { .. }) => {}
            other => panic!("expected InsufficientData, got {:?}", other),
        }
    }

    #[test]
    fn single_trade_count_bounded_by_n(
        n in 30usize..200,
        entry_idx_a in 10usize..30,
        entry_idx_b in 30usize..60,
    ) {
        let n = n.max(150);
        let prices = rising_prices(n, 10.0, 0.1);
        let ks = make_klines(&prices, 0.5);
        let cfg = default_single_config();
        let r = run_single_strategy_backtest(
            &ks,
            &cfg,
            move |i, _, _| {
                if i == entry_idx_a || i == entry_idx_b {
                    Some(prices[i])
                } else {
                    None
                }
            },
            |_, _, _, _| None,
        )
        .unwrap();
        if r.trades.len() > n {
            panic!("trades.len() = {} > n = {}", r.trades.len(), n);
        }
    }

    #[test]
    fn single_no_signal_no_trades(
        n in 30usize..200,
        base in 5.0f64..100.0,
    ) {
        let prices = vec![base; n];
        let ks = make_klines(&prices, 1.0);
        let cfg = default_single_config();
        let r = run_single_strategy_backtest(&ks, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        if r.trades.len() != 0 {
            panic!("expected 0 trades, got {}", r.trades.len());
        }
        if (r.final_value - cfg.initial_cash).abs() > 1e-6 {
            panic!(
                "final_value = {}, expected {}",
                r.final_value,
                cfg.initial_cash
            );
        }
    }

    #[test]
    fn single_net_values_length_matches_klines(
        n in 20usize..150,
    ) {
        let prices = rising_prices(n, 10.0, 0.05);
        let ks = make_klines(&prices, 0.5);
        let cfg = default_single_config();
        let r = run_single_strategy_backtest(&ks, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        if r.net_values.len() != n {
            panic!(
                "net_values.len() = {}, expected {}",
                r.net_values.len(),
                n
            );
        }
    }

    #[test]
    fn single_signal_with_sufficient_cash_trades(
        entry_idx in 15usize..50,
        n_extra in 50usize..100,
    ) {
        let n = entry_idx + n_extra;
        let prices = vec![10.0_f64; n];
        let ks = make_klines(&prices, 1.0);
        let cfg = default_single_config();
        let r = run_single_strategy_backtest(
            &ks,
            &cfg,
            move |i, _, _| if i == entry_idx { Some(10.0) } else { None },
            |_, _, _, _| None,
        )
        .unwrap();
        if r.trades.is_empty() {
            panic!("expected at least 1 trade");
        }
        // alloc = 100_000 * 0.5 = 50_000
        // shares = floor(50_000 / 10 / 100) * 100 = 50 * 100 = 5_000
        // final_value = cash(50_000) + shares * last_close(10) = 100_000
        let expected = cfg.initial_cash;
        if (r.final_value - expected).abs() > 1e-6 {
            panic!(
                "final_value = {}, expected {}",
                r.final_value, expected
            );
        }
    }

    #[test]
    fn single_pnl_matches_price_diff(
        entry_idx in 15usize..50,
    ) {
        let n = entry_idx + 50;
        let prices = rising_prices(n, 10.0, 0.1);
        let ks = make_klines(&prices, 0.5);
        let cfg = default_single_config();
        let r = run_single_strategy_backtest(
            &ks,
            &cfg,
            move |i, _, _| if i == entry_idx { Some(prices[entry_idx]) } else { None },
            |_, _, _, _| None,
        )
        .unwrap();
        if r.trades.len() != 1 {
            panic!("expected 1 trade, got {}", r.trades.len());
        }
        let t = &r.trades[0];
        let entry = t.entry_price;
        let exit = t.exit_price;
        let shares = (cfg.initial_cash * cfg.position_pct / entry / 100.0).floor() * 100.0;
        let expected_pnl = (exit - entry) * shares;
        if (t.pnl - expected_pnl).abs() > 1e-3 {
            panic!(
                "trade pnl = {}, expected {} (entry={}, exit={}, shares={})",
                t.pnl, expected_pnl, entry, exit, shares
            );
        }
    }

    // portfolio
    #[test]
    fn portfolio_empty_errors_unused(_unused: ()) {
        let map: HashMap<String, KLineSeries> = HashMap::new();
        let cfg = PortfolioConfig {
            days: 100,
            max_positions: 5,
            single: default_single_config(),
        };
        let r = run_portfolio_backtest(&map, &cfg, |_, _, _| None, |_, _, _, _| None);
        match r {
            Err(CoreError::EmptyDateRange { .. }) => {}
            other => panic!("expected EmptyDateRange, got {:?}", other),
        }
    }

    #[test]
    fn portfolio_trades_have_known_codes(
        n_stocks in 1usize..5,
    ) {
        let mut map: HashMap<String, KLineSeries> = HashMap::new();
        let codes: Vec<String> = (0..n_stocks)
            .map(|i| format!("{:06}.SZ", i))
            .collect();
        let prices = rising_prices(100, 10.0, 0.1);
        for code in &codes {
            map.insert(code.clone(), make_klines(&prices, 0.5));
        }
        let cfg = PortfolioConfig {
            days: 100,
            max_positions: 5,
            single: default_single_config(),
        };
        let r = run_portfolio_backtest(&map, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        for t in &r.trades {
            if !map.contains_key(&t.ts_code) {
                panic!("unknown ts_code in trade: {}", t.ts_code);
            }
        }
    }

    #[test]
    fn portfolio_trades_aggregate(
        n_stocks in 1usize..4,
    ) {
        let mut map: HashMap<String, KLineSeries> = HashMap::new();
        let prices = vec![10.0_f64; 100];
        for i in 0..n_stocks {
            map.insert(format!("S{:02}", i), make_klines(&prices, 1.0));
        }
        let cfg = PortfolioConfig {
            days: 100,
            max_positions: 5,
            single: default_single_config(),
        };
        let r = run_portfolio_backtest(&map, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        if r.trades.len() != 0 {
            panic!("expected 0 trades (no signal), got {}", r.trades.len());
        }
    }

    #[test]
    fn portfolio_net_values_length_is_max(
        n_stocks in 1usize..4,
        base_len in 50usize..150,
    ) {
        let mut map: HashMap<String, KLineSeries> = HashMap::new();
        for i in 0..n_stocks {
            let len = base_len + i;
            let prices = rising_prices(len, 10.0, 0.1);
            map.insert(format!("S{:02}", i), make_klines(&prices, 0.5));
        }
        let cfg = PortfolioConfig {
            days: base_len + n_stocks,
            max_positions: 5,
            single: default_single_config(),
        };
        let r = run_portfolio_backtest(&map, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        let expected_max = base_len + n_stocks - 1;
        if r.net_values.len() != expected_max {
            panic!(
                "net_values.len() = {}, expected {}",
                r.net_values.len(),
                expected_max
            );
        }
    }

    #[test]
    fn portfolio_no_signal_final_value(
        n_stocks in 1usize..5,
    ) {
        let mut map: HashMap<String, KLineSeries> = HashMap::new();
        let prices = vec![10.0_f64; 100];
        for i in 0..n_stocks {
            map.insert(format!("S{:02}", i), make_klines(&prices, 1.0));
        }
        let cfg = PortfolioConfig {
            days: 100,
            max_positions: 5,
            single: default_single_config(),
        };
        let r = run_portfolio_backtest(&map, &cfg, |_, _, _| None, |_, _, _, _| None).unwrap();
        if (r.final_value - cfg.single.initial_cash).abs() > 1e-6 {
            panic!(
                "final_value = {}, expected {}",
                r.final_value, cfg.single.initial_cash
            );
        }
    }
}
//! proptest attribute tests for zt_indicators::compute_atr.
//!
//! 不变式覆盖：
//! 1. atr[i] >= 0（非负性）
//! 2. 窗口边界：window < 1 报错；数据不足报错
//! 3. 零波动（high == low）：所有 TR 为 0
//! 4. ATR 输出长度 == 输入 K 线数
//! 5. ATR 上界：rolling mean 不超过 max(tr)

use proptest::prelude::*;
use zt_core_types::{CoreError, KLine, KLineSeries};
use zt_indicators::compute_atr;

/// 构造 KLineSeries：prices[i] 是 close，high/low 由 close ± offset 决定。
fn make_klines(prices: &[f64], offset: f64) -> KLineSeries {
    let items = prices
        .iter()
        .enumerate()
        .map(|(i, &p)| KLine {
            ts_code: "TEST".into(),
            trade_date: i as i32,
            open: p,
            high: p + offset,
            low: p - offset,
            close: p,
            vol: 0.0,
            amount: 0.0,
            pct_chg: 0.0,
            vol_ratio: None,
            is_limit_up: None,
            is_limit_down: None,
        })
        .collect();
    KLineSeries { items }
}

/// 自定义 Strategy：任意长度 >= window 的 prices 序列。
fn price_series(min_len: usize) -> impl Strategy<Value = Vec<f64>> {
    prop::collection::vec(1.0f64..1000.0, min_len..200)
}

proptest! {
    /// 不变式 1：ATR 输出与输入 K 线数等长。
    #[test]
    fn atr_output_length_matches_input(
        window in 1usize..30,
        prices in price_series(50)
    ) {
        let ks = make_klines(&prices, 1.0);
        let atr = compute_atr(&ks, window).unwrap();
        prop_assert_eq!(atr.len(), ks.len());
    }

    /// 不变式 2：ATR 全部非负且有限。
    #[test]
    fn atr_is_non_negative(
        window in 1usize..30,
        prices in price_series(50)
    ) {
        let ks = make_klines(&prices, 1.0);
        let atr = compute_atr(&ks, window).unwrap();
        for (i, &v) in atr.iter().enumerate() {
            prop_assert!(v >= 0.0);
            prop_assert!(v.is_finite());
            // panic if not, with debug info
            if !(v >= 0.0 && v.is_finite()) {
                panic!("atr[{}] = {} violated non-negative+finite", i, v);
            }
        }
    }

    /// 不变式 3：window = 0 必须报错（InvalidParameter）。
    #[test]
    fn atr_zero_window_errors(prices in price_series(20)) {
        let ks = make_klines(&prices, 1.0);
        let r = compute_atr(&ks, 0);
        match r {
            Err(CoreError::InvalidParameter { .. }) => {}
            other => panic!("expected InvalidParameter, got {:?}", other),
        }
    }

    /// 不变式 4：数据不足必须报错（InsufficientData）。
    #[test]
    fn atr_insufficient_data_errors(
        window in 2usize..50,
        n in 1usize..30
    ) {
        prop_assume!(n < window);
        let prices = vec![10.0_f64; n];
        let ks = make_klines(&prices, 1.0);
        let r = compute_atr(&ks, window);
        match r {
            Err(CoreError::InsufficientData { .. }) => {}
            other => panic!("expected InsufficientData, got {:?}", other),
        }
    }

    /// 不变式 5：零波动（high == low 即 offset = 0）时，TR 全部为 0。
    #[test]
    fn atr_zero_volatility_is_zero(
        window in 1usize..20,
        base in 1.0f64..1000.0,
        n in 20usize..100
    ) {
        let prices = vec![base; n];
        let ks = make_klines(&prices, 0.0); // high == low == close
        let atr = compute_atr(&ks, window).unwrap();
        for (i, &v) in atr.iter().enumerate() {
            if v != 0.0 {
                panic!("atr[{}] = {} expected 0", i, v);
            }
        }
    }

    /// 不变式 6：纯涨序列（close 单调递增且无跳空），ATR 在窗口填满之后等于常量。
    /// TR_0 = 2*offset（首根 K 线无 prev_close）
    /// TR_t (t>=1) = max(2*offset, step+offset, |step - offset|)
    ///            = step + offset (step >= offset)
    ///            = 2*offset   (step <  offset)
    /// ATR[i>=window] 应等于上面那个常量。
    #[test]
    fn atr_monotonic_up_constant(
        window in 2usize..10,
        offset in 0.1f64..10.0,
        step in 0.1f64..5.0,
        n_extra in 30usize..60
    ) {
        let n = window + n_extra;
        let prices: Vec<f64> = (0..n).map(|i| 100.0 + i as f64 * step).collect();
        let ks = make_klines(&prices, offset);
        let atr = compute_atr(&ks, window).unwrap();
        let expected: f64 = if step >= offset { step + offset } else { 2.0 * offset };
        // 从 i=window 开始（tr[0] 已经滚出窗口）
        for i in window..atr.len() {
            let v = atr[i];
            if (v - expected).abs() > 1e-6 {
                panic!(
                    "atr[{}] = {}, expected {} (window={}, offset={}, step={})",
                    i, v, expected, window, offset, step
                );
            }
        }
    }

    /// 不变式 7：ATR 不超过整个序列的最大 TR（rolling mean 不超过 max）。
    #[test]
    fn atr_bounded_by_max_tr(
        window in 1usize..15,
        prices in price_series(40)
    ) {
        let ks = make_klines(&prices, 1.0);
        // 先手算所有 TR
        let mut tr: Vec<f64> = vec![0.0; prices.len()];
        tr[0] = 2.0_f64;
        for i in 1..prices.len() {
            let prev_close: f64 = prices[i - 1];
            let range1: f64 = 2.0;
            let range2: f64 = ((prices[i] + 1.0) - prev_close).abs();
            let range3: f64 = ((prices[i] - 1.0) - prev_close).abs();
            tr[i] = range1.max(range2).max(range3);
        }
        let max_tr: f64 = tr.iter().cloned().fold(0.0_f64, f64::max);
        let atr = compute_atr(&ks, window).unwrap();
        for i in (window - 1)..atr.len() {
            let v = atr[i];
            if v > max_tr + 1e-9 {
                panic!("atr[{}] = {} > max_tr = {}", i, v, max_tr);
            }
        }
    }

    /// 不变式 8：常量 close + 任何 offset → ATR 等于 2*offset（除前 window-1 位）。
    #[test]
    fn atr_constant_close_constant_atr(
        window in 1usize..20,
        offset in 0.0f64..10.0,
        n in 30usize..80
    ) {
        let prices = vec![42.0_f64; n];
        let ks = make_klines(&prices, offset);
        let atr = compute_atr(&ks, window).unwrap();
        let expected: f64 = 2.0 * offset;
        for i in (window - 1)..atr.len() {
            let v = atr[i];
            if (v - expected).abs() > 1e-9 {
                panic!("atr[{}] = {}, expected {}", i, v, expected);
            }
        }
    }
}

//! ATR（Average True Range）实现。
//!
//! TR_t = max(high_t - low_t, |high_t - close_{t-1}|, |low_t - close_{t-1}|)
//! ATR_t = mean(TR_{t-window+1..=t})
//!
//! 输出长度 = len(klines)。前 (window-1) 个位置是 NaN/0.0，按 Python 现有约定
//! 用 0.0 占位（M1 末尾会和 Python 实现对比确认）。

use zt_core_types::{CoreError, KLineSeries, Result};

const DEFAULT_WINDOW: usize = 14;

pub fn compute_atr(klines: &KLineSeries, window: usize) -> Result<Vec<f64>> {
    if window == 0 {
        return Err(CoreError::InvalidParameter {
            field: "window".into(),
            value: 0.0,
            constraint: ">= 1".into(),
        });
    }
    if klines.len() < window {
        return Err(CoreError::InsufficientData {
            need: window,
            got: klines.len(),
        });
    }

    let n = klines.len();
    let mut tr = vec![0.0_f64; n];
    // 第一根 K 线的 TR = high - low
    tr[0] = klines.items[0].high - klines.items[0].low;

    for i in 1..n {
        let prev_close = klines.items[i - 1].close;
        let hi = klines.items[i].high;
        let lo = klines.items[i].low;
        let range1 = hi - lo;
        let range2 = (hi - prev_close).abs();
        let range3 = (lo - prev_close).abs();
        tr[i] = range1.max(range2).max(range3);
    }

    // ATR = rolling mean of TR over `window` days, 对齐到 tr[i]
    // 前 (window-1) 个位置按 Python 现有行为：返回 0.0
    let mut atr = vec![0.0_f64; n];
    let mut sum = 0.0_f64;
    for i in 0..n {
        sum += tr[i];
        if i >= window {
            sum -= tr[i - window];
        }
        if i + 1 >= window {
            atr[i] = sum / window as f64;
        }
    }

    Ok(atr)
}

pub fn compute_atr_default(klines: &KLineSeries) -> Result<Vec<f64>> {
    compute_atr(klines, DEFAULT_WINDOW)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_klines(prices: &[f64]) -> KLineSeries {
        let items = prices
            .iter()
            .enumerate()
            .map(|(i, &p)| zt_core_types::KLine {
                ts_code: "TEST".into(),
                trade_date: i as i32,
                open: p,
                high: p + 1.0,
                low: p - 1.0,
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

    #[test]
    fn atr_empty_window_errors() {
        let ks = make_klines(&[1.0; 20]);
        assert!(matches!(
            compute_atr(&ks, 0),
            Err(CoreError::InvalidParameter { .. })
        ));
    }

    #[test]
    fn atr_insufficient_data_errors() {
        let ks = make_klines(&[1.0; 5]);
        assert!(matches!(
            compute_atr(&ks, 14),
            Err(CoreError::InsufficientData { .. })
        ));
    }

    #[test]
    fn atr_constant_prices_is_zero() {
        let ks = make_klines(&[10.0; 50]);
        let atr = compute_atr(&ks, 14).unwrap();
        // 常数价格：tr = 2（high-low），rolling mean 后所有非零位置都是 2
        for i in 13..atr.len() {
            assert!((atr[i] - 2.0).abs() < 1e-12, "atr[{i}]={}", atr[i]);
        }
    }

    #[test]
    fn atr_first_13_positions_are_zero() {
        let ks = make_klines(&(0..50).map(|i| i as f64).collect::<Vec<_>>());
        let atr = compute_atr(&ks, 14).unwrap();
        for i in 0..13 {
            assert_eq!(atr[i], 0.0);
        }
    }
}

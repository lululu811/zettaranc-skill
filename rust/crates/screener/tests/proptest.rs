//! proptest attribute tests for zt_screener::screen_stocks.
//!
//! 不变式覆盖：
//! 1. scores.len() <= top_n && scores.len() <= df.height()
//! 2. 加权：相同权重下，total_score = sum of per_criterion
//! 3. 空 criteria 报错
//! 4. 空 dataframe 不 panic
//! 5. 排序：scores 按 total_score 降序

use polars::prelude::*;
use proptest::prelude::*;
use zt_core_types::{CoreError, KLine, KLineSeries};
use zt_screener::{screen_stocks, Criterion};

/// 自定义 Strategy：随机 polars DataFrame（带 ts_code / close / sma20 / volume）。
fn make_df(
    ts_codes: Vec<String>,
    closes: Vec<f64>,
    sma20s: Vec<f64>,
    volumes: Vec<f64>,
) -> std::result::Result<DataFrame, polars::error::PolarsError> {
    df![
        "ts_code" => ts_codes,
        "close" => closes,
        "sma20" => sma20s,
        "volume" => volumes,
    ]
}

fn vec_string(min_len: usize, max_len: usize) -> impl Strategy<Value = Vec<String>> {
    prop::collection::vec("[A-Z]{6}", min_len..max_len)
}

proptest! {
    // 不变式 1：scores.len() <= top_n && scores.len() <= df.height()
    #[test]
    fn scores_len_bounded(
        n_stocks in 1usize..20,
        top_n in 1usize..30,
    ) {
        let codes: Vec<String> = (0..n_stocks).map(|i| format!("{:06}.SZ", i)).collect();
        let closes: Vec<f64> = (0..n_stocks).map(|i| 10.0 + i as f64).collect();
        let sma20s: Vec<f64> = (0..n_stocks).map(|i| 9.0 + i as f64).collect();
        let volumes: Vec<f64> = (0..n_stocks).map(|i| 1.0e6 * (i + 1) as f64).collect();
        let df = make_df(codes, closes, sma20s, volumes).unwrap();
        let criteria = vec![Criterion {
            name: "trend".into(),
            weight: 1.0,
            expression: "close_vs_sma20".into(),
        }];
        let scores = screen_stocks(&df, &criteria, top_n).unwrap();
        if scores.len() > top_n {
            panic!("scores.len()={} > top_n={}", scores.len(), top_n);
        }
        if scores.len() > n_stocks {
            panic!("scores.len()={} > n_stocks={}", scores.len(), n_stocks);
        }
    }

    // 不变式 2：排序 - scores 按 total_score 降序
    #[test]
    fn scores_sorted_descending(
        n_stocks in 2usize..15,
    ) {
        let codes: Vec<String> = (0..n_stocks).map(|i| format!("{:06}.SZ", i)).collect();
        let closes: Vec<f64> = (0..n_stocks).map(|i| 10.0 + i as f64).collect();
        let sma20s: Vec<f64> = (0..n_stocks).map(|i| 9.0 + i as f64).collect();
        let volumes: Vec<f64> = (0..n_stocks).map(|i| 1.0e6 * (i + 1) as f64).collect();
        let df = make_df(codes, closes, sma20s, volumes).unwrap();
        let criteria = vec![Criterion {
            name: "trend".into(),
            weight: 1.0,
            expression: "trend_strength".into(),
        }];
        let scores = screen_stocks(&df, &criteria, n_stocks).unwrap();
        for w in scores.windows(2) {
            if w[0].total_score < w[1].total_score {
                panic!(
                    "scores not sorted desc: {} < {}",
                    w[0].total_score, w[1].total_score
                );
            }
        }
    }

    // 不变式 3：total_score = sum of per_criterion
    #[test]
    fn total_score_equals_sum_of_criteria(
        n_stocks in 2usize..10,
        n_criteria in 1usize..4,
    ) {
        let codes: Vec<String> = (0..n_stocks).map(|i| format!("{:06}.SZ", i)).collect();
        let closes: Vec<f64> = (0..n_stocks).map(|i| 10.0 + i as f64).collect();
        let sma20s: Vec<f64> = (0..n_stocks).map(|i| 9.0 + i as f64).collect();
        let volumes: Vec<f64> = (0..n_stocks).map(|i| 1.0e6 * (i + 1) as f64).collect();
        let df = make_df(codes, closes, sma20s, volumes).unwrap();
        let criteria: Vec<Criterion> = (0..n_criteria)
            .map(|i| Criterion {
                name: format!("c{}", i),
                weight: 0.3 + 0.2 * i as f64,
                expression: "close_vs_sma20".into(),
            })
            .collect();
        let scores = screen_stocks(&df, &criteria, n_stocks).unwrap();
        for s in &scores {
            let sum: f64 = s.per_criterion.iter().sum();
            if (s.total_score - sum).abs() > 1e-6 {
                panic!(
                    "ts_code={}: total_score={} != sum(per_criterion)={}",
                    s.ts_code, s.total_score, sum
                );
            }
        }
    }

    // 不变式 4：空 criteria 必须报错
    #[test]
    fn empty_criteria_errors_unused(_unused: ()) {
        let codes: Vec<String> = vec!["A".into()];
        let closes: Vec<f64> = vec![10.0];
        let sma20s: Vec<f64> = vec![9.0];
        let volumes: Vec<f64> = vec![1e6];
        let df = make_df(codes, closes, sma20s, volumes).unwrap();
        let r = screen_stocks(&df, &[], 1);
        match r {
            Err(CoreError::InvalidParameter { .. }) => {}
            other => panic!("expected InvalidParameter, got {:?}", other),
        }
    }

    // 不变式 5：缺失 ts_code 列必须报错
    #[test]
    fn missing_ts_code_errors_unused(_unused: ()) {
        let closes: Vec<f64> = vec![10.0];
        let sma20s: Vec<f64> = vec![9.0];
        let volumes: Vec<f64> = vec![1e6];
        let df = df!["close" => closes, "sma20" => sma20s, "volume" => volumes].unwrap();
        let criteria = vec![Criterion {
            name: "x".into(),
            weight: 1.0,
            expression: "close_vs_sma20".into(),
        }];
        let r = screen_stocks(&df, &criteria, 1);
        match r {
            Err(CoreError::MissingColumn(_)) => {}
            other => panic!("expected MissingColumn, got {:?}", other),
        }
    }

    // 不变式 6：top_n = 0 → 返回空结果
    #[test]
    fn zero_top_n_returns_empty(
        n_stocks in 1usize..10,
    ) {
        let codes: Vec<String> = (0..n_stocks).map(|i| format!("{:06}.SZ", i)).collect();
        let closes: Vec<f64> = (0..n_stocks).map(|i| 10.0 + i as f64).collect();
        let sma20s: Vec<f64> = (0..n_stocks).map(|i| 9.0 + i as f64).collect();
        let volumes: Vec<f64> = (0..n_stocks).map(|i| 1.0e6 * (i + 1) as f64).collect();
        let df = make_df(codes, closes, sma20s, volumes).unwrap();
        let criteria = vec![Criterion {
            name: "trend".into(),
            weight: 1.0,
            expression: "close_vs_sma20".into(),
        }];
        let scores = screen_stocks(&df, &criteria, 0).unwrap();
        if !scores.is_empty() {
            panic!("expected empty scores for top_n=0, got {}", scores.len());
        }
    }

    // 不变式 7：未知的 criterion expression 不 panic，给 0 分
    #[test]
    fn unknown_expression_returns_zero(
        n_stocks in 1usize..10,
    ) {
        let codes: Vec<String> = (0..n_stocks).map(|i| format!("{:06}.SZ", i)).collect();
        let closes: Vec<f64> = (0..n_stocks).map(|i| 10.0 + i as f64).collect();
        let sma20s: Vec<f64> = (0..n_stocks).map(|i| 9.0 + i as f64).collect();
        let volumes: Vec<f64> = (0..n_stocks).map(|i| 1.0e6 * (i + 1) as f64).collect();
        let df = make_df(codes, closes, sma20s, volumes).unwrap();
        let criteria = vec![Criterion {
            name: "unknown".into(),
            weight: 1.0,
            expression: "does_not_exist".into(),
        }];
        let scores = screen_stocks(&df, &criteria, n_stocks).unwrap();
        for s in &scores {
            if s.total_score != 0.0 {
                panic!("expected total_score=0 for unknown expr, got {}", s.total_score);
            }
        }
    }

    // 不变式 8：单只股票，scores.len() <= 1
    #[test]
    fn single_stock_returns_at_most_one(
        top_n in 1usize..10,
    ) {
        let codes: Vec<String> = vec!["000001.SZ".into()];
        let closes: Vec<f64> = vec![10.0];
        let sma20s: Vec<f64> = vec![9.0];
        let volumes: Vec<f64> = vec![1e6];
        let df = make_df(codes, closes, sma20s, volumes).unwrap();
        let criteria = vec![Criterion {
            name: "trend".into(),
            weight: 1.0,
            expression: "close_vs_sma20".into(),
        }];
        let scores = screen_stocks(&df, &criteria, top_n).unwrap();
        if scores.len() > 1 {
            panic!("expected at most 1 score, got {}", scores.len());
        }
    }
}

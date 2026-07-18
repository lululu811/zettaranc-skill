//! 选股评分引擎：用 polars DataFrame 直接计算每只股票的综合评分。
//!
//! 简化版（M5 stub）：支持 3 种内置评分规则，按 weight 加权求和。

use polars::prelude::*;
use serde::{Deserialize, Serialize};
use zt_core_types::{CoreError, Result};

#[derive(Debug, Clone, Deserialize)]
pub struct Criterion {
    pub name: String,
    pub weight: f64,
    /// 内置规则名：close_vs_sma20 / volume_breakout / trend_strength
    pub expression: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StockScore {
    pub ts_code: String,
    pub total_score: f64,
    pub per_criterion: Vec<f64>,
}

/// 主入口：按 criteria 加权求和，按 total_score 降序返回 top N。
///
/// 期望 df 至少包含列：ts_code, close, sma20（已预计算）, volume
pub fn screen_stocks(
    df: &DataFrame,
    criteria: &[Criterion],
    top_n: usize,
) -> Result<Vec<StockScore>> {
    if !df.schema().contains("ts_code") {
        return Err(CoreError::MissingColumn("ts_code".into()));
    }
    if criteria.is_empty() {
        return Err(CoreError::InvalidParameter {
            field: "criteria".into(),
            value: 0.0,
            constraint: "non-empty".into(),
        });
    }

    let codes = df.column("ts_code")?.str()?;
    let n = df.height();
    let mut total_scores = vec![0.0_f64; n];
    let mut per_criterion: Vec<Vec<f64>> = vec![vec![0.0; n]; criteria.len()];

    for (ci, criterion) in criteria.iter().enumerate() {
        let scores = compute_criterion(df, criterion)?;
        for (i, s) in scores.iter().enumerate() {
            per_criterion[ci][i] = *s;
            total_scores[i] += s;
        }
    }

    // 按 total_scores 降序排序
    let mut indexed: Vec<usize> = (0..n).collect();
    indexed.sort_by(|&a, &b| {
        total_scores[b]
            .partial_cmp(&total_scores[a])
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let limit = top_n.min(n);
    let mut out = Vec::with_capacity(limit);
    for &idx in indexed.iter().take(limit) {
        let per: Vec<f64> = (0..criteria.len())
            .map(|ci| per_criterion[ci][idx])
            .collect();
        out.push(StockScore {
            ts_code: codes.get(idx).unwrap_or("").to_string(),
            total_score: total_scores[idx],
            per_criterion: per,
        });
    }
    Ok(out)
}

fn compute_criterion(df: &DataFrame, criterion: &Criterion) -> Result<Vec<f64>> {
    let n = df.height();
    match criterion.expression.as_str() {
        "close_vs_sma20" => {
            let close = df.column("close")?.f64()?;
            let sma = df.column("sma20")?.f64()?;
            let w = criterion.weight;
            Ok((0..n)
                .map(|i| match (close.get(i), sma.get(i)) {
                    (Some(c), Some(s)) if c > s => w,
                    _ => 0.0,
                })
                .collect())
        }
        "volume_breakout" => {
            // 简化：volume > sma_volume * 1.5 计分（无 rolling mean）
            let vol = df.column("volume")?.f64()?;
            let w = criterion.weight;
            let mean_vol: f64 = (0..n).filter_map(|i| vol.get(i)).sum::<f64>() / n as f64;
            Ok((0..n)
                .map(|i| match vol.get(i) {
                    Some(v) if v > mean_vol * 1.5 => w,
                    _ => 0.0,
                })
                .collect())
        }
        "trend_strength" => {
            let close = df.column("close")?.f64()?;
            let sma = df.column("sma20")?.f64()?;
            let w = criterion.weight;
            Ok((0..n)
                .map(|i| match (close.get(i), sma.get(i)) {
                    (Some(c), Some(s)) if s > 0.0 => ((c - s) / s).max(0.0) * w,
                    _ => 0.0,
                })
                .collect())
        }
        _ => Ok(vec![0.0; n]), // 未知规则返回零分
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_df() -> DataFrame {
        df![
            "ts_code" => ["A", "B", "C", "D"],
            "close" => [10.0, 20.0, 30.0, 40.0],
            "sma20" => [9.0, 22.0, 28.0, 41.0],
            "volume" => [1.0e6, 2.0e6, 3.0e6, 4.0e6],
        ]
        .unwrap()
    }

    #[test]
    fn screens_close_above_sma20() {
        let df = make_test_df();
        let criteria = vec![Criterion {
            name: "trend".into(),
            weight: 1.0,
            expression: "close_vs_sma20".into(),
        }];
        let scores = screen_stocks(&df, &criteria, 4).unwrap();
        // A (10>9) ✓, B (20<22) ✗, C (30>28) ✓, D (40<41) ✗
        // 排序后：A, C, B, D
        assert_eq!(scores[0].ts_code, "A");
        assert_eq!(scores[1].ts_code, "C");
        assert_eq!(scores[2].ts_code, "B");
        assert_eq!(scores[3].ts_code, "D");
    }

    #[test]
    fn missing_ts_code_errors() {
        let df = df!["close" => [10.0], "sma20" => [9.0]].unwrap();
        let criteria = vec![Criterion {
            name: "x".into(),
            weight: 1.0,
            expression: "close_vs_sma20".into(),
        }];
        let r = screen_stocks(&df, &criteria, 1);
        assert!(matches!(r, Err(CoreError::MissingColumn(_))));
    }

    #[test]
    fn empty_criteria_errors() {
        let df = make_test_df();
        let r = screen_stocks(&df, &[], 1);
        assert!(matches!(r, Err(CoreError::InvalidParameter { .. })));
    }

    #[test]
    fn top_n_limits_results() {
        let df = make_test_df();
        let criteria = vec![Criterion {
            name: "trend".into(),
            weight: 1.0,
            expression: "close_vs_sma20".into(),
        }];
        let scores = screen_stocks(&df, &criteria, 2).unwrap();
        assert_eq!(scores.len(), 2);
    }

    #[test]
    fn multiple_criteria_combine_scores() {
        let df = make_test_df();
        let criteria = vec![
            Criterion {
                name: "trend".into(),
                weight: 1.0,
                expression: "close_vs_sma20".into(),
            },
            Criterion {
                name: "vol".into(),
                weight: 0.5,
                expression: "volume_breakout".into(),
            },
        ];
        let scores = screen_stocks(&df, &criteria, 4).unwrap();
        // A, C 满足 close_vs_sma20 (weight=1.0)，volume_breakout 可能也给分
        assert_eq!(scores[0].ts_code, "A"); // A 和 C 都是 1.0+，但排序应稳定
        assert!(scores[0].total_score >= scores[3].total_score);
    }
}

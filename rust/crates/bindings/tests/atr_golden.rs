//! 用 Python 生成的 golden file 验证 Rust ATR 实现的数值等价性。

use approx::assert_abs_diff_eq;
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Deserialize)]
struct GoldenCase {
    name: String,
    #[allow(dead_code)]
    input: Vec<serde_json::Value>,
    window: usize,
    expected: Vec<f64>,
}

#[derive(Deserialize)]
struct GoldenFile {
    cases: Vec<GoldenCase>,
}

fn load_golden() -> GoldenFile {
    // CARGO_MANIFEST_DIR = rust/crates/bindings；向上 3 层到 repo root
    let manifest = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let path = manifest
        .join("..")
        .join("..")
        .join("..")
        .join("tests")
        .join("golden")
        .join("atr")
        .join("basic.json");
    let data = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("read golden {}: {e}", path.display()));
    serde_json::from_str(&data).expect("parse golden JSON")
}

fn json_to_kline(v: &serde_json::Value) -> zt_core_types::KLine {
    use serde_json::Value::*;
    let o = v.as_object().expect("input must be object");
    let fld = |k: &str| -> f64 {
        o.get(k)
            .and_then(|v| v.as_f64())
            .unwrap_or_else(|| panic!("missing/invalid f64 field {k}"))
    };
    zt_core_types::KLine {
        ts_code: o
            .get("ts_code")
            .and_then(|v| v.as_str())
            .unwrap_or("TEST")
            .to_string(),
        trade_date: o.get("trade_date").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
        open: fld("open"),
        high: fld("high"),
        low: fld("low"),
        close: fld("close"),
        vol: fld("vol"),
        amount: fld("amount"),
        pct_chg: fld("pct_chg"),
        vol_ratio: o.get("vol_ratio").and_then(|v| v.as_f64()),
        is_limit_up: o.get("is_limit_up").and_then(|v| v.as_bool()),
        is_limit_down: o.get("is_limit_down").and_then(|v| v.as_bool()),
    }
}

#[test]
fn rust_atr_matches_python_for_all_cases() {
    let g = load_golden();
    assert!(!g.cases.is_empty(), "golden file is empty");

    for case in &g.cases {
        let items: Vec<zt_core_types::KLine> = case.input.iter().map(json_to_kline).collect();
        let series = zt_core_types::KLineSeries { items };

        let got = zt_indicators::compute_atr(&series, case.window)
            .unwrap_or_else(|e| panic!("compute_atr({}) failed: {e}", case.name));

        assert_eq!(
            got.len(),
            case.expected.len(),
            "length mismatch for case {}",
            case.name
        );
        for (i, (g, w)) in got.iter().zip(case.expected.iter()).enumerate() {
            assert_abs_diff_eq!(g, w, epsilon = 1e-9);
        }
        println!("✓ case {} passed ({} values)", case.name, got.len());
    }
}

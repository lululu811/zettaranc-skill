//! proptest attribute tests for zt_grid_search::run_grid_search.
//!
//! 不变式覆盖：
//! 1. results.len() == splits.len() * grid.len()（笛卡尔积）
//! 2. 空 grid 必须报错
//! 3. 单 split：results.len() == grid.len()
//! 4. 同一参数在多个 split 上都有结果
//! 5. walk-forward splits 互不重叠（每个 test 日期只在 1 个 split 里）

use proptest::prelude::*;
use zt_core_types::{CoreError, KLine, KLineSeries};
use zt_grid_search::{make_walk_forward_splits, run_grid_search, ParamSet, WalkForwardSplit};

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

proptest! {
    // 不变式 1：results.len() == splits.len() * grid.len()
    #[test]
    fn grid_search_results_count(
        total in 100usize..300,
        train in 20usize..60,
        test in 10usize..40,
        grid_size in 1usize..6,
    ) {
        // 保证 train + test <= total
        prop_assume!(train + test <= total);
        let klines = make_klines(total);
        let splits = match make_walk_forward_splits(total, train, test) {
            Ok(s) => s,
            Err(_) => return Ok(()),
        };
        let grid: Vec<ParamSet> = (0..grid_size)
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
        if results.len() != splits.len() * grid.len() {
            panic!(
                "results.len() = {}, expected {} (splits={} * grid={})",
                results.len(),
                splits.len() * grid.len(),
                splits.len(),
                grid.len()
            );
        }
    }

    // 不变式 2：空 grid 必须报错
    #[test]
    fn empty_grid_errors(_unused: ()) {
        let klines = make_klines(100);
        let splits = make_walk_forward_splits(100, 30, 30).unwrap();
        let r = run_grid_search(&klines, &[], &splits, 100_000.0);
        match r {
            Err(CoreError::InvalidParameter { .. }) => {}
            other => panic!("expected InvalidParameter, got {:?}", other),
        }
    }

    // 不变式 3：单 split == results.len() == grid.len()
    #[test]
    fn single_split_equals_grid_size(
        total in 60usize..150,
        train in 20usize..40,
        test in 20usize..40,
        grid_size in 1usize..6,
    ) {
        prop_assume!(train + test <= total);
        let klines = make_klines(total);
        let splits = match make_walk_forward_splits(total, train, test) {
            Ok(s) => s,
            Err(_) => return Ok(()),
        };
        prop_assume!(splits.len() == 1);
        let grid: Vec<ParamSet> = (0..grid_size)
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
        if results.len() != grid.len() {
            panic!(
                "results.len() = {}, expected {} (single split)",
                results.len(),
                grid.len()
            );
        }
    }

    // 不变式 4：split 之间 test_range 不重叠（每个日期只在 1 个 test 窗口内）
    #[test]
    fn walk_forward_test_ranges_no_overlap(
        total in 50usize..200,
        train in 10usize..40,
        test in 10usize..30,
    ) {
        prop_assume!(train + test <= total);
        let splits = match make_walk_forward_splits(total, train, test) {
            Ok(s) => s,
            Err(_) => return Ok(()),
        };
        let mut seen = std::collections::HashSet::new();
        for s in &splits {
            for i in s.test_start..s.test_end {
                if !seen.insert(i) {
                    panic!("test date {} covered by multiple splits", i);
                }
            }
        }
    }

    // 不变式 5：walk_forward splits 内部结构有效
    // （train_end == test_start > train_start, test_end > test_start, 所有值在 [0, total] 范围）
    #[test]
    fn walk_forward_splits_structure(
        total in 80usize..200,
        train in 15usize..40,
        test in 10usize..25,
    ) {
        prop_assume!(train + test <= total);
        let splits = match make_walk_forward_splits(total, train, test) {
            Ok(s) => s,
            Err(_) => return Ok(()),
        };
        for s in &splits {
            // train 窗口：train_start < train_end
            if s.train_start >= s.train_end {
                panic!(
                    "invalid train window: train_start={} >= train_end={}",
                    s.train_start, s.train_end
                );
            }
            // test 紧跟 train
            if s.test_start != s.train_end {
                panic!(
                    "test_start={} != train_end={}",
                    s.test_start, s.train_end
                );
            }
            // test 窗口非空
            if s.test_start >= s.test_end {
                panic!(
                    "invalid test window: test_start={} >= test_end={}",
                    s.test_start, s.test_end
                );
            }
            // 范围在 total 内
            if s.test_end > total {
                panic!("test_end={} > total={}", s.test_end, total);
            }
        }
    }

    // 不变式 6：walk_forward train/test 窗口大小 = train_days / test_days
    #[test]
    fn walk_forward_window_sizes(
        total in 60usize..200,
        train in 10usize..40,
        test in 10usize..30,
    ) {
        prop_assume!(train + test <= total);
        let splits = match make_walk_forward_splits(total, train, test) {
            Ok(s) => s,
            Err(_) => return Ok(()),
        };
        for s in &splits {
            let train_size = s.train_end - s.train_start;
            let test_size = s.test_end - s.test_start;
            if train_size != train {
                panic!("train window size = {}, expected {}", train_size, train);
            }
            if test_size != test {
                panic!("test window size = {}, expected {}", test_size, test);
            }
        }
    }

    // 不变式 7：split 数 = floor((total - train - test) / test) + 1
    #[test]
    fn walk_forward_split_count(
        total in 60usize..200,
        train in 10usize..30,
        test in 10usize..30,
    ) {
        prop_assume!(train + test <= total);
        let splits = match make_walk_forward_splits(total, train, test) {
            Ok(s) => s,
            Err(_) => return Ok(()),
        };
        // 算法：cursor 从 0 开始，每次 += test_days
        // 循环条件：cursor + train + test <= total
        // 即 cursor <= total - train - test
        // 第一次 cursor = 0, 然后 += test
        // 步数：ceil((total - train - test + 1) / test) ?
        // 实际上：cursor 取值：0, test, 2*test, ..., k*test
        // 满足 k*test <= total - train - test
        // k <= (total - train - test) / test
        // k_max = floor((total - train - test) / test)
        // split 数 = k_max + 1
        let expected = (total - train - test) / test + 1;
        if splits.len() != expected {
            panic!(
                "splits.len() = {}, expected {} (total={}, train={}, test={})",
                splits.len(),
                expected,
                total,
                train,
                test
            );
        }
    }

    // 不变式 8：grid 同一参数，train_sharpe 应该有相同值（不同 split 可能不同）
    // 我们检查所有 results 中，相同 ParamSet 的 train_sharpe 应与 split 索引相关。
    // 简化检查：相同 ParamSet 出现次数 == splits.len()
    #[test]
    fn grid_search_param_count_per_split(
        total in 100usize..200,
        train in 30usize..50,
        test in 20usize..30,
        grid_size in 1usize..4,
    ) {
        prop_assume!(train + test <= total);
        let klines = make_klines(total);
        let splits = match make_walk_forward_splits(total, train, test) {
            Ok(s) => s,
            Err(_) => return Ok(()),
        };
        let grid: Vec<ParamSet> = (0..grid_size)
            .map(|i| ParamSet {
                j_threshold: -5.0 + i as f64,
                stop_loss_pct: 0.05,
                vol_shrink_threshold: 0.5,
                bbi_break_days: 3,
                min_holding_days: 3,
                lu_half: true,
                position_pct: 0.5,
            })
            .collect();
        let results = run_grid_search(&klines, &grid, &splits, 100_000.0).unwrap();
        // 计数每个 ParamSet 的出现次数
        let mut counts: std::collections::HashMap<(i64, i64, i64, usize, usize, bool, i64), usize> =
            std::collections::HashMap::new();
        for r in &results {
            let key = (
                (r.param.j_threshold * 1e9) as i64,
                (r.param.stop_loss_pct * 1e9) as i64,
                (r.param.vol_shrink_threshold * 1e9) as i64,
                r.param.bbi_break_days,
                r.param.min_holding_days,
                r.param.lu_half,
                (r.param.position_pct * 1e9) as i64,
            );
            *counts.entry(key).or_insert(0) += 1;
        }
        for (_, c) in counts {
            if c != splits.len() {
                panic!("ParamSet appears {} times, expected {}", c, splits.len());
            }
        }
    }
}

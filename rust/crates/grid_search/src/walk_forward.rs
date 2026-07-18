//! Walk-forward 滚动窗口切片。

use zt_core_types::{CoreError, Result};

#[derive(Debug, Clone)]
pub struct WalkForwardSplit {
    pub train_start: usize,
    pub train_end: usize,
    pub test_start: usize,
    pub test_end: usize,
}

pub fn make_walk_forward_splits(
    total_days: usize,
    train_days: usize,
    test_days: usize,
) -> Result<Vec<WalkForwardSplit>> {
    if train_days == 0 || test_days == 0 {
        return Err(CoreError::InvalidWalkForward(
            "train_days and test_days must be > 0".into(),
        ));
    }
    if train_days + test_days > total_days {
        return Err(CoreError::InvalidWalkForward(format!(
            "train({}) + test({}) > total({})",
            train_days, test_days, total_days
        )));
    }

    let mut splits = Vec::new();
    let mut cursor = 0_usize;
    while cursor + train_days + test_days <= total_days {
        splits.push(WalkForwardSplit {
            train_start: cursor,
            train_end: cursor + train_days,
            test_start: cursor + train_days,
            test_end: cursor + train_days + test_days,
        });
        cursor += test_days; // 滑动步长 = test 窗口
    }
    Ok(splits)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_window_errors() {
        assert!(make_walk_forward_splits(100, 0, 10).is_err());
    }

    #[test]
    fn too_large_window_errors() {
        assert!(make_walk_forward_splits(50, 30, 30).is_err());
    }

    #[test]
    fn test_ranges_cover_all_dates_exactly_once() {
        let splits = make_walk_forward_splits(100, 30, 10).unwrap();
        let mut test_covered = std::collections::HashSet::new();
        for s in &splits {
            for i in s.test_start..s.test_end {
                assert!(test_covered.insert(i), "test date {i} covered twice");
            }
        }
    }
}

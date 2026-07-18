//! 选股引擎 crate。
#![forbid(unsafe_code)]

pub mod scoring;

pub use scoring::{screen_stocks, Criterion, StockScore};

//! 技术指标 crate。
#![forbid(unsafe_code)]

pub mod atr;

pub use atr::{compute_atr, compute_atr_default};

//! zettaranc 共享类型 + Arrow schema + 错误定义。
//!
//! 这是所有 Rust crate 的依赖根。Python 业务层通过 `_core_compute`
//! （由 `bindings` crate 暴露）访问本 crate 导出的能力。

#![forbid(unsafe_code)]
#![warn(missing_debug_implementations)]

pub mod error;
pub mod schema;

pub use error::{CoreError, Result};
pub use schema::kline_schema;

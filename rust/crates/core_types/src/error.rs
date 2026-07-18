use thiserror::Error;

/// 整个 Rust 内核的统一错误类型。所有 crate 边界都用这个。
#[derive(Error, Debug)]
pub enum CoreError {
    #[error("invalid K-line data: {0}")]
    InvalidKLine(String),

    #[error("missing required column: {0}")]
    MissingColumn(String),

    #[error("insufficient data: need {need} rows, got {got}")]
    InsufficientData { need: usize, got: usize },

    #[error("date range empty: {start} -> {end}")]
    EmptyDateRange { start: String, end: String },

    #[error("parameter out of range: {field}={value}, expected {constraint}")]
    InvalidParameter {
        field: String,
        value: f64,
        constraint: String,
    },

    #[error("walk-forward split invalid: {0}")]
    InvalidWalkForward(String),

    #[error("database: {0}")]
    Database(String),

    #[error(transparent)]
    Polars(#[from] polars::error::PolarsError),

    #[error(transparent)]
    Arrow(#[from] arrow_schema::ArrowError),
}

pub type Result<T> = std::result::Result<T, CoreError>;

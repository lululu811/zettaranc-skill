use std::sync::Arc;

use arrow_schema::{DataType, Field, Schema, SchemaRef};

/// K 线数据的 Arrow schema。Rust 和 Python 共享同一份字节布局。
pub fn kline_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("ts_code", DataType::Utf8, false),
        Field::new("trade_date", DataType::Date32, false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("vol", DataType::Float64, false),
        Field::new("amount", DataType::Float64, false),
        Field::new("pct_chg", DataType::Float64, false),
        Field::new("vol_ratio", DataType::Float64, true),
        Field::new("is_limit_up", DataType::Boolean, true),
        Field::new("is_limit_down", DataType::Boolean, true),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schema_has_12_fields() {
        let s = kline_schema();
        assert_eq!(s.fields().len(), 12);
        assert_eq!(s.field(0).name(), "ts_code");
        assert_eq!(s.field(5).name(), "close");
    }
}

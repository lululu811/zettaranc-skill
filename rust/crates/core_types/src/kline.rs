//! K 线输入序列。纯字段结构，便于从 Python `list[DailyData]` 构造。
//!
//! 注意：本类型是行存输入格式。回测引擎会把它转成 Arrow 列存后再做计算。

#[derive(Debug, Clone)]
pub struct KLine {
    pub ts_code: String,
    pub trade_date: i32, // 距 1970-01-01 的天数（Date32）
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub vol: f64,
    pub amount: f64,
    pub pct_chg: f64,
    pub vol_ratio: Option<f64>,
    pub is_limit_up: Option<bool>,
    pub is_limit_down: Option<bool>,
}

#[derive(Debug, Clone)]
pub struct KLineSeries {
    pub items: Vec<KLine>,
}

impl KLineSeries {
    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }
}

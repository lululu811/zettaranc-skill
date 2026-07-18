use zt_core_types::{kline_schema, CoreError};

#[test]
fn schema_loads() {
    let s = kline_schema();
    assert_eq!(s.fields().len(), 12);
}

#[test]
fn error_display_works() {
    let e = CoreError::InsufficientData { need: 100, got: 50 };
    let msg = format!("{e}");
    assert!(msg.contains("100"));
    assert!(msg.contains("50"));
}

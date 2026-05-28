"""
技术指标计算模块

将原 indicators.py 拆分为4个子模块后，通过 __init__.py 保持向后兼容。
"""

from .core import (
    TradeSignal, DailyData, IndicatorResult,
    DB_PATH, DATA_MODE, get_data_mode,
    get_db_connection,
    calculate_ma, calculate_ema, calculate_sma_td, calculate_slope,
    calculate_kdj, precompute_kdj_sequence, precompute_bbi_sequence,
    precompute_macd_sequence, calculate_macd,
    calculate_bbi, calculate_rsi, calculate_rsi_multi,
    calculate_wr, calculate_wr_multi, calculate_bollinger, calculate_vol_ratio,
)

from .price_patterns import (
    calculate_zg_white, calculate_dg_yellow, detect_double_line_cross,
    calculate_rsl, detect_needle_20, detect_needle_30,
    detect_double_gun, detect_sb1_detailed,
    calculate_dmi,
    calculate_brick_value, calculate_brick_history, detect_brick_trend, detect_fanbao,
    detect_volume_pattern,
    detect_b1_today, detect_b2_today,
    detect_key_k, detect_violence_k,
    check_two_30_rule,
    detect_nana_chart, detect_golden_bowl, detect_breathing_structure,
    detect_sb1, detect_b3, detect_four_brick_system,
    detect_divergence, detect_macd_signals,
)

from .volume_patterns import (
    detect_volume_anomaly,
    calculate_sell_score, detect_trade_signal,
)

from .data_layer import (
    _indicator_memory_cache,
    _load_indicator_cache, _save_indicator_cache, clear_indicator_memory_cache,
    get_kline_data, get_realtime_data,
    analyze_stock, visualize_brick_chart, format_result,
    main,
)

__all__ = [
    # types
    "TradeSignal", "DailyData", "IndicatorResult",
    # env
    "DB_PATH", "DATA_MODE", "get_data_mode",
    # db
    "get_db_connection",
    # core math
    "calculate_ma", "calculate_ema", "calculate_sma_td", "calculate_slope",
    # core indicators
    "calculate_kdj", "precompute_kdj_sequence", "precompute_bbi_sequence",
    "precompute_macd_sequence", "calculate_macd",
    "calculate_bbi", "calculate_rsi", "calculate_rsi_multi",
    "calculate_wr", "calculate_wr_multi", "calculate_bollinger", "calculate_vol_ratio",
    # price patterns
    "calculate_zg_white", "calculate_dg_yellow", "detect_double_line_cross",
    "calculate_rsl", "detect_needle_20", "detect_needle_30",
    "detect_volume_anomaly",
    "detect_double_gun", "detect_sb1_detailed",
    "calculate_dmi",
    "calculate_brick_value", "calculate_brick_history", "detect_brick_trend", "detect_fanbao",
    "detect_volume_pattern",
    "detect_b1_today", "detect_b2_today",
    "detect_key_k", "detect_violence_k",
    "check_two_30_rule",
    "detect_nana_chart", "detect_golden_bowl", "detect_breathing_structure",
    "detect_sb1", "detect_b3", "detect_four_brick_system",
    "detect_divergence", "detect_macd_signals",
    # volume patterns
    "calculate_sell_score", "detect_trade_signal",
    # data layer
    "clear_indicator_memory_cache",
    "get_kline_data", "get_realtime_data",
    "analyze_stock", "visualize_brick_chart", "format_result",
    "main",
]

#!/usr/bin/env python3
"""
screener 错误码接入测试（v3.10.4）

覆盖：
- ``screen_stocks`` 传入未注册的 criteria → ``ZettarancError(SCREENER_INVALID_CRITERIA)``
- ``screen_stocks`` 拿不到股票列表 → ``ZettarancError(SCREENER_NO_DATA)``
- ``screen_stocks`` 正常路径仍返回 list（向后兼容）
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.core.errors import ErrorCode, ZettarancError


def test_screen_stocks_invalid_criteria_raises():
    """未注册的 criteria 必须抛 SCREENER_INVALID_CRITERIA"""
    from modules.screener import screen_stocks

    with pytest.raises(ZettarancError) as exc_info:
        screen_stocks(criteria="not_a_real_strategy", max_stocks=1)
    assert exc_info.value.code == ErrorCode.SCREENER_INVALID_CRITERIA
    assert "not_a_real_strategy" in exc_info.value.message


def test_screen_stocks_invalid_criteria_message_lists_valid_options():
    """错误消息应提示合法 criteria 列表"""
    from modules.screener import screen_stocks

    with pytest.raises(ZettarancError) as exc_info:
        screen_stocks(criteria="bogus")
    msg = exc_info.value.message
    assert "b1" in msg  # 默认合法
    assert "perfect" in msg


def test_screen_stocks_empty_pool_raises_no_data():
    """注入的 datasource 和本地 SQLite 都拿不到 → SCREENER_NO_DATA"""
    from modules.screener import screen_stocks

    # mock get_all_stocks 返回空列表
    with patch("modules.screener.engine.get_all_stocks", return_value=[]):
        with pytest.raises(ZettarancError) as exc_info:
            screen_stocks(criteria="b1")
    assert exc_info.value.code == ErrorCode.SCREENER_NO_DATA


def test_screen_stocks_valid_criteria_does_not_raise_on_invalid_check():
    """合法 criteria（如 'b1'）必须通过验证——用 1 只股票 + 注入 datasource 让 _analyze_worker 返回 None（无 K 线）"""
    from modules.screener import screen_stocks

    # 注入 datasource 让 get_kline_dicts 返回空，analyze_stock 返回空 Score → 结果空列表
    fake_ds = type(
        "DS",
        (),
        {
            "get_kline_dicts": lambda self, ts_code, days: [],
            "get_stock_list": lambda self, exchange=None: [{"ts_code": "000001.SZ", "name": "测试"}],
            "name": "fake",
        },
    )()
    # 这里应该返回 []，因为 analyze_worker 在 klines < 30 时返回 None
    # 关键点：不应该抛 SCREENER_INVALID_CRITERIA
    results = screen_stocks(criteria="b1", max_stocks=1, use_parallel=False, datasource=fake_ds)
    assert isinstance(results, list)


def test_analyze_stock_no_klines_returns_empty_score():
    """analyze_stock 在无 K 线时仍返回默认空 StockScore（保持向后兼容）"""
    from modules.screener import analyze_stock, StockScore

    # 使用 mock datasource 返回空
    fake_ds = type(
        "DS",
        (),
        {
            "get_kline_dicts": lambda self, ts_code, days: [],
            "name": "fake",
        },
    )()
    score = analyze_stock("000001.SZ", klines=[], datasource=fake_ds)
    assert isinstance(score, StockScore)
    assert score.ts_code == "000001.SZ"


def test_screener_invalid_criteria_zettaranc_is_value_error():
    """ZettarancError 必须仍是 ValueError 子类，保证上游 except ValueError 仍捕获"""
    from modules.screener import screen_stocks

    with pytest.raises(ValueError):
        screen_stocks(criteria="nope")

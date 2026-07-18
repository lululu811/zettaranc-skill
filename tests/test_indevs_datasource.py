"""Indevs 数据源单元测试"""

from __future__ import annotations

import os

import pytest

from modules.indevs_client import IndevsClient, _dataframe_from_payload


def test_dataframe_from_payload_native_envelope():
    """把 Indevs 返回的 fields/items 结构正确转成 DataFrame"""
    payload = {
        "code": 0,
        "data": {
            "fields": ["ts_code", "trade_date", "close"],
            "items": [["000001.SZ", "20260710", 10.5]],
        },
    }
    df = _dataframe_from_payload(payload)
    assert df is not None
    assert list(df.columns) == ["ts_code", "trade_date", "close"]
    assert len(df) == 1


def test_dataframe_from_payload_empty_items():
    """空 items 时返回空 DataFrame"""
    payload = {
        "code": 0,
        "data": {"fields": ["ts_code"], "items": []},
    }
    df = _dataframe_from_payload(payload)
    assert df is not None
    assert df.empty


@pytest.mark.skipif(not os.environ.get("INDEVS_API_KEY"), reason="需配置 INDEVS_API_KEY")
def test_indevs_client_health_check():
    """真实 Indevs API 连通性检查"""
    client = IndevsClient()
    assert client.health_check() is True


@pytest.mark.skipif(not os.environ.get("INDEVS_API_KEY"), reason="需配置 INDEVS_API_KEY")
def test_indevs_client_get_kline_dicts_normalizes_fields():
    """get_kline_dicts 返回的 dict 使用 prev_close 而非 pre_close"""
    client = IndevsClient()
    records = client.get_kline_dicts("000001.SZ", days=5)
    assert records
    for rec in records:
        assert "prev_close" in rec
        assert "pre_close" not in rec
        assert "change" not in rec


@pytest.mark.skipif(not os.environ.get("INDEVS_API_KEY"), reason="需配置 INDEVS_API_KEY")
def test_indevs_client_index_daily():
    """指数代码走 index_daily 接口"""
    client = IndevsClient()
    records = client.get_kline_dicts("000001.SH", days=5)
    assert records
    assert all(r["ts_code"] == "000001.SH" for r in records)

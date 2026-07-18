#!/usr/bin/env python3
"""
indevs_client 错误码接入测试（v3.10.4）

覆盖：
- ``IndevsClient.request`` 在 API key 缺失时抛 ``ZettarancError(INDEVS_NO_DATA)``
- ``IndevsClient.request`` 在 API 返回 ``code != 0`` 时抛 ``ZettarancError(INDEVS_NO_DATA)``
- ``IndevsClient.request`` 在网络/HTTP 异常 3 次重试后抛 ``ZettarancError(INDEVS_NO_DATA)``
- 公开 ``get_*`` 方法仍返回 ``Optional[DataFrame]``，不在内部 raise
- ``health_check`` 失败时返回 False（不抛）
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from modules.core.errors import ErrorCode, ZettarancError
from modules.indevs_client import IndevsClient


def test_request_no_api_key_raises():
    """API key 未配置 → 直接抛 INDEVS_NO_DATA"""
    client = IndevsClient(api_key="")
    with pytest.raises(ZettarancError) as exc_info:
        client.request("daily", {"ts_code": "000001.SZ"})
    assert exc_info.value.code == ErrorCode.INDEVS_NO_DATA
    assert "INDEVS_API_KEY" in exc_info.value.message


def test_request_api_returns_error_code_raises():
    """API 返回 code != 0 → 抛 INDEVS_NO_DATA"""
    client = IndevsClient(api_key="fake-key")

    fake_response = type(
        "R",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"code": 1, "msg": "rate limited"},
        },
    )()

    with patch("modules.indevs_client.requests.get", return_value=fake_response):
        with pytest.raises(ZettarancError) as exc_info:
            client.request("daily", {"ts_code": "000001.SZ"})
    assert exc_info.value.code == ErrorCode.INDEVS_NO_DATA
    assert "rate limited" in exc_info.value.message


def test_request_network_failure_raises_after_retry():
    """网络异常 3 次重试后抛 INDEVS_NO_DATA（含 cause）"""
    client = IndevsClient(api_key="fake-key")

    with patch("modules.indevs_client.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(ZettarancError) as exc_info:
            client.request("daily", {"ts_code": "000001.SZ"})
    assert exc_info.value.code == ErrorCode.INDEVS_NO_DATA
    assert exc_info.value.cause is not None
    assert "3 次重试耗尽" in exc_info.value.message


def test_request_http_error_raises_after_retry():
    """HTTPError（如 500）3 次重试后抛"""
    client = IndevsClient(api_key="fake-key")

    fake_response = type(
        "R",
        (),
        {
            "raise_for_status": lambda self: (_ for _ in ()).throw(requests.HTTPError("500 Server Error")),
            "json": lambda self: {},
        },
    )()

    with patch("modules.indevs_client.requests.get", return_value=fake_response):
        with pytest.raises(ZettarancError) as exc_info:
            client.request("daily", {"ts_code": "000001.SZ"})
    assert exc_info.value.code == ErrorCode.INDEVS_NO_DATA


def test_request_success_returns_payload():
    """正常情况下 request 返回 payload 字典（不再是 None / 不抛）"""
    client = IndevsClient(api_key="fake-key")

    fake_response = type(
        "R",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"code": 0, "msg": "ok", "data": {"fields": ["ts_code"], "items": [["000001.SZ"]]}},
        },
    )()

    with patch("modules.indevs_client.requests.get", return_value=fake_response):
        payload = client.request("daily", {"ts_code": "000001.SZ"})
    assert isinstance(payload, dict)
    assert payload["code"] == 0


def test_public_get_daily_swallows_error_returns_none():
    """get_daily 在底层 raise 时不向调用方抛错，仍返回 None（保持 Protocol 兼容）"""
    client = IndevsClient(api_key="")
    assert client.get_daily("000001.SZ") is None
    assert client.get_index_daily("000001.SH") is None
    assert client.get_moneyflow("000001.SZ", "20260710") is None
    assert client.get_daily_basic("000001.SZ") is None
    assert client.get_stk_factor("000001.SZ") is None
    assert client.get_stock_basic() is None
    assert client.get_trade_cal() is None
    assert client.get_realtime_quote(["000001.SZ"]) is None
    assert client.get_kline_dicts("000001.SZ") == []


def test_health_check_returns_false_on_error():
    """health_check 在 API key 缺失时不抛错，返回 False"""
    client = IndevsClient(api_key="")
    assert client.health_check() is False

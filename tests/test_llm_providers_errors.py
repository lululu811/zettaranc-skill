#!/usr/bin/env python3
"""
llm_providers 错误码接入测试（v3.10.4）

覆盖：
- 超时 → ``ZettarancError(LLM_TIMEOUT)``
- HTTP 非 2xx → ``ZettarancError(LLM_API_ERROR)``
- 返回结构异常（无 choices / JSON 解析失败）→ ``ZettarancError(LLM_INVALID_RESPONSE)``
- 网络层错误 → ``ZettarancError(LLM_API_ERROR)``
- ``ZettarancError`` 是 ``ValueError`` 子类（向后兼容 narrator ``except ValueError``）
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import httpx
import pytest

from modules.core.errors import ErrorCode, ZettarancError


def _make_provider():
    """绕开 API key 检查直接构造 provider。"""
    from modules.llm_providers import MiniMaxProvider

    return MiniMaxProvider(api_key="sk-fake-key", base_url="https://example.invalid/v1/chat/completions")


def test_generate_missing_api_key_raises_config_missing():
    """API key 缺失仍抛 CONFIG_MISSING（继承自 v3.10.4 之前的语义）"""
    from modules.llm_providers import MiniMaxProvider

    with pytest.raises(ZettarancError) as exc_info:
        MiniMaxProvider(api_key="", base_url="https://example.invalid")
    assert exc_info.value.code == ErrorCode.CONFIG_MISSING


def test_generate_timeout_raises_llm_timeout():
    provider = _make_provider()
    with patch("httpx.post", side_effect=httpx.TimeoutException("read timed out")):
        with pytest.raises(ZettarancError) as exc_info:
            provider.generate("sys", "user")
    assert exc_info.value.code == ErrorCode.LLM_TIMEOUT
    assert exc_info.value.cause is not None
    assert isinstance(exc_info.value.cause, httpx.TimeoutException)


def test_generate_http_status_error_raises_llm_api_error():
    provider = _make_provider()

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.text = "internal server error"
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=fake_response
    )

    with patch("httpx.post", return_value=fake_response):
        with pytest.raises(ZettarancError) as exc_info:
            provider.generate("sys", "user")
    assert exc_info.value.code == ErrorCode.LLM_API_ERROR
    assert "500" in exc_info.value.message


def test_generate_network_error_raises_llm_api_error():
    provider = _make_provider()
    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        with pytest.raises(ZettarancError) as exc_info:
            provider.generate("sys", "user")
    assert exc_info.value.code == ErrorCode.LLM_API_ERROR


def test_generate_invalid_json_raises_llm_invalid_response():
    provider = _make_provider()

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.side_effect = ValueError("not json")

    with patch("httpx.post", return_value=fake_response):
        with pytest.raises(ZettarancError) as exc_info:
            provider.generate("sys", "user")
    assert exc_info.value.code == ErrorCode.LLM_INVALID_RESPONSE


def test_generate_missing_choices_raises_llm_invalid_response():
    provider = _make_provider()

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"code": 0, "msg": "ok"}  # no choices

    with patch("httpx.post", return_value=fake_response):
        with pytest.raises(ZettarancError) as exc_info:
            provider.generate("sys", "user")
    assert exc_info.value.code == ErrorCode.LLM_INVALID_RESPONSE


def test_generate_empty_content_raises_llm_invalid_response():
    provider = _make_provider()

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"choices": [{"message": {"content": ""}}]}

    with patch("httpx.post", return_value=fake_response):
        with pytest.raises(ZettarancError) as exc_info:
            provider.generate("sys", "user")
    assert exc_info.value.code == ErrorCode.LLM_INVALID_RESPONSE


def test_generate_success_returns_content():
    provider = _make_provider()

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"choices": [{"message": {"content": "hello"}}]}

    with patch("httpx.post", return_value=fake_response):
        text = provider.generate("sys", "user")
    assert text == "hello"


def test_zettaranc_error_is_value_error_subclass_for_narrator_compat():
    """向后兼容：narrator ``except ValueError`` 必须能捕获到 LLM 错误"""
    provider = _make_provider()
    with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
        with pytest.raises(ValueError):
            provider.generate("sys", "user")
    # 类型同时是 ZettarancError
    try:
        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            provider.generate("sys", "user")
    except ZettarancError as e:
        assert e.code == ErrorCode.LLM_TIMEOUT


def test_generate_stream_timeout_raises_llm_timeout():
    provider = _make_provider()
    with patch("httpx.stream", side_effect=httpx.TimeoutException("timeout")):
        with pytest.raises(ZettarancError) as exc_info:
            list(provider.generate_stream("sys", "user"))
    assert exc_info.value.code == ErrorCode.LLM_TIMEOUT


def test_generate_stream_connect_error_raises_llm_api_error():
    """ConnectError 在 stream() 阶段抛出 → LLM_API_ERROR"""
    provider = _make_provider()
    with patch("httpx.stream", side_effect=httpx.ConnectError("connection refused")):
        with pytest.raises(ZettarancError) as exc_info:
            list(provider.generate_stream("sys", "user"))
    assert exc_info.value.code == ErrorCode.LLM_API_ERROR


def test_generate_stream_http_status_raises_llm_api_error():
    """流式响应 raise_for_status() 抛 HTTPStatusError → LLM_API_ERROR"""
    provider = _make_provider()

    # 构造一个 context manager 包装的 response，__enter__ 返回 self
    fake_response = MagicMock()
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock(status_code=500)
    )

    with patch("httpx.stream", return_value=fake_response):
        with pytest.raises(ZettarancError) as exc_info:
            list(provider.generate_stream("sys", "user"))
    assert exc_info.value.code == ErrorCode.LLM_API_ERROR

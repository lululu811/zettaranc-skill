#!/usr/bin/env python3
"""
统一错误码测试（v3.10.4）

覆盖：
- ErrorCode 枚举取值
- ZettarancError 消息格式 / to_dict / cause 透传
- 向后兼容：ZettarancError 是 ValueError 子类
- 试点模块：TushareClient 配置缺失抛 CONFIG_MISSING
- CLI 顶层捕获 ZettarancError → stderr 统一格式 + exit 2
"""

import os
import subprocess
import sys

import pytest

from modules.core.errors import ErrorCode, ZettarancError


class TestErrorCode:
    """错误码枚举"""

    def test_codes(self):
        assert ErrorCode.CONFIG_MISSING.value == "CONFIG_MISSING"
        assert ErrorCode.DATA_SOURCE_ERROR.value == "DATA_SOURCE_ERROR"
        assert ErrorCode.RATE_LIMIT.value == "RATE_LIMIT"
        assert ErrorCode.DB_ERROR.value == "DB_ERROR"
        assert ErrorCode.INVALID_PARAM.value == "INVALID_PARAM"

    def test_code_is_str_enum(self):
        assert isinstance(ErrorCode.CONFIG_MISSING, str)


class TestZettarancError:
    """异常基类"""

    def test_message_format(self):
        err = ZettarancError(ErrorCode.CONFIG_MISSING, "未设置 TUSHARE_TOKEN")
        assert str(err) == "[CONFIG_MISSING] 未设置 TUSHARE_TOKEN"

    def test_is_value_error_subclass(self):
        """向后兼容：现有 except ValueError / pytest.raises(ValueError) 不受影响"""
        err = ZettarancError(ErrorCode.DB_ERROR, "读取失败")
        assert isinstance(err, ValueError)
        with pytest.raises(ValueError):
            raise err

    def test_attributes(self):
        cause = RuntimeError("原始异常")
        err = ZettarancError(ErrorCode.DATA_SOURCE_ERROR, "API 失败", cause=cause)
        assert err.code == ErrorCode.DATA_SOURCE_ERROR
        assert err.message == "API 失败"
        assert err.cause is cause

    def test_to_dict(self):
        err = ZettarancError(ErrorCode.RATE_LIMIT, "触发限流")
        d = err.to_dict()
        assert d["error_code"] == "RATE_LIMIT"
        assert d["message"] == "触发限流"
        assert d["cause"] is None

    def test_to_dict_with_cause(self):
        err = ZettarancError(ErrorCode.DB_ERROR, "写入失败", cause=KeyError("k"))
        assert "KeyError" in err.to_dict()["cause"]


class TestTushareClientPilot:
    """试点：TushareClient 配置缺失抛结构化错误"""

    def test_missing_token_raises_zettaranc_error(self, monkeypatch):
        monkeypatch.setenv("DATA_MODE", "jnb")
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        import modules.tushare_client as tc

        monkeypatch.setattr(tc, "TUSHARE_TOKEN", "")
        monkeypatch.setattr(tc, "TUSHARE_API_URL", "http://example.com")
        with pytest.raises(ZettarancError) as exc_info:
            tc.TushareClient()
        assert exc_info.value.code == ErrorCode.CONFIG_MISSING
        assert "TUSHARE_TOKEN" in str(exc_info.value)

    def test_missing_api_url_raises_zettaranc_error(self, monkeypatch):
        monkeypatch.setenv("DATA_MODE", "jnb")
        import modules.tushare_client as tc

        monkeypatch.setattr(tc, "TUSHARE_TOKEN", "fake_token")
        monkeypatch.setattr(tc, "TUSHARE_API_URL", "")
        with pytest.raises(ZettarancError, match="TUSHARE_API_URL"):
            tc.TushareClient()


class TestDatasourcePilot:
    """试点：CompositeDataSource 非法 preferred 抛结构化错误"""

    def test_invalid_preferred_raises_zettaranc_error(self):
        from modules.datasource import CompositeDataSource

        with pytest.raises(ZettarancError) as exc_info:
            CompositeDataSource(preferred="not-a-source")
        assert exc_info.value.code == ErrorCode.INVALID_PARAM
        assert "not-a-source" in str(exc_info.value)

    def test_valid_preferred_accepted(self):
        from modules.datasource import CompositeDataSource

        for p in CompositeDataSource.VALID_PREFERRED:
            ds = CompositeDataSource(preferred=p)
            assert ds._preferred == p


class TestCliTopLevelCatch:
    """CLI 顶层捕获 ZettarancError，stderr 输出统一格式并 exit 2"""

    def test_cli_catches_zettaranc_error(self, monkeypatch, capsys):
        from modules import cli

        class FakeArgs:
            command = "analyze"

        monkeypatch.setattr(cli, "build_parser", lambda: type("P", (), {"parse_args": lambda self: FakeArgs()})())
        monkeypatch.setattr(
            cli,
            "cmd_analyze",
            lambda args: (_ for _ in ()).throw(ZettarancError(ErrorCode.CONFIG_MISSING, "未配置 Token")),
        )
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code == 2
        assert "[CONFIG_MISSING] 未配置 Token" in capsys.readouterr().err


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

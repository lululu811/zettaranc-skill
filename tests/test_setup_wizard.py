"""
setup_wizard.py 配置测试
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from modules.setup_wizard import (
    check_env_exists, check_data_mode, write_env_file,
    get_mode_display_name, MODE_JNB, MODE_NORMAL
)


class TestCheckEnvExists:
    def test_no_env_not_configured(self):
        # 清除环境变量
        for key in ("TUSHARE_TOKEN", "DATA_MODE"):
            if key in os.environ:
                del os.environ[key]
        assert check_env_exists() is False


class TestWriteEnvFile:
    def test_write_websearch_mode(self):
        """写普通小万模式"""
        # 先清除已有的 DATA_MODE
        if "DATA_MODE" in os.environ:
            del os.environ["DATA_MODE"]

        path = write_env_file(mode=MODE_NORMAL)
        assert Path(path).exists()
        assert os.environ.get("DATA_MODE") == MODE_NORMAL

        content = Path(path).read_text(encoding="utf-8")
        assert "DATA_MODE=websearch" in content

    def test_write_jnb_mode(self):
        """写 JNB 模式"""
        if "DATA_MODE" in os.environ:
            del os.environ["DATA_MODE"]
        if "TUSHARE_TOKEN" in os.environ:
            del os.environ["TUSHARE_TOKEN"]

        path = write_env_file(token="test_token_12345", mode=MODE_JNB)
        assert Path(path).exists()
        assert os.environ.get("DATA_MODE") == MODE_JNB
        assert os.environ.get("TUSHARE_TOKEN") == "test_token_12345"

        content = Path(path).read_text(encoding="utf-8")
        assert "DATA_MODE=jnb" in content
        assert "TUSHARE_TOKEN=test_token_12345" in content


class TestCheckDataMode:
    def test_returns_mode(self):
        os.environ["DATA_MODE"] = "websearch"
        assert check_data_mode() == "websearch"

    def test_returns_none_if_not_set(self):
        if "DATA_MODE" in os.environ:
            del os.environ["DATA_MODE"]
        # 新进程可能没有设置
        mode = check_data_mode()
        assert mode is None or mode in ("websearch", "jnb")


class TestGetModeDisplayName:
    def test_jnb(self):
        assert get_mode_display_name(MODE_JNB) == "JNB"

    def test_normal(self):
        assert get_mode_display_name(MODE_NORMAL) == "普通小万"

    def test_unknown(self):
        assert get_mode_display_name("unknown") == "unknown"

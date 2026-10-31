"""数据源决议的一致性测试。

「环境变量 → provider」的判定矩阵只在这里写一次。读路径
（``CompositeDataSource``）与写路径（``DataSyncer``）各自的测试不再重复抄
这张矩阵，只断言"我选出来的 == 决议结果"——规则改了只需要改这一张表。
"""

from __future__ import annotations

import pytest

from modules.datasource import CompositeDataSource
from modules.datasource_resolution import ProviderResolution, resolve_provider
from modules.data_sync.syncer import DataSyncer

# 决议矩阵：环境变量 → 期望选中的 provider
#   provider 为 None 表示"无配置"，调用方回退免费源 a-stock-data
#   JNB 模式（DATA_MODE=jnb）下 tushare 还需 TUSHARE_API_URL 才算配置完整——
#   缺任一项都回退 a-stock-data（见 TushareClient.__init__ 的 CONFIG_MISSING 检查）
_MATRIX = [
    ({}, None, "零配置"),
    ({"HITHINK_FINANCE_API_KEY": "k"}, "hithink", "配置了 hithink key"),
    ({"INDEVS_API_KEY": "k"}, "indevs", "配置了 indevs key"),
    ({"HITHINK_FINANCE_API_KEY": "k", "INDEVS_API_KEY": "k"}, "hithink", "hithink 优先于 indevs"),
    (
        {"DATA_MODE": "jnb", "TUSHARE_TOKEN": "t", "TUSHARE_API_URL": "https://example.invalid"},
        "tushare",
        "JNB 模式且配了 token",
    ),
    ({"TUSHARE_TOKEN": "t"}, None, "仅 token 但非 JNB 模式（tushare 无数据后端）"),
    ({"DATA_MODE": "jnb"}, None, "JNB 模式但没配 token"),
    ({"DATA_MODE": "jnb", "TUSHARE_TOKEN": "t"}, None, "JNB 模式有 token 但缺 API URL"),
    ({"DATA_MODE": "websearch", "TUSHARE_TOKEN": "t"}, None, "websearch 模式配了 token"),
]

_ALL_ENV_KEYS = (
    "HITHINK_FINANCE_API_KEY",
    "INDEVS_API_KEY",
    "TUSHARE_TOKEN",
    "TUSHARE_API_URL",
    "DATA_MODE",
)


def _clean_env(monkeypatch, env: dict[str, str]) -> None:
    """把环境变量清干净，再按用例设置。

    ``resolve_provider()`` 与 ``TushareClient`` 的可用性判定读的是**同一份实时
    环境变量**（``tushare_client.current_api_url()`` / ``current_token()``），
    所以这里只需管环境变量——本机 ``.env`` 有没有 ``TUSHARE_API_URL`` 都不影响
    结果，CI 与本地行为一致。
    """
    for key in _ALL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


class TestResolveProvider:
    """决议本身：环境变量 → provider。"""

    @pytest.mark.parametrize(
        ("env", "expected", "label"),
        _MATRIX,
        ids=[label for _, _, label in _MATRIX],
    )
    def test_matrix(self, monkeypatch, env, expected, label):
        _clean_env(monkeypatch, env)
        resolution = resolve_provider()
        assert resolution.provider == expected, label
        assert isinstance(resolution.reason, str) and resolution.reason

    def test_reason_explains_the_choice(self, monkeypatch):
        _clean_env(monkeypatch, {"HITHINK_FINANCE_API_KEY": "k"})
        resolution = resolve_provider()
        assert "HITHINK_FINANCE_API_KEY" in resolution.reason
        assert "hithink" in resolution.describe()

    def test_uses_free_source_flag(self, monkeypatch):
        _clean_env(monkeypatch, {})
        assert resolve_provider().uses_free_source is True
        _clean_env(monkeypatch, {"INDEVS_API_KEY": "k"})
        assert resolve_provider().uses_free_source is False

    def test_resolution_is_immutable(self):
        resolution = ProviderResolution("hithink", "理由")
        with pytest.raises(Exception):
            resolution.provider = "indevs"  # type: ignore[misc]


class TestReadPathMatchesResolution:
    """读路径（CompositeDataSource）的首选源必须等于决议结果。"""

    @pytest.mark.parametrize(
        ("env", "expected", "label"),
        _MATRIX,
        ids=[label for _, _, label in _MATRIX],
    )
    def test_preferred_source_matches_resolution(self, monkeypatch, env, expected, label):
        _clean_env(monkeypatch, env)
        preferred = CompositeDataSource("auto")._preferred_token_source()
        name = getattr(preferred, "name", None) if preferred is not None else None
        assert name == expected, label


class TestWritePathMatchesResolution:
    """写路径（DataSyncer）的数据源必须等于决议结果。"""

    @pytest.mark.parametrize(
        ("env", "expected", "label"),
        _MATRIX,
        ids=[label for _, _, label in _MATRIX],
    )
    def test_datasource_matches_resolution(self, monkeypatch, env, expected, label):
        _clean_env(monkeypatch, env)
        syncer = DataSyncer()
        expected_name = expected or "a-stock-data"
        assert syncer._datasource.name == expected_name, label

    def test_hithink_config_is_honored_by_write_path(self, monkeypatch):
        """回归：写路径此前没有 hithink 分支——配了 key 的用户 analyze 走同花顺、sync 走免费源。"""
        _clean_env(monkeypatch, {"HITHINK_FINANCE_API_KEY": "k"})
        assert DataSyncer()._datasource.name == "hithink"

    def test_explicit_token_still_wins(self, monkeypatch):
        """显式传入 token 是调用方的明确意图，仍应直接用 tushare。"""
        _clean_env(monkeypatch, {"HITHINK_FINANCE_API_KEY": "k"})
        syncer = DataSyncer(token="explicit-token")
        assert syncer._datasource.name == "tushare"


class TestCliSyncDoesNotPinTushare:
    """`zt sync` 不再钉死 tushare。

    钉死的后果：默认的 websearch 模式下 TushareClient._pro is None（无数据后端），
    取数恒返回 None，整次同步静默同步 0 行却照样打印"同步完成"。
    """

    @staticmethod
    def _capture_constructions(monkeypatch) -> list[dict]:
        """替换 DataSyncer，记录每次构造时传入的关键字参数。"""
        constructions: list[dict] = []

        class _FakeSyncer:
            def __init__(self, *args, **kwargs):
                constructions.append(kwargs)

            def sync_stock_basic(self):
                return 0

            def sync_all_daily_kline(self, days=730):
                return {}

            def sync_daily_kline(self, ts_code, *a, **k):
                return 0

            def sync_stk_factor(self, ts_code, start_date, end_date):
                return 0

            def sync_all_stk_factor(self, days=365):
                return {}

            def get_sync_status(self):
                return {}

        # cmd_sync 在函数内部 `from modules.data_sync import DataSyncer`，
        # 因此要替换的是包上的那个名字
        monkeypatch.setattr("modules.data_sync.DataSyncer", _FakeSyncer, raising=False)
        return constructions

    def test_sync_action_does_not_pin_a_datasource(self, monkeypatch):
        import argparse

        import modules.cli_commands.data as data_cmd

        constructions = self._capture_constructions(monkeypatch)

        args = argparse.Namespace(
            sync_action="sync",
            ts_code=None,
            skip_indicators=True,
            indicators=False,
            days=250,
        )
        data_cmd.cmd_sync(args)

        assert constructions, "cmd_sync 应构造一个 DataSyncer"
        assert "datasource" not in constructions[0], "zt sync 不应钉死数据源"

    def test_stk_factor_action_keeps_tushare(self, monkeypatch):
        """技术因子只有 tushare/indevs 提供，stk-factor 命令保留 tushare 钉死。"""
        import argparse

        import modules.cli_commands.data as data_cmd

        constructions = self._capture_constructions(monkeypatch)

        args = argparse.Namespace(sync_action="stk-factor", ts_code=None, days=30)
        data_cmd.cmd_sync(args)

        assert "datasource" in constructions[0], "stk-factor 应显式注入 datasource"

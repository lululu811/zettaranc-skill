"""Phase B.1 regression tests for modules.data_sync package refactor."""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import Mock

import pytest


# ==================== 导入路径 ====================


def test_data_syncer_importable_from_package():
    """DataSyncer 可从 modules.data_sync 包导入"""
    from modules.data_sync import DataSyncer

    assert DataSyncer is not None


def test_data_syncer_importable_from_syncer_module():
    """DataSyncer 可从 modules.data_sync.syncer 模块导入"""
    from modules.data_sync.syncer import DataSyncer

    assert DataSyncer is not None


def test_data_syncer_importable_from_top_level_shim():
    """DataSyncer 可从顶层 modules.data_sync shim 导入"""
    from modules import data_sync

    assert hasattr(data_sync, "DataSyncer")
    assert data_sync.DataSyncer is not None


# ==================== 公共方法签名 ====================


PUBLIC_METHODS = {
    "sync_stock_basic": {},
    "sync_daily_kline": {"start_date": None, "end_date": None},
    "sync_missing": {"days": 730},
    "sync_all_daily_kline": {"ts_codes": None, "days": 730, "incremental": False},
    "sync_indicator_cache": {"days": 120, "warmup": 250, "incremental": False},
    "sync_all_indicators": {"ts_codes": None, "days": 120, "warmup": 250, "incremental": False},
    "sync_daily_and_compute": {"ts_codes": None, "days": 730, "incremental": False},
    "sync_stk_factor": {"start_date": None, "end_date": None},
    "sync_all_stk_factor": {"ts_codes": None, "days": 365},
    "ensure_daily_basic_columns": {},
    "sync_daily_basic": {"start_date": "", "end_date": ""},
    "sync_all_daily_basic": {"ts_codes": None, "days": 730},
    "sync_moneyflow": {},
    "get_sync_status": {},
}


@pytest.mark.parametrize("method_name,expected_defaults", PUBLIC_METHODS.items())
def test_data_syncer_public_method_signatures(method_name, expected_defaults):
    """DataSyncer 公共方法签名与原文件一致"""
    from modules.data_sync.syncer import DataSyncer

    assert hasattr(DataSyncer, method_name), f"DataSyncer.{method_name} missing"
    sig = inspect.signature(getattr(DataSyncer, method_name))
    for param_name, default in expected_defaults.items():
        assert param_name in sig.parameters, f"DataSyncer.{method_name} missing {param_name}"
        assert sig.parameters[param_name].default == default, f"DataSyncer.{method_name}.{param_name} default mismatch"


# ==================== 依赖注入 DataSource ====================


class FakeDataSource:
    """Minimal fake DataSource for injection tests."""

    @property
    def name(self) -> str:
        return "fake"

    def health_check(self) -> bool:
        return True

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> Any:
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> Any:
        return None

    def get_realtime_quote(self, ts_codes: list[str]) -> Any:
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> Any:
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> Any:
        return None

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> Any:
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> Any:
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> Any:
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        return []

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        return []


def test_data_syncer_accepts_datasource_parameter(monkeypatch):
    """DataSyncer 可接受 datasource 参数（依赖注入）"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "websearch")
    fake = FakeDataSource()
    syncer = DataSyncer(token="dummy", datasource=fake)
    assert syncer._datasource is fake
    assert syncer._fetcher.datasource is fake


def test_data_syncer_default_datasource_is_a_stock_data(monkeypatch):
    """零配置（无 TUSHARE_TOKEN / INDEVS_API_KEY）时，DataSyncer 默认 datasource 为 a-stock-data（免费源）"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    syncer = DataSyncer()
    assert syncer._datasource.name == "a-stock-data"


def test_data_syncer_default_datasource_prefers_indevs(monkeypatch):
    """同时配置 INDEVS_API_KEY 与 TUSHARE_TOKEN 时，默认数据源最优先 Indevs Replay API"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("INDEVS_API_KEY", "dummy-key")
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    syncer = DataSyncer()
    assert syncer._datasource.name == "indevs"


def test_data_syncer_default_datasource_websearch_token_uses_a_stock_data(monkeypatch):
    """websearch 模式（默认）仅配置 TUSHARE_TOKEN 环境变量时，默认数据源为 a-stock-data。

    tushare 在 websearch 模式下无数据后端（_pro=None），路由过去必失败；
    父版本 auto 行为即 a-stock-data，老用户行为保持不变。
    """
    from modules.datasource import AStockDataDataSource
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    syncer = DataSyncer()
    assert isinstance(syncer._datasource, AStockDataDataSource)


def test_data_syncer_default_datasource_prefers_tushare_in_jnb(monkeypatch):
    """JNB 模式 + TUSHARE_TOKEN + TUSHARE_API_URL 时，默认数据源为 tushare（老用户行为不变）"""
    import modules.tushare_client as tc

    from modules.datasource import TushareDataSource
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "jnb")
    # 模块级常量在 import 时读取，monkeypatch.setenv 无效，需直接改模块属性
    monkeypatch.setenv("TUSHARE_API_URL", "https://tt.xiaodefa.cn")
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    syncer = DataSyncer()
    assert isinstance(syncer._datasource, TushareDataSource)
    assert syncer._datasource._client.token == "env-token"


def test_data_syncer_jnb_missing_url_falls_back_to_a_stock_data(monkeypatch):
    """JNB 模式 + TUSHARE_TOKEN 但缺 TUSHARE_API_URL：构造期不抛错，回退 a-stock-data"""
    import modules.tushare_client as tc

    from modules.datasource import AStockDataDataSource
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "jnb")
    monkeypatch.setenv("TUSHARE_API_URL", "")
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    syncer = DataSyncer()
    assert isinstance(syncer._datasource, AStockDataDataSource)


def test_datasyncer_honors_token_argument(monkeypatch):
    """显式传入 token 时，默认数据源为 TushareDataSource，且 token 透传到内部 TushareClient"""
    from modules.datasource import TushareDataSource
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    ds = DataSyncer(token="explicit-token")
    assert ds.token == "explicit-token"
    assert isinstance(ds._datasource, TushareDataSource)
    assert ds._datasource._client.token == "explicit-token"


def test_data_syncer_with_datasource_skips_jnb_validation(monkeypatch):
    """提供 datasource 时，即使 JNB 模式缺少 token/URL 也不应抛错"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "jnb")
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_API_URL", raising=False)
    fake = FakeDataSource()
    syncer = DataSyncer(token=None, datasource=fake)
    assert syncer._datasource is fake
    assert syncer._fetcher.datasource is fake


# ==================== _call_api_with_retry ====================


def test_call_api_with_retry_returns_result(monkeypatch):
    """_call_api_with_retry 成功时返回 func 结果"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "websearch")
    syncer = DataSyncer(token="dummy", datasource=FakeDataSource())
    syncer._rate_limit = Mock()
    result = syncer._call_api_with_retry("test_api", lambda: "ok")
    assert result == "ok"
    syncer._rate_limit.assert_called_once_with("test_api")


def test_call_api_with_retry_retries_then_raises(monkeypatch):
    """_call_api_with_retry 失败时重试 3 次后抛出异常"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "websearch")
    syncer = DataSyncer(token="dummy", datasource=FakeDataSource())
    syncer._rate_limit = Mock()
    monkeypatch.setattr("time.sleep", lambda x: None)

    attempts = 0

    def fail():
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        syncer._call_api_with_retry("test_api", fail)

    assert attempts == 3
    assert syncer._rate_limit.call_count == 3


def test_call_api_with_retry_passes_args_kwargs(monkeypatch):
    """_call_api_with_retry 正确传递 *args, **kwargs"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "websearch")
    syncer = DataSyncer(token="dummy", datasource=FakeDataSource())
    syncer._rate_limit = Mock()

    captured = {}

    def func(a, b, c=None):
        captured["args"] = (a, b)
        captured["c"] = c
        return "ok"

    result = syncer._call_api_with_retry("test_api", func, 1, 2, c=3)
    assert result == "ok"
    assert captured["args"] == (1, 2)
    assert captured["c"] == 3


# ==================== _batch_sync ====================


def test_batch_sync_returns_empty_for_empty_list(monkeypatch):
    """_batch_sync 空列表返回空 dict"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "websearch")
    syncer = DataSyncer(token="dummy", datasource=FakeDataSource())
    result = syncer._batch_sync("test", lambda code: 1, [])
    assert result == {}


def test_batch_sync_maps_codes_to_counts(monkeypatch):
    """_batch_sync 并发执行并返回 dict[ts_code] = count"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "websearch")
    syncer = DataSyncer(token="dummy", datasource=FakeDataSource())

    def sync_fn(code: str) -> int:
        return int(code)

    result = syncer._batch_sync("test", sync_fn, ["1", "2", "3"])
    assert result == {"1": 1, "2": 2, "3": 3}


def test_batch_sync_handles_failure_gracefully(monkeypatch):
    """_batch_sync 单个任务失败时返回 0 且不中断其他任务"""
    from modules.data_sync.syncer import DataSyncer

    monkeypatch.setenv("DATA_MODE", "websearch")
    syncer = DataSyncer(token="dummy", datasource=FakeDataSource())

    def sync_fn(code: str) -> int:
        if code == "bad":
            raise RuntimeError("fail")
        return 1

    result = syncer._batch_sync("test", sync_fn, ["good", "bad", "good2"])
    assert result["good"] == 1
    assert result["bad"] == 0
    assert result["good2"] == 1


# ==================== 内部辅助方法 ====================


def test_fetch_all_codes_queries_database(monkeypatch):
    """_fetch_all_codes 从数据库查询代码列表"""
    from modules.data_sync.syncer import DataSyncer

    rows = [("000001.SZ",), ("600000.SH",)]

    class FakeCursor:
        def execute(self, query):
            pass

        def fetchall(self):
            return rows

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("modules.data_sync.syncer.get_connection", lambda: FakeConn())
    monkeypatch.setattr("modules.data_sync._infra.get_connection", lambda: FakeConn())
    codes = DataSyncer._fetch_all_codes("SELECT ts_code FROM stock_basic")
    assert codes == ["000001.SZ", "600000.SH"]

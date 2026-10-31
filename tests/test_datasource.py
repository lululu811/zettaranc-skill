"""
DataSource 协议与实现测试
"""

import pandas as pd
import pytest

from modules.bridge_client import BridgeConfig, get_bridge_config, is_bridge_available
from modules.datasource import (
    AStockDataDataSource,
    BridgeDataSource,
    CompositeDataSource,
    DataSource,
    IndevsDataSource,
    SqliteDataSource,
    TushareDataSource,
    get_datasource,
)


class FakeDataSource:
    """用于验证 Protocol 运行时检查的最小实现。"""

    @property
    def name(self) -> str:
        return "fake"

    def health_check(self) -> bool:
        return True

    def get_daily(self, ts_code: str, start_date: str | None = None, end_date: str | None = None):
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str):
        return None

    def get_realtime_quote(self, ts_codes: list[str]):
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str):
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str):
        return None

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str):
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None):
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str):
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


def test_datasource_protocol_runtime_checkable():
    """Protocol 应支持运行时 isinstance 检查。"""
    assert isinstance(SqliteDataSource(), DataSource)
    assert isinstance(FakeDataSource(), DataSource)


def test_tushare_datasource_name():
    assert TushareDataSource().name == "tushare"


def test_tushare_datasource_get_kline_dicts_omits_empty_dates(monkeypatch):
    """未指定起止日期时，不应向 TushareClient.get_daily 传入空字符串。"""
    captured: list[dict] = []

    def capture_get_daily(self, ts_code, start_date=None, end_date=None):
        captured.append({"ts_code": ts_code, "start_date": start_date, "end_date": end_date})
        return pd.DataFrame(
            [
                {
                    "trade_date": "20260101",
                    "open": 1,
                    "high": 2,
                    "low": 0.5,
                    "close": 1.5,
                    "vol": 100,
                    "amount": 150,
                    "pct_chg": 0.5,
                }
            ]
        )

    monkeypatch.setattr("modules.datasource.TushareClient.get_daily", capture_get_daily)
    ds = TushareDataSource()
    result = ds.get_kline_dicts("600519.SH")
    assert len(result) == 1
    assert captured[-1]["start_date"] is None
    assert captured[-1]["end_date"] is None


def test_bridge_datasource_name():
    assert BridgeDataSource().name == "bridge"


def test_sqlite_datasource_name():
    assert SqliteDataSource().name == "sqlite"


def test_composite_prefers_bridge_when_available(monkeypatch):
    monkeypatch.setattr("modules.datasource.is_bridge_available", lambda config=None: True)
    ds = CompositeDataSource()
    assert ds.health_check() is True


def test_composite_falls_back_to_sqlite(monkeypatch, temp_db, db_conn):
    from tests.conftest import write_klines_to_db, write_stock_basic

    monkeypatch.setattr("modules.bridge_client.is_bridge_available", lambda: False)
    write_stock_basic(db_conn, ts_code="600519.SH", name="贵州茅台", industry="白酒", market="主板")
    rows = [
        {
            "ts_code": "600519.SH",
            "trade_date": "20260101",
            "open": 1500.0,
            "high": 1520.0,
            "low": 1490.0,
            "close": 1510.0,
            "vol": 10000.0,
            "amount": 15100000.0,
            "pct_chg": 0.5,
        },
        {
            "ts_code": "600519.SH",
            "trade_date": "20260102",
            "open": 1510.0,
            "high": 1530.0,
            "low": 1500.0,
            "close": 1520.0,
            "vol": 11000.0,
            "amount": 16720000.0,
            "pct_chg": 0.6,
        },
    ]
    write_klines_to_db(db_conn, rows)

    ds = CompositeDataSource()
    data = ds.get_kline_dicts("600519.SH", days=60)
    assert len(data) == 2
    assert data[0]["trade_date"] == "20260101"
    assert data[1]["trade_date"] == "20260102"


def test_get_datasource_factory():
    ds = get_datasource("sqlite")
    assert isinstance(ds, SqliteDataSource)
    assert ds.name == "sqlite"


def test_bridge_datasource_with_custom_config_does_not_mutate_global(monkeypatch):
    """传入自定义 BridgeConfig 不应修改全局 bridge 配置，且实例方法使用自身配置。"""
    from modules.bridge_client import set_bridge_config

    # 重置全局配置到已知状态
    set_bridge_config(host="127.0.0.1", port=8765, timeout=10, enabled="auto")
    custom = BridgeConfig(host="10.0.0.1", port=9999, timeout=3, enabled="never")

    captured: list[BridgeConfig | None] = []

    def capture_is_available(config=None):
        captured.append(config)
        return False  # 统一返回不可用，避免真实 HTTP 请求

    monkeypatch.setattr("modules.datasource.is_bridge_available", capture_is_available)

    ds = BridgeDataSource(config=custom)
    assert ds._config == custom

    # 健康检查应把实例配置透传下去
    ds.health_check()
    assert captured == [custom]

    # 全局配置保持不变
    cfg = get_bridge_config()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.timeout == 10
    assert cfg.enabled == "auto"


def test_bridge_datasource_default_uses_global_config(monkeypatch):
    """未传 config 时，BridgeDataSource 使用全局 bridge 配置。"""
    captured: list[BridgeConfig | None] = []

    def capture_is_available(config=None):
        captured.append(config)
        return False

    monkeypatch.setattr("modules.datasource.is_bridge_available", capture_is_available)
    ds = BridgeDataSource()
    ds.health_check()
    assert captured == [None]


def test_composite_auto_does_not_use_tushare(monkeypatch, temp_db, db_conn):
    """auto 策略在 bridge 不可用时回退到 SQLite，不应调用 TushareDataSource。"""
    from tests.conftest import write_klines_to_db, write_stock_basic

    # bridge 不可用
    monkeypatch.setattr("modules.bridge_client.is_bridge_available", lambda config=None: False)
    # 标记 TushareDataSource.get_kline_dicts 被调用即失败
    original_get_kline_dicts = TushareDataSource.get_kline_dicts

    def failing_tushare_klines(self, ts_code, days=60, start_date=None, end_date=None):
        pytest.fail("TushareDataSource.get_kline_dicts should not be called in auto fallback")

    monkeypatch.setattr(TushareDataSource, "get_kline_dicts", failing_tushare_klines)

    write_stock_basic(db_conn, ts_code="600519.SH", name="贵州茅台", industry="白酒", market="主板")
    rows = [
        {
            "ts_code": "600519.SH",
            "trade_date": "20260101",
            "open": 1500.0,
            "high": 1520.0,
            "low": 1490.0,
            "close": 1510.0,
            "vol": 10000.0,
            "amount": 15100000.0,
            "pct_chg": 0.5,
        },
    ]
    write_klines_to_db(db_conn, rows)

    ds = CompositeDataSource(preferred="auto")
    data = ds.get_kline_dicts("600519.SH", days=60)
    assert len(data) == 1
    assert data[0]["trade_date"] == "20260101"

    # 恢复原始方法（monkeypatch 会自动恢复，但显式恢复更安全）
    monkeypatch.setattr(TushareDataSource, "get_kline_dicts", original_get_kline_dicts)


def test_composite_auto_does_not_eagerly_construct_tushare(monkeypatch):
    """auto 模式下 CompositeDataSource 不应在构造时急切创建 TushareDataSource。"""
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    composite = CompositeDataSource("auto")
    assert composite._tushare is None
    result = composite.health_check()
    assert isinstance(result, bool)


def test_composite_auto_prefers_a_stock_data_without_config(monkeypatch):
    """零配置（无 TUSHARE_TOKEN / INDEVS_API_KEY）时 auto 模式首选 a-stock-data。"""
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(AStockDataDataSource, "get_daily", lambda self, *a, **k: sentinel)
    monkeypatch.setattr(TushareDataSource, "get_daily", lambda self, *a, **k: pytest.fail("零配置不应调用 tushare"))
    monkeypatch.setattr(IndevsDataSource, "get_daily", lambda self, *a, **k: pytest.fail("零配置不应调用 indevs"))

    ds = CompositeDataSource("auto")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel
    # 零配置不应构造 tushare / indevs 源
    assert ds._tushare is None
    assert ds._indevs is None


def test_composite_auto_prefers_tushare_when_token_set(monkeypatch):
    """JNB 模式配置 TUSHARE_TOKEN（无 INDEVS_API_KEY）时 auto 模式优先 tushare。"""
    import modules.tushare_client as tc

    monkeypatch.setenv("DATA_MODE", "jnb")
    # 模块级常量在 import 时读取，monkeypatch.setenv 无效，需直接改模块属性
    monkeypatch.setenv("TUSHARE_API_URL", "https://tt.xiaodefa.cn")
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(TushareDataSource, "get_daily", lambda self, *a, **k: sentinel)
    monkeypatch.setattr(
        AStockDataDataSource,
        "get_daily",
        lambda self, *a, **k: pytest.fail("tushare 成功时不应回退 a-stock-data"),
    )

    ds = CompositeDataSource("auto")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel


def test_composite_auto_websearch_token_goes_a_stock_data(monkeypatch):
    """websearch 模式（默认）即使配置 TUSHARE_TOKEN 也走 a-stock-data（tushare 无数据后端）。"""
    monkeypatch.setenv("DATA_MODE", "websearch")
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(
        TushareDataSource, "get_daily", lambda self, *a, **k: pytest.fail("websearch 模式不应调用 tushare")
    )
    monkeypatch.setattr(IndevsDataSource, "get_daily", lambda self, *a, **k: pytest.fail("不应调用 indevs"))
    monkeypatch.setattr(AStockDataDataSource, "get_daily", lambda self, *a, **k: sentinel)

    ds = CompositeDataSource("auto")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel
    # 不应构造 tushare 源
    assert ds._tushare is None


def test_composite_auto_jnb_missing_url_falls_back(monkeypatch):
    """JNB 模式 + TUSHARE_TOKEN 但缺 TUSHARE_API_URL：构造 tushare 抛 ZettarancError，回退 a-stock-data 不崩溃。"""
    import modules.tushare_client as tc

    monkeypatch.setenv("DATA_MODE", "jnb")
    # 模块属性需显式置空：其他测试可能 reload 模块留下非空 TUSHARE_API_URL
    monkeypatch.setenv("TUSHARE_API_URL", "")
    monkeypatch.delenv("TUSHARE_API_URL", raising=False)
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(AStockDataDataSource, "get_daily", lambda self, *a, **k: sentinel)

    ds = CompositeDataSource("auto")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel
    assert ds._tushare is None


def test_composite_auto_prefers_indevs_over_tushare(monkeypatch):
    """同时配置 INDEVS_API_KEY 与 TUSHARE_TOKEN 时 auto 模式最优先 indevs。"""
    monkeypatch.setenv("INDEVS_API_KEY", "dummy-key")
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(IndevsDataSource, "get_daily", lambda self, *a, **k: sentinel)
    monkeypatch.setattr(
        TushareDataSource, "get_daily", lambda self, *a, **k: pytest.fail("indevs 优先，不应调用 tushare")
    )

    ds = CompositeDataSource("auto")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel


def test_composite_auto_falls_back_to_a_stock_data_when_tushare_returns_none(monkeypatch):
    """JNB 模式 tushare 无数据（返回 None）时 auto 模式回退 a-stock-data。"""
    import modules.tushare_client as tc

    monkeypatch.setenv("DATA_MODE", "jnb")
    monkeypatch.setenv("TUSHARE_API_URL", "https://tt.xiaodefa.cn")
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(TushareDataSource, "get_daily", lambda self, *a, **k: None)
    monkeypatch.setattr(AStockDataDataSource, "get_daily", lambda self, *a, **k: sentinel)

    ds = CompositeDataSource("auto")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel


def test_composite_auto_call_swallows_source_exception(monkeypatch):
    """_auto_call 遇到源抛异常（而非返回 None）时回退下一源，不向上抛。"""
    import modules.tushare_client as tc

    monkeypatch.setenv("DATA_MODE", "jnb")
    monkeypatch.setenv("TUSHARE_API_URL", "https://tt.xiaodefa.cn")
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    sentinel = pd.DataFrame([{"close": 1.0}])

    def _boom(self, *a, **k):
        raise KeyError("tushare boom")

    monkeypatch.setattr(TushareDataSource, "get_daily", _boom)
    monkeypatch.setattr(AStockDataDataSource, "get_daily", lambda self, *a, **k: sentinel)

    ds = CompositeDataSource("auto")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel


def test_composite_explicit_tushare_routes_to_tushare(monkeypatch):
    """preferred='tushare' 应路由 tushare 源（回归：旧实现误路由到 indevs）。"""
    import modules.tushare_client as tc

    monkeypatch.setenv("DATA_MODE", "jnb")
    monkeypatch.setenv("TUSHARE_API_URL", "https://tt.xiaodefa.cn")
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(TushareDataSource, "get_daily", lambda self, *a, **k: sentinel)
    monkeypatch.setattr(
        IndevsDataSource, "get_daily", lambda self, *a, **k: pytest.fail("preferred=tushare 不应调用 indevs")
    )

    ds = CompositeDataSource("tushare")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel


def test_composite_explicit_indevs_routes_to_indevs(monkeypatch):
    """preferred='indevs' 路由 indevs 源。"""
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    sentinel = pd.DataFrame([{"close": 1.0}])

    monkeypatch.setattr(
        TushareDataSource, "get_daily", lambda self, *a, **k: pytest.fail("preferred=indevs 不应调用 tushare")
    )
    monkeypatch.setattr(IndevsDataSource, "get_daily", lambda self, *a, **k: sentinel)

    ds = CompositeDataSource("indevs")
    assert ds.get_daily("600519.SH", "20260101", "20260102") is sentinel


def test_composite_auto_health_check_bool_contract(monkeypatch):
    """auto 模式 health_check 恒返回 bool：源探测异常（如 tushare 配置不完整）不向上抛。"""
    import modules.tushare_client as tc

    monkeypatch.setenv("DATA_MODE", "jnb")
    monkeypatch.setenv("TUSHARE_API_URL", "")  # TushareClient 构造抛 ZettarancError
    monkeypatch.delenv("INDEVS_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")

    monkeypatch.setattr(AStockDataDataSource, "health_check", lambda self: False)

    ds = CompositeDataSource("auto")
    result = ds.health_check()
    assert isinstance(result, bool)
    assert ds._tushare is None

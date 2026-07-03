"""
DataSource 协议与实现测试
"""

import pytest

from modules.bridge_client import is_bridge_available
from modules.datasource import (
    BridgeDataSource,
    CompositeDataSource,
    DataSource,
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

    def get_daily(self, ts_code: str, start_date: str, end_date: str):
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


def test_bridge_datasource_name():
    assert BridgeDataSource().name == "bridge"


def test_sqlite_datasource_name():
    assert SqliteDataSource().name == "sqlite"


def test_composite_prefers_bridge_when_available(monkeypatch):
    monkeypatch.setattr("modules.datasource.is_bridge_available", lambda: True)
    ds = CompositeDataSource()
    assert ds.health_check() is True


def test_composite_falls_back_to_sqlite(monkeypatch, temp_db, db_conn):
    from tests.conftest import write_klines_to_db, write_stock_basic

    monkeypatch.setattr("modules.datasource.is_bridge_available", lambda: False)
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

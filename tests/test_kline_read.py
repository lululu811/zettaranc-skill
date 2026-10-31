"""K 线读取 SQL 的单一来源护栏。

此前"取最近 N 天、按日期升序"的查询抄了三处：
``datasource.SqliteDataSource.get_kline_dicts``、
``datasource.CompositeDataSource.get_kline_dicts``（几乎是第一处的逐字副本）、
``indicators.data_layer.get_kline_data``。

现在都走 :func:`modules.core.kline.read_kline_rows`。
"""

from __future__ import annotations

import pytest

from modules.core.kline import KLINE_COLUMNS, read_kline_rows, read_kline_rows_batch, resolve_kline_limit


@pytest.fixture
def klined_db(temp_db, db_conn):
    """写入 3 天 K 线的临时库。"""
    from conftest import write_klines_to_db

    rows = [
        {
            "ts_code": "600519.SH",
            "trade_date": "20260101",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "vol": 1000.0,
            "amount": 10500.0,
            "pct_chg": 1.0,
        },
        {
            "ts_code": "600519.SH",
            "trade_date": "20260102",
            "open": 10.5,
            "high": 11.5,
            "low": 10.0,
            "close": 11.0,
            "vol": 1200.0,
            "amount": 13200.0,
            "pct_chg": 1.5,
        },
        {
            "ts_code": "600519.SH",
            "trade_date": "20260103",
            "open": 11.0,
            "high": 12.0,
            "low": 10.8,
            "close": 11.8,
            "vol": 900.0,
            "amount": 10620.0,
            "pct_chg": 1.2,
        },
    ]
    write_klines_to_db(db_conn, rows)
    return rows


class TestReadKlineRows:
    def test_returns_ascending_by_date(self, klined_db):
        from modules.database import get_db_connection

        with get_db_connection() as conn:
            rows = read_kline_rows("600519.SH", conn=conn)
        assert [r["trade_date"] for r in rows] == ["20260101", "20260102", "20260103"]

    def test_limit_takes_most_recent_days(self, klined_db):
        from modules.database import get_db_connection

        with get_db_connection() as conn:
            rows = read_kline_rows("600519.SH", conn=conn, limit=2)
        assert [r["trade_date"] for r in rows] == ["20260102", "20260103"]

    def test_date_range_filter(self, klined_db):
        from modules.database import get_db_connection

        with get_db_connection() as conn:
            rows = read_kline_rows(
                "600519.SH",
                conn=conn,
                start_date="20260102",
                end_date="20260103",
            )
        assert [r["trade_date"] for r in rows] == ["20260102", "20260103"]

    def test_limit_zero_returns_nothing(self, klined_db):
        """limit=0 表示不取任何行——indicators 路径此前恒带 LIMIT，语义保持。"""
        from modules.database import get_db_connection

        with get_db_connection() as conn:
            assert read_kline_rows("600519.SH", conn=conn, limit=0) == []

    def test_columns_are_the_single_definition(self):
        assert KLINE_COLUMNS == (
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol",
            "amount",
            "pct_chg",
        )


class TestConsumersUseTheSharedReader:
    def test_sqlite_datasource_matches_shared_reader(self, klined_db):
        from modules.core.kline import read_kline_rows
        from modules.database import get_db_connection
        from modules.datasource import SqliteDataSource

        with get_db_connection() as conn:
            expected = read_kline_rows("600519.SH", conn=conn, limit=60)
        assert SqliteDataSource().get_kline_dicts("600519.SH", days=60) == expected

    def test_composite_datasource_matches_sqlite(self, klined_db):
        """DB 有数据时，Composite 与 Sqlite 必须给出同一批 K 线。

        此前 Composite 内联复制了 Sqlite 的 SQL，两边可能漂移。
        """
        from modules.datasource import CompositeDataSource, SqliteDataSource

        expected = SqliteDataSource().get_kline_dicts("600519.SH", days=60)
        assert CompositeDataSource("auto").get_kline_dicts("600519.SH", days=60) == expected

    def test_indicators_reader_matches_shared_reader(self, klined_db):
        """indicators 的 get_kline_data 与共享 reader 取到同一批行。"""
        from modules.core.kline import read_kline_rows
        from modules.database import get_db_connection
        from modules.indicators.data_layer import get_kline_data

        with get_db_connection() as conn:
            expected = read_kline_rows("600519.SH", conn=conn, limit=100)
        daily = get_kline_data("600519.SH", days=100)
        assert [d.trade_date for d in daily] == [r["trade_date"] for r in expected]


class TestResolveKlineLimit:
    """``days`` 与日期区间的优先级——6 个数据源实现各写一遍，此处只定义一处。

    协议：给了 ``start_date`` 就以区间为准（``days`` 被忽略）；否则按 ``days``
    截断最近 N 天。DB 路径与 API 路径若漂移，会给出不同长度的 K 线。
    """

    def test_start_date_wins_over_days(self):
        """给了 start_date → 不截断（区间内全部）。"""
        assert resolve_kline_limit(days=2, start_date="20260101") is None

    def test_days_limits_without_start_date(self):
        assert resolve_kline_limit(days=2, start_date=None) == 2

    def test_non_positive_days_means_no_limit(self):
        assert resolve_kline_limit(days=0, start_date=None) is None
        assert resolve_kline_limit(days=-5, start_date=None) is None


class TestStartDateOverridesDaysInConsumers:
    """行为护栏：DB 路径在有 start_date 时不得按 days 截断。

    此前 sqlite/composite 的 SQL 各自写死 ``if not start_date and days > 0``，
    统一到 helper 时最容易把这条规则弄丢——丢了就会静默少返回 K 线。
    """

    def test_sqlite_datasource_keeps_full_range_with_start_date(self, klined_db):
        from modules.datasource import SqliteDataSource

        rows = SqliteDataSource().get_kline_dicts("600519.SH", days=1, start_date="20260101")
        assert [r["trade_date"] for r in rows] == ["20260101", "20260102", "20260103"]

    def test_composite_datasource_keeps_full_range_with_start_date(self, klined_db):
        from modules.datasource import CompositeDataSource

        rows = CompositeDataSource("auto").get_kline_dicts("600519.SH", days=1, start_date="20260101")
        assert [r["trade_date"] for r in rows] == ["20260101", "20260102", "20260103"]

    def test_batch_reader_keeps_full_range_with_start_date(self, klined_db):
        from modules.database import get_db_connection

        with get_db_connection() as conn:
            result = read_kline_rows_batch(["600519.SH"], conn=conn, days=1, start_date="20260101")
        assert [r["trade_date"] for r in result["600519.SH"]] == ["20260101", "20260102", "20260103"]

    def test_batch_reader_matches_single_reader(self, klined_db):
        """批量路径与单只路径必须给出同一批 K 线（此前是两份独立 SQL）。"""
        from modules.database import get_db_connection
        from modules.datasource import SqliteDataSource

        with get_db_connection() as conn:
            batch = read_kline_rows_batch(["600519.SH"], conn=conn, days=60)
        single = SqliteDataSource().get_kline_dicts("600519.SH", days=60)
        assert batch["600519.SH"] == single

    def test_batch_reader_truncates_by_days_without_start_date(self, klined_db):
        from modules.database import get_db_connection

        with get_db_connection() as conn:
            result = read_kline_rows_batch(["600519.SH"], conn=conn, days=2)
        assert [r["trade_date"] for r in result["600519.SH"]] == ["20260102", "20260103"]


class TestOtherConsumersUseTheSharedReader:
    """bridge_client 与 market_timing 的 SQLite 路径此前也各抄了一份 SQL。"""

    def test_bridge_local_daily_matches_shared_reader(self, klined_db):
        from modules.bridge_client import _get_local_daily
        from modules.core.kline import read_kline_rows
        from modules.database import get_db_connection

        with get_db_connection() as conn:
            expected = read_kline_rows("600519.SH", conn=conn, limit=60)
        assert _get_local_daily("600519.SH", days=60) == expected

    def test_bridge_local_daily_keeps_full_range_with_start_date(self, klined_db):
        """bridge 的截断规则同样必须服从"start_date 优先"。"""
        from modules.bridge_client import _get_local_daily

        rows = _get_local_daily("600519.SH", days=1, start_date="20260101")
        assert [r["trade_date"] for r in rows] == ["20260101", "20260102", "20260103"]

    def test_market_timing_index_klines_match_shared_reader(self, klined_db):
        """market_timing 的指数路径取 8 列（无 pct_chg），值须与共享 reader 一致。"""
        from modules.core.kline import read_kline_rows
        from modules.database import get_db_connection
        from modules.market_timing import _load_index_klines_sqlite

        with get_db_connection() as conn:
            expected = read_kline_rows(
                "600519.SH",
                conn=conn,
                limit=100,
                columns=("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"),
            )
        daily = _load_index_klines_sqlite("600519.SH", days=100)
        assert [d.trade_date for d in daily] == [r["trade_date"] for r in expected]
        assert [d.close for d in daily] == [r["close"] for r in expected]

    def test_market_timing_computes_pct_chg_locally(self, klined_db):
        """指数行的 pct_chg 由相邻收盘价本地计算，不取库里的值。"""
        from modules.market_timing import _load_index_klines_sqlite

        daily = _load_index_klines_sqlite("600519.SH", days=100)
        assert daily[0].pct_chg == 0.0  # 首行 prev_close == close
        # 第二行 prev_close = 10.5，close = 11.0
        assert abs(daily[1].pct_chg - (11.0 / 10.5 - 1.0) * 100.0) < 1e-9

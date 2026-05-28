"""
watchlist.py 自选股观察池测试
"""

import pytest
from modules.watchlist import (
    add_watch, remove_watch, list_watch,
    scan_watchlist, WatchAlert,
)


class TestWatchlistCRUD:
    def test_add_and_list(self, temp_db, db_conn):
        from tests.conftest import write_stock_basic
        write_stock_basic(db_conn, "600519.SH", "贵州茅台")

        wid = add_watch("600519.SH", name="贵州茅台", tags="波段")
        assert wid > 0

        watches = list_watch()
        assert len(watches) == 1
        assert watches[0]["ts_code"] == "600519.SH"
        assert watches[0]["tags"] == "波段"

    def test_remove(self, temp_db, db_conn):
        from tests.conftest import write_stock_basic
        write_stock_basic(db_conn, "000001.SZ", "平安银行")

        add_watch("000001.SZ", name="平安银行")
        assert len(list_watch()) == 1

        assert remove_watch("000001.SZ") is True
        assert len(list_watch()) == 0

    def test_list_by_tags(self, temp_db, db_conn):
        from tests.conftest import write_stock_basic
        write_stock_basic(db_conn, "600519.SH", "贵州茅台")
        write_stock_basic(db_conn, "000001.SZ", "平安银行")

        add_watch("600519.SH", tags="波段")
        add_watch("000001.SZ", tags="短线")

        band = list_watch(tags="波段")
        assert len(band) == 1
        assert band[0]["ts_code"] == "600519.SH"


class TestScanWatchlist:
    def test_empty(self, temp_db):
        result = scan_watchlist()
        assert result["summary"]["total"] == 0
        assert result["alerts"] == []

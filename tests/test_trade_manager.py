"""
trade_manager.py 交易记录管理测试
覆盖修复后的三个函数：get_indicator_data / get_stock_info / match_strategy
"""

import pytest
from modules.trade_manager import (
    TradeManager,
    get_indicator_data,
    get_stock_info,
    match_strategy,
)
from modules.database import save_trade_record, get_connection


class TestGetIndicatorData:
    def test_no_cache_no_kline(self, temp_db):
        """无缓存且无K线数据时应返回 None"""
        result = get_indicator_data("000001.SZ", "20260101")
        assert result is None

    def test_with_stock_basic_only(self, temp_db, db_conn):
        """仅有股票基本信息，无K线时返回 None"""
        from tests.conftest import write_stock_basic
        write_stock_basic(db_conn, "000001.SZ", "平安银行")
        result = get_indicator_data("000001.SZ", "20260101")
        assert result is None


class TestGetStockInfo:
    def test_exists(self, temp_db, db_conn):
        from tests.conftest import write_stock_basic
        write_stock_basic(db_conn, "600519.SH", "贵州茅台")
        info = get_stock_info("600519.SH")
        assert info is not None
        assert info["name"] == "贵州茅台"

    def test_not_exists(self, temp_db):
        info = get_stock_info("999999.XY")
        assert info is None


class TestMatchStrategy:
    def test_none_indicators(self):
        assert match_strategy(None) is None
        assert match_strategy({}) is None

    def test_missing_fields(self):
        assert match_strategy({"ts_code": "600519.SH"}) is None
        assert match_strategy({"trade_date": "20260101"}) is None


class TestTradeManagerCRUD:
    def test_add_and_get_trade(self, temp_db):
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        mgr = TradeManager()
        trade_id = mgr.add_trade({
            "ts_code": "600519.SH",
            "trade_date": today,
            "action": "BUY",
            "price": 1500.0,
            "quantity": 100,
            "amount": 150000.0,
            "reason": "B1买点",
        })
        assert trade_id > 0

        trade = mgr.get_trade_history("600519.SH", days=30)
        assert len(trade) == 1
        assert trade[0]["action"] == "BUY"

    def test_get_stock_holding(self, temp_db):
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        mgr = TradeManager()
        mgr.add_trade({
            "ts_code": "600519.SH",
            "trade_date": today,
            "action": "BUY",
            "price": 1400.0,
            "quantity": 100,
            "amount": 140000.0,
        })
        mgr.add_trade({
            "ts_code": "600519.SH",
            "trade_date": today,
            "action": "SELL",
            "price": 1500.0,
            "quantity": 50,
            "amount": 75000.0,
        })

        holding = mgr.get_stock_holding("600519.SH")
        assert holding["current_qty"] == 50
        assert holding["avg_cost"] == 1400.0

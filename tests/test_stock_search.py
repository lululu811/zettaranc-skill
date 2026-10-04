"""股票联想搜索回归测试（代码 / 中文名称 / 拼音）"""

from __future__ import annotations

import pytest


STOCKS = [
    ("000001.SZ", "平安银行", "银行", "主板"),
    ("600487.SH", "亨通光电", "通信设备", "主板"),
    ("601318.SH", "中国平安", "保险", "主板"),
    ("300750.SZ", "宁德时代", "电气设备", "创业板"),
]


@pytest.fixture
def search_index(temp_db):
    """写入少量 stock_basic 数据并重建搜索索引"""
    from modules.database import get_connection
    from api.services import stock_service

    with get_connection() as conn:
        cur = conn.cursor()
        for ts_code, name, industry, market in STOCKS:
            cur.execute(
                "INSERT OR REPLACE INTO stock_basic (ts_code, name, industry, market) VALUES (?,?,?,?)",
                (ts_code, name, industry, market),
            )

    stock_service.invalidate_search_index()
    yield stock_service
    stock_service.invalidate_search_index()


def test_search_by_code_prefix(search_index):
    results = search_index.search_stocks("6004", limit=10)
    assert [r["ts_code"] for r in results] == ["600487.SH"]
    assert results[0]["match_type"] == "code_prefix"


def test_search_by_chinese_name(search_index):
    results = search_index.search_stocks("平安", limit=10)
    codes = [r["ts_code"] for r in results]
    assert codes[:2] == ["000001.SZ", "601318.SH"]  # 名称前缀优先于子串


def test_search_by_pinyin_initials(search_index):
    results = search_index.search_stocks("payh", limit=10)
    assert [r["ts_code"] for r in results] == ["000001.SZ"]
    assert results[0]["match_type"] == "initials_prefix"


def test_search_by_full_pinyin(search_index):
    results = search_index.search_stocks("pingan", limit=10)
    assert "000001.SZ" in [r["ts_code"] for r in results]


def test_search_empty_query_returns_empty(search_index):
    assert search_index.search_stocks("", limit=10) == []


def test_search_respects_limit(search_index):
    results = search_index.search_stocks("银行", limit=1)
    assert len(results) == 1


def test_search_result_fields(search_index):
    item = search_index.search_stocks("000001", limit=1)[0]
    assert item["name"] == "平安银行"
    assert item["industry"] == "银行"
    assert item["market"] == "主板"

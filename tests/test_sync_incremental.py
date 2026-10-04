"""增量同步回归测试

覆盖：
- sync_all_daily_kline(incremental=True) 以 daily_kline 实际最后一根 K 线为断点
- 已同步到最新时不再发请求
- K 线 UPSERT 不清除 sync_daily_basic 写入的估值列
- sync_indicator_cache 增量只写新增交易日、warmup 段不写库

注意：不使用 db_conn fixture（长事务会锁库），每步操作都自建短连接并提交。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
import pytest

CODE = "600519.SH"


def _conn():
    from modules.database import get_connection

    return get_connection()


def _make_syncer():
    from modules.data_sync.syncer import DataSyncer

    fake = Mock()
    fake.name = "fake"
    return DataSyncer(token="dummy", datasource=fake)


def _kline_df(ts_code: str, trade_date: str, close: float = 11.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": ts_code,
                "trade_date": trade_date,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "vol": 1000.0,
                "amount": close * 1000,
                "pct_chg": 1.2,
            }
        ]
    )


def _insert_kline(ts_code: str, trade_date: str, close: float = 10.0):
    with _conn() as conn:
        conn.cursor().execute(
            "INSERT OR REPLACE INTO daily_kline (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (ts_code, trade_date, close, close, close, close, 1000.0, close * 1000, 0.0),
        )


def _query(sql: str, params: tuple = ()):
    with _conn() as conn:
        return conn.cursor().execute(sql, params).fetchall()


# ==================== K 线增量断点 ====================


def test_incremental_uses_kline_last_date_as_breakpoint(temp_db):
    """incremental=True：起点 = 库里最后一根 K 线的下一天"""
    _insert_kline(CODE, "20240102")
    syncer = _make_syncer()

    captured = {}

    def fake(ts_code, start_date, end_date):
        captured["start"] = start_date
        return _kline_df(ts_code, "20240103")

    with patch.object(syncer._fetcher, "fetch_daily_kline", side_effect=fake):
        syncer.sync_all_daily_kline(ts_codes=[CODE], days=730, incremental=True)

    assert captured["start"] == "20240103"


def test_non_incremental_uses_days_window(temp_db):
    """incremental=False：按 days 窗口整段重拉"""
    _insert_kline(CODE, "20240102")
    syncer = _make_syncer()

    captured = {}

    def fake(ts_code, start_date, end_date):
        captured["start"] = start_date
        return _kline_df(ts_code, "20240103")

    with patch.object(syncer._fetcher, "fetch_daily_kline", side_effect=fake):
        syncer.sync_all_daily_kline(ts_codes=[CODE], days=30, incremental=False)

    expected = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    assert captured["start"] == expected


def test_incremental_skips_when_already_up_to_date(temp_db):
    """库里已是最新交易日：不发请求"""
    today = datetime.now().strftime("%Y%m%d")
    _insert_kline(CODE, today)
    syncer = _make_syncer()

    with patch.object(syncer._fetcher, "fetch_daily_kline", side_effect=_kline_df) as m:
        result = syncer.sync_all_daily_kline(ts_codes=[CODE], days=730, incremental=True)

    assert m.call_count == 0
    assert result[CODE] == 0


def test_incremental_falls_back_to_days_for_new_code(temp_db):
    """库里无数据：回落到 days 窗口"""
    syncer = _make_syncer()
    captured = {}

    def fake(ts_code, start_date, end_date):
        captured["start"] = start_date
        return _kline_df(ts_code, "20240103")

    with patch.object(syncer._fetcher, "fetch_daily_kline", side_effect=fake):
        syncer.sync_all_daily_kline(ts_codes=[CODE], days=30, incremental=True)

    expected = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    assert captured["start"] == expected


# ==================== 写入正确性 ====================


def test_kline_upsert_preserves_fundamental_columns(temp_db):
    """重拉 K 线不得清空 pe/pb/total_mv（sync_daily_basic 写入的列）"""
    syncer = _make_syncer()
    syncer.ensure_daily_basic_columns()

    _insert_kline(CODE, "20240102", close=10.0)
    with _conn() as conn:
        conn.cursor().execute(
            "UPDATE daily_kline SET pe=9.9, pb=1.1, total_mv=123.0 WHERE ts_code=? AND trade_date=?",
            (CODE, "20240102"),
        )

    with patch.object(syncer._fetcher, "fetch_daily_kline", side_effect=lambda c, s, e: _kline_df(c, "20240102", 99.0)):
        syncer.sync_daily_kline(CODE, "20240102", "20240102")

    row = _query(
        "SELECT close, pe, pb, total_mv FROM daily_kline WHERE ts_code=? AND trade_date=?", (CODE, "20240102")
    )[0]

    assert row["close"] == 99.0  # 行情列被更新
    assert row["pe"] == 9.9  # 基本面列保留
    assert row["pb"] == 1.1
    assert row["total_mv"] == 123.0


# ==================== 指标缓存增量 ====================


@pytest.fixture
def klines_60(temp_db):
    """写入 60 根 K 线到 daily_kline"""
    rows = []
    dt = datetime(2024, 1, 1)
    price = 100.0
    for i in range(60):
        price *= 1.002
        rows.append(
            {
                "ts_code": CODE,
                "trade_date": (dt + timedelta(days=i)).strftime("%Y%m%d"),
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "vol": 10000.0 * (1 + i * 0.01),
                "amount": price * 10000,
                "pct_chg": 0.2,
            }
        )
    with _conn() as conn:
        cur = conn.cursor()
        for r in rows:
            cur.execute(
                "INSERT OR REPLACE INTO daily_kline"
                " (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    r["ts_code"],
                    r["trade_date"],
                    r["open"],
                    r["high"],
                    r["low"],
                    r["close"],
                    r["vol"],
                    r["amount"],
                    r["pct_chg"],
                ),
            )
    return rows


def test_indicator_cache_warmup_not_written(klines_60):
    """warmup 段只参与计算，不写回 indicator_cache"""
    syncer = _make_syncer()
    written = syncer.sync_indicator_cache(CODE, days=10, warmup=20, incremental=False)

    assert written == 10
    dates = [
        r["trade_date"]
        for r in _query("SELECT trade_date FROM indicator_cache WHERE ts_code=? ORDER BY trade_date", (CODE,))
    ]
    assert dates == [r["trade_date"] for r in klines_60[-10:]]


def test_indicator_cache_incremental_only_writes_new_days(klines_60):
    """incremental=True：已算过的交易日不重写"""
    syncer = _make_syncer()
    first = syncer.sync_indicator_cache(CODE, days=30, warmup=30, incremental=False)
    assert first > 0

    # 打标记：把已缓存行的 ma5 改成哨兵值
    with _conn() as conn:
        conn.cursor().execute("UPDATE indicator_cache SET ma5=999.0 WHERE ts_code=?", (CODE,))

    second = syncer.sync_indicator_cache(CODE, days=30, warmup=30, incremental=True)
    assert second == 0

    sentinel = _query("SELECT COUNT(*) AS c FROM indicator_cache WHERE ts_code=? AND ma5=999.0", (CODE,))[0]
    assert sentinel["c"] == first  # 旧值未被覆盖


def test_indicator_cache_incremental_writes_newly_added_day(klines_60):
    """K 线新增一天后，增量只补算这一天"""
    syncer = _make_syncer()
    syncer.sync_indicator_cache(CODE, days=30, warmup=30, incremental=False)

    last_date = klines_60[-1]["trade_date"]
    new_date = (datetime.strptime(last_date, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    _insert_kline(CODE, new_date, close=klines_60[-1]["close"] * 1.01)

    written = syncer.sync_indicator_cache(CODE, days=30, warmup=30, incremental=True)
    assert written == 1

    row = _query("SELECT trade_date FROM indicator_cache WHERE ts_code=? ORDER BY trade_date DESC LIMIT 1", (CODE,))[0]
    assert row["trade_date"] == new_date

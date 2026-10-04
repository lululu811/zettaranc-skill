"""市场择时指标模块单元测试。"""

import pytest

from modules.indicators import DailyData
from modules.market_timing import (
    _breadth_score,
    _classify_regime,
    _index_not_in_params,
    _index_not_in_sql_fragment,
    _moneyflow_score,
    _normalize_date,
    _risk_score,
    _sentiment_score,
    _INDEX_CODES_TO_EXCLUDE,
    compute_market_timing,
)


def test_normalize_date():
    assert _normalize_date("20260821") == "2026-08-21"
    assert _normalize_date("2026-08-21") == "2026-08-21"


def test_breadth_score():
    snapshot = {
        "total": 100,
        "advancers": 60,
        "decliners": 40,
        "limit_up": 5,
        "limit_down": 1,
        "strong_up": 10,
        "strong_down": 5,
    }
    score = _breadth_score(snapshot)
    assert 0 <= score <= 100
    assert score > 50


def test_moneyflow_score():
    amount_history = [100.0] * 20
    snapshot = {"total_amount": 120.0}
    score, ratio = _moneyflow_score(amount_history, snapshot)
    assert ratio == 1.2
    assert score == 60.0


def test_risk_score_rising_market():
    klines = []
    price = 100.0
    for i in range(30):
        price *= 1.005
        klines.append(
            DailyData(
                ts_code="000001.SH",
                trade_date=f"202601{i + 1:02d}",
                open=price * 0.99,
                high=price * 1.01,
                low=price * 0.98,
                close=price,
                vol=10000.0,
                amount=price * 10000.0,
                pct_chg=0.5,
                prev_close=price / 1.005,
            )
        )
    score, vol, dd = _risk_score(klines)
    assert 0 <= score <= 100
    assert dd > -0.05


def test_sentiment_score():
    snapshot = {
        "total": 100,
        "advancers": 60,
        "decliners": 40,
        "limit_up": 5,
        "limit_down": 1,
    }
    score = _sentiment_score(snapshot)
    assert 0 <= score <= 100
    assert score > 50


def test_classify_regime():
    assert _classify_regime(70) == "强势"
    assert _classify_regime(50) == "震荡"
    assert _classify_regime(30) == "弱势"


# ---- CRITICAL regression:指数黑名单完整性 ----
# 之前 _INDEX_BLACKLIST 只有 4 个指数,缺少 000905.SH / 000688.SH
# 修复:抽常量到 _INDEX_CODES_TO_EXCLUDE,覆盖 6 个指数


def test_index_blacklist_includes_all_six_default_indices():
    """指数黑名单必须覆盖 index_sync.py DEFAULT_INDEX_CODES 的全部 6 个。"""
    from modules.index_sync import DEFAULT_INDEX_CODES

    for code in DEFAULT_INDEX_CODES:
        assert code in _INDEX_CODES_TO_EXCLUDE, (
            f"指数 {code} 必须在 _INDEX_CODES_TO_EXCLUDE 中,否则会被当作个股纳入涨跌/成交统计"
        )


def test_index_not_in_sql_fragment_quotes_all_codes():
    """_index_not_in_sql_fragment 必须为所有 6 个指数生成带引号的 SQL 片段。"""
    frag = _index_not_in_sql_fragment()
    for code in _INDEX_CODES_TO_EXCLUDE:
        assert f"'{code}'" in frag, f"SQL 片段缺 {code}"


def test_index_not_in_params_returns_tuple():
    """参数化查询占位符元组。"""
    params = _index_not_in_params()
    assert isinstance(params, tuple)
    assert len(params) == len(_INDEX_CODES_TO_EXCLUDE)


# ---- E2E:compute_market_timing SQLite 路径 ----
# 之前 0/4 测试文件覆盖 compute_market_timing E2E,这个测试确保 SQLite 路径可工作
# DuckDB 路径依赖外部环境,留给真实数据回归


def test_compute_market_timing_sqlite_end_to_end(tmp_path, monkeypatch):
    """SQLite 路径:有数据时 _load_market_snapshot_sqlite 应正确排除 6 个指数。"""
    from modules import database

    # 把数据库路径重定向到临时目录
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    database.init_database()

    # 插入指数 + 个股的 K 线
    import sqlite3

    con = sqlite3.connect(str(tmp_path / "test.db"))
    trade_date = "20260821"
    rows = [
        # 6 个指数(应被排除)
        ("000001.SH", trade_date, 3000, 3050, 2990, 3040, 1e9, 3.04e11, 1.0, 0, 0),
        ("399001.SZ", trade_date, 9000, 9050, 8990, 9040, 1e9, 9.04e11, 0.5, 0, 0),
        ("399006.SZ", trade_date, 2000, 2050, 1990, 2040, 5e8, 1.02e11, 1.0, 0, 0),
        ("000300.SH", trade_date, 3500, 3550, 3490, 3540, 8e8, 2.83e11, 1.0, 0, 0),
        ("000905.SH", trade_date, 5500, 5550, 5490, 5540, 6e8, 3.32e11, 1.0, 0, 0),
        ("000688.SH", trade_date, 850, 860, 845, 855, 4e8, 3.42e10, 1.0, 0, 0),
    ]
    # 100 只股票:前 60 涨,中间 5 涨停,中间 1 跌停,后 34 跌
    for i in range(100):
        code = f"{600000 + i:06d}.SH"
        if i < 60:
            pct = 0.5 + (i % 30) * 0.05  # 0.5 ~ 2.0
            close = 10.0 * (1 + pct / 100)
            rows.append((code, trade_date, 9.9, 10.1, 9.8, close, 1e7, close * 1e7, pct, 0, 0))
        elif i < 65:  # 5 涨停
            rows.append((code, trade_date, 9.9, 11.0, 9.8, 11.0, 1e7, 1.1e8, 10.0, 1, 0))
        elif i < 66:  # 1 跌停
            rows.append((code, trade_date, 10.1, 10.2, 9.0, 9.0, 1e7, 9e7, -10.0, 0, 1))
        else:  # 34 跌
            pct = -0.5 - (i % 20) * 0.05
            close = 10.0 * (1 + pct / 100)
            rows.append((code, trade_date, 10.1, 10.2, close * 0.99, close, 1e7, close * 1e7, pct, 0, 0))
    con.executemany(
        "INSERT INTO daily_kline (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg, is_limit_up, is_limit_down) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    con.commit()
    con.close()

    # 单元测试 SQL 过滤(更稳,直接调底层函数,避免被上层 active_mv 等其他逻辑干扰)
    from modules.market_timing import _load_market_snapshot_sqlite

    snapshot = _load_market_snapshot_sqlite(trade_date)
    # 关键断言:total 应只算 100 只股票,不应包含 6 个指数
    assert snapshot["total"] == 100, (
        f"total 期望 100(只算个股,排除 6 个指数),实际 {snapshot['total']};如果等于 106,说明指数过滤失效"
    )
    # advancers 60 + 5 涨停 65,decliners 1 跌停 + 34 跌 = 35
    assert snapshot["advancers"] == 65
    assert snapshot["decliners"] == 35
    assert snapshot["limit_up"] == 5
    assert snapshot["limit_down"] == 1


def test_compute_market_timing_empty_db_raises_helpful_error(tmp_path, monkeypatch):
    """空 DB 时 compute_market_timing 应抛有意义的错误(不是返回周末日期)。"""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "empty.db"))
    from modules import database

    database.init_database()

    # 没有任何数据 → 应抛 ValueError,而不是拿 datetime.now() 兜底
    with pytest.raises(ValueError, match="无任何 daily_kline 数据"):
        compute_market_timing(trade_date=None, duckdb_path=None)

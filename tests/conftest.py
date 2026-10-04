"""
测试基础设施
提供临时数据库 fixture 和测试数据工厂
"""

import os
import sys
import tempfile
import pytest
from datetime import datetime, timedelta
from pathlib import Path

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def mock_env_for_tests():
    """所有测试自动设置 mock 环境变量"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        env_vars = {
            "DATA_MODE": "websearch",
            "DB_PATH": db_path,
            "DATA_DIR": tmpdir,
        }
        # 清除可能影响测试的已有变量（含开发者本地 .env 注入的数据源 Key，保证用例封闭）
        for key in list(os.environ.keys()):
            if key in (
                "DATA_MODE",
                "DB_PATH",
                "DATA_DIR",
                "TUSHARE_TOKEN",
                "HITHINK_FINANCE_API_KEY",
                "HITHINK_FINANCE_API_URL",
            ):
                del os.environ[key]
        os.environ.update(env_vars)
        # 每次测试清空 bridge 健康缓存，隔离 patch _http_get 的 auto 测试（不触发 set_bridge_config）
        from modules import bridge_client

        bridge_client.reset_bridge_health_cache()
        yield db_path


@pytest.fixture
def temp_db(mock_env_for_tests):
    """提供初始化好的临时数据库"""
    from modules.database import init_database, drop_all_tables

    init_database()
    yield mock_env_for_tests
    try:
        drop_all_tables()
    except Exception:
        pass


@pytest.fixture
def db_conn(temp_db):
    """提供数据库连接"""
    from modules.database import get_connection

    with get_connection() as conn:
        yield conn


def make_kline_row(ts_code="600519.SH", base_date="20260101", base_price=1500.0, base_vol=10000.0):
    """
    工厂函数：生成单根 K 线数据（dict 格式，用于 strategies/screener 模块）
    """
    return {
        "ts_code": ts_code,
        "trade_date": base_date,
        "open": base_price,
        "high": base_price * 1.02,
        "low": base_price * 0.98,
        "close": base_price,
        "vol": base_vol,
        "amount": base_price * base_vol,
        "pct_chg": 0.0,
        "prev_close": base_price,
        "prev_vol": base_vol,
        "is_rise": False,
        "is_beidou": False,
        "is_suoliang": False,
        "is_jiayin": False,
        "is_yinxian": False,
        "is_fangliang_yinxian": False,
    }


def make_daily_data(ts_code="600519.SH", base_date="20260101", base_price=1500.0, base_vol=10000.0):
    """
    工厂函数：生成 DailyData 对象（用于 indicators 模块）
    """
    from modules.indicators import DailyData

    return DailyData(
        ts_code=ts_code,
        trade_date=base_date,
        open=base_price,
        high=base_price * 1.02,
        low=base_price * 0.98,
        close=base_price,
        vol=base_vol,
        amount=base_price * base_vol,
        pct_chg=0.0,
        prev_close=base_price,
    )


def generate_uptrend_klines(
    n=120, ts_code="600519.SH", start_date="20250601", start_price=100.0, daily_pct=0.5, vol_base=10000
):
    """
    生成 n 天上升趋势的 K 线数据（dict 格式）
    """
    rows = []
    dt = datetime.strptime(start_date, "%Y%m%d")
    price = start_price
    for i in range(n):
        date_str = dt.strftime("%Y%m%d")
        prev_price = price
        price *= 1 + daily_pct / 100
        vol = vol_base * (1 + i * 0.01)  # 温和放量
        prev_close = rows[-1]["close"] if rows else price * 0.995
        rows.append(
            {
                "ts_code": ts_code,
                "trade_date": date_str,
                "open": prev_price,
                "high": price * 1.01,
                "low": prev_price * 0.99,
                "close": price,
                "vol": vol,
                "amount": price * vol,
                "pct_chg": (price - prev_close) / prev_close * 100,
                "prev_close": prev_close,
                "prev_vol": rows[-1]["vol"] if rows else vol,
                "is_rise": price > prev_close,
                "is_beidou": vol >= (rows[-1]["vol"] * 2 if rows else vol),
                "is_suoliang": vol <= (rows[-1]["vol"] * 0.5 if rows else vol),
                "is_jiayin": price < prev_price and price > prev_close,
                "is_yinxian": price < prev_close,
                "is_fangliang_yinxian": price < prev_close and vol > (rows[-1]["vol"] * 1.5 if rows else vol),
            }
        )
        dt += timedelta(days=1)
    return rows


def generate_downtrend_klines(
    n=120, ts_code="600519.SH", start_date="20250601", start_price=200.0, daily_pct=-0.8, vol_base=10000
):
    """
    生成 n 天下降趋势的 K 线数据（dict 格式）
    """
    rows = []
    dt = datetime.strptime(start_date, "%Y%m%d")
    price = start_price
    for i in range(n):
        date_str = dt.strftime("%Y%m%d")
        prev_price = price
        price *= 1 + daily_pct / 100
        vol = vol_base * (1 - i * 0.005)  # 缩量下跌
        if vol < 1000:
            vol = 1000
        prev_close = rows[-1]["close"] if rows else price * 1.008
        rows.append(
            {
                "ts_code": ts_code,
                "trade_date": date_str,
                "open": prev_price,
                "high": prev_price * 1.005,
                "low": price * 0.99,
                "close": price,
                "vol": vol,
                "amount": price * vol,
                "pct_chg": (price - prev_close) / prev_close * 100,
                "prev_close": prev_close,
                "prev_vol": rows[-1]["vol"] if rows else vol,
                "is_rise": price > prev_close,
                "is_beidou": vol >= (rows[-1]["vol"] * 2 if rows else vol),
                "is_suoliang": vol <= (rows[-1]["vol"] * 0.5 if rows else vol),
                "is_jiayin": price < prev_price and price > prev_close,
                "is_yinxian": price < prev_close,
                "is_fangliang_yinxian": price < prev_close and vol > (rows[-1]["vol"] * 1.5 if rows else vol),
            }
        )
        dt += timedelta(days=1)
    return rows


def generate_b1_scenario(ts_code="600519.SH"):
    """
    生成 B1 买点场景：价格连续下跌后 J 值打到负值 + 缩量
    120 天数据，最后几天满足 B1 条件
    """
    # 先 100 天震荡
    rows = generate_uptrend_klines(n=100, ts_code=ts_code, start_price=150.0, daily_pct=0.05)
    # 再 20 天快速下跌，J 打到负值
    price = rows[-1]["close"]
    dt = datetime.strptime(rows[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
    for i in range(20):
        date_str = dt.strftime("%Y%m%d")
        prev_close = price
        price *= 0.97  # 每天跌 3%
        vol = 5000 * (1 - i * 0.04)  # 持续缩量
        if vol < 500:
            vol = 500
        rows.append(
            {
                "ts_code": ts_code,
                "trade_date": date_str,
                "open": prev_close,
                "high": prev_close * 0.995,
                "low": price * 0.99,
                "close": price,
                "vol": vol,
                "amount": price * vol,
                "pct_chg": (price - prev_close) / prev_close * 100,
                "prev_close": prev_close,
                "prev_vol": rows[-1]["vol"] if rows else vol,
                "is_rise": price > prev_close,
                "is_beidou": False,
                "is_suoliang": vol <= rows[-1]["vol"] * 0.6 if rows else False,
                "is_jiayin": False,
                "is_yinxian": True,
                "is_fangliang_yinxian": False,
            }
        )
        dt += timedelta(days=1)
    return rows


def write_klines_to_db(db_conn, rows):
    """将 K 线数据写入数据库"""
    cursor = db_conn.cursor()
    for row in rows:
        cursor.execute(
            """
            INSERT OR REPLACE INTO daily_kline
            (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                row["ts_code"],
                row["trade_date"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["vol"],
                row["amount"],
                row["pct_chg"],
            ),
        )
    db_conn.commit()


def write_stock_basic(db_conn, ts_code="600519.SH", name="贵州茅台", industry="白酒", market="主板"):
    """写入股票基本信息"""
    cursor = db_conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO stock_basic
        (ts_code, name, area, industry, market, list_date, is_hs)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (ts_code, name, "贵州", industry, market, "20010801", "SH"),
    )
    db_conn.commit()


@pytest.fixture
def state_with_interrupted_run(tmp_path):
    """上次 run 到 round 2 中断, 验证下次 run 询问恢复."""
    import json

    state_file = tmp_path / "self_optimizer_state.json"
    state = {
        "run_id": "2026-06-10-abcd",
        "started_at": "2026-06-10T07:30:00",
        "target": "trading",
        "mode": "dry_run",
        "current_round": 2,
        "baseline_score": 80.0,
        "rounds": [
            {"round": 1, "old": 80.0, "new": 82.5, "delta": 2.5, "status": "keep"},
        ],
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    yield state_file


@pytest.fixture
def mock_monthly_reviews_with_poor_strategy():
    """mock 3 个月复盘数据, 一只策略 stock_count=1 胜率 -30%."""
    from datetime import datetime, timedelta

    from modules.database import get_connection

    months = []
    base = datetime(2026, 3, 1)
    for i in range(3):
        month = (base + timedelta(days=30 * i)).strftime("%Y%m")
        months.append(month)

    with get_connection() as conn:
        cursor = conn.cursor()
        # 确保表存在 (init_database 不创建 monthly_reviews_self，因为它是 tracking_tables.sql 的内容)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_reviews_self (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_month TEXT NOT NULL,
                ts_code TEXT NOT NULL,
                monthly_return REAL,
                max_drawdown REAL,
                buy_signals_count INTEGER,
                correct_buy_signals INTEGER,
                UNIQUE(ts_code, review_month)
            )
            """
        )
        for month in months:
            cursor.execute(
                """
                INSERT OR REPLACE INTO monthly_reviews_self
                (ts_code, review_month, monthly_return, max_drawdown,
                 buy_signals_count, correct_buy_signals)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("600000.SH", month, -30.0, 45.0, 5, 1),
            )
        conn.commit()
    yield months

"""
数据库管理模块
负责 SQLite 数据库的创建、连接和数据表操作
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class TradeRecord:
    """交易记录数据类"""
    ts_code: str
    trade_date: str
    action: str
    price: float
    quantity: int
    amount: float
    reason: str = ""
    signal_type: str = ""
    zg_review: str = ""
    broker: str = ""
    fee: float = 0
    tags: str = ""
    notes: str = ""


@dataclass
class StockInfo:
    """股票信息数据类"""
    ts_code: str
    name: str = ""
    area: str = ""
    industry: str = ""
    market: str = ""


from contextlib import contextmanager
from dotenv import load_dotenv

# 加载项目内的 .env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# 数据库路径：从环境变量读取，支持相对路径和绝对路径
_db_path_str = os.getenv("DB_PATH", "data/stock_data.db")
_db_path = Path(_db_path_str)
if not _db_path.is_absolute():
    _db_path = Path(__file__).parent.parent / _db_path_str
DB_PATH = _db_path.resolve()


def get_db_path() -> Path:
    """获取数据库路径"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_database():
    """初始化数据库，创建所有表"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. 核心K线数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_kline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                vol REAL,
                amount REAL,
                pct_chg REAL,
                vol_ratio REAL,
                is_limit_up INTEGER DEFAULT 0,
                is_limit_down INTEGER DEFAULT 0,
                UNIQUE(ts_code, trade_date)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_kline_code_date
            ON daily_kline(ts_code, trade_date DESC)
        """)

        # 2. 技术指标缓存表（每日快照）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicator_cache (
                -- 主键
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,

                -- 基础行情
                close REAL DEFAULT 0,
                open REAL DEFAULT 0,
                high REAL DEFAULT 0,
                low REAL DEFAULT 0,
                vol REAL DEFAULT 0,
                pct_chg REAL DEFAULT 0,

                -- KDJ
                k REAL DEFAULT 0,
                d REAL DEFAULT 0,
                j REAL DEFAULT 0,

                -- MACD
                dif REAL DEFAULT 0,
                dea REAL DEFAULT 0,
                macd_hist REAL DEFAULT 0,

                -- BBI
                bbi REAL DEFAULT 0,

                -- 均线
                ma5 REAL DEFAULT 0,
                ma10 REAL DEFAULT 0,
                ma20 REAL DEFAULT 0,
                ma60 REAL DEFAULT 0,

                -- RSI
                rsi6 REAL DEFAULT 0,
                rsi12 REAL DEFAULT 0,
                rsi24 REAL DEFAULT 0,

                -- WR
                wr5 REAL DEFAULT 0,
                wr10 REAL DEFAULT 0,

                -- 布林带
                boll_mid REAL DEFAULT 0,
                boll_upper REAL DEFAULT 0,
                boll_lower REAL DEFAULT 0,
                boll_width REAL DEFAULT 0,
                boll_position REAL DEFAULT 0,

                -- 量比
                vol_ratio REAL DEFAULT 1.0,

                -- 双线战法
                zg_white REAL DEFAULT 0,
                dg_yellow REAL DEFAULT 0,
                is_gold_cross INTEGER DEFAULT 0,
                is_dead_cross INTEGER DEFAULT 0,

                -- 单针下20
                rsl_short REAL DEFAULT 0,
                rsl_long REAL DEFAULT 0,
                is_needle_20 INTEGER DEFAULT 0,

                -- 砖型图
                brick_value REAL DEFAULT 0,
                brick_trend TEXT DEFAULT 'NEUTRAL',
                brick_count INTEGER DEFAULT 0,
                brick_trend_up INTEGER DEFAULT 0,
                is_fanbao INTEGER DEFAULT 0,

                -- 量价信号
                is_beidou INTEGER DEFAULT 0,
                is_suoliang INTEGER DEFAULT 0,
                is_jiayin_zhenyang INTEGER DEFAULT 0,
                is_jiayang_zhenyin INTEGER DEFAULT 0,
                is_fangliang_yinxian INTEGER DEFAULT 0,

                -- 防卖飞评分
                sell_score INTEGER DEFAULT 0,
                sell_reason TEXT DEFAULT '',

                -- 交易信号
                signal TEXT DEFAULT 'WATCH',
                signal_desc TEXT DEFAULT '',

                -- 关键价位
                prev_high REAL DEFAULT 0,
                prev_low REAL DEFAULT 0,

                -- DMI/ADX 趋势指标
                dmi_plus REAL DEFAULT 0,
                dmi_minus REAL DEFAULT 0,
                adx REAL DEFAULT 0,

                -- 资金流
                net_lg_mf REAL DEFAULT 0,
                net_elg_mf REAL DEFAULT 0,

                -- B1/B2战法记录
                last_b1_date TEXT,
                last_b1_price REAL DEFAULT 0,

                -- 异动记录
                last_yidong_date TEXT,

                -- 市场背景（每日收盘后更新）
                market_pct_chg REAL DEFAULT 0,
                market_dir TEXT DEFAULT 'NEUTRAL',

                -- 元数据
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                PRIMARY KEY (ts_code, trade_date)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ind_date
            ON indicator_cache(trade_date DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ind_signal
            ON indicator_cache(signal)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ind_brick
            ON indicator_cache(brick_trend, brick_count)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ind_yidong
            ON indicator_cache(last_yidong_date)
        """)

        # 3. 资金流向表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS moneyflow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                buy_sm_amount REAL,
                buy_md_amount REAL,
                buy_lg_amount REAL,
                buy_elg_amount REAL,
                sell_sm_amount REAL,
                sell_md_amount REAL,
                sell_lg_amount REAL,
                sell_elg_amount REAL,
                net_mf REAL,
                pct_mf REAL,
                UNIQUE(ts_code, trade_date)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mf_code_date
            ON moneyflow(ts_code, trade_date DESC)
        """)

        # 4. 财务数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financial_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                ann_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                report_type INTEGER,
                revenue REAL,
                net_profit REAL,
                total_assets REAL,
                total_liab REAL,
                equity REAL,
                pe REAL,
                pb REAL,
                ps REAL,
                UNIQUE(ts_code, ann_date)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fin_code_date
            ON financial_data(ts_code, end_date DESC)
        """)

        # 5. 股票基本信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_basic (
                ts_code TEXT PRIMARY KEY,
                name TEXT,
                area TEXT,
                industry TEXT,
                market TEXT,
                list_date TEXT,
                is_hs TEXT
            )
        """)

        # 6. 交易信号记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                signal_type TEXT,
                signal_score REAL,
                signal_price REAL,
                processed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_code_date
            ON trade_signals(ts_code, signal_date DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_type
            ON trade_signals(signal_type, signal_date DESC)
        """)

        # 7. 随堂测试/交易记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                amount REAL NOT NULL,
                reason TEXT,
                signal_type TEXT,
                zg_review TEXT,
                broker TEXT,
                fee REAL DEFAULT 0,
                tags TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trade_code_date
            ON trade_records(ts_code, trade_date DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trade_action
            ON trade_records(action, trade_date DESC)
        """)

        # 8. 数据更新日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_type TEXT NOT NULL,
                ts_code TEXT,
                last_date TEXT,
                status TEXT,
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        print(f"数据库初始化完成: {get_db_path()}")

        # 删除旧的indicators表（如果存在）
        cursor.execute("DROP TABLE IF EXISTS indicators")


# ============== 随堂测试/交易记录操作 ==============

def save_trade_record(record: Dict[str, Any]) -> int:
    """保存交易记录，返回记录ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trade_records (
                ts_code, trade_date, action, price, quantity, amount,
                reason, signal_type, zg_review, broker, fee, tags, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.get("ts_code"),
            record.get("trade_date"),
            record.get("action"),
            record.get("price"),
            record.get("quantity"),
            record.get("amount"),
            record.get("reason", ""),
            record.get("signal_type", ""),
            record.get("zg_review", ""),
            record.get("broker", ""),
            record.get("fee", 0),
            record.get("tags", ""),
            record.get("notes", "")
        ))
        return cursor.lastrowid


def get_trade_records(
    ts_code: str = None,
    start_date: str = None,
    end_date: str = None,
    action: str = None,
    limit: int = 100
) -> List[Dict]:
    """查询交易记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT * FROM trade_records WHERE 1=1"
        params = []

        if ts_code:
            sql += " AND ts_code = ?"
            params.append(ts_code)
        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date)
        if action:
            sql += " AND action = ?"
            params.append(action)

        sql += " ORDER BY trade_date DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def get_trade_record_by_id(trade_id: int) -> Optional[Dict]:
    """根据ID获取单条交易记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_records WHERE id = ?", (trade_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_trade_record(trade_id: int, updates: Dict[str, Any]) -> bool:
    """更新交易记录"""
    allowed_fields = {
        "reason", "signal_type", "zg_review", "broker", "fee", "tags", "notes"
    }
    updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not updates:
        return False

    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [trade_id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE trade_records SET {set_clause} WHERE id = ?",
            values
        )
        return cursor.rowcount > 0


def delete_trade_record(trade_id: int) -> bool:
    """删除交易记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trade_records WHERE id = ?", (trade_id,))
        return cursor.rowcount > 0


def get_trade_summary(ts_code: str = None, start_date: str = None, end_date: str = None) -> Dict:
    """获取交易汇总统计"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT action, COUNT(*) as count, SUM(amount) as total_amount FROM trade_records WHERE 1=1"
        params = []

        if ts_code:
            sql += " AND ts_code = ?"
            params.append(ts_code)
        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date)

        sql += " GROUP BY action"
        cursor.execute(sql, params)

        result = {"BUY": {}, "SELL": {}}
        for row in cursor.fetchall():
            result[row["action"]] = {
                "count": row["count"],
                "total_amount": row["total_amount"] or 0
            }
        return result


def drop_all_tables():
    """删除所有表（慎用，仅用于测试）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        tables = cursor.fetchall()
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table[0]}")
        print("所有表已删除")


if __name__ == "__main__":
    init_database()

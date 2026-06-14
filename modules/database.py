"""
数据库管理模块
负责 SQLite 数据库的创建、连接和数据表操作
"""

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional
from collections.abc import Generator
from dataclasses import dataclass
from contextlib import contextmanager


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


# 模块首次 import 时由 modules/__init__.py 统一加载 .env，
# 此处不再重复加载（保留仅为兼容独立脚本运行 `python modules/database.py`）

# 数据库路径：从环境变量读取，支持相对路径和绝对路径
_db_path_str = os.getenv("DB_PATH", "data/stock_data.db")
_db_path = Path(_db_path_str)
if not _db_path.is_absolute():
    _db_path = Path(__file__).parent.parent / _db_path_str
DB_PATH = _db_path.resolve()


def get_db_path() -> Path:
    """获取数据库路径（每次调用时动态读取 DB_PATH 环境变量）"""
    path_str = os.getenv("DB_PATH", "data/stock_data.db")
    path = Path(path_str)
    if not path.is_absolute():
        path = Path(__file__).parent.parent / path_str
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_db_connection() -> sqlite3.Connection:
    """获取数据库连接（动态读取 DB_PATH 环境变量）"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """获取数据库连接的上下文管理器"""
    conn = get_db_connection()
    # 开启 WAL 模式以提升并发和写入性能
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_tracking_tables(conn: sqlite3.Connection) -> None:
    """初始化自我改进系统跟踪表（4 张表 + 索引）

    表定义对应 modules/tracking_tables.sql，所有表名以 _self 结尾，
    与主系统表区分。
    """
    cursor = conn.cursor()

    # 1. 跟踪池表：管理跟踪的股票
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracking_pool_self (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            name TEXT,
            add_date TEXT NOT NULL,
            remove_date TEXT,
            status TEXT DEFAULT 'active',
            track_reason TEXT,
            strategy_tags TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(ts_code, add_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracking_pool_self_code
        ON tracking_pool_self(ts_code)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracking_pool_self_status
        ON tracking_pool_self(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracking_pool_self_add_date
        ON tracking_pool_self(add_date)
    """)

    # 2. 跟踪记录表：记录每日的行情、指标、信号
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracking_records_self (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            vol REAL,
            pct_chg REAL,
            amount REAL,
            j_value REAL,
            k_value REAL,
            d_value REAL,
            bbi REAL,
            macd_dif REAL,
            macd_dea REAL,
            macd_hist REAL,
            rsi_6 REAL,
            wr_6 REAL,
            boll_upper REAL,
            boll_mid REAL,
            boll_lower REAL,
            vol_ratio REAL,
            is_brick_red INTEGER DEFAULT 0,
            is_brick_green INTEGER DEFAULT 0,
            brick_count INTEGER DEFAULT 0,
            is_n_structure INTEGER DEFAULT 0,
            is_double_gun INTEGER DEFAULT 0,
            signal_type TEXT,
            signal_score REAL,
            signal_reason TEXT,
            stage TEXT,
            stage_confidence REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(ts_code, trade_date)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracking_records_self_code
        ON tracking_records_self(ts_code)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracking_records_self_date
        ON tracking_records_self(trade_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracking_records_self_signal
        ON tracking_records_self(signal_type)
    """)

    # 3. 月度复盘表：记录每月的复盘结果
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_reviews_self (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_month TEXT NOT NULL,
            ts_code TEXT NOT NULL,
            start_price REAL,
            start_j_value REAL,
            start_signal TEXT,
            end_price REAL,
            end_j_value REAL,
            end_signal TEXT,
            monthly_return REAL,
            max_drawdown REAL,
            max_gain REAL,
            buy_signals_count INTEGER,
            sell_signals_count INTEGER,
            correct_buy_signals INTEGER,
            correct_sell_signals INTEGER,
            review_summary TEXT,
            lessons_learned TEXT,
            strategy_adjustments TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(review_month, ts_code)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_monthly_reviews_self_month
        ON monthly_reviews_self(review_month)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_monthly_reviews_self_code
        ON monthly_reviews_self(ts_code)
    """)

    # 4. 策略表现统计表：统计各策略的表现
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategy_performance_self (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT NOT NULL,
            review_month TEXT NOT NULL,
            total_signals INTEGER,
            correct_signals INTEGER,
            accuracy_rate REAL,
            avg_return REAL,
            max_return REAL,
            min_return REAL,
            win_rate REAL,
            avg_drawdown REAL,
            max_drawdown REAL,
            sharpe_ratio REAL,
            strengths TEXT,
            weaknesses TEXT,
            adjustments TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(strategy_name, review_month)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategy_performance_self_name
        ON strategy_performance_self(strategy_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategy_performance_self_month
        ON strategy_performance_self(review_month)
    """)


def init_database() -> None:
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

        # 9. 自选股观察池表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL UNIQUE,
                name TEXT,
                tags TEXT DEFAULT '',
                added_date TEXT DEFAULT CURRENT_TIMESTAMP,
                alert_enabled INTEGER DEFAULT 1,
                notes TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_tags
            ON watchlist(tags)
        """)

        # 10. Tushare 官方指标缓存表（用于和我们自己算的指标做 diff 验证）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tushare_indicator_cache (
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL DEFAULT 0,
                macd_dif REAL DEFAULT 0,
                macd_dea REAL DEFAULT 0,
                macd REAL DEFAULT 0,
                kdj_k REAL DEFAULT 0,
                kdj_d REAL DEFAULT 0,
                kdj_j REAL DEFAULT 0,
                rsi_6 REAL DEFAULT 0,
                rsi_12 REAL DEFAULT 0,
                rsi_24 REAL DEFAULT 0,
                boll_upper REAL DEFAULT 0,
                boll_mid REAL DEFAULT 0,
                boll_lower REAL DEFAULT 0,
                cci REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ts_code, trade_date)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tushare_ind_date
            ON tushare_indicator_cache(ts_code, trade_date DESC)
        """)

        # 11. LLM 响应耗时日志表
        # 记录每次 LLM 调用的响应时间、股票代码、日期、模型、是否成功
        # 用于监控 LLM 服务的性能与可用性
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_response_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,           -- 股票代码（如 600519.SH）
                request_date TEXT NOT NULL,      -- 请求日期 yyyy-mm-dd
                model TEXT NOT NULL,             -- 调用的 LLM 模型名
                response_time_ms REAL NOT NULL,  -- 响应耗时（毫秒）
                success INTEGER DEFAULT 1,       -- 1=成功，0=失败
                error_message TEXT,              -- 失败时的错误信息
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_log_code_date
            ON llm_response_log(ts_code, request_date DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_log_date
            ON llm_response_log(request_date DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_log_model
            ON llm_response_log(model, request_date DESC)
        """)

        # 12. 自我改进系统跟踪表（tracking_tables.sql）
        init_tracking_tables(conn)

        print(f"数据库初始化完成: {get_db_path()}")

        # 删除旧的indicators表（如果存在）
        cursor.execute("DROP TABLE IF EXISTS indicators")


# ============== 自选股观察池操作 ==============


def add_watchlist_item(ts_code: str, name: str = "", tags: str = "", notes: str = "") -> int:
    """添加自选股，返回ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO watchlist (ts_code, name, tags, notes)
            VALUES (?, ?, ?, ?)
        """,
            (ts_code, name, tags, notes),
        )
        return cursor.lastrowid if cursor.lastrowid is not None else 0


def remove_watchlist_item(ts_code: str) -> bool:
    """移除自选股"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE ts_code = ?", (ts_code,))
        return cursor.rowcount > 0


def get_watchlist(tags: str | None = None) -> list[dict]:
    """获取自选股列表"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT * FROM watchlist ORDER BY added_date DESC"
        params: tuple[str, ...] = ()
        if tags:
            sql = "SELECT * FROM watchlist WHERE tags LIKE ? ORDER BY added_date DESC"
            params = (f"%{tags}%",)
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def update_watchlist_item(ts_code: str, updates: dict[str, Any]) -> bool:
    """更新自选股信息"""
    allowed = {"name", "tags", "alert_enabled", "notes"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [ts_code]
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE watchlist SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE ts_code = ?", values)
        return cursor.rowcount > 0


# ============== 随堂测试/交易记录操作 ==============


def save_trade_record(record: dict[str, Any]) -> int:
    """保存交易记录，返回记录ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trade_records (
                ts_code, trade_date, action, price, quantity, amount,
                reason, signal_type, zg_review, broker, fee, tags, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
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
                record.get("notes", ""),
            ),
        )
        return cursor.lastrowid if cursor.lastrowid is not None else 0


def get_trade_records(
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """查询交易记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT * FROM trade_records WHERE 1=1"
        params: list[Any] = []

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


def get_trade_record_by_id(trade_id: int) -> dict | None:
    """根据ID获取单条交易记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_records WHERE id = ?", (trade_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_trade_record(trade_id: int, updates: dict[str, Any]) -> bool:
    """更新交易记录"""
    allowed_fields = {"reason", "signal_type", "zg_review", "broker", "fee", "tags", "notes"}
    updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not updates:
        return False

    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [trade_id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE trade_records SET {set_clause} WHERE id = ?", values)
        return cursor.rowcount > 0


def delete_trade_record(trade_id: int) -> bool:
    """删除交易记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trade_records WHERE id = ?", (trade_id,))
        return cursor.rowcount > 0


def get_trade_summary(ts_code: str | None = None, start_date: str | None = None, end_date: str | None = None) -> dict:
    """获取交易汇总统计"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT action, COUNT(*) as count, SUM(amount) as total_amount FROM trade_records WHERE 1=1"
        params: list[Any] = []

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

        result: dict[str, dict[str, Any]] = {"BUY": {}, "SELL": {}}
        for row in cursor.fetchall():
            result[row["action"]] = {"count": row["count"], "total_amount": row["total_amount"] or 0}
        return result


def drop_all_tables() -> None:
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


# ============== LLM 响应耗时日志 ==============


def record_llm_response(
    ts_code: str,
    model: str,
    response_time_ms: float,
    success: bool = True,
    error_message: str = "",
    request_date: str | None = None,
) -> int:
    """记录 LLM 调用响应时间。

    Args:
        ts_code: 股票代码（如 600519.SH）
        model: 调用的 LLM 模型名
        response_time_ms: 响应耗时（毫秒）
        success: 是否调用成功
        error_message: 失败时的错误信息（成功时可为空）
        request_date: 请求日期 yyyy-mm-dd；默认使用当天日期

    Returns:
        插入的记录 ID
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if request_date is None:
            cursor.execute("SELECT date('now', 'localtime')")
            request_date = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO llm_response_log (
                ts_code, request_date, model,
                response_time_ms, success, error_message
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ts_code,
                request_date,
                model,
                float(response_time_ms),
                1 if success else 0,
                error_message or "",
            ),
        )
        return cursor.lastrowid if cursor.lastrowid is not None else 0


def get_llm_response_log(
    ts_code: str | None = None,
    request_date: str | None = None,
    model: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """查询 LLM 响应日志。

    Args:
        ts_code: 按股票代码过滤
        request_date: 按请求日期过滤
        model: 按模型过滤
        limit: 返回记录数上限

    Returns:
        日志记录列表，按 created_at 倒序
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT * FROM llm_response_log WHERE 1=1"
        params: list[Any] = []

        if ts_code:
            sql += " AND ts_code = ?"
            params.append(ts_code)
        if request_date:
            sql += " AND request_date = ?"
            params.append(request_date)
        if model:
            sql += " AND model = ?"
            params.append(model)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def get_llm_response_stats(request_date: str | None = None) -> dict:
    """按日聚合 LLM 响应统计：调用次数、成功率、平均/最大耗时。

    Args:
        request_date: 按请求日期过滤（默认当天）

    Returns:
        {
          "request_date": "...",
          "total_calls": N,
          "success_calls": N,
          "failed_calls": N,
          "avg_ms": ...,
          "max_ms": ...,
          "min_ms": ...,
        }
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if request_date is None:
            cursor.execute("SELECT date('now', 'localtime')")
            request_date = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(success), 0) AS success_calls,
                COALESCE(AVG(response_time_ms), 0) AS avg_ms,
                COALESCE(MAX(response_time_ms), 0) AS max_ms,
                COALESCE(MIN(response_time_ms), 0) AS min_ms
            FROM llm_response_log
            WHERE request_date = ?
            """,
            (request_date,),
        )
        row = cursor.fetchone()
        total = int(row["total_calls"] or 0)
        success = int(row["success_calls"] or 0)
        return {
            "request_date": request_date,
            "total_calls": total,
            "success_calls": success,
            "failed_calls": total - success,
            "avg_ms": float(row["avg_ms"] or 0),
            "max_ms": float(row["max_ms"] or 0),
            "min_ms": float(row["min_ms"] or 0),
        }


if __name__ == "__main__":
    init_database()

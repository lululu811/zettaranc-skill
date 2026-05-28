"""
db_test 数据库同步脚本
创建完整的大A全量数据库，包含股票基本信息、日线K线和技术指标

使用方法:
    python scripts/sync_db_test.py          # 交互式选择
    python scripts/sync_db_test.py init     # 仅初始化数据库
    python scripts/sync_db_test.py full     # 全量同步（股票+K线+指标）
    python scripts/sync_db_test.py stocks    # 仅同步股票信息
    python scripts/sync_db_test.py kline    # 仅同步K线数据
    python scripts/sync_db_test.py indic    # 仅计算技术指标
    python scripts/sync_db_test.py status   # 查看状态
"""

import os
import sys
import time
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import List, Optional, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import tushare as ts
    from dotenv import load_dotenv
except ImportError as e:
    print(f"请先安装依赖: pip install tushare python-dotenv")
    sys.exit(1)

# 加载环境变量
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# ==================== 配置 ====================

DB_TEST_PATH = "data/db_test.db"
TUSHARE_API_URL = "http://tsy.xiaodefa.cn"
VERIFY_TOKEN_URL = "http://tsy.xiaodefa.cn/dataapi/sdk-event"

# 限流控制：120次/分钟
MIN_INTERVAL = 60 / 120

# ==================== 日志配置 ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/sync_db_test.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ==================== 数据库管理 ====================

@contextmanager
def get_connection(db_path: str = DB_TEST_PATH):
    """获取数据库连接"""
    if not os.path.isabs(db_path):
        db_path = str(Path(__file__).parent.parent / db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_db_test():
    """初始化 db_test 数据库"""
    db_path = Path(__file__).parent.parent / DB_TEST_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果已存在，先删除（用于全新初始化）
    if db_path.exists():
        logger.warning(f"数据库已存在: {db_path}")
        response = input("是否删除重建? (y/N): ")
        if response.lower() != 'y':
            logger.info("取消初始化")
            return False
        db_path.unlink()
        logger.info("已删除旧数据库")

    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. 核心K线数据表
        cursor.execute("""
            CREATE TABLE daily_kline (
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
            CREATE INDEX idx_kline_code_date
            ON daily_kline(ts_code, trade_date DESC)
        """)

        # 2. 技术指标缓存表
        cursor.execute("""
            CREATE TABLE indicator_cache (
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL DEFAULT 0,
                open REAL DEFAULT 0,
                high REAL DEFAULT 0,
                low REAL DEFAULT 0,
                vol REAL DEFAULT 0,
                pct_chg REAL DEFAULT 0,
                k REAL DEFAULT 0,
                d REAL DEFAULT 0,
                j REAL DEFAULT 0,
                dif REAL DEFAULT 0,
                dea REAL DEFAULT 0,
                macd_hist REAL DEFAULT 0,
                bbi REAL DEFAULT 0,
                ma5 REAL DEFAULT 0,
                ma10 REAL DEFAULT 0,
                ma20 REAL DEFAULT 0,
                ma60 REAL DEFAULT 0,
                rsi6 REAL DEFAULT 0,
                rsi12 REAL DEFAULT 0,
                rsi24 REAL DEFAULT 0,
                wr5 REAL DEFAULT 0,
                wr10 REAL DEFAULT 0,
                boll_mid REAL DEFAULT 0,
                boll_upper REAL DEFAULT 0,
                boll_lower REAL DEFAULT 0,
                boll_width REAL DEFAULT 0,
                boll_position REAL DEFAULT 0,
                vol_ratio REAL DEFAULT 1.0,
                zg_white REAL DEFAULT 0,
                dg_yellow REAL DEFAULT 0,
                is_gold_cross INTEGER DEFAULT 0,
                is_dead_cross INTEGER DEFAULT 0,
                rsl_short REAL DEFAULT 0,
                rsl_long REAL DEFAULT 0,
                is_needle_20 INTEGER DEFAULT 0,
                brick_value REAL DEFAULT 0,
                brick_trend TEXT DEFAULT 'NEUTRAL',
                brick_count INTEGER DEFAULT 0,
                brick_trend_up INTEGER DEFAULT 0,
                is_fanbao INTEGER DEFAULT 0,
                is_beidou INTEGER DEFAULT 0,
                is_suoliang INTEGER DEFAULT 0,
                is_jiayin_zhenyang INTEGER DEFAULT 0,
                is_jiayang_zhenyin INTEGER DEFAULT 0,
                is_fangliang_yinxian INTEGER DEFAULT 0,
                sell_score INTEGER DEFAULT 0,
                sell_reason TEXT DEFAULT '',
                signal TEXT DEFAULT 'WATCH',
                signal_desc TEXT DEFAULT '',
                prev_high REAL DEFAULT 0,
                prev_low REAL DEFAULT 0,
                dmi_plus REAL DEFAULT 0,
                dmi_minus REAL DEFAULT 0,
                adx REAL DEFAULT 0,
                net_lg_mf REAL DEFAULT 0,
                net_elg_mf REAL DEFAULT 0,
                last_b1_date TEXT,
                last_b1_price REAL DEFAULT 0,
                last_yidong_date TEXT,
                market_pct_chg REAL DEFAULT 0,
                market_dir TEXT DEFAULT 'NEUTRAL',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ts_code, trade_date)
            )
        """)
        cursor.execute("CREATE INDEX idx_ind_date ON indicator_cache(trade_date DESC)")
        cursor.execute("CREATE INDEX idx_ind_signal ON indicator_cache(signal)")
        cursor.execute("CREATE INDEX idx_ind_brick ON indicator_cache(brick_trend, brick_count)")

        # 3. 资金流向表
        cursor.execute("""
            CREATE TABLE moneyflow (
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
        cursor.execute("CREATE INDEX idx_mf_code_date ON moneyflow(ts_code, trade_date DESC)")

        # 4. 财务数据表
        cursor.execute("""
            CREATE TABLE financial_data (
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
        cursor.execute("CREATE INDEX idx_fin_code_date ON financial_data(ts_code, end_date DESC)")

        # 5. 股票基本信息表
        cursor.execute("""
            CREATE TABLE stock_basic (
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
            CREATE TABLE trade_signals (
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
        cursor.execute("CREATE INDEX idx_signal_code_date ON trade_signals(ts_code, signal_date DESC)")

        # 7. 数据更新日志表
        cursor.execute("""
            CREATE TABLE sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_type TEXT NOT NULL,
                ts_code TEXT,
                last_date TEXT,
                status TEXT,
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    logger.info(f"db_test 数据库初始化完成: {db_path}")
    return True


# ==================== Tushare 客户端 ====================

class TushareSyncer:
    """数据同步器"""

    def __init__(self, db_path: str = DB_TEST_PATH):
        self.token = os.environ.get("TUSHARE_TOKEN")
        if not self.token:
            raise ValueError("未设置 TUSHARE_TOKEN")

        ts.set_token(self.token)
        self.pro = ts.pro_api()
        self.pro._DataApi__http_url = TUSHARE_API_URL

        from tushare.stock import cons as ct
        ct.verify_token_url = VERIFY_TOKEN_URL

        self.db_path = db_path
        self.last_request_time = {}

    def _rate_limit(self, api_name: str):
        """限流控制"""
        now = time.time()
        last = self.last_request_time.get(api_name, 0)
        elapsed = now - last
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        self.last_request_time[api_name] = time.time()

    def _log_sync(self, data_type: str, ts_code: Optional[str], last_date: str,
                  status: str, message: str = ""):
        """记录同步日志"""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_log (data_type, ts_code, last_date, status, message)
                VALUES (?, ?, ?, ?, ?)
            """, (data_type, ts_code, last_date, status, message))

    def _get_last_date(self, data_type: str, ts_code: Optional[str] = None) -> Optional[str]:
        """获取最后同步日期"""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            if ts_code:
                cursor.execute("""
                    SELECT last_date FROM sync_log
                    WHERE data_type = ? AND ts_code = ? AND status = 'success'
                    ORDER BY created_at DESC LIMIT 1
                """, (data_type, ts_code))
            else:
                cursor.execute("""
                    SELECT last_date FROM sync_log
                    WHERE data_type = ? AND ts_code IS NULL AND status = 'success'
                    ORDER BY created_at DESC LIMIT 1
                """, (data_type,))
            result = cursor.fetchone()
            return result['last_date'] if result else None

    # ==================== 同步方法 ====================

    def sync_stock_basic(self) -> int:
        """同步股票基本信息"""
        logger.info("开始同步股票基本信息...")
        try:
            self._rate_limit("stock_basic")
            df = self.pro.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,name,area,industry,market,list_date,is_hs'
            )

            if df is None or len(df) == 0:
                logger.warning("获取股票基本信息失败")
                return 0

            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                for _, row in df.iterrows():
                    cursor.execute("""
                        INSERT OR REPLACE INTO stock_basic
                        (ts_code, name, area, industry, market, list_date, is_hs)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row['ts_code'], row['name'], row.get('area'),
                        row.get('industry'), row.get('market'),
                        row.get('list_date'), row.get('is_hs')
                    ))

            self._log_sync("stock_basic", None, datetime.now().strftime("%Y%m%d"), "success")
            logger.info(f"股票基本信息同步完成，共 {len(df)} 只")
            return len(df)

        except Exception as e:
            logger.error(f"股票基本信息同步失败: {e}")
            self._log_sync("stock_basic", None, "", "failed", str(e))
            return 0

    def sync_daily_kline(self, ts_code: str, start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> int:
        """同步单只股票的日线数据"""
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        try:
            self._rate_limit("daily_kline")
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is None or len(df) == 0:
                return 0

            df['is_limit_up'] = df['pct_chg'].apply(lambda x: 1 if x >= 9.9 else 0)
            df['is_limit_down'] = df['pct_chg'].apply(lambda x: 1 if x <= -9.9 else 0)

            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                for _, row in df.iterrows():
                    cursor.execute("""
                        INSERT OR REPLACE INTO daily_kline
                        (ts_code, trade_date, open, high, low, close, vol, amount,
                         pct_chg, vol_ratio, is_limit_up, is_limit_down)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row['ts_code'], row['trade_date'],
                        row['open'], row['high'], row['low'], row['close'],
                        row['vol'], row['amount'], row['pct_chg'],
                        None, row.get('is_limit_up', 0), row.get('is_limit_down', 0)
                    ))

            latest_date = df['trade_date'].max()
            self._log_sync("daily_kline", ts_code, latest_date, "success")
            return len(df)

        except Exception as e:
            logger.error(f"日线数据同步失败 {ts_code}: {e}")
            self._log_sync("daily_kline", ts_code, "", "failed", str(e))
            return 0

    def sync_all_daily_kline(self, ts_codes: Optional[List[str]] = None,
                              days: int = 730) -> Dict[str, int]:
        """批量同步多只股票的日线数据"""
        results = {}

        if ts_codes is None:
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ts_code FROM stock_basic")
                ts_codes = [row['ts_code'] for row in cursor.fetchall()]

        logger.info(f"开始批量同步日线数据，共 {len(ts_codes)} 只股票...")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        success_count = 0
        for i, ts_code in enumerate(ts_codes):
            try:
                count = self.sync_daily_kline(ts_code, start_date, end_date)
                results[ts_code] = count
                if count > 0:
                    success_count += 1

                if (i + 1) % 50 == 0:
                    logger.info(f"进度: {i + 1}/{len(ts_codes)}, 成功: {success_count}")

            except Exception as e:
                logger.error(f"同步失败 {ts_code}: {e}")
                results[ts_code] = 0

        logger.info(f"批量同步完成，成功 {success_count}/{len(ts_codes)}")
        return results

    def sync_indicator_cache(self, ts_code: str, days: int = 120) -> int:
        """同步单只股票的技术指标到 indicator_cache 表"""
        try:
            # 导入指标计算模块
            try:
                from modules.indicators import (
                    get_kline_data, calculate_kdj, calculate_macd,
                    calculate_bbi, calculate_ma, calculate_rsi_multi, calculate_wr_multi,
                    calculate_bollinger, calculate_vol_ratio, calculate_zg_white,
                    calculate_dg_yellow, detect_double_line_cross, detect_needle_20,
                    calculate_brick_value, calculate_brick_history, detect_brick_trend,
                    detect_fanbao, detect_volume_pattern, calculate_sell_score,
                    detect_trade_signal, calculate_dmi
                )
            except ImportError:
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from modules.indicators import (
                    get_kline_data, calculate_kdj, calculate_macd,
                    calculate_bbi, calculate_ma, calculate_rsi_multi, calculate_wr_multi,
                    calculate_bollinger, calculate_vol_ratio, calculate_zg_white,
                    calculate_dg_yellow, detect_double_line_cross, detect_needle_20,
                    calculate_brick_value, calculate_brick_history, detect_brick_trend,
                    detect_fanbao, detect_volume_pattern, calculate_sell_score,
                    detect_trade_signal, calculate_dmi
                )

            # 获取K线数据
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
                    FROM daily_kline
                    WHERE ts_code = ?
                    ORDER BY trade_date DESC
                    LIMIT ?
                """, (ts_code, days))

                rows = cursor.fetchall()
                if not rows:
                    return 0

                # 转换为数据结构
                klines = []
                for row in rows:
                    klines.append(type('Kline', (), {
                        'ts_code': row['ts_code'],
                        'trade_date': row['trade_date'],
                        'open': row['open'],
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                        'vol': row['vol'],
                        'amount': row['amount'],
                        'pct_chg': row['pct_chg'],
                        'prev_close': row['close']  # 简化处理
                    })())

                klines.reverse()  # 按时间正序

            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()

                for i, kline in enumerate(klines):
                    sub_klines = klines[:i+1]
                    today = kline
                    yesterday = sub_klines[-2] if len(sub_klines) > 1 else None

                    # 计算各项指标
                    k, d, j = calculate_kdj(sub_klines) if len(sub_klines) >= 9 else (50, 50, 50)
                    macd_result = calculate_macd(sub_klines) if len(sub_klines) >= 30 else ([], [], [])
                    dif = macd_result[0][-1] if macd_result[0] else 0
                    dea = macd_result[1][-1] if macd_result[1] else 0
                    macd_hist = macd_result[2][-1] if macd_result[2] else 0
                    bbi = calculate_bbi(sub_klines) if len(sub_klines) >= 24 else 0

                    closes = [k.close for k in sub_klines]
                    ma5 = calculate_ma(closes, 5) if len(closes) >= 5 else 0
                    ma10 = calculate_ma(closes, 10) if len(closes) >= 10 else 0
                    ma20 = calculate_ma(closes, 20) if len(closes) >= 20 else 0
                    ma60 = calculate_ma(closes, 60) if len(closes) >= 60 else 0

                    rsi6, rsi12, rsi24 = calculate_rsi_multi(sub_klines) if len(sub_klines) >= 25 else (50, 50, 50)
                    wr5, wr10 = calculate_wr_multi(sub_klines) if len(sub_klines) >= 10 else (-50, -50)

                    boll_mid, boll_upper, boll_lower, boll_width, boll_pos = calculate_bollinger(sub_klines) if len(sub_klines) >= 20 else (0, 0, 0, 0, 50)

                    vol_ratio = calculate_vol_ratio(sub_klines)

                    zg_white = calculate_zg_white(sub_klines) if len(sub_klines) >= 115 else 0
                    dg_yellow = calculate_dg_yellow(sub_klines) if len(sub_klines) >= 115 else 0
                    gold_cross, dead_cross = detect_double_line_cross(sub_klines) if len(sub_klines) >= 115 else (False, False)

                    rsl_short, rsl_long, is_needle = detect_needle_20(sub_klines) if len(sub_klines) >= 22 else (50, 50, False)

                    brick_value = calculate_brick_value(sub_klines) if len(sub_klines) >= 8 else 0
                    brick_trend, brick_count = calculate_brick_history(sub_klines) if len(sub_klines) >= 10 else ("NEUTRAL", 0)
                    brick_trend_up = detect_brick_trend(sub_klines) if len(sub_klines) >= 115 else False
                    is_fanbao = detect_fanbao(sub_klines) if len(sub_klines) >= 4 else False

                    vol_pattern = detect_volume_pattern(today, yesterday) if yesterday else {}
                    sell_result = calculate_sell_score(sub_klines) if len(sub_klines) >= 5 else (3, {})
                    sell_score = sell_result[0]
                    sell_items = sell_result[1] if isinstance(sell_result[1], dict) else {}
                    sell_reason = ','.join([k for k, v in sell_items.items() if not v]) if sell_items else '数据不足'
                    signal = detect_trade_signal(sub_klines) if len(sub_klines) >= 30 else "WATCH"
                    signal_desc = signal.value if hasattr(signal, 'value') else str(signal)

                    dmi_plus, dmi_minus, adx = calculate_dmi(sub_klines) if len(sub_klines) >= 30 else (0, 0, 0)

                    prev_high = sub_klines[-2].high if len(sub_klines) > 1 else 0
                    prev_low = sub_klines[-2].low if len(sub_klines) > 1 else 0

                    cursor.execute("""
                    vol_pattern_ints = {
                        'is_beidou': int(vol_pattern.get('is_beidou', 0)),
                        'is_suoliang': int(vol_pattern.get('is_suoliang', 0)),
                        'is_jiayin_zhenyang': int(vol_pattern.get('is_jiayin_zhenyang', 0)),
                        'is_jiayang_zhenyin': int(vol_pattern.get('is_jiayang_zhenyin', 0)),
                        'is_fangliang_yinxian': int(vol_pattern.get('is_fangliang_yinxian', 0)),
                    }

                    # 整理所有指标值 - 与表列一一对应
                    row_values = [
                        ts_code, today.trade_date,
                        today.close, today.open, today.high, today.low, today.vol, today.pct_chg,
                        k, d, j,
                        dif, dea, macd_hist,
                        bbi,
                        ma5, ma10, ma20, ma60,
                        rsi6, rsi12, rsi24,
                        wr5, wr10,
                        boll_mid, boll_upper, boll_lower, boll_width, boll_pos,
                        vol_ratio,
                        zg_white, dg_yellow,
                        int(gold_cross), int(dead_cross),
                        rsl_short, rsl_long, int(is_needle),
                        brick_value, brick_trend, brick_count, int(brick_trend_up), int(is_fanbao),
                        vol_pattern_ints['is_beidou'], vol_pattern_ints['is_suoliang'],
                        vol_pattern_ints['is_jiayin_zhenyang'], vol_pattern_ints['is_jiayang_zhenyin'],
                        vol_pattern_ints['is_fangliang_yinxian'],
                        sell_score, sell_reason,
                        signal_desc, signal_desc,
                        prev_high, prev_low,
                        dmi_plus, dmi_minus, adx,
                        0, 0, None, 0,
                        None, 0, 'NEUTRAL',
                        None
                    ]

                    columns = [
                        'ts_code', 'trade_date',
                        'close', 'open', 'high', 'low', 'vol', 'pct_chg',
                        'k', 'd', 'j',
                        'dif', 'dea', 'macd_hist',
                        'bbi',
                        'ma5', 'ma10', 'ma20', 'ma60',
                        'rsi6', 'rsi12', 'rsi24',
                        'wr5', 'wr10',
                        'boll_mid', 'boll_upper', 'boll_lower', 'boll_width', 'boll_position',
                        'vol_ratio',
                        'zg_white', 'dg_yellow',
                        'is_gold_cross', 'is_dead_cross',
                        'rsl_short', 'rsl_long', 'is_needle_20',
                        'brick_value', 'brick_trend', 'brick_count', 'brick_trend_up', 'is_fanbao',
                        'is_beidou', 'is_suoliang', 'is_jiayin_zhenyang', 'is_jiayang_zhenyin', 'is_fangliang_yinxian',
                        'sell_score', 'sell_reason',
                        'signal', 'signal_desc',
                        'prev_high', 'prev_low',
                        'dmi_plus', 'dmi_minus', 'adx',
                        'net_lg_mf', 'net_elg_mf', 'last_b1_date', 'last_b1_price',
                        'last_yidong_date', 'market_pct_chg', 'market_dir',
                        'updated_at'
                    ]

                    placeholders = ', '.join(['?'] * len(row_values))
                    col_names = ', '.join(columns)

                    cursor.execute(f"""
                        INSERT OR REPLACE INTO indicator_cache
                        ({col_names})
                        VALUES ({placeholders})
                    """, row_values)


            self._log_sync("indicator_cache", ts_code, klines[-1].trade_date, "success")
            return len(klines)

        except Exception as e:
            logger.error(f"指标缓存同步失败 {ts_code}: {e}")
            self._log_sync("indicator_cache", ts_code, "", "failed", str(e))
            return 0

    def sync_all_indicators(self, ts_codes: Optional[List[str]] = None) -> Dict[str, int]:
        """批量同步所有股票的指标缓存"""
        results = {}

        if ts_codes is None:
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT ts_code FROM daily_kline")
                ts_codes = [row['ts_code'] for row in cursor.fetchall()]

        logger.info(f"开始批量同步指标缓存，共 {len(ts_codes)} 只股票...")

        success_count = 0
        for i, ts_code in enumerate(ts_codes):
            try:
                count = self.sync_indicator_cache(ts_code)
                results[ts_code] = count
                if count > 0:
                    success_count += 1

                if (i + 1) % 50 == 0:
                    logger.info(f"指标进度: {i + 1}/{len(ts_codes)}, 成功: {success_count}")

            except Exception as e:
                logger.error(f"指标同步失败 {ts_code}: {e}")
                results[ts_code] = 0

        logger.info(f"批量指标同步完成，成功 {success_count}/{len(ts_codes)}")
        return results

    def get_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as cnt FROM stock_basic")
            stock_count = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(*) as cnt FROM daily_kline")
            kline_count = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(*) as cnt FROM indicator_cache")
            ind_count = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(DISTINCT ts_code) as cnt FROM daily_kline")
            kline_stock = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(DISTINCT ts_code) as cnt FROM indicator_cache")
            ind_stock = cursor.fetchone()['cnt']

            db_path = Path(self.db_path)
            if not db_path.is_absolute():
                db_path = Path(__file__).parent.parent / self.db_path
            db_size = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0

            return {
                "stock_count": stock_count,
                "kline_count": kline_count,
                "kline_stock": kline_stock,
                "ind_count": ind_count,
                "ind_stock": ind_stock,
                "db_path": str(db_path.resolve()),
                "db_size_mb": round(db_size, 2)
            }


# ==================== 主程序 ====================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="db_test 数据库同步工具")
    parser.add_argument("action", choices=["init", "full", "stocks", "kline", "indic", "status"],
                        help="操作类型")
    parser.add_argument("--days", type=int, default=730, help="K线同步天数")
    parser.add_argument("--limit", type=int, default=0, help="限制股票数量(用于测试)")
    args = parser.parse_args()

    # 确保日志目录存在
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if args.action == "init":
        init_db_test()

    elif args.action == "full":
        logger.info("=" * 60)
        logger.info("开始全量同步: 股票信息 -> K线 -> 技术指标")
        logger.info("=" * 60)

        syncer = TushareSyncer()

        # Step 1: 同步股票基本信息
        logger.info("\n[Step 1/3] 同步股票基本信息...")
        count = syncer.sync_stock_basic()
        logger.info(f"股票基本信息: {count} 只")

        # Step 2: 同步K线数据
        logger.info("\n[Step 2/3] 同步日线K线数据...")
        if args.limit > 0:
            with get_connection(DB_TEST_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT ts_code FROM stock_basic LIMIT {args.limit}")
                ts_codes = [row['ts_code'] for row in cursor.fetchall()]
            logger.info(f"测试模式: 仅同步 {len(ts_codes)} 只股票")
        else:
            ts_codes = None
        syncer.sync_all_daily_kline(ts_codes, days=args.days)

        # Step 3: 计算技术指标
        logger.info("\n[Step 3/3] 计算技术指标...")
        syncer.sync_all_indicators(ts_codes)

        # 输出状态
        logger.info("\n" + "=" * 60)
        logger.info("全量同步完成!")
        logger.info("=" * 60)
        status = syncer.get_status()
        logger.info(f"数据库: {status['db_path']}")
        logger.info(f"数据库大小: {status['db_size_mb']} MB")
        logger.info(f"股票数量: {status['stock_count']}")
        logger.info(f"K线数据: {status['kline_count']} 条 ({status['kline_stock']} 只)")
        logger.info(f"指标缓存: {status['ind_count']} 条 ({status['ind_stock']} 只)")

    elif args.action == "stocks":
        syncer = TushareSyncer()
        count = syncer.sync_stock_basic()
        print(f"股票基本信息同步完成: {count} 只")

    elif args.action == "kline":
        syncer = TushareSyncer()
        ts_codes = None
        if args.limit > 0:
            with get_connection(DB_TEST_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT ts_code FROM stock_basic LIMIT {args.limit}")
                ts_codes = [row['ts_code'] for row in cursor.fetchall()]
        syncer.sync_all_daily_kline(ts_codes, days=args.days)
        status = syncer.get_status()
        print(f"K线同步完成: {status['kline_count']} 条 ({status['kline_stock']} 只)")

    elif args.action == "indic":
        syncer = TushareSyncer()
        ts_codes = None
        if args.limit > 0:
            with get_connection(DB_TEST_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT DISTINCT ts_code FROM daily_kline LIMIT {args.limit}")
                ts_codes = [row['ts_code'] for row in cursor.fetchall()]
        syncer.sync_all_indicators(ts_codes)
        status = syncer.get_status()
        print(f"指标计算完成: {status['ind_count']} 条 ({status['ind_stock']} 只)")

    elif args.action == "status":
        syncer = TushareSyncer()
        status = syncer.get_status()
        print("=" * 50)
        print(f"数据库: {status['db_path']}")
        print(f"数据库大小: {status['db_size_mb']} MB")
        print(f"股票数量: {status['stock_count']}")
        print(f"K线数据: {status['kline_count']} 条 ({status['kline_stock']} 只)")
        print(f"指标缓存: {status['ind_count']} 条 ({status['ind_stock']} 只)")


if __name__ == "__main__":
    main()

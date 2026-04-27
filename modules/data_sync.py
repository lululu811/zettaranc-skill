"""
数据同步模块
从 Tushare API 获取数据并存储到 SQLite
支持增量更新和全量更新
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

try:
    import tushare as ts
    from dotenv import load_dotenv
except ImportError:
    print("请先安装依赖: pip install tushare python-dotenv")

# 加载项目内的 .env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

try:
    from .database import get_connection, get_db_path
    from .tushare_client import TushareClient
except ImportError:
    from database import get_connection, get_db_path
    from tushare_client import TushareClient

logger = logging.getLogger(__name__)

# 中转 API 配置
TUSHARE_API_URL = "http://tsy.xiaodefa.cn"
VERIFY_TOKEN_URL = "http://tsy.xiaodefa.cn/dataapi/sdk-event"


class DataSyncer:
    """数据同步器"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("TUSHARE_TOKEN")
        if not self.token:
            raise ValueError("未设置 TUSHARE_TOKEN")

        # 初始化 Tushare
        ts.set_token(self.token)
        self.pro = ts.pro_api()
        self.pro._DataApi__http_url = TUSHARE_API_URL

        # 限流控制：120次/分钟
        self.min_interval = 60 / 120
        self.last_request_time = {}

    def _rate_limit(self, api_name: str):
        """限流控制"""
        now = time.time()
        last = self.last_request_time.get(api_name, 0)
        elapsed = now - last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time[api_name] = time.time()

    def _log_sync(self, data_type: str, ts_code: Optional[str], last_date: str,
                  status: str, message: str = ""):
        """记录同步日志"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_log (data_type, ts_code, last_date, status, message)
                VALUES (?, ?, ?, ?, ?)
            """, (data_type, ts_code, last_date, status, message))

    def _get_last_date(self, data_type: str, ts_code: Optional[str] = None) -> Optional[str]:
        """获取最后同步日期"""
        with get_connection() as conn:
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

    # ==================== 股票基本信息 ====================

    def sync_stock_basic(self) -> int:
        """
        同步股票基本信息
        股票信息基本不变化，每周同步一次即可
        """
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

            with get_connection() as conn:
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

    # ==================== 日线K线数据 ====================

    def sync_daily_kline(self, ts_code: str, start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> int:
        """
        同步单只股票的日线数据（增量更新）

        Args:
            ts_code: 股票代码，如 '000001.SZ'
            start_date: 开始日期，格式 YYYYMMDD，None 表示从数据库最后一条开始
            end_date: 结束日期，格式 YYYYMMDD，None 表示到最新

        Returns:
            更新条数
        """
        # 增量更新：获取最后同步日期
        if start_date is None:
            last_date = self._get_last_date("daily_kline", ts_code)
            if last_date:
                # 从后一天开始
                last_dt = datetime.strptime(last_date, "%Y%m%d")
                start_date = (last_dt + timedelta(days=1)).strftime("%Y%m%d")

        # 默认从2年前开始
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

            # 计算量比（需要历史数据，这里先跳过，由指标计算模块处理）
            # 计算涨跌停标记
            df['is_limit_up'] = df['pct_chg'].apply(lambda x: 1 if x >= 9.9 else 0)
            df['is_limit_down'] = df['pct_chg'].apply(lambda x: 1 if x <= -9.9 else 0)

            with get_connection() as conn:
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
                        None,  # vol_ratio later
                        row.get('is_limit_up', 0), row.get('is_limit_down', 0)
                    ))

            # 更新同步日志
            latest_date = df['trade_date'].max()
            self._log_sync("daily_kline", ts_code, latest_date, "success")

            logger.info(f"日线数据同步完成: {ts_code}, {len(df)} 条, {start_date}-{latest_date}")
            return len(df)

        except Exception as e:
            logger.error(f"日线数据同步失败 {ts_code}: {e}")
            self._log_sync("daily_kline", ts_code, "", "failed", str(e))
            return 0

    def sync_all_daily_kline(self, ts_codes: Optional[List[str]] = None,
                              days: int = 730) -> Dict[str, int]:
        """
        批量同步多只股票的日线数据

        Args:
            ts_codes: 股票代码列表，None 表示同步所有股票
            days: 同步天数，默认2年

        Returns:
            每只股票的更新条数
        """
        results = {}

        # 如果没有指定股票，获取所有股票代码
        if ts_codes is None:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ts_code FROM stock_basic")
                ts_codes = [row['ts_code'] for row in cursor.fetchall()]

        logger.info(f"开始批量同步日线数据，共 {len(ts_codes)} 只股票...")

        # 计算起始日期
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        for i, ts_code in enumerate(ts_codes):
            try:
                # 检查是否已有数据，避免重复同步
                last_date = self._get_last_date("daily_kline", ts_code)
                if last_date:
                    last_dt = datetime.strptime(last_date, "%Y%m%d")
                    if (datetime.now() - last_dt).days < 2:
                        # 2天内已同步过，跳过
                        continue

                count = self.sync_daily_kline(ts_code, start_date, end_date)
                results[ts_code] = count

                # 进度显示
                if (i + 1) % 10 == 0:
                    logger.info(f"进度: {i + 1}/{len(ts_codes)}")

            except Exception as e:
                logger.error(f"同步失败 {ts_code}: {e}")
                results[ts_code] = 0

        logger.info(f"批量同步完成，成功 {sum(1 for v in results.values() if v > 0)}/{len(ts_codes)}")
        return results

    # ==================== 指标缓存 ====================

    def sync_indicator_cache(self, ts_code: str, days: int = 120) -> int:
        """
        同步单只股票的技术指标到 indicator_cache 表

        Args:
            ts_code: 股票代码
            days: 计算天数

        Returns:
            更新条数
        """
        try:
            # 导入指标计算模块
            try:
                from .indicators import (
                    get_kline_data, analyze_stock, calculate_kdj, calculate_macd,
                    calculate_bbi, calculate_ma, calculate_rsi_multi, calculate_wr_multi,
                    calculate_bollinger, calculate_vol_ratio, calculate_zg_white,
                    calculate_dg_yellow, detect_double_line_cross, detect_needle_20,
                    calculate_brick_value, calculate_brick_history, detect_brick_trend,
                    detect_fanbao, detect_volume_pattern, calculate_sell_score,
                    detect_trade_signal, calculate_dmi
                )
            except ImportError:
                from indicators import (
                    get_kline_data, analyze_stock, calculate_kdj, calculate_macd,
                    calculate_bbi, calculate_ma, calculate_rsi_multi, calculate_wr_multi,
                    calculate_bollinger, calculate_vol_ratio, calculate_zg_white,
                    calculate_dg_yellow, detect_double_line_cross, detect_needle_20,
                    calculate_brick_value, calculate_brick_history, detect_brick_trend,
                    detect_fanbao, detect_volume_pattern, calculate_sell_score,
                    detect_trade_signal, calculate_dmi
                )

            # 获取K线数据
            klines = get_kline_data(ts_code, days)
            if not klines:
                return 0

            # 计算所有指标
            result = analyze_stock(ts_code, days)

            # 准备写入数据
            with get_connection() as conn:
                cursor = conn.cursor()

                for i, kline in enumerate(klines):
                    # 计算单日指标
                    sub_klines = klines[:i+1]
                    today = kline
                    yesterday = sub_klines[-2] if len(sub_klines) > 1 else None

                    # 获取各项指标
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

                    # 昨高昨低
                    prev_high = sub_klines[-2].high if len(sub_klines) > 1 else 0
                    prev_low = sub_klines[-2].low if len(sub_klines) > 1 else 0

                    cursor.execute("""
                        INSERT OR REPLACE INTO indicator_cache
                        (ts_code, trade_date, close, open, high, low, vol, pct_chg,
                         k, d, j, dif, dea, macd_hist, bbi,
                         ma5, ma10, ma20, ma60,
                         rsi6, rsi12, rsi24, wr5, wr10,
                         boll_mid, boll_upper, boll_lower, boll_width, boll_position,
                         vol_ratio, zg_white, dg_yellow,
                         is_gold_cross, is_dead_cross,
                         rsl_short, rsl_long, is_needle_20,
                         brick_value, brick_trend, brick_count, brick_trend_up, is_fanbao,
                         is_beidou, is_suoliang, is_jiayin_zhenyang, is_jiayang_zhenyin, is_fangliang_yinxian,
                         sell_score, sell_reason, signal, signal_desc,
                         prev_high, prev_low, dmi_plus, dmi_minus, adx,
                         net_lg_mf, net_elg_mf, last_b1_date, last_b1_price,
                         last_yidong_date, market_pct_chg, market_dir, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ts_code, today.trade_date, today.close, today.open, today.high, today.low, today.vol, today.pct_chg,
                        k, d, j, dif, dea, macd_hist, bbi,
                        ma5, ma10, ma20, ma60,
                        rsi6, rsi12, rsi24, wr5, wr10,
                        boll_mid, boll_upper, boll_lower, boll_width, boll_pos,
                        vol_ratio, zg_white, dg_yellow,
                        int(gold_cross), int(dead_cross),
                        rsl_short, rsl_long, int(is_needle),
                        brick_value, brick_trend, brick_count, int(brick_trend_up), int(is_fanbao),
                        int(vol_pattern.get('is_beidou', 0)), int(vol_pattern.get('is_suoliang', 0)),
                        int(vol_pattern.get('is_jiayin_zhenyang', 0)), int(vol_pattern.get('is_jiayang_zhenyin', 0)),
                        int(vol_pattern.get('is_fangliang_yinxian', 0)),
                        sell_score, sell_reason, signal_desc, signal_desc,
                        prev_high, prev_low, dmi_plus, dmi_minus, adx,
                        0, 0, None, 0, None, 0, 'NEUTRAL', None
                    ))

            self._log_sync("indicator_cache", ts_code, klines[-1].trade_date, "success")
            logger.info(f"指标缓存同步完成: {ts_code}, {len(klines)} 条")
            return len(klines)

        except Exception as e:
            logger.error(f"指标缓存同步失败 {ts_code}: {e}")
            self._log_sync("indicator_cache", ts_code, "", "failed", str(e))
            return 0

    def sync_all_indicators(self, ts_codes: Optional[List[str]] = None) -> Dict[str, int]:
        """
        批量同步所有股票的指标缓存

        Args:
            ts_codes: 股票代码列表，None 表示同步所有有K线数据的股票

        Returns:
            每只股票的更新条数
        """
        results = {}

        if ts_codes is None:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT ts_code FROM daily_kline")
                ts_codes = [row['ts_code'] for row in cursor.fetchall()]

        logger.info(f"开始批量同步指标缓存，共 {len(ts_codes)} 只股票...")

        for i, ts_code in enumerate(ts_codes):
            try:
                count = self.sync_indicator_cache(ts_code)
                results[ts_code] = count

                if (i + 1) % 10 == 0:
                    logger.info(f"进度: {i + 1}/{len(ts_codes)}")

            except Exception as e:
                logger.error(f"指标同步失败 {ts_code}: {e}")
                results[ts_code] = 0

        logger.info(f"批量指标同步完成，成功 {sum(1 for v in results.values() if v > 0)}/{len(ts_codes)}")
        return results


    # ==================== 资金流向 ====================

    def sync_moneyflow(self, ts_code: str, trade_date: str) -> int:
        """
        同步单只股票的单日资金流向

        Args:
            ts_code: 股票代码
            trade_date: 交易日期，格式 YYYYMMDD

        Returns:
            更新条数
        """
        try:
            self._rate_limit("moneyflow")
            df = self.pro.moneyflow(ts_code=ts_code, trade_date=trade_date)

            if df is None or len(df) == 0:
                return 0

            with get_connection() as conn:
                cursor = conn.cursor()
                for _, row in df.iterrows():
                    cursor.execute("""
                        INSERT OR REPLACE INTO moneyflow
                        (ts_code, trade_date, buy_sm_amount, buy_md_amount,
                         buy_lg_amount, buy_elg_amount, sell_sm_amount,
                         sell_md_amount, sell_lg_amount, sell_elg_amount,
                         net_mf, pct_mf)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row['ts_code'], row['trade_date'],
                        row.get('buy_sm_amount'), row.get('buy_md_amount'),
                        row.get('buy_lg_amount'), row.get('buy_elg_amount'),
                        row.get('sell_sm_amount'), row.get('sell_md_amount'),
                        row.get('sell_lg_amount'), row.get('sell_elg_amount'),
                        row.get('net_mf'), row.get('pct_mf')
                    ))

            self._log_sync("moneyflow", ts_code, trade_date, "success")
            return len(df)

        except Exception as e:
            logger.error(f"资金流向同步失败 {ts_code} {trade_date}: {e}")
            self._log_sync("moneyflow", ts_code, "", "failed", str(e))
            return 0

    # ==================== 工具方法 ====================

    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        with get_connection() as conn:
            cursor = conn.cursor()

            # 各表数据量
            cursor.execute("SELECT COUNT(*) as cnt FROM stock_basic")
            stock_count = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(*) as cnt FROM daily_kline")
            kline_count = cursor.fetchone()['cnt']

            # 最后同步时间
            cursor.execute("""
                SELECT data_type, last_date, status, created_at
                FROM sync_log
                WHERE id IN (
                    SELECT MAX(id) FROM sync_log GROUP BY data_type
                )
            """)
            sync_status = [dict(row) for row in cursor.fetchall()]

            return {
                "stock_count": stock_count,
                "kline_count": kline_count,
                "db_path": str(get_db_path()),
                "sync_status": sync_status
            }


# ==================== 命令行工具 ====================

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Tushare 数据同步工具")
    parser.add_argument("action", choices=["init", "sync", "status"],
                        help="操作: init=初始化数据库, sync=同步数据, status=查看状态")
    parser.add_argument("--ts_code", help="股票代码，如 000001.SZ")
    parser.add_argument("--days", type=int, default=730, help="同步天数")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    if args.action == "init":
        from .database import init_database
        init_database()
        print("数据库初始化完成")

    elif args.action == "sync":
        syncer = DataSyncer()

        if args.ts_code:
            # 同步单只股票
            syncer.sync_daily_kline(args.ts_code)
        else:
            # 批量同步所有股票
            syncer.sync_stock_basic()
            syncer.sync_all_daily_kline(days=args.days)

        print("同步完成")
        print(syncer.get_sync_status())

    elif args.action == "status":
        syncer = DataSyncer()
        status = syncer.get_sync_status()
        print("=" * 50)
        print(f"数据库: {status['db_path']}")
        print(f"股票数量: {status['stock_count']}")
        print(f"K线数据: {status['kline_count']}")
        print("-" * 50)
        print("同步状态:")
        for s in status['sync_status']:
            print(f"  {s['data_type']}: {s['last_date']} ({s['status']})")


if __name__ == "__main__":
    main()

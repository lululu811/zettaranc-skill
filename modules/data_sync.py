"""
数据同步模块
从 Tushare API 获取数据并存储到 SQLite
支持增量更新和全量更新
"""

import os
import time
import logging
import threading
import collections
import multiprocessing
import concurrent.futures
from datetime import datetime, timedelta
from typing import Any, Optional

try:
    import tushare as ts
except ImportError:
    print("请先安装依赖: pip install tushare")

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载，override=True）

from .database import get_connection, get_db_path

logger = logging.getLogger(__name__)

# 并发同步线程数（4 个 sync_* 方法共用）
_MAX_SYNC_WORKERS = 5

# 涨跌停阈值（主板 10%，此处用 9.9% 容差）
# 注意：创业板(300xxx)/科创板(688xxx) 实际为 20%，ST 为 5%，
# 新股前 5 日无限制。当前简化处理，v2.11.0 计划按 market 字段动态调整。
_LIMIT_THRESHOLD = 9.9

# 中转 API 配置（从环境变量读取）
TUSHARE_API_URL = os.environ.get("TUSHARE_API_URL", "")
VERIFY_TOKEN_URL = os.environ.get("TUSHARE_VERIFY_TOKEN_URL", "")


# ==================== 模块级限流器（v2.10.0 P1-4） ====================
# 多进程安全：同机多进程共享同一把 multiprocessing.Lock
# 限流仅同机多进程有效，跨机器需 Redis 协调（详见 plan P1-4 风险）
class _RateLimiter:
    """Tushare 限流器（多进程安全 + 滑动窗口 token bucket）

    设计：
    - 60s 滑动窗口内的请求计数（in-memory deque）
    - multiprocessing.Lock 序列化 critical section
    - TUSHARE_RPM env var 控制 max requests/min（默认 180，留 20 缓冲应对 200 上限）

    用法：
        _GLOBAL_LIMITER.wait()  # 阻塞直到安全可调
    """

    def __init__(self, max_per_min: int = 180):
        self._max = max_per_min
        self._window: collections.deque = collections.deque()
        # 关键：multiprocessing.Lock 不是进程间共享的默认锁
        # 在父进程创建，子进程 fork 后会继承一份
        self._lock = multiprocessing.Lock()

    def wait(self) -> None:
        """阻塞直到 60s 窗口内有空位"""
        with self._lock:
            now = time.monotonic()
            # 弹出 60s 外的旧时间戳
            while self._window and (now - self._window[0]) > 60:
                self._window.popleft()
            if len(self._window) >= self._max:
                # 等待最老一项出窗口
                sleep_for = 60 - (now - self._window[0]) + 0.05  # +0.05s 缓冲
                logger.debug(f"限流：等 {sleep_for:.2f}s（窗口已满 {self._max} req）")
                time.sleep(sleep_for)
                # 重新弹出（防止极端情况）
                now = time.monotonic()
                while self._window and (now - self._window[0]) > 60:
                    self._window.popleft()
            self._window.append(time.monotonic())

    @property
    def current_count(self) -> int:
        """当前窗口内请求数（只读，调试用）"""
        with self._lock:
            now = time.monotonic()
            while self._window and (now - self._window[0]) > 60:
                self._window.popleft()
            return len(self._window)


# 模块级单例（v2.10.0 P1-4 替代原 instance-level _rate_limit_lock）
_GLOBAL_LIMITER = _RateLimiter(max_per_min=int(os.environ.get("TUSHARE_RPM", "180")))


def _rate_limit_global() -> None:
    """模块级公开限流入口（v2.10.0 P1-4 新增，替代 instance-level _rate_limit）"""
    _GLOBAL_LIMITER.wait()


class DataSyncer:
    """数据同步器"""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("TUSHARE_TOKEN")
        # 仅在 JNB 模式下强制检查 Tushare 配置
        data_mode = os.getenv("DATA_MODE", "websearch")
        if data_mode == "jnb":
            if not self.token:
                raise ValueError("JNB 模式下未设置 TUSHARE_TOKEN，请检查 .env 文件。")
            if not TUSHARE_API_URL:
                raise ValueError(
                    "JNB 模式下未设置 TUSHARE_API_URL，请在 .env 中配置中转 API 地址。\n"
                    "示例：TUSHARE_API_URL=https://tt.xiaodefa.cn"
                )

        # 初始化 Tushare
        ts.set_token(self.token)
        self.pro = ts.pro_api()
        self.pro._DataApi__http_url = TUSHARE_API_URL

        # 向后兼容：保留 instance-level attrs（外部可能引用）
        # 但实际限流走模块级 _GLOBAL_LIMITER
        # （v2.11.0 计划移除，改用 @property + DeprecationWarning）
        self.last_request_time: dict[str, float] = {}

    def _rate_limit(self, api_name: str):
        """线程安全的限流控制（v2.10.0 P1-4 改为调模块级 _GLOBAL_LIMITER）"""
        # v2.10.0：原 per-instance lock 改用模块级 multiprocessing 安全限流器
        _rate_limit_global()
        # 保留旧字段更新，便于外部观察（不影响实际限流）
        self.last_request_time[api_name] = time.time()

    def _log_sync(self, data_type: str, ts_code: str | None, last_date: str, status: str, message: str = ""):
        """记录同步日志"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sync_log (data_type, ts_code, last_date, status, message)
                VALUES (?, ?, ?, ?, ?)
            """,
                (data_type, ts_code, last_date, status, message),
            )

    def _get_last_date(self, data_type: str, ts_code: str | None = None) -> str | None:
        """获取最后同步日期"""
        with get_connection() as conn:
            cursor = conn.cursor()
            if ts_code:
                cursor.execute(
                    """
                    SELECT last_date FROM sync_log
                    WHERE data_type = ? AND ts_code = ? AND status = 'success'
                    ORDER BY created_at DESC LIMIT 1
                """,
                    (data_type, ts_code),
                )
            else:
                cursor.execute(
                    """
                    SELECT last_date FROM sync_log
                    WHERE data_type = ? AND ts_code IS NULL AND status = 'success'
                    ORDER BY created_at DESC LIMIT 1
                """,
                    (data_type,),
                )
            result = cursor.fetchone()
            return result["last_date"] if result else None

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
                exchange="", list_status="L", fields="ts_code,name,area,industry,market,list_date,is_hs"
            )

            if df is None or len(df) == 0:
                logger.warning("获取股票基本信息失败")
                return 0

            # 填充 NaN 以免插入失败，且保留必要的列
            df = df[["ts_code", "name", "area", "industry", "market", "list_date", "is_hs"]].fillna("")
            with get_connection() as conn:
                df.to_sql("stock_basic", conn, if_exists="append", index=False, method="multi")

            self._log_sync("stock_basic", None, datetime.now().strftime("%Y%m%d"), "success")
            logger.info(f"股票基本信息同步完成，共 {len(df)} 只")
            return len(df)

        except Exception as e:
            logger.error(f"股票基本信息同步失败: {e}")
            self._log_sync("stock_basic", None, "", "failed", str(e))
            return 0

    # ==================== 日线K线数据 ====================

    def sync_daily_kline(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> int:
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
            df = ts.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                adj="qfq",
                api=self.pro,
            )

            if df is None or len(df) == 0:
                return 0

            # 计算量比（需要历史数据，这里先跳过，由指标计算模块处理）
            # 计算涨跌停标记
            df["is_limit_up"] = df["pct_chg"].apply(lambda x: 1 if x >= _LIMIT_THRESHOLD else 0)
            df["is_limit_down"] = df["pct_chg"].apply(lambda x: 1 if x <= -_LIMIT_THRESHOLD else 0)

            with get_connection() as conn:
                cursor = conn.cursor()

                # 准备批量插入的数据
                records = []
                for row in df.itertuples(index=False):
                    row_dict = row._asdict()
                    records.append(
                        (
                            row_dict["ts_code"],
                            row_dict["trade_date"],
                            row_dict["open"],
                            row_dict["high"],
                            row_dict["low"],
                            row_dict["close"],
                            row_dict["vol"],
                            row_dict["amount"],
                            row_dict.get("pct_chg", 0),
                            None,  # vol_ratio later
                            row_dict.get("is_limit_up", 0),
                            row_dict.get("is_limit_down", 0),
                        )
                    )

                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO daily_kline
                    (ts_code, trade_date, open, high, low, close, vol, amount,
                     pct_chg, vol_ratio, is_limit_up, is_limit_down)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    records,
                )

            # 更新同步日志
            latest_date = df["trade_date"].max()
            self._log_sync("daily_kline", ts_code, latest_date, "success")

            logger.info(f"日线数据同步完成: {ts_code}, {len(df)} 条, {start_date}-{latest_date}")
            return len(df)

        except Exception as e:
            logger.error(f"日线数据同步失败 {ts_code}: {e}")
            self._log_sync("daily_kline", ts_code, "", "failed", str(e))
            return 0

    def sync_missing(self, ts_codes: list[str], days: int = 730) -> dict[str, int]:
        """
        同步 ts_codes 中"在 daily_kline 表里完全缺失"的股票（增量补齐）

        与 sync_all_daily_kline 的区别：
        - sync_all_daily_kline：所有 ts_codes 都同步（已有的会跳过早于 2 天的部分）
        - sync_missing：只在 daily_kline 表里完全没有数据的才同步

        用于"自选股清单第一次接入"或"补齐漏掉的股票"场景

        Args:
            ts_codes: 股票代码列表
            days: 同步天数

        Returns:
            每只股票的更新条数
        """
        if not ts_codes:
            return {}

        with get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(ts_codes))
            cursor.execute(
                f"SELECT DISTINCT ts_code FROM daily_kline WHERE ts_code IN ({placeholders})",
                ts_codes,
            )
            have = {row["ts_code"] for row in cursor.fetchall()}

        missing = [c for c in ts_codes if c not in have]
        logger.info(f"sync_missing: 共 {len(ts_codes)} 只，已有 {len(have)} 只，需补齐 {len(missing)} 只")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        results = {}
        for code in missing:
            count = self.sync_daily_kline(code, start_date=start_date)
            results[code] = count
        return results

    def sync_all_daily_kline(self, ts_codes: list[str] | None = None, days: int = 730) -> dict[str, int]:
        """
        批量同步多只股票的日线数据（并发执行）

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
                ts_codes = [row["ts_code"] for row in cursor.fetchall()]

        logger.info(f"开始批量同步日线数据，共 {len(ts_codes)} 只股票...")

        # 计算起始日期
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        # 进度追踪锁
        progress_lock = threading.Lock()
        completed = 0
        total = len(ts_codes)

        def sync_single(ts_code):
            nonlocal completed
            try:
                # 检查是否已有数据，避免重复同步
                last_date = self._get_last_date("daily_kline", ts_code)
                if last_date:
                    last_dt = datetime.strptime(last_date, "%Y%m%d")
                    if (datetime.now() - last_dt).days < 2:
                        with progress_lock:
                            completed += 1
                        return ts_code, 0  # Skip

                count = self.sync_daily_kline(ts_code, start_date, end_date)

                with progress_lock:
                    completed += 1
                    if completed % 10 == 0:
                        logger.info(f"进度: {completed}/{total}")

                return ts_code, count
            except Exception as e:
                logger.error(f"同步失败 {ts_code}: {e}")
                with progress_lock:
                    completed += 1
                return ts_code, 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_SYNC_WORKERS) as executor:
            futures = [executor.submit(sync_single, code) for code in ts_codes]
            for future in concurrent.futures.as_completed(futures):
                code, count = future.result()
                results[code] = count

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
            from .indicators import (
                get_kline_data,
                precompute_kdj_sequence,
                precompute_macd_sequence,
                calculate_bbi,
                calculate_ma,
                calculate_rsi_multi,
                calculate_wr_multi,
                calculate_bollinger,
                calculate_vol_ratio,
                calculate_zg_white,
                calculate_dg_yellow,
                detect_double_line_cross,
                detect_needle_20,
                calculate_brick_value,
                calculate_brick_history,
                detect_brick_trend,
                detect_fanbao,
                detect_volume_pattern,
                calculate_sell_score,
                detect_trade_signal,
                calculate_dmi,
            )

            # 获取K线数据
            klines = get_kline_data(ts_code, days)
            if not klines:
                return 0

            # 预计算指标序列（避免循环中O(n²)重复计算）
            kdj_seq = precompute_kdj_sequence(klines) if len(klines) >= 9 else None
            macd_dif_seq, macd_dea_seq, macd_hist_seq = (
                precompute_macd_sequence(klines) if len(klines) >= 30 else (None, None, None)
            )

            # 准备写入数据
            with get_connection() as conn:
                cursor = conn.cursor()

                for i, kline in enumerate(klines):
                    # 计算单日指标
                    sub_klines = klines[: i + 1]
                    today = kline
                    yesterday = sub_klines[-2] if len(sub_klines) > 1 else None

                    # 获取各项指标（优先从预计算序列取值）
                    if kdj_seq:
                        k, d, j = kdj_seq[i]
                    else:
                        k, d, j = 50, 50, 50

                    if macd_dif_seq is not None and macd_dea_seq is not None and macd_hist_seq is not None:
                        dif = macd_dif_seq[i]
                        dea = macd_dea_seq[i]
                        macd_hist = macd_hist_seq[i]
                    else:
                        dif, dea, macd_hist = 0.0, 0.0, 0.0

                    bbi = calculate_bbi(sub_klines) if len(sub_klines) >= 24 else 0

                    closes = [k.close for k in sub_klines]
                    ma5 = calculate_ma(closes, 5) if len(closes) >= 5 else 0
                    ma10 = calculate_ma(closes, 10) if len(closes) >= 10 else 0
                    ma20 = calculate_ma(closes, 20) if len(closes) >= 20 else 0
                    ma60 = calculate_ma(closes, 60) if len(closes) >= 60 else 0

                    rsi6, rsi12, rsi24 = calculate_rsi_multi(sub_klines) if len(sub_klines) >= 25 else (50, 50, 50)
                    wr5, wr10 = calculate_wr_multi(sub_klines) if len(sub_klines) >= 10 else (-50, -50)

                    boll_mid, boll_upper, boll_lower, boll_width, boll_pos = (
                        calculate_bollinger(sub_klines) if len(sub_klines) >= 20 else (0, 0, 0, 0, 50)
                    )

                    vol_ratio = calculate_vol_ratio(sub_klines)

                    zg_white = calculate_zg_white(sub_klines) if len(sub_klines) >= 115 else 0
                    dg_yellow = calculate_dg_yellow(sub_klines) if len(sub_klines) >= 115 else 0
                    gold_cross, dead_cross = (
                        detect_double_line_cross(sub_klines) if len(sub_klines) >= 115 else (False, False)
                    )

                    rsl_short, rsl_long, is_needle = (
                        detect_needle_20(sub_klines) if len(sub_klines) >= 22 else (50, 50, False)
                    )

                    brick_value = calculate_brick_value(sub_klines) if len(sub_klines) >= 8 else 0
                    brick_trend, brick_count = (
                        calculate_brick_history(sub_klines) if len(sub_klines) >= 10 else ("NEUTRAL", 0)
                    )
                    brick_trend_up = detect_brick_trend(sub_klines) if len(sub_klines) >= 115 else False
                    is_fanbao = detect_fanbao(sub_klines) if len(sub_klines) >= 4 else False

                    vol_pattern = detect_volume_pattern(today, yesterday) if yesterday else {}
                    sell_result = calculate_sell_score(sub_klines) if len(sub_klines) >= 5 else (3, {})
                    sell_score = sell_result[0]
                    sell_items = sell_result[1] if isinstance(sell_result[1], dict) else {}
                    sell_reason = ",".join([k for k, v in sell_items.items() if not v]) if sell_items else "数据不足"
                    signal = detect_trade_signal(sub_klines) if len(sub_klines) >= 30 else "WATCH"
                    signal_desc = signal.value if hasattr(signal, "value") else str(signal)

                    dmi_plus, dmi_minus, adx = calculate_dmi(sub_klines) if len(sub_klines) >= 30 else (0, 0, 0)

                    # 昨高昨低
                    prev_high = sub_klines[-2].high if len(sub_klines) > 1 else 0
                    prev_low = sub_klines[-2].low if len(sub_klines) > 1 else 0

                    cursor.execute(
                        """
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
                    """,
                        (
                            ts_code,
                            today.trade_date,
                            today.close,
                            today.open,
                            today.high,
                            today.low,
                            today.vol,
                            today.pct_chg,
                            k,
                            d,
                            j,
                            dif,
                            dea,
                            macd_hist,
                            bbi,
                            ma5,
                            ma10,
                            ma20,
                            ma60,
                            rsi6,
                            rsi12,
                            rsi24,
                            wr5,
                            wr10,
                            boll_mid,
                            boll_upper,
                            boll_lower,
                            boll_width,
                            boll_pos,
                            vol_ratio,
                            zg_white,
                            dg_yellow,
                            int(gold_cross),
                            int(dead_cross),
                            rsl_short,
                            rsl_long,
                            int(is_needle),
                            brick_value,
                            brick_trend,
                            brick_count,
                            int(brick_trend_up),
                            int(is_fanbao),
                            int(vol_pattern.get("is_beidou", 0)),
                            int(vol_pattern.get("is_suoliang", 0)),
                            int(vol_pattern.get("is_jiayin_zhenyang", 0)),
                            int(vol_pattern.get("is_jiayang_zhenyin", 0)),
                            int(vol_pattern.get("is_fangliang_yinxian", 0)),
                            sell_score,
                            sell_reason,
                            signal_desc,
                            signal_desc,
                            prev_high,
                            prev_low,
                            dmi_plus,
                            dmi_minus,
                            adx,
                            0,
                            0,
                            None,
                            0,
                            None,
                            0,
                            "NEUTRAL",
                            None,
                        ),
                    )

            self._log_sync("indicator_cache", ts_code, klines[-1].trade_date, "success")
            logger.info(f"指标缓存同步完成: {ts_code}, {len(klines)} 条")
            return len(klines)

        except Exception as e:
            logger.error(f"指标缓存同步失败 {ts_code}: {e}")
            self._log_sync("indicator_cache", ts_code, "", "failed", str(e))
            return 0

    def sync_all_indicators(self, ts_codes: list[str] | None = None) -> dict[str, int]:
        """
        批量同步所有股票的指标缓存（并发执行）

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
                ts_codes = [row["ts_code"] for row in cursor.fetchall()]

        logger.info(f"开始批量同步指标缓存，共 {len(ts_codes)} 只股票...")

        progress_lock = threading.Lock()
        completed = 0
        total = len(ts_codes)

        def sync_single(ts_code):
            nonlocal completed
            try:
                count = self.sync_indicator_cache(ts_code)
                with progress_lock:
                    completed += 1
                    if completed % 10 == 0:
                        logger.info(f"进度: {completed}/{total}")
                return ts_code, count
            except Exception as e:
                logger.error(f"指标同步失败 {ts_code}: {e}")
                with progress_lock:
                    completed += 1
                return ts_code, 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_SYNC_WORKERS) as executor:
            futures = [executor.submit(sync_single, code) for code in ts_codes]
            for future in concurrent.futures.as_completed(futures):
                code, count = future.result()
                results[code] = count

        logger.info(f"批量指标同步完成，成功 {sum(1 for v in results.values() if v > 0)}/{len(ts_codes)}")
        return results

    def sync_daily_and_compute(self, ts_codes: list[str] | None = None, days: int = 730) -> dict[str, int]:
        """
        一站式：同步日线 K 线 + 同步指标缓存

        这是 scripts/sync_and_compute.py 业务逻辑的接收方
        （v2.10.0 之前是 ~300 行的内联实现）

        Args:
            ts_codes: 股票代码列表，None = 全市场
            days: 同步天数

        Returns:
            每只股票的指标更新条数（dict[ts_code] = count）
        """
        kline_results = self.sync_all_daily_kline(ts_codes=ts_codes, days=days)
        # 同步哪些股票有数据，传给指标计算
        if ts_codes is None:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT ts_code FROM daily_kline")
                ts_codes_for_indic = [row["ts_code"] for row in cursor.fetchall()]
        else:
            ts_codes_for_indic = [c for c, n in kline_results.items() if n > 0]
        return self.sync_all_indicators(ts_codes=ts_codes_for_indic or None)

    # ==================== Tushare 官方指标（用于 diff 验证） ====================

    def sync_stk_factor(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> int:
        """
        同步单只股票的 Tushare 官方技术指标（stk_factor 接口）

        Args:
            ts_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            更新条数
        """
        try:
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            if end_date is None:
                end_date = datetime.now().strftime("%Y%m%d")

            self._rate_limit("stk_factor")
            df = self.pro.stk_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is None or len(df) == 0:
                return 0

            # 字段映射：Tushare 字段名 -> 数据库字段名
            field_map = {
                "ts_code": "ts_code",
                "trade_date": "trade_date",
                "close": "close",
                "macd_dif": "macd_dif",
                "macd_dea": "macd_dea",
                "macd": "macd",
                "kdj_k": "kdj_k",
                "kdj_d": "kdj_d",
                "kdj_j": "kdj_j",
                "rsi_6": "rsi_6",
                "rsi_12": "rsi_12",
                "rsi_24": "rsi_24",
                "boll_upper": "boll_upper",
                "boll_mid": "boll_mid",
                "boll_lower": "boll_lower",
                "cci": "cci",
            }

            with get_connection() as conn:
                cursor = conn.cursor()
                records = []
                for row in df.itertuples(index=False):
                    row_dict = row._asdict()
                    values = [row_dict.get(field_map.get(k, k), 0) for k in field_map.keys()]
                    records.append(values)

                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO tushare_indicator_cache
                    (ts_code, trade_date, close, macd_dif, macd_dea, macd,
                     kdj_k, kdj_d, kdj_j, rsi_6, rsi_12, rsi_24,
                     boll_upper, boll_mid, boll_lower, cci)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    records,
                )

            latest_date = df["trade_date"].max()
            self._log_sync("stk_factor", ts_code, latest_date, "success")
            logger.info(f"Tushare 指标同步完成: {ts_code}, {len(df)} 条")
            return len(df)

        except Exception as e:
            logger.error(f"Tushare 指标同步失败 {ts_code}: {e}")
            self._log_sync("stk_factor", ts_code, "", "failed", str(e))
            return 0

    def sync_all_stk_factor(self, ts_codes: list[str] | None = None, days: int = 365) -> dict[str, int]:
        """
        批量同步多只股票的 Tushare 官方指标（并发执行）

        Args:
            ts_codes: 股票代码列表，None 表示同步所有股票
            days: 同步天数

        Returns:
            每只股票的更新条数
        """
        results = {}

        if ts_codes is None:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ts_code FROM stock_basic")
                ts_codes = [row["ts_code"] for row in cursor.fetchall()]

        logger.info(f"开始批量同步 Tushare 指标，共 {len(ts_codes)} 只股票...")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        progress_lock = threading.Lock()
        completed = 0
        total = len(ts_codes)

        def sync_single(ts_code):
            nonlocal completed
            try:
                count = self.sync_stk_factor(ts_code, start_date, end_date)
                with progress_lock:
                    completed += 1
                    if completed % 10 == 0:
                        logger.info(f"进度: {completed}/{total}")
                return ts_code, count
            except Exception as e:
                logger.error(f"Tushare 指标同步失败 {ts_code}: {e}")
                with progress_lock:
                    completed += 1
                return ts_code, 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_SYNC_WORKERS) as executor:
            futures = [executor.submit(sync_single, code) for code in ts_codes]
            for future in concurrent.futures.as_completed(futures):
                code, count = future.result()
                results[code] = count

        logger.info(f"批量 Tushare 指标同步完成，成功 {sum(1 for v in results.values() if v > 0)}/{len(ts_codes)}")
        return results

    # ==================== 每日估值指标 (PE/PB/PS) ====================

    def ensure_daily_basic_columns(self):
        """确保 daily_kline 表包含 PE/PB/PS/总市值/流通市值 列"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(daily_kline)")
            existing = {row[1] for row in cursor.fetchall()}

            for col_name, col_type in [
                ("pe", "REAL"),
                ("pe_ttm", "REAL"),
                ("pb", "REAL"),
                ("ps", "REAL"),
                ("ps_ttm", "REAL"),
                ("total_mv", "REAL"),
                ("circ_mv", "REAL"),
            ]:
                if col_name not in existing:
                    cursor.execute(f"ALTER TABLE daily_kline ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to daily_kline")

    def sync_daily_basic(self, ts_code: str, start_date: str = "", end_date: str = "") -> int:
        """
        同步单只股票的每日估值指标（PE/PB/PS/市值等）

        使用 Tushare daily_basic 接口，数据写入 daily_kline 表对应列。

        Args:
            ts_code: 股票代码
            start_date: 起始日期 YYYYMMDD，默认 2 年前
            end_date: 结束日期 YYYYMMDD，默认今天

        Returns:
            更新条数
        """
        try:
            self.ensure_daily_basic_columns()
            self._rate_limit("daily_basic")

            if not start_date:
                start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")

            df = self.pro.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or len(df) == 0:
                return 0

            with get_connection() as conn:
                cursor = conn.cursor()
                for row in df.itertuples(index=False):
                    row_dict = row._asdict()
                    cursor.execute(
                        """
                        UPDATE daily_kline SET
                            pe = ?, pe_ttm = ?, pb = ?, ps = ?, ps_ttm = ?,
                            total_mv = ?, circ_mv = ?
                        WHERE ts_code = ? AND trade_date = ?
                    """,
                        (
                            row_dict.get("pe"),
                            row_dict.get("pe_ttm"),
                            row_dict.get("pb"),
                            row_dict.get("ps"),
                            row_dict.get("ps_ttm"),
                            row_dict.get("total_mv"),
                            row_dict.get("circ_mv"),
                            row_dict["ts_code"],
                            row_dict["trade_date"],
                        ),
                    )

            self._log_sync("daily_basic", ts_code, end_date, "success")
            return len(df)

        except Exception as e:
            logger.error(f"每日估值指标同步失败 {ts_code}: {e}")
            self._log_sync("daily_basic", ts_code, "", "failed", str(e))
            return 0

    def sync_all_daily_basic(self, ts_codes: list[str] | None = None, days: int = 730) -> dict[str, int]:
        """
        批量同步多只股票的每日估值指标（并发执行）

        Args:
            ts_codes: 股票代码列表，None 表示同步所有有 K 线的股票
            days: 同步天数，默认 2 年

        Returns:
            每只股票的更新条数
        """
        self.ensure_daily_basic_columns()
        results = {}

        if ts_codes is None:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT ts_code FROM daily_kline ORDER BY ts_code")
                ts_codes = [row[0] for row in cursor.fetchall()]

        logger.info(f"开始批量同步每日估值指标，共 {len(ts_codes)} 只股票...")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        progress_lock = threading.Lock()
        completed = 0
        total = len(ts_codes)

        def sync_single(ts_code):
            nonlocal completed
            try:
                count = self.sync_daily_basic(ts_code, start_date, end_date)
                with progress_lock:
                    completed += 1
                    if completed % 10 == 0:
                        logger.info(f"进度: {completed}/{total}")
                return ts_code, count
            except Exception as e:
                logger.error(f"估值指标同步失败 {ts_code}: {e}")
                with progress_lock:
                    completed += 1
                return ts_code, 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_SYNC_WORKERS) as executor:
            futures = [executor.submit(sync_single, code) for code in ts_codes]
            for future in concurrent.futures.as_completed(futures):
                code, count = future.result()
                results[code] = count

        logger.info(f"批量估值指标同步完成，成功 {sum(1 for v in results.values() if v > 0)}/{len(ts_codes)}")
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
                records = []
                for row in df.itertuples(index=False):
                    row_dict = row._asdict()
                    records.append(
                        (
                            row_dict["ts_code"],
                            row_dict["trade_date"],
                            row_dict.get("buy_sm_amount"),
                            row_dict.get("buy_md_amount"),
                            row_dict.get("buy_lg_amount"),
                            row_dict.get("buy_elg_amount"),
                            row_dict.get("sell_sm_amount"),
                            row_dict.get("sell_md_amount"),
                            row_dict.get("sell_lg_amount"),
                            row_dict.get("sell_elg_amount"),
                            row_dict.get("net_mf"),
                            row_dict.get("pct_mf"),
                        )
                    )

                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO moneyflow
                    (ts_code, trade_date, buy_sm_amount, buy_md_amount,
                     buy_lg_amount, buy_elg_amount, sell_sm_amount,
                     sell_md_amount, sell_lg_amount, sell_elg_amount,
                     net_mf, pct_mf)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    records,
                )

            self._log_sync("moneyflow", ts_code, trade_date, "success")
            return len(df)

        except Exception as e:
            logger.error(f"资金流向同步失败 {ts_code} {trade_date}: {e}")
            self._log_sync("moneyflow", ts_code, "", "failed", str(e))
            return 0

    # ==================== 工具方法 ====================

    def get_sync_status(self) -> dict[str, Any]:
        """获取同步状态"""
        with get_connection() as conn:
            cursor = conn.cursor()

            # 各表数据量
            cursor.execute("SELECT COUNT(*) as cnt FROM stock_basic")
            stock_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM daily_kline")
            kline_count = cursor.fetchone()["cnt"]

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
                "sync_status": sync_status,
            }


# ==================== 命令行工具 ====================


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Tushare 数据同步工具")
    parser.add_argument(
        "action",
        choices=["init", "sync", "status", "stk-factor"],
        help="操作: init=初始化数据库, sync=同步数据, status=查看状态, stk-factor=同步Tushare官方指标",
    )
    parser.add_argument("--ts_code", help="股票代码，如 000001.SZ")
    parser.add_argument("--days", type=int, default=730, help="同步天数")
    parser.add_argument("--indicators", action="store_true", help="同步完成后计算并缓存技术指标（indicator_cache 表）")
    parser.add_argument(
        "--skip-indicators",
        action="store_true",
        help="跳过指标缓存同步（默认单只股票自动同步，批量需指定 --indicators）",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    if args.action == "init":
        from .database import init_database

        init_database()
        print("数据库初始化完成")

    elif args.action == "sync":
        syncer = DataSyncer()

        if args.ts_code:
            # 同步单只股票
            syncer.sync_daily_kline(args.ts_code)
            # 单只股票默认同步指标缓存（除非显式跳过）
            if not args.skip_indicators:
                print(f"正在同步指标缓存: {args.ts_code} ...")
                syncer.sync_indicator_cache(args.ts_code, days=args.days)
        else:
            # 批量同步所有股票
            syncer.sync_stock_basic()
            syncer.sync_all_daily_kline(days=args.days)
            # 批量同步指标缓存（需显式指定 --indicators）
            if args.indicators and not args.skip_indicators:
                print("正在批量同步指标缓存...")
                syncer.sync_all_indicators()

        print("同步完成")
        print(syncer.get_sync_status())

    elif args.action == "stk-factor":
        syncer = DataSyncer()

        if args.ts_code:
            print(f"正在同步 Tushare 官方指标: {args.ts_code} ...")
            start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            count = syncer.sync_stk_factor(args.ts_code, start_date=start_date, end_date=end_date)
            print(f"同步完成，{count} 条")
        else:
            print("正在批量同步 Tushare 官方指标...")
            results = syncer.sync_all_stk_factor(days=args.days)
            success = sum(1 for v in results.values() if v > 0)
            print(f"批量同步完成，成功 {success}/{len(results)}")

    elif args.action == "status":
        syncer = DataSyncer()
        status = syncer.get_sync_status()
        print("=" * 50)
        print(f"数据库: {status['db_path']}")
        print(f"股票数量: {status['stock_count']}")
        print(f"K线数据: {status['kline_count']}")
        print("-" * 50)
        print("同步状态:")
        for s in status["sync_status"]:
            print(f"  {s['data_type']}: {s['last_date']} ({s['status']})")


if __name__ == "__main__":
    main()

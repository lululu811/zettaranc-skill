"""Data syncer coordinating batch synchronization, logging and status."""

from __future__ import annotations

import os
import time
import logging
import threading
import concurrent.futures
from datetime import datetime, timedelta
from typing import Any, Optional

from ..database import get_connection, get_db_path
from ..datasource import DataSource, IndevsDataSource, TushareDataSource, get_datasource
from .rate_limiter import _rate_limit_global, _MAX_SYNC_WORKERS
from .indicator_cache import (
    _get_indicator_funcs,
    _compute_day_indicators,
    _build_indicator_row,
    _INDICATOR_INSERT_COLUMNS,
)
from .fetcher import DataFetcher
from modules.core.errors import ErrorCode, ZettarancError

logger = logging.getLogger(__name__)

# 涨跌停阈值（主板 10%，此处用 9.9% 容差）
# 注意：创业板(300xxx)/科创板(688xxx) 实际为 20%，ST 为 5%，
# 新股前 5 日无限制。当前简化处理，v2.11.0 计划按 market 字段动态调整。
_LIMIT_THRESHOLD = 9.9

# 中转 API 配置（从环境变量读取）
TUSHARE_API_URL = os.environ.get("TUSHARE_API_URL", "")
VERIFY_TOKEN_URL = os.environ.get("TUSHARE_VERIFY_TOKEN_URL", "")


class DataSyncer:
    """数据同步器"""

    def __init__(self, token: str | None = None, datasource: DataSource | None = None):
        self.token = token or os.environ.get("TUSHARE_TOKEN")

        # 依赖注入 DataSource；默认按环境变量选择数据源
        if datasource is None:
            data_mode = os.getenv("DATA_MODE", "websearch")
            # 优先 Indevs Replay API
            if os.environ.get("INDEVS_API_KEY"):
                datasource = IndevsDataSource()
            elif data_mode == "jnb":
                if not self.token:
                    raise ZettarancError(
                        ErrorCode.CONFIG_MISSING,
                        "JNB 模式下未设置 TUSHARE_TOKEN，请检查 .env 文件。",
                    )
                if not TUSHARE_API_URL:
                    raise ZettarancError(
                        ErrorCode.CONFIG_MISSING,
                        "JNB 模式下未设置 TUSHARE_API_URL，请在 .env 中配置中转 API 地址。\n"
                        "示例：TUSHARE_API_URL=https://tt.xiaodefa.cn",
                    )
                datasource = TushareDataSource(token=self.token)
            else:
                datasource = TushareDataSource(token=self.token)
        self._datasource = datasource
        self._fetcher = DataFetcher(self._datasource)

        # 向后兼容：保留 instance-level attrs（外部可能引用）
        # 但实际限流走模块级 _GLOBAL_LIMITER
        self.last_request_time: dict[str, float] = {}

    def _rate_limit(self, api_name: str):
        """线程安全的限流控制（v2.10.0 P1-4 改为调模块级 _GLOBAL_LIMITER）"""
        # v2.10.0：原 per-instance lock 改用模块级 multiprocessing 安全限流器
        _rate_limit_global()
        # 保留旧字段更新，便于外部观察（不影响实际限流）
        self.last_request_time[api_name] = time.time()

    def _call_api_with_retry(self, api_name: str, func, *args, **kwargs):
        """带退避算法和限流控制的 API 调用封装"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._rate_limit(api_name)
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                sleep_time = 2**attempt
                logger.warning(
                    f"[{api_name}] API 调用异常: {e}, 等待 {sleep_time} 秒后重试 ({attempt + 1}/{max_retries})"
                )
                time.sleep(sleep_time)

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

    # ==================== 批量同步基础设施 ====================

    def _batch_sync(self, task_name: str, sync_fn, ts_codes: list[str]) -> dict[str, int]:
        """通用批量同步：并发执行 + 进度追踪 + 异常处理

        消除 sync_all_daily_kline / sync_all_indicators / sync_all_stk_factor /
        sync_all_daily_basic 四个方法中的重复模式。

        Args:
            task_name: 任务名称（用于日志，如"日线数据"）
            sync_fn: 同步函数 callable(ts_code) -> count
            ts_codes: 股票代码列表

        Returns:
            dict[ts_code] = count
        """
        results: dict[str, int] = {}
        if not ts_codes:
            return results

        total = len(ts_codes)
        logger.info(f"开始批量同步{task_name}，共 {total} 只股票...")

        progress_lock = threading.Lock()
        completed = 0

        def _worker(ts_code: str) -> tuple[str, int]:
            nonlocal completed
            try:
                count = sync_fn(ts_code)
                with progress_lock:
                    completed += 1
                    if completed % 10 == 0:
                        logger.info(f"进度: {completed}/{total}")
                return ts_code, count
            except Exception as e:
                logger.error(f"{task_name}同步失败 {ts_code}: {e}")
                with progress_lock:
                    completed += 1
                return ts_code, 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_SYNC_WORKERS) as executor:
            futures = [executor.submit(_worker, code) for code in ts_codes]
            for future in concurrent.futures.as_completed(futures):
                code, count = future.result()
                results[code] = count

        success_count = sum(1 for v in results.values() if v > 0)
        logger.info(f"批量{task_name}同步完成，成功 {success_count}/{total}")
        return results

    @staticmethod
    def _fetch_all_codes(query: str) -> list[str]:
        """从数据库查询股票代码列表"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return [row[0] for row in cursor.fetchall()]

    # ==================== 股票基本信息 ====================

    def sync_stock_basic(self) -> int:
        """
        同步股票基本信息
        股票信息基本不变化，每周同步一次即可
        """
        logger.info("开始同步股票基本信息...")
        try:
            df = self._call_api_with_retry(
                "stock_basic",
                self._fetcher.fetch_stock_basic,
            )

            if df is None or len(df) == 0:
                logger.warning("获取股票基本信息失败")
                return 0

            # 选择并填充必要列
            available_cols = [
                c for c in ["ts_code", "name", "area", "industry", "market", "list_date", "is_hs"] if c in df.columns
            ]
            df = df[available_cols].fillna("")
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
            df = self._call_api_with_retry(
                "daily_kline",
                self._fetcher.fetch_daily_kline,
                ts_code,
                start_date,
                end_date,
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
        """批量同步日线数据（并发，含智能跳过）"""
        if ts_codes is None:
            ts_codes = self._fetch_all_codes("SELECT ts_code FROM stock_basic")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        def _sync_one(code: str) -> int:
            # 近2天已同步则跳过
            last_date = self._get_last_date("daily_kline", code)
            if last_date and (datetime.now() - datetime.strptime(last_date, "%Y%m%d")).days < 2:
                return 0
            return self.sync_daily_kline(code, start_date, end_date)

        return self._batch_sync("日线数据", _sync_one, ts_codes)

    # ==================== 指标缓存 ====================

    def sync_indicator_cache(self, ts_code: str, days: int = 120) -> int:
        """同步单只股票技术指标到 indicator_cache 表

        计算流程：
        1. 加载 K 线数据
        2. 预计算 KDJ / MACD 全量序列（O(n)，避免循环内 O(n²)）
        3. 逐日计算指标 → 构建 INSERT 行 → 批量写入
        """
        try:
            f = _get_indicator_funcs()
            klines = f.get_kline_data(ts_code, days)
            if not klines:
                return 0

            # 预计算 O(n) 序列
            kdj_seq = f.precompute_kdj_sequence(klines) if len(klines) >= 9 else None
            if len(klines) >= 30:
                macd_dif_seq, macd_dea_seq, macd_hist_seq = f.precompute_macd_sequence(klines)
            else:
                macd_dif_seq = macd_dea_seq = macd_hist_seq = None

            cols = [c.strip() for c in _INDICATOR_INSERT_COLUMNS.split(",")]
            insert_sql = f"INSERT OR REPLACE INTO indicator_cache ({_INDICATOR_INSERT_COLUMNS}) VALUES ({','.join(['?'] * len(cols))})"

            with get_connection() as conn:
                cursor = conn.cursor()
                for i, kline in enumerate(klines):
                    sub_klines = klines[: i + 1]
                    yesterday = sub_klines[-2] if len(sub_klines) > 1 else None

                    ind = _compute_day_indicators(
                        f,
                        sub_klines,
                        kline,
                        yesterday,
                        kdj_seq,
                        macd_dif_seq,
                        macd_dea_seq,
                        macd_hist_seq,
                        i,
                    )
                    row = _build_indicator_row(ts_code, kline.trade_date, ind)
                    cursor.execute(insert_sql, row)

            self._log_sync("indicator_cache", ts_code, klines[-1].trade_date, "success")
            logger.info(f"指标缓存同步完成: {ts_code}, {len(klines)} 条")
            return len(klines)

        except Exception as e:
            logger.error(f"指标缓存同步失败 {ts_code}: {e}")
            self._log_sync("indicator_cache", ts_code, "", "failed", str(e))
            return 0

    def sync_all_indicators(self, ts_codes: list[str] | None = None) -> dict[str, int]:
        """批量同步指标缓存（并发）"""
        if ts_codes is None:
            ts_codes = self._fetch_all_codes("SELECT DISTINCT ts_code FROM daily_kline")
        return self._batch_sync("指标缓存", self.sync_indicator_cache, ts_codes)

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

            df = self._call_api_with_retry(
                "stk_factor",
                self._fetcher.fetch_stk_factor,
                ts_code,
                start_date,
                end_date,
            )

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
        """批量同步 Tushare 官方指标（并发）"""
        if ts_codes is None:
            ts_codes = self._fetch_all_codes("SELECT ts_code FROM stock_basic")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        return self._batch_sync("Tushare指标", lambda code: self.sync_stk_factor(code, start_date, end_date), ts_codes)

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

            df = self._fetcher.fetch_daily_basic(ts_code, start_date, end_date)

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
        """批量同步每日估值指标（并发）"""
        self.ensure_daily_basic_columns()
        if ts_codes is None:
            ts_codes = self._fetch_all_codes("SELECT DISTINCT ts_code FROM daily_kline ORDER BY ts_code")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        return self._batch_sync("估值指标", lambda code: self.sync_daily_basic(code, start_date, end_date), ts_codes)

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
            df = self._fetcher.fetch_moneyflow(ts_code, trade_date)

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

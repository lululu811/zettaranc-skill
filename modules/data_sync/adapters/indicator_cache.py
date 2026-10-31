"""IndicatorCacheAdapter: 指标缓存同步适配器。

负责 indicator_cache 表的 fetch → compute → upsert 管线。
支持增量同步（只写新增交易日）和预热（长历史避免指标计算失真）。
"""

from __future__ import annotations

import sqlite3
import logging
from typing import Any

from ...database import get_connection
from .._infra import SyncContext
from ..indicator_cache import (
    _get_indicator_funcs,
    _compute_day_indicators,
    _build_indicator_row,
    _INDICATOR_INSERT_COLUMNS,
)

logger = logging.getLogger(__name__)


class IndicatorCacheAdapter:
    """指标缓存同步适配器。

    职责：
    - 加载 K 线数据（含 warmup 预热段）
    - 预计算 KDJ / MACD 全量序列（O(n)，避免循环内 O(n²)）
    - 逐日计算指标 → 构建 INSERT 行 → 批量写入
    - 支持增量同步（只写新增交易日）
    """

    def __init__(self, ctx: SyncContext) -> None:
        self.ctx = ctx

    @staticmethod
    def _get_indicator_last_date(ts_code: str) -> str | None:
        """取 indicator_cache 中该股已缓存指标的最后交易日（增量断点）"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(trade_date) FROM indicator_cache WHERE ts_code = ?", (ts_code,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else None

    def sync_one(
        self,
        ts_code: str,
        days: int = 120,
        warmup: int = 250,
        incremental: bool = False,
    ) -> int:
        """同步单只股票技术指标到 indicator_cache 表。

        Args:
            ts_code: 股票代码
            days: 写回窗口天数（只写最后 days 根）
            warmup: 额外加载但不写回的历史根数。MA60/MA250/MACD 需要预热，
                否则窗口最早几天因历史不足被算坏；设 0 可恢复旧行为
            incremental: True 只写回 trade_date > 已缓存最后日期的行，
                不覆盖此前算好的旧值

        Returns:
            实际写入条数
        """
        try:
            f = _get_indicator_funcs()
            load_days = days + warmup if warmup > 0 else days
            klines = f.get_kline_data(ts_code, load_days)
            if not klines:
                return 0

            # 预热段只参与计算，不写库（避免用不足的历史覆盖旧值）
            write_from = max(0, len(klines) - days) if days > 0 else 0
            last_cached = self._get_indicator_last_date(ts_code) if incremental else None

            # 预计算 O(n) 序列（基于完整加载窗口，含预热）
            kdj_seq = f.precompute_kdj_sequence(klines) if len(klines) >= 9 else None
            if len(klines) >= 30:
                macd_dif_seq, macd_dea_seq, macd_hist_seq = f.precompute_macd_sequence(klines)
            else:
                macd_dif_seq = macd_dea_seq = macd_hist_seq = None

            cols = [c.strip() for c in _INDICATOR_INSERT_COLUMNS.split(",")]
            insert_sql = f"INSERT OR REPLACE INTO indicator_cache ({_INDICATOR_INSERT_COLUMNS}) VALUES ({','.join(['?'] * len(cols))})"

            written = 0
            with get_connection() as conn:
                cursor = conn.cursor()
                for i in range(write_from, len(klines)):
                    kline = klines[i]
                    if last_cached and kline.trade_date <= last_cached:
                        continue  # 已算过：跳过，保留此前用完整历史算出的值

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
                    written += 1

            self.ctx.log_sync("indicator_cache", ts_code, klines[-1].trade_date, "success")
            logger.info(f"指标缓存同步完成: {ts_code}, 写入 {written} 条")
            return written

        except (sqlite3.Error, ValueError, KeyError, OSError) as e:
            logger.error(f"指标缓存同步失败 {ts_code}: {e}")
            self.ctx.log_sync("indicator_cache", ts_code, "", "failed", str(e))
            return 0

    def sync_batch(
        self,
        ts_codes: list[str] | None = None,
        days: int = 120,
        warmup: int = 250,
        incremental: bool = False,
        **kwargs: Any,
    ) -> dict[str, int]:
        """批量同步指标缓存（并发）。

        Args:
            ts_codes: 股票代码列表，None = daily_kline 中全部代码
            days: 写回窗口天数
            warmup: 额外加载用于预热、不写回的历史根数
            incremental: True 只写回新增交易日，不覆盖已算好的旧值
        """
        if ts_codes is None:
            ts_codes = self.ctx.fetch_all_codes("SELECT DISTINCT ts_code FROM daily_kline")

        def _sync_one(code: str) -> int:
            return self.sync_one(code, days=days, warmup=warmup, incremental=incremental)

        return self.ctx.batch_sync("指标缓存", _sync_one, ts_codes)

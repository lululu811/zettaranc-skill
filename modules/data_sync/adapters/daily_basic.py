"""DailyBasicAdapter: 每日估值指标同步适配器。

负责 daily_kline 表中估值列（PE/PB/PS/市值等）的 UPDATE 管线。
注意：与 DailyKlineAdapter 共享 daily_kline 表，但只更新估值列。
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Any, cast

from ...database import get_connection
from .._infra import SyncContext

logger = logging.getLogger(__name__)

UPDATE_SQL = """
    UPDATE daily_kline SET
        pe = ?, pe_ttm = ?, pb = ?, ps = ?, ps_ttm = ?,
        total_mv = ?, circ_mv = ?
    WHERE ts_code = ? AND trade_date = ?
"""


class DailyBasicAdapter:
    """每日估值指标同步适配器。

    职责：
    - 从 DataSource 拉取 daily_basic 数据
    - UPDATE 写入 daily_kline 表的估值列
    - 确保表结构包含所需列（ensure_columns）

    注意：与 DailyKlineAdapter 共享 daily_kline 表。
    兼容约定：UPSERT 不覆盖估值列，UPDATE 不覆盖行情列。
    """

    def __init__(self, ctx: SyncContext) -> None:
        self.ctx = ctx

    def ensure_columns(self) -> None:
        """确保 daily_kline 表包含 PE/PB/PS/总市值/流通市值 列。"""
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

    def sync_one(
        self,
        ts_code: str,
        start_date: str = "",
        end_date: str = "",
    ) -> int:
        """同步单只股票的每日估值指标。

        Args:
            ts_code: 股票代码
            start_date: 起始日期 YYYYMMDD，默认 2 年前
            end_date: 结束日期 YYYYMMDD，默认今天

        Returns:
            更新条数
        """
        try:
            self.ensure_columns()
            self.ctx.rate_limit("daily_basic")

            if not start_date:
                start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")

            df = self.ctx.fetcher.fetch_daily_basic(ts_code, start_date, end_date)

            if df is None or len(df) == 0:
                return 0

            with get_connection() as conn:
                cursor = conn.cursor()
                for row in df.itertuples(index=False):
                    row_dict = cast("Any", row)._asdict()
                    cursor.execute(
                        UPDATE_SQL,
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

            self.ctx.log_sync("daily_basic", ts_code, end_date, "success")
            return len(df)

        except (sqlite3.Error, ValueError, KeyError, OSError) as e:
            logger.error(f"每日估值指标同步失败 {ts_code}: {e}")
            self.ctx.log_sync("daily_basic", ts_code, "", "failed", str(e))
            return 0

    def sync_batch(
        self,
        ts_codes: list[str] | None = None,
        days: int = 730,
        **kwargs: Any,
    ) -> dict[str, int]:
        """批量同步每日估值指标（并发）。"""
        self.ensure_columns()
        if ts_codes is None:
            ts_codes = self.ctx.fetch_all_codes("SELECT DISTINCT ts_code FROM daily_kline ORDER BY ts_code")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        return self.ctx.batch_sync(
            "估值指标",
            lambda code: self.sync_one(code, start_date, end_date),
            ts_codes,
        )

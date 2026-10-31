"""StkFactorAdapter: Tushare 官方技术指标同步适配器。

负责 tushare_indicator_cache 表的 fetch → transform → upsert 管线。
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Any, cast

from ...database import get_connection
from .._infra import SyncContext

logger = logging.getLogger(__name__)

# 字段映射：Tushare 字段名 -> 数据库字段名
FIELD_MAP = {
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

UPSERT_SQL = """
    INSERT OR REPLACE INTO tushare_indicator_cache
    (ts_code, trade_date, close, macd_dif, macd_dea, macd,
     kdj_k, kdj_d, kdj_j, rsi_6, rsi_12, rsi_24,
     boll_upper, boll_mid, boll_lower, cci)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def build_upsert_records(df: Any) -> list[tuple[Any, ...]]:
    """从 DataFrame 构建 UPSERT 记录列表。纯函数，可独立测试。"""
    records: list[tuple[Any, ...]] = []
    for row in df.itertuples(index=False):
        row_dict = cast("Any", row)._asdict()
        values = tuple(row_dict.get(FIELD_MAP.get(k, k), 0) for k in FIELD_MAP.keys())
        records.append(values)
    return records


class StkFactorAdapter:
    """Tushare 官方技术指标同步适配器。

    职责：
    - 从 DataSource 拉取 stk_factor 数据
    - 字段映射 + UPSERT 写入 tushare_indicator_cache 表
    """

    def __init__(self, ctx: SyncContext) -> None:
        self.ctx = ctx

    def sync_one(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """同步单只股票的 Tushare 官方技术指标。

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

            df = self.ctx.call_api_with_retry(
                "stk_factor",
                self.ctx.fetcher.fetch_stk_factor,
                ts_code,
                start_date,
                end_date,
            )

            if df is None or len(df) == 0:
                return 0

            records = build_upsert_records(df)

            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(UPSERT_SQL, records)

            latest_date = df["trade_date"].max()
            self.ctx.log_sync("stk_factor", ts_code, latest_date, "success")
            logger.info(f"Tushare 指标同步完成: {ts_code}, {len(df)} 条")
            return len(df)

        except (sqlite3.Error, ValueError, KeyError, OSError) as e:
            logger.error(f"Tushare 指标同步失败 {ts_code}: {e}")
            self.ctx.log_sync("stk_factor", ts_code, "", "failed", str(e))
            return 0

    def sync_batch(
        self,
        ts_codes: list[str] | None = None,
        days: int = 365,
        **kwargs: Any,
    ) -> dict[str, int]:
        """批量同步 Tushare 官方指标（并发）。"""
        if ts_codes is None:
            ts_codes = self.ctx.fetch_all_codes("SELECT ts_code FROM stock_basic")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        return self.ctx.batch_sync(
            "Tushare指标",
            lambda code: self.sync_one(code, start_date, end_date),
            ts_codes,
        )

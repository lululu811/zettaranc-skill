"""MoneyflowAdapter: 资金流向同步适配器。

负责 moneyflow 表的 fetch → transform → upsert 管线。
"""

from __future__ import annotations

import sqlite3
import logging
from typing import Any, cast

from ...database import get_connection
from .._infra import SyncContext

logger = logging.getLogger(__name__)

UPSERT_SQL = """
    INSERT OR REPLACE INTO moneyflow
    (ts_code, trade_date, buy_sm_amount, buy_md_amount,
     buy_lg_amount, buy_elg_amount, sell_sm_amount,
     sell_md_amount, sell_lg_amount, sell_elg_amount,
     net_mf, pct_mf)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def build_upsert_records(df: Any) -> list[tuple]:
    """从 DataFrame 构建 UPSERT 记录列表。纯函数，可独立测试。"""
    records = []
    for row in df.itertuples(index=False):
        row_dict = cast("Any", row)._asdict()
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
                # 三个数据源统一输出 tushare 官方列名 net_mf_amount/net_mf_rate；
                # 兼容旧 net_mf/pct_mf 命名
                (
                    row_dict.get("net_mf_amount")
                    if row_dict.get("net_mf_amount") is not None
                    else row_dict.get("net_mf")
                ),
                (
                    row_dict.get("net_mf_rate")
                    if row_dict.get("net_mf_rate") is not None
                    else row_dict.get("pct_mf")
                ),
            )
        )
    return records


class MoneyflowAdapter:
    """资金流向同步适配器。

    职责：
    - 从 DataSource 拉取资金流向数据
    - UPSERT 写入 moneyflow 表
    """

    def __init__(self, ctx: SyncContext) -> None:
        self.ctx = ctx

    def sync_one(self, ts_code: str, trade_date: str) -> int:
        """同步单只股票的单日资金流向。

        Args:
            ts_code: 股票代码
            trade_date: 交易日期，格式 YYYYMMDD

        Returns:
            更新条数
        """
        try:
            self.ctx.rate_limit("moneyflow")
            df = self.ctx.fetcher.fetch_moneyflow(ts_code, trade_date)

            if df is None or len(df) == 0:
                return 0

            records = build_upsert_records(df)

            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(UPSERT_SQL, records)

            self.ctx.log_sync("moneyflow", ts_code, trade_date, "success")
            return len(df)

        except (sqlite3.Error, ValueError, KeyError, OSError) as e:
            logger.error(f"资金流向同步失败 {ts_code} {trade_date}: {e}")
            self.ctx.log_sync("moneyflow", ts_code, "", "failed", str(e))
            return 0

    def sync_batch(self, ts_codes: list[str] | None = None, **kwargs: Any) -> dict[str, int]:
        """批量同步（资金流向无批量接口，返回空 dict）。"""
        return {}

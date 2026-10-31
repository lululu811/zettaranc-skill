"""StockBasicAdapter: 股票基本信息同步适配器。

负责 stock_basic 表的 fetch → append 管线。
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime

from ...database import get_connection
from .._infra import SyncContext

logger = logging.getLogger(__name__)


class StockBasicAdapter:
    """股票基本信息同步适配器。

    职责：
    - 从 DataSource 拉取股票基本信息
    - append 写入 stock_basic 表
    """

    def __init__(self, ctx: SyncContext) -> None:
        self.ctx = ctx

    def sync_one(self) -> int:
        """同步股票基本信息（全量，无 ts_code 参数）。

        股票信息基本不变化，每周同步一次即可。

        Returns:
            写入条数
        """
        logger.info("开始同步股票基本信息...")
        try:
            df = self.ctx.call_api_with_retry(
                "stock_basic",
                self.ctx.fetcher.fetch_stock_basic,
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

            self.ctx.log_sync("stock_basic", None, datetime.now().strftime("%Y%m%d"), "success")
            logger.info(f"股票基本信息同步完成，共 {len(df)} 只")
            return len(df)

        except (sqlite3.Error, ValueError, KeyError, OSError) as e:
            logger.error(f"股票基本信息同步失败: {e}")
            self.ctx.log_sync("stock_basic", None, "", "failed", str(e))
            return 0

    def sync_batch(self, ts_codes: list[str] | None = None, **kwargs) -> dict[str, int]:
        """批量同步（stock_basic 无批量概念，返回空 dict）。"""
        return {}

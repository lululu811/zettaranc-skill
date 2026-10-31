"""DailyKlineAdapter: 日线 K 线数据同步适配器。

负责 daily_kline 表的 fetch → transform → upsert 管线。
支持增量同步（从最后一根 K 线续拉）和全量同步。
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Any, cast

from ...database import get_connection
from .._infra import SyncContext

logger = logging.getLogger(__name__)

# 涨跌停阈值（主板 10%，此处用 9.9% 容差）
# 注意：创业板(300xxx)/科创板(688xxx) 实际为 20%，ST 为 5%，
# 新股前 5 日无限制。当前简化处理，v2.11.0 计划按 market 字段动态调整。
_LIMIT_THRESHOLD = 9.9

# UPSERT SQL：只更新行情列，保留估值列（pe/pb/total_mv 等）
# 这是与 sync_daily_basic 的兼容约定：两者都操作 daily_kline 表，
# UPSERT 不覆盖估值列，UPDATE 不覆盖行情列。
UPSERT_SQL = """
    INSERT INTO daily_kline
    (ts_code, trade_date, open, high, low, close, vol, amount,
     pct_chg, vol_ratio, is_limit_up, is_limit_down)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(ts_code, trade_date) DO UPDATE SET
        open=excluded.open,
        high=excluded.high,
        low=excluded.low,
        close=excluded.close,
        vol=excluded.vol,
        amount=excluded.amount,
        pct_chg=excluded.pct_chg,
        is_limit_up=excluded.is_limit_up,
        is_limit_down=excluded.is_limit_down
"""


def build_upsert_records(df: Any) -> list[tuple]:
    """从 DataFrame 构建 UPSERT 记录列表。

    纯函数，无 DB 依赖，可独立测试。

    Args:
        df: fetch_daily_kline 返回的 DataFrame

    Returns:
        list of tuples，每个 tuple 对应一条 K 线记录
    """
    records = []
    for row in df.itertuples(index=False):
        row_dict = cast("Any", row)._asdict()
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
                1 if row_dict.get("pct_chg", 0) >= _LIMIT_THRESHOLD else 0,  # is_limit_up
                1 if row_dict.get("pct_chg", 0) <= -_LIMIT_THRESHOLD else 0,  # is_limit_down
            )
        )
    return records


class DailyKlineAdapter:
    """日线 K 线数据同步适配器。

    职责：
    - 从 DataSource 拉取日 K 线数据
    - 计算涨跌停标记
    - UPSERT 写入 daily_kline 表（保留估值列）
    - 支持增量同步（从最后一根 K 线续拉）
    """

    def __init__(self, ctx: SyncContext) -> None:
        """初始化适配器。

        Args:
            ctx: 共享基础设施容器
        """
        self.ctx = ctx

    @staticmethod
    def get_kline_last_date(ts_code: str) -> str | None:
        """取 daily_kline 中该股实际最后一根 K 线的交易日。

        与 SyncContext.get_last_date 的区别：后者读 sync_log（可能因失败/清库而缺失），
        这里以库里真实数据为准，作为增量续拉的断点。
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(trade_date) FROM daily_kline WHERE ts_code = ?", (ts_code,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else None

    def sync_one(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """同步单只股票的日线数据（增量更新）。

        Args:
            ts_code: 股票代码，如 '000001.SZ'
            start_date: 开始日期，格式 YYYYMMDD，None 表示从数据库最后一条开始
            end_date: 结束日期，格式 YYYYMMDD，None 表示到最新

        Returns:
            更新条数
        """
        # 增量更新：获取最后同步日期
        if start_date is None:
            last_date = self.ctx.get_last_date("daily_kline", ts_code)
            if last_date:
                last_dt = datetime.strptime(last_date, "%Y%m%d")
                start_date = (last_dt + timedelta(days=1)).strftime("%Y%m%d")

        # 默认从2年前开始
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        try:
            df = self.ctx.call_api_with_retry(
                "daily_kline",
                self.ctx.fetcher.fetch_daily_kline,
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

            # 更新同步日志
            latest_date = df["trade_date"].max()
            self.ctx.log_sync("daily_kline", ts_code, latest_date, "success")

            logger.info(f"日线数据同步完成: {ts_code}, {len(df)} 条, {start_date}-{latest_date}")
            return len(df)

        except (sqlite3.Error, ValueError, KeyError, OSError) as e:
            logger.error(f"日线数据同步失败 {ts_code}: {e}")
            self.ctx.log_sync("daily_kline", ts_code, "", "failed", str(e))
            return 0

    def sync_batch(
        self,
        ts_codes: list[str] | None = None,
        days: int = 730,
        incremental: bool = False,
    ) -> dict[str, int]:
        """批量同步日线数据（并发）。

        Args:
            ts_codes: 股票代码列表，None = 全市场（stock_basic）
            days: 回溯窗口天数
            incremental: False（默认）落后超 2 天的股票按 days 窗口整段重拉；
                True 严格增量，每只股票从其最后一根 K 线的下一天续拉，
                只有库里完全没有数据的股票才回落到 days 窗口

        Returns:
            dict[ts_code] = 更新条数（0 表示无需更新/停牌/失败）
        """
        if ts_codes is None:
            ts_codes = self.ctx.fetch_all_codes("SELECT ts_code FROM stock_basic")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        def _sync_one(code: str) -> int:
            if incremental:
                last_date = self.get_kline_last_date(code)
                if last_date is None:
                    # 新股 / 从未同步：无断点可续，回落到 days 窗口
                    return self.sync_one(code, start_date, end_date)
                next_date = (datetime.strptime(last_date, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
                if next_date > end_date:
                    return 0  # 已同步到最新，不发请求
                return self.sync_one(code, next_date, end_date)

            # 非增量：近2天已同步则跳过，否则整段重拉窗口
            last_date = self.ctx.get_last_date("daily_kline", code)
            if last_date and (datetime.now() - datetime.strptime(last_date, "%Y%m%d")).days < 2:
                return 0
            return self.sync_one(code, start_date, end_date)

        return self.ctx.batch_sync("日线数据", _sync_one, ts_codes)

    def sync_missing(self, ts_codes: list[str], days: int = 730) -> dict[str, int]:
        """同步 ts_codes 中"在 daily_kline 表里完全缺失"的股票（增量补齐）。

        与 sync_batch 的区别：
        - sync_batch：所有 ts_codes 都同步（已有的会跳过早于 2 天的部分）
        - sync_missing：只在 daily_kline 表里完全没有数据的才同步

        用于"自选股清单第一次接入"或"补齐漏掉的股票"场景。

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
            count = self.sync_one(code, start_date=start_date)
            results[code] = count
        return results

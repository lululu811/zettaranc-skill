"""DataSyncer: 数据同步编排器（Orchestrator）。

职责：
1. 构造 DataSource / DataFetcher / SyncContext
2. 创建并持有 6 个 adapter 实例
3. 委托调用，不包含任何 SQL 或业务逻辑

各数据类型的同步逻辑已拆分到 adapters/ 目录：
- StockBasicAdapter: stock_basic 表
- DailyKlineAdapter: daily_kline 表（行情列）
- IndicatorCacheAdapter: indicator_cache 表
- StkFactorAdapter: tushare_indicator_cache 表
- DailyBasicAdapter: daily_kline 表（估值列）
- MoneyflowAdapter: moneyflow 表

共享基础设施在 _infra.py（SyncContext 容器）。
"""

from __future__ import annotations

import os
import logging
from typing import Any

from modules.core.errors import ZettarancError

from ..database import get_connection, get_db_path
from ..datasource import (
    AStockDataDataSource,
    DataSource,
    HithinkFinanceDataSource,
    IndevsDataSource,
    TushareDataSource,
)
from ..datasource_resolution import ProviderResolution, resolve_provider
from .fetcher import DataFetcher
from ._infra import SyncContext
from .adapters import (
    DailyKlineAdapter,
    StockBasicAdapter,
    IndicatorCacheAdapter,
    StkFactorAdapter,
    DailyBasicAdapter,
    MoneyflowAdapter,
)

# 向后兼容：测试可能从 syncer 导入这些符号
from .indicator_cache import (
    _INDICATOR_INSERT_COLUMNS,
    _build_indicator_row,
    _compute_day_indicators,
    _get_indicator_funcs,
)

logger = logging.getLogger(__name__)


def _build_resolved_source(resolution: ProviderResolution, token: str | None) -> DataSource:
    """按决议结果构造默认数据源；构造失败时回退免费源。"""
    if resolution.provider == "hithink":
        return HithinkFinanceDataSource()
    if resolution.provider == "indevs":
        return IndevsDataSource()
    if resolution.provider == "tushare":
        try:
            return TushareDataSource(token=token)
        except ZettarancError as e:
            logger.warning("[datasyncer] tushare 配置不完整(%s)，回退 a-stock-data", e)
            return AStockDataDataSource()
    return AStockDataDataSource()


class DataSyncer:
    """数据同步编排器。

    向后兼容：保留所有原方法名作为委托，外部调用方无需改动。
    """

    def __init__(self, token: str | None = None, datasource: DataSource | None = None) -> None:
        from ..tushare_client import current_token

        self.token = token or current_token()

        # 依赖注入 DataSource
        if datasource is None:
            if token is not None:
                datasource = TushareDataSource(token=self.token)
            else:
                resolution = resolve_provider()
                datasource = _build_resolved_source(resolution, self.token)
                logger.info("[datasyncer] 数据源决议：%s", resolution.describe())
        self._datasource = datasource
        self._fetcher = DataFetcher(self._datasource)

        # 构造共享基础设施容器
        self._ctx = SyncContext(self._fetcher)

        # 构造 6 个 adapter
        self.stock_basic = StockBasicAdapter(self._ctx)
        self.daily_kline = DailyKlineAdapter(self._ctx)
        self.indicator_cache = IndicatorCacheAdapter(self._ctx)
        self.stk_factor = StkFactorAdapter(self._ctx)
        self.daily_basic = DailyBasicAdapter(self._ctx)
        self.moneyflow = MoneyflowAdapter(self._ctx)

    # ==================== 向后兼容的委托方法 ====================

    def sync_stock_basic(self) -> int:
        """同步股票基本信息。"""
        return self.stock_basic.sync_one()

    def sync_daily_kline(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> int:
        """同步单只股票的日线数据。"""
        return self.daily_kline.sync_one(ts_code, start_date, end_date)

    def sync_all_daily_kline(
        self,
        ts_codes: list[str] | None = None,
        days: int = 730,
        incremental: bool = False,
    ) -> dict[str, int]:
        """批量同步日线数据（并发）。"""
        return self.daily_kline.sync_batch(ts_codes, days, incremental)

    def sync_missing(self, ts_codes: list[str], days: int = 730) -> dict[str, int]:
        """同步完全缺失的股票。"""
        return self.daily_kline.sync_missing(ts_codes, days)

    def sync_indicator_cache(
        self,
        ts_code: str,
        days: int = 120,
        warmup: int = 250,
        incremental: bool = False,
    ) -> int:
        """同步单只股票指标缓存。"""
        return self.indicator_cache.sync_one(ts_code, days, warmup, incremental)

    def sync_all_indicators(
        self,
        ts_codes: list[str] | None = None,
        days: int = 120,
        warmup: int = 250,
        incremental: bool = False,
    ) -> dict[str, int]:
        """批量同步指标缓存。"""
        return self.indicator_cache.sync_batch(ts_codes, days, warmup, incremental)

    def sync_daily_and_compute(
        self,
        ts_codes: list[str] | None = None,
        days: int = 730,
        incremental: bool = False,
    ) -> dict[str, int]:
        """一站式：同步日线 K 线 + 同步指标缓存。"""
        kline_results = self.sync_all_daily_kline(ts_codes=ts_codes, days=days, incremental=incremental)
        # 同步哪些股票有数据，传给指标计算
        if ts_codes is None:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT ts_code FROM daily_kline")
                ts_codes_for_indic = [row["ts_code"] for row in cursor.fetchall()]
        else:
            ts_codes_for_indic = [c for c, n in kline_results.items() if n > 0]
        return self.sync_all_indicators(ts_codes=ts_codes_for_indic or None)

    def sync_stk_factor(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> int:
        """同步单只股票的 Tushare 官方技术指标。"""
        return self.stk_factor.sync_one(ts_code, start_date, end_date)

    def sync_all_stk_factor(self, ts_codes: list[str] | None = None, days: int = 365) -> dict[str, int]:
        """批量同步 Tushare 官方指标。"""
        return self.stk_factor.sync_batch(ts_codes, days)

    def ensure_daily_basic_columns(self) -> None:
        """确保 daily_kline 表包含估值列。"""
        self.daily_basic.ensure_columns()

    def sync_daily_basic(self, ts_code: str, start_date: str = "", end_date: str = "") -> int:
        """同步单只股票的每日估值指标。"""
        return self.daily_basic.sync_one(ts_code, start_date, end_date)

    def sync_all_daily_basic(self, ts_codes: list[str] | None = None, days: int = 730) -> dict[str, int]:
        """批量同步每日估值指标。"""
        return self.daily_basic.sync_batch(ts_codes, days)

    def sync_moneyflow(self, ts_code: str, trade_date: str) -> int:
        """同步单只股票的单日资金流向。"""
        return self.moneyflow.sync_one(ts_code, trade_date)

    # ==================== 向后兼容的内部方法委托 ====================
    # 这些方法已移到 SyncContext，但测试可能直接调用

    def _rate_limit(self, api_name: str) -> None:
        """限流控制（委托到 SyncContext）。"""
        self._ctx.rate_limit(api_name)

    def _call_api_with_retry(self, api_name: str, func: Any, *args: Any, **kwargs: Any) -> Any:
        """带退避算法和限流控制的 API 调用封装。

        注意：为保持测试兼容，这里使用 self._rate_limit 而非 self._ctx.rate_limit，
        以便测试可以 mock syncer._rate_limit。
        """
        import time

        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._rate_limit(api_name)
                return func(*args, **kwargs)
            except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError, KeyError) as e:
                if attempt == max_retries - 1:
                    raise
                sleep_time = 2**attempt
                logger.warning(
                    f"[{api_name}] API 调用异常: {e}, 等待 {sleep_time} 秒后重试 ({attempt + 1}/{max_retries})"
                )
                time.sleep(sleep_time)
        return None  # unreachable

    def _batch_sync(self, task_name: str, sync_fn: Any, ts_codes: list[str]) -> dict[str, int]:
        """通用批量同步（委托到 SyncContext）。"""
        return self._ctx.batch_sync(task_name, sync_fn, ts_codes)

    @staticmethod
    def _fetch_all_codes(query: str) -> list[str]:
        """从数据库查询股票代码列表（委托到 SyncContext）。"""
        return SyncContext.fetch_all_codes(query)

    # ==================== 工具方法 ====================

    def get_sync_status(self) -> dict[str, Any]:
        """获取同步状态。"""
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as cnt FROM stock_basic")
            stock_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM daily_kline")
            kline_count = cursor.fetchone()["cnt"]

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

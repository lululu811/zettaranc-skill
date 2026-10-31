"""共享基础设施：SyncContext 容器 + 公共工具函数。

将原 DataSyncer 中的 _call_api_with_retry / _log_sync / _get_last_date /
_batch_sync / _fetch_all_codes 集中到这里，供各 adapter 注入使用。

设计意图：让每种数据类型的 adapter 可以独立实例化、独立测试，
不需要构造完整 DataSyncer（含 DataSource 注入、token 解析等）。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import logging
import concurrent.futures
from datetime import datetime
from typing import Any

from ..database import get_connection
from .rate_limiter import _rate_limit_global, _MAX_SYNC_WORKERS

logger = logging.getLogger(__name__)


class SyncContext:
    """共享基础设施容器，注入给每个 adapter。

    把原 DataSyncer 中的共享方法集中到这里：
    - call_api_with_retry: 带退避和限流的 API 调用
    - log_sync / get_last_date: 同步日志读写
    - batch_sync: 并发批量执行框架
    - fetch_all_codes: 从 DB 查代码列表
    """

    def __init__(self, fetcher: Any) -> None:
        """初始化 SyncContext。

        Args:
            fetcher: DataFetcher 实例，封装 raw data pulling
        """
        self.fetcher = fetcher
        # 向后兼容：保留 instance-level attrs（外部可能引用）
        self.last_request_time: dict[str, float] = {}

    def rate_limit(self, api_name: str) -> None:
        """线程安全的限流控制（调模块级 _GLOBAL_LIMITER）"""
        _rate_limit_global()
        self.last_request_time[api_name] = time.time()

    def call_api_with_retry(self, api_name: str, func: Any, *args: Any, **kwargs: Any) -> Any:
        """带退避算法和限流控制的 API 调用封装"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.rate_limit(api_name)
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

    def log_sync(
        self, data_type: str, ts_code: str | None, last_date: str, status: str, message: str = ""
    ) -> None:
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

    def get_last_date(self, data_type: str, ts_code: str | None = None) -> str | None:
        """获取最后同步日期（从 sync_log 表）"""
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

    def batch_sync(
        self, task_name: str, sync_fn: Any, ts_codes: list[str]
    ) -> dict[str, int]:
        """通用批量同步：并发执行 + 进度追踪 + 异常处理

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
            except (sqlite3.Error, RuntimeError, ValueError, KeyError, OSError) as e:
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
    def fetch_all_codes(query: str) -> list[str]:
        """从数据库查询股票代码列表"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return [row[0] for row in cursor.fetchall()]

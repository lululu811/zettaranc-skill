"""请求速率限制的公共实现 —— 所有数据源客户端共用。

仓库里此前有 6 处限流实现，各自为政：

- 4 个客户端各抄了一份**完全相同**的"最小间隔 sleep"逻辑，参数不同：
  tushare 0.55s / indevs 0.5s / a-stock-data 0.5s / hithink 0.25s
- syncer 用一份 60s 滑动窗口 + 多进程锁（只读 ``TUSHARE_RPM``）

两种算法语义不同（间隔 vs 窗口），都保留，但**实现只此一处**。调用方只声明
自己的策略参数，不再各写一份 sleep 逻辑。
"""

from __future__ import annotations

import collections
import logging
import multiprocessing
import os
import time

from ..constants import RATE_LIMITER_WINDOW_BUFFER_S

logger = logging.getLogger(__name__)


def wait_min_interval(min_interval: float, last_request_time: float) -> float:
    """最小间隔限流：等到距上次请求至少间隔 ``min_interval`` 秒。

    这是 4 个数据源客户端（tushare / indevs / a-stock-data / hithink）此前
    各自抄了一份的同一段逻辑。

    Args:
        min_interval: 相邻两次请求的最小间隔秒数（<= 0 表示不限流）。
        last_request_time: 上次请求的时间戳（``time.time()`` 口径）。

    Returns:
        本次请求的时间戳——调用方应把它存回自己的 ``last_request_time``。
    """
    now = time.time()
    elapsed = now - last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
        now = time.time()
    return now


class WindowRateLimiter:
    """Tushare 限流器（多进程安全 + 滑动窗口 token bucket）

    设计：
    - 60s 滑动窗口内的请求计数（in-memory deque）
    - multiprocessing.Lock 序列化 critical section
    - ``TUSHARE_RPM`` env var 控制 max requests/min（默认 180，留 20 缓冲应对 200 上限）

    用法：
        limiter.wait()  # 阻塞直到安全可调
    """

    def __init__(self, max_per_min: int = 180) -> None:
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
                sleep_for = 60 - (now - self._window[0]) + RATE_LIMITER_WINDOW_BUFFER_S  # 缓冲秒数
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


def make_window_limiter(max_per_min: int | None = None) -> WindowRateLimiter:
    """按 ``TUSHARE_RPM``（默认 180）构造滑动窗口限流器。"""
    if max_per_min is None:
        max_per_min = int(os.environ.get("TUSHARE_RPM", "180"))
    return WindowRateLimiter(max_per_min=max_per_min)


__all__ = [
    "WindowRateLimiter",
    "make_window_limiter",
    "wait_min_interval",
]

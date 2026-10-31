"""数据同步的限流基础设施。

限流算法本身在 :mod:`modules.core.rate_limit`（公共实现）；本 module 只保留
同步专用的单例与入口：

- ``_GLOBAL_LIMITER`` —— 模块级滑动窗口限流器（多进程安全）
- ``_rate_limit_global()`` —— 模块级公开限流入口
- ``_RateLimiter`` —— :class:`modules.core.rate_limit.WindowRateLimiter` 的别名
"""

import logging

from ..core.rate_limit import WindowRateLimiter, make_window_limiter
from ..core.rate_limit import wait_min_interval  # noqa: F401  re-export：公共限流原语

logger = logging.getLogger(__name__)

# 并发同步线程数（4 个 sync_* 方法共用）
_MAX_SYNC_WORKERS = 5

# 模块级单例（v2.10.0 P1-4 替代原 instance-level _rate_limit_lock）
_RateLimiter = WindowRateLimiter
_GLOBAL_LIMITER = make_window_limiter()


def _rate_limit_global() -> None:
    """模块级公开限流入口（v2.10.0 P1-4 新增，替代 instance-level _rate_limit）"""
    _GLOBAL_LIMITER.wait()

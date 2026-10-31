"""API 错误映射 —— 路由层统一的异常出口。

此前 10 个路由文件里散落着 25 处 ``except Exception → HTTPException(500)``，
把 :mod:`modules.core.errors` 里 50+ 个 ``ErrorCode`` 全部压成一句
``detail="回测失败: ..."``——宿主既拿不到错误码，也无法区分"参数非法"（4xx）
和"数据库挂了"（5xx）。

现在：

- ``ZettarancError`` **不被路由捕获**，直接冒泡到 ``api/main.py`` 的全局处理器，
  由它按错误码映射 HTTP 状态码并输出统一外壳；
- 其他异常由路由层的 :func:`raise_api_error` 统一包装，不再各写一遍。
"""

from __future__ import annotations

from fastapi import HTTPException

from modules.core.command_result import exception_to_dict, http_status_for
from modules.core.errors import ZettarancError

__all__ = ["ApiError", "raise_api_error", "http_exception_for"]


class ApiError(Exception):
    """API 层异常 —— 携带统一外壳与 HTTP 状态码。

    与 ``HTTPException`` 的区别：FastAPI 会把 ``HTTPException.detail`` 包进
    ``{"detail": ...}``，于是响应体变成 ``{"detail": {"ok": false, ...}}``——
    与 CLI 的扁平外壳 ``{"ok": false, ...}`` 形状不同，宿主要写两套解析。
    ``ApiError`` 由 ``api/main.py`` 的处理器直接输出扁平外壳。
    """

    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self.payload = payload
        super().__init__(payload.get("message", ""))


def http_exception_for(exc: BaseException, *, prefix: str = "") -> ApiError:
    """把异常映射成带结构化外壳的 ``ApiError``。

    ``payload`` 是统一外壳 dict（``ok`` / ``error_code`` / ``message`` / ``cause``），
    状态码按错误码判定：客户端错误 4xx、资源不存在 404、其余 5xx。
    """
    payload = exception_to_dict(exc)
    if prefix:
        payload = {**payload, "message": f"{prefix}: {payload['message']}"}
    return ApiError(status_code=http_status_for(exc), payload=payload)


def raise_api_error(exc: BaseException, *, prefix: str = "") -> None:
    """把异常转成 ``ApiError`` 抛出。

    ``ZettarancError`` 的 message **原样保留**（不加前缀）——它已经是人类可读的
    具体原因（如 "days 必须 > 0，当前: 0"），再加一层 "回测失败: " 会让 CLI 与 API
    的 ``message`` 字段长得不一样，破坏"同一形状"的目标。

    其他异常（没有结构化 message）才加前缀，补上宿主读得懂的上下文。
    """
    raise http_exception_for(exc, prefix="" if isinstance(exc, ZettarancError) else prefix) from exc

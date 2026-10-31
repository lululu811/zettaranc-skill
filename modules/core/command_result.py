"""命令结果外壳 —— CLI ``--json`` 与 Web API 的统一错误映射。

此前每条命令各造 JSON 形状，结构化错误系统（:mod:`modules.core.errors`）存在却
几乎无人调用：

- ``cli.py`` 顶层只 ``print(str(e), file=sys.stderr)`` 就退出——``--json`` 时
  **stdout 完全为空**，宿主的 JSON 解析直接失败，也拿不到 ``ErrorCode``；
- ``api/main.py`` 的全局兜底返回 ``{"error": "internal_error"}``，把 50+ 个
  ``ErrorCode`` 压成一句话。

**成功路径的 JSON 形状保持各命令原样**（裸 list / ``{"success": …}`` /
``asdict()`` 裸结构…）——那是各命令的既有契约，改动会破坏所有宿主。
**只有错误路径统一**：无论 CLI 还是 API，都产出同一个外壳，宿主可按
``error_code`` 分支。

统一外壳形状::

    {
      "ok": false,
      "error_code": "SIMULATOR_INVALID_PRICE",
      "message": "days 必须 > 0，当前: 0",
      "cause": null,
      "detail": "..."            # 仅 API 的 HTTP 响应带（HTTPException 惯例）
    }
"""

from __future__ import annotations

from typing import Any

from .errors import ErrorCode, ZettarancError

__all__ = [
    "CommandResult",
    "error_result",
    "exception_to_dict",
    "http_status_for",
]


def exception_to_dict(exc: BaseException) -> dict[str, Any]:
    """把异常映射成统一外壳的 ``data`` 部分。

    ``ZettarancError`` 保留它的 ``ErrorCode``；其他异常一律归到
    ``INTERNAL_ERROR``（新增错误码），不再静默变成没有语义的 ``internal_error``
    字符串。
    """
    if isinstance(exc, ZettarancError):
        return {
            "ok": False,
            "error_code": exc.code.value,
            "message": exc.message,
            "cause": repr(exc.cause) if exc.cause else None,
        }
    return {
        "ok": False,
        "error_code": ErrorCode.INTERNAL_ERROR.value,
        "message": str(exc) or exc.__class__.__name__,
        "cause": None,
    }


def http_status_for(exc: BaseException) -> int:
    """把异常映射成 HTTP 状态码。

    客户端错误（参数非法、无数据）用 4xx，服务端错误用 5xx——此前一律 500，
    让"股票代码不存在"和"数据库挂了"在宿主侧无法区分。
    """
    if isinstance(exc, ZettarancError):
        if exc.code in _CLIENT_ERROR_CODES:
            return 400
        if exc.code in _NOT_FOUND_CODES:
            return 404
    return 500


# 4xx：调用方的问题（参数非法 / 数据不存在 / 未配置）
_CLIENT_ERROR_CODES: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.INVALID_PARAM,
        ErrorCode.SIMULATOR_INVALID_PRICE,
        ErrorCode.SCREENER_INVALID_CRITERIA,
        ErrorCode.BACKTEST_INVALID_CONFIG,
        ErrorCode.CONFIG_MISSING,
    }
)

# 404：资源不存在
_NOT_FOUND_CODES: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.SCREENER_NO_DATA,
        ErrorCode.SIMULATOR_NO_KLINES,
        ErrorCode.BACKTEST_EMPTY_KLINES,
        ErrorCode.INDEVS_NO_DATA,
    }
)


class CommandResult:
    """命令结果的统一外壳。

    成功时 ``ok=True`` 且 ``data`` 是各命令原有的 JSON 载荷；失败时
    ``ok=False`` 且 ``error_code`` / ``message`` 描述原因。

    用法::

        result = CommandResult.success(payload)
        result = CommandResult.failure(ErrorCode.INVALID_PARAM, "days 必须 > 0")

    也可直接 ``CommandResult(exc)`` 从异常构造。
    """

    __slots__ = ("_data", "_error_code", "_message", "_cause")

    def __init__(
        self,
        *,
        data: Any = None,
        error_code: ErrorCode | str | None = None,
        message: str = "",
        cause: str | None = None,
    ) -> None:
        self._data = data
        self._error_code = error_code
        self._message = message
        self._cause = cause

    @classmethod
    def success(cls, data: Any = None) -> CommandResult:
        """成功结果。``data`` 直接是各命令原有的 JSON 载荷。"""
        return cls(data=data)

    @classmethod
    def failure(
        cls,
        error_code: ErrorCode | str,
        message: str,
        *,
        cause: str | None = None,
    ) -> CommandResult:
        """失败结果。"""
        return cls(error_code=error_code, message=message, cause=cause)

    @classmethod
    def from_exception(cls, exc: BaseException) -> CommandResult:
        """从异常构造失败结果。"""
        payload = exception_to_dict(exc)
        return cls(
            error_code=payload["error_code"],
            message=payload["message"],
            cause=payload["cause"],
        )

    @property
    def ok(self) -> bool:
        return self._error_code is None

    @property
    def data(self) -> Any:
        """成功时的 JSON 载荷。失败时为 ``None``。"""
        return self._data

    @property
    def error_code(self) -> str | None:
        """失败时的错误码（``ErrorCode`` 的字符串值）。成功时为 ``None``。"""
        if self._error_code is None:
            return None
        if isinstance(self._error_code, ErrorCode):
            return self._error_code.value
        return str(self._error_code)

    @property
    def message(self) -> str:
        return self._message

    @property
    def cause(self) -> str | None:
        return self._cause

    def to_dict(self) -> dict[str, Any]:
        """转成 JSON 可序列化的 dict。

        成功时返回 ``{"ok": True, "data": …}``；失败时返回统一错误外壳。
        """
        if self.ok:
            return {"ok": True, "data": self._data}
        return {
            "ok": False,
            "error_code": self.error_code,
            "message": self._message,
            "cause": self._cause,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        if self.ok:
            return f"CommandResult(ok=True, data_type={type(self._data).__name__})"
        return f"CommandResult(ok=False, error_code={self.error_code!r}, message={self._message!r})"


def error_result(exc: BaseException) -> dict[str, Any]:
    """便捷函数：异常 → 统一错误外壳 dict。"""
    return exception_to_dict(exc)

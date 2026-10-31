"""CLI 子命令共享工具函数。"""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

from modules.core.errors import ErrorCode

# CLI 统一的错误退出码。顶层 cli.py 的异常路径也用 2——此前 error() 退 1、
# 异常退 2，宿主脚本要记两套码。
ERROR_EXIT_CODE = 2


def json_output(data: Any) -> None:
    """将数据序列化为 JSON 并打印到 stdout"""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def error(msg: str, *, as_json: bool = False, error_code: ErrorCode | str = ErrorCode.INVALID_PARAM) -> NoReturn:
    """打印错误信息并退出。

    ``as_json=True`` 时 stdout 是**合法 JSON**（统一错误外壳，宿主可按
    ``error_code`` 分支），stderr 仍保留人类可读信息。

    默认只打 stderr——非 JSON 模式下这是正确行为（stdout 保持干净）。
    """
    if as_json:
        code = error_code.value if isinstance(error_code, ErrorCode) else str(error_code)
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": code,
                    "message": msg,
                    "cause": None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(ERROR_EXIT_CODE)


def warn(msg: str) -> None:
    """打印警告信息到 stderr"""
    print(f"警告: {msg}", file=sys.stderr)

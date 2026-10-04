"""CLI 子命令共享工具函数。"""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn


def json_output(data: Any) -> None:
    """将数据序列化为 JSON 并打印到 stdout"""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def error(msg: str) -> NoReturn:
    """打印错误信息到 stderr 并退出"""
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    """打印警告信息到 stderr"""
    print(f"警告: {msg}", file=sys.stderr)

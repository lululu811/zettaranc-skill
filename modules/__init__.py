"""
Zettaranc 技术分析模块包
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ─── 全局一次性加载 .env（包首次 import 时执行）───────────────────────────────
# 优先读取环境变量指向的路径，其次查找项目根目录的 .env
_env_path = Path(os.getenv("ZETTARANC_ENV", Path(__file__).parent.parent / ".env"))
load_dotenv(_env_path, override=False)  # 已有的环境变量不被 .env 覆盖（保持测试 fixture 隔离能力）


# ─── 公开 API ────────────────────────────────────────────────────────────────
from .database import get_connection, get_db_path, init_database  # noqa: E402
from .tushare_client import TushareClient  # noqa: E402
from .setup_wizard import run_wizard, check_env_exists, check_data_mode  # noqa: E402

# 随堂测试复盘模块（数据准备层，点评由LLM生成）
from .trade_parser import TradeParser, ParseResult, format_trade_for_review  # noqa: E402
from .trade_manager import TradeManager, trade_manager  # noqa: E402
from .trade_reviewer import TradeReviewer, ReviewContext, create_reviewer  # noqa: E402

__all__ = [
    # 数据库
    "get_connection",
    "get_db_path",
    "init_database",
    # Tushare
    "TushareClient",
    # 初始化向导
    "run_wizard",
    "check_env_exists",
    "check_data_mode",
    # 随堂测试复盘（数据层）
    "TradeParser",
    "ParseResult",
    "format_trade_for_review",
    "TradeManager",
    "trade_manager",
    "TradeReviewer",
    "ReviewContext",
    "create_reviewer",
    # 控制台编码
    "ensure_utf8_stdout",
]


def get_data_mode() -> str:
    """获取当前数据模式：jnb 或 websearch"""
    return os.getenv("DATA_MODE", "websearch")


def get_project_root() -> Path:
    """获取项目根目录（modules/ 的上一级）"""
    return Path(__file__).parent.parent


def ensure_utf8_stdout() -> None:
    """确保 stdout/stderr 使用 UTF-8，避免 Windows 控制台中文乱码。

    仅在各 CLI 入口（``python -m modules.X``）的 ``if __name__ == "__main__":``
    块里调用，**绝不在模块顶层调用**——否则会污染 API server / 测试 / 库导入等
    所有 import 方（pytest 捕获的 stdout 没有 ``.buffer`` 属性，模块级强行包装会报错）。

    幂等：当前流已是 UTF-8、或被重定向无 ``.buffer``（IDE / pytest 捕获）时直接跳过。
    """
    import io
    import sys

    for _name in ("stdout", "stderr"):
        _stream = getattr(sys, _name, None)
        if _stream is None:
            continue
        _enc = getattr(_stream, "encoding", "") or ""
        if _enc.lower().replace("-", "") == "utf8":
            continue
        _buf = getattr(_stream, "buffer", None)
        if _buf is None:
            continue  # 已被重定向（IDE / pytest 捕获等），不要动
        setattr(sys, _name, io.TextIOWrapper(_buf, encoding="utf-8", errors="replace"))

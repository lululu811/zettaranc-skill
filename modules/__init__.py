"""
Zettaranc 技术分析模块包
"""

from .database import get_connection, get_db_path, init_database
from .tushare_client import TushareClient
from .setup_wizard import run_wizard, check_env_exists, check_data_mode

# 随堂测试复盘模块（数据准备层，点评由LLM生成）
from .trade_parser import TradeParser, ParseResult, format_trade_for_review
from .trade_manager import TradeManager, trade_manager
from .trade_reviewer import TradeReviewer, ReviewContext, create_reviewer

__all__ = [
    'get_connection',
    'get_db_path',
    'init_database',
    'TushareClient',
    'run_wizard',
    'check_env_exists',
    'check_data_mode',
    # 随堂测试复盘（数据层）
    'TradeParser',
    'ParseResult',
    'format_trade_for_review',
    'TradeManager',
    'trade_manager',
    'TradeReviewer',
    'ReviewContext',
    'create_reviewer',
]


def get_data_mode() -> str:
    """获取当前数据模式：jnb 或 websearch"""
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    return os.getenv("DATA_MODE", "websearch")

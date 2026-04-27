"""
Zettaranc 技术分析模块包
"""

from .database import get_connection, get_db_path, init_database
from .tushare_client import TushareClient
from .setup_wizard import run_wizard, check_env_exists, check_data_mode

__all__ = [
    'get_connection',
    'get_db_path',
    'init_database',
    'TushareClient',
    'run_wizard',
    'check_env_exists',
    'check_data_mode',
]


def get_data_mode() -> str:
    """获取当前数据模式：jnb 或 websearch"""
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    return os.getenv("DATA_MODE", "websearch")

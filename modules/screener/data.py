"""选股数据获取层（支持 DataSource 注入）。"""

from ..database import get_db_connection
from ..datasource import DataSource, dict_to_daily, get_datasource
from ..indicators import DailyData

# 向后兼容别名
_dict_to_daily = dict_to_daily


def get_all_stocks(datasource: DataSource | None = None) -> list[dict]:
    """
    获取所有股票基本信息

    优先从注入的 datasource 获取，为空时回退到本地 SQLite
    """
    if datasource is None:
        datasource = get_datasource()

    stocks = datasource.get_stock_list()
    if stocks:
        # 过滤主板/创业板/科创板
        return [s for s in stocks if s.get("market") in ("主板", "创业板", "科创板", None)]

    # 回退到本地
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ts_code, name, industry, market
        FROM stock_basic
        WHERE market IN ('主板', '创业板', '科创板')
        ORDER BY ts_code
    """)
    stocks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return stocks


def get_recent_klines(ts_code: str, days: int = 60, datasource: DataSource | None = None) -> list[DailyData]:
    """
    获取近期 K 线数据

    从注入的 datasource 获取并转换为 DailyData（升序）
    """
    if datasource is None:
        datasource = get_datasource()

    rows = datasource.get_kline_dicts(ts_code, days=days)
    if not rows:
        return []

    return _dict_to_daily(rows)

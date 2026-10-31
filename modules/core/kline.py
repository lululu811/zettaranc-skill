"""K 线序列读取 —— ``daily_kline`` 查询的唯一 SQL 定义处。

此前同一段"取最近 N 天、升序返回"的 SQL 抄了三处：
- ``datasource.SqliteDataSource.get_kline_dicts``
- ``datasource.CompositeDataSource.get_kline_dicts``（几乎是上一处的逐字副本）
- ``indicators.data_layer.get_kline_data``

批量查询（``datasource.SqliteDataSource.get_kline_dicts_batch``）是第 4 处副本，
用 ``IN (...)`` 一次取多只，形状不同但列定义与截断规则相同。

现在单只走 :func:`read_kline_rows`，批量走 :func:`read_kline_rows_batch`。

**只统一 SQL，不统一 dict → DailyData 的转换**：
``datasource.dict_to_daily`` 会显式计算 ``is_rise`` / ``is_beidou`` / ``is_suoliang``
等派生标志，而 ``indicators.data_layer.get_kline_data`` 不算（用 DailyData 的默认值
False）。下游的战法检测依赖这些标志，两条路径的 DailyData **并不等价**，强行统一
会改变回测结果。
"""

from __future__ import annotations

from typing import Any

KLINE_COLUMNS = ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount", "pct_chg")


def resolve_kline_limit(days: int, start_date: str | None = None) -> int | None:
    """按数据源协议算出 LIMIT 值 —— **``days`` 与日期区间的优先级只此一处定义**。

    协议（``DataSource.get_kline_dicts`` 的全部 6 个实现一致）：
    - 给了 ``start_date``：以区间为准，**忽略** ``days``（返回区间内全部 K 线）；
    - 否则 ``days > 0``：只返回最近 ``days`` 天；
    - 否则（``days <= 0``）：不截断。

    此前这条规则在 6 处各写一遍（sqlite/composite 走 SQL LIMIT，tushare/hithink/
    a-stock/indevs 走 Python 切片 ``records[-days:]``），任何一处漂移都会让
    DB 路径与 API 路径给出不同长度的 K 线。
    """
    if start_date:
        return None
    return days if days > 0 else None


def _rows_to_dicts(rows: list[Any]) -> list[dict]:
    """把查询结果转成 dict 列表（升序）。

    ``row_factory`` 为 ``sqlite3.Row`` 时走 ``dict(row)``；为 ``None``（裸元组）时
    用 ``zip`` 补列名——批量逐股场景下 ``sqlite3.Row`` 构造开销大。
    """
    if not rows:
        return []
    if not isinstance(rows[0], tuple):
        return [dict(row) for row in rows]
    return [dict(zip(KLINE_COLUMNS, row)) for row in rows]


def read_kline_rows(
    ts_code: str,
    *,
    conn: Any,
    limit: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """从 ``daily_kline`` 读一段 K 线（按日期**升序**）。

    Args:
        ts_code: 股票代码。
        conn: **已打开**的连接（``row_factory`` 可为 ``sqlite3.Row`` 或 ``None``）。
        limit: 取最近 N 行；``None`` 表示不限；``0`` 表示不取任何行。
        start_date: 起始日（含）；``None`` 表示不限。
        end_date: 结束日（含）；``None`` 表示不限。

    Returns:
        K 线 dict 列表，按 ``trade_date`` 升序。
    """
    cursor = conn.cursor()
    sql = f"SELECT {', '.join(KLINE_COLUMNS)} FROM daily_kline WHERE ts_code = ?"
    params: list[Any] = [ts_code]

    if start_date:
        sql += " AND trade_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND trade_date <= ?"
        params.append(end_date)

    sql += " ORDER BY trade_date DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    cursor.execute(sql, params)
    # SQL 按 DESC 取（配合 LIMIT 取"最近 N 天"），这里反转成升序
    return _rows_to_dicts(list(reversed(cursor.fetchall())))


def read_kline_rows_batch(
    ts_codes: list[str],
    *,
    conn: Any,
    days: int = 60,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, list[dict]]:
    """批量读取多只股票的 K 线（共享一条 ``IN (...)`` 查询，避免 N+1 次 SELECT）。

    每只股票的截断规则与 :func:`read_kline_rows` 一致（走
    :func:`resolve_kline_limit`）：给了 ``start_date`` 就以区间为准，否则按 ``days``
    取最近 N 天。

    Returns:
        ``{ts_code: [K 线 dict 升序]}``；无数据的股票对应空列表。
    """
    result: dict[str, list[dict]] = {code: [] for code in ts_codes}
    if not ts_codes:
        return result

    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ts_codes)
    params: list[Any] = list(ts_codes)
    sql = f"SELECT {', '.join(KLINE_COLUMNS)} FROM daily_kline WHERE ts_code IN ({placeholders})"

    if start_date:
        sql += " AND trade_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND trade_date <= ?"
        params.append(end_date)

    sql += " ORDER BY ts_code, trade_date DESC"
    cursor.execute(sql, params)

    # 按 ts_code 分组（组内仍是 DESC）
    per_code: dict[str, list[Any]] = {}
    for row in cursor.fetchall():
        per_code.setdefault(row[0], []).append(row)

    limit = resolve_kline_limit(days, start_date)
    for ts_code in ts_codes:
        rows = per_code.get(ts_code, [])
        if limit:
            rows = rows[:limit]
        result[ts_code] = _rows_to_dicts(list(reversed(rows)))
    return result


__all__ = ["KLINE_COLUMNS", "read_kline_rows", "read_kline_rows_batch", "resolve_kline_limit"]

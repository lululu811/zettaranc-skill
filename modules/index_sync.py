#!/usr/bin/env python3
"""
模块说明：指数日线同步（CLI: `zt sync index`），与 modules/data_sync/ 同名前缀不同义。
命名约定：data_sync = A 股个股日线（DB-first）；index_sync = 主要指数日线（DuckDB）。
CLI 入口：`zt sync index --start 20160101 [--codes 000001.SH,...]`。

数据源：hithink（同花顺官方金融数据服务）
- 指数端点：/api/a-share-index/prices/historical
- 封装：HithinkFinanceDataSource.get_index_daily()
- 写入：DuckDB.raw_kline_daily（与个股日线同表，v_daily / v_daily_qfq 自动可见）
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_INDEX_CODES = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "399006.SZ",  # 创业板指
    "000300.SH",  # 沪深300
    "000905.SH",  # 中证500
    "000688.SH",  # 科创50
]


def _parse_trade_date(value: Any) -> Any:
    """把 YYYYMMDD / YYYY-MM-DD / datetime 统一转成 DuckDB DATE 可写值。"""
    if hasattr(value, "date"):  # pandas Timestamp / datetime
        return value.date()
    s = str(value).replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return str(value)


def sync_indices_to_duckdb(
    duckdb_path: str,
    index_codes: list[str] | None = None,
    start_date: str | None = "20160101",
    end_date: str | None = None,
    datasource: Any = None,
) -> dict[str, Any]:
    """通过 hithink 把主要指数日线同步到 DuckDB。

    Args:
        duckdb_path: DuckDB 数据库路径。
        index_codes: 指数代码列表，默认 DEFAULT_INDEX_CODES。
        start_date: 起始日期 YYYYMMDD，默认 2016-01-01。
        end_date: 结束日期 YYYYMMDD，默认今天。
        datasource: 数据源；None 时使用 hithink。

    Returns:
        {"total_rows": int, "details": {code: {"rows": int, "status": str}}}
    """
    codes = index_codes or DEFAULT_INDEX_CODES
    if datasource is None:
        from .datasource import get_datasource

        datasource = get_datasource(preferred="hithink")

    try:
        import duckdb  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError("需要安装 duckdb 包才能同步到 DuckDB") from e

    con = duckdb.connect(duckdb_path)
    batch_id = f"hithink-index-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    total_rows = 0
    details: dict[str, Any] = {}

    try:
        for code in codes:
            try:
                df = datasource.get_index_daily(code, start_date=start_date, end_date=end_date)
            except Exception:  # noqa: BLE001
                # 异常信息（可能含 URL/鉴权 token）只能进日志，绝不能进返回 dict
                # 返回 dict 会被 cli.py 直接 stdout + 序列化到 --json
                logger.exception("获取指数 %s 失败", code)
                details[code] = {"rows": 0, "status": "error: api"}
                continue

            if df is None or getattr(df, "empty", True):
                details[code] = {"rows": 0, "status": "no data"}
                continue

            rows = []
            for _, r in df.iterrows():
                rows.append(
                    (
                        str(r["ts_code"]),
                        _parse_trade_date(r["trade_date"]),
                        float(r["open"]),
                        float(r["high"]),
                        float(r["low"]),
                        float(r["close"]),
                        float(r.get("vol", 0) or 0),
                        float(r.get("amount", 0) or 0),
                        "CNY",
                        "1d",
                        "none",
                        batch_id,
                    )
                )

            if not rows:
                details[code] = {"rows": 0, "status": "no rows"}
                continue

            con.executemany(
                """
                INSERT INTO raw_kline_daily
                    (thscode, date, open, high, low, "close", volume, turnover,
                     currency, "interval", adjusted, source_batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (thscode, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    "close" = excluded."close",
                    volume = excluded.volume,
                    turnover = excluded.turnover,
                    currency = excluded.currency,
                    "interval" = excluded."interval",
                    adjusted = excluded.adjusted,
                    source_batch_id = excluded.source_batch_id
                """,
                rows,
            )
            total_rows += len(rows)
            details[code] = {"rows": len(rows), "status": "ok"}
            logger.info("指数 %s 同步 %d 条", code, len(rows))

        # 记录导入批次
        con.execute(
            """
            INSERT INTO _import_batches (batch_id, "source", kind, started_at, finished_at, row_count, notes)
            VALUES (?, 'hithink', 'index_daily', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?)
            """,
            [batch_id, total_rows, ",".join(codes)],
        )
    finally:
        con.close()

    return {"total_rows": total_rows, "batch_id": batch_id, "details": details}

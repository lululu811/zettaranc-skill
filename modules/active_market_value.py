#!/usr/bin/env python3
"""
模块说明：活跃市值（0AMV）闸门（Backtest 专用；Simulator 不消费）。
CLI 入口：`zt sync 0amv --csv <path> --duckdb <path>` 导入；下游 `apply_active_mv_gate` 由 b1_b2 / portfolio 调用。

活跃市值（0AMV）数据加载与择时信号模块。

数据源：指南针 0AMV 活跃市值指数日线 CSV（date/open/high/low/close/volume/amount）。
规则（来自 zettaranc 体系）：
- 日环比 >= +4%   → 多头信号（增量资金进场）
- 日环比 <= -2.3% → 空头信号（资金离场）
"""

from __future__ import annotations

import bisect
import csv
import logging
import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional


@dataclass
class ActiveMarketValuePoint:
    """0AMV 活跃市值单日数据。"""

    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    pct_chg: float = 0.0
    cum2_pct: float = 0.0  # 两日累计涨幅（今日 close / 前2个交易日 close - 1）
    signal: str = "NEUTRAL"  # UP / DOWN / NEUTRAL


def default_path() -> Path:
    """默认 CSV 路径。优先读 DATA_DIR 环境变量，缺省时回退到包内 data/ 目录。"""
    data_dir = os.getenv("DATA_DIR")
    if data_dir:
        return Path(data_dir) / "0amv_active_market_value.csv"
    return Path(__file__).resolve().parent.parent / "data" / "0amv_active_market_value.csv"


def _finalize_points(raw_rows: list[dict]) -> list[ActiveMarketValuePoint]:
    """把原始 OHLCV 行转成 ActiveMarketValuePoint，并计算 pct/cum2/signal。"""
    points: list[ActiveMarketValuePoint] = []
    prev_close: float | None = None
    for row in raw_rows:
        close = float(row["close"])
        pct_chg = (close / prev_close - 1.0) * 100.0 if prev_close and prev_close > 0 else 0.0
        if pct_chg >= 4.0:
            signal = "UP"
        elif pct_chg <= -2.3:
            signal = "DOWN"
        else:
            signal = "NEUTRAL"
        points.append(
            ActiveMarketValuePoint(
                date=str(row["date"]).strip(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=close,
                volume=float(row["volume"]),
                amount=float(row["amount"]),
                pct_chg=round(pct_chg, 4),
                signal=signal,
            )
        )
        prev_close = close

    # 两日累计涨幅：今日 close / 前 2 个交易日 close - 1
    for i, point in enumerate(points):
        if i >= 2 and points[i - 2].close > 0:
            point.cum2_pct = round((point.close / points[i - 2].close - 1.0) * 100.0, 4)
    return points


def _read_csv_rows(csv_path: Path) -> list[dict]:
    """从 CSV 读取原始行（单行解析失败时跳过并 warning,而不是整文件 abort）。"""
    raw_rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):  # 行号从 2 开始（标题行占 1）
            try:
                raw_rows.append(
                    {
                        "date": row["date"],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "amount": row["amount"],
                    }
                )
            except KeyError as e:
                logging.getLogger(__name__).warning("0AMV CSV 第 %d 行缺字段 %s，已跳过", line_no, e)
                continue
    return raw_rows


def _read_duckdb_rows(duckdb_path: str) -> list[dict]:
    """从 DuckDB 的 active_market_value 表读取原始行。"""
    try:
        import duckdb  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError("需要安装 duckdb 包才能读取 DuckDB") from e

    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT CAST(date AS VARCHAR) AS date, open, high, low, close, volume, amount "
            "FROM active_market_value ORDER BY date"
        ).fetchall()
    finally:
        con.close()

    return [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5], "amount": r[6]}
        for r in rows
    ]


# mtime 感知的 lru_cache:key 是 (path, mtime)，文件变更时自动失效，避免 lru_cache
# 单纯用 path 导致的"热重载后拿到旧数据"和"长跑进程内存泄漏"两个问题。
@lru_cache(maxsize=8)
def _load_csv_cached(path: str, mtime: float) -> list[ActiveMarketValuePoint]:
    """从 CSV 加载（按 (path, mtime) 缓存）。"""
    return _finalize_points(_read_csv_rows(Path(path)))


@lru_cache(maxsize=8)
def _load_duckdb_cached(duckdb_path: str, mtime: float) -> list[ActiveMarketValuePoint]:
    """从 DuckDB 的 active_market_value 表加载（按 (path, mtime) 缓存）。"""
    return _finalize_points(_read_duckdb_rows(duckdb_path))


def _safe_mtime(path: str) -> float:
    """取 path 的 mtime;文件不存在返回 0（让 cache 命中一个稳定的空 key）。"""
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def _build_index(points: list[ActiveMarketValuePoint]) -> dict[str, ActiveMarketValuePoint]:
    """date → point 的 O(1) 索引，替代线性扫描。"""
    return {p.date: p for p in points}


# 同样按 (path, mtime) 缓存索引;索引失效时点列表也失效（同一 mtime 触发）。
@lru_cache(maxsize=8)
def _index_csv_cached(path: str, mtime: float) -> dict[str, ActiveMarketValuePoint]:
    return _build_index(_load_csv_cached(path, mtime))


@lru_cache(maxsize=8)
def _index_duckdb_cached(duckdb_path: str, mtime: float) -> dict[str, ActiveMarketValuePoint]:
    return _build_index(_load_duckdb_cached(duckdb_path, mtime))


def clear_cache() -> None:
    """显式清空所有 0AMV 缓存（测试/CSV 热重载时调用）。"""
    _load_csv_cached.cache_clear()
    _load_duckdb_cached.cache_clear()
    _index_csv_cached.cache_clear()
    _index_duckdb_cached.cache_clear()


def _load_index_and_rows(
    path: str | None, duckdb_path: str | None
) -> tuple[list[ActiveMarketValuePoint], dict[str, ActiveMarketValuePoint]]:
    """返回 (rows, date→point 索引)。O(1) 查找用索引，需要 idx 算 cum 用 rows。

    优先 DuckDB，失败/空时回退 CSV。两边都按 (path, mtime) 缓存，文件变更自动失效。
    """
    if duckdb_path:
        mtime = _safe_mtime(duckdb_path)
        try:
            rows = _load_duckdb_cached(duckdb_path, mtime)
            if rows:
                return rows, _index_duckdb_cached(duckdb_path, mtime)
        except Exception:  # noqa: BLE001
            pass
    csv_path = str(path or default_path())
    mtime = _safe_mtime(csv_path)
    rows = _load_csv_cached(csv_path, mtime)
    return rows, _index_csv_cached(csv_path, mtime)


def load_active_market_value(
    path: str | None = None,
    duckdb_path: str | None = None,
) -> list[ActiveMarketValuePoint]:
    """加载 0AMV 日线数据（按 (path, mtime) 缓存，文件变更自动失效）。

    优先 DuckDB（active_market_value 表），未提供 DuckDB 或表为空时使用 CSV。

    Args:
        path: CSV 路径；None 使用项目默认路径（优先 DATA_DIR）。
        duckdb_path: DuckDB 数据库路径；提供时优先从 DuckDB 读取。

    Returns:
        按日期升序的活跃市值点列表。
    """
    if duckdb_path:
        try:
            mtime = _safe_mtime(duckdb_path)
            rows = _load_duckdb_cached(duckdb_path, mtime)
            if rows:
                return rows
        except Exception:  # noqa: BLE001
            # DuckDB 表不存在或读取失败时回退 CSV
            pass
    csv_path = str(path or default_path())
    return _load_csv_cached(csv_path, _safe_mtime(csv_path))


def _normalize_query_date(date: str) -> str:
    """把 YYYYMMDD 转成 CSV 里的 YYYY-MM-DD。"""
    s = str(date).replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return str(date)


def get_active_market_value(
    date: str | None = None,
    path: str | None = None,
    duckdb_path: str | None = None,
) -> ActiveMarketValuePoint | None:
    """获取指定日期或最新一日的活跃市值数据。"""
    rows, index = _load_index_and_rows(path, duckdb_path)
    if not rows:
        return None

    if date is None:
        return rows[-1]

    target = _normalize_query_date(date)
    return index.get(target)


def get_active_market_signal(
    date: str | None = None,
    up_threshold: float = 4.0,
    down_threshold: float = -2.3,
    path: str | None = None,
    duckdb_path: str | None = None,
) -> str:
    """获取活跃市值择时信号：UP / DOWN / NEUTRAL；无数据返回 NEUTRAL。"""
    point = get_active_market_value(date, path, duckdb_path)
    if point is None:
        return "NEUTRAL"
    if point.pct_chg >= up_threshold:
        return "UP"
    if point.pct_chg <= down_threshold:
        return "DOWN"
    return "NEUTRAL"


def _cum_pct(rows: list[ActiveMarketValuePoint], idx: int, lookback: int) -> float | None:
    """计算第 idx 天相对前 lookback 个交易日收盘的累计涨幅（%）。"""
    if idx < lookback:
        return None
    base = rows[idx - lookback].close
    if base <= 0:
        return None
    return (rows[idx].close / base - 1.0) * 100.0


def get_active_market_gate(
    date: str | None = None,
    open_lookback: int = 2,
    open_threshold: float = 4.0,
    clear_threshold: float = -2.3,
    path: str | None = None,
    duckdb_path: str | None = None,
) -> str:
    """活跃市值全局交易闸门。

    规则：
    - 累计涨幅（默认 2 日）> open_threshold（默认 +4%）→ OPEN，允许开仓
    - 当日跌幅 <= clear_threshold（默认 -2.3%） 或 累计跌幅 <= clear_threshold → CLEAR，清仓
    - 其他情况 → WAIT，不开新仓

    Returns:
        OPEN / WAIT / CLEAR
    """
    rows, index = _load_index_and_rows(path, duckdb_path)
    if not rows:
        return "WAIT"

    if date is None:
        idx = len(rows) - 1
    else:
        target = _normalize_query_date(date)
        # index 是 date→point 的 O(1) 字典，先验证存在；rows 本身 date-asc，
        # 用 bisect 把 target → idx 走 O(log n)，替代原来的 O(n) 线性扫描
        if target not in index:
            return "WAIT"
        idx = bisect.bisect_left([r.date for r in rows], target)

    point = rows[idx]
    cum = _cum_pct(rows, idx, open_lookback)

    if point.pct_chg <= clear_threshold:
        return "CLEAR"
    if cum is not None and cum <= clear_threshold:
        return "CLEAR"
    if cum is not None and cum > open_threshold:
        return "OPEN"
    return "WAIT"


def format_active_market_value(point: ActiveMarketValuePoint) -> str:
    """人类可读输出。"""
    signal_text = {
        "UP": "多头（+4% 以上）",
        "DOWN": "空头（-2.3% 以下）",
        "NEUTRAL": "中性",
    }.get(point.signal, point.signal)
    return (
        f"活跃市值(0AMV) · {point.date}\n收盘: {point.close:,.2f}\n日环比: {point.pct_chg:+.2f}%\n信号: {signal_text}"
    )


class GateAction(Enum):
    """活跃市值全局闸门动作（v4.3+ 统一闸门 API 返回值）。

    - OPEN  - 允许开新仓
    - WAIT  - 观望（不开新仓、不平仓）
    - CLEAR - 强平（清仓所有/当前持仓）
    """

    OPEN = "OPEN"
    WAIT = "WAIT"
    CLEAR = "CLEAR"


def apply_active_mv_gate(
    date: str,
    *,
    enabled: bool = True,
    duckdb_path: str | None = None,
    path: str | None = None,
) -> GateAction:
    """活跃市值全局闸门统一入口（v4.3+ 替代各 engine 自己的 _gate 实现）。

    规则：
    - enabled=False：返回 OPEN（闸门关闭，不限制任何行为）
    - enabled=True：调 get_active_market_gate 把字符串映射为 GateAction 枚举
      - 任何映射失败/异常：返回 WAIT（保守：不开新仓、不强平），不抛异常阻断回测

    Args:
        date: YYYYMMDD 或 YYYY-MM-DD 格式交易日
        enabled: 是否启用闸门；False 等价于"闸门不存在"
        duckdb_path: 优先 DuckDB 路径
        path: 备选 CSV 路径

    Returns:
        GateAction 枚举值（OPEN / WAIT / CLEAR），调用方按需解释

    Note:
        各 backtest engine（B1B2 / Portfolio）应在自己的循环里调本函数，
        拿到 GateAction 后决定：WAIT 跳过开仓、CLEAR 触发自己的强平逻辑。
        强平 scope（当前持仓 vs 所有持仓）由各 engine 自己决定，因为单股 vs 组合
        上下文不同。
    """
    if not enabled:
        return GateAction.OPEN
    try:
        gate_str = get_active_market_gate(date, duckdb_path=duckdb_path, path=path)
    except Exception:  # noqa: BLE001
        # 闸门查询失败时保守返回 WAIT,不让异常阻断回测主流程
        return GateAction.WAIT
    return {
        "OPEN": GateAction.OPEN,
        "WAIT": GateAction.WAIT,
        "CLEAR": GateAction.CLEAR,
    }.get(gate_str, GateAction.WAIT)


def import_0amv_csv_to_duckdb(csv_path: str, duckdb_path: str) -> int:
    """把 0AMV CSV 导入 DuckDB 的 active_market_value 表。

    Args:
        csv_path: 源 CSV 路径。
        duckdb_path: 目标 DuckDB 数据库路径。

    Returns:
        导入行数。
    """
    try:
        import duckdb  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError("需要安装 duckdb 包") from e

    points = load_active_market_value(path=csv_path)
    if not points:
        return 0

    con = duckdb.connect(duckdb_path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS active_market_value (
                date DATE PRIMARY KEY,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                amount DOUBLE,
                source VARCHAR,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.executemany(
            """
            INSERT INTO active_market_value
                (date, open, high, low, close, volume, amount, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '0amv_csv', now())
            ON CONFLICT (date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                amount = excluded.amount,
                source = excluded.source,
                updated_at = now()
            """,
            [
                (
                    point.date,
                    point.open,
                    point.high,
                    point.low,
                    point.close,
                    point.volume,
                    point.amount,
                )
                for point in points
            ],
        )
    finally:
        con.close()
    return len(points)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="活跃市值 0AMV")
    parser.add_argument("--date", default=None, help="日期 YYYY-MM-DD，默认最新")
    parser.add_argument("--path", default=None, help="CSV 路径")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    point = get_active_market_value(args.date, args.path)
    if point is None:
        print("未找到数据")
        raise SystemExit(1)

    gate = get_active_market_gate(args.date, path=args.path)

    if args.json:
        data = point.__dict__.copy()
        data["gate"] = gate
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_active_market_value(point))
        print(f"全局闸门: {gate}")

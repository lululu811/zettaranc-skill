#!/usr/bin/env python3
"""
模块说明：大盘择时指标（市值闸门前置条件）。
CLI 入口：`zt market timing [--date YYYYMMDD] [--index 000001.SH] [--json]`。

市场择时指标模块。
把“大盘择时”从简单的指数状态扩展到全市场维度：
- 指数趋势（均线、斜率、白线/黄线）
- 市场广度（涨跌家数、涨停/跌停、强势上涨/下跌家数）
- 资金量能（全市场成交额及趋势）
- 波动风险（指数年化波动率、距高点回撤）
- 市场情绪（涨跌停、涨跌家数综合）

数据源：
- 优先使用 DuckDB 全市场数据（推荐，能算真实广度）
- 未提供 DuckDB 时回退到项目 SQLite
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from .core.market_context import MarketRegime
from .indicators import DailyData, calculate_ma
from .market_regime import MarketRegimeClassifier
from .database import get_connection
from .dynamic_config import MarketTimingWeights
from .active_market_value import get_active_market_gate, get_active_market_value

# 常见指数代码，计算市场广度时排除（与 modules.index_sync.DEFAULT_INDEX_CODES 保持一致）
# 任何新增/删除默认指数时，这里必须同步更新；否则会把指数行当作"个股"纳入涨跌/成交统计。
_INDEX_CODES_TO_EXCLUDE = (
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "399006.SZ",  # 创业板指
    "000300.SH",  # 沪深300
    "000905.SH",  # 中证500
    "000688.SH",  # 科创50
)


def _index_not_in_sql_fragment() -> str:
    """生成 `NOT IN ('code1','code2',...)` 形式的 SQL 片段（DuckDB / SQLite 通用）。"""
    return ", ".join(f"'{c}'" for c in _INDEX_CODES_TO_EXCLUDE)


def _index_not_in_params() -> tuple:
    """参数化查询的占位符元组（`ts_code NOT IN (?, ?, ...)`）。"""
    return _INDEX_CODES_TO_EXCLUDE


@dataclass
class MarketTimingIndicators:
    """市场择时指标快照。"""

    date: str
    index_code: str = "000001.SH"

    # 指数趋势
    trend_score: float = 50.0
    ma_alignment: float = 0.0
    index_slope: float = 0.0
    white_yellow_diff: float = 0.0

    # 市场广度
    total_stocks: int = 0
    advancers: int = 0
    decliners: int = 0
    limit_up: int = 0
    limit_down: int = 0
    strong_up: int = 0
    strong_down: int = 0
    breadth_score: float = 50.0

    # 资金量能
    total_amount: float = 0.0
    amount_ratio_20: float = 1.0
    moneyflow_score: float = 50.0

    # 波动风险
    index_volatility_20: float = 0.0
    index_drawdown: float = 0.0
    risk_score: float = 50.0

    # 市场情绪
    sentiment_score: float = 50.0

    # 活跃市值（0AMV）
    active_mv_close: float = 0.0
    active_mv_pct_chg: float = 0.0
    active_mv_cum2_pct: float = 0.0
    active_mv_signal: str = "NEUTRAL"  # UP / DOWN / NEUTRAL
    active_mv_score: float = 50.0
    active_mv_gate: str = "WAIT"  # OPEN / WAIT / CLEAR

    # 综合择时
    composite_score: float = 50.0
    regime: str = MarketRegime.NEUTRAL.value  # 强势 / 震荡 / 弱势
    notes: list[str] = field(default_factory=list)


def _daily_returns(prices: list[float]) -> list[float]:
    """日收益率序列。"""
    rets: list[float] = []
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        if prev > 0:
            rets.append(prices[i] / prev - 1.0)
    return rets


def _normalize_date(trade_date: str) -> str:
    """把 YYYYMMDD 或 YYYY-MM-DD 统一成 DuckDB 可用的 YYYY-MM-DD。"""
    s = str(trade_date).replace("-", "")
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return str(trade_date)


def _to_daily_data_list(rows: list[tuple]) -> list[DailyData]:
    """把 DuckDB/SQLite 行统一转成 DailyData（升序）。"""
    result: list[DailyData] = []
    for i, row in enumerate(rows):
        # row: ts_code, trade_date(str), open, high, low, close, vol, amount
        ts_code = str(row[0])
        trade_date = str(row[1])
        close = float(row[5])
        prev_close = float(rows[i - 1][5]) if i > 0 else close
        result.append(
            DailyData(
                ts_code=ts_code,
                trade_date=trade_date,
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=close,
                vol=float(row[6]),
                amount=float(row[7]),
                pct_chg=(close / prev_close - 1.0) * 100.0 if prev_close else 0.0,
                prev_close=prev_close,
            )
        )
    return result


def _load_index_klines_duckdb(con: Any, index_code: str, days: int) -> list[DailyData]:
    """从 DuckDB 加载指数前复权 K 线。"""
    rows = con.execute(
        """
        SELECT thscode, CAST(date AS VARCHAR), open, high, low, close, volume, turnover
        FROM v_daily_qfq
        WHERE thscode = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        [index_code, days],
    ).fetchall()
    rows.reverse()
    return _to_daily_data_list(rows)


def _load_index_klines_sqlite(index_code: str, days: int) -> list[DailyData]:
    """从项目 SQLite 加载指数 K 线。"""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ts_code, trade_date, open, high, low, close, vol, amount
            FROM (
                SELECT ts_code, trade_date, open, high, low, close, vol, amount
                FROM daily_kline
                WHERE ts_code = ?
                ORDER BY trade_date DESC
                LIMIT ?
            )
            ORDER BY trade_date ASC
            """,
            (index_code, days),
        ).fetchall()
    return _to_daily_data_list(rows)


def _load_market_snapshot_duckdb(con: Any, trade_date: str, weights: Any = None) -> dict[str, float]:
    """从 DuckDB 统计指定日期全市场涨跌/成交。

    Args:
        weights: MarketTimingWeights 实例,提供 limit_up_pct / limit_down_pct /
            strong_up_pct / strong_down_pct 阈值。None 时用项目默认。
    """
    from modules.dynamic_config import DEFAULT_MARKET_TIMING_WEIGHTS

    if weights is None:
        weights = DEFAULT_MARKET_TIMING_WEIGHTS
    iso_date = _normalize_date(trade_date)
    row = con.execute(
        f"""
        WITH prev AS (
            SELECT thscode, date, close, turnover,
                   LAG(close) OVER (PARTITION BY thscode ORDER BY date) AS prev_close
            FROM v_daily_qfq
        )
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN close > prev_close THEN 1 ELSE 0 END), 0) AS advancers,
            COALESCE(SUM(CASE WHEN close < prev_close THEN 1 ELSE 0 END), 0) AS decliners,
            COALESCE(SUM(CASE WHEN (close / prev_close - 1) * 100 >= {weights.limit_up_pct} THEN 1 ELSE 0 END), 0) AS limit_up,
            COALESCE(SUM(CASE WHEN (close / prev_close - 1) * 100 <= {weights.limit_down_pct} THEN 1 ELSE 0 END), 0) AS limit_down,
            COALESCE(SUM(CASE WHEN (close / prev_close - 1) * 100 >= {weights.strong_up_pct} THEN 1 ELSE 0 END), 0) AS strong_up,
            COALESCE(SUM(CASE WHEN (close / prev_close - 1) * 100 <= {weights.strong_down_pct} THEN 1 ELSE 0 END), 0) AS strong_down,
            COALESCE(SUM(turnover), 0) AS total_amount
        FROM prev
        WHERE date = ? AND prev_close IS NOT NULL AND prev_close > 0
          AND thscode NOT IN ({_index_not_in_sql_fragment()})
        """,
        [iso_date],
    ).fetchone()
    keys = ["total", "advancers", "decliners", "limit_up", "limit_down", "strong_up", "strong_down", "total_amount"]
    return dict(zip(keys, [float(v) if v is not None else 0.0 for v in row]))


def _load_market_snapshot_sqlite(trade_date: str, weights: Any = None) -> dict[str, float]:
    """从项目 SQLite 统计指定日期全市场涨跌/成交（数据量有限）。

    Args:
        weights: MarketTimingWeights 实例,None 时用项目默认。
    """
    from modules.dynamic_config import DEFAULT_MARKET_TIMING_WEIGHTS

    if weights is None:
        weights = DEFAULT_MARKET_TIMING_WEIGHTS
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END), 0) AS advancers,
                COALESCE(SUM(CASE WHEN pct_chg < 0 THEN 1 ELSE 0 END), 0) AS decliners,
                COALESCE(SUM(CASE WHEN pct_chg >= {weights.limit_up_pct} THEN 1 ELSE 0 END), 0) AS limit_up,
                COALESCE(SUM(CASE WHEN pct_chg <= {weights.limit_down_pct} THEN 1 ELSE 0 END), 0) AS limit_down,
                COALESCE(SUM(CASE WHEN pct_chg >= {weights.strong_up_pct} THEN 1 ELSE 0 END), 0) AS strong_up,
                COALESCE(SUM(CASE WHEN pct_chg <= {weights.strong_down_pct} THEN 1 ELSE 0 END), 0) AS strong_down,
                COALESCE(SUM(amount), 0) AS total_amount
            FROM daily_kline
            WHERE trade_date = ? AND ts_code NOT IN ({_index_not_in_sql_fragment()})
            """,
            (trade_date,),
        ).fetchone()
    keys = ["total", "advancers", "decliners", "limit_up", "limit_down", "strong_up", "strong_down", "total_amount"]
    return dict(zip(keys, [float(v) if v is not None else 0.0 for v in row]))


def _load_amount_history_duckdb(con: Any, trade_date: str, lookback: int = 40) -> list[float]:
    """从 DuckDB 取最近 lookback 个交易日全市场成交额。"""
    iso_date = _normalize_date(trade_date)
    rows = con.execute(
        f"""
        SELECT date, SUM(turnover) AS amt
        FROM v_daily_qfq
        WHERE date <= ? AND thscode NOT IN ({_index_not_in_sql_fragment()})
        GROUP BY date
        ORDER BY date DESC
        LIMIT ?
        """,
        [iso_date, lookback],
    ).fetchall()
    return [float(r[1]) for r in rows] if rows else []


def _load_amount_history_sqlite(trade_date: str, lookback: int = 40) -> list[float]:
    """从项目 SQLite 取最近 lookback 个交易日全市场成交额。"""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT trade_date, SUM(amount) AS amt
            FROM daily_kline
            WHERE trade_date <= ? AND ts_code NOT IN ({_index_not_in_sql_fragment()})
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (trade_date, lookback),
        ).fetchall()
    return [float(r[1]) for r in rows] if rows else []


def _trend_score_from_index(klines: list[DailyData]) -> tuple[float, float, float, float]:
    """由指数 K 线计算趋势分（0-100）与明细。"""
    if len(klines) < 30:
        return 50.0, 0.0, 0.0, 0.0

    classifier = MarketRegimeClassifier()
    detail = classifier.get_score_detail(klines)
    composite = detail.get("composite", 0.0)
    trend_score = max(0.0, min(100.0, (composite + 1.0) / 2.0 * 100.0))

    closes = [k.close for k in klines]
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)
    ma120 = calculate_ma(closes, 120) if len(closes) >= 120 else 0.0
    ma_alignment = 0.0
    if ma20 and ma60 and ma120:
        ma_alignment = 1.0 if ma20 > ma60 > ma120 else (-1.0 if ma20 < ma60 < ma120 else 0.0)

    white = detail.get("white_yellow_raw", 0.0)
    slope = detail.get("trend_slope_raw", 0.0)
    return trend_score, ma_alignment, slope, white


def _breadth_score(snapshot: dict[str, float]) -> float:
    """市场广度分 0-100。"""
    total = snapshot.get("total", 0)
    if total <= 0:
        return 50.0
    up = snapshot.get("advancers", 0)
    down = snapshot.get("decliners", 0)
    limit_up = snapshot.get("limit_up", 0)
    limit_down = snapshot.get("limit_down", 0)
    strong_up = snapshot.get("strong_up", 0)
    strong_down = snapshot.get("strong_down", 0)

    score = 50.0
    score += (up - down) / total * 40.0
    score += (strong_up - strong_down) / total * 30.0
    score += (limit_up - limit_down) / total * 30.0
    return max(0.0, min(100.0, score))


def _moneyflow_score(amount_history: list[float], snapshot: dict[str, float]) -> tuple[float, float]:
    """资金量能分 0-100，返回 (score, amount_ratio_20)。"""
    today_amount = snapshot.get("total_amount", 0.0)
    amount_ratio = 1.0
    if len(amount_history) >= 20:
        recent_avg = sum(amount_history[:20]) / 20.0
        if recent_avg > 0:
            amount_ratio = today_amount / recent_avg

    score = 50.0 + (amount_ratio - 1.0) * 50.0
    return max(0.0, min(100.0, score)), round(amount_ratio, 4)


def _risk_score(klines: list[DailyData]) -> tuple[float, float, float]:
    """波动风险分 0-100，返回 (score, annual_vol, drawdown)。"""
    if len(klines) < 20:
        return 50.0, 0.0, 0.0

    closes = [k.close for k in klines]
    rets = _daily_returns(closes[-21:])
    vol_annual = statistics.stdev(rets) * math.sqrt(252) if len(rets) > 1 else 0.0

    peak = max(closes)
    drawdown = (closes[-1] / peak - 1.0) if peak > 0 else 0.0

    vol_score = max(0.0, min(100.0, 100.0 - vol_annual * 120.0))
    dd_penalty = max(0.0, -drawdown * 100.0)
    score = max(0.0, min(100.0, vol_score - dd_penalty * 0.5))
    return score, round(vol_annual, 4), round(drawdown, 4)


def _sentiment_score(snapshot: dict[str, float]) -> float:
    """市场情绪分 0-100。"""
    total = snapshot.get("total", 0)
    if total <= 0:
        return 50.0
    up = snapshot.get("advancers", 0)
    down = snapshot.get("decliners", 0)
    limit_up = snapshot.get("limit_up", 0)
    limit_down = snapshot.get("limit_down", 0)

    score = 50.0
    score += (up - down) / total * 30.0
    score += (limit_up - limit_down) / total * 80.0
    return max(0.0, min(100.0, score))


def _active_mv_score(point) -> float:
    """活跃市值 0AMV 分 0-100：UP≈100，DOWN≈0，NEUTRAL 按涨幅线性映射。"""
    if point is None:
        return 50.0
    if point.signal == "UP":
        return 100.0
    if point.signal == "DOWN":
        return 0.0
    return max(0.0, min(100.0, 50.0 + point.pct_chg * 10.0))


def _classify_regime(composite: float, weights: Any = None) -> str:
    """综合分 → 市场状态(v4.3+ 阈值走 MarketTimingWeights)。

    Args:
        composite: 综合分 0-100
        weights: MarketTimingWeights 实例,None 时用项目默认
    """
    from modules.dynamic_config import DEFAULT_MARKET_TIMING_WEIGHTS

    if weights is None:
        weights = DEFAULT_MARKET_TIMING_WEIGHTS
    if composite >= weights.strong_threshold:
        return MarketRegime.STRONG.value
    if composite <= weights.weak_threshold:
        return MarketRegime.WEAK.value
    return MarketRegime.NEUTRAL.value


def compute_market_timing(
    trade_date: str | None = None,
    index_code: str = "000001.SH",
    days: int = 120,
    duckdb_path: str | None = None,
    weights: MarketTimingWeights | None = None,
) -> MarketTimingIndicators:
    """计算市场择时指标。

    Args:
        trade_date: 目标交易日 YYYYMMDD；None 表示最新日期。
        index_code: 大盘指数代码，默认上证指数。
        days: 指数 K 线回溯天数。
        duckdb_path: DuckDB 全市场数据库路径；None 则回退 SQLite。

    Returns:
        MarketTimingIndicators

    Note:
        weights (v4.3+):综合分权重与阈值抽到 modules.dynamic_config.MarketTimingWeights,
        默认用 DEFAULT_MARKET_TIMING_WEIGHTS(与原 magic numbers 完全一致)。
        改阈值 / 调权重不再需要改本函数。
    """
    if weights is None:
        from modules.dynamic_config import DEFAULT_MARKET_TIMING_WEIGHTS

        weights = DEFAULT_MARKET_TIMING_WEIGHTS
    if duckdb_path is not None:
        try:
            import duckdb  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError("使用 DuckDB 需要安装 duckdb 包") from e
        con = duckdb.connect(duckdb_path, read_only=True)
        try:
            if trade_date is None:
                row = con.execute("SELECT MAX(CAST(date AS VARCHAR)) FROM v_daily_qfq").fetchone()
                trade_date = str(row[0]) if row else ""
            klines = _load_index_klines_duckdb(con, index_code, days)
            # DuckDB 通常不包含指数，指数 K 线回退到项目 SQLite
            if not klines:
                klines = _load_index_klines_sqlite(index_code, days)
            snapshot = _load_market_snapshot_duckdb(con, trade_date, weights=weights)
            amount_history = _load_amount_history_duckdb(con, trade_date)
        finally:
            con.close()
    else:
        if trade_date is None:
            with get_connection() as conn:
                # 先按本指数查最近交易日，空则按全表最近交易日兜底（避免周末/节假日 datetime.now() 返回非交易日）
                row = conn.execute(
                    "SELECT MAX(trade_date) FROM daily_kline WHERE ts_code = ?",
                    (index_code,),
                ).fetchone()
                if row and row[0]:
                    trade_date = str(row[0])
                else:
                    row = conn.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
                    trade_date = str(row[0]) if row and row[0] else None
            if trade_date is None:
                raise ValueError("SQLite 路径无任何 daily_kline 数据，无法确定 trade_date")
        klines = _load_index_klines_sqlite(index_code, days)
        snapshot = _load_market_snapshot_sqlite(trade_date, weights=weights)
        amount_history = _load_amount_history_sqlite(trade_date)

    trend_score, ma_alignment, slope, white_yellow = _trend_score_from_index(klines)
    b_score = _breadth_score(snapshot)
    m_score, amount_ratio = _moneyflow_score(amount_history, snapshot)
    r_score, vol_annual, drawdown = _risk_score(klines)
    s_score = _sentiment_score(snapshot)

    active_mv_duckdb = duckdb_path
    active_mv = get_active_market_value(trade_date, duckdb_path=active_mv_duckdb)
    amv_score = _active_mv_score(active_mv)
    amv_pct = round(active_mv.pct_chg, 4) if active_mv else 0.0
    amv_signal = active_mv.signal if active_mv else "NEUTRAL"
    amv_close = round(active_mv.close, 2) if active_mv else 0.0
    amv_cum2 = round(active_mv.cum2_pct, 4) if active_mv else 0.0
    amv_gate = get_active_market_gate(trade_date, duckdb_path=active_mv_duckdb)

    composite = (
        trend_score * weights.weight_trend
        + b_score * weights.weight_breadth
        + m_score * weights.weight_moneyflow
        + r_score * weights.weight_risk
        + s_score * weights.weight_sentiment
        + amv_score * weights.weight_amv
    )
    composite = max(0.0, min(100.0, composite))

    notes = [
        f"指数趋势分 {trend_score:.0f}",
        f"市场广度分 {b_score:.0f}",
        f"资金量能分 {m_score:.0f}",
        f"波动风险分 {r_score:.0f}",
        f"市场情绪分 {s_score:.0f}",
        f"活跃市值 {amv_signal} 闸门={amv_gate} ({amv_cum2:+.2f}%)",
    ]

    return MarketTimingIndicators(
        date=trade_date.replace("-", ""),
        index_code=index_code,
        trend_score=round(trend_score, 2),
        ma_alignment=round(ma_alignment, 4),
        index_slope=round(slope, 6),
        white_yellow_diff=round(white_yellow, 6),
        total_stocks=int(snapshot.get("total", 0)),
        advancers=int(snapshot.get("advancers", 0)),
        decliners=int(snapshot.get("decliners", 0)),
        limit_up=int(snapshot.get("limit_up", 0)),
        limit_down=int(snapshot.get("limit_down", 0)),
        strong_up=int(snapshot.get("strong_up", 0)),
        strong_down=int(snapshot.get("strong_down", 0)),
        breadth_score=round(b_score, 2),
        total_amount=round(snapshot.get("total_amount", 0.0), 2),
        amount_ratio_20=amount_ratio,
        moneyflow_score=round(m_score, 2),
        index_volatility_20=vol_annual,
        index_drawdown=drawdown,
        risk_score=round(r_score, 2),
        sentiment_score=round(s_score, 2),
        active_mv_close=amv_close,
        active_mv_pct_chg=amv_pct,
        active_mv_cum2_pct=amv_cum2,
        active_mv_signal=amv_signal,
        active_mv_score=round(amv_score, 2),
        active_mv_gate=amv_gate,
        composite_score=round(composite, 2),
        regime=_classify_regime(composite, weights=weights),
        notes=notes,
    )


def format_market_timing(ind: MarketTimingIndicators) -> str:
    """人类可读输出。"""
    lines = [
        f"市场择时 · {ind.date} ({ind.index_code})",
        f"市场状态: {ind.regime}",
        f"综合择时分: {ind.composite_score:.1f}",
        f"指数趋势: {ind.trend_score:.1f}",
        f"市场广度: {ind.breadth_score:.1f} (涨 {ind.advancers} / 跌 {ind.decliners} / 涨停 {ind.limit_up} / 跌停 {ind.limit_down})",
        f"资金量能: {ind.moneyflow_score:.1f} (总额 {ind.total_amount:,.0f} / 20日均比 {ind.amount_ratio_20:.2f})",
        f"波动风险: {ind.risk_score:.1f} (年化波动 {ind.index_volatility_20:.2%} / 回撤 {ind.index_drawdown:.2%})",
        f"市场情绪: {ind.sentiment_score:.1f}",
        f"活跃市值: {ind.active_mv_signal} 闸门={ind.active_mv_gate} (2日累计 {ind.active_mv_cum2_pct:+.2f}% / 收盘 {ind.active_mv_close:,.2f})",
        f"备注: {', '.join(ind.notes)}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="市场择时指标")
    parser.add_argument("--date", default=None, help="交易日 YYYYMMDD，默认最新")
    parser.add_argument("--index", default="000001.SH", help="大盘指数代码")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--duckdb", default=None, help="DuckDB 全市场数据库路径")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = compute_market_timing(args.date, args.index, args.days, args.duckdb)
    if args.json:
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_market_timing(result))

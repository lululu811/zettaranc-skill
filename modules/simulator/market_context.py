#!/usr/bin/env python3
"""
市场环境判断模块。

基于大盘指数（sh000001 / sz399006）和全市场涨跌家数比，
把每个交易日归类为 STRONG / NEUTRAL / WEAK，用于控制仓位上限。
"""

from __future__ import annotations

import logging
import sqlite3

from ..database import get_connection
from ..datasource import DataSource, get_datasource
from ..indicators import DailyData, calculate_zg_white, calculate_dg_yellow, calculate_ma
from ..indicators.core import calculate_ema_series
from . import MarketContext, MarketRegime
from modules.core.errors import ErrorCode, ZettarancError


logger = logging.getLogger(__name__)

_DEFAULT_INDEX_CODE = "000001.SH"


def _trend_score_from_values(
    white: float,
    yellow: float,
    prev_white: float,
    prev_yellow: float,
    close: float,
) -> float:
    """由已算好的白线/黄线值给出大盘趋势得分 0-100（纯算术，无重复计算）。"""
    score = 50.0
    if white > yellow:
        score += 20
    else:
        score -= 20

    if white > prev_white:
        score += 10
    if yellow > prev_yellow:
        score += 10

    # 价格在黄线上方加分
    if close > yellow:
        score += 10

    return max(0.0, min(100.0, score))


def _trend_score(klines: list[DailyData]) -> float:
    """基于白线/黄线位置与斜率给出大盘趋势得分 0-100。"""
    if len(klines) < 60:
        return 50.0

    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    prev_white = calculate_zg_white(klines[:-1])
    prev_yellow = calculate_dg_yellow(klines[:-1])

    return _trend_score_from_values(white, yellow, prev_white, prev_yellow, klines[-1].close)


def _precompute_line_series(klines: list[DailyData], start: int) -> tuple[dict[int, float], dict[int, float]]:
    """一次性预计算白线/黄线序列，避免逐日期 O(n) 重复计算。

    浮点运算顺序与 calculate_zg_white / calculate_dg_yellow 完全一致，
    保证结果逐位相同。仅计算 start 及之后的位置（precompute 只需 idx >= 59）。

    Returns:
        (whites, yellows)：下标 -> 指标值 的两个 dict
    """
    closes = [k.close for k in klines]
    whites: dict[int, float] = {}
    yellows: dict[int, float] = {}
    ema1_series = calculate_ema_series(closes, 10)
    ema2_series = calculate_ema_series(ema1_series, 10)

    for i in range(max(0, start), len(klines)):
        n = i + 1
        # 白线：EMA(EMA(C, 10), 10)，与 calculate_zg_white 完全一致。
        whites[i] = round(ema2_series[i], 2) if n >= 10 else 0
        # 黄线：calculate_dg_yellow 同款分支
        if n < 114:
            yellows[i] = 0
        else:
            ma14 = sum(closes[i - 13 : i + 1]) / 14
            ma28 = sum(closes[i - 27 : i + 1]) / 28
            ma57 = sum(closes[i - 56 : i + 1]) / 57
            ma114 = sum(closes[i - 113 : i + 1]) / 114
            yellows[i] = round((ma14 + ma28 + ma57 + ma114) / 4, 2)

    return whites, yellows


def _breadth_approx(klines: list[DailyData]) -> float:
    """用指数涨跌幅度近似市场广度，-1 ~ 1。"""
    if len(klines) < 20:
        return 0.0

    up_days = sum(1 for k in klines[-20:] if k.close > k.open)
    down_days = 20 - up_days
    return (up_days - down_days) / 20.0


def _moneyflow_score(klines: list[DailyData]) -> float:
    """基于量价关系给出资金得分 0-100。"""
    if len(klines) < 20:
        return 50.0

    recent = klines[-20:]
    volume_trend = recent[-1].vol / (sum(k.vol for k in recent[:-1]) / max(1, len(recent) - 1))
    price_trend = recent[-1].close / recent[0].close - 1.0

    score = 50.0 + price_trend * 200  # 涨幅 5% → +10 分
    if volume_trend > 1.2:
        score += 10
    elif volume_trend < 0.8:
        score -= 10

    return max(0.0, min(100.0, score))


def _fetch_breadth(trade_date: str) -> tuple[int, int]:
    """查询当日涨跌停家数（基于 pct_chg 启发式阈值）。"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN pct_chg >= 9.5 THEN 1 ELSE 0 END), 0) AS limit_up,
                    COALESCE(SUM(CASE WHEN pct_chg <= -9.5 THEN 1 ELSE 0 END), 0) AS limit_down
                FROM daily_kline
                WHERE trade_date = ?
                """,
                (trade_date,),
            )
            row = cursor.fetchone()
            if row is None:
                return 0, 0
            return int(row["limit_up"]), int(row["limit_down"])
    except (sqlite3.Error, KeyError, TypeError, ValueError) as e:
        logger.warning("[market_context] 查询涨跌停家数失败: %s", e)
        return 0, 0


def _fetch_turnover_trend(trade_date: str) -> float | None:
    """
    计算全市场成交额趋势：最近 20 个交易日总成交额 / 前 20 个交易日总成交额。

    返回 None 表示数据不足或查询失败。
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT trade_date, SUM(amount) AS total_amount
                FROM daily_kline
                WHERE trade_date <= ?
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT 40
                """,
                (trade_date,),
            )
            rows = cursor.fetchall()
            if len(rows) < 40:
                return None
            recent = sum(float(r["total_amount"]) for r in rows[:20])
            previous = sum(float(r["total_amount"]) for r in rows[20:40])
            if previous <= 0:
                return None
            return recent / previous
    except (sqlite3.Error, KeyError, TypeError, ValueError, ZeroDivisionError, ArithmeticError) as e:
        logger.warning("[market_context] 计算成交额趋势失败: %s", e)
        return None


def get_market_context(
    trade_date: str,
    index_code: str = _DEFAULT_INDEX_CODE,
    datasource: DataSource | None = None,
) -> MarketContext:
    """
    获取指定交易日之前的市场环境上下文。

    Args:
        trade_date: 当前日期（YYYYMMDD 或 YYYY-MM-DD）
        index_code: 大盘指数代码
        datasource: 数据源，默认 Composite

    Returns:
        MarketContext
    """
    ds = datasource or get_datasource()
    normalized_date = trade_date.replace("-", "")
    raw_klines = ds.get_kline_dicts(index_code, days=120, end_date=normalized_date)

    if not raw_klines:
        return MarketContext(
            date=trade_date,
            regime=MarketRegime.NEUTRAL,
            index_trend=50.0,
            breadth=0.0,
            moneyflow_score=50.0,
            notes=["无指数数据，默认震荡"],
        )

    klines: list[DailyData] = [DailyData(**k) for k in raw_klines]

    trend = _trend_score(klines)
    breadth = _breadth_approx(klines)
    mf = _moneyflow_score(klines)

    # 环境判定
    if trend >= 65 and breadth > 0.1 and mf >= 55:
        regime = MarketRegime.STRONG
    elif trend <= 40 or breadth < -0.15 or mf <= 40:
        regime = MarketRegime.WEAK
    else:
        regime = MarketRegime.NEUTRAL

    limit_up, limit_down = _fetch_breadth(normalized_date)
    turnover_trend = _fetch_turnover_trend(normalized_date)
    turnover_up = turnover_trend is not None and turnover_trend > 1.0
    panic_greed_ratio = limit_up / max(limit_down, 1)

    notes = [f"大盘趋势得分 {trend:.0f}", f"涨跌广度 {breadth:+.2f}", f"资金得分 {mf:.0f}"]

    if limit_up > 0 or limit_down > 0:
        notes.append(f"涨停{limit_up}家/跌停{limit_down}家")

    if panic_greed_ratio > 10 and turnover_up:
        notes.append("情绪贪婪")
    elif panic_greed_ratio < 0.5 or limit_down > 100:
        notes.append("情绪恐慌")
        if regime == MarketRegime.STRONG:
            # 技术面强势但情绪极端恐慌时，保守降级
            regime = MarketRegime.WEAK if limit_down > 100 else MarketRegime.NEUTRAL

    return MarketContext(
        date=trade_date,
        regime=regime,
        index_trend=trend,
        breadth=breadth,
        moneyflow_score=mf,
        notes=notes,
    )


def precompute_market_contexts(
    dates: list[str],
    index_code: str = _DEFAULT_INDEX_CODE,
    datasource: DataSource | None = None,
) -> dict[str, MarketContext]:
    """批量预计算所有日期的 MarketContext，避免逐天重复查询数据库。

    比 get_market_context 快 100x+：2 次 SQL 替代 N 次，指标序列一次性预计算。
    """
    if not dates:
        return {}

    ds = datasource or get_datasource()
    result: dict[str, MarketContext] = {}

    # 1. 一次性拉取指数 K 线（覆盖全部日期 + 前 120 天缓冲）
    earliest = min(dates)
    raw_all = ds.get_kline_dicts(index_code, days=len(dates) + 150, end_date=max(dates))
    index_klines: list[DailyData] = []
    for k in raw_all or []:
        if "ts_code" not in k:
            k["ts_code"] = index_code
        index_klines.append(DailyData(**k))
    index_dates = {k.trade_date: i for i, k in enumerate(index_klines)}

    # 2. 批量查询涨跌停家数与每日总成交额（单条 SQL 一次扫描，避免两次全表扫描）
    breadth_map: dict[str, tuple[int, int]] = {}
    daily_amounts: dict[str, float] = {}
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT trade_date,
                    SUM(CASE WHEN pct_chg >= 9.5 THEN 1 ELSE 0 END) AS limit_up,
                    SUM(CASE WHEN pct_chg <= -9.5 THEN 1 ELSE 0 END) AS limit_down,
                    SUM(amount) AS total_amount
                FROM daily_kline
                WHERE trade_date >= ? AND trade_date <= ?
                GROUP BY trade_date
                ORDER BY trade_date
                """,
                (earliest, max(dates)),
            )
            for row in cursor.fetchall():
                breadth_map[row["trade_date"]] = (int(row["limit_up"]), int(row["limit_down"]))
                daily_amounts[row["trade_date"]] = float(row["total_amount"])
    except (sqlite3.Error, KeyError, TypeError, ValueError) as e:
        # 调用方通过 breadth_map/daily_amounts 缺失回退为 (0,0)/None，已自然容错
        logger.warning("[market_context] 批量查询涨跌停/成交额失败，使用默认值: %s", e)

    sorted_amount_dates = sorted(daily_amounts.keys())
    amount_pos = {d: i for i, d in enumerate(sorted_amount_dates)}

    # 3. 一次性预计算白线/黄线序列（idx < 60 的日期走默认环境，最小需要 idx-1=59）
    whites, yellows = _precompute_line_series(index_klines, start=59)

    # 4. 逐日期组装 MarketContext（纯内存计算，无 IO）
    for trade_date in dates:
        normalized = trade_date.replace("-", "")
        idx = index_dates.get(normalized)

        if idx is None or idx < 60:
            result[trade_date] = MarketContext(
                date=trade_date,
                regime=MarketRegime.NEUTRAL,
                index_trend=50.0,
                breadth=0.0,
                moneyflow_score=50.0,
                notes=["无指数数据，默认震荡"],
            )
            continue

        trend = _trend_score_from_values(
            whites[idx], yellows[idx], whites[idx - 1], yellows[idx - 1], index_klines[idx].close
        )
        # 广度/资金得分只依赖最近 20 根 K 线，传窗口避免整段切片复制
        window20 = index_klines[idx - 19 : idx + 1]
        breadth = _breadth_approx(window20)
        mf = _moneyflow_score(window20)

        if trend >= 65 and breadth > 0.1 and mf >= 55:
            regime = MarketRegime.STRONG
        elif trend <= 40 or breadth < -0.15 or mf <= 40:
            regime = MarketRegime.WEAK
        else:
            regime = MarketRegime.NEUTRAL

        limit_up, limit_down = breadth_map.get(normalized, (0, 0))

        amt_idx = amount_pos.get(normalized, -1)
        if amt_idx >= 40 and sorted_amount_dates[amt_idx] == normalized:
            recent = sum(daily_amounts[sorted_amount_dates[amt_idx - i]] for i in range(20))
            previous = sum(daily_amounts[sorted_amount_dates[amt_idx - 20 - i]] for i in range(20))
            turnover_trend = recent / previous if previous > 0 else None
        else:
            turnover_trend = None

        turnover_up = turnover_trend is not None and turnover_trend > 1.0
        panic_greed_ratio = limit_up / max(limit_down, 1)

        notes = [f"大盘趋势得分 {trend:.0f}", f"涨跌广度 {breadth:+.2f}", f"资金得分 {mf:.0f}"]
        if limit_up > 0 or limit_down > 0:
            notes.append(f"涨停{limit_up}家/跌停{limit_down}家")
        if panic_greed_ratio > 10 and turnover_up:
            notes.append("情绪贪婪")
        elif panic_greed_ratio < 0.5 or limit_down > 100:
            notes.append("情绪恐慌")
            if regime == MarketRegime.STRONG:
                regime = MarketRegime.WEAK if limit_down > 100 else MarketRegime.NEUTRAL

        result[trade_date] = MarketContext(
            date=trade_date,
            regime=regime,
            index_trend=trend,
            breadth=breadth,
            moneyflow_score=mf,
            notes=notes,
        )

    return result


def max_positions_allowed(context: MarketContext, config_max: int, weak_max: int) -> int:
    """根据市场环境返回当日最大持仓数。"""
    if context.regime == MarketRegime.STRONG:
        return config_max
    if context.regime == MarketRegime.WEAK:
        return weak_max
    return max(config_max - 1, weak_max)

"""v1.0 验收股票池加载器

为少妇战法 v1.0 验收提供质量过滤后的股票池，替代 `stock_basic` 前 N 只的粗暴采样。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from ..database import get_connection
from ..datasource import DataSource, get_datasource
from modules.core.errors import ErrorCode, ZettarancError

logger = logging.getLogger(__name__)

# 默认过滤阈值
DEFAULT_MIN_AVG_AMOUNT = 100_000_000  # 近 60 日日均成交额 ≥ 1 亿
DEFAULT_MIN_LIST_DAYS = 365  # 上市时间 ≥ 1 年
DEFAULT_LOOKBACK_DAYS = 60  # 用于计算流动性和趋势的回看天数

# v3.7.6：多指标分组选股。
# 同一组内的 criteria 是“或”关系；组与组之间默认也是“或”关系（union），
# 但调用方可以只选一个 group，避免左侧低吸 / 右侧突破 / 中周期吸筹等不同风格混在一起。
CRITERIA_GROUPS: dict[str, list[str]] = {
    # 左侧低吸：与少妇战法 B1 入场完全兼容
    "left_pullback": [
        "b1",
        "super_b1",
        "changan",
        "bull_rope",
        "sandglass_perfect",
    ],
    # 右侧突破：当前 PortfolioBacktestEngine 只买 B1，默认不启用；等引擎支持多策略入场后再开
    "right_breakout": [
        "b2_breakout",
        "b3_consensus",
        "breakout",
        "volume_ratio_super",
    ],
    # 中周期位置：判断股票处于吸筹/建仓阶段，和左侧低吸互补
    "stage_accumulation": [
        "build_wave",
        "xishou",
        "safe",
    ],
    # 质量确认：完美图形，可单独用作防守型组合
    "quality_confirm": [
        "perfect",
    ],
}

# v3.7.6 默认选股分组：与当前 B1-only 组合引擎对齐
DEFAULT_VERIFY_POOL_GROUPS = ["left_pullback", "stage_accumulation"]


def _parse_trade_date(date_str: str) -> datetime:
    """把 trade_date 字符串解析为 datetime"""
    return datetime.strptime(date_str, "%Y%m%d")


def _format_trade_date(dt: datetime) -> str:
    """把 datetime 格式化为 trade_date 字符串"""
    return dt.strftime("%Y%m%d")


def _get_latest_trade_date(conn: Any) -> str | None:
    """获取 daily_kline 中最新交易日"""
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(trade_date) as max_date FROM daily_kline")
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def load_v10_stock_pool(
    limit: int = 100,
    min_avg_amount: float = DEFAULT_MIN_AVG_AMOUNT,
    min_list_days: int = DEFAULT_MIN_LIST_DAYS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    top_return_pct: float | None = 0.30,
    exclude_st: bool = True,
    exclude_markets: set[str] | None = None,
) -> list[str]:
    """加载 v1.0 验收股票池

    过滤规则（按执行顺序）：
    1. 市场过滤：默认保留主板/创业板/科创板
    2. 上市时间：≥ min_list_days 天
    3. 排除 ST：name 中包含 "ST" 的股票
    4. 流动性：近 lookback_days 日日均成交额 ≥ min_avg_amount
    5. 趋势：取近 lookback_days 日涨幅前 top_return_pct 的股票

    Args:
        limit: 最终返回股票数量上限
        min_avg_amount: 最小日均成交额（元）
        min_list_days: 最小上市天数
        lookback_days: 流动性和趋势计算回看天数
        top_return_pct: 涨幅分位数阈值，如 0.30 表示取前 30%；None 表示不筛选
        exclude_st: 是否排除 ST 股票
        exclude_markets: 需要排除的市场集合，默认排除北交所/新三板等

    Returns:
        ts_code 列表，按 60 日涨幅降序
    """
    if exclude_markets is None:
        exclude_markets = {"北交所", "新三板"}

    with get_connection() as conn:
        latest_date = _get_latest_trade_date(conn)
        if not latest_date:
            logger.warning("daily_kline 无数据，回退到 stock_basic 前 %d 只", limit)
            return _fallback_stock_codes(limit)

        start_date = _format_trade_date(_parse_trade_date(latest_date) - timedelta(days=lookback_days))

        # 1. 先拿到所有候选股票（含上市日期、市场）
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ts_code, name, market, list_date
            FROM stock_basic
            WHERE market IN ('主板', '创业板', '科创板')
            ORDER BY ts_code
            """
        )
        candidates = [
            {
                "ts_code": row[0],
                "name": row[1] or "",
                "market": row[2] or "",
                "list_date": row[3] or "",
            }
            for row in cursor.fetchall()
        ]

    # 2. 市场和上市时间过滤
    latest_dt = _parse_trade_date(latest_date)
    min_list_date = _format_trade_date(latest_dt - timedelta(days=min_list_days))

    filtered: list[dict[str, Any]] = []
    for stock in candidates:
        market = stock["market"]
        if market in exclude_markets:
            continue
        list_date = stock["list_date"]
        if not list_date or list_date > min_list_date:
            continue
        if exclude_st and "ST" in stock["name"]:
            continue
        filtered.append(stock)

    if not filtered:
        logger.warning("基础过滤后无候选股票，回退到 stock_basic 前 %d 只", limit)
        return _fallback_stock_codes(limit)

    # 3. 计算流动性和趋势（按 ts_code 批量 SQL）
    codes = [s["ts_code"] for s in filtered]
    stats = _calc_liquidity_and_return(codes, start_date, latest_date)

    # 4. 流动性过滤
    liquid = []
    for stock in filtered:
        ts_code = stock["ts_code"]
        stat = stats.get(ts_code)
        if not stat:
            continue
        if stat["avg_amount"] < min_avg_amount:
            continue
        stock["avg_amount"] = stat["avg_amount"]
        stock["return_pct"] = stat["return_pct"]
        liquid.append(stock)

    if not liquid:
        logger.warning(
            "流动性过滤后无候选股票（min_avg_amount=%.0f），回退到 stock_basic 前 %d 只",
            min_avg_amount,
            limit,
        )
        return _fallback_stock_codes(limit)

    # 5. 趋势过滤：取涨幅前 top_return_pct
    if top_return_pct is not None:
        liquid.sort(key=lambda s: s["return_pct"], reverse=True)
        keep_count = max(1, int(len(liquid) * top_return_pct))
        liquid = liquid[:keep_count]

    # 6. 最终截断到 limit
    liquid = liquid[:limit]

    logger.info(
        "v10 股票池：候选=%d，流动性过滤后=%d，最终=%d",
        len(candidates),
        len([s for s in filtered if s["ts_code"] in stats and stats[s["ts_code"]]["avg_amount"] >= min_avg_amount]),
        len(liquid),
    )
    return [s["ts_code"] for s in liquid]


def _calc_liquidity_and_return(
    ts_codes: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, float]]:
    """批量计算候选股票的近段日均成交额和区间涨幅

    使用 SQL 聚合避免逐股拉取 K 线，提升加载速度。
    """
    if not ts_codes:
        return {}

    with get_connection() as conn:
        cursor = conn.cursor()
        # 使用占位符批量查询
        placeholders = ",".join("?" * len(ts_codes))
        cursor.execute(
            f"""
            SELECT
                ts_code,
                AVG(amount) as avg_amount,
                MIN(trade_date) as first_date,
                MAX(trade_date) as last_date
            FROM daily_kline
            WHERE ts_code IN ({placeholders})
              AND trade_date >= ?
              AND trade_date <= ?
            GROUP BY ts_code
            """,
            (*ts_codes, start_date, end_date),
        )
        agg = {
            row[0]: {
                "avg_amount": row[1] or 0.0,
                "first_date": row[2],
                "last_date": row[3],
            }
            for row in cursor.fetchall()
        }

        # 需要首尾收盘价计算区间涨幅
        # 分别取每只股票的首尾交易日收盘价
        stats: dict[str, dict[str, float]] = {}
        for code in ts_codes:
            info = agg.get(code)
            if not info or info["avg_amount"] == 0:
                continue
            cursor.execute(
                "SELECT close FROM daily_kline WHERE ts_code = ? AND trade_date = ?",
                (code, info["first_date"]),
            )
            first_row = cursor.fetchone()
            cursor.execute(
                "SELECT close FROM daily_kline WHERE ts_code = ? AND trade_date = ?",
                (code, info["last_date"]),
            )
            last_row = cursor.fetchone()
            if not first_row or not last_row:
                continue
            first_close = first_row[0]
            last_close = last_row[0]
            if first_close <= 0:
                continue
            stats[code] = {
                "avg_amount": float(info["avg_amount"]),
                "return_pct": (last_close - first_close) / first_close,
            }
        return stats


def _fallback_stock_codes(limit: int) -> list[str]:
    """无数据时的兜底：按 ts_code 排序取前 limit 只"""
    from ..database import get_all_stock_codes

    return get_all_stock_codes(limit=limit)


def _resolve_group_definitions(
    groups: list[str] | dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    """把 group 名称列表或自定义字典解析为 {group_name: [criteria]}"""
    if groups is None:
        return {g: CRITERIA_GROUPS[g] for g in DEFAULT_VERIFY_POOL_GROUPS}
    if isinstance(groups, dict):
        return {k: [c.strip() for c in v if c.strip()] for k, v in groups.items() if v}

    group_defs: dict[str, list[str]] = {}
    for name in groups:
        name = name.strip()
        if not name:
            continue
        if name not in CRITERIA_GROUPS:
            logger.warning("未知选股分组: %s，已跳过", name)
            continue
        group_defs[name] = CRITERIA_GROUPS[name]
    return group_defs


def _merge_group_results(
    group_results: dict[str, list[Any]],
    mode: str,
) -> list[Any]:
    """合并多个分组的选股结果

    mode:
      - union: 各分组命中结果去重合并
      - intersection: 仅保留在每个分组都至少命中一个 criteria 的股票
    """
    if mode not in ("union", "intersection"):
        raise ZettarancError(
            ErrorCode.INVALID_PARAM,
            f"不支持的合并模式: {mode}，仅支持 union / intersection",
        )

    if mode == "union":
        merged: dict[str, Any] = {}
        for scores in group_results.values():
            for s in scores:
                existing = merged.get(s.ts_code)
                if existing is None or s.score > existing.score:
                    merged[s.ts_code] = s
    else:
        # intersection: 每个分组都命中的股票；任意分组为空则结果为空
        code_sets = [set(s.ts_code for s in scores) for scores in group_results.values()]
        if not code_sets or any(not s for s in code_sets):
            return []
        common = set.intersection(*code_sets)
        merged = {}
        for scores in group_results.values():
            for s in scores:
                if s.ts_code in common:
                    existing = merged.get(s.ts_code)
                    if existing is None or s.score > existing.score:
                        merged[s.ts_code] = s

    result = list(merged.values())
    result.sort(key=lambda s: s.score, reverse=True)
    return result


def load_v10_stock_pool_multi_criteria(
    groups: list[str] | dict[str, list[str]] | None = None,
    limit: int = 200,
    mode: str = "union",
    min_avg_amount: float = DEFAULT_MIN_AVG_AMOUNT,
    min_list_days: int = DEFAULT_MIN_LIST_DAYS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    datasource: DataSource | None = None,
) -> list[str]:
    """多指标分组选股池加载器（v3.7.6）

    流程：
      1. 先用基础质量过滤得到候选集（默认 500 只）。
      2. 对每个分组内的 criteria，逐个分析候选股票并判断是否符合。
      3. 按 mode 合并各分组结果，去重后按综合评分降序取前 limit。
      4. 若结果为空，回退到基础质量池。

    Args:
        groups: 分组名称列表（如 ["left_pullback", "stage_accumulation"]）
                或自定义字典（如 {"custom": ["b1", "super_b1"] }）
        limit: 最终返回数量
        mode: union（并集）或 intersection（交集）
        min_avg_amount / min_list_days / lookback_days: 基础质量过滤参数
        datasource: 可选数据源注入

    Returns:
        ts_code 列表
    """
    group_defs = _resolve_group_definitions(groups)
    if not group_defs:
        logger.warning("没有有效的选股分组，回退到基础质量池")
        return load_v10_stock_pool(limit=limit, top_return_pct=None)

    base_limit = max(500, limit)
    base_pool = load_v10_stock_pool(
        limit=base_limit,
        min_avg_amount=min_avg_amount,
        min_list_days=min_list_days,
        lookback_days=lookback_days,
        top_return_pct=None,
    )
    if not base_pool:
        logger.warning("基础质量池为空，回退到 stock_basic 前 %d 只", limit)
        return _fallback_stock_codes(limit)

    # 局部 import 避免循环依赖
    from ..screener.criteria import _CRITERIA_REGISTRY
    from ..screener.data import get_recent_klines
    from ..screener.engine import analyze_stock

    group_results: dict[str, list[Any]] = {}

    for group_name, criteria_names in group_defs.items():
        matched: dict[str, Any] = {}
        for code in base_pool:
            try:
                klines = get_recent_klines(code, days=lookback_days, datasource=datasource)
                if len(klines) < 30:
                    continue
                score = analyze_stock(code, klines=klines, datasource=datasource)
            except Exception as e:  # noqa: BLE001
                logger.debug("分析 %s 失败: %s", code, e)
                continue

            for criteria in criteria_names:
                handler = _CRITERIA_REGISTRY.get(criteria)
                if handler is None:
                    logger.debug("未知 criteria: %s", criteria)
                    continue
                try:
                    if handler(klines, score):
                        matched[code] = score
                        break
                except Exception as e:  # noqa: BLE001
                    logger.debug("criteria %s 在 %s 上失败: %s", criteria, code, e)
                    continue

        group_results[group_name] = list(matched.values())
        logger.debug("分组 %s 命中 %d 只", group_name, len(matched))

    merged_scores = _merge_group_results(group_results, mode)
    merged_scores.sort(key=lambda s: s.score, reverse=True)
    result = [s.ts_code for s in merged_scores[:limit]]

    if not result:
        logger.warning(
            "多指标选股结果为空（groups=%s, mode=%s），回退到基础质量池",
            list(group_defs.keys()),
            mode,
        )
        return load_v10_stock_pool(limit=limit, top_return_pct=None)

    logger.info(
        "多指标选股池：groups=%s, mode=%s, 命中=%d, 最终=%d",
        list(group_defs.keys()),
        mode,
        len(merged_scores),
        len(result),
    )
    return result


def load_v10_stock_pool_via_screener(
    limit: int = 100,
    criteria: str = "b1",
    min_avg_amount: float = DEFAULT_MIN_AVG_AMOUNT,
    min_list_days: int = DEFAULT_MIN_LIST_DAYS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    top_return_pct: float | None = 0.30,
    datasource: DataSource | None = None,
) -> list[str]:
    """通过 screener 预选后再做质量过滤（较慢，可选）

    流程：
    1. 先做基础质量过滤（流动性/上市时间/ST）
    2. 对过滤后股票调用 screener 评分
    3. 取评分前 limit 只
    """
    from ..screener.engine import screen_stocks

    base_pool = load_v10_stock_pool(
        limit=500,
        min_avg_amount=min_avg_amount,
        min_list_days=min_list_days,
        lookback_days=lookback_days,
        top_return_pct=top_return_pct,
    )
    if not base_pool:
        return []

    if datasource is None:
        datasource = get_datasource(preferred="auto")

    # screener 目前不支持传入指定股票池，只能全市场扫描后截取
    # 因此这里先扫描再过滤到 base_pool
    screened = screen_stocks(
        criteria=criteria,
        max_stocks=max(500, len(base_pool) * 2),
        datasource=datasource,
    )
    codes_set = set(base_pool)
    filtered = [s for s in screened if s.ts_code in codes_set]
    filtered = filtered[:limit]
    logger.info(
        "screener 预选后：base_pool=%d，screened=%d，最终=%d",
        len(base_pool),
        len(filtered),
        len(filtered),
    )
    return [s.ts_code for s in filtered]

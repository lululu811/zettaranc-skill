#!/usr/bin/env python3
"""活跃市值（0AMV）全局交易闸门 —— 闸门判定的唯一实现。

对外只暴露一个 interface：

    evaluate(date, config) -> GateAction

调用方只问"这个交易日能不能开仓 / 要不要强平"，不必知道阈值、数据源路径
或失败降级策略——那些都在 implementation 内部。回测 engine 通过注入闸门
port 使用它，测试用假闸门 adapter 替身。

阈值口径与 :mod:`modules.active_market_value` 的"活跃市值信号"不同：信号看
**当日**涨跌幅，闸门看**两日累计**涨幅。数值相同纯属巧合，两者是两组阈值。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import bisect

from .active_market_value import (
    ActiveMarketValuePoint,
    _load_index_and_rows,
    _normalize_query_date,
)

logger = logging.getLogger(__name__)


class GateAction(StrEnum):
    """活跃市值全局闸门动作。

    - OPEN  - 允许开新仓
    - WAIT  - 观望（不开新仓、不平仓）
    - CLEAR - 强平（清仓所有/当前持仓）

    刻意用 StrEnum：闸门动作只有这一种表示，枚举本身就是字符串，
    既兼容既有调用方的字符串比较，也让"枚举 vs 字符串"不再是错误类别。
    StrEnum 的 __str__ 直接给出 "OPEN"，f-string 不会打印 "GateAction.OPEN"。
    """

    OPEN = "OPEN"
    WAIT = "WAIT"
    CLEAR = "CLEAR"


@dataclass(frozen=True)
class GateThresholds:
    """闸门阈值：按【两日累计】涨幅判定开仓 / 清仓。

    与 :class:`modules.active_market_value.SignalThresholds` 是两组不同语义的
    阈值——口径不同（当日 vs 两日累计），用途不同（多空读数 vs 交易闸门）。
    数值相同纯属巧合，不可合并。
    """

    open: float = 4.0
    clear: float = -2.3
    open_lookback: int = 2


GATE_THRESHOLDS = GateThresholds()


@dataclass(frozen=True)
class GateConfig:
    """闸门配置：是否生效，以及闸门从何处读取数据。"""

    enabled: bool = True
    duckdb_path: str | None = None
    path: str | None = None


def _cum_pct(rows: list[ActiveMarketValuePoint], idx: int, lookback: int) -> float | None:
    """计算第 idx 天相对前 lookback 个交易日收盘的累计涨幅（%）。"""
    if idx < lookback:
        return None
    base = rows[idx - lookback].close
    if base <= 0:
        return None
    return (rows[idx].close / base - 1.0) * 100.0


def _decide(
    date: str | None,
    thresholds: GateThresholds,
    path: str | None,
    duckdb_path: str | None,
) -> GateAction:
    """纯判定：给定阈值与数据源，给出闸门动作。无数据一律 WAIT（fail-closed）。"""
    rows, index = _load_index_and_rows(path, duckdb_path)
    if not rows:
        return GateAction.WAIT

    if date is None:
        idx = len(rows) - 1
    else:
        target = _normalize_query_date(date)
        # index 是 date→point 的 O(1) 字典，先验证存在；rows 本身 date-asc，
        # 用 bisect 把 target → idx 走 O(log n)，替代原来的 O(n) 线性扫描
        if target not in index:
            return GateAction.WAIT
        idx = bisect.bisect_left([r.date for r in rows], target)

    point = rows[idx]
    cum = _cum_pct(rows, idx, thresholds.open_lookback)

    if point.pct_chg <= thresholds.clear:
        return GateAction.CLEAR
    if cum is not None and cum <= thresholds.clear:
        return GateAction.CLEAR
    if cum is not None and cum > thresholds.open:
        return GateAction.OPEN
    return GateAction.WAIT


def evaluate(date: str | None = None, config: GateConfig | None = None) -> GateAction:
    """闸门判定 —— 本 module 的唯一 interface。

    规则：
    - 闸门关闭（enabled=False）→ OPEN（不限制任何行为）
    - 两日累计涨幅 > open 阈值（默认 +4%）→ OPEN，允许开仓
    - 当日跌幅 <= clear 阈值（默认 -2.3%）或累计跌幅 <= clear 阈值 → CLEAR，清仓
    - 其余 → WAIT，不开新仓
    - 无数据（两个数据源都空 / 日期不在索引里）→ WAIT
    - 加载异常 → WAIT（fail-closed：闸门存在却读不到数据时放行开仓等于伪造信号）

    Args:
        date: YYYYMMDD 或 YYYY-MM-DD 格式交易日；None 表示最新一日。
        config: 闸门配置；None 等价于 GateConfig()。

    Returns:
        GateAction（OPEN / WAIT / CLEAR）。
    """
    cfg = config or GateConfig()
    if not cfg.enabled:
        return GateAction.OPEN
    try:
        return _decide(date, GATE_THRESHOLDS, cfg.path, cfg.duckdb_path)
    except Exception:  # noqa: BLE001
        # 闸门查询失败时保守返回 WAIT，不让异常阻断回测主流程
        logger.warning("[active_mv_gate] 闸门查询失败，降级为 WAIT", exc_info=True)
        return GateAction.WAIT


# ---- 兼容层：v4.3 之前的公开 API 路径 ----
# 旧路径 `from modules.active_market_value import get_active_market_gate` 已由
# modules/active_market_value.py 的 __getattr__ 转出，这里保留实现。


def get_active_market_gate(
    date: str | None = None,
    open_lookback: int = GATE_THRESHOLDS.open_lookback,
    open_threshold: float = GATE_THRESHOLDS.open,
    clear_threshold: float = GATE_THRESHOLDS.clear,
    path: str | None = None,
    duckdb_path: str | None = None,
) -> GateAction:
    """兼容层：闸门判定（可显式指定阈值）。

    返回 GateAction。枚举继承 str，历史调用方的字符串比较与 isinstance 断言
    继续成立。
    """
    thresholds = GateThresholds(
        open=open_threshold,
        clear=clear_threshold,
        open_lookback=open_lookback,
    )
    return _decide(date, thresholds, path, duckdb_path)


def apply_active_mv_gate(
    date: str,
    *,
    enabled: bool = True,
    duckdb_path: str | None = None,
    path: str | None = None,
) -> GateAction:
    """兼容层：闸门统一入口（v4.3+ 替代各 engine 自己的 _gate 实现）。

    Note:
        各 backtest engine 应在自己的循环里问闸门 port 拿动作，
        拿到 GateAction 后决定：WAIT 跳过开仓、CLEAR 触发自己的强平逻辑。
        强平 scope（当前持仓 vs 所有持仓）由各 engine 自己决定，因为单股 vs
        组合上下文不同。
    """
    return evaluate(date, GateConfig(enabled=enabled, duckdb_path=duckdb_path, path=path))

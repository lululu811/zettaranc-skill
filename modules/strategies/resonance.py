"""共振检测器 —— 回测循环专用的轻量策略检测。

这些检测器从 loop_engine.py 提取而来，服务于多策略共振投票（_vote_signals）。
与 strategies/compound_strategies.py 中的同名检测器的区别：

- 本模块的检测器为回测循环设计，追求速度（每根 K 线调用一次）
- 输入只有 klines（无 index、无 kirin_context）
- 输出是 dict | None（无 StrategySignal 开销）
- 无 MDC 评分、无置信度计算

strategies/compound_strategies.py 中的检测器为选股/诊断设计，追求精度，
带 MDC 多维验证和置信度打分。两套检测器口径不同，保留共存。

口径差异示例：
- 长安：本模块缩半量用 0.6，compound_strategies 用 0.5（严格 20%）
- 娜娜：本模块要求 1 天放量涨，compound_strategies 要求 3 天北斗放量涨
- 平行重炮：本模块固定 5 天窗口，compound_strategies 动态搜索 7 天窗口
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ..indicators import calculate_kdj
from ..indicators.core import DailyData
from ..indicators.price_patterns.screener_helper import detect_b1_today

logger = logging.getLogger(__name__)


class SignalDetector(Protocol):
    """轻量策略检测器协议——回测循环专用。"""

    def __call__(self, klines: list[DailyData]) -> dict[str, Any] | None: ...


def detect_b2_resonance(klines: list[DailyData]) -> dict[str, Any] | None:
    """B2: B1 后放量长阳确认（前 5-15 日出现过 B1 + 当日涨幅≥4% + 放量）。"""
    if len(klines) < 20:
        return None
    today = klines[-1]
    yesterday = klines[-2]
    if yesterday.close <= 0:
        return None
    price_change = (today.close - yesterday.close) / yesterday.close
    if price_change < 0.04:
        return None
    if yesterday.vol > 0 and today.vol < yesterday.vol * 1.5:
        return None
    has_b1_recent = False
    for i in range(max(0, len(klines) - 15), len(klines) - 1):
        b1 = detect_b1_today(klines[: i + 1])
        if b1.get("is_b1"):
            has_b1_recent = True
            break
    if not has_b1_recent:
        return None
    return {
        "price_change": price_change,
        "volume_ratio": today.vol / yesterday.vol if yesterday.vol > 0 else 0,
    }


def detect_changan_resonance(klines: list[DailyData]) -> dict[str, Any] | None:
    """长安战法：三日 B1 + 放量阳 + 缩半量。"""
    if len(klines) < 5:
        return None
    day2_prev = klines[-4]
    day2 = klines[-2]
    day3 = klines[-1]
    kdj = calculate_kdj(klines[:-2])
    j_val = kdj[2] if isinstance(kdj, tuple) else kdj.j
    if j_val >= -13:
        return None
    if day2_prev.close <= 0:
        return None
    day2_change = (day2.close - day2_prev.close) / day2_prev.close
    if day2_change < 0.04:
        return None
    if day2.close < day2.open:
        return None
    if day2_prev.vol > 0 and day2.vol < day2_prev.vol * 1.3:
        return None
    if day2.close <= 0:
        return None
    day3_change = (day3.close - day2.close) / day2.close
    if day3_change < 0 or day3_change > 0.02:
        return None
    if day3.close < day3.open:
        return None
    if day2.vol > 0 and day3.vol > day2.vol * 0.6:
        return None
    return {
        "day1_j": j_val,
        "day2_change": day2_change,
        "day3_change": day3_change,
    }


def detect_nana_resonance(klines: list[DailyData]) -> dict[str, Any] | None:
    """娜娜图形：放量涨 + 缩量回调 + J < 0。"""
    if len(klines) < 10:
        return None
    kdj = calculate_kdj(klines)
    j_val = kdj[2] if isinstance(kdj, tuple) else kdj.j
    if j_val >= 0:
        return None
    has_volume_up = False
    for i in range(max(0, len(klines) - 6), len(klines) - 2):
        day = klines[i]
        prev = klines[i - 1] if i > 0 else None
        if prev and day.close > prev.close and day.vol > prev.vol:
            has_volume_up = True
            break
    if not has_volume_up:
        return None
    shrink_days = 0
    for i in range(len(klines) - 3, len(klines) - 1):
        day = klines[i]
        prev = klines[i - 1] if i > 0 else None
        if prev and day.vol < prev.vol * 0.8:
            shrink_days += 1
    if shrink_days < 2:
        return None
    return {"j_value": j_val, "shrink_days": shrink_days}


def detect_pinghang_resonance(klines: list[DailyData]) -> dict[str, Any] | None:
    """平行重炮：双阳夹阴 + 第二阳≥4% + J < 55。"""
    if len(klines) < 5:
        return None
    kdj = calculate_kdj(klines)
    j_val = kdj[2] if isinstance(kdj, tuple) else kdj.j
    if j_val >= 55:
        return None
    day1, day2, day3, day4 = klines[-5], klines[-4], klines[-3], klines[-2]
    if not (
        day1.close > day1.open and day2.close < day2.open and day3.close < day3.open and day4.close > day4.open
    ):
        return None
    if day3.close <= 0:
        return None
    day4_change = (day4.close - day3.close) / day3.close
    if day4_change < 0.04:
        return None
    if day2.vol > 0 and day1.vol < day2.vol * 1.2:
        return None
    if day3.vol > 0 and day4.vol < day3.vol * 1.2:
        return None
    return {"j_value": j_val, "day4_change": day4_change}


# 检测器注册表
DETECTOR_REGISTRY: dict[str, SignalDetector] = {
    "B2": detect_b2_resonance,
    "长安": detect_changan_resonance,
    "娜娜": detect_nana_resonance,
    "平行重炮": detect_pinghang_resonance,
}


__all__ = [
    "SignalDetector",
    "detect_b2_resonance",
    "detect_changan_resonance",
    "detect_nana_resonance",
    "detect_pinghang_resonance",
    "DETECTOR_REGISTRY",
]

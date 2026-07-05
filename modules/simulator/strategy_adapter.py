#!/usr/bin/env python3
"""
战法信号适配层。

把 modules.strategies.StrategySignal 转换为模拟器内部统一的 RawStrategySignal，
负责标准化命名、分类、动作，并提供日期过滤与同类型去重。
"""

from __future__ import annotations

from datetime import datetime

from ..strategies import StrategySignal
from . import RawStrategySignal


# 原始 strategy.value -> (strategy_name, category, action)
STRATEGY_MAPPING: dict[str, tuple[str, str, str]] = {
    "B1": ("B1", "rebound", "BUY"),
    "B2": ("B2", "breakout", "BUY"),
    "B3": ("B3", "consensus", "BUY"),
    "SB1": ("超级B1", "rebound", "BUY"),
    "长安战法": ("长安", "breakout", "BUY"),
    "四分之三阴量": ("四分之三阴量", "rebound", "BUY"),
    "娜娜图形": ("娜娜", "pattern", "BUY"),
    "异动+地量地价": ("异动地量", "rebound", "BUY"),
    "平行重炮": ("平行重炮", "breakout", "BUY"),
    "坑里起好货": ("坑里起好货", "rebound", "BUY"),
    "对称 VA": ("对称VA", "pattern", "BUY"),
    "S1": ("S1", "risk", "SELL"),
    "S2": ("S2", "risk", "SELL"),
    "S3": ("S3", "risk", "SELL"),
    "四块砖翻绿": ("砖形图翻绿", "risk", "SELL"),
    "四块砖减仓": ("砖形图减仓", "risk", "SELL"),
    "四块砖反弹": ("砖形图反弹", "stage", "WATCH"),
    "买盘枯竭": ("买盘枯竭", "risk", "SELL"),
    "绿肥红瘦": ("绿肥红瘦", "risk", "SELL"),
    "阶梯放量下跌": ("阶梯放量下跌", "risk", "SELL"),
    "顶部大风车": ("顶部大风车", "risk", "SELL"),
    "麒麟·吸筹": ("麒麟吸筹", "stage", "WATCH"),
    "麒麟·拉升": ("麒麟拉升", "stage", "HOLD"),
    "麒麟·派发": ("麒麟派发", "stage", "SELL"),
    "麒麟·回落": ("麒麟回落", "stage", "SELL"),
    "滴滴战法": ("滴滴战法", "risk", "SELL"),
    "MACD 金叉空": ("MACD金叉空", "risk", "SELL"),
    "MACD 死叉多": ("MACD死叉多", "rebound", "BUY"),
    "出货五式": ("出货五式", "risk", "SELL"),
    "量比攻击": ("量比攻击", "breakout", "WATCH"),
    "灾后重建": ("灾后重建", "rebound", "BUY"),
    "跃跃欲试": ("跃跃欲试", "breakout", "BUY"),
    "关键K": ("关键K", "pattern", "BUY"),
}


# 三波理论前缀与输出映射
_THREE_WAVE_PREFIX = "三波理论·"
_THREE_WAVE_MAP: dict[str, tuple[str, str, str]] = {
    "建仓波": ("三波建仓", "stage", "BUY"),
    "拉升波": ("三波拉升", "stage", "HOLD"),
    "冲刺波": ("三波冲刺", "stage", "SELL"),
}


def _parse_three_wave(sig: StrategySignal) -> RawStrategySignal | None:
    """若信号描述或原因包含三波理论前缀，解析并返回对应 RawStrategySignal。"""
    text = sig.reason or sig.description or ""
    if not text.startswith(_THREE_WAVE_PREFIX):
        return None
    wave_name = text[len(_THREE_WAVE_PREFIX):].split("：", 1)[0].split(":", 1)[0]
    mapped = _THREE_WAVE_MAP.get(wave_name)
    if not mapped:
        return None
    name, category, action = mapped
    return RawStrategySignal(
        strategy=name,
        category=category,
        action=action,
        confidence=float(sig.confidence or 0.0),
        trade_date=str(sig.trade_date or ""),
        reason=text,
    )


def adapt(signals: list[StrategySignal]) -> list[RawStrategySignal]:
    """把 StrategySignal 列表转换为 RawStrategySignal 列表。"""
    result: list[RawStrategySignal] = []
    for sig in signals:
        # 优先处理三波理论：以 description/reason 中的波次名称为准
        three_wave = _parse_three_wave(sig)
        if three_wave:
            result.append(three_wave)
            continue

        mapped = STRATEGY_MAPPING.get(sig.strategy.value)
        if not mapped:
            continue
        name, category, action = mapped
        # 关键K 特殊处理：根据 description 判断方向
        if name == "关键K":
            action = "SELL" if "阴破位" in (sig.reason or sig.description or "") else "BUY"
        result.append(
            RawStrategySignal(
                strategy=name,
                category=category,
                action=action,
                confidence=float(sig.confidence or 0.0),
                trade_date=str(sig.trade_date or ""),
                reason=str(sig.reason or sig.description or ""),
            )
        )
    return result


def filter_by_date(
    signals: list[RawStrategySignal],
    trade_date: str,
    lookback_days: int = 5,
) -> list[RawStrategySignal]:
    """保留 trade_date 当日及之前 lookback_days 个交易日内的信号。

    为简化实现，日期差按自然日计算；若输入日期格式非法则回退为字符串比较。
    """
    try:
        end_dt = datetime.strptime(trade_date, "%Y%m%d")
    except ValueError:
        return [s for s in signals if s.trade_date and s.trade_date <= trade_date]

    filtered: list[RawStrategySignal] = []
    for s in signals:
        if not s.trade_date or s.trade_date > trade_date:
            continue
        try:
            sig_dt = datetime.strptime(s.trade_date, "%Y%m%d")
        except ValueError:
            continue
        if (end_dt - sig_dt).days <= lookback_days:
            filtered.append(s)
    return filtered


def deduplicate(signals: list[RawStrategySignal]) -> list[RawStrategySignal]:
    """同一天同一 strategy 保留 confidence 最高的一条。"""
    best: dict[tuple[str, str], RawStrategySignal] = {}
    for s in signals:
        key = (s.strategy, s.trade_date)
        if key not in best or s.confidence > best[key].confidence:
            best[key] = s
    return list(best.values())

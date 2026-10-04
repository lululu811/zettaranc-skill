"""选股筛选条件注册表。"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from .data import _dict_to_daily

if TYPE_CHECKING:
    from .models import StockScore


CriteriaFn = Callable[[list, "StockScore"], bool]

_CRITERIA_REGISTRY: dict[str, CriteriaFn] = {}

logger = logging.getLogger(__name__)


def _register(name: str):
    """装饰器：注册筛选条件处理函数"""

    def decorator(fn: CriteriaFn) -> CriteriaFn:
        """内层装饰器：把处理函数注册到 _CRITERIA_REGISTRY 并原样返回。"""
        _CRITERIA_REGISTRY[name] = fn
        return fn

    return decorator


# ---------- 硬过滤 ----------


def _check_centipede(klines) -> bool:
    """蜈蚣图硬过滤：呼吸紊乱的票直接排除"""
    try:
        from ..indicators import detect_centipede_pattern

        return bool(detect_centipede_pattern(klines).get("is_centipede"))
    except (KeyError, ValueError, AttributeError, TypeError, ArithmeticError) as e:
        # 判定失败 → 当作"非蜈蚣图"(不过滤)；调用方已经把 false 当作兜底。
        logger.warning("[criteria] 蜈蚣图检测失败，不触发过滤: %s", e)
        return False


def _check_sandglass_min(klines, min_score: int = 50) -> bool:
    """沙漏最低分过滤"""
    try:
        from ..indicators import calculate_sandglass_score

        return calculate_sandglass_score(klines).get("score", 0) < min_score
    except (KeyError, ValueError, AttributeError, TypeError, ArithmeticError) as e:
        # 评分失败 → 当作"未低于最低分"(不进入过滤)；调用方已经把 false 当作兜底。
        logger.warning("[criteria] 沙漏最低分检测失败，不触发过滤: %s", e)
        return False


# ---------- 基础评分条件 ----------


@_register("b1")
def _criteria_b1(klines, score: "StockScore") -> bool:
    return score.b1_score >= 50


@_register("perfect")
def _criteria_perfect(klines, score: "StockScore") -> bool:
    return score.score >= 65


@_register("oversold")
def _criteria_oversold(klines, score: "StockScore") -> bool:
    return score.trend_score <= 40


@_register("breakout")
def _criteria_breakout(klines, score: "StockScore") -> bool:
    return score.volume_score >= 70


# ---------- 高级战法条件 ----------


@_register("super_b1")
def _criteria_super_b1(klines, score: "StockScore") -> bool:
    from ..strategies import detect_sb1

    for i in range(max(10, len(klines) - 5), len(klines)):
        sig = detect_sb1(klines, i)
        if sig:
            score.warnings.append(f"超级B1 J={sig.details.get('j', 0):.1f}")
            return True
    return False


@_register("changan")
def _criteria_changan(klines, score: "StockScore") -> bool:
    from ..strategies import detect_changan

    for i in range(max(3, len(klines) - 5), len(klines)):
        sig = detect_changan(klines, i)
        if sig:
            score.reasons.append("长安战法 胜率75%")
            return True
    return False


@_register("b2_breakout")
def _criteria_b2_breakout(klines, score: "StockScore") -> bool:
    from ..strategies import detect_b2

    for i in range(max(15, len(klines) - 5), len(klines)):
        sig = detect_b2(klines, i)
        if sig:
            score.reasons.append(f"B2突破 涨{sig.details.get('pct_chg', 0):.1f}%")
            return True
    return False


@_register("b3_consensus")
def _criteria_b3_consensus(klines, score: "StockScore") -> bool:
    from ..strategies import detect_b3

    for i in range(max(20, len(klines) - 5), len(klines)):
        sig = detect_b3(klines, i)
        if sig:
            score.reasons.append("B3分歧转一致")
            return True
    return False


# ---------- P2 指标（三波/麒麟） ----------


@_register("build_wave")
def _criteria_build_wave(klines, score: "StockScore") -> bool:
    from ..indicators import detect_three_waves

    wave = detect_three_waves(klines)
    if wave["wave"] == "建仓波" and wave["confidence"] >= 0.5:
        score.reasons.append(f"建仓波(conf={wave['confidence']})")
        return True
    return False


@_register("xishou")
def _criteria_xishou(klines, score: "StockScore") -> bool:
    from ..indicators import detect_kirin_stage

    kirin = detect_kirin_stage(klines)
    if kirin["stage"] == "吸筹" and kirin["confidence"] >= 0.5:
        score.reasons.append(f"吸筹({kirin['sub_type']}, conf={kirin['confidence']})")
        return True
    return False


@_register("safe")
def _criteria_safe(klines, score: "StockScore") -> bool:
    from ..indicators import detect_three_waves, detect_kirin_stage

    wave = detect_three_waves(klines)
    kirin = detect_kirin_stage(klines)
    is_safe = wave["wave"] != "冲刺波" and kirin["stage"] not in ("派发", "回落")
    if is_safe:
        score.reasons.append(f"安全：{wave['wave']}+{kirin['stage']}")
    return is_safe


# ---------- P3 指标 ----------


@_register("bull_rope")
def _criteria_bull_rope(klines, score: "StockScore") -> bool:
    from ..indicators import detect_bull_rope

    daily_klines = _dict_to_daily(klines)
    rope = detect_bull_rope(daily_klines)
    if rope.get("status") == "牵牛" and rope.get("is_bullish"):
        score.reasons.append(f"牛绳·牵牛(gap={rope['gap_pct']}%)")
        return True
    return False


@_register("sandglass_perfect")
def _criteria_sandglass_perfect(klines, score: "StockScore") -> bool:
    from ..indicators import calculate_sandglass_score

    daily_klines = _dict_to_daily(klines)
    sg = calculate_sandglass_score(daily_klines)
    if sg.get("is_perfect") or sg.get("score", 0) >= 80:
        score.reasons.append(f"沙漏完美图形({sg['score']}分)")
        return True
    return False


@_register("volume_ratio_super")
def _criteria_volume_ratio_super(klines, score: "StockScore") -> bool:
    from ..indicators import detect_volume_ratio_strategy

    daily_klines = _dict_to_daily(klines)
    vr = detect_volume_ratio_strategy(daily_klines)
    if vr.get("action") == "立即买" or vr.get("scenario") in ("超级攻击", "攻击日", "单向拉升"):
        score.reasons.append(f"量比战法·{vr['scenario']}(量比={vr['vol_ratio']})")
        return True
    return False


# ---------- 简单完美图形（笔记《交易系统.md》§2.2.3 三种形态）----------


def _apply_simple_perfect(klines, score: "StockScore", index: int, label: str) -> bool:
    """调用 simple_perfect 模块的第 index 种形态判定，命中时把 reasons 并入 score"""
    from .simple_perfect import (
        detect_simple_perfect_1,
        detect_simple_perfect_2,
        detect_simple_perfect_3,
    )

    detectors = (detect_simple_perfect_1, detect_simple_perfect_2, detect_simple_perfect_3)
    try:
        result = detectors[index - 1](klines)
    except (KeyError, ValueError, IndexError, TypeError, AttributeError, ArithmeticError) as e:
        logger.warning("[criteria] %s 判定失败: %s", label, e)
        return False

    if not result.get("is_match"):
        return False

    score.reasons.append(f"{label}：" + "；".join(result.get("reasons", [])))
    return True


@_register("simple_perfect_1")
def _criteria_simple_perfect_1(klines, score: "StockScore") -> bool:
    return _apply_simple_perfect(klines, score, 1, "简单完美图形-1·经典")


@_register("simple_perfect_2")
def _criteria_simple_perfect_2(klines, score: "StockScore") -> bool:
    return _apply_simple_perfect(klines, score, 2, "简单完美图形-2·异动后横盘")


@_register("simple_perfect_3")
def _criteria_simple_perfect_3(klines, score: "StockScore") -> bool:
    return _apply_simple_perfect(klines, score, 3, "简单完美图形-3·完美绿帽")

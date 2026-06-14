from typing import Any
from ..core import DailyData, calculate_slope
from .base import calculate_zg_white, calculate_dg_yellow


def detect_bull_rope(klines: list[DailyData]) -> dict:
    """
    牛绳理论量化检测

    核心逻辑（源自 Z 哥语料 trend-lines.md）：
    - 白线在黄线上 = 主力牵着牛绳，任何下跌都是洗盘
    - 白线在黄线下 = 牛绳断了，任何上涨都是反弹

    状态判定：
    - 牵牛：白线 > 黄线 且 白线在上升（white[-1] > white[-3]）
    - 牛绳断：白线 < 黄线
    - 金叉：白线从下方刚上穿黄线（今日白>黄，昨日白<=黄）
    - 死叉：白线从上方刚下穿黄线（今日白<黄，昨日白>=黄）

    Args:
        klines: K线数据（至少120根）

    Returns:
        {
            'status': '牵牛' | '牛绳断' | '金叉' | '死叉',
            'white': 当前白线值,
            'yellow': 当前黄线值,
            'gap_pct': 白黄差距百分比（正=多头缺口）,
            'white_trend': '上升' | '下降' | '横盘',
            'is_bullish': bool,
            'is_bearish': bool,
        }
    """
    result: dict[str, Any] = {
        "status": "牛绳断",
        "white": 0.0,
        "yellow": 0.0,
        "gap_pct": 0.0,
        "white_trend": "横盘",
        "is_bullish": False,
        "is_bearish": True,
    }

    if len(klines) < 120:
        return result

    # 计算最近几天的白线和黄线历史值（需要至少3天来判断交叉和趋势）
    white_values: list[float] = []
    yellow_values: list[float] = []

    for i in range(114, len(klines) + 1):
        sub = klines[:i]
        w = calculate_zg_white(sub)
        y = calculate_dg_yellow(sub)
        if w > 0 and y > 0:
            white_values.append(w)
            yellow_values.append(y)

    if len(white_values) < 3:
        return result

    w_now = white_values[-1]
    w_prev = white_values[-2]
    w_prev2 = white_values[-3]
    y_now = yellow_values[-1]
    y_prev = yellow_values[-2]

    result["white"] = round(w_now, 2)
    result["yellow"] = round(y_now, 2)

    # 白黄差距百分比
    if y_now > 0:
        result["gap_pct"] = round((w_now - y_now) / y_now * 100, 2)

    # 状态判定（优先级：金叉/死叉 > 牵牛/牛绳断）
    is_golden_cross = w_now > y_now and w_prev <= y_prev
    is_death_cross = w_now < y_now and w_prev >= y_prev

    if is_golden_cross:
        result["status"] = "金叉"
    elif is_death_cross:
        result["status"] = "死叉"
    elif w_now > y_now:
        # 白线在黄线上，进一步判断是否上升
        if w_now > w_prev2:
            result["status"] = "牵牛"
        else:
            # 白线在黄线上但走弱，仍算牵牛（牛绳未断）
            result["status"] = "牵牛"
    else:
        result["status"] = "牛绳断"

    # 白线趋势：用最近5天的斜率
    if len(white_values) >= 5:
        slope = calculate_slope(white_values, 5)
        if slope > 0.01:
            result["white_trend"] = "上升"
        elif slope < -0.01:
            result["white_trend"] = "下降"
        else:
            result["white_trend"] = "横盘"
    elif w_now > w_prev2:
        result["white_trend"] = "上升"
    elif w_now < w_prev2:
        result["white_trend"] = "下降"

    # 多空判断
    result["is_bullish"] = result["status"] in ("牵牛", "金叉")
    result["is_bearish"] = result["status"] in ("牛绳断", "死叉")

    return result

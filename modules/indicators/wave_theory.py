"""
三波理论识别模块

来源：knowledge/indicators.md
核心：建仓波 → 拉升波 → 冲刺波
"""

from .core import DailyData


def _find_recent_low(klines: list[DailyData], window: int = 5) -> tuple[int, float]:
    """
    找近期低点：在 klines 中找局部最小值（连续 window 日最低点）

    返回：(低点索引, 低点价格)
    """
    if len(klines) < window * 2 + 1:
        # 数据不足，返回全局最低
        lows = [(i, k.low) for i, k in enumerate(klines)]
        min_idx = min(lows, key=lambda x: x[1])[0]
        return min_idx, klines[min_idx].low

    # 从后往前找局部最小值
    for i in range(len(klines) - window - 1, window - 1, -1):
        current_low = klines[i].low
        is_local_min = True
        for j in range(i - window, i + window + 1):
            if j == i:
                continue
            if klines[j].low < current_low:
                is_local_min = False
                break
        if is_local_min:
            return i, current_low

    # 没找到局部最小值，返回全局最低
    lows = [(i, k.low) for i, k in enumerate(klines)]
    min_idx = min(lows, key=lambda x: x[1])[0]
    return min_idx, klines[min_idx].low


def _count_limit_up(klines: list[DailyData], start_idx: int) -> int:
    """统计从 start_idx 到今日的涨停次数（pct_chg >= 9.9%）"""
    count = 0
    for k in klines[start_idx:]:
        if k.pct_chg >= 9.9:
            count += 1
    return count


def _calculate_red_ratio(klines: list[DailyData], start_idx: int) -> float:
    """计算从 start_idx 到今日的阳线占比"""
    segment = klines[start_idx:]
    if not segment:
        return 0.0
    red_count = sum(1 for k in segment if k.close > k.open)
    return red_count / len(segment)


def _calculate_avg_daily_gain(klines: list[DailyData], start_idx: int) -> float:
    """计算从 start_idx 到今日的日均涨幅（%）"""
    segment = klines[start_idx:]
    if len(segment) < 2:
        return 0.0
    total_gain = (segment[-1].close / segment[0].close - 1) * 100
    return total_gain / len(segment)


def _calculate_20day_gain(klines: list[DailyData]) -> float:
    """计算最近 20 日涨幅"""
    if len(klines) < 20:
        return 0.0
    return (klines[-1].close / klines[-20].close - 1) * 100


def detect_three_waves(klines: list[DailyData]) -> dict:
    """
    识别当前处于三波理论的哪个阶段

    建仓波：底部起涨 25%-50%，无涨停或 ≤1 次，阳线占比 > 60%，日均涨幅温和
    拉升波：涨幅 > 50% 或 20 日涨幅 > 30%，涨停 ≥2 次，快速脱离
    冲刺波：涨幅 > 100%，频繁涨停，高位加速

    返回：
    {
        'wave': '建仓波' | '拉升波' | '冲刺波' | '未知',
        'confidence': float,  # 0-1
        'stats': {
            'low_price': float,
            'high_price': float,
            'gain_pct': float,
            'limit_up_count': int,
            'red_ratio': float,
            'avg_daily_gain': float,
            'gain_20day': float,
            'days_from_low': int,
        },
        'b1_suggestion': '可干' | '等回调' | '不看' | '观望',
    }
    """
    result = {
        "wave": "未知",
        "confidence": 0.0,
        "stats": {},
        "b1_suggestion": "观望",
    }

    if len(klines) < 30:
        return result

    # 找近期低点
    low_idx, low_price = _find_recent_low(klines, window=5)
    if low_idx >= len(klines) - 1:
        # 低点就在今天或昨天，无法判断
        return result

    today = klines[-1]
    segment = klines[low_idx:]
    days_from_low = len(segment) - 1

    # 统计数据
    high_price = max(k.high for k in segment)
    gain_pct = (today.close / low_price - 1) * 100
    limit_up_count = _count_limit_up(klines, low_idx)
    red_ratio = _calculate_red_ratio(klines, low_idx)
    avg_daily_gain = _calculate_avg_daily_gain(klines, low_idx)
    gain_20day = _calculate_20day_gain(klines)

    stats = {
        "low_price": round(low_price, 2),
        "high_price": round(high_price, 2),
        "gain_pct": round(gain_pct, 2),
        "limit_up_count": limit_up_count,
        "red_ratio": round(red_ratio, 2),
        "avg_daily_gain": round(avg_daily_gain, 2),
        "gain_20day": round(gain_20day, 2),
        "days_from_low": days_from_low,
    }
    result["stats"] = stats

    # ========== 冲刺波判断 ==========
    # 涨幅 > 100% 且频繁涨停（≥3次）
    sprint_score = 0
    if gain_pct > 100:
        sprint_score += 40
    if limit_up_count >= 3:
        sprint_score += 30
    if gain_20day > 30:
        sprint_score += 20
    if red_ratio > 0.7:
        sprint_score += 10

    if sprint_score >= 60:
        result["wave"] = "冲刺波"
        result["confidence"] = round(min(sprint_score / 100, 1.0), 2)
        result["b1_suggestion"] = "不看"
        return result

    # ========== 拉升波判断 ==========
    # 涨幅 > 50% 或 20 日涨幅 > 30%，涨停 ≥2 次
    pull_score = 0
    if gain_pct > 50:
        pull_score += 35
    elif gain_pct > 40:
        pull_score += 20
    if gain_20day > 30:
        pull_score += 25
    elif gain_20day > 20:
        pull_score += 15
    if limit_up_count >= 2:
        pull_score += 25
    elif limit_up_count >= 1:
        pull_score += 10
    if avg_daily_gain > 1.5:
        pull_score += 15

    if pull_score >= 50:
        result["wave"] = "拉升波"
        result["confidence"] = round(min(pull_score / 100, 1.0), 2)
        result["b1_suggestion"] = "等回调"
        return result

    # ========== 建仓波判断 ==========
    # 25% ≤ 涨幅 ≤ 50%，涨停 ≤1 次，阳线占比 > 60%，日均涨幅温和
    build_score = 0
    if 25 <= gain_pct <= 50:
        build_score += 35
    elif 15 <= gain_pct < 25:
        build_score += 20
    elif 50 < gain_pct <= 60:
        build_score += 15
    if limit_up_count <= 1:
        build_score += 25
    if red_ratio > 0.6:
        build_score += 20
    elif red_ratio > 0.5:
        build_score += 10
    if 0.3 <= avg_daily_gain <= 2.0:
        build_score += 20

    if build_score >= 50:
        result["wave"] = "建仓波"
        result["confidence"] = round(min(build_score / 100, 1.0), 2)
        result["b1_suggestion"] = "可干"
        return result

    # 无法明确判断
    result["confidence"] = round(max(sprint_score, pull_score, build_score) / 100, 2)
    return result


def classify_wave_for_b1(klines: list[DailyData]) -> str:
    """
    简化接口：直接返回 B1 操作建议

    建仓波 → 可干
    拉升波 → 等回调
    冲刺波 → 不看
    未知 → 观望
    """
    result = detect_three_waves(klines)
    return result["b1_suggestion"]


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    # 简单测试
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from modules.indicators import DailyData

    # 建仓波场景：底部起涨 35%，无涨停，连续阳线
    klines = []
    price = 100.0
    for i in range(60):
        # 温和上涨，日均约 0.5%
        price *= 1.005
        k = DailyData(
            ts_code="000001.SZ",
            trade_date=f"202601{i + 1:02d}",
            open=price * 0.998,
            high=price * 1.01,
            low=price * 0.995,
            close=price,
            vol=10000,
            amount=price * 10000,
            pct_chg=0.5,
            prev_close=price / 1.005,
        )
        klines.append(k)

    result = detect_three_waves(klines)
    print("建仓波测试:", result)

    # 拉升波场景：快速上涨 60%，有涨停
    klines2 = []
    price = 100.0
    for i in range(40):
        if i < 20:
            price *= 1.008
            pct = 0.8
        else:
            price *= 1.03
            pct = 3.0
        k = DailyData(
            ts_code="000001.SZ",
            trade_date=f"202601{i + 1:02d}",
            open=price * 0.99,
            high=price * 1.05,
            low=price * 0.98,
            close=price,
            vol=20000,
            amount=price * 20000,
            pct_chg=pct,
            prev_close=price / (1 + pct / 100),
        )
        klines2.append(k)

    result2 = detect_three_waves(klines2)
    print("拉升波测试:", result2)

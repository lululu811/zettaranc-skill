from typing import Any
from ..core import DailyData, calculate_ma, calculate_slope


def calculate_sandglass_score(klines: list[DailyData]) -> dict:
    """
    沙漏评分 V9 —— 基于图形审美的选股评分系统

    五因子模型（各 0-20 分，总分 0-100）：
    1. 缩量/收敛 (Volume Contraction)：近期量能收缩、量幅收窄
    2. 枢轴邻近 (Pivot Proximity)：当前价格接近近期支撑位
    3. 量能斜率 (Volume Slope)：成交量趋势温和下降（可控抛压）
    4. 均线结构 (MA Structure)：MA5 > MA10 > MA20 多头排列 + 均线收敛
    5. 事件风险 (Event Risk)：从 20 分起扣，检查跳空/连跌/异常放量/近高点
    """
    result: dict[str, Any] = {
        "score": 0,
        "rating": "极差",
        "factors": {},
        "is_perfect": False,
    }

    if len(klines) < 20:
        return result

    n = len(klines)
    closes = [k.close for k in klines]
    volumes = [k.vol for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]

    # ========== 因子 1：缩量/收敛 (0-20) ==========
    vol_ma10 = sum(volumes[-10:]) / 10
    vol_ma20 = sum(volumes[-20:]) / 20

    # 子因子 A：10 日均量 vs 20 日均量（收缩程度）
    if vol_ma20 > 0:
        vol_ratio = vol_ma10 / vol_ma20
    else:
        vol_ratio = 1.0

    if vol_ratio < 0.6:
        score_contraction_a = 12
    elif vol_ratio < 0.8:
        score_contraction_a = 8
    elif vol_ratio < 1.0:
        score_contraction_a = 4
    else:
        score_contraction_a = 0

    # 子因子 B：量幅收窄（近 5 天量幅 vs 前 5 天量幅）
    recent_5_vol = volumes[-5:]
    prev_5_vol = volumes[-10:-5]
    vol_range_recent = max(recent_5_vol) - min(recent_5_vol)
    vol_range_prev = max(prev_5_vol) - min(prev_5_vol) if prev_5_vol else vol_range_recent

    if vol_range_prev > 0:
        vol_range_ratio = vol_range_recent / vol_range_prev
    else:
        vol_range_ratio = 1.0

    if vol_range_ratio < 0.5:
        score_contraction_b = 8
    elif vol_range_ratio < 0.8:
        score_contraction_b = 5
    elif vol_range_ratio < 1.0:
        score_contraction_b = 3
    else:
        score_contraction_b = 0

    score_contraction = min(20, score_contraction_a + score_contraction_b)

    # ========== 因子 2：枢轴邻近 (0-20) ==========
    # 近 20 天最低价作为支撑位
    support = min(lows[-20:])
    current_price = closes[-1]

    if support > 0:
        distance_pct = (current_price - support) / support
    else:
        distance_pct = 1.0

    if distance_pct <= 0.03:
        score_pivot = 20
    elif distance_pct <= 0.05:
        score_pivot = 16
    elif distance_pct <= 0.08:
        score_pivot = 12
    elif distance_pct <= 0.10:
        score_pivot = 8
    elif distance_pct <= 0.15:
        score_pivot = 4
    else:
        score_pivot = 0

    # ========== 因子 3：量能斜率 (0-20) ==========
    # 计算最近 10 天成交量的线性回归斜率
    vol_slope = calculate_slope(volumes[-10:], 10) if len(volumes) >= 10 else 0

    # 归一化：斜率相对均值的比值
    if vol_ma10 > 0:
        slope_normalized = vol_slope / vol_ma10
    else:
        slope_normalized = 0

    # 理想：温和下降（-0.05 ~ -0.01）
    if -0.05 <= slope_normalized <= -0.01:
        score_vol_slope = 20
    elif -0.10 <= slope_normalized < -0.05:
        score_vol_slope = 15
    elif -0.01 < slope_normalized <= 0.02:
        score_vol_slope = 12
    elif -0.15 <= slope_normalized < -0.10:
        score_vol_slope = 8
    elif slope_normalized > 0.05:
        # 急剧放量 = 分发风险
        score_vol_slope = 2
    else:
        score_vol_slope = 5

    # ========== 因子 4：均线结构 (0-20) ==========
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)

    score_ma = 0

    # 子因子 A：多头排列 MA5 > MA10 > MA20
    if ma5 > ma10 > ma20:
        score_ma += 10
    elif ma5 > ma10 or ma10 > ma20:
        score_ma += 5

    # 子因子 B：价格在 MA20 上方
    if ma20 > 0 and current_price > ma20:
        score_ma += 4

    # 子因子 C：均线收敛（MA5 与 MA20 差距缩小 = 潜在突破）
    if ma20 > 0:
        ma_gap = abs(ma5 - ma20) / ma20
        if ma_gap < 0.02:
            score_ma += 6  # 极度收敛
        elif ma_gap < 0.05:
            score_ma += 4
        elif ma_gap < 0.08:
            score_ma += 2

    score_ma = min(20, score_ma)

    # ========== 因子 5：事件风险 (0-20，从 20 分起扣) ==========
    score_risk = 20

    # 检查 1：近 5 天大幅跳空下跌
    for i in range(max(0, n - 5), n):
        if i > 0:
            gap_down = (klines[i].open - klines[i - 1].close) / klines[i - 1].close
            if gap_down < -0.03:
                score_risk -= 10
                break

    # 检查 2：连续 3 天以上下跌
    down_count = 0
    for i in range(max(0, n - 5), n):
        if klines[i].pct_chg < 0:
            down_count += 1
        else:
            down_count = 0
    if down_count >= 3:
        score_risk -= 5

    # 检查 3：放量不涨（量增价滞）
    if n >= 5:
        recent_vol_spike = volumes[-1] > vol_ma10 * 1.8
        price_no_rise = closes[-1] <= closes[-2] if n >= 2 else False
        if recent_vol_spike and price_no_rise:
            score_risk -= 5

    # 检查 4：近 52 周高点（距 240 天最高价 < 5%）
    lookback_52w = min(240, n)
    high_52w = max(highs[-lookback_52w:])
    if high_52w > 0 and (high_52w - current_price) / high_52w < 0.05:
        score_risk -= 5

    score_risk = max(0, score_risk)

    # ========== 汇总 ==========
    total_score = score_contraction + score_pivot + score_vol_slope + score_ma + score_risk
    total_score = max(0, min(100, total_score))

    # 评级
    if total_score >= 80:
        rating = "极佳"
    elif total_score >= 65:
        rating = "良好"
    elif total_score >= 45:
        rating = "一般"
    elif total_score >= 25:
        rating = "较差"
    else:
        rating = "极差"

    result["score"] = total_score
    result["rating"] = rating
    result["factors"] = {
        "缩量收敛": score_contraction,
        "枢轴邻近": score_pivot,
        "量能斜率": score_vol_slope,
        "均线结构": score_ma,
        "事件风险": score_risk,
    }
    result["is_perfect"] = total_score >= 80

    return result

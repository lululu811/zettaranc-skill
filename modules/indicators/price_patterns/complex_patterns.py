from typing import Any
from ..core import DailyData, calculate_ma, calculate_kdj, calculate_slope
from .base import calculate_zg_white, calculate_dg_yellow


def detect_divergence(klines: list[DailyData], dif_list: list[float]) -> dict:
    """
    顶底背离系统化检测（基于语料标准）

    顶背离：价格创新高但DIF不创新高 → 趋势衰竭，见顶减仓
    底背离：价格创新低但DIF不创新低 → 反转在即，底部建仓

    要求：
    - 对比窗口：最近60个交易日的极值区间
    - 价格容忍度：接近极值1%-2%即视为"同一水平"
    - DIF衰减：DIF未突破前值的90%(顶)或未跌破前值的110%(底)
    """
    result = {
        "is_top_divergence": False,
        "is_bottom_divergence": False,
    }

    if len(klines) < 60 or len(dif_list) < 30:
        return result

    closes = [k.close for k in klines]
    today_close = closes[-1]

    # ====== 顶背离检测 ======
    # 找最近60天内的最高收盘价窗口（排除最后5天，避免与当前比较）
    window_start = max(0, len(closes) - 60)
    window_end = max(0, len(closes) - 10)
    if window_end <= window_start:
        window_end = len(closes) - 5

    if window_end > window_start:
        max_close = max(closes[window_start:window_end])

        # 对应窗口的DIF最大值
        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            max_dif = max(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最高，但DIF明显低于前高
            price_near_high = today_close >= max_close * 0.98
            dif_weaker = dif_list[-1] < max_dif * 0.9

            if price_near_high and dif_weaker and max_dif > 0:
                result["is_top_divergence"] = True

    # ====== 底背离检测 ======
    if window_end > window_start:
        min_close = min(closes[window_start:window_end])

        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            min_dif = min(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最低，但DIF明显高于前低
            price_near_low = today_close <= min_close * 1.02
            dif_stronger = dif_list[-1] > min_dif * 1.1

            if price_near_low and dif_stronger and min_dif < 0:
                result["is_bottom_divergence"] = True

    return result


def detect_macd_signals(
    klines: list[DailyData], dif_list: list[float], dea_list: list[float], macd_list: list[float]
) -> dict[str, Any]:
    """
    根据 Z哥 语料检测 MACD 信号

    三大用法:
    1. DIF 上下穿 0 轴 — 判多空区间
    2. 顶/底背离 — 判趋势终结
    3. 金叉空 + 死叉多 — 判陷阱
    """
    signals = {
        "is_dif_positive": False,
        "is_dif_cross_zero": False,
        "is_dif_cross_zero_down": False,
        "is_gold_cross": False,
        "is_dead_cross": False,
        "is_gold_fake": False,
        "is_dead_fake": False,
        "is_top_divergence": False,
        "is_bottom_divergence": False,
        "macd_veto": False,
    }

    if len(dif_list) < 2 or len(dea_list) < 1:
        return signals

    dif_today = dif_list[-1]
    dif_yesterday = dif_list[-2] if len(dif_list) >= 2 else 0
    dea_today = dea_list[-1]
    dea_yesterday = dea_list[-2] if len(dea_list) >= 2 else 0

    # === 用法 1: DIF 0 轴判多空 ===
    signals["is_dif_positive"] = dif_today > 0

    # DIF 上穿 0 轴
    signals["is_dif_cross_zero"] = dif_yesterday <= 0 and dif_today > 0
    # DIF 下穿 0 轴
    signals["is_dif_cross_zero_down"] = dif_yesterday >= 0 and dif_today < 0

    # === 金叉/死叉 ===
    if len(dif_list) >= 3 and len(dea_list) >= 2:
        signals["is_gold_cross"] = dif_yesterday <= dea_yesterday and dif_today > dea_today
        signals["is_dead_cross"] = dif_yesterday >= dea_yesterday and dif_today < dea_today

    # === 用法 3: 金叉空 + 死叉多（多等一天）===
    if len(dif_list) >= 5 and len(dea_list) >= 3:
        # 检查最近 3 天的金叉/死叉变化
        recent_gold = 0
        recent_dead = 0
        for i in range(max(0, len(dif_list) - 4), len(dif_list) - 1):
            di = i
            dei = i - (len(dif_list) - len(dea_list))
            if dei >= 0 and dei < len(dea_list) and dei + 1 < len(dea_list):
                if dif_list[di] > dea_list[dei] and dif_list[di - 1] <= dea_list[dei - 1 if dei > 0 else 0]:
                    recent_gold += 1
                if dif_list[di] < dea_list[dei] and dif_list[di - 1] >= dea_list[dei - 1 if dei > 0 else 0]:
                    recent_dead += 1

        # 金叉空：刚金叉又马上死叉
        if signals["is_dead_cross"] and recent_gold >= 1:
            signals["is_gold_fake"] = True

        # 死叉多：刚死叉又马上金叉
        if signals["is_gold_cross"] and recent_dead >= 1:
            signals["is_dead_fake"] = True

    # === 用法 2: 顶底背离（系统化检测）===
    div = detect_divergence(klines, dif_list)
    signals["is_top_divergence"] = div["is_top_divergence"]
    signals["is_bottom_divergence"] = div["is_bottom_divergence"]

    # === 一票否决权 ===
    # DIF < 0 + 没有底背离 → 一票否决
    if dif_today < 0 and not signals["is_bottom_divergence"]:
        signals["macd_veto"] = True

    return signals


def detect_double_gun(klines: list[DailyData]) -> dict:
    """
    双枪战法检测

    图形特征：两根放量阳柱中间夹一堆缩量阴线
    本质：主力建仓确认 — 第一根试盘，中间洗盘，第二根确认

    规则：
    - 往前找最近一根放量阳线（第二枪），排除今天
    - 再往前找另一根放量阳线（第一枪）
    - 中间夹缩量小阴小阳（3-10天）
    - 第二枪前一日应有B1痕迹（J<13）
    """
    result: dict[str, Any] = {
        "is_double_gun": False,
        "double_gun_vol1": 0.0,
        "double_gun_vol2": 0.0,
        "double_gun_gap_days": 0,
    }
    if len(klines) < 15:
        return result

    n = len(klines)

    # 往前找最近一根放量阳线（第二枪），排除今天
    gun2_idx = None
    for i in range(n - 2, max(0, n - 15), -1):
        if i > 0:
            prev_i = klines[i - 1]
            vol_ratio = klines[i].vol / prev_i.vol if prev_i.vol > 0 else 0
            if klines[i].pct_chg >= 3 and klines[i].close > klines[i].open and vol_ratio >= 1.8:
                gun2_idx = i
                break

    if gun2_idx is None or gun2_idx < 5:
        return result

    # 检查第二枪前一日是否有B1痕迹
    _, _, j_before_gun2 = calculate_kdj(klines[:gun2_idx])
    has_b1_before = j_before_gun2 < 20

    # 从第二枪往前找第一枪
    gun1_idx = None
    for i in range(gun2_idx - 3, max(0, gun2_idx - 12), -1):
        if i > 0:
            prev_i = klines[i - 1]
            vol_ratio = klines[i].vol / prev_i.vol if prev_i.vol > 0 else 0
            if klines[i].pct_chg >= 3 and klines[i].close > klines[i].open and vol_ratio >= 1.8:
                gun1_idx = i
                break

    if gun1_idx is None:
        return result

    gap_days = gun2_idx - gun1_idx

    # 检查中间是否缩量
    mid_vols = []
    for i in range(gun1_idx + 1, gun2_idx):
        if i > 0:
            prev_i = klines[i - 1]
            if prev_i.vol > 0:
                mid_vols.append(klines[i].vol / prev_i.vol)

    if not mid_vols:
        return result

    avg_mid_vol = sum(mid_vols) / len(mid_vols)
    is_shrink_mid = avg_mid_vol < 1.2  # 中间平均量比 < 1.2

    # 计算两枪的量比
    g1_prev = klines[gun1_idx - 1] if gun1_idx > 0 else None
    g2_prev = klines[gun2_idx - 1] if gun2_idx > 0 else None
    vol1: float = klines[gun1_idx].vol / g1_prev.vol if g1_prev and g1_prev.vol > 0 else 0.0
    vol2: float = klines[gun2_idx].vol / g2_prev.vol if g2_prev and g2_prev.vol > 0 else 0.0

    if is_shrink_mid and has_b1_before and 3 <= gap_days <= 10:
        result["is_double_gun"] = True
        result["double_gun_vol1"] = round(vol1, 1)
        result["double_gun_vol2"] = round(vol2, 1)
        result["double_gun_gap_days"] = gap_days

    return result


def detect_sb1_detailed(klines: list[DailyData]) -> dict:
    """
    超级B1独立检测

    形态流程：
    N型上涨 → 缩量回调 → 标准B1触发 → 突然放量大阴线击穿止损位 →
    缩量企稳 + J值大负值 → 反转K线确认 → 入场

    只赌一次，不可重复博弈
    """
    result = {
        "is_sb1_detailed": False,
    }
    if len(klines) < 15:
        return result

    n = len(klines)
    today = klines[-1]
    _, _, j_today = calculate_kdj(klines)

    # 往前找放量大阴线（击穿止损位）
    big_drop_idx = None
    for i in range(n - 2, max(0, n - 10), -1):
        if i > 0:
            prev_i = klines[i - 1]
            vol_ratio = klines[i].vol / prev_i.vol if prev_i.vol > 0 else 0
            # 放量大阴线：跌幅>3%, 量比>1.5, 收阴
            if klines[i].pct_chg <= -3 and vol_ratio >= 1.5 and klines[i].close < klines[i].open:
                big_drop_idx = i
                break

    if big_drop_idx is None:
        return result

    # 大阴线后缩量企稳（1-3天）
    days_after_drop = n - 1 - big_drop_idx
    if days_after_drop < 1 or days_after_drop > 3:
        return result

    # 检查大阴线后是否缩量
    drop_vol = klines[big_drop_idx].vol
    for i in range(big_drop_idx + 1, n):
        if klines[i].vol > drop_vol * 0.7:
            return result  # 没有缩量

    # J值大负值
    if j_today > -5:
        return result

    # 反转K线确认（十字星或小阳）
    body = abs(today.close - today.open)
    prev_close = klines[-2].close if len(klines) > 1 else today.close
    body_pct = body / prev_close * 100 if prev_close > 0 else 0
    is_reversal = body_pct <= 2 or (today.pct_chg > 0 and today.close > today.open)

    if not is_reversal:
        return result

    # 检查大阴线前是否有N型上涨结构
    if big_drop_idx >= 5:
        pre_lows = [klines[i].low for i in range(max(0, big_drop_idx - 10), big_drop_idx)]
        if len(pre_lows) >= 3:
            # 简单判断：大阴线前的低点在抬高
            first_half = pre_lows[: len(pre_lows) // 2]
            second_half = pre_lows[len(pre_lows) // 2 :]
            if min(second_half) < min(first_half):
                result["is_sb1_detailed"] = True

    return result


def detect_nana_chart(klines: list[DailyData]) -> dict:
    """
    娜娜图检测：完美建仓形态
    条件：股价新高但阳线缩量，次高点阴线也缩量
    """
    result = {"is_nana": False}
    if len(klines) < 20:
        return result
    n = len(klines)
    # 找最近高点区域
    highs = [k.high for k in klines]
    peak_idx = n - 1
    for i in range(n - 2, max(0, n - 30), -1):
        if highs[i] >= highs[peak_idx]:
            peak_idx = i
    # 从峰值往前找第二高
    second_peak = None
    for i in range(peak_idx - 2, max(0, peak_idx - 25), -1):
        if klines[i].high < klines[peak_idx].high * 0.98:
            second_peak = i
            break
    if second_peak is None or peak_idx < 5:
        return result
    # 检查峰值区域是否缩量
    peak_vol = klines[peak_idx].vol
    prev5_avg = sum(k.vol for k in klines[max(0, peak_idx - 5) : peak_idx]) / min(5, peak_idx)
    vol_shrink_at_peak = peak_vol < prev5_avg * 0.8 if prev5_avg > 0 else False
    # 次高点缩量
    second_vol = klines[second_peak].vol
    sec_prev5 = sum(k.vol for k in klines[max(0, second_peak - 5) : second_peak]) / min(5, second_peak)
    vol_shrink_second = second_vol < sec_prev5 * 0.8 if sec_prev5 > 0 else False
    # 底部堆量：找低点区域量是否明显大于峰值区域
    low_idx = min(range(max(0, second_peak - 10), second_peak), key=lambda i: klines[i].low)
    bottom_vol = klines[low_idx].vol
    if vol_shrink_at_peak and vol_shrink_second and bottom_vol > peak_vol * 0.5:
        result["is_nana"] = True
    return result


def detect_golden_bowl(klines: list[DailyData]) -> dict:
    """
    黄金碗检测：价格在白线( zg_white )和黄线( dg_yellow )之间
    条件：白线>黄线(多头排列) + 价格落入碗内
    """
    result: dict[str, Any] = {"is_in_bowl": False, "bowl_upper": 0.0, "bowl_lower": 0.0}
    if len(klines) < 120:
        return result
    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    if white <= 0 or yellow <= 0:
        return result
    result["bowl_upper"] = round(white, 2)
    result["bowl_lower"] = round(yellow, 2)
    today_close = klines[-1].close
    # 白线>黄线且价格在碗内
    if white > yellow and yellow <= today_close <= white:
        result["is_in_bowl"] = True
    return result


def detect_breathing_structure(klines: list[DailyData]) -> dict:
    """
    呼吸结构检测：放量涨->缩量跌->放量涨 的N型节奏
    """
    result = {"breath_phase": "", "breath_n_type": False}
    if len(klines) < 10:
        return result
    n = len(klines)
    # 分析最近5-7天的量价节奏
    phases = []
    for i in range(max(0, n - 7), n):
        day = klines[i]
        prev = klines[i - 1] if i > 0 else None
        if not prev or prev.vol <= 0:
            continue
        vol_ratio = day.vol / prev.vol
        if day.pct_chg > 0 and vol_ratio > 1:
            phases.append("exhale")  # 放量涨=呼气
        elif day.pct_chg < 0 and vol_ratio < 1:
            phases.append("inhale")  # 缩量跌=吸气
        else:
            phases.append("other")
    # 判断当前阶段
    if len(phases) >= 2:
        if phases[-1] == "exhale":
            result["breath_phase"] = "exhale"
        elif phases[-1] == "inhale":
            result["breath_phase"] = "inhale"
        else:
            result["breath_phase"] = "none"
    # N型结构：最近3个低点依次抬高
    if n >= 10:
        lows = [klines[i].low for i in range(n - 10, n, 3)]
        if len(lows) >= 3 and lows[-1] > lows[-2] > lows[-3]:
            result["breath_n_type"] = True
    return result


def detect_sb1(klines: list[DailyData]) -> dict:
    """
    SB1假摔检测：B1后跌破前低再迅速收回
    条件：1)跌破前低 2)次日反包收回 3)收回放量
    """
    result = {"is_sb1": False}
    if len(klines) < 6:
        return result
    n = len(klines)
    yesterday = klines[-2]
    # 前天是假摔日
    if len(klines) >= 3:
        fake_drop = klines[-3]
        prev_low = min(k.low for k in klines[-8:-3]) if n >= 8 else klines[-4].low
        # 1) 跌破前低
        broken_low = fake_drop.low < prev_low
        # 2) 次日反包收回
        recovered = yesterday.close > prev_low and yesterday.pct_chg > 2
        # 3) 反包放量
        vol_up = yesterday.vol > fake_drop.vol * 1.2
        if broken_low and recovered and vol_up:
            result["is_sb1"] = True
    return result


def detect_b3(klines: list[DailyData]) -> dict:
    """
    B3买点检测：B2后缩量回踩不破B2低点
    条件：1) 前面有B2(大涨>=4%) 2) 缩量小阳/十字星 3) 不破B2低点
    """
    result = {"is_b3": False}
    if len(klines) < 15:
        return result
    n = len(klines)
    today = klines[-1]
    # 往前找B2(大涨>=4%的阳线)
    b2_idx = None
    for i in range(n - 2, max(0, n - 15), -1):
        if klines[i].pct_chg >= 4 and klines[i].close > klines[i].open:
            b2_idx = i
            break
    if b2_idx is None:
        return result
    b2_low = klines[b2_idx].low
    # B2后缩量小阳线
    days_after = n - 1 - b2_idx
    if 2 <= days_after <= 5:
        today_vol_ratio = today.vol / klines[b2_idx].vol if klines[b2_idx].vol > 0 else 0
        not_break_low = today.low >= b2_low * 0.98
        small_candle = abs(today.pct_chg) < 3
        if today_vol_ratio < 0.8 and not_break_low and small_candle:
            result["is_b3"] = True
    return result


def detect_zaihou_chongjian(klines: list[DailyData]) -> dict:
    """
    灾后重建检测 —— 放量金叉后缩量回踩黄线

    来源：advanced-patterns.md
    定义：放量金叉后缩量回踩黄线，交易价值最大，是最后拉升前的震仓动作。

    条件：
    1. 前期有放量上涨（涨幅 > 5%，量 > 前5日均量 × 1.5）
    2. 近期缩量回调（量 < 放量日量的 60%）
    3. 价格回踩黄线（大哥线 / 4参数BBI变体）附近（±2%）
    4. 黄线趋势向上

    Args:
        klines: K线数据（至少60根）

    Returns:
        {'is_rebuild': bool, 'confidence': float, 'desc': str}
    """
    if len(klines) < 60:
        return {"is_rebuild": False}

    today = klines[-1]

    # 计算黄线（4参数BBI变体）
    closes = [k.close for k in klines]
    ma3 = calculate_ma(closes, 3)
    ma6 = calculate_ma(closes, 6)
    ma12 = calculate_ma(closes, 12)
    ma24 = calculate_ma(closes, 24)
    yellow_line = (ma3 + ma6 + ma12 + ma24) / 4

    # 黄线趋势：近5天黄线 vs 近10天黄线
    yellow_5 = (
        calculate_ma(closes[-5:], 3)
        + calculate_ma(closes[-5:], 6)
        + calculate_ma(closes[-5:], 12)
        + calculate_ma(closes[-5:], 24)
    ) / 4
    yellow_10 = (
        calculate_ma(closes[-10:], 3)
        + calculate_ma(closes[-10:], 6)
        + calculate_ma(closes[-10:], 12)
        + calculate_ma(closes[-10:], 24)
    ) / 4
    yellow_up = yellow_5 > yellow_10

    # 查找近期放量上涨日（近15天内）
    recent_15 = klines[-15:]
    fangliang_day = None
    for i, k in enumerate(recent_15):
        if i == 0:
            continue
        prev_5_avg = sum(kl.vol for kl in recent_15[max(0, i - 5) : i]) / 5
        if k.pct_chg > 5 and k.vol > prev_5_avg * 1.5:
            fangliang_day = k
            break

    if fangliang_day is None:
        return {"is_rebuild": False}

    # 缩量条件：今天量 < 放量日量的 60%
    is_suoliang = today.vol < fangliang_day.vol * 0.6

    # 回踩黄线：收盘价在黄线 ±2% 范围内
    near_yellow = abs(today.close - yellow_line) / yellow_line < 0.02 if yellow_line > 0 else False

    if is_suoliang and near_yellow and yellow_up:
        return {
            "is_rebuild": True,
            "confidence": 0.85,
            "yellow_line": round(yellow_line, 2),
            "fangliang_price": round(fangliang_day.close, 2),
            "desc": f"灾后重建：放量({fangliang_day.close:.2f})后缩量回踩黄线({yellow_line:.2f})",
        }

    return {"is_rebuild": False}


def detect_yueyueyushi(klines: list[DailyData]) -> dict:
    """
    跃跃欲试检测 —— 横盘期间放巨大量三次

    来源：advanced-patterns.md
    定义：横盘期间放巨大量，红长绿短、红肥绿瘦，出现至少三次后越往后突破概率越大。
    前提：仅限牛市、未出货的赛赛图。"横有多长竖有多高"。

    条件：
    1. 近20天振幅 < 15%（横盘）
    2. 近20天出现至少3次巨量（量 > 前10日均量 × 2）
    3. 巨量日多为阳线（红肥绿瘦）
    4. 当前未处于明显高位（距20日高点 < 10% 可接受）

    Args:
        klines: K线数据（至少30根）

    Returns:
        {'is_ready': bool, 'count': int, 'confidence': float, 'desc': str}
    """
    if len(klines) < 30:
        return {"is_ready": False}

    recent_20 = klines[-20:]
    high_20 = max(k.high for k in recent_20)
    low_20 = min(k.low for k in recent_20)
    amplitude = (high_20 - low_20) / low_20 if low_20 > 0 else 0

    # 横盘条件
    if amplitude > 0.15:
        return {"is_ready": False}

    # 计算近10日均量
    vols_10 = [k.vol for k in klines[-10:]]
    avg_vol_10 = sum(vols_10) / len(vols_10)

    # 统计巨量次数（量 > 前10日均量 × 2）
    juliang_count = 0
    yang_count = 0
    for k in recent_20:
        if k.vol > avg_vol_10 * 2:
            juliang_count += 1
            if k.close > k.open:
                yang_count += 1

    # 至少3次巨量，且阳线占比 > 50%
    if juliang_count >= 3 and yang_count / juliang_count > 0.5:
        confidence = 0.70 + 0.05 * min(juliang_count - 3, 3)  # 每多一次+5%，上限85%
        return {
            "is_ready": True,
            "count": juliang_count,
            "yang_ratio": round(yang_count / juliang_count, 2),
            "confidence": round(confidence, 2),
            "desc": f"跃跃欲试：横盘振幅{amplitude * 100:.0f}%，{juliang_count}次巨量，阳线占比{yang_count / juliang_count * 100:.0f}%",
        }

    return {"is_ready": False}

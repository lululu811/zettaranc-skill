from typing import Any
from ..core import DailyData, calculate_kdj, calculate_ma


def detect_key_k(klines: list[DailyData], lookback: int = 60) -> list[dict]:
    """
    关键K检测（位置 + 放量 + 长阳/长阴），扫描最近lookback天
    找出那2-3根真正在指挥走势的关键K
    """
    n = len(klines)
    if n < 10:
        return []
    start = max(0, n - lookback)
    scan = klines[start:]
    n = len(scan)
    if n < 10:
        return []

    results = []
    for i in range(max(5, n - 5), n):
        day = scan[i]
        prev = scan[i - 1] if i > 0 else None
        if not prev or prev.close <= 0:
            continue

        body = abs(day.close - day.open)
        body_pct = body / prev.close * 100

        vol_start = max(0, i - 5)
        avg_vol = sum(k.vol for k in scan[vol_start:i]) / max(1, i - vol_start)
        vol_ratio = day.vol / avg_vol if avg_vol > 0 else 0

        is_big_body = body_pct >= 3
        # 大阳线(>=7%)或涨停时放宽量比要求，涨停缩量突破也认可
        vol_threshold = 1.1 if body_pct >= 7 else 1.3
        is_high_vol = vol_ratio >= vol_threshold

        pos_start = max(0, i - 20)
        if i > pos_start:
            recent_high = max(k.high for k in scan[pos_start:i])
            recent_low = min(k.low for k in scan[pos_start:i])
            dist_high = (day.high - recent_high) / recent_high
            dist_low = (recent_low - day.low) / recent_low if recent_low > 0 else 0
            at_key = (dist_high >= -0.02 and dist_high <= 0.15) or (dist_low >= -0.02 and dist_low <= 0.15)
        else:
            at_key = False

        if is_big_body and is_high_vol and at_key:
            results.append(
                {
                    "date": day.trade_date,
                    "close": day.close,
                    "pct": day.pct_chg,
                    "type": "反转" if day.close > day.open else "衰竭",
                    "body_pct": round(body_pct, 1),
                    "vol_ratio": round(vol_ratio, 1),
                    "is_latest": (i == n - 1),
                }
            )

    return results


def detect_violence_k(klines: list[DailyData], lookback: int = 60) -> list[dict]:
    """
    暴力K检测（底部 + 突兀 + 倍量），扫描最近lookback天
    关键K的满配版
    """
    n = len(klines)
    if n < 10:
        return []
    start = max(0, n - lookback)
    scan = klines[start:]
    n = len(scan)
    if n < 10:
        return []

    results = []
    for i in range(max(5, n - 5), n):
        day = scan[i]
        prev = scan[i - 1] if i > 0 else None
        if not prev or prev.close <= 0:
            continue

        body = abs(day.close - day.open)
        body_pct = body / prev.close * 100

        pos_start = max(0, i - 20)
        if i > pos_start:
            recent_low = min(k.low for k in scan[pos_start:i])
            at_bottom = day.low <= recent_low * 1.05
        else:
            at_bottom = False

        body_start = max(0, i - 5)
        prev_bodies = []
        for j in range(body_start, i):
            p = scan[j - 1] if j > 0 else None
            if p and p.close > 0:
                prev_bodies.append(abs(scan[j].close - scan[j].open) / p.close * 100)
        avg_body = sum(prev_bodies) / len(prev_bodies) if prev_bodies else 0
        is_abrupt = body_pct > avg_body * 2 and body_pct >= 5

        vol_start = max(0, i - 5)
        avg_vol = sum(k.vol for k in scan[vol_start:i]) / max(1, i - vol_start)
        vol_ratio = day.vol / avg_vol if avg_vol > 0 else 0
        is_double_vol = vol_ratio >= 2

        if at_bottom and is_abrupt and is_double_vol:
            results.append(
                {
                    "date": day.trade_date,
                    "close": day.close,
                    "pct": day.pct_chg,
                    "type": "大暴力" if vol_ratio >= 3 else "小暴力",
                    "body_pct": round(body_pct, 1),
                    "vol_ratio": round(vol_ratio, 1),
                    "is_latest": (i == n - 1),
                }
            )

    return results


def detect_key_candle(klines: list[DailyData]) -> dict:
    """
    关键 K 检测 —— 走势中管理其他 K 线的关键位置放量长中阳/阴

    来源：key-candles.md
    核心价值：
    1. 判断趋势反转（80分含金量）：下跌→上涨、横盘→上涨等
    2. 判断走势衰竭（20分含金量）：卖盘枯竭/买盘枯竭

    关键K条件：
    1. 关键位置（突破前高、跌破前低、平台边缘）
    2. 放量（量 > 前10日均量 × 1.5）
    3. 实体够大（|收-开| / (高-低) > 0.6）
    4. 阳线 close > open，阴线 close < open

    返回最近一根关键K的信息和趋势转换判断。
    """
    if len(klines) < 20:
        return {"is_key": False}

    today = klines[-1]
    recent_10 = klines[-10:]
    recent_20 = klines[-20:]

    # 实体比例
    body = abs(today.close - today.open)
    range_ = today.high - today.low
    body_ratio = body / range_ if range_ > 0 else 0

    # 放量
    avg_vol_10 = sum(k.vol for k in recent_10) / len(recent_10)
    is_fangliang = today.vol > avg_vol_10 * 1.5

    # 实体够大
    is_big_body = body_ratio > 0.6

    if not is_fangliang or not is_big_body:
        return {"is_key": False}

    # 判断关键位置
    high_20 = max(k.high for k in recent_20[:-1])  # 排除今天
    low_20 = min(k.low for k in recent_20[:-1])
    is_break_high = today.high > high_20 * 1.01  # 突破前高1%
    is_break_low = today.low < low_20 * 0.99  # 跌破前低1%

    # 判断方向
    is_yang = today.close > today.open
    is_yin = today.close < today.open

    result: dict[str, Any] = {"is_key": True, "body_ratio": round(body_ratio, 2)}

    if is_yang and is_break_high:
        result["direction"] = "向上突破"
        result["type"] = "关键阳突破"
        result["confidence"] = 0.90
    elif is_yin and is_break_low:
        result["direction"] = "向下破位"
        result["type"] = "关键阴破位"
        result["confidence"] = 0.90
    elif is_yang:
        result["direction"] = "底部/回调阳"
        result["type"] = "关键阳"
        result["confidence"] = 0.75
    elif is_yin:
        result["direction"] = "顶部/滞涨阴"
        result["type"] = "关键阴"
        result["confidence"] = 0.75
    else:
        return {"is_key": False}

    return result


def detect_key_candle_coverage(klines: list[DailyData]) -> dict:
    """
    关键K管辖范围检测 —— 扫描最近20天寻找关键K，判断当前价是否在其管辖范围内

    核心逻辑：
    1. 扫描最近20天，找到最近一根关键K（复用 detect_key_candle 的判断条件）
    2. 如果找到关键K，记录其上沿（high）和下沿（low）
    3. 检查当前价格是否在关键K上下沿之间（管辖范围）
    4. 检查关键K之后是否缩量洗盘（量能递减）
    5. 判断当前价是否在关键K一半位置（最佳买点）
    """
    empty = {
        "has_key_candle": False,
        "key_date": "",
        "key_high": 0.0,
        "key_low": 0.0,
        "key_direction": "",
        "in_range": False,
        "volume_shrinking": False,
        "buy_point": False,
    }

    if len(klines) < 20:
        return empty

    # 扫描最近20天，从远到近找最近一根关键K
    key_idx = -1
    scan_start = max(0, len(klines) - 20)
    for i in range(scan_start, len(klines)):
        k = klines[i]
        # 取该天之前的窗口（不含当天）
        win_start = max(0, i - 20)
        window = klines[win_start:i]
        if len(window) < 10:
            continue

        # 取该天之前的10天窗口（用于计算均量）
        recent_10 = klines[max(0, i - 10) : i]
        if len(recent_10) < 5:
            continue

        # 实体比例
        body = abs(k.close - k.open)
        range_ = k.high - k.low
        body_ratio = body / range_ if range_ > 0 else 0

        # 放量
        avg_vol_10 = sum(v.vol for v in recent_10) / len(recent_10)
        is_fangliang = k.vol > avg_vol_10 * 1.5

        # 实体够大
        is_big_body = body_ratio > 0.6

        if not is_fangliang or not is_big_body:
            continue

        # 判断关键位置
        high_20 = max(w.high for w in window)
        low_20 = min(w.low for w in window)
        is_break_high = k.high > high_20 * 1.01
        is_break_low = k.low < low_20 * 0.99

        is_yang_k = k.close > k.open
        is_yin_k = k.close < k.open

        # 必须满足关键K条件之一
        if not ((is_yang_k and is_break_high) or (is_yin_k and is_break_low) or is_yang_k or is_yin_k):
            continue

        key_idx = i
        # 不 break，继续往后扫描找更新的关键K

    if key_idx < 0:
        return empty

    key_k = klines[key_idx]
    today = klines[-1]

    # 判断方向
    pre_window = klines[max(0, key_idx - 20) : key_idx]
    if pre_window:
        high_20 = max(w.high for w in pre_window)
        low_20 = min(w.low for w in pre_window)
        if key_k.close > key_k.open and key_k.high > high_20 * 1.01:
            direction = "向上突破"
        elif key_k.close < key_k.open and key_k.low < low_20 * 0.99:
            direction = "向下突破"
        elif key_k.close > key_k.open:
            direction = "向上突破"
        else:
            direction = "向下突破"
    else:
        direction = "向上突破" if key_k.close > key_k.open else "向下突破"

    key_high = key_k.high
    key_low = key_k.low

    # 当前价是否在上下沿之间
    in_range = key_low <= today.close <= key_high

    # 关键K之后是否缩量洗盘（量能递减）
    volume_shrinking = False
    if key_idx < len(klines) - 1:
        post_klines = klines[key_idx + 1 :]
        if len(post_klines) >= 2:
            shrinking = True
            for j in range(1, len(post_klines)):
                if post_klines[j].vol >= post_klines[j - 1].vol:
                    shrinking = False
                    break
            volume_shrinking = shrinking

    # 最佳买点：当前价在关键K一半位置附近（±3%）
    mid = (key_high + key_low) / 2
    buy_point = False
    if key_high > key_low:
        buy_point = abs(today.close - mid) / (key_high - key_low) < 0.15 and in_range

    return {
        "has_key_candle": True,
        "key_date": key_k.trade_date,
        "key_high": round(key_high, 2),
        "key_low": round(key_low, 2),
        "key_direction": direction,
        "in_range": in_range,
        "volume_shrinking": volume_shrinking,
        "buy_point": buy_point,
    }


def detect_abc_stages(klines: list[DailyData]) -> dict:
    """
    ABC三阶段建仓检测

    - A阶段（止跌试水）：近10天内有止跌信号（J值<0后回升），缩量横盘（波动率<3%），量能萎缩
    - B阶段（横盘重仓）：价格在A阶段低点附近横盘，量能温和放大（比A阶段高20-50%），波动率适中
    - C阶段（放量突破）：放量突破B阶段高点，量能 > B阶段均量×1.5
    - 评分制：每个阶段0-100分
    """
    empty = {
        "stage": "未知",
        "a_score": 0.0,
        "b_score": 0.0,
        "c_score": 0.0,
        "confidence": 0.0,
        "action": "观察",
    }

    if len(klines) < 30:
        return empty

    today = klines[-1]

    # ===== A阶段评分（止跌试水）=====
    recent_10 = klines[-10:]
    prev_20 = klines[-30:-10]

    a_score = 0.0

    # 1. J值<0后回升：用最近10天的KDJ序列
    kdj_vals = calculate_kdj(klines[-19:])
    j_val = kdj_vals[2]

    # 检查近10天内J值是否曾经<0
    j_was_negative = False
    for i in range(max(0, len(klines) - 10), len(klines)):
        slice_k = klines[max(0, i - 8) : i + 1]
        if len(slice_k) >= 9:
            _, _, j = calculate_kdj(slice_k)
            if j < 0:
                j_was_negative = True
                break

    if j_was_negative and j_val > 0:
        a_score += 40  # J值从负值回升，止跌信号强
    elif j_was_negative:
        a_score += 20  # J值曾为负但还没回升

    # 2. 缩量横盘（波动率<3%）
    closes_10 = [k.close for k in recent_10]
    if closes_10:
        max_c = max(closes_10)
        min_c = min(closes_10)
        volatility = (max_c - min_c) / min_c if min_c > 0 else 1
        if volatility < 0.03:
            a_score += 30  # 波动率很小，缩量横盘
        elif volatility < 0.05:
            a_score += 15

    # 3. 量能萎缩（最近5天均量 < 前20天均量的60%）
    avg_vol_recent = sum(k.vol for k in recent_10[-5:]) / 5 if len(recent_10) >= 5 else 0
    avg_vol_prev = sum(k.vol for k in prev_20) / len(prev_20) if prev_20 else 1
    if avg_vol_prev > 0:
        vol_ratio = avg_vol_recent / avg_vol_prev
        if vol_ratio < 0.6:
            a_score += 30  # 明显缩量
        elif vol_ratio < 0.8:
            a_score += 15
    a_score = min(a_score, 100)

    # ===== B阶段评分（横盘重仓）=====
    b_score = 0.0

    # A阶段低点（近20天最低）
    a_low = min(k.low for k in klines[-20:])

    # 1. 价格在A阶段低点附近横盘（不跌破低点5%）
    if today.close >= a_low * 0.95:
        b_score += 30
    if today.close >= a_low * 1.0:
        b_score += 10

    # 2. 量能温和放大（比A阶段均量高20-50%）
    if avg_vol_prev > 0 and avg_vol_recent > 0:
        b_vol_ratio = avg_vol_recent / avg_vol_prev
        if 1.2 <= b_vol_ratio <= 1.5:
            b_score += 35  # 温和放大，最佳
        elif 1.0 < b_vol_ratio < 1.2:
            b_score += 20
        elif b_vol_ratio > 1.5:
            b_score += 10  # 放量过猛，可能是C阶段

    # 3. 波动率适中（3%-8%）
    closes_20 = [k.close for k in klines[-20:]]
    if closes_20:
        vol_range = (max(closes_20) - min(closes_20)) / min(closes_20) if min(closes_20) > 0 else 1
        if 0.03 <= vol_range <= 0.08:
            b_score += 25
        elif vol_range < 0.03:
            b_score += 10  # 波动太小，可能还在A阶段

    b_score = min(b_score, 100)

    # ===== C阶段评分（放量突破）=====
    c_score = 0.0

    # B阶段高点（近20天最高）
    b_high = max(k.high for k in klines[-20:])

    # 1. 放量突破B阶段高点
    if today.close > b_high:
        c_score += 40
    elif today.high > b_high:
        c_score += 20  # 盘中突破但未站稳

    # 2. 量能 > B阶段均量×1.5
    b_avg_vol = sum(k.vol for k in klines[-10:]) / 10
    if b_avg_vol > 0 and today.vol > b_avg_vol * 1.5:
        c_score += 35
    elif b_avg_vol > 0 and today.vol > b_avg_vol * 1.2:
        c_score += 20

    # 3. 当日涨幅 > 3%
    if today.pct_chg > 3:
        c_score += 25
    elif today.pct_chg > 1:
        c_score += 10

    c_score = min(c_score, 100)

    # ===== 判断当前阶段 =====
    if c_score >= 60:
        stage = "C"
        confidence = c_score / 100
        action = "突破"
    elif b_score >= 60:
        stage = "B"
        confidence = b_score / 100
        action = "重仓"
    elif a_score >= 40:
        stage = "A"
        confidence = a_score / 100
        action = "试水"
    else:
        stage = "未知"
        confidence = 0.0
        action = "观察"

    return {
        "stage": stage,
        "a_score": round(a_score, 1),
        "b_score": round(b_score, 1),
        "c_score": round(c_score, 1),
        "confidence": round(confidence, 2),
        "action": action,
    }

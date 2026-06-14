from typing import Any
from ..core import DailyData, calculate_kdj
from .brick import calculate_brick_value


def detect_fanbao(klines: list[DailyData]) -> bool:
    """
    检测精准反包信号

    条件：
    1. 今天红柱（砖型图上涨）
    2. 昨天绿柱（砖型图下跌）
    3. 今天砖型图超过昨日绿柱2/3位置
    """
    if len(klines) < 4:
        return False

    brick_today = calculate_brick_value(klines)
    brick_yesterday = calculate_brick_value(klines[:-1])
    brick_before = calculate_brick_value(klines[:-2]) if len(klines) >= 3 else 0

    # 今天红柱
    is_red = brick_today > brick_yesterday
    # 昨天绿柱
    is_green_yesterday = brick_yesterday < brick_before
    # 昨天绿柱的实体高度
    lzgd = max(brick_yesterday, brick_before) - min(brick_yesterday, brick_before)
    # 反包阈值 = 昨日低点 + 2/3高度
    zddd = min(brick_yesterday, brick_before)
    fbwz = zddd + lzgd * 2 / 3

    # 满足2/3反包
    is_fanbao = brick_today > fbwz if lzgd > 0 else False

    return is_red and is_green_yesterday and is_fanbao


def detect_volume_pattern(today: DailyData, yesterday: DailyData | None = None) -> dict[str, bool]:
    """
    检测量价形态
    """
    result = {
        "is_beidou": False,  # 倍量
        "is_suoliang": False,  # 缩量
        "is_jiayin_zhenyang": False,  # 假阴真阳
        "is_jiayang_zhenyin": False,  # 假阳真阴
        "is_fangliang_yinxian": False,  # 放量阴线
    }

    if yesterday is None:
        return result

    # 倍量：今日量 > 昨日量 × 2
    if today.vol >= yesterday.vol * 2:
        result["is_beidou"] = True

    # 缩量：今日量 < 昨日量 × 0.5
    if today.vol <= yesterday.vol * 0.5:
        result["is_suoliang"] = True

    # 假阴真阳：收 < 开 but 收 > 昨收
    if today.close < today.open and today.close > today.prev_close:
        result["is_jiayin_zhenyang"] = True

    # 假阳真阴：收 > 开 but 收 < 昨收
    if today.close > today.open and today.close < today.prev_close:
        result["is_jiayang_zhenyin"] = True

    # 放量阴线：下跌 + 放量
    if today.close < today.prev_close and today.vol > yesterday.vol * 1.5:
        result["is_fangliang_yinxian"] = True

    return result


def detect_didi(klines: list[DailyData]) -> dict:
    """
    滴滴战法检测（高位连续两根阴线下台阶）

    性质：最高优先级卖出信号，绕过防卖飞直接清仓。
    """
    if len(klines) < 2:
        return {"is_didi": False}

    today = klines[-1]
    yesterday = klines[-2]

    # 两根都是阴线（严格：收盘价 < 开盘价）
    is_yin_1 = yesterday.close < yesterday.open
    is_yin_2 = today.close < today.open

    # 下台阶：第二根收盘 < 第一根最低
    is_down_step = today.close < yesterday.low

    # 量未明显萎缩（今天量 >= 昨天量 × 0.8）
    is_volume_ok = today.vol >= yesterday.vol * 0.8 if yesterday.vol > 0 else False

    # 高位判断（当前 >= 近20天最高价的 80%）
    recent = klines[-20:] if len(klines) >= 20 else klines
    recent_high = max(k.high for k in recent)
    is_high = today.close >= recent_high * 0.8

    if is_yin_1 and is_yin_2 and is_down_step and is_volume_ok and is_high:
        return {
            "is_didi": True,
            "first_low": round(yesterday.low, 2),
            "second_close": round(today.close, 2),
            "volume_ratio": round(today.vol / yesterday.vol, 2) if yesterday.vol > 0 else 0,
            "recent_high": round(recent_high, 2),
        }

    return {"is_didi": False}


def calculate_zuchong_target(klines: list[DailyData], lookback: int = 60) -> dict:
    """
    祖冲之法 —— 主力目标价计算

    公式：目标价 = 2a - b
      a = 近期高点（填坑前的高点）
      b = 近期低点（坑底）
    """
    if len(klines) < 10:
        return {"target": 0, "a": 0, "b": 0, "current": 0, "upside_pct": 0}

    recent = klines[-lookback:] if len(klines) >= lookback else klines

    highs = [k.high for k in recent]
    lows = [k.low for k in recent]

    a = max(highs)  # 近期高点
    b = min(lows)  # 近期低点
    current = klines[-1].close

    target = 2 * a - b
    upside_pct = (target - current) / current * 100 if current > 0 else 0

    return {
        "target": round(target, 2),
        "a": round(a, 2),
        "b": round(b, 2),
        "current": round(current, 2),
        "upside_pct": round(upside_pct, 1),
    }


def detect_b1_today(klines: list[DailyData]) -> dict:
    """
    B1建仓波检测（只检查最新这天）
    标准：J<13, 振幅<4%, 涨幅-2%~+1.8%, 缩量
    """
    result: dict[str, Any] = {
        "is_b1": False,
        "b1_j_value": 0.0,
        "b1_amplitude": 0.0,
        "b1_pct_chg": 0.0,
        "b1_volume_shrink": False,
        "b1_score": 0.0,
    }
    if len(klines) < 2:
        return result
    today = klines[-1]
    prev = klines[-2]
    _, _, j = calculate_kdj(klines)
    amplitude = (today.high - today.low) / prev.close * 100 if prev.close > 0 else 0
    pct = today.pct_chg
    vol_shrink = today.vol < prev.vol
    score = 0
    if j < 13:
        score += 1
    if amplitude < 4:
        score += 1
    if -2 <= pct <= 1.8:
        score += 1
    if vol_shrink:
        score += 1
    if score >= 3:
        result["is_b1"] = True
    result["b1_j_value"] = round(j, 2)
    result["b1_amplitude"] = round(amplitude, 2)
    result["b1_pct_chg"] = round(pct, 2)
    result["b1_volume_shrink"] = vol_shrink
    result["b1_score"] = score
    return result


def detect_b2_today(klines: list[DailyData]) -> dict:
    """
    B2突破检测（只检查最新这天）
    标准：B1后5天内, 涨幅>=4%, 放量20%+, J<55
    """
    result: dict[str, Any] = {
        "is_b2": False,
        "b2_follows_b1": False,
        "b2_pct_chg": 0.0,
        "b2_j_value": 0.0,
        "b2_volume_up": False,
        "b2_score": 0.0,
    }
    if len(klines) < 10:
        return result
    today = klines[-1]
    prev = klines[-2]
    if not prev or prev.close <= 0:
        return result
    # 检查最近5天是否有B1痕迹
    has_recent_b1 = False
    for i in range(max(1, len(klines) - 5), len(klines)):
        _, _, j_check = calculate_kdj(klines[: i + 1])
        if j_check < 13:
            has_recent_b1 = True
            break
    _, _, j = calculate_kdj(klines)
    pct = today.pct_chg
    vol_up = today.vol > prev.vol * 1.2
    score = 0
    if has_recent_b1:
        score += 1
    if pct >= 4:
        score += 1
    if j < 55:
        score += 1
    if vol_up:
        score += 1
    if has_recent_b1 and pct >= 4 and score >= 3:
        result["is_b2"] = True
    result["b2_follows_b1"] = has_recent_b1
    result["b2_pct_chg"] = round(pct, 2)
    result["b2_j_value"] = round(j, 2)
    result["b2_volume_up"] = vol_up
    result["b2_score"] = score
    return result


def check_two_30_rule(klines: list[DailyData]) -> dict:
    """
    两个30%原则检查（B1筛选）
    1. B1涨幅约30%
    2. 累计换手率不超过30%
    """
    result: dict[str, Any] = {
        "b1_rally_pct": 0.0,
        "b1_turnover": 0.0,
        "b1_pass_30": False,
    }
    if len(klines) < 10:
        return result
    # 找最近30天的最低点作为B1起点
    lookback = min(30, len(klines))
    lows = [(klines[-lookback + i].low, klines[-lookback + i].close) for i in range(lookback)]
    min_price, min_close = min(lows, key=lambda x: x[0])
    today_close = klines[-1].close
    rally_pct = (today_close - min_close) / min_close * 100 if min_close > 0 else 0
    # 估算累计换手率
    result["b1_rally_pct"] = round(rally_pct, 2)
    result["b1_pass_30"] = 25 <= rally_pct <= 40
    return result


def detect_centipede_pattern(klines: list[DailyData]) -> dict:
    """
    蜈蚣图识别 —— 堆量不涨、影线交替、无呼吸节奏的烂股形态

    五大因子（各0-20分，总分0-100）：
    1. 长上影线比例
    2. 长下影线比例
    3. 十字星比例
    4. 量能无规律
    5. 价格无趋势
    """
    result: dict[str, Any] = {
        "is_centipede": False,
        "score": 0,
        "factors": {},
    }

    if len(klines) < 20:
        return result

    recent = klines[-20:]
    factor_scores: dict[str, int] = {}

    # --- 因子1：长上影线比例 ---
    upper_shadow_days = 0
    for k in recent:
        body = abs(k.close - k.open)
        upper_shadow = k.high - k.close
        if body > 0 and upper_shadow > 2 * body:
            upper_shadow_days += 1
    upper_ratio = upper_shadow_days / 20
    if upper_ratio > 0.4:
        factor_scores["长上影线"] = 20
    elif upper_ratio > 0.25:
        factor_scores["长上影线"] = 10
    else:
        factor_scores["长上影线"] = 0

    # --- 因子2：长下影线比例 ---
    lower_shadow_days = 0
    for k in recent:
        body = abs(k.close - k.open)
        lower_shadow = k.close - k.low
        if body > 0 and lower_shadow > 2 * body:
            lower_shadow_days += 1
    lower_ratio = lower_shadow_days / 20
    if lower_ratio > 0.4:
        factor_scores["长下影线"] = 20
    elif lower_ratio > 0.25:
        factor_scores["长下影线"] = 10
    else:
        factor_scores["长下影线"] = 0

    # --- 因子3：十字星比例 ---
    doji_days = 0
    for k in recent:
        if k.open > 0:
            body_pct = abs(k.close - k.open) / k.open
            if body_pct < 0.01:
                doji_days += 1
    doji_ratio = doji_days / 20
    if doji_ratio > 0.3:
        factor_scores["十字星"] = 20
    elif doji_ratio > 0.15:
        factor_scores["十字星"] = 10
    else:
        factor_scores["十字星"] = 0

    # --- 因子4：量能无规律（变异系数） ---
    volumes = [k.vol for k in recent]
    vol_mean = sum(volumes) / len(volumes)
    if vol_mean > 0:
        vol_std = (sum((v - vol_mean) ** 2 for v in volumes) / len(volumes)) ** 0.5
        vol_cv = vol_std / vol_mean
    else:
        vol_cv = 0
    if vol_cv > 0.8:
        factor_scores["量能无规律"] = 20
    elif vol_cv > 0.5:
        factor_scores["量能无规律"] = 10
    else:
        factor_scores["量能无规律"] = 0

    # --- 因子5：价格无趋势（窄幅震荡 + 高波动） ---
    total_change = (recent[-1].close - recent[0].open) / recent[0].open if recent[0].open > 0 else 0
    daily_pcts = [k.pct_chg for k in recent]
    pct_mean = sum(daily_pcts) / len(daily_pcts)
    pct_std = (sum((p - pct_mean) ** 2 for p in daily_pcts) / len(daily_pcts)) ** 0.5
    is_range_bound = abs(total_change) < 0.05
    is_volatile = pct_std > 2.0
    if is_range_bound and is_volatile:
        factor_scores["价格无趋势"] = 20
    elif is_range_bound or is_volatile:
        factor_scores["价格无趋势"] = 10
    else:
        factor_scores["价格无趋势"] = 0

    # --- 汇总 ---
    total_score = sum(factor_scores.values())
    result["score"] = total_score
    result["factors"] = factor_scores
    result["is_centipede"] = total_score >= 60

    return result

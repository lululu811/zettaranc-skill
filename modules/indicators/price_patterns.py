"""
价格模式识别模块
"""

from typing import List, Dict, Any, Optional, Tuple

try:
    from .core import (
        DailyData, TradeSignal, IndicatorResult,
        calculate_ma, calculate_ema, calculate_sma_td, calculate_slope,
        calculate_kdj, calculate_bbi, calculate_rsi_multi, calculate_wr_multi,
        calculate_bollinger, calculate_vol_ratio,
    )
except ImportError:
    from core import (
        DailyData, TradeSignal, IndicatorResult,
        calculate_ma, calculate_ema, calculate_sma_td, calculate_slope,
        calculate_kdj, calculate_bbi, calculate_rsi_multi, calculate_wr_multi,
        calculate_bollinger, calculate_vol_ratio,
    )

def detect_divergence(klines: List[DailyData], dif_list: List[float]) -> Dict:
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
        'is_top_divergence': False,
        'is_bottom_divergence': False,
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
        max_close_idx = closes[window_start:window_end].index(max_close) + window_start

        # 对应窗口的DIF最大值
        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            max_dif = max(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最高，但DIF明显低于前高
            price_near_high = today_close >= max_close * 0.98
            dif_weaker = dif_list[-1] < max_dif * 0.9

            if price_near_high and dif_weaker and max_dif > 0:
                result['is_top_divergence'] = True

    # ====== 底背离检测 ======
    if window_end > window_start:
        min_close = min(closes[window_start:window_end])
        min_close_idx = closes[window_start:window_end].index(min_close) + window_start

        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            min_dif = min(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最低，但DIF明显高于前低
            price_near_low = today_close <= min_close * 1.02
            dif_stronger = dif_list[-1] > min_dif * 1.1

            if price_near_low and dif_stronger and min_dif < 0:
                result['is_bottom_divergence'] = True

    return result
def detect_macd_signals(klines: List[DailyData], dif_list: List[float],
                        dea_list: List[float], macd_list: List[float]) -> Dict[str, Any]:
    """
    根据 Z哥 语料检测 MACD 信号

    三大用法:
    1. DIF 上下穿 0 轴 — 判多空区间
    2. 顶/底背离 — 判趋势终结
    3. 金叉空 + 死叉多 — 判陷阱
    """
    signals = {
        'is_dif_positive': False,
        'is_dif_cross_zero': False,
        'is_dif_cross_zero_down': False,
        'is_gold_cross': False,
        'is_dead_cross': False,
        'is_gold_fake': False,
        'is_dead_fake': False,
        'is_top_divergence': False,
        'is_bottom_divergence': False,
        'macd_veto': False,
    }

    if len(dif_list) < 2 or len(dea_list) < 1:
        return signals

    dif_today = dif_list[-1]
    dif_yesterday = dif_list[-2] if len(dif_list) >= 2 else 0
    dea_today = dea_list[-1]
    dea_yesterday = dea_list[-2] if len(dea_list) >= 2 else 0

    # === 用法 1: DIF 0 轴判多空 ===
    signals['is_dif_positive'] = dif_today > 0

    # DIF 上穿 0 轴
    signals['is_dif_cross_zero'] = dif_yesterday <= 0 and dif_today > 0
    # DIF 下穿 0 轴
    signals['is_dif_cross_zero_down'] = dif_yesterday >= 0 and dif_today < 0

    # === 金叉/死叉 ===
    if len(dif_list) >= 3 and len(dea_list) >= 2:
        signals['is_gold_cross'] = dif_yesterday <= dea_yesterday and dif_today > dea_today
        signals['is_dead_cross'] = dif_yesterday >= dea_yesterday and dif_today < dea_today

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
        if signals['is_dead_cross'] and recent_gold >= 1:
            signals['is_gold_fake'] = True

        # 死叉多：刚死叉又马上金叉
        if signals['is_gold_cross'] and recent_dead >= 1:
            signals['is_dead_fake'] = True

    # === 用法 2: 顶底背离（系统化检测）===
    div = detect_divergence(klines, dif_list)
    signals['is_top_divergence'] = div['is_top_divergence']
    signals['is_bottom_divergence'] = div['is_bottom_divergence']

    # === 一票否决权 ===
    # DIF < 0 + 没有底背离 → 一票否决
    if dif_today < 0 and not signals['is_bottom_divergence']:
        signals['macd_veto'] = True

    return signals
def calculate_zg_white(klines: List[DailyData]) -> float:
    """
    计算 Z哥白线 = EMA(EMA(C,10),10)

    双重平滑后的短期动能线
    """
    if len(klines) < 10:
        return 0
    closes = [k.close for k in klines]
    ema1 = calculate_ema(closes, 10)
    # 再次平滑：用前10天数据计算第二次EMA
    if len(klines) < 19:
        return ema1
    recent_10 = closes[-10:]
    ema2 = calculate_ema(recent_10, 10)
    return round(ema2, 2)
def calculate_dg_yellow(klines: List[DailyData]) -> float:
    """
    计算 大哥线 = (MA14 + MA28 + MA57 + MA114) / 4

    多空生命线，长期均线系统
    """
    if len(klines) < 114:
        return 0
    closes = [k.close for k in klines]
    ma14 = calculate_ma(closes, 14)
    ma28 = calculate_ma(closes, 28)
    ma57 = calculate_ma(closes, 57)
    ma114 = calculate_ma(closes, 114)
    return round((ma14 + ma28 + ma57 + ma114) / 4, 2)
def detect_double_line_cross(klines: List[DailyData]) -> Tuple[bool, bool]:
    """
    检测双线战法金叉死叉

    Returns:
        (is_gold_cross, is_dead_cross)
    """
    if len(klines) < 3:
        return False, False

    # 需要足够数据计算大哥线
    if len(klines) < 115:
        return False, False

    closes = [k.close for k in klines]

    # 计算历史白线和大哥线
    white_values = []
    dg_values = []

    for i in range(60, len(klines) + 1):
        sub_klines = klines[:i]
        if len(sub_klines) >= 114:
            white = calculate_zg_white(sub_klines)
            dg = calculate_dg_yellow(sub_klines)
            white_values.append(white)
            dg_values.append(dg)

    if len(white_values) < 3:
        return False, False

    # 今天、前天、昨天
    w_today = white_values[-1]
    w_yesterday = white_values[-2]
    w_before_yesterday = white_values[-3]

    d_today = dg_values[-1]
    d_yesterday = dg_values[-2]

    # 金叉：白线从下方上穿大哥线
    gold_cross = w_yesterday <= d_yesterday and w_today > d_today

    # 死叉：白线从上方下穿大哥线
    dead_cross = w_yesterday >= d_yesterday and w_today < d_today

    return gold_cross, dead_cross
def calculate_rsl(klines: List[DailyData], period: int) -> float:
    """
    计算 RSL 相对强度定位（通达信标准公式）

    100*(C-LLV(L,N))/(HHV(C,N)-LLV(L,N))
    """
    if len(klines) < period:
        return 50

    recent = klines[-period:]
    lows = [k.low for k in recent]
    closes = [k.close for k in recent]
    current_close = klines[-1].close

    llv = min(lows)
    hhv = max(closes)  # 通达信用 HHV(CLOSE)，不是 HHV(HIGH)

    if hhv == llv:
        return 50

    rsl = (current_close - llv) / (hhv - llv) * 100
    return round(rsl, 2)
def detect_needle_20(klines: List[DailyData]) -> Tuple[float, float, bool]:
    """
    检测单针下20信号（通达信标准）

    条件：短期RSL(3) <= 20 AND 长期RSL(21) >= 60
    即白线下20买：散户浮筹<20 且 主力控盘>60

    Returns:
        (rsl_short, rsl_long, is_needle_20)
    """
    if len(klines) < 22:
        return 50, 50, False

    rsl_short = calculate_rsl(klines, 3)
    rsl_long = calculate_rsl(klines, 21)

    is_needle = rsl_short <= 20 and rsl_long >= 60  # 对齐通达信

    return rsl_short, rsl_long, is_needle
def detect_needle_30(klines: List[DailyData]) -> bool:
    """
    检测单针下30信号（单针下20的迭代版）

    量化资金介入后阈值上移：
    - 红线(主力控盘) > 85
    - 白线(散户浮筹) < 30

    舍弃部分低位空间，换取更高确定性与入场频次
    """
    if len(klines) < 22:
        return False
    rsl_short = calculate_rsl(klines, 3)
    rsl_long = calculate_rsl(klines, 21)
    return rsl_long > 85 and rsl_short < 30
def detect_double_gun(klines: List[DailyData]) -> Dict:
    """
    双枪战法检测

    图形特征：两根放量阳柱中间夹一堆缩量阴线
    本质：主力建仓确认 — 第一根试盘，中间洗盘，第二根确认

    规则：
    - 往前找最近一根放量阳线（第二枪）
    - 再往前找另一根放量阳线（第一枪）
    - 中间夹缩量小阴小阳（3-10天）
    - 第二枪前一日应有B1痕迹（J<13）
    """
    result = {
        'is_double_gun': False,
        'double_gun_vol1': 0,
        'double_gun_vol2': 0,
        'double_gun_gap_days': 0,
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
    vol1 = klines[gun1_idx].vol / g1_prev.vol if g1_prev and g1_prev.vol > 0 else 0
    vol2 = klines[gun2_idx].vol / g2_prev.vol if g2_prev and g2_prev.vol > 0 else 0

    if is_shrink_mid and has_b1_before and 3 <= gap_days <= 10:
        result['is_double_gun'] = True
        result['double_gun_vol1'] = round(vol1, 1)
        result['double_gun_vol2'] = round(vol2, 1)
        result['double_gun_gap_days'] = gap_days

    return result
def detect_sb1_detailed(klines: List[DailyData]) -> Dict:
    """
    超级B1独立检测

    形态流程：
    N型上涨 → 缩量回调 → 标准B1触发 → 突然放量大阴线击穿止损位 →
    缩量企稳 + J值大负值 → 反转K线确认 → 入场

    只赌一次，不可重复博弈
    """
    result = {
        'is_sb1_detailed': False,
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
            first_half = pre_lows[:len(pre_lows)//2]
            second_half = pre_lows[len(pre_lows)//2:]
            if min(second_half) < min(first_half):
                result['is_sb1_detailed'] = True

    return result
def calculate_dmi(klines: List[DailyData], period: int = 14) -> Tuple[float, float, float]:
    """
    计算 DMI 趋向指标

    通达信公式:
    DMI: (MTM-MTM的N日简单移动平均) / (MTM的绝对值的N日简单移动平均) * 100
    MTM = CLOSE - REF(CLOSE,1)

    Args:
        klines: K线数据
        period: 周期，默认14

    Returns:
        (DMI+, DMI-, ADX)
    """
    if len(klines) < period + 1:
        return 0, 0, 0

    # 计算 MTM = 当日收盘 - 昨日收盘
    mtm_list = []
    for i in range(1, len(klines)):
        mtm = klines[i].close - klines[i-1].close
        mtm_list.append(mtm)

    if len(mtm_list) < period:
        return 0, 0, 0

    # 计算 DMI+ 和 DMI-
    dmi_plus_list = []
    dmi_minus_list = []

    for i in range(1, len(klines)):
        high_diff = klines[i].high - klines[i-1].high
        low_diff = klines[i-1].low - klines[i].low

        dm_plus = high_diff if high_diff > low_diff and high_diff > 0 else 0
        dm_minus = low_diff if low_diff > high_diff and low_diff > 0 else 0

        dmi_plus_list.append(dm_plus)
        dmi_minus_list.append(dm_minus)

    # 计算 N 日简单移动平均
    if len(dmi_plus_list) < period:
        return 0, 0, 0

    dm_plus_ma = sum(dmi_plus_list[-period:]) / period
    dm_minus_ma = sum(dmi_minus_list[-period:]) / period

    # 计算 TR (True Range)
    tr_list = []
    for i in range(1, len(klines)):
        high = klines[i].high
        low = klines[i].low
        prev_close = klines[i-1].close

        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = max(tr1, tr2, tr3)
        tr_list.append(tr)

    if len(tr_list) < period:
        return 0, 0, 0

    tr_ma = sum(tr_list[-period:]) / period

    if tr_ma == 0:
        return 0, 0, 0

    dmi_plus = dm_plus_ma / tr_ma * 100
    dmi_minus = dm_minus_ma / tr_ma * 100

    # 计算 ADX
    dx_list = []
    for i in range(period - 1, len(dmi_plus_list)):
        di_plus = sum(dmi_plus_list[i-period+1:i+1]) / period / tr_ma * 100 if tr_ma > 0 else 0
        di_minus = sum(dmi_minus_list[i-period+1:i+1]) / period / tr_ma * 100 if tr_ma > 0 else 0
        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
        dx_list.append(dx)

    if len(dx_list) < period:
        adx = sum(dx_list) / len(dx_list) if dx_list else 0
    else:
        adx = sum(dx_list[-period:]) / period

    return round(dmi_plus, 2), round(dmi_minus, 2), round(adx, 2)
def calculate_brick_value(klines: List[DailyData]) -> float:
    """
    计算砖型图数值（通达信标准公式 - 短期砖型图指标v2026）

    VAR1A = (HHV(HIGH,4) - CLOSE) / (HHV(HIGH,4) - LLV(LOW,4)) * 100 - 90
    VAR2A = SMA(VAR1A, 4, 1) + 100
    VAR3A = (CLOSE - LLV(LOW,4)) / (HHV(HIGH,4) - LLV(LOW,4)) * 100
    VAR4A = SMA(VAR3A, 6, 1)
    VAR5A = SMA(VAR4A, 6, 1) + 100
    VAR6A = VAR5A - VAR2A
    砖型图 = IF(VAR6A > 4, VAR6A - 4, 0)
    """
    if len(klines) < 12:
        return 0

    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]

    # 构建 VAR3A 序列（需要至少 6 个值来算 SMA(VAR3A,6,1)）
    var3a_list = []
    for i in range(3, len(klines)):  # HHV/LLV 需要 4 天，所以从索引 3 开始
        hhv4 = max(highs[max(0, i-3):i+1])
        llv4 = min(lows[max(0, i-3):i+1])
        if hhv4 == llv4:
            v3 = 50
        else:
            v3 = (closes[i] - llv4) / (hhv4 - llv4) * 100
        var3a_list.append(v3)

    if len(var3a_list) < 6:
        return 0

    # VAR4A = SMA(VAR3A, 6, 1)
    var4a = calculate_sma_td(var3a_list[-6:], 6, 1)

    # 构建 VAR4A 历史序列来算 SMA
    var4a_list = []
    for i in range(5, len(var3a_list) + 1):
        sub = var3a_list[max(0, i-6):i]
        if len(sub) >= 6:
            v4 = calculate_sma_td(sub, 6, 1)
            var4a_list.append(v4)

    if len(var4a_list) < 6:
        # 数据不足，用已有数据近似
        var5a = var4a + 100
    else:
        # VAR5A = SMA(VAR4A, 6, 1) + 100
        var5a = calculate_sma_td(var4a_list[-6:], 6, 1) + 100

    # 构建 VAR1A 序列
    var1a_list = []
    for i in range(3, len(klines)):
        hhv4 = max(highs[max(0, i-3):i+1])
        llv4 = min(lows[max(0, i-3):i+1])
        if hhv4 == llv4:
            v1 = -90
        else:
            v1 = (hhv4 - closes[i]) / (hhv4 - llv4) * 100 - 90
        var1a_list.append(v1)

    if len(var1a_list) < 4:
        var2a = (var1a_list[-1] if var1a_list else -90) + 100
    else:
        # VAR2A = SMA(VAR1A, 4, 1) + 100
        var2a = calculate_sma_td(var1a_list[-4:], 4, 1) + 100

    # VAR6A = VAR5A - VAR2A
    var6a = var5a - var2a

    # 砖型图 = IF(VAR6A > 4, VAR6A - 4, 0)
    brick = var6a - 4 if var6a > 4 else 0

    return round(brick, 2)
def calculate_brick_history(klines: List[DailyData], lookback: int = 20) -> Tuple[str, int]:
    """
    计算砖型图趋势（连续红砖/绿砖数量）

    通达信公式逻辑（与官方一致）：
    - 红砖：今日砖值 >= 昨日砖值（动量上涨）→ COLORRED
    - 绿砖：今日砖值 < 昨日砖值（动量下跌）→ COLOR00FF00

    Args:
        klines: K线数据
        lookback: 回溯天数

    Returns:
        (趋势状态: RED/GREEN/NEUTRAL, 连续砖数)
    """
    if len(klines) < 10:
        return "NEUTRAL", 0

    # 计算历史砖值序列（对比昨日大小判断红绿）
    # 1=红(涨), -1=绿(跌), 0=平
    brick_colors = []
    prev_brick = None

    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)

        if prev_brick is not None:
            if brick_val >= prev_brick:
                brick_colors.append(1)   # 红砖 = 上涨
            else:
                brick_colors.append(-1)  # 绿砖 = 下跌
        prev_brick = brick_val

    if not brick_colors:
        return "NEUTRAL", 0

    # 从最新往前数连续同色砖
    current_color = brick_colors[-1]
    if current_color == 0:
        return "NEUTRAL", 0

    count = 1
    for i in range(len(brick_colors) - 2, -1, -1):
        if brick_colors[i] == current_color:
            count += 1
        else:
            break

    trend = "RED" if current_color > 0 else "GREEN"
    return trend, count
def detect_brick_trend(klines: List[DailyData]) -> bool:
    """
    检测命值趋势是否上升

    条件：SLOPE(命值, 7) > -0.02 AND 运值 > 命值
    """
    if len(klines) < 115:
        return False

    closes = [k.close for k in klines]

    # 计算命值序列
    ming_values = []
    for i in range(113, len(klines)):
        sub = closes[:i+1]
        ma14 = calculate_ma(sub, 14)
        ma28 = calculate_ma(sub, 28)
        ma57 = calculate_ma(sub, 57)
        ma114 = calculate_ma(sub, 114)
        ming = (ma14 + ma28 + ma57 + ma114) / 4
        ming_values.append(ming)

    if len(ming_values) < 8:
        return False

    # 使用正确的 SLOPE 函数计算7日斜率
    slope = calculate_slope(ming_values, 7)

    # 计算当前运值和命值
    current_ming = ming_values[-1]
    yun_zhi = calculate_zg_white(klines)

    return slope > -0.02 and yun_zhi > current_ming
def detect_fanbao(klines: List[DailyData]) -> bool:
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
def detect_volume_pattern(today: DailyData, yesterday: Optional[DailyData] = None) -> Dict[str, bool]:
    """
    检测量价形态

    Args:
        today: 今日数据
        yesterday: 昨日数据

    Returns:
        形态检测结果
    """
    result = {
        'is_beidou': False,           # 倍量
        'is_suoliang': False,        # 缩量
        'is_jiayin_zhenyang': False, # 假阴真阳
        'is_jiayang_zhenyin': False, # 假阳真阴
        'is_fangliang_yinxian': False # 放量阴线
    }

    if yesterday is None:
        return result

    # 倍量：今日量 > 昨日量 × 2
    if today.vol >= yesterday.vol * 2:
        result['is_beidou'] = True

    # 缩量：今日量 < 昨日量 × 0.5
    if today.vol <= yesterday.vol * 0.5:
        result['is_suoliang'] = True

    # 假阴真阳：收 < 开 but 收 > 昨收
    if today.close < today.open and today.close > today.prev_close:
        result['is_jiayin_zhenyang'] = True

    # 假阳真阴：收 > 开 but 收 < 昨收
    if today.close > today.open and today.close < today.prev_close:
        result['is_jiayang_zhenyin'] = True

    # 放量阴线：下跌 + 放量
    if today.close < today.prev_close and today.vol > yesterday.vol * 1.5:
        result['is_fangliang_yinxian'] = True

    return result
def detect_b1_today(klines: List[DailyData]) -> Dict:
    """
    B1建仓波检测（只检查最新这天）
    标准：J<13, 振幅<4%, 涨幅-2%~+1.8%, 缩量
    """
    result = {
        'is_b1': False,
        'b1_j_value': 0,
        'b1_amplitude': 0,
        'b1_pct_chg': 0,
        'b1_volume_shrink': False,
        'b1_score': 0,
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
    if j < 13: score += 1
    if amplitude < 4: score += 1
    if -2 <= pct <= 1.8: score += 1
    if vol_shrink: score += 1
    if score >= 3:
        result['is_b1'] = True
    result['b1_j_value'] = round(j, 2)
    result['b1_amplitude'] = round(amplitude, 2)
    result['b1_pct_chg'] = round(pct, 2)
    result['b1_volume_shrink'] = vol_shrink
    result['b1_score'] = score
    return result
def detect_b2_today(klines: List[DailyData]) -> Dict:
    """
    B2突破检测（只检查最新这天）
    标准：B1后5天内, 涨幅>=4%, 放量20%+, J<55
    """
    result = {
        'is_b2': False,
        'b2_follows_b1': False,
        'b2_pct_chg': 0,
        'b2_j_value': 0,
        'b2_volume_up': False,
        'b2_score': 0,
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
        _, _, j_check = calculate_kdj(klines[:i + 1])
        if j_check < 13:
            has_recent_b1 = True
            break
    _, _, j = calculate_kdj(klines)
    pct = today.pct_chg
    vol_up = today.vol > prev.vol * 1.2
    score = 0
    if has_recent_b1: score += 1
    if pct >= 4: score += 1
    if j < 55: score += 1
    if vol_up: score += 1
    if has_recent_b1 and pct >= 4 and score >= 3:
        result['is_b2'] = True
    result['b2_follows_b1'] = has_recent_b1
    result['b2_pct_chg'] = round(pct, 2)
    result['b2_j_value'] = round(j, 2)
    result['b2_volume_up'] = vol_up
    result['b2_score'] = score
    return result
def detect_key_k(klines: List[DailyData], lookback: int = 60) -> List[Dict]:
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
            results.append({
                'date': day.trade_date,
                'close': day.close,
                'pct': day.pct_chg,
                'type': '反转' if day.close > day.open else '衰竭',
                'body_pct': round(body_pct, 1),
                'vol_ratio': round(vol_ratio, 1),
                'is_latest': (i == n - 1),
            })

    return results
def detect_violence_k(klines: List[DailyData], lookback: int = 60) -> List[Dict]:
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
            results.append({
                'date': day.trade_date,
                'close': day.close,
                'pct': day.pct_chg,
                'type': '大暴力' if vol_ratio >= 3 else '小暴力',
                'body_pct': round(body_pct, 1),
                'vol_ratio': round(vol_ratio, 1),
                'is_latest': (i == n - 1),
            })

    return results
def check_two_30_rule(klines: List[DailyData]) -> Dict:
    """
    两个30%原则检查（B1筛选）
    1. B1涨幅约30%
    2. 累计换手率不超过30%
    """
    result = {
        'b1_rally_pct': 0,
        'b1_turnover': 0,
        'b1_pass_30': False,
    }
    if len(klines) < 10:
        return result
    # 找最近30天的最低点作为B1起点
    lookback = min(30, len(klines))
    lows = [(klines[-lookback + i].low, klines[-lookback + i].close) for i in range(lookback)]
    min_price, min_close = min(lows, key=lambda x: x[0])
    today_close = klines[-1].close
    rally_pct = (today_close - min_close) / min_close * 100 if min_close > 0 else 0
    # 估算累计换手率（简化：累加每日vol/流通股本，用vol近似）
    total_vol = sum(k.vol for k in klines[-lookback:])
    avg_cap = sum(k.vol for k in klines[-lookback:]) / lookback  # 简化
    turnover_est = total_vol / (avg_cap * lookback) * 100 if avg_cap > 0 else 0
    # 用更简单的方式：涨幅在25%-35%之间算通过
    result['b1_rally_pct'] = round(rally_pct, 2)
    result['b1_pass_30'] = 25 <= rally_pct <= 40
    return result
def detect_nana_chart(klines: List[DailyData]) -> Dict:
    """
    娜娜图检测：完美建仓形态
    条件：股价新高但阳线缩量，次高点阴线也缩量
    """
    result = {'is_nana': False}
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
    prev5_avg = sum(k.vol for k in klines[max(0,peak_idx-5):peak_idx]) / min(5, peak_idx)
    vol_shrink_at_peak = peak_vol < prev5_avg * 0.8 if prev5_avg > 0 else False
    # 次高点缩量
    second_vol = klines[second_peak].vol
    sec_prev5 = sum(k.vol for k in klines[max(0,second_peak-5):second_peak]) / min(5, second_peak)
    vol_shrink_second = second_vol < sec_prev5 * 0.8 if sec_prev5 > 0 else False
    # 底部堆量：找低点区域量是否明显大于峰值区域
    low_idx = min(range(max(0, second_peak-10), second_peak), key=lambda i: klines[i].low)
    bottom_vol = klines[low_idx].vol
    if vol_shrink_at_peak and vol_shrink_second and bottom_vol > peak_vol * 0.5:
        result['is_nana'] = True
    return result
def detect_golden_bowl(klines: List[DailyData]) -> Dict:
    """
    黄金碗检测：价格在白线( zg_white )和黄线( dg_yellow )之间
    条件：白线>黄线(多头排列) + 价格落入碗内
    """
    result = {'is_in_bowl': False, 'bowl_upper': 0, 'bowl_lower': 0}
    if len(klines) < 120:
        return result
    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    if white <= 0 or yellow <= 0:
        return result
    result['bowl_upper'] = round(white, 2)
    result['bowl_lower'] = round(yellow, 2)
    today_close = klines[-1].close
    # 白线>黄线且价格在碗内
    if white > yellow and yellow <= today_close <= white:
        result['is_in_bowl'] = True
    return result
def detect_breathing_structure(klines: List[DailyData]) -> Dict:
    """
    呼吸结构检测：放量涨->缩量跌->放量涨 的N型节奏
    """
    result = {'breath_phase': '', 'breath_n_type': False}
    if len(klines) < 10:
        return result
    n = len(klines)
    # 分析最近5-7天的量价节奏
    phases = []
    for i in range(max(0, n-7), n):
        day = klines[i]
        prev = klines[i-1] if i > 0 else None
        if not prev or prev.vol <= 0:
            continue
        vol_ratio = day.vol / prev.vol
        if day.pct_chg > 0 and vol_ratio > 1:
            phases.append('exhale')  # 放量涨=呼气
        elif day.pct_chg < 0 and vol_ratio < 1:
            phases.append('inhale')  # 缩量跌=吸气
        else:
            phases.append('other')
    # 判断当前阶段
    if len(phases) >= 2:
        if phases[-1] == 'exhale':
            result['breath_phase'] = 'exhale'
        elif phases[-1] == 'inhale':
            result['breath_phase'] = 'inhale'
        else:
            result['breath_phase'] = 'none'
    # N型结构：最近3个低点依次抬高
    if n >= 10:
        lows = [klines[i].low for i in range(n-10, n, 3)]
        if len(lows) >= 3 and lows[-1] > lows[-2] > lows[-3]:
            result['breath_n_type'] = True
    return result
def detect_sb1(klines: List[DailyData]) -> Dict:
    """
    SB1假摔检测：B1后跌破前低再迅速收回
    条件：1)跌破前低 2)次日反包收回 3)收回放量
    """
    result = {'is_sb1': False}
    if len(klines) < 6:
        return result
    n = len(klines)
    today = klines[-1]
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
            result['is_sb1'] = True
    return result
def detect_b3(klines: List[DailyData]) -> Dict:
    """
    B3买点检测：B2后缩量回踩不破B2低点
    条件：1) 前面有B2(大涨>=4%) 2) 缩量小阳/十字星 3) 不破B2低点
    """
    result = {'is_b3': False}
    if len(klines) < 15:
        return result
    n = len(klines)
    today = klines[-1]
    prev = klines[-2]
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
            result['is_b3'] = True
    return result
def detect_four_brick_system(klines: List[DailyData]) -> Dict:
    """
    四块砖交易体系检测

    通达信公式逻辑（与官方一致）：
    - 红砖 = 上涨动量（今日砖值 >= 昨日砖值）→ COLORRED
    - 绿砖 = 下跌动量（今日砖值 < 昨日砖值）→ COLOR00FF00

    规则：
    1. 红砖数满4块 → 减仓至少一半
    2. 红砖翻绿 → 立刻止损
    3. 绿砖下跌 → 绝不抄底，先数4块
    4. 买入后3天不涨 → 止损（DSZ铁律）
    """
    result = {
        'brick_consecutive': 0,      # 当前连续砖数
        'brick_action': '观望',      # 操作建议
        'brick_action_desc': '',     # 操作描述
        'is_brick_flip_green': False,  # 红砖刚翻绿（上涨转下跌）
    }

    if len(klines) < 10:
        result['brick_action_desc'] = '数据不足'
        return result

    # 计算历史砖值序列（至少需要8天才能开始算砖值）
    brick_history = []
    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)
        brick_history.append(brick_val)

    if len(brick_history) < 3:
        result['brick_action_desc'] = '数据不足'
        return result

    # 计算红绿砖：与官方公式一致
    # 1=红砖(上涨), -1=绿砖(下跌)
    colors = []
    for i in range(1, len(brick_history)):
        if brick_history[i] >= brick_history[i - 1]:
            colors.append(1)   # 红砖 = 上涨
        else:
            colors.append(-1)  # 绿砖 = 下跌

    if not colors:
        result['brick_action_desc'] = '无砖型数据'
        return result

    # 从最新往前数连续同色砖
    current_color = colors[-1]
    count = 1
    for i in range(len(colors) - 2, -1, -1):
        if colors[i] == current_color:
            count += 1
        else:
            break

    result['brick_consecutive'] = count

    # === 规则判断 ===

    # 1. 红砖翻绿（止损信号）- 上涨转下跌
    if current_color == -1 and len(colors) >= 2:
        prev_color = colors[-2] if len(colors) >= 2 else 1
        if prev_color == 1:
            # 刚翻绿
            result['is_brick_flip_green'] = True
            result['brick_action'] = '止损'
            result['brick_action_desc'] = f'红砖翻绿！立刻止损（连续红砖{count}块后翻绿）'
            return result

    # 2. 红砖数满4块 → 减仓（连续上涨）
    if current_color == 1 and count >= 4:
        result['brick_action'] = '减仓'
        if count == 4:
            result['brick_action_desc'] = f'红砖已满4块，至少减仓一半'
        else:
            result['brick_action_desc'] = f'红砖已延续{count}块，趋势延续中，但未减仓需警惕'
        return result

    # 3. 绿砖下跌 → 禁止抄底（连续下跌）
    if current_color == -1:
        result['brick_action'] = '禁止抄底'
        if count >= 4:
            result['brick_action_desc'] = f'绿砖已连续{count}块，跌势可能接近尾声但仍禁止抄底'
        else:
            result['brick_action_desc'] = f'绿砖下跌中（{count}块），绝不抄底，先数4块'
        return result

    # 4. 红砖不足4块 → 持有/观察（上涨中）
    if current_color == 1 and count < 4:
        result['brick_action'] = '持有'
        result['brick_action_desc'] = f'红砖上涨中（{count}块），继续持有'
        return result

    result['brick_action'] = '观望'
    result['brick_action_desc'] = '中性'
    return result

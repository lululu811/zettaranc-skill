"""
量价模式检测模块
"""

from typing import List, Dict, Any, Optional, Tuple

try:
    from .core import (
        DailyData, TradeSignal, IndicatorResult,
        calculate_ma, calculate_bbi, calculate_kdj, calculate_macd,
    )
    from .price_patterns import detect_volume_pattern, detect_macd_signals
except ImportError:
    from core import (
        DailyData, TradeSignal, IndicatorResult,
        calculate_ma, calculate_bbi, calculate_kdj, calculate_macd,
    )
    from price_patterns import detect_volume_pattern, detect_macd_signals

def detect_volume_anomaly(klines: List[DailyData]) -> Dict:
    """
    异动选股法检测

    核心：成交量突然放大 + 价随量升 + 位置（60日线附近或下方）

    分级：
    - 詹姆斯级：建仓波大开大合，放巨量、假阴真阳反包、阳线密集堆积
    - 徐杰级：仅一根放量阳线，量能没堆起来

    返回异动信息，供后续缩量回调时介入
    """
    result = {
        'is_yidong': False,
        'yidong_type': '',
        'yidong_vol_ratio': 0,
        'yidong_above_60d': False,
    }
    if len(klines) < 65:  # 需要60日均线数据
        return result

    today = klines[-1]
    prev = klines[-2] if len(klines) > 1 else None
    if not prev or prev.vol <= 0:
        return result

    # 量比检测：今日量 / 5日均量 >= 2.0
    avg_vol_5 = sum(klines[i].vol for i in range(max(1, len(klines)-6), len(klines)-1)) / 5
    vol_ratio = today.vol / avg_vol_5 if avg_vol_5 > 0 else 0

    if vol_ratio < 2.0:
        return result

    # 价随量升：收盘涨且不是滞涨（涨幅/量比合理）
    if today.pct_chg <= 0:
        return result

    # 位置检测：收盘价是否在60日线附近或下方
    closes_60 = [k.close for k in klines[-60:]]
    ma60 = sum(closes_60) / 60
    above_60d = today.close >= ma60 * 0.95  # 在60日线上下5%以内或上方

    result['yidong_vol_ratio'] = round(vol_ratio, 2)
    result['yidong_above_60d'] = above_60d

    # 判断异动等级
    # 詹姆斯级：量大 + 涨幅可观 + 有阳线堆积迹象
    if vol_ratio >= 3.0 and today.pct_chg >= 5:
        # 检查最近几天是否有阳线堆积
        red_count = sum(1 for k in klines[-5:] if k.close > k.open)
        if red_count >= 3:
            result['is_yidong'] = True
            result['yidong_type'] = '詹姆斯级'
            return result

    # 徐杰级：单根放量阳线
    if vol_ratio >= 2.0 and today.pct_chg >= 2:
        result['is_yidong'] = True
        result['yidong_type'] = '徐杰级'

    return result
def calculate_sell_score(klines: List[DailyData]) -> Tuple[int, str, Dict[str, bool]]:
    """
    计算防卖飞评分 V1.4（5分制）

    评分条件：
    1. 收盘涨？ +1
    2. BBI 没破？ +1
    3. 不是放量阴线？ +1
    4. 趋势还向上？ +1
    5. J 没死叉？ +1

    Returns:
        (评分, 满分描述, 明细字典)
    """
    if len(klines) < 2:
        return 3, "数据不足", {}

    today = klines[-1]
    yesterday = klines[-2]

    score = 5
    reasons = []
    items = {}

    # 1. 收盘涨？
    close_up = today.close > today.prev_close if hasattr(today, 'prev_close') and today.prev_close > 0 else today.pct_chg > 0
    items['收盘上涨'] = close_up
    if not close_up:
        score -= 1
        reasons.append("收盘不涨")

    # 2. BBI 没破？
    if len(klines) >= 24:
        bbi = calculate_bbi(klines)
        bbi_ok = today.close >= bbi
        items['BBI支撑'] = bbi_ok
        if not bbi_ok:
            score -= 1
            reasons.append("跌破BBI")

    # 3. 不是放量阴线？
    vol_pattern = detect_volume_pattern(today, yesterday)
    not_bearish_vol = not vol_pattern['is_fangliang_yinxian']
    items['非放量阴线'] = not_bearish_vol
    if not not_bearish_vol:
        score -= 1
        reasons.append("放量阴线")

    # 4. 趋势还向上？（用简单均线判断）
    if len(klines) >= 5:
        ma5_today = calculate_ma([k.close for k in klines[-5:]], 5)
        ma5_yesterday = calculate_ma([k.close for k in klines[-6:-1]], 5)
        trend_up = ma5_today > ma5_yesterday
        items['趋势向上'] = trend_up
        if not trend_up:
            score -= 1
            reasons.append("均线向下")

    # 5. J 没死叉？
    if len(klines) >= 9:
        k, d, j = calculate_kdj(klines)
        j_ok = j >= d or j < 80  # J没有从高位下穿
        items['KDJ未死叉'] = j_ok
        if not j_ok:
            score -= 1
            reasons.append("KDJ死叉")

    reason_str = "；".join(reasons) if reasons else "无扣分项"
    return score, reason_str, items
def detect_trade_signal(klines: List[DailyData]) -> TradeSignal:
    """
    检测交易信号（集成 MACD 一票否决权）

    Args:
        klines: K线数据（至少30天）

    Returns:
        信号类型
    """
    if len(klines) < 30:
        return TradeSignal.WATCH

    today = klines[-1]
    yesterday = klines[-2]

    # 计算当前指标
    k, d, j = calculate_kdj(klines)
    dif_list, dea_list, macd_list = calculate_macd(klines)
    macd_hist = macd_list[-1] if macd_list else 0

    # MACD 语料判断
    macd_signals = {}
    if dif_list and dea_list:
        macd_signals = detect_macd_signals(klines, dif_list, dea_list, macd_list)

    # === 一票否决权：MACD 说不能买 → 绝对不买 ===
    if macd_signals.get('macd_veto', False):
        return TradeSignal.WATCH

    if macd_signals.get('is_gold_fake', False):
        return TradeSignal.S1

    bbi = calculate_bbi(klines)
    vol_pattern = detect_volume_pattern(today, yesterday)

    # ========== 卖出信号检测 ==========

    # S1: 放量阴线（最高优先级）
    if vol_pattern['is_fangliang_yinxian'] and today.pct_chg < -3:
        return TradeSignal.S1

    if macd_signals.get('is_top_divergence', False):
        return TradeSignal.S2

    if macd_signals.get('is_bottom_divergence', False):
        return TradeSignal.B1

    if macd_signals.get('is_dead_fake', False):
        return TradeSignal.B2

    if j < -10 and vol_pattern['is_suoliang']:
        return TradeSignal.B1

    # B2: B1后放量确认
    if j > -10 and j < 55:
        prev_j_list = []
        for i in range(2, min(10, len(klines))):
            pk, pd, pj = calculate_kdj(klines[:-i])
            prev_j_list.append(pj)

        if any(pj < -10 for pj in prev_j_list):
            if today.pct_chg > 4 and vol_pattern['is_beidou']:
                return TradeSignal.B2

    if len(klines) >= 5:
        prev_2 = klines[-3]
        if prev_2.close < prev_2.open and prev_2.vol > klines[-4].vol * 1.5:
            if j < -5 and vol_pattern['is_suoliang']:
                return TradeSignal.SB1

    if today.close > bbi and j > 0 and today.pct_chg > 0:
        return TradeSignal.HOLD

    return TradeSignal.WATCH

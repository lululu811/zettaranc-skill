"""
技术指标数据层模块
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

try:
    from .core import (
        DB_PATH, get_db_connection,
        DailyData, TradeSignal, IndicatorResult,
        calculate_ma, calculate_ema, calculate_kdj, calculate_bbi,
        calculate_rsi_multi, calculate_wr_multi, calculate_bollinger,
        calculate_vol_ratio, calculate_macd, get_data_mode,
    )
    from .price_patterns import (
        calculate_zg_white, calculate_dg_yellow, detect_double_line_cross,
        detect_needle_20, detect_needle_30,
        calculate_brick_value, calculate_brick_history, detect_brick_trend, detect_fanbao,
        detect_b1_today, detect_b2_today, detect_key_k, detect_violence_k,
        check_two_30_rule, detect_nana_chart, detect_golden_bowl,
        detect_breathing_structure, detect_sb1, detect_sb1_detailed,
        detect_b3, detect_double_gun, detect_four_brick_system,
        detect_volume_pattern,
        detect_macd_signals, calculate_dmi,
    )
    from .volume_patterns import (
        detect_volume_anomaly, calculate_sell_score, detect_trade_signal,
    )
except ImportError:
    from core import (
        DB_PATH, get_db_connection,
        DailyData, TradeSignal, IndicatorResult,
        calculate_ma, calculate_ema, calculate_kdj, calculate_bbi,
        calculate_rsi_multi, calculate_wr_multi, calculate_bollinger,
        calculate_vol_ratio, calculate_macd, get_data_mode,
    )
    from price_patterns import (
        calculate_zg_white, calculate_dg_yellow, detect_double_line_cross,
        detect_needle_20, detect_needle_30,
        calculate_brick_value, calculate_brick_history, detect_brick_trend, detect_fanbao,
        detect_b1_today, detect_b2_today, detect_key_k, detect_violence_k,
        check_two_30_rule, detect_nana_chart, detect_golden_bowl,
        detect_breathing_structure, detect_sb1, detect_sb1_detailed,
        detect_b3, detect_double_gun, detect_four_brick_system,
        detect_volume_pattern,
        detect_macd_signals, calculate_dmi,
    )
    from volume_patterns import (
        detect_volume_anomaly, calculate_sell_score, detect_trade_signal,
    )

# 加载项目内的 .env（fallback）
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

# 指标缓存层（内存 + SQLite）
_indicator_memory_cache: Dict[Tuple[str, str], IndicatorResult] = {}


def _load_indicator_cache(ts_code: str, trade_date: str) -> Optional[IndicatorResult]:
    """
    从 indicator_cache 表加载指标结果

    Returns:
        IndicatorResult 或 None（缓存未命中）
    """
    # 1. 先查内存缓存
    mem_key = (ts_code, trade_date)
    if mem_key in _indicator_memory_cache:
        return _indicator_memory_cache[mem_key]

    # 2. 查数据库缓存
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM indicator_cache
            WHERE ts_code = ? AND trade_date = ?
        """, (ts_code, trade_date))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # 映射数据库字段到 IndicatorResult
        result = IndicatorResult(
            ts_code=row['ts_code'],
            trade_date=row['trade_date'],
            k=row['k'] or 0,
            d=row['d'] or 0,
            j=row['j'] or 0,
            dif=row['dif'] or 0,
            dea=row['dea'] or 0,
            macd_hist=row['macd_hist'] or 0,
            bbi=row['bbi'] or 0,
            ma5=row['ma5'] or 0,
            ma10=row['ma10'] or 0,
            ma20=row['ma20'] or 0,
            ma60=row['ma60'] or 0,
            rsi6=row['rsi6'] or 0,
            rsi12=row['rsi12'] or 0,
            rsi24=row['rsi24'] or 0,
            wr5=row['wr5'] or 0,
            wr10=row['wr10'] or 0,
            boll_mid=row['boll_mid'] or 0,
            boll_upper=row['boll_upper'] or 0,
            boll_lower=row['boll_lower'] or 0,
            boll_width=row['boll_width'] or 0,
            boll_position=row['boll_position'] or 0,
            vol_ratio=row['vol_ratio'] or 0,
            zg_white=row['zg_white'] or 0,
            dg_yellow=row['dg_yellow'] or 0,
            is_gold_cross=bool(row['is_gold_cross']),
            is_dead_cross=bool(row['is_dead_cross']),
            rsl_short=row['rsl_short'] or 0,
            rsl_long=row['rsl_long'] or 0,
            is_needle_20=bool(row['is_needle_20']),
            brick_value=row['brick_value'] or 0,
            brick_trend=row['brick_trend'] or 'NEUTRAL',
            brick_count=row['brick_count'] or 0,
            brick_trend_up=bool(row['brick_trend_up']),
            is_fanbao=bool(row['is_fanbao']),
            is_beidou=bool(row['is_beidou']),
            is_suoliang=bool(row['is_suoliang']),
            is_jiayin_zhenyang=bool(row['is_jiayin_zhenyang']),
            is_jiayang_zhenyin=bool(row['is_jiayang_zhenyin']),
            is_fangliang_yinxian=bool(row['is_fangliang_yinxian']),
            sell_score=row['sell_score'] or 0,
            prev_high=row['prev_high'] or 0,
            prev_low=row['prev_low'] or 0,
            dmi_plus=row['dmi_plus'] or 0,
            dmi_minus=row['dmi_minus'] or 0,
            adx=row['adx'] or 0,
            net_lg_mf=row['net_lg_mf'] or 0,
            net_elg_mf=row['net_elg_mf'] or 0,
            last_b1_date=row['last_b1_date'] or '',
            last_b1_price=row['last_b1_price'] or 0,
            signal=TradeSignal(row['signal']) if row['signal'] and row['signal'] in [e.value for e in TradeSignal] else TradeSignal.WATCH,
        )

        # 写入内存缓存
        _indicator_memory_cache[mem_key] = result
        return result

    except Exception:
        return None
def _save_indicator_cache(result: IndicatorResult, klines: List[DailyData]) -> bool:
    """
    将指标结果写入 indicator_cache 表

    Args:
        result: 指标计算结果
        klines: 原始K线数据（用于补充基础行情字段）

    Returns:
        是否成功
    """
    if not klines:
        return False

    today = klines[-1]
    yesterday = klines[-2] if len(klines) > 1 else None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO indicator_cache
            (ts_code, trade_date, close, open, high, low, vol, pct_chg,
             k, d, j, dif, dea, macd_hist, bbi,
             ma5, ma10, ma20, ma60,
             rsi6, rsi12, rsi24, wr5, wr10,
             boll_mid, boll_upper, boll_lower, boll_width, boll_position,
             vol_ratio, zg_white, dg_yellow,
             is_gold_cross, is_dead_cross,
             rsl_short, rsl_long, is_needle_20,
             brick_value, brick_trend, brick_count, brick_trend_up, is_fanbao,
             is_beidou, is_suoliang, is_jiayin_zhenyang, is_jiayang_zhenyin, is_fangliang_yinxian,
             sell_score, sell_reason, signal, signal_desc,
             prev_high, prev_low, dmi_plus, dmi_minus, adx,
             net_lg_mf, net_elg_mf, last_b1_date, last_b1_price,
             last_yidong_date, market_pct_chg, market_dir, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.ts_code, result.trade_date, today.close, today.open, today.high, today.low, today.vol, today.pct_chg,
            result.k, result.d, result.j, result.dif, result.dea, result.macd_hist, result.bbi,
            result.ma5, result.ma10, result.ma20, result.ma60,
            result.rsi6, result.rsi12, result.rsi24, result.wr5, result.wr10,
            result.boll_mid, result.boll_upper, result.boll_lower, result.boll_width, result.boll_position,
            result.vol_ratio, result.zg_white, result.dg_yellow,
            int(result.is_gold_cross), int(result.is_dead_cross),
            result.rsl_short, result.rsl_long, int(result.is_needle_20),
            result.brick_value, result.brick_trend, result.brick_count, int(result.brick_trend_up), int(result.is_fanbao),
            int(result.is_beidou), int(result.is_suoliang), int(result.is_jiayin_zhenyang), int(result.is_jiayang_zhenyin), int(result.is_fangliang_yinxian),
            result.sell_score, '',
            result.signal.value if hasattr(result.signal, 'value') else str(result.signal),
            result.signal.value if hasattr(result.signal, 'value') else str(result.signal),
            result.prev_high, result.prev_low, result.dmi_plus, result.dmi_minus, result.adx,
            result.net_lg_mf, result.net_elg_mf, result.last_b1_date, result.last_b1_price,
            '', 0, 'NEUTRAL', None
        ))

        conn.commit()
        conn.close()

        # 写入内存缓存
        _indicator_memory_cache[(result.ts_code, result.trade_date)] = result
        return True

    except Exception:
        return False
def clear_indicator_memory_cache():
    """清空内存缓存（用于测试或数据更新后）"""
    _indicator_memory_cache.clear()
def get_kline_data(ts_code: str, days: int = 100) -> List[DailyData]:
    """
    获取K线数据

    Args:
        ts_code: 股票代码
        days: 获取天数

    Returns:
        K线数据列表（按日期升序）
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
        FROM (
            SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
            FROM daily_kline
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT ?
        )
        ORDER BY trade_date ASC
    """, (ts_code, days))

    rows = cursor.fetchall()
    conn.close()

    data_list = []
    for i, row in enumerate(rows):
        prev_close = rows[i-1]['close'] if i > 0 else row['close']
        data_list.append(DailyData(
            ts_code=row['ts_code'],
            trade_date=row['trade_date'],
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            vol=row['vol'],
            amount=row['amount'],
            pct_chg=row['pct_chg'],
            prev_close=prev_close
        ))

    return data_list
def get_realtime_data(ts_code: str) -> Optional[DailyData]:
    """
    获取实时/最新行情数据
    需要外部传入实时数据，这里仅作为数据结构定义
    """
    # 实际使用时由 tushare_client 获取实时数据
    pass
def analyze_stock(ts_code: str, days: int = 100) -> IndicatorResult:
    """
    综合分析单只股票

    Args:
        ts_code: 股票代码
        days: 分析数据天数

    Returns:
        指标计算结果
    """
    klines = get_kline_data(ts_code, days)

    if not klines:
        return IndicatorResult(ts_code=ts_code, trade_date="")

    today = klines[-1]
    yesterday = klines[-2] if len(klines) > 1 else None

    # ===== 缓存查询 =====
    cached = _load_indicator_cache(ts_code, today.trade_date)
    if cached:
        return cached

    result = IndicatorResult(
        ts_code=ts_code,
        trade_date=today.trade_date
    )

    # 计算 KDJ
    k, d, j = calculate_kdj(klines)
    result.k = k
    result.d = d
    result.j = j

    # 计算 MACD（通达信标准公式，返回完整序列）
    if len(klines) >= 30:
        dif_list, dea_list, macd_list = calculate_macd(klines)
        if dif_list and dea_list and macd_list:
            # 最新值
            result.dif = round(dif_list[-1], 4)
            result.dea = round(dea_list[-1], 4)
            result.macd_hist = round(macd_list[-1], 4)

    # MACD 语料判断
            macd_signals = detect_macd_signals(klines, dif_list, dea_list, macd_list)
            result.is_dif_positive = macd_signals['is_dif_positive']
            result.is_dif_cross_zero = macd_signals['is_dif_cross_zero']
            result.is_dif_cross_zero_down = macd_signals['is_dif_cross_zero_down']
            result.macd_gold_cross = macd_signals['is_gold_cross']
            result.macd_dead_cross = macd_signals['is_dead_cross']
            result.is_gold_fake = macd_signals['is_gold_fake']
            result.is_dead_fake = macd_signals['is_dead_fake']
            result.is_top_divergence = macd_signals['is_top_divergence']
            result.is_bottom_divergence = macd_signals['is_bottom_divergence']
            result.macd_veto = macd_signals['macd_veto']

    # 计算 BBI（需要足够历史数据）
    if len(klines) >= 24:
        result.bbi = calculate_bbi(klines)

    # 计算均线
    closes = [k.close for k in klines]
    if len(closes) >= 5:
        result.ma5 = calculate_ma(closes, 5)
    if len(closes) >= 10:
        result.ma10 = calculate_ma(closes, 10)
    if len(closes) >= 20:
        result.ma20 = calculate_ma(closes, 20)
    if len(closes) >= 60:
        result.ma60 = calculate_ma(closes, 60)
    # 52周（约240交易日）最高价
    if len(klines) >= 240:
        highs = [k.high for k in klines[-240:]]
        result.high_52w = max(highs)
        result.high_52w_dist = (result.high_52w - today.close) / today.close * 100

    # 计算 RSI
    if len(klines) >= 25:
        rsi6, rsi12, rsi24 = calculate_rsi_multi(klines)
        result.rsi6 = rsi6
        result.rsi12 = rsi12
        result.rsi24 = rsi24

    # 计算 WR
    if len(klines) >= 10:
        wr5, wr10 = calculate_wr_multi(klines)
        result.wr5 = wr5
        result.wr10 = wr10

    # 计算布林带
    if len(klines) >= 20:
        boll_mid, boll_upper, boll_lower, boll_width, boll_pos = calculate_bollinger(klines)
        result.boll_mid = boll_mid
        result.boll_upper = boll_upper
        result.boll_lower = boll_lower
        result.boll_width = boll_width
        result.boll_position = boll_pos

    # 计算量比
    result.vol_ratio = calculate_vol_ratio(klines)

    # ========== Z哥双线战法 ==========
    if len(klines) >= 115:
        result.zg_white = calculate_zg_white(klines)
        result.dg_yellow = calculate_dg_yellow(klines)
        gold_cross, dead_cross = detect_double_line_cross(klines)
        result.is_gold_cross = gold_cross
        result.is_dead_cross = dead_cross

    # ========== 单针下20 ==========
    if len(klines) >= 22:
        rsl_s, rsl_l, is_needle = detect_needle_20(klines)
        result.rsl_short = rsl_s
        result.rsl_long = rsl_l
        result.is_needle_20 = is_needle

    # ========== 单针下30 ==========
    if len(klines) >= 22:
        result.is_needle_30 = detect_needle_30(klines)

    # ========== 砖型图系统 ==========
    if len(klines) >= 10:
        result.brick_value = calculate_brick_value(klines)
        brick_trend, brick_count = calculate_brick_history(klines)
        result.brick_trend = brick_trend
        result.brick_count = brick_count
        result.brick_trend_up = detect_brick_trend(klines)
        result.is_fanbao = detect_fanbao(klines)

    # ========== 关键价位 ==========
    if len(klines) >= 2:
        result.prev_high = klines[-2].high
        result.prev_low = klines[-2].low

    # ========== DMI/ADX ==========
    if len(klines) >= 30:
        dmi_plus, dmi_minus, adx = calculate_dmi(klines)
        result.dmi_plus = dmi_plus
        result.dmi_minus = dmi_minus
        result.adx = adx

    # 量价形态检测
    vol_pattern = detect_volume_pattern(today, yesterday)
    result.is_beidou = vol_pattern['is_beidou']
    result.is_suoliang = vol_pattern['is_suoliang']
    result.is_jiayin_zhenyang = vol_pattern['is_jiayin_zhenyang']
    result.is_jiayang_zhenyin = vol_pattern['is_jiayang_zhenyin']
    result.is_fangliang_yinxian = vol_pattern['is_fangliang_yinxian']

    # ========== B1建仓波检测 ==========
    if len(klines) >= 10:
        b1 = detect_b1_today(klines)
        result.is_b1 = b1['is_b1']
        result.b1_j_value = b1['b1_j_value']
        result.b1_amplitude = b1['b1_amplitude']
        result.b1_pct_chg = b1['b1_pct_chg']
        result.b1_volume_shrink = b1['b1_volume_shrink']
        result.b1_score = b1['b1_score']

    # ========== B2突破检测 ==========
    if len(klines) >= 10:
        b2 = detect_b2_today(klines)
        result.is_b2 = b2['is_b2']
        result.b2_follows_b1 = b2['b2_follows_b1']
        result.b2_pct_chg = b2['b2_pct_chg']
        result.b2_j_value = b2['b2_j_value']
        result.b2_volume_up = b2['b2_volume_up']
        result.b2_score = b2['b2_score']

    # ========== 关键K检测（扫描60日） ==========
    if len(klines) >= 10:
        result.key_k_list = detect_key_k(klines)

    # ========== 暴力K检测（扫描60日） ==========
    if len(klines) >= 10:
        vk_list = detect_violence_k(klines)
        if vk_list:
            latest_vk = [v for v in vk_list if v.get('is_latest', False)]
            if latest_vk:
                vk = latest_vk[0]
                result.is_violence_k = True
                result.violence_k_type = vk['type']
                result.violence_k_body = vk['body_pct']

    # ========== 两个30%原则 ==========
    if len(klines) >= 10:
        rule30 = check_two_30_rule(klines)
        result.b1_rally_pct = rule30['b1_rally_pct']
        result.b1_pass_30 = rule30['b1_pass_30']

    # ========== 娜娜图 ==========
    if len(klines) >= 20:
        nana = detect_nana_chart(klines)
        result.is_nana = nana['is_nana']

    # ========== 黄金碗 ==========
    if len(klines) >= 120:
        bowl = detect_golden_bowl(klines)
        result.is_in_bowl = bowl['is_in_bowl']
        result.bowl_upper = bowl['bowl_upper']
        result.bowl_lower = bowl['bowl_lower']

    # ========== 呼吸结构 ==========
    if len(klines) >= 10:
        breath = detect_breathing_structure(klines)
        result.breath_phase = breath['breath_phase']
        result.breath_n_type = breath['breath_n_type']

    # ========== SB1假摔 ==========
    if len(klines) >= 6:
        sb1 = detect_sb1(klines)
        result.is_sb1 = sb1['is_sb1']

    # ========== 超级B1 ==========
    if len(klines) >= 15:
        sb1_detail = detect_sb1_detailed(klines)
        result.is_sb1_detailed = sb1_detail['is_sb1_detailed']

    # ========== 双枪战法 ==========
    if len(klines) >= 15:
        dg = detect_double_gun(klines)
        result.is_double_gun = dg['is_double_gun']
        result.double_gun_vol1 = dg['double_gun_vol1']
        result.double_gun_vol2 = dg['double_gun_vol2']
        result.double_gun_gap_days = dg['double_gun_gap_days']

    # ========== 异动选股法 ==========
    if len(klines) >= 65:
        yidong = detect_volume_anomaly(klines)
        result.is_yidong = yidong['is_yidong']
        result.yidong_type = yidong['yidong_type']
        result.yidong_vol_ratio = yidong['yidong_vol_ratio']
        result.yidong_above_60d = yidong['yidong_above_60d']

    # ========== B3买点 ==========
    if len(klines) >= 15:
        b3 = detect_b3(klines)
        result.is_b3 = b3['is_b3']

    # ========== 四块砖交易体系 ==========
    if len(klines) >= 10:
        brick_sys = detect_four_brick_system(klines)
        result.brick_consecutive = brick_sys['brick_consecutive']
        result.brick_action = brick_sys['brick_action']
        result.brick_action_desc = brick_sys['brick_action_desc']
        result.is_brick_flip_green = brick_sys['is_brick_flip_green']

    # 卖出评分
    sell_score, sell_desc, sell_items = calculate_sell_score(klines)
    result.sell_score = sell_score
    result.sell_items = sell_items

    # 交易信号
    result.signal = detect_trade_signal(klines)

    return result
def visualize_brick_chart(klines: List[DailyData], lookback: int = 20) -> str:
    """
    生成砖型图可视化（文本版）

    用汉字+个数显示砖型图，红*N/绿*N，不表示强弱
    """
    if len(klines) < 10:
        return "数据不足"

    # 计算全量历史砖值序列
    brick_history = []
    dates = []
    closes = []
    pcts = []

    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)
        brick_history.append(brick_val)
        day = klines[i - 1]
        dates.append(day.trade_date)
        closes.append(day.close)
        pcts.append(day.pct_chg)

    if len(brick_history) < 3:
        return "数据不足"

    # 只取最近 lookback 天
    brick_history = brick_history[-lookback:]
    dates = dates[-lookback:]
    closes = closes[-lookback:]
    pcts = pcts[-lookback:]

    # 计算红绿砖：当日砖值 >= 昨日砖值 = 红砖
    colors = []  # 1=红, -1=绿
    for i in range(1, len(brick_history)):
        if brick_history[i] >= brick_history[i - 1]:
            colors.append(1)
        else:
            colors.append(-1)

    if not colors:
        return "无砖型数据"

    lines = []
    lines.append(f"  {'日期':<10} {'收盘':>7} {'涨跌%':>7} {'砖值':>6}  砖型图")
    lines.append("  " + "-" * 45)

    # 计算连续同色砖
    i = 0
    while i < len(colors):
        idx = i + 1
        color = colors[i]
        count = 1
        while i + count < len(colors) and colors[i + count] == color:
            count += 1

        brick = brick_history[idx]
        if color == 1:
            bar = f"红 * {count}"
        else:
            bar = f"绿 * {count}"

        pct_str = f"{pcts[idx]:+6.2f}%"
        line = f"  {dates[idx]}  {closes[idx]:7.2f}  {pct_str}  {brick:6.1f}  {bar}"
        lines.append(line)

        i += count

    lines.append("  " + "-" * 45)
    trend_text = "红砖(上涨动量)" if colors[-1] == 1 else "绿砖(下跌动量)"
    lines.append(f"  趋势: {trend_text}")
    lines.append(f"  砖值范围: {min(brick_history):.1f} ~ {max(brick_history):.1f}")

    return "\n".join(lines)
def format_result(result: IndicatorResult) -> str:
    """格式化输出结果"""
    lines = [
        f"{'='*60}",
        f"股票: {result.ts_code}  日期: {result.trade_date}",
        f"{'='*60}",
        f"[KDJ]  K={result.k:.2f}  D={result.d:.2f}  J={result.j:.2f}",
        f"",
        f"[MACD] DIF={result.dif:.4f}  DEA={result.dea:.4f}  柱={result.macd_hist:.4f}",
    ]

    # MACD 语料判断
    macd_lines = []
    zone = "多头区间(DIF>0)" if result.is_dif_positive else "空头区间(DIF<0)"
    macd_lines.append(f"  0轴位置: {zone}")

    if result.is_dif_cross_zero:
        macd_lines.append("  * DIF 上穿0轴（红点标记）")
    if result.is_dif_cross_zero_down:
        macd_lines.append("  * DIF 下穿0轴（绿点标记）")

    if result.macd_gold_cross:
        macd_lines.append("  金叉: DIF 上穿 DEA")
    if result.macd_dead_cross:
        macd_lines.append("  死叉: DIF 下穿 DEA")

    if result.is_gold_fake:
        macd_lines.append("  !!! 金叉空（诱多陷阱，快跑）")
    if result.is_dead_fake:
        macd_lines.append("  !!! 死叉多（空中加油，强多）")

    if result.is_top_divergence:
        macd_lines.append("  !!! 顶背离，见顶减仓")
    if result.is_bottom_divergence:
        macd_lines.append("  !!! 底背离，反转建仓")

    if result.macd_veto:
        macd_lines.append("  XXX MACD一票否决：不能买！")
    else:
        macd_lines.append("  MACD未否决")

    lines.append("\n".join(macd_lines))
    lines.append("")
    lines.append(f"[BBI]  {result.bbi:.2f}")
    lines.append(f"[均线] MA5={result.ma5:.2f}  MA10={result.ma10:.2f}  MA20={result.ma20:.2f}  MA60={result.ma60:.2f}")
    if result.high_52w > 0:
        lines.append(f"[52周最高] {result.high_52w:.2f}  (距现价 +{result.high_52w_dist:.1f}%)")
    lines.append(f"[RSI]  RSI6={result.rsi6:.2f}  RSI12={result.rsi12:.2f}  RSI24={result.rsi24:.2f}")
    lines.append(f"[WR]   WR5={result.wr5:.2f}  WR10={result.wr10:.2f}")
    lines.append(f"[布林带] 中={result.boll_mid:.2f}  上={result.boll_upper:.2f}  下={result.boll_lower:.2f}  宽={result.boll_width:.2f}%  位置={result.boll_position:.1f}%")
    lines.append(f"[量比] {result.vol_ratio:.2f}x")
    lines.append("")
    lines.append(f"[双线战法] 白线={result.zg_white:.2f}  大哥线={result.dg_yellow:.2f}  Gold:{result.is_gold_cross}  Dead:{result.is_dead_cross}")
    lines.append(f"[单针下20] RSL_S={result.rsl_short:.2f}  RSL_L={result.rsl_long:.2f}  Signal:{result.is_needle_20}")
    if result.is_needle_30:
        lines.append(f"[单针下30] *** 信号触发 (红>85, 白<30)")
    lines.append("")

    # B1/B2 战法检测
    if result.b1_score > 0 or result.b2_score > 0:
        lines.append("[B1建仓波]")
        if result.is_b1:
            lines.append(f"  *** B1信号触发! J={result.b1_j_value}  振幅={result.b1_amplitude:.1f}%  涨幅={result.b1_pct_chg:.1f}%  缩量:{result.b1_volume_shrink}  评分:{result.b1_score}/4")
        else:
            lines.append(f"  J={result.b1_j_value}  振幅={result.b1_amplitude:.1f}%  涨幅={result.b1_pct_chg:.1f}%  评分:{result.b1_score}/4 (未触发)")
        lines.append("")

        lines.append("[B2突破]")
        if result.is_b2:
            lines.append(f"  *** B2信号触发! 涨幅={result.b2_pct_chg:.1f}%  J={result.b2_j_value}  放量:{result.b2_volume_up}  评分:{result.b2_score}/4")
        else:
            lines.append(f"  涨幅={result.b2_pct_chg:.1f}%  J={result.b2_j_value}  跟随B1:{result.b2_follows_b1}  评分:{result.b2_score}/4 (未触发)")
        lines.append("")

    # 砖型图可视化
    try:
        klines = get_kline_data(result.ts_code, days=120)
        if len(klines) >= 10:
            brick_vis = visualize_brick_chart(klines, lookback=15)
            lines.append("[砖型图可视化]")
            lines.append(brick_vis)
            lines.append("")
    except Exception:
        pass

    lines.append(f"[砖型图] Brick={result.brick_value:.2f}  TrendUp:{result.brick_trend_up}  Fanbao:{result.is_fanbao}")
    lines.append("")
    lines.append("[量价形态]")
    lines.append(f"  倍量: {'OK' if result.is_beidou else '--'}  缩量: {'OK' if result.is_suoliang else '--'}")
    lines.append(f"  假阴真阳: {'OK' if result.is_jiayin_zhenyang else '--'}  放量阴线: {'OK' if result.is_fangliang_yinxian else '--'}")
    lines.append("")

    # 关键K / 暴力K（显示60日内找到的关键K）
    if result.key_k_list:
        lines.append(f"[关键K] 60日内找到 {len(result.key_k_list)} 根关键K:")
        for kk in result.key_k_list[-5:]:  # 最多显示最近5根
            marker = " <<< 今日" if kk.get('is_latest', False) else ""
            lines.append(f"  {kk['date']}  {kk['type']}  收{kk['close']:.2f}({kk['pct']:+.1f}%)  实体{kk['body_pct']:.1f}%  量比{kk['vol_ratio']:.1f}x{marker}")
        lines.append("")
    if result.is_violence_k:
        lines.append(f"[暴力K] *** {result.violence_k_type}  实体={result.violence_k_body:.1f}%")
        lines.append("")

    # 两个30%原则
    if result.b1_rally_pct != 0 or result.b1_pass_30:
        lines.append(f"[两个30%原则] B1涨幅={result.b1_rally_pct:.1f}%  通过:{result.b1_pass_30}")
        lines.append("")

    # 娜娜图/黄金碗/呼吸结构/SB1/B3
    if result.is_nana:
        lines.append(f"[娜娜图] *** 完美建仓信号")
        lines.append("")
    if result.is_in_bowl:
        lines.append(f"[黄金碗] *** 价格在碗内  上沿={result.bowl_upper:.2f}  下沿={result.bowl_lower:.2f}")
        lines.append("")
    if result.breath_phase and result.breath_phase != 'none':
        n_type = " N型结构" if result.breath_n_type else ""
        phase_label = "呼气" if result.breath_phase == 'exhale' else "吸气"
        lines.append(f"[呼吸结构] {phase_label}{n_type}")
        lines.append("")
    if result.is_sb1:
        lines.append(f"[SB1假摔] *** 假摔信号触发")
        lines.append("")
    if result.is_sb1_detailed:
        lines.append(f"[超级B1] *** 超级B1信号触发")
        lines.append("")
    if result.is_double_gun:
        lines.append(f"[双枪战法] *** 第一枪量比{result.double_gun_vol1:.1f}x 第二枪{result.double_gun_vol2:.1f}x 间隔{result.double_gun_gap_days}天")
        lines.append("")
    if result.is_yidong:
        lines.append(f"[异动选股] *** {result.yidong_type} 量比{result.yidong_vol_ratio:.1f}x 60日线={'上方' if result.yidong_above_60d else '下方'}")
        lines.append("")
    if result.is_b3:
        lines.append(f"[B3买点] *** B3信号触发")
        lines.append("")

    # 四块砖交易体系
    if result.brick_action:
        flip_marker = " *** 红翻绿止损" if result.is_brick_flip_green else ""
        lines.append(f"[四块砖体系] 连续{result.brick_consecutive}砖 | 操作: {result.brick_action}{flip_marker}")
        lines.append(f"  {result.brick_action_desc}")
        lines.append("")

    lines.append(f"[防卖飞评分] {result.sell_score}/5")
    if result.sell_items:
        for item_name, passed in result.sell_items.items():
            lines.append(f"  {item_name}: {'[Y]' if passed else '[N]'}")
    else:
        lines.append(f"  (数据不足)")
    lines.append("")
    lines.append(f"[交易信号] {result.signal.value}")
    lines.append(f"{'='*60}")
    return "\n".join(lines)
def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Z哥 技术指标分析")
    parser.add_argument("ts_code", help="股票代码，如 000001.SZ")
    parser.add_argument("--days", type=int, default=100, help="分析天数")

    args = parser.parse_args()

    result = analyze_stock(args.ts_code, args.days)
    print(format_result(result))


if __name__ == "__main__":
    main()

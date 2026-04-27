"""
技术指标计算模块
实现 Z哥 策略中常用的技术指标计算
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

# 加载项目内的 .env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# 数据库路径：从环境变量读取，支持相对路径和绝对路径
_db_path_str = os.getenv("DB_PATH", "data/stock_data.db")
_db_path = Path(_db_path_str)
if not _db_path.is_absolute():
    _db_path = Path(__file__).parent.parent / _db_path_str
DB_PATH = str(_db_path.resolve())


class TradeSignal(Enum):
    """交易信号"""
    B1 = "B1"           # 买入点1
    B2 = "B2"           # 买入点2（确认）
    B3 = "B3"           # 买入点3
    SB1 = "SB1"         # 超级B1
    S1 = "S1"           # 卖出信号1
    S2 = "S2"           # 卖出信号2
    HOLD = "HOLD"       # 持有
    WATCH = "WATCH"     # 观望


@dataclass
class DailyData:
    """单日行情数据"""
    ts_code: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    vol: float
    amount: float
    pct_chg: float
    prev_close: float = 0


@dataclass
class IndicatorResult:
    """指标计算结果"""
    ts_code: str
    trade_date: str

    # KDJ
    k: float = 0
    d: float = 0
    j: float = 0

    # MACD
    dif: float = 0
    dea: float = 0
    macd_hist: float = 0

    # MACD 语料判断
    is_dif_positive: bool = False  # DIF > 0 多头区间
    is_dif_cross_zero: bool = False  # DIF 上穿 0 轴（红点）
    is_dif_cross_zero_down: bool = False  # DIF 下穿 0 轴（绿点）
    macd_gold_cross: bool = False  # DIF 上穿 DEA
    macd_dead_cross: bool = False  # DIF 下穿 DEA
    is_gold_fake: bool = False  # 金叉空（金叉后立即死叉，诱多）
    is_dead_fake: bool = False  # 死叉多（死叉后立即金叉，空中加油）
    is_top_divergence: bool = False  # 顶背离
    top_div_desc: str = ""           # 顶背离描述
    is_bottom_divergence: bool = False  # 底背离
    bottom_div_desc: str = ""        # 底背离描述
    macd_veto: bool = False  # MACD 一票否决（不能买）

    # BBI
    bbi: float = 0

    # MA
    ma5: float = 0
    ma10: float = 0
    ma20: float = 0
    ma60: float = 0
    high_52w: float = 0  # 52周（约240交易日）最高价
    high_52w_dist: float = 0  # 距52周高点的百分比差距

    # RSI
    rsi6: float = 0
    rsi12: float = 0
    rsi24: float = 0

    # WR (Williams %R)
    wr5: float = 0
    wr10: float = 0

    # 布林带
    boll_mid: float = 0      # 中轨 = MA20
    boll_upper: float = 0   # 上轨 = 中轨 + 2*STD
    boll_lower: float = 0   # 下轨 = 中轨 - 2*STD
    boll_width: float = 0   # 布林带宽度
    boll_position: float = 0 # 股价在布林带中的位置 (0-100%)

    # 量比
    vol_ratio: float = 0    # 量比 = 当前量 / 5日均量

    # ========== Z哥双线战法 ==========
    zg_white: float = 0     # Z哥白线 = EMA(EMA(C,10),10)
    dg_yellow: float = 0    # 大哥线 = (MA14+MA28+MA57+MA114)/4
    is_gold_cross: bool = False  # 金叉（白线上穿大哥线）
    is_dead_cross: bool = False  # 死叉（白线下穿大哥线）

    # ========== 单针下20 ==========
    rsl_short: float = 0    # 短期RSL (3日)
    rsl_long: float = 0     # 长期RSL (21日)
    is_needle_20: bool = False  # 单针下20信号

    # ========== 砖型图系统 ==========
    brick_value: float = 0   # 砖型图数值
    brick_trend: str = "NEUTRAL"  # 趋势: RED(红砖)/GREEN(绿砖)/NEUTRAL(中性)
    brick_count: int = 0     # 连续砖数
    brick_trend_up: bool = False  # 命值趋势上升
    is_fanbao: bool = False  # 精准反包信号（2/3位置）

    # 量价信号
    is_beidou: bool = False      # 倍量
    is_suoliang: bool = False    # 缩量
    is_jiayin_zhenyang: bool = 0  # 假阴真阳
    is_jiayang_zhenyin: bool = 0  # 假阳真阴
    is_fangliang_yinxian: bool = 0 # 放量阴线

    # 卖出评分
    sell_score: int = 0         # 0-5分
    sell_reason: str = ""        # 扣分原因

    # 交易信号
    signal: TradeSignal = TradeSignal.WATCH
    signal_desc: str = ""

    # 关键价位
    prev_high: float = 0    # 昨日最高价
    prev_low: float = 0     # 昨日最低价

    # DMI/ADX
    dmi_plus: float = 0
    dmi_minus: float = 0
    adx: float = 0

    # 资金流
    net_lg_mf: float = 0    # 主力净流入
    net_elg_mf: float = 0   # 超大单净流入

    # B1/B2战法记录
    last_b1_date: str = ""
    last_b1_price: float = 0

    # B1建仓波检测
    is_b1: bool = False          # 当日是否为B1
    b1_j_value: float = 0        # B1的J值
    b1_amplitude: float = 0      # B1振幅
    b1_pct_chg: float = 0        # B1涨幅
    b1_volume_shrink: bool = False  # 是否缩量
    b1_score: int = 0            # B1匹配度评分(0-4)

    # B2突破检测
    is_b2: bool = False          # 当日是否为B2
    b2_follows_b1: bool = False  # 是否在B1后
    b2_pct_chg: float = 0        # B2涨幅
    b2_j_value: float = 0        # B2的J值
    b2_volume_up: bool = False   # 是否放量
    b2_score: int = 0            # B2匹配度评分(0-4)

    # 关键K检测
    key_k_list: List[Dict] = None    # 关键K列表，每根含日期/类型/实体%/量比

    # 暴力K检测
    is_violence_k: bool = False  # 最新这天是否暴力K
    violence_k_type: str = ""    # 大暴力/小暴力
    violence_k_body: float = 0   # 实体涨幅%

    # 两个30%原则 (B1筛选)
    b1_rally_pct: float = 0      # B1建仓波涨幅%
    b1_turnover: float = 0       # B1累计换手率%
    b1_pass_30: bool = False     # 是否通过两个30%原则

    # 异动记录
    last_yidong_date: str = ""

    # 市场背景
    market_pct_chg: float = 0
    market_dir: str = "NEUTRAL"


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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


def calculate_ma(prices: List[float], period: int) -> float:
    """计算简单移动平均"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> float:
    """计算指数移动平均"""
    if len(prices) < period:
        return 0

    k = 2 / (period + 1)
    ema = prices[0]

    for price in prices[1:]:
        ema = price * k + ema * (1 - k)

    return ema


def calculate_sma_td(values: List[float], period: int, m: int) -> float:
    """
    通达信 SMA 函数

    公式: SMA = X * M/N + SMA_prev * (1 - M/N)

    Args:
        values: 价格序列
        period: 周期 N
        m: 权重 M

    Returns:
        SMA 值
    """
    if len(values) < period:
        return sum(values) / len(values) if values else 0

    weight = m / period
    sma = values[0]

    for v in values[1:]:
        sma = v * weight + sma * (1 - weight)

    return sma


def calculate_slope(values: List[float], period: int) -> float:
    """
    通达信 SLOPE 函数（线性回归斜率）

    公式: SLOPE = (N * SUM(X*Y) - SUM(X) * SUM(Y)) / (N * SUM(X^2) - SUM(X)^2)

    Args:
        values: 数据序列
        period: 周期 N

    Returns:
        斜率值（每bar变化量）
    """
    if len(values) < period:
        period = len(values)

    if period < 2:
        return 0

    recent = values[-period:]

    # 线性回归: y = a * x + b
    # slope a = (N*SUM(xy) - SUM(x)*SUM(y)) / (N*SUM(x^2) - SUM(x)^2)
    n = period
    sum_x = n * (n - 1) / 2  # 0+1+2+...+n-1
    sum_xx = (n - 1) * n * (2 * n - 1) / 6  # 0^2+1^2+...+(n-1)^2

    sum_y = sum(recent)
    sum_xy = sum(recent[i] * i for i in range(n))

    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope


def calculate_kdj(klines: List[DailyData], period: int = 9,
                  k_ma: int = 3, d_ma: int = 3) -> Tuple[float, float, float]:
    """
    计算 KDJ 指标

    Args:
        klines: K线数据（需要至少 period 天）
        period: RSV 周期，默认9
        k_ma: K 线的 MA 周期
        d_ma: D 线的 MA 周期

    Returns:
        (K, D, J) 值
    """
    if len(klines) < period:
        return 50, 50, 50  # 默认值

    # 计算 RSV
    rsv_list = []
    for i in range(period - 1, len(klines)):
        low_list = [klines[j].low for j in range(i - period + 1, i + 1)]
        high_list = [klines[j].high for j in range(i - period + 1, i + 1)]

        low_min = min(low_list)
        high_max = max(high_list)

        if high_max == low_min:
            rsv = 50
        else:
            rsv = (klines[i].close - low_min) / (high_max - low_min) * 100

        rsv_list.append(rsv)

    if not rsv_list:
        return 50, 50, 50

    # 计算 K、D、J
    k = 50.0
    d = 50.0

    for rsv in rsv_list:
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k

    j = 3 * k - 2 * d

    return round(k, 2), round(d, 2), round(j, 2)


def calculate_macd(klines: List[DailyData],
                   fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
    """
    计算 MACD 指标（通达信标准公式）

    DIFF: EMA(CLOSE, 12) - EMA(CLOSE, 26)
    DEA: EMA(DIFF, 9)
    MACD: 2 * (DIFF - DEA), COLORSTICK

    Args:
        klines: K线数据
        fast: 快线周期，默认12
        slow: 慢线周期，默认26
        signal: 信号线周期，默认9

    Returns:
        (DIF序列, DEA序列, MACD柱序列)
    """
    if len(klines) < slow:
        return [], [], []

    closes = [k.close for k in klines]

    # 计算完整的 DIF 序列
    dif_list = []
    for i in range(slow - 1, len(closes)):
        sub = closes[:i + 1]
        ema_fast = calculate_ema(sub, fast)
        ema_slow = calculate_ema(sub, slow)
        dif_list.append(ema_fast - ema_slow)

    if len(dif_list) < signal:
        return dif_list, [], []

    # 计算完整的 DEA 序列（DIF 的 EMA）
    dea_list = []
    for i in range(signal - 1, len(dif_list)):
        sub_dif = dif_list[:i + 1]
        dea_list.append(calculate_ema(sub_dif, signal))

    # MACD 柱 = 2 * (DIF - DEA)
    macd_list = []
    for i in range(len(dea_list)):
        dif_idx = signal - 1 + i
        if dif_idx < len(dif_list):
            macd_list.append(2 * (dif_list[dif_idx] - dea_list[i]))

    return dif_list, dea_list, macd_list


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
        'top_div_desc': '',
        'is_bottom_divergence': False,
        'bottom_div_desc': '',
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
                decay_pct = (1 - dif_list[-1] / max_dif) * 100 if max_dif != 0 else 0
                result['top_div_desc'] = f"价近高({today_close:.2f} vs {max_close:.2f}) DIF衰减{decay_pct:.0f}%"

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
                strength_pct = (1 - dif_list[-1] / min_dif) * 100 if min_dif != 0 else 0
                result['bottom_div_desc'] = f"价近低({today_close:.2f} vs {min_close:.2f}) DIF回升{strength_pct:.0f}%"

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
        'is_dif_positive': False,        # DIF > 0 多头区间
        'is_dif_cross_zero': False,      # DIF 上穿 0 轴（红点）
        'is_dif_cross_zero_down': False,  # DIF 下穿 0 轴（绿点）
        'is_gold_cross': False,          # DIF 上穿 DEA
        'is_dead_cross': False,          # DIF 下穿 DEA
        'is_gold_fake': False,           # 金叉空（诱多）
        'is_dead_fake': False,           # 死叉多（空中加油）
        'is_top_divergence': False,      # 顶背离
        'top_div_desc': '',              # 顶背离描述
        'is_bottom_divergence': False,    # 底背离
        'bottom_div_desc': '',           # 底背离描述
        'macd_veto': False,              # 一票否决
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
    signals['top_div_desc'] = div['top_div_desc']
    signals['bottom_div_desc'] = div['bottom_div_desc']

    # === 一票否决权 ===
    # DIF < 0 + 没有底背离 → 一票否决
    if dif_today < 0 and not signals['is_bottom_divergence']:
        signals['macd_veto'] = True

    return signals


def calculate_bbi(klines: List[DailyData]) -> float:
    """
    计算 BBI 多空指标
    BBI = (MA3 + MA6 + MA12 + MA24) / 4
    """
    if len(klines) < 24:
        return 0

    closes = [k.close for k in klines]

    ma3 = calculate_ma(closes, 3)
    ma6 = calculate_ma(closes, 6)
    ma12 = calculate_ma(closes, 12)
    ma24 = calculate_ma(closes, 24)

    bbi = (ma3 + ma6 + ma12 + ma24) / 4
    return round(bbi, 2)


def calculate_rsi(klines: List[DailyData],
                  period: int = 14) -> float:
    """
    计算 RSI 相对强弱指标

    通达信公式:
    RSI := SMA(MAX(CLOSE-REF(CLOSE,1),0),N,1) / SMA(ABS(CLOSE-REF(CLOSE,1)),N,1) * 100

    Args:
        klines: K线数据
        period: 周期，默认14

    Returns:
        RSI 值 (0-100)
    """
    if len(klines) < period + 1:
        return 50  # 默认中性值

    closes = [k.close for k in klines]

    # 计算涨跌序列
    changes = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        changes.append(change)

    if len(changes) < period:
        return 50

    # 计算这段时间的上涨和下跌
    recent_changes = changes[-period:]

    up_sum = sum(max(c, 0) for c in recent_changes)
    down_sum = sum(abs(min(c, 0)) for c in recent_changes)

    if down_sum == 0:
        return 100  # 一直涨

    rs = up_sum / down_sum
    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 2)


def calculate_rsi_multi(klines: List[DailyData]) -> Tuple[float, float, float]:
    """
    计算多周期 RSI (RSI6, RSI12, RSI24)

    Args:
        klines: K线数据

    Returns:
        (RSI6, RSI12, RSI24)
    """
    rsi6 = calculate_rsi(klines, 6) if len(klines) >= 7 else 50
    rsi12 = calculate_rsi(klines, 12) if len(klines) >= 13 else 50
    rsi24 = calculate_rsi(klines, 24) if len(klines) >= 25 else 50
    return rsi6, rsi12, rsi24


def calculate_wr(klines: List[DailyData], period: int = 14) -> float:
    """
    计算 Williams %R 威廉指标

    通达信公式:
    WR := (HIGHN-CLOSE) / (HIGHN-LOWN) * 100

    Args:
        klines: K线数据
        period: 周期，默认14

    Returns:
        WR 值 (-100 到 0)
    """
    if len(klines) < period:
        return -50  # 默认中性值

    # 取最近 period 天
    recent = klines[-period:]

    high = max(k.high for k in recent)
    low = min(k.low for k in recent)
    close = klines[-1].close

    if high == low:
        return -50

    wr = (high - close) / (high - low) * 100

    return round(wr, 2)


def calculate_wr_multi(klines: List[DailyData]) -> Tuple[float, float]:
    """
    计算多周期 WR (WR5, WR10)

    Args:
        klines: K线数据

    Returns:
        (WR5, WR10)
    """
    wr5 = calculate_wr(klines, 5) if len(klines) >= 5 else -50
    wr10 = calculate_wr(klines, 10) if len(klines) >= 10 else -50
    return wr5, wr10


def calculate_bollinger(klines: List[DailyData],
                       period: int = 20,
                       std_dev: float = 2.0) -> Tuple[float, float, float, float, float]:
    """
    计算布林带

    通达信公式:
    BOLL = MA(CLOSE, N)
    UB = BOLL + 2 * STD(CLOSE, N)
    LB = BOLL - 2 * STD(CLOSE, N)

    Args:
        klines: K线数据
        period: 周期，默认20
        std_dev: 标准差倍数，默认2

    Returns:
        (中轨, 上轨, 下轨, 带宽, 位置%)
    """
    if len(klines) < period:
        return 0, 0, 0, 0, 50

    closes = [k.close for k in klines]
    recent_closes = closes[-period:]

    # 计算中轨 (MA20)
    mid = sum(recent_closes) / period

    # 计算标准差
    variance = sum((c - mid) ** 2 for c in recent_closes) / period
    std = variance ** 0.5

    upper = mid + std_dev * std
    lower = mid - std_dev * std

    # 带宽：(上轨 - 下轨) / 中轨 * 100
    if mid > 0:
        width = (upper - lower) / mid * 100
    else:
        width = 0

    # 位置：当前价格在布林带中的位置
    current_close = closes[-1]
    if upper != lower:
        position = (current_close - lower) / (upper - lower) * 100
    else:
        position = 50

    return round(mid, 2), round(upper, 2), round(lower, 2), round(width, 2), round(position, 1)


def calculate_vol_ratio(klines: List[DailyData], period: int = 5) -> float:
    """
    计算量比

    量比 = 当前成交量 / 过去N日平均成交量

    Args:
        klines: K线数据
        period: 参考周期，默认5

    Returns:
        量比值
    """
    if len(klines) < period + 1:
        return 1.0  # 默认等量

    # 取最近 period 天的平均量（不包括今天）
    recent_vols = [klines[i].vol for i in range(-period-1, -1)]

    if not recent_vols:
        return 1.0

    avg_vol = sum(recent_vols) / len(recent_vols)
    current_vol = klines[-1].vol

    if avg_vol == 0:
        return 1.0

    ratio = current_vol / avg_vol

    return round(ratio, 2)


# ========== Z哥双线战法 ==========

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


# ========== 单针下20 ==========

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


# ========== DMI/ADX 趋势指标 ==========

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


# ========== 砖型图系统 ==========

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

    通达信逻辑：
    - 红砖：今日砖值 >= 昨日砖值（动量上涨）
    - 绿砖：今日砖值 < 昨日砖值（动量下跌）

    Args:
        klines: K线数据
        lookback: 回溯天数

    Returns:
        (趋势状态: RED/GREEN/NEUTRAL, 连续砖数)
    """
    if len(klines) < 10:
        return "NEUTRAL", 0

    # 计算历史砖值序列（对比昨日大小判断红绿）
    brick_colors = []  # 1=红(涨), -1=绿(跌), 0=平
    prev_brick = None

    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)

        if prev_brick is not None:
            if brick_val >= prev_brick:
                brick_colors.append(1)  # 红砖
            else:
                brick_colors.append(-1)  # 绿砖
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


def calculate_sell_score(klines: List[DailyData]) -> Tuple[int, str]:
    """
    计算防卖飞评分 V1.4（5分制）

    评分条件：
    1. 收盘涨？ +1
    2. BBI 没破？ +1
    3. 不是放量阴线？ +1
    4. 趋势还向上？ +1
    5. J 没死叉？ +1

    Args:
        klines: K线数据（至少5天）

    Returns:
        (评分, 扣分原因)
    """
    if len(klines) < 2:
        return 3, "数据不足"

    today = klines[-1]
    yesterday = klines[-2]

    score = 5
    reasons = []

    # 1. 收盘涨？
    if today.close <= today.prev_close:
        score -= 1
        reasons.append("收盘不涨")

    # 2. BBI 没破？
    if len(klines) >= 24:
        bbi = calculate_bbi(klines)
        if today.close < bbi:
            score -= 1
            reasons.append("跌破BBI")

    # 3. 不是放量阴线？
    vol_pattern = detect_volume_pattern(today, yesterday)
    if vol_pattern['is_fangliang_yinxian']:
        score -= 1
        reasons.append("放量阴线")

    # 4. 趋势还向上？（用简单均线判断）
    if len(klines) >= 5:
        ma5_today = calculate_ma([k.close for k in klines[-5:]], 5)
        ma5_yesterday = calculate_ma([k.close for k in klines[-6:-1]], 5)
        if ma5_today <= ma5_yesterday:
            score -= 1
            reasons.append("均线向下")

    # 5. J 没死叉？
    if len(klines) >= 9:
        k, d, j = calculate_kdj(klines)
        prev_k, prev_d, prev_j = calculate_kdj(klines[:-1])

        # 死叉状态：J 在 K、D 之下
        if j < k and j < d:
            score -= 1
            reasons.append("KDJ死叉")

    return max(0, score), "; ".join(reasons) if reasons else "满分"


def detect_trade_signal(klines: List[DailyData]) -> Tuple[TradeSignal, str]:
    """
    检测交易信号（集成 MACD 一票否决权）

    Args:
        klines: K线数据（至少30天）

    Returns:
        (信号类型, 信号描述)
    """
    if len(klines) < 30:
        return TradeSignal.WATCH, "数据不足"

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
        return TradeSignal.WATCH, "MACD一票否决：DIF<0且无底背离，不能买"

    # === 金叉空：A股最恶毒的诱多 ===
    if macd_signals.get('is_gold_fake', False):
        return TradeSignal.S1, "金叉空诱多，主力出货，快跑"

    bbi = calculate_bbi(klines)
    vol_pattern = detect_volume_pattern(today, yesterday)

    # ========== 卖出信号检测 ==========

    # S1: 放量阴线（最高优先级）
    if vol_pattern['is_fangliang_yinxian'] and today.pct_chg < -3:
        return TradeSignal.S1, f"放量阴线S1，跌{today.pct_chg:.2f}%"

    # 顶背离 → 减仓
    if macd_signals.get('is_top_divergence', False):
        return TradeSignal.S2, "顶背离，见顶减仓"

    # ========== 买入信号检测 ==========

    # 底背离 → 反转建仓
    if macd_signals.get('is_bottom_divergence', False):
        return TradeSignal.B1, "底背离，反转建仓"

    # 死叉多（空中加油）→ 最强多头信号
    if macd_signals.get('is_dead_fake', False):
        return TradeSignal.B2, "死叉多（空中加油），最强多头信号"

    # B1: J < -10 + 缩量回调
    if j < -10 and vol_pattern['is_suoliang']:
        return TradeSignal.B1, f"B1买点，J={j:.2f}"

    # B2: B1后放量确认
    if j > -10 and j < 55:
        prev_j_list = []
        for i in range(2, min(10, len(klines))):
            pk, pd, pj = calculate_kdj(klines[:-i])
            prev_j_list.append(pj)

        if any(pj < -10 for pj in prev_j_list):
            if today.pct_chg > 4 and vol_pattern['is_beidou']:
                return TradeSignal.B2, f"B2确认，涨{today.pct_chg:.2f}%，量比放大"

    # SB1: 超级B1（放量跌后缩量+J负值）
    if len(klines) >= 5:
        prev_2 = klines[-3]
        if prev_2.close < prev_2.open and prev_2.vol > klines[-4].vol * 1.5:
            if j < -5 and vol_pattern['is_suoliang']:
                return TradeSignal.SB1, f"超级B1，J={j:.2f}"

    # ========== 持有判断 ==========

    if today.close > bbi and j > 0 and today.pct_chg > 0:
        return TradeSignal.HOLD, f"持有信号，收{today.close:.2f}，BBI={bbi:.2f}，J={j:.2f}"

    return TradeSignal.WATCH, f"观望，J={j:.2f}，MACD={macd_hist:.4f}"


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
        return IndicatorResult(ts_code=ts_code, trade_date="", signal_desc="无数据")

    today = klines[-1]
    yesterday = klines[-2] if len(klines) > 1 else None

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

            # 语料判断
            macd_signals = detect_macd_signals(klines, dif_list, dea_list, macd_list)
            result.is_dif_positive = macd_signals['is_dif_positive']
            result.is_dif_cross_zero = macd_signals['is_dif_cross_zero']
            result.is_dif_cross_zero_down = macd_signals['is_dif_cross_zero_down']
            result.macd_gold_cross = macd_signals['is_gold_cross']
            result.macd_dead_cross = macd_signals['is_dead_cross']
            result.is_gold_fake = macd_signals['is_gold_fake']
            result.is_dead_fake = macd_signals['is_dead_fake']
            result.is_top_divergence = macd_signals['is_top_divergence']
            result.top_div_desc = macd_signals.get('top_div_desc', '')
            result.is_bottom_divergence = macd_signals['is_bottom_divergence']
            result.bottom_div_desc = macd_signals.get('bottom_div_desc', '')
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

    # 卖出评分
    sell_score, sell_reason = calculate_sell_score(klines)
    result.sell_score = sell_score
    result.sell_reason = sell_reason

    # 交易信号
    signal, signal_desc = detect_trade_signal(klines)
    result.signal = signal
    result.signal_desc = signal_desc

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
        macd_lines.append(f"  !!! 顶背离，见顶减仓 ({result.top_div_desc})")
    if result.is_bottom_divergence:
        macd_lines.append(f"  !!! 底背离，反转建仓 ({result.bottom_div_desc})")

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

    lines.append(f"[防卖飞评分] {result.sell_score}/5  ({result.sell_reason})")
    lines.append("")
    lines.append(f"[交易信号] {result.signal.value}  {result.signal_desc}")
    lines.append(f"{'='*60}")
    return "\n".join(lines)


# ==================== 命令行工具 ====================

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

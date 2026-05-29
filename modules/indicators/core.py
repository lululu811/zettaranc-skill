"""
技术指标计算模块 — 核心基础类型与数学工具
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
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

# 数据库路径：从环境变量读取，支持相对路径和绝对路径
_db_path_str = os.getenv("DB_PATH", "data/stock_data.db")
_db_path = Path(_db_path_str)
if not _db_path.is_absolute():
    _db_path = Path(__file__).parent.parent.parent / _db_path_str
DB_PATH = str(_db_path.resolve())

# 数据模式
DATA_MODE = os.getenv("DATA_MODE", "websearch")


def get_data_mode() -> str:
    """获取当前数据模式：jnb 或 websearch"""
    return DATA_MODE

_env_path = Path(__file__).parent.parent / ".env"
_db_path_str = os.getenv("DB_PATH", "data/stock_data.db")
_db_path = Path(_db_path_str)
DB_PATH = str(_db_path.resolve())
DATA_MODE = os.getenv("DATA_MODE", "websearch")
def get_data_mode() -> str:
    """获取当前数据模式：jnb 或 websearch"""
    return DATA_MODE
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
    is_bottom_divergence: bool = False  # 底背离
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

    # ========== 单针下30 ==========
    is_needle_30: bool = False  # 单针下30信号（红>85, 白<30）

    # ========== 异动选股法 ==========
    is_yidong: bool = False    # 当日是否异动（突然放量+60日线附近）
    yidong_type: str = ""      # 异动类型：詹姆斯级/徐杰级
    yidong_vol_ratio: float = 0  # 异动量比
    yidong_above_60d: bool = False  # 是否从60日线附近起来

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
    sell_items: Dict[str, bool] = None  # 5项明细 {项目名: 是否通过}

    # 交易信号
    signal: TradeSignal = TradeSignal.WATCH

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

    # 双枪战法
    is_double_gun: bool = False  # 双枪战法信号
    double_gun_vol1: float = 0   # 第一枪量比
    double_gun_vol2: float = 0   # 第二枪量比
    double_gun_gap_days: int = 0  # 两枪间隔天数

    # 超级B1
    is_sb1_detailed: bool = False  # 超级B1（独立检测）

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

    # 娜娜图 (完美建仓形态)
    is_nana: bool = False        # 娜娜图信号

    # 黄金碗 (白线黄线之间的区域)
    is_in_bowl: bool = False     # 价格是否在碗内(白线>价>黄线)
    bowl_upper: float = 0        # 碗上沿(白线)
    bowl_lower: float = 0        # 碗下沿(黄线)

    # 呼吸结构
    breath_phase: str = ""       # exhale/inhale/none
    breath_n_type: bool = False  # 是否N型结构

    # SB1假摔
    is_sb1: bool = False         # SB1假摔信号

    # B3买点
    is_b3: bool = False          # B3买点信号

    # 四块砖交易体系
    brick_consecutive: int = 0   # 当前连续砖数
    brick_action: str = ""       # 操作建议: 减仓/止损/持有/观望/禁止抄底
    brick_action_desc: str = ""  # 操作描述
    is_brick_flip_green: bool = False  # 红砖刚翻绿（止损信号）

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
def calculate_ma(prices: List[float], period: int) -> float:
    """计算简单移动平均"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period
def calculate_ema(prices: List[float], period: int) -> float:
    """计算指数移动平均（返回最新值）"""
    series = calculate_ema_series(prices, period)
    return series[-1] if series else 0


def calculate_ema_series(prices: List[float], period: int) -> List[float]:
    """
    计算指数移动平均完整序列（通达信标准，从第一个值递归）

    EMA[i] = price[i] * k + EMA[i-1] * (1 - k)
    EMA[0] = price[0]

    Returns: 与 prices 等长的 EMA 序列
    """
    if not prices:
        return []

    k = 2 / (period + 1)
    result = [prices[0]]

    for price in prices[1:]:
        result.append(price * k + result[-1] * (1 - k))

    return result
def calculate_sma_td(values: List[float], period: int, m: int) -> float:
    """
    通达信 SMA 函数（仅取最终值）

    公式: SMA = X * M/N + SMA_prev * (1 - M/N)

    Args:
        values: 价格序列
        period: 周期 N
        m: 权重 M

    Returns:
        SMA 最终值
    """
    series = calculate_sma_td_series(values, period, m)
    return series[-1] if series else 0


def calculate_sma_td_series(values: List[float], period: int, m: int) -> List[float]:
    """
    通达信标准 SMA 递归函数，返回完整序列

    SMA[i] = X[i] * M/N + SMA[i-1] * (1 - M/N)
    SMA[0] = X[0]（初始值）

    通达信的 SMA 是从第一个值开始递归累积的，每一天的结果都影响下一天。

    Args:
        values: 输入序列
        period: 周期 N
        m: 权重 M

    Returns:
        与 values 等长的 SMA 序列
    """
    if not values:
        return []

    weight = m / period
    result = [values[0]]

    for i in range(1, len(values)):
        result.append(values[i] * weight + result[-1] * (1 - weight))

    return result
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
def precompute_kdj_sequence(klines: List[DailyData], period: int = 9) -> List[Tuple[float, float, float]]:
    """
    预计算全量 KDJ 序列（增量算法，O(n)）

    返回每一天的 (K, D, J)，避免在循环中重复计算。
    """
    n = len(klines)
    if n < period:
        return [(50, 50, 50)] * n

    result = []
    k = 50.0
    d = 50.0

    for i in range(n):
        if i < period - 1:
            result.append((50, 50, 50))
            continue

        low_min = min(klines[j].low for j in range(i - period + 1, i + 1))
        high_max = max(klines[j].high for j in range(i - period + 1, i + 1))

        if high_max == low_min:
            rsv = 50
        else:
            rsv = (klines[i].close - low_min) / (high_max - low_min) * 100

        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k
        j = 3 * k - 2 * d

        result.append((round(k, 2), round(d, 2), round(j, 2)))

    return result
def precompute_bbi_sequence(klines: List[DailyData]) -> List[float]:
    """
    预计算全量 BBI 序列（增量算法，O(n)）
    """
    n = len(klines)
    if n < 24:
        return [0.0] * n

    closes = [k.close for k in klines]
    result = []

    for i in range(n):
        if i < 23:
            result.append(0.0)
        else:
            sub = closes[:i+1]
            ma3 = calculate_ma(sub, 3)
            ma6 = calculate_ma(sub, 6)
            ma12 = calculate_ma(sub, 12)
            ma24 = calculate_ma(sub, 24)
            result.append(round((ma3 + ma6 + ma12 + ma24) / 4, 2))

    return result
def precompute_macd_sequence(klines: List[DailyData],
                              fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
    """
    预计算全量 MACD 序列（增量算法，O(n)）

    返回每一天的 (DIF, DEA, MACD_HIST)。
    对于数据不足的天数，返回 0.0。
    """
    n = len(klines)
    dif_seq = [0.0] * n
    dea_seq = [0.0] * n
    macd_seq = [0.0] * n

    if n < slow:
        return dif_seq, dea_seq, macd_seq

    closes = [k.close for k in klines]

    # 增量计算 EMA
    k_fast = 2 / (fast + 1)
    k_slow = 2 / (slow + 1)

    ema_fast = [closes[0]]
    ema_slow = [closes[0]]

    for i in range(1, n):
        ema_fast.append(closes[i] * k_fast + ema_fast[-1] * (1 - k_fast))
        ema_slow.append(closes[i] * k_slow + ema_slow[-1] * (1 - k_slow))

    # DIF 从 slow-1 开始有效
    dif_list = []
    for i in range(slow - 1, n):
        dif_val = ema_fast[i] - ema_slow[i]
        dif_list.append(dif_val)
        dif_seq[i] = dif_val

    if len(dif_list) < signal:
        return dif_seq, dea_seq, macd_seq

    # 增量计算 DEA (DIF 的 EMA)
    k_signal = 2 / (signal + 1)
    dea = [dif_list[0]]

    for i in range(1, len(dif_list)):
        dea_val = dif_list[i] * k_signal + dea[-1] * (1 - k_signal)
        dea.append(dea_val)

        dea_idx = slow - 1 + i
        if dea_idx < n:
            dea_seq[dea_idx] = dea_val
            macd_seq[dea_idx] = 2 * (dif_list[i] - dea_val)

    return dif_seq, dea_seq, macd_seq
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

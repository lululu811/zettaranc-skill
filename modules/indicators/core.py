"""
技术指标计算模块 — 核心基础类型与数学工具
"""

from typing import Optional, Any

import os
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载，override=True）

from modules.database import DB_PATH as _db_path, get_db_connection

DB_PATH = str(_db_path)

# 数据模式
DATA_MODE = os.getenv("DATA_MODE", "websearch")


def get_data_mode() -> str:
    """获取当前数据模式：jnb 或 websearch"""
    return DATA_MODE


class TradeSignal(Enum):
    """交易信号"""

    B1 = "B1"  # 买入点1
    B2 = "B2"  # 买入点2（确认）
    B3 = "B3"  # 买入点3
    SB1 = "SB1"  # 超级B1
    S1 = "S1"  # 卖出信号1
    S2 = "S2"  # 卖出信号2
    HOLD = "HOLD"  # 持有
    WATCH = "WATCH"  # 观望


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

    # 扩展形态与特征字段（供 strategies 策略计算使用）
    is_rise: bool = False
    is_beidou: bool = False
    is_suoliang: bool = False
    is_jiayin: bool = False
    is_yinxian: bool = False
    is_fangliang_yinxian: bool = False
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None
    bbi: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


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
    boll_mid: float = 0  # 中轨 = MA20
    boll_upper: float = 0  # 上轨 = 中轨 + 2*STD
    boll_lower: float = 0  # 下轨 = 中轨 - 2*STD
    boll_width: float = 0  # 布林带宽度
    boll_position: float = 0  # 股价在布林带中的位置 (0-100%)

    # 量比
    vol_ratio: float = 0  # 量比 = 当前量 / 5日均量

    # ========== Z哥双线战法 ==========
    zg_white: float = 0  # Z哥白线 = EMA(EMA(C,10),10)
    dg_yellow: float = 0  # 大哥线 = (MA14+MA28+MA57+MA114)/4
    is_gold_cross: bool = False  # 金叉（白线上穿大哥线）
    is_dead_cross: bool = False  # 死叉（白线下穿大哥线）

    # ========== 单针下20 ==========
    rsl_short: float = 0  # 短期RSL (3日)
    rsl_long: float = 0  # 长期RSL (21日)
    is_needle_20: bool = False  # 单针下20信号

    # ========== 单针下30 ==========
    is_needle_30: bool = False  # 单针下30信号（红>85, 白<30）

    # ========== 异动选股法 ==========
    is_yidong: bool = False  # 当日是否异动（突然放量+60日线附近）
    yidong_type: str = ""  # 异动类型：詹姆斯级/徐杰级
    yidong_vol_ratio: float = 0  # 异动量比
    yidong_above_60d: bool = False  # 是否从60日线附近起来

    # ========== 砖型图系统 ==========
    brick_value: float = 0  # 砖型图数值
    brick_trend: str = "NEUTRAL"  # 趋势: RED(红砖)/GREEN(绿砖)/NEUTRAL(中性)
    brick_count: int = 0  # 连续砖数
    brick_trend_up: bool = False  # 命值趋势上升
    is_fanbao: bool = False  # 精准反包信号（2/3位置）

    # 量价信号
    is_beidou: bool = False  # 倍量
    is_suoliang: bool = False  # 缩量
    is_jiayin_zhenyang: bool = False  # 假阴真阳
    is_jiayang_zhenyin: bool = False  # 假阳真阴
    is_fangliang_yinxian: bool = False  # 放量阴线

    # 卖出评分
    sell_score: int = 0  # 0-5分
    sell_items: dict[str, bool] | None = None  # 5项明细 {项目名: 是否通过}

    # 交易信号
    signal: TradeSignal = TradeSignal.WATCH

    # 关键价位
    prev_high: float = 0  # 昨日最高价
    prev_low: float = 0  # 昨日最低价

    # DMI/ADX
    dmi_plus: float = 0
    dmi_minus: float = 0
    adx: float = 0

    # 资金流
    net_lg_mf: float = 0  # 主力净流入
    net_elg_mf: float = 0  # 超大单净流入

    # B1/B2战法记录
    last_b1_date: str = ""
    last_b1_price: float = 0

    # B1建仓波检测
    is_b1: bool = False  # 当日是否为B1
    b1_j_value: float = 0  # B1的J值
    b1_amplitude: float = 0  # B1振幅
    b1_pct_chg: float = 0  # B1涨幅
    b1_volume_shrink: bool = False  # 是否缩量
    b1_score: int = 0  # B1匹配度评分(0-4)

    # B2突破检测
    is_b2: bool = False  # 当日是否为B2
    b2_follows_b1: bool = False  # 是否在B1后
    b2_pct_chg: float = 0  # B2涨幅
    b2_j_value: float = 0  # B2的J值
    b2_volume_up: bool = False  # 是否放量
    b2_score: int = 0  # B2匹配度评分(0-4)

    # 双枪战法
    is_double_gun: bool = False  # 双枪战法信号
    double_gun_vol1: float = 0  # 第一枪量比
    double_gun_vol2: float = 0  # 第二枪量比
    double_gun_gap_days: int = 0  # 两枪间隔天数

    # 超级B1
    is_sb1_detailed: bool = False  # 超级B1（独立检测）

    # 关键K检测
    key_k_list: list[dict] | None = None  # 关键K列表，每根含日期/类型/实体%/量比

    # 暴力K检测
    is_violence_k: bool = False  # 最新这天是否暴力K
    violence_k_type: str = ""  # 大暴力/小暴力
    violence_k_body: float = 0  # 实体涨幅%

    # 两个30%原则 (B1筛选)
    b1_rally_pct: float = 0  # B1建仓波涨幅%
    b1_turnover: float = 0  # B1累计换手率%
    b1_pass_30: bool = False  # 是否通过两个30%原则

    # 娜娜图 (完美建仓形态)
    is_nana: bool = False  # 娜娜图信号

    # 黄金碗 (白线黄线之间的区域)
    is_in_bowl: bool = False  # 价格是否在碗内(白线>价>黄线)
    bowl_upper: float = 0  # 碗上沿(白线)
    bowl_lower: float = 0  # 碗下沿(黄线)

    # 呼吸结构
    breath_phase: str = ""  # exhale/inhale/none
    breath_n_type: bool = False  # 是否N型结构

    # SB1假摔
    is_sb1: bool = False  # SB1假摔信号

    # B3买点
    is_b3: bool = False  # B3买点信号

    # 四块砖交易体系
    brick_consecutive: int = 0  # 当前连续砖数
    brick_action: str = ""  # 操作建议: 减仓/止损/持有/观望/禁止抄底
    brick_action_desc: str = ""  # 操作描述
    is_brick_flip_green: bool = False  # 红砖刚翻绿（止损信号）

    # 异动记录
    last_yidong_date: str = ""

    # 市场背景
    market_pct_chg: float = 0
    market_dir: str = "NEUTRAL"


def calculate_ma(prices: list[float], period: int) -> float:
    """计算简单移动平均"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period


def calculate_ema(prices: list[float], period: int) -> float:
    """计算指数移动平均"""
    if len(prices) < period:
        return 0

    k = 2 / (period + 1)
    ema = prices[0]

    for price in prices[1:]:
        ema = price * k + ema * (1 - k)

    return ema


def calculate_sma_td(values: list[float], period: int, m: int) -> float:
    """
    通达信 SMA 函数（返回最后一个值）

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


def calculate_sma_series(values: list[float], period: int, m: int) -> list[float]:
    """
    通达信 SMA 递推序列（返回完整序列）

    与通达信完全一致：从序列第一个值开始递推，
    每个点的 SMA 都承接前一个点的结果。

    公式: SMA[i] = values[i] * M/N + SMA[i-1] * (1 - M/N)
    初始值: SMA[0] = values[0]

    Args:
        values: 输入序列
        period: 周期 N
        m: 权重 M

    Returns:
        SMA 序列（长度与输入一致）
    """
    if not values:
        return []

    weight = m / period
    sma = values[0]
    result = [sma]

    for v in values[1:]:
        sma = v * weight + sma * (1 - weight)
        result.append(sma)

    return result


def calculate_slope(values: list[float], period: int) -> float:
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


def calculate_kdj(klines: list[DailyData], period: int = 9, k_ma: int = 3, d_ma: int = 3) -> tuple[float, float, float]:
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
    rsv_list: list[float] = []
    for i in range(period - 1, len(klines)):
        low_list = [klines[j].low for j in range(i - period + 1, i + 1)]
        high_list = [klines[j].high for j in range(i - period + 1, i + 1)]

        low_min = min(low_list)
        high_max = max(high_list)

        if high_max == low_min:
            rsv = 50.0
        else:
            rsv = (klines[i].close - low_min) / (high_max - low_min) * 100

        rsv_list.append(rsv)

    if not rsv_list:
        return 50.0, 50.0, 50.0

    # 计算 K、D、J
    k = 50.0
    d = 50.0

    for rsv in rsv_list:
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k

    j = 3 * k - 2 * d

    return round(k, 2), round(d, 2), round(j, 2)


def precompute_kdj_sequence(klines: list[DailyData], period: int = 9) -> list[tuple[float, float, float]]:
    """
    预计算全量 KDJ 序列（增量算法，O(n)），使用 Pandas 向量化优化。
    """
    import pandas as pd

    n = len(klines)
    if n < period:
        return [(50.0, 50.0, 50.0)] * n

    df = pd.DataFrame(
        {"high": [k.high for k in klines], "low": [k.low for k in klines], "close": [k.close for k in klines]}
    )

    low_min = df["low"].rolling(window=period, min_periods=period).min()
    high_max = df["high"].rolling(window=period, min_periods=period).max()

    rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50.0)

    first_valid_idx = period - 1
    valid_rsv = rsv.iloc[first_valid_idx:]

    rsv_with_init = pd.concat([pd.Series([50.0]), valid_rsv]).reset_index(drop=True)

    k = rsv_with_init.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    j = 3 * k - 2 * d

    k = k.iloc[1:].reset_index(drop=True)
    d = d.iloc[1:].reset_index(drop=True)
    j = j.iloc[1:].reset_index(drop=True)

    prefix_k = pd.Series([50.0] * first_valid_idx)
    prefix_d = pd.Series([50.0] * first_valid_idx)
    prefix_j = pd.Series([50.0] * first_valid_idx)

    final_k = pd.concat([prefix_k, k], ignore_index=True).round(2)
    final_d = pd.concat([prefix_d, d], ignore_index=True).round(2)
    final_j = pd.concat([prefix_j, j], ignore_index=True).round(2)

    return list(zip(final_k.tolist(), final_d.tolist(), final_j.tolist()))


def precompute_bbi_sequence(klines: list[DailyData]) -> list[float]:
    """
    预计算全量 BBI 序列，使用 Pandas 向量化优化。
    """
    import pandas as pd

    n = len(klines)
    if n < 24:
        return [0.0] * n

    closes = pd.Series([k.close for k in klines])

    ma3 = closes.rolling(window=3, min_periods=3).mean()
    ma6 = closes.rolling(window=6, min_periods=6).mean()
    ma12 = closes.rolling(window=12, min_periods=12).mean()
    ma24 = closes.rolling(window=24, min_periods=24).mean()

    bbi = (ma3 + ma6 + ma12 + ma24) / 4
    bbi = bbi.fillna(0.0).round(2)

    return bbi.tolist()


def precompute_macd_sequence(
    klines: list[DailyData], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float], list[float]]:
    """
    预计算全量 MACD 序列，使用 Pandas 向量化优化。

    返回每一天的 (DIF, DEA, MACD_HIST)。
    对于数据不足的天数，返回 0.0。
    """
    import pandas as pd

    n = len(klines)
    if n < slow:
        return [0.0] * n, [0.0] * n, [0.0] * n

    df = pd.DataFrame({"close": [k.close for k in klines]})

    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow

    # Strictly match TDX loop initialization
    dif_series = dif.copy()
    dif_series.loc[: slow - 2] = 0.0

    dea_valid = dif_series.iloc[slow - 1 :].ewm(span=signal, adjust=False).mean()
    dea_series = pd.concat([pd.Series([0.0] * (slow - 1)), dea_valid]).reset_index(drop=True)

    macd_series = (dif_series - dea_series) * 2

    return dif_series.tolist(), dea_series.tolist(), macd_series.tolist()


def calculate_macd(
    klines: list[DailyData], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float], list[float]]:
    """
    计算 MACD 指标（通达信标准公式）

    DIFF: EMA(CLOSE, 12) - EMA(CLOSE, 26)
    DEA: EMA(DIFF, 9)
    MACD: 2 * (DIFF - DEA), COLORSTICK

    内部复用 precompute_macd_sequence 的 O(n) 递推实现，
    避免对子序列重复调用 calculate_ema 导致的 O(n²) 性能和精度问题。

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

    dif_seq, dea_seq, macd_seq = precompute_macd_sequence(klines, fast, slow, signal)

    # DIF 从 slow-1 开始有效
    dif_list = dif_seq[slow - 1 :]

    # DEA/MACD 从 slow+signal-2 开始有效
    dea_start = slow + signal - 2
    dea_list = dea_seq[dea_start:]
    macd_list = macd_seq[dea_start:]

    return dif_list, dea_list, macd_list


def calculate_bbi(klines: list[DailyData]) -> float:
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


def calculate_rsi(klines: list[DailyData], period: int = 14) -> float:
    """
    计算 RSI 相对强弱指标（通达信标准公式）

    通达信公式:
    RSI := SMA(MAX(CLOSE-REF(CLOSE,1),0),N,1) / SMA(ABS(CLOSE-REF(CLOSE,1)),N,1) * 100

    关键点：分子分母都是递推 SMA，不是简单平均。

    Args:
        klines: K线数据
        period: 周期，默认14

    Returns:
        RSI 值 (0-100)
    """
    if len(klines) < period + 1:
        return 50  # 默认中性值

    closes = [k.close for k in klines]

    # 计算每日涨跌序列
    changes = []
    for i in range(1, len(closes)):
        changes.append(closes[i] - closes[i - 1])

    if len(changes) < period:
        return 50

    # 分离上涨和下跌
    up_list = [max(c, 0) for c in changes]
    down_list = [abs(min(c, 0)) for c in changes]

    # 用递推 SMA 计算平均上涨和平均下跌（和通达信一致）
    avg_up_list = calculate_sma_series(up_list, period, 1)
    avg_down_list = calculate_sma_series(down_list, period, 1)

    avg_up = avg_up_list[-1]
    avg_down = avg_down_list[-1]

    if avg_down == 0:
        return 100  # 一直涨

    rsi = avg_up / (avg_up + avg_down) * 100

    return round(rsi, 2)


def calculate_rsi_multi(klines: list[DailyData]) -> tuple[float, float, float]:
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


def detect_macd_trap(dif_list: list[float], dea_list: list[float]) -> dict[str, bool]:
    """
    MACD 金叉空 / 死叉多 陷阱识别

    来源：indicators.md 3.12「金叉空 + 死叉多」
    核心价值：避开 90% 的诱多/诱空陷阱。

    金叉空：眼看就要金叉，白线(DIF)突然拐头向下，金叉没成
      → 原下跌趋势延续，最恶毒的诱多
      → 条件：前3天 DIF 在 DEA 下方 + DIF 连续上升接近 DEA + 最近拐头向下

    死叉多：眼看就要死叉，白线(DIF)突然拐头向上，死叉没成
      → 原上涨趋势延续，空中加油
      → 条件：前3天 DIF 在 DEA 上方 + DIF 连续下降接近 DEA + 最近拐头向上

    Args:
        dif_list: DIF 序列（至少5个点）
        dea_list: DEA 序列（至少5个点）

    Returns:
        {'is_gold_trap': bool, 'is_dead_trap': bool}
    """
    if len(dif_list) < 5 or len(dea_list) < 5:
        return {"is_gold_trap": False, "is_dead_trap": False}

    # 取最近5天
    dif = dif_list[-5:]
    dea = dea_list[-5:]

    # ====== 金叉空检测 ======
    # 前3天 DIF 在 DEA 下方（空头区间）
    is_below = all(dif[i] < dea[i] for i in range(3))
    # 第3天 → 第4天 DIF 上升（眼看金叉）
    is_approaching = dif[2] < dif[3]
    # 第4天 → 第5天 DIF 拐头向下（金叉没成）
    is_turn_down = dif[3] > dif[4]
    # 最终 DIF 仍在 DEA 下方
    is_gold_trap = is_below and is_approaching and is_turn_down and dif[4] < dea[4]

    # ====== 死叉多检测 ======
    # 前3天 DIF 在 DEA 上方（多头区间）
    is_above = all(dif[i] > dea[i] for i in range(3))
    # 第3天 → 第4天 DIF 下降（眼看死叉）
    is_approaching_dead = dif[2] > dif[3]
    # 第4天 → 第5天 DIF 拐头向上（死叉没成）
    is_turn_up = dif[3] < dif[4]
    # 最终 DIF 仍在 DEA 上方
    is_dead_trap = is_above and is_approaching_dead and is_turn_up and dif[4] > dea[4]

    return {"is_gold_trap": is_gold_trap, "is_dead_trap": is_dead_trap}


def calculate_wr(klines: list[DailyData], period: int = 14) -> float:
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


def calculate_wr_multi(klines: list[DailyData]) -> tuple[float, float]:
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


def calculate_bollinger(
    klines: list[DailyData], period: int = 20, std_dev: float = 2.0
) -> tuple[float, float, float, float, float]:
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
    std = variance**0.5

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


def calculate_vol_ratio(klines: list[DailyData], period: int = 5) -> float:
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
    recent_vols = [klines[i].vol for i in range(-period - 1, -1)]

    if not recent_vols:
        return 1.0

    avg_vol = sum(recent_vols) / len(recent_vols)
    current_vol = klines[-1].vol

    if avg_vol == 0:
        return 1.0

    ratio = current_vol / avg_vol

    return round(ratio, 2)

"""
战法识别模块
实现 Z哥 策略中的各种战法识别
"""

import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

# 数据库路径
DB_PATH = "data/stock_data.db"

# Import 兼容：支持从 indicators 导入砖形图相关函数
try:
    from .indicators import DailyData, detect_four_brick_system, calculate_brick_value
except ImportError:
    from indicators import DailyData, detect_four_brick_system, calculate_brick_value


def _klines_dict_to_daily(klines: List[Dict]) -> List[DailyData]:
    """将 strategies 模块用的 dict klines 转为 indicators 模块用的 DailyData"""
    result = []
    for i, k in enumerate(klines):
        prev_close = klines[i-1]["close"] if i > 0 else k["close"]
        result.append(DailyData(
            ts_code=k["ts_code"],
            trade_date=k["trade_date"],
            open=k["open"],
            high=k["high"],
            low=k["low"],
            close=k["close"],
            vol=k["vol"],
            amount=k.get("amount", k["close"] * k["vol"]),
            pct_chg=k.get("pct_chg", 0),
            prev_close=prev_close,
        ))
    return result


class StrategyType(Enum):
    """战法类型"""
    # 基础战法
    B1 = "B1"                    # 买点1
    B2 = "B2"                    # 买点2（确认）
    B3 = "B3"                    # 买点3
    SB1 = "SB1"                  # 超级B1

    # 复合战法
    CHANGAN = "长安战法"          # 三日确认战法
    SI_FEN_ZHI_SAN = "四分之三阴量"  # 假突破识别
    NANA = "娜娜图形"            # 连续放量涨+缩量回调
    CHAOFAN = "超级B1"            # 超级买点

    # 异动战法
    YIDONG_DILIAN = "异动+地量地价"  # 异动后缩量买点

    # 特殊形态
    PINGHANG = "平行重炮"          # 双阳夹阴
    KENGQI = "坑里起好货"          # 填坑战法
    DUIchen = "对称VA"             # 对称战法

    # 逃顶信号
    S1 = "S1"                    # 初级逃顶（丑陋大绿帽）
    S2 = "S2"                    # 确认逃顶（MACD顶背离）
    S3 = "S3"                    # 最后逃生（反抽无力）

    # 主力阶段
    XISHOU = "吸筹"               # 麒麟会吸筹阶段
    LASHENG = "拉升"              # 麒麟会拉升阶段
    PAIFA = "派发"                # 麒麟会派发阶段
    LUOLUO = "回落"               # 麒麟会回落阶段

    # 砖形图信号
    BRICK_EXIT = "四块砖翻绿"      # 红砖翻绿 → 止损
    BRICK_REDUCE = "四块砖减仓"    # 红砖满4块 → 减仓一半
    BRICK_BOUNCE = "四块砖反弹"    # 绿砖满4块 → 可能止跌，观察B1


class Priority(Enum):
    """信号优先级"""
    CRITICAL = 3     # 紧急：止损、逃顶
    OPPORTUNITY = 2  # 机会：买点、战法
    OBSERVE = 1      # 观察：提示、减仓、阶段判断


@dataclass
class StrategySignal:
    """战法信号"""
    ts_code: str
    trade_date: str
    strategy: StrategyType
    confidence: float              # 置信度 0-1
    description: str
    details: Dict[str, Any] = field(default_factory=dict)

    # 交易建议
    action: str = "WATCH"          # BUY/SELL/HOLD/WATCH
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_ratio: Optional[float] = None

    # 信号优先级（由策略检测函数自动填入）
    priority: Priority = Priority.OBSERVE


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_kline_data(ts_code: str, days: int = 120) -> List[Dict]:
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
        FROM daily_kline
        WHERE ts_code = ?
        ORDER BY trade_date ASC
        LIMIT ?
    """, (ts_code, days))

    rows = cursor.fetchall()
    conn.close()

    data_list = []
    for i, row in enumerate(rows):
        prev_close = rows[i-1]['close'] if i > 0 else row['close']
        prev_vol = rows[i-1]['vol'] if i > 0 else row['vol']

        data_list.append({
            'ts_code': row['ts_code'],
            'trade_date': row['trade_date'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'vol': row['vol'],
            'amount': row['amount'],
            'pct_chg': row['pct_chg'],
            'prev_close': prev_close,
            'prev_vol': prev_vol,
            # 基础指标计算
            'is_rise': row['close'] > prev_close,
            'is_beidou': row['vol'] >= prev_vol * 2,
            'is_suoliang': row['vol'] <= prev_vol * 0.5,
            'is_jiayin': row['close'] < row['open'] and row['close'] > prev_close,  # 假阴真阳
            'is_yinxian': row['close'] < prev_close,  # 阴线
            'is_fangliang_yinxian': row['close'] < prev_close and row['vol'] > prev_vol * 1.5,
        })

    return data_list


# ---------------------------------------------------------------------------
# 指标计算委托给 indicators.py，消除重复实现
# ---------------------------------------------------------------------------

def _dict_to_daily(klines: List[Dict]) -> List[Any]:
    """将 Dict K 线列表转换为 indicators.DailyData"""
    try:
        from modules.indicators import DailyData
    except ImportError:
        from indicators import DailyData
    return [DailyData(
        ts_code=k['ts_code'],
        trade_date=k['trade_date'],
        open=k['open'],
        high=k['high'],
        low=k['low'],
        close=k['close'],
        vol=k['vol'],
        amount=k.get('amount', 0),
        pct_chg=k.get('pct_chg', 0),
    ) for k in klines]


def _calc_kdj(klines: List[Dict]) -> Tuple[float, float, float]:
    """通过 indicators.py 计算 KDJ"""
    try:
        from modules.indicators import calculate_kdj
    except ImportError:
        from indicators import calculate_kdj
    daily = _dict_to_daily(klines)
    return calculate_kdj(daily)


def _calc_bbi(klines: List[Dict]) -> float:
    """通过 indicators.py 计算 BBI"""
    try:
        from modules.indicators import calculate_bbi
    except ImportError:
        from indicators import calculate_bbi
    daily = _dict_to_daily(klines)
    return calculate_bbi(daily)


# 兼容层：保留旧API供测试和外部调用使用
def calculate_ma(prices: List[float], period: int) -> float:
    """已废弃：请使用 indicators.calculate_ma"""
    try:
        from modules.indicators import calculate_ma as _calc_ma_ind
    except ImportError:
        from indicators import calculate_ma as _calc_ma_ind
    return _calc_ma_ind(prices, period)


def calculate_kdj(klines: List[Dict], period: int = 9) -> Tuple[float, float, float]:
    """已废弃：请使用 indicators.calculate_kdj（接收 DailyData）"""
    return _calc_kdj(klines)


def calculate_bbi(klines: List[Dict]) -> float:
    """已废弃：请使用 indicators.calculate_bbi（接收 DailyData）"""
    return _calc_bbi(klines)


def detect_b1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B1 买点

    B1 条件：
    1. J < -10（核心条件）
    2. 缩量回调（最佳）
    3. 价格在 BBI 下方或附近
    4. 非绿砖状态（连续下跌）
    """
    if index < 10:
        return None

    today = klines[index]
    k, d, j = _calc_kdj(klines[:index+1])

    # 核心条件：J < -10
    if j >= -10:
        return None

    # 最佳条件：缩量回调
    is_suoliang = today['is_suoliang']

    # 检查是否在连续下跌中（绿砖状态）
    # 绿砖：连续4根阴线
    recent_4 = klines[index-3:index+1]
    yin_count = sum(1 for k in recent_4 if k['is_yinxian'])

    # B1 买点
    bbi = _calc_bbi(klines[:index+1])
    price = today['close']

    # 计算止损位
    stop_loss = today['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B1,
        confidence=0.8 if is_suoliang else 0.6,
        description=f"B1买点 J={j:.2f}" + (" 缩量回调" if is_suoliang else ""),
        details={
            'j': j,
            'k': k,
            'd': d,
            'is_suoliang': is_suoliang,
            'yin_count_4': yin_count,
            'bbi': bbi,
            'price': price,
        },
        action="BUY",
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY)


def detect_b2(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B2 买点

    B2 条件（B1后的确认信号）：
    1. 前几日有B1（J<-10）
    2. 放量长阳（涨幅>=4%）
    3. J值拐头（>-10）
    4. 无上影线最好
    """
    if index < 15:
        return None

    today = klines[index]

    # 检查是否有B1在前几日
    has_b1 = False
    prev_j_list = []
    for i in range(5, min(15, index)):
        pk, pd, pj = _calc_kdj(klines[:index-i+1])
        prev_j_list.append(pj)
        if pj < -10:
            has_b1 = True
            break

    if not has_b1:
        return None

    # 放量长阳
    is_beidou = today['is_beidou']
    pct_chg = today['pct_chg']
    is_long_yang = pct_chg >= 4

    # 无上影线
    has_upper_shadow = today['high'] > today['close'] * 1.01

    if not (is_long_yang and is_beidou):
        return None

    # 计算J值
    k, d, j = _calc_kdj(klines[:index+1])

    # B2 确认
    stop_loss = today['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B2,
        confidence=0.85 if not has_upper_shadow else 0.75,
        description=f"B2确认 涨{pct_chg:.2f}% J={j:.2f}",
        details={
            'j': j,
            'pct_chg': pct_chg,
            'is_beidou': is_beidou,
            'has_upper_shadow': has_upper_shadow,
            'price': today['close'],
        },
        action="BUY",
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY)


def detect_b3(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B3 中继买点

    B3 条件：
    1. B2后出现
    2. 分歧转一致（小阳线）
    3. 涨幅<2%
    4. 振幅<7%
    """
    if index < 20:
        return None

    today = klines[index]
    prev_2 = klines[index-2] if index >= 2 else None
    prev_3 = klines[index-3] if index >= 3 else None

    # 检查前几日是否有B2
    has_b2 = False
    for i in range(3, min(10, index)):
        if klines[index-i]['pct_chg'] >= 4 and klines[index-i]['is_beidou']:
            has_b2 = True
            break

    if not has_b2:
        return None

    # B3：小阳线，分歧转一致
    pct_chg = today['pct_chg']
    amplitude = (today['high'] - today['low']) / today['prev_close'] * 100

    if not (0 < pct_chg < 2 and amplitude < 7):
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B3,
        confidence=0.7,
        description=f"B3中继 涨{pct_chg:.2f}% 振幅{amplitude:.2f}%",
        details={
            'pct_chg': pct_chg,
            'amplitude': amplitude,
            'price': today['close'],
        },
        action="BUY",
        stop_loss=today['low'],
        priority=Priority.OPPORTUNITY)


def detect_sb1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测超级B1

    超级B1条件：
    1. 缩量回调到极致
    2. 突然放量下跌（震仓）
    3. 继续缩量企稳
    4. J出现负值
    """
    if index < 10:
        return None

    today = klines[index]
    prev_1 = klines[index-1] if index >= 1 else None
    prev_2 = klines[index-2] if index >= 2 else None

    if not (prev_1 and prev_2):
        return None

    # 检查前2天是否有放量下跌
    is_drop_vol = prev_2['close'] < prev_2['open'] and prev_2['vol'] > klines[index-3]['vol'] * 1.5

    if not is_drop_vol:
        return None

    # 今日缩量企稳
    is_suoliang = today['is_suoliang']

    # J值
    k, d, j = _calc_kdj(klines[:index+1])

    if j >= -5:
        return None

    # 超级B1确认
    stop_loss = prev_2['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.SB1,
        confidence=0.9,
        description=f"超级B1 J={j:.2f} 放量跌后缩量企稳",
        details={
            'j': j,
            'drop_vol': prev_2['vol'],
            'is_suoliang': is_suoliang,
            'price': today['close'],
        },
        action="BUY",
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY)


def detect_changan(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测长安战法（胜率75%）

    三条件：
    1. 第一天为B1（J<-13）
    2. 第二天为放量长阳，J值拐头
    3. 第三天为分歧转一致且缩半量
    """
    if index < 3:
        return None

    day1 = klines[index-2]
    day2 = klines[index-1]
    day3 = klines[index]

    # 第一天：B1（J<-13）
    k1, d1, j1 = _calc_kdj(klines[:index-1])
    if j1 >= -13:
        return None

    # 第二天：放量长阳，J拐头
    k2, d2, j2 = _calc_kdj(klines[:index])
    if not (day2['pct_chg'] >= 4 and day2['is_beidou'] and j2 > j1):
        return None

    # 第三天：分歧转一致，缩半量
    pct_chg = day3['pct_chg']
    amplitude = (day3['high'] - day3['low']) / day3['prev_close'] * 100
    is_half_vol = day3['vol'] <= day2['vol'] * 0.5

    if not (0 < pct_chg < 2 and amplitude < 7 and is_half_vol):
        return None

    return StrategySignal(
        ts_code=day3['ts_code'],
        trade_date=day3['trade_date'],
        strategy=StrategyType.CHANGAN,
        confidence=0.75,
        description=f"长安战法确认 胜率75%",
        details={
            'j1': j1,
            'j2': j2,
            'day2_pct': day2['pct_chg'],
            'day3_pct': pct_chg,
            'amplitude': amplitude,
        },
        action="BUY",
        stop_loss=day3['low'],
        priority=Priority.OPPORTUNITY)


def detect_sifen_zhiyi_sanyin(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测四分之三阴量战法

    条件：大阳线后次日阴量 > 阳量 × 0.75 = 假突破
    """
    if index < 1:
        return None

    today = klines[index]
    yesterday = klines[index-1]

    # 昨日大阳线
    if yesterday['pct_chg'] < 3:
        return None

    # 今日阴线
    if today['close'] >= today['open']:
        return None

    # 阴量判断
    vol_ratio = today['vol'] / yesterday['vol']

    if vol_ratio > 0.75:
        # 假突破！主力出货
        return StrategySignal(
            ts_code=today['ts_code'],
            trade_date=today['trade_date'],
            strategy=StrategyType.SI_FEN_ZHI_SAN,
            confidence=0.9,
            description=f"假突破！阴量{vol_ratio:.0%}超过阳量75%",
            details={
                'yang_vol': yesterday['vol'],
                'yin_vol': today['vol'],
                'vol_ratio': vol_ratio,
            },
            action="SELL",
        priority=Priority.OPPORTUNITY)

    return None


def detect_nana(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测娜娜图形

    四条件同时满足：
    1. 连续放量上涨
    2. 顶部无巨量阴线
    3. 连续缩量回调
    4. J下到负值
    """
    if index < 10:
        return None

    # 检查连续放量上涨（最近3-5天）
    rise_count = 0
    for i in range(index-4, index+1):
        if i < 1:
            continue
        if klines[i]['is_rise'] and klines[i]['is_beidou']:
            rise_count += 1

    if rise_count < 3:
        return None

    # 检查顶部无巨量阴线
    for i in range(index-4, index):
        if klines[i]['is_fangliang_yinxian']:
            return None

    # 检查连续缩量回调
    suoliang_count = 0
    for i in range(index-4, index):
        if klines[i]['is_suoliang']:
            suoliang_count += 1

    if suoliang_count < 2:
        return None

    # J值负值
    k, d, j = _calc_kdj(klines[:index+1])
    if j >= 0:
        return None

    return StrategySignal(
        ts_code=klines[index]['ts_code'],
        trade_date=klines[index]['trade_date'],
        strategy=StrategyType.NANA,
        confidence=0.85,
        description=f"娜娜图形 J={j:.2f} 连续放量涨+缩量回调",
        details={
            'j': j,
            'rise_count': rise_count,
            'suoliang_count': suoliang_count,
        },
        action="BUY",
        stop_loss=klines[index]['low'],
        priority=Priority.OPPORTUNITY)


def detect_yidong_dilian(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测异动+地量地价战法

    三步：
    1. 异动 = 突然放量，资金进场
    2. 异动后缩量回调
    3. 地量 = 最佳B1买点
    """
    if index < 5:
        return None

    today = klines[index]

    # 检查前几天是否有异动
    yidong_index = None
    for i in range(index-1, max(0, index-10), -1):
        # 异动：放量+上涨
        if klines[i]['is_beidou'] and klines[i]['is_rise']:
            yidong_index = i
            break

    if yidong_index is None:
        return None

    # 检查异动后是否缩量回调
    days_after = index - yidong_index
    if days_after < 2:
        return None

    # 回调期间应该有缩量
    has_suoliang = any(klines[j]['is_suoliang'] for j in range(yidong_index+1, index+1))

    # 今日地量（最佳买点）
    if not today['is_suoliang']:
        return None

    # J值判断
    k, d, j = _calc_kdj(klines[:index+1])

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.YIDONG_DILIAN,
        confidence=0.8,
        description=f"异动+地量地价 异动后{days_after}天缩量回调 J={j:.2f}",
        details={
            'yidong_date': klines[yidong_index]['trade_date'],
            'days_after': days_after,
            'j': j,
        },
        action="BUY",
        stop_loss=today['low'],
        priority=Priority.OPPORTUNITY)


def detect_pinghang(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测平行重炮 / 多门重炮

    特征：
    1. 两根放量阳线夹住中间若干阴线（至少2根）
    2. 阳线成交量稳稳压住阴线成交量
    3. 第二根阳线涨幅 >= 4%，量能 >= 第一根阳线 90%
    4. J < 55，无上影线最佳
    """
    if index < 6:
        return None

    # 收集最近7天内的放量阳线索引
    yang_indices = []
    for i in range(max(0, index - 6), index + 1):
        if klines[i]['is_rise'] and klines[i]['is_beidou']:
            yang_indices.append(i)

    if len(yang_indices) < 2:
        return None

    # 取最近两根放量阳线
    y1, y2 = yang_indices[-2], yang_indices[-1]

    # 中间必须夹有至少2根K线
    between_count = y2 - y1 - 1
    if between_count < 2:
        return None

    # 中间阴线数量占比过半
    yin_count = sum(1 for i in range(y1 + 1, y2) if not klines[i]['is_rise'])
    if yin_count < between_count * 0.5:
        return None

    # 阳线成交量压住阴线
    max_yin_vol = max(klines[i]['vol'] for i in range(y1 + 1, y2))
    if klines[y1]['vol'] < max_yin_vol * 1.2 or klines[y2]['vol'] < max_yin_vol * 1.2:
        return None

    # 第二根阳线涨幅 >= 4%
    if klines[y2]['pct_chg'] < 4:
        return None

    # 第二根量能 >= 第一根 90%
    if klines[y2]['vol'] < klines[y1]['vol'] * 0.9:
        return None

    # J 值 < 55
    k, d, j = _calc_kdj(klines[:y2 + 1])
    if j >= 55:
        return None

    # 无上影线（可选加分）
    has_upper_shadow = klines[y2]['high'] > klines[y2]['close'] * 1.01
    confidence = 0.85 if not has_upper_shadow else 0.75

    return StrategySignal(
        ts_code=klines[y2]['ts_code'],
        trade_date=klines[y2]['trade_date'],
        strategy=StrategyType.PINGHANG,
        confidence=confidence,
        description=f"平行重炮 涨{klines[y2]['pct_chg']:.1f}% J={j:.1f} 夹{between_count}阴",
        details={
            'j': j,
            'yang1_vol': klines[y1]['vol'],
            'yang2_vol': klines[y2]['vol'],
            'between_count': between_count,
            'yin_count': yin_count,
            'pct_chg': klines[y2]['pct_chg'],
            'has_upper_shadow': has_upper_shadow,
        },
        action="BUY",
        stop_loss=klines[y2]['low'],
        priority=Priority.OPPORTUNITY)


def detect_kengqi(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测坑里起好货 / 填坑战法

    三步：
    1. 放量挖坑（急跌 + 放量，跌破前期平台）
    2. 缩量填坑（企稳 + 缩量回升）
    3. 回到坑沿 = 最后震仓，交易价值最大
    """
    if index < 15:
        return None

    today = klines[index]

    # 找坑：最近15天内的最低点
    recent_low = min(klines[i]['low'] for i in range(index - 14, index + 1))
    low_index = next(i for i in range(index - 14, index + 1) if klines[i]['low'] == recent_low)

    # 坑前高点（坑前5天的最高点）
    if low_index < 5:
        return None

    pre_high = max(klines[i]['high'] for i in range(low_index - 5, low_index))

    # 坑深条件：跌幅 >= 10%
    keng_depth = (pre_high - recent_low) / pre_high
    if keng_depth < 0.10:
        return None

    # 挖坑日必须放量下跌
    keng_day = klines[low_index]
    if not (keng_day['close'] < keng_day['open'] and keng_day['vol'] > klines[low_index - 1]['vol'] * 1.3):
        return None

    # 填坑：从坑底到当前，价格回升到坑沿的 80% 以上
    fill_ratio = (today['close'] - recent_low) / (pre_high - recent_low)
    if fill_ratio < 0.8:
        return None

    # 填坑过程缩量（坑后5日均量 < 坑前5日均量）
    post_vols = [klines[i]['vol'] for i in range(low_index + 1, min(low_index + 6, index + 1))]
    pre_vols = [klines[i]['vol'] for i in range(low_index - 5, low_index)]
    if post_vols and pre_vols:
        post_avg = sum(post_vols) / len(post_vols)
        pre_avg = sum(pre_vols) / len(pre_vols)
        if post_avg >= pre_avg * 0.8:
            return None

    # 祖冲之法目标价 = 2a - b
    target_price = round(2 * pre_high - recent_low, 2)

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.KENGQI,
        confidence=0.8,
        description=f"坑里起好货 坑深{keng_depth*100:.0f}% 填{fill_ratio*100:.0f}% 目标{target_price:.1f}",
        details={
            'keng_depth': round(keng_depth, 4),
            'fill_ratio': round(fill_ratio, 4),
            'pre_high': pre_high,
            'keng_low': recent_low,
            'target_price': target_price,
        },
        action="BUY",
        stop_loss=recent_low,
        priority=Priority.OPPORTUNITY)


def detect_duichen_va(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测对称 VA 战法

    核心：多空力量守恒 → 怎么上涨就怎么下跌（时间+空间）。
    交易价值出现在"守恒被破坏"的位置——即对称完成后的企稳/反弹点。

    简化实现：
    1. 找近期一个上涨波段（低点→高点）
    2. 计算随后的下跌波段（高点→低点）
    3. 如果空间对称（跌幅≈涨幅的 50%~100%）且时间对称
    4. 当前已企稳（缩量 + J 负值或低位）→ 守恒被破坏，有交易价值
    """
    if index < 20:
        return None

    today = klines[index]

    # 找近期高点和低点（过去20天）
    window = klines[index - 19:index + 1]
    highs = [(i, k['high']) for i, k in enumerate(window)]
    lows = [(i, k['low']) for i, k in enumerate(window)]

    peak_idx, peak_price = max(highs, key=lambda x: x[1])
    trough_idx, trough_price = min(lows, key=lambda x: x[1])

    # 必须形成 低→高→低 的 N 型结构
    if not (trough_idx < peak_idx < len(window) - 1):
        return None

    # 上涨波段
    up_days = peak_idx - trough_idx
    up_pct = (peak_price - trough_price) / trough_price

    # 下跌波段（高点后至今）
    down_days = len(window) - 1 - peak_idx
    down_pct = (peak_price - window[-1]['close']) / peak_price

    # 时间对称：下跌天数 / 上涨天数 在 0.8~1.5 之间
    time_sym = down_days / up_days if up_days > 0 else 0
    if not (0.5 <= time_sym <= 2.0):
        return None

    # 空间对称：跌幅 / 涨幅 在 0.4~1.1 之间（直接对称或间接对称）
    space_sym = down_pct / up_pct if up_pct > 0 else 0
    if not (0.4 <= space_sym <= 1.1):
        return None

    # 守恒被破坏的标志：当前已企稳（缩量 + J 低位）
    k, d, j = _calc_kdj(klines[:index + 1])
    is_stable = today['vol'] < klines[index - 1]['vol'] * 0.7 and j < 20

    if not is_stable:
        return None

    # 对称类型
    sym_type = "直接对称(A杀)" if space_sym >= 0.85 else "间接对称(回调一半)"

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.DUIchen,
        confidence=0.75,
        description=f"对称VA {sym_type} 时{time_sym:.1f}空{space_sym:.1f} J={j:.1f}",
        details={
            'sym_type': sym_type,
            'time_symmetry': round(time_sym, 2),
            'space_symmetry': round(space_sym, 2),
            'up_days': up_days,
            'down_days': down_days,
            'up_pct': round(up_pct * 100, 2),
            'down_pct': round(down_pct * 100, 2),
            'j': j,
        },
        action="BUY",
        stop_loss=trough_price,
        priority=Priority.OPPORTUNITY)


def detect_all_strategies(ts_code: str, days: int = 120) -> List[StrategySignal]:
    """
    检测所有战法信号

    Args:
        ts_code: 股票代码
        days: 分析天数

    Returns:
        战法信号列表
    """
    klines = get_kline_data(ts_code, days)

    if not klines:
        return []

    signals = []

    # ===== 预计算指标序列（避免 daily loop 内重复计算）=====
    daily_klines = _dict_to_daily(klines)

    try:
        from modules.indicators import precompute_kdj_sequence, precompute_bbi_sequence
    except ImportError:
        from indicators import precompute_kdj_sequence, precompute_bbi_sequence

    kdj_sequence = precompute_kdj_sequence(daily_klines)
    bbi_sequence = precompute_bbi_sequence(daily_klines)

    # 临时替换 _calc_kdj / _calc_bbi 为查表版本
    _orig_calc_kdj = globals()['_calc_kdj']
    _orig_calc_bbi = globals()['_calc_bbi']

    def _fast_calc_kdj(klines_slice: List[Dict]) -> Tuple[float, float, float]:
        idx = len(klines_slice) - 1
        return kdj_sequence[idx]

    def _fast_calc_bbi(klines_slice: List[Dict]) -> float:
        idx = len(klines_slice) - 1
        return bbi_sequence[idx]

    globals()['_calc_kdj'] = _fast_calc_kdj
    globals()['_calc_bbi'] = _fast_calc_bbi

    try:
        # 预计算 MACD DIF（供 S2 使用）
        dif_list = _calc_dif(klines)

        # 遍历每一天检测战法
        for i in range(10, len(klines)):
            # B1 检测
            signal = detect_b1(klines, i)
            if signal:
                signals.append(signal)

            # B2 检测
            signal = detect_b2(klines, i)
            if signal:
                signals.append(signal)

            # B3 检测
            signal = detect_b3(klines, i)
            if signal:
                signals.append(signal)

            # 超级B1 检测
            signal = detect_sb1(klines, i)
            if signal:
                signals.append(signal)

            # 长安战法
            signal = detect_changan(klines, i)
            if signal:
                signals.append(signal)

            # 四分之三阴量
            signal = detect_sifen_zhiyi_sanyin(klines, i)
            if signal:
                signals.append(signal)

            # 娜娜图形
            signal = detect_nana(klines, i)
            if signal:
                signals.append(signal)

            # 异动+地量地价
            signal = detect_yidong_dilian(klines, i)
            if signal:
                signals.append(signal)

            # 平行重炮
            signal = detect_pinghang(klines, i)
            if signal:
                signals.append(signal)

            # 坑里起好货
            signal = detect_kengqi(klines, i)
            if signal:
                signals.append(signal)

            # 对称 VA
            signal = detect_duichen_va(klines, i)
            if signal:
                signals.append(signal)

            # S1 逃顶
            signal = detect_s1(klines, i)
            if signal:
                signals.append(signal)

            # S2 确认逃顶（MACD顶背离）
            signal = detect_s2(klines, i, dif_list=dif_list)
            if signal:
                signals.append(signal)

            # S3 最后逃生
            signal = detect_s3(klines, i)
            if signal:
                signals.append(signal)

            # 砖形图信号
            signal = detect_brick_signals(klines, i)
            if signal:
                signals.append(signal)

        # ===== 信号后处理：去重 + 截断 + 排序 =====
        signals = _post_process_signals(signals)

    finally:
        # 恢复原始函数
        globals()['_calc_kdj'] = _orig_calc_kdj
        globals()['_calc_bbi'] = _orig_calc_bbi

    return signals


def _post_process_signals(signals: List[StrategySignal]) -> List[StrategySignal]:
    """
    信号后处理：
    1. 按日期+策略类型去重（同一天同一类型只保留置信度最高的）
    2. 按优先级和日期排序
    3. 截断：最多保留最近30个信号，且每个类型最多保留最近3个
    """
    if not signals:
        return []

    # 1. 去重：同一天同一策略类型，保留置信度最高的
    key_map: Dict[Tuple[str, str], StrategySignal] = {}
    for s in signals:
        key = (s.trade_date, s.strategy.value)
        if key not in key_map or s.confidence > key_map[key].confidence:
            key_map[key] = s

    deduped = list(key_map.values())

    # 2. 按优先级降序、日期降序排序
    deduped.sort(key=lambda x: (x.priority.value, x.confidence, x.trade_date), reverse=True)

    # 3. 截断：每个策略类型最多保留3个最新信号，总体最多30个
    type_counts: Dict[str, int] = {}
    filtered = []
    for s in deduped:
        type_key = s.strategy.value
        if type_counts.get(type_key, 0) >= 3:
            continue
        if len(filtered) >= 30:
            break
        type_counts[type_key] = type_counts.get(type_key, 0) + 1
        filtered.append(s)

    # 最终按日期降序输出（用户看时间线最自然）
    filtered.sort(key=lambda x: x.trade_date, reverse=True)
    return filtered


def detect_s1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 S1 初级逃顶信号

    触发条件：
    1. 近期流畅上涨（20日内涨幅 > 15%，位于高位）
    2. 丑陋大绿帽：放量阴线或假阴真阳，收盘价接近当日低点
    3. 量能异常（放量 > 前日 1.5 倍）
    """
    if index < 20:
        return None

    today = klines[index]

    # 近期高点
    recent_high = max(k['high'] for k in klines[index - 19:index + 1])
    recent_low_20 = min(k['low'] for k in klines[index - 19:index])

    # 流畅上涨条件：20日内涨幅 > 15%
    up_pct = (recent_high - recent_low_20) / recent_low_20
    if up_pct < 0.15:
        return None

    # 当前位于高位（距20日高点 < 10%）
    if today['close'] < recent_high * 0.90:
        return None

    # 丑陋大绿帽：放量阴线 或 假阴真阳
    is_ugly = (
        today['is_fangliang_yinxian'] or
        (today['is_jiayin'] and today['vol'] > klines[index - 1]['vol'] * 1.5)
    )
    if not is_ugly:
        return None

    # 收盘价接近当日低点（绿帽实体大）
    day_range = today['high'] - today['low']
    if day_range > 0:
        close_position = (today['close'] - today['low']) / day_range
    else:
        close_position = 0.5

    if close_position > 0.3:
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.S1,
        confidence=0.85,
        description=f"S1逃顶 20日涨{up_pct*100:.0f}% 放量阴线 收盘距低点{close_position*100:.0f}%",
        details={
            'up_pct': round(up_pct * 100, 2),
            'close_position': round(close_position, 2),
            'vol_ratio': round(today['vol'] / klines[index - 1]['vol'], 2) if klines[index - 1]['vol'] > 0 else 0,
        },
        action="SELL",
        stop_loss=today['low'],
        priority=Priority.CRITICAL)


def detect_s2(klines: List[Dict], index: int,
              dif_list: Optional[List[float]] = None) -> Optional[StrategySignal]:
    """
    检测 S2 确认逃顶信号（MACD顶背离）

    触发条件：
    1. 股价挑战前高（close >= 近期高点 * 0.97）
    2. MACD 顶背离（价格创新高，DIF未创新高）

    dif_list: 可选的外部 MACD DIF 序列，避免重复计算
    """
    if index < 30:
        return None

    today = klines[index]

    # 找前高（过去30天内的最高点，排除最近5天）
    prev_high = max(k['high'] for k in klines[index - 29:index - 4])
    prev_high_idx = next(
        i for i in range(index - 29, index - 4)
        if klines[i]['high'] == prev_high
    )

    # 当前价格接近或超过前高
    if today['close'] < prev_high * 0.97:
        return None

    # 计算 DIF（如果没有外部传入）
    if dif_list is None or len(dif_list) < index + 1:
        dif_list = _calc_dif(klines)

    if not dif_list or len(dif_list) < index + 1:
        return None

    # 顶背离：价格创新高，DIF 未创新高
    current_dif = dif_list[index]
    prev_dif = dif_list[prev_high_idx]

    if today['close'] > klines[prev_high_idx]['close'] and current_dif < prev_dif * 0.98:
        return StrategySignal(
            ts_code=today['ts_code'],
            trade_date=today['trade_date'],
            strategy=StrategyType.S2,
            confidence=0.8,
            description="S2顶背离 价新高DIF未新高",
            details={
                'prev_high': prev_high,
                'prev_high_date': klines[prev_high_idx]['trade_date'],
                'current_dif': round(current_dif, 4),
                'prev_dif': round(prev_dif, 4),
            },
            action="SELL",
            stop_loss=klines[prev_high_idx]['low'],
        priority=Priority.CRITICAL)

    return None


def _calc_dif(klines: List[Dict]) -> List[float]:
    """
    简化版 MACD DIF 计算（用于 S2 顶背离检测）
    EMA12 - EMA26
    """
    if len(klines) < 26:
        return []

    closes = [k['close'] for k in klines]

    def ema(data, period):
        multiplier = 2 / (period + 1)
        result = [data[0]]
        for price in data[1:]:
            result.append(price * multiplier + result[-1] * (1 - multiplier))
        return result

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = [ema12[i] - ema26[i] for i in range(len(closes))]
    return dif


def detect_s3(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 S3 最后逃生信号（简化版）

    触发条件：
    1. 之前有 S1 或高位放量阴线
    2. 近期反弹到 S1 高点下沿但量能不足
    3. 无法突破，出现滞涨
    """
    if index < 15:
        return None

    today = klines[index]

    # 找近期 S1 或放量阴线的位置（过去15天内）
    s1_index = None
    for i in range(index - 14, index):
        if klines[i].get('is_fangliang_yinxian', False) and klines[i]['close'] < klines[i]['open']:
            s1_index = i
            break

    if s1_index is None:
        return None

    s1_high = klines[s1_index]['high']
    s1_open = klines[s1_index]['open']

    # 当前价格反弹到 S1 开盘价附近但未能突破 S1 高点
    if not (s1_open * 0.95 <= today['close'] <= s1_high * 1.02):
        return None

    # 反弹量能不足（小于 S1 当天量能的 70%）
    if today['vol'] > klines[s1_index]['vol'] * 0.7:
        return None

    # 当日涨幅受限（< 2%）
    if today['pct_chg'] > 2:
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.S3,
        confidence=0.7,
        description=f"S3最后逃生 反弹至S1下沿 量能不足",
        details={
            's1_date': klines[s1_index]['trade_date'],
            's1_high': s1_high,
            'rebound_pct': round((today['close'] - klines[s1_index]['close']) / klines[s1_index]['close'] * 100, 2),
            'vol_ratio': round(today['vol'] / klines[s1_index]['vol'], 2),
        },
        action="SELL",
        stop_loss=klines[s1_index]['low'],
        priority=Priority.CRITICAL)


def detect_brick_signals(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测砖形图信号

    基于四块砖交易体系，检测状态变化点：
    - 红砖翻绿 → 止损 (BRICK_EXIT)
    - 红砖满4块 → 减仓 (BRICK_REDUCE)
    - 绿砖满4块 → 可能止跌观察 (BRICK_BOUNCE)

    只在状态变化当天触发，避免连续多天重复信号。
    """
    if index < 11:
        return None

    today = klines[index]

    # 转换为 DailyData 并检测今天状态
    daily_list = _klines_dict_to_daily(klines[:index + 1])
    brick_today = detect_four_brick_system(daily_list)

    # 只关注重要操作状态
    action_today = brick_today.get('brick_action', '观望')
    if action_today in ('观望', '持有'):
        return None

    # 检测昨天状态（用于判断是否为状态变化首日）
    daily_yesterday = _klines_dict_to_daily(klines[:index])
    brick_yesterday = detect_four_brick_system(daily_yesterday)
    action_yesterday = brick_yesterday.get('brick_action', '观望')

    # 如果昨天已经是同样的重要状态，说明不是首日，不重复触发
    if action_yesterday == action_today:
        return None

    # 映射到 StrategyType
    strategy_map = {
        '止损': (StrategyType.BRICK_EXIT, 'SELL', 0.85, Priority.CRITICAL),
        '减仓': (StrategyType.BRICK_REDUCE, 'SELL', 0.75, Priority.OBSERVE),
        '禁止抄底': (StrategyType.BRICK_BOUNCE, 'WATCH', 0.7, Priority.OBSERVE),
    }

    if action_today not in strategy_map:
        return None

    strategy_type, action, confidence, priority = strategy_map[action_today]

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=strategy_type,
        confidence=confidence,
        description=brick_today.get('brick_action_desc', action_today),
        details={
            'brick_consecutive': brick_today.get('brick_consecutive', 0),
            'is_brick_flip_green': brick_today.get('is_brick_flip_green', False),
            'prev_action': action_yesterday,
            'current_action': action_today,
        },
        action=action,
        stop_loss=today['low'],
        priority=priority,
    )


def analyze_kirin_phase(klines: List[Dict]) -> Dict[str, Any]:
    """
    分析麒麟会四阶段（吸→拉→派→落）

    基于最近 30 天量价特征判断当前最可能阶段
    """
    if len(klines) < 30:
        return {"phase": "UNKNOWN", "confidence": 0}

    recent = klines[-30:]
    closes = [k['close'] for k in recent]
    vols = [k['vol'] for k in recent]
    avg_vol = sum(vols) / len(vols)

    # 1. 趋势方向
    first_half = closes[:15]
    second_half = closes[15:]
    trend = "UP" if second_half[-1] > first_half[0] else "DOWN"

    # 2. 量价关系
    red_vol = sum(k['vol'] for k in recent if k['is_rise'])
    green_vol = sum(k['vol'] for k in recent if not k['is_rise'])
    red_days = sum(1 for k in recent if k['is_rise'])
    green_days = 30 - red_days

    red_avg = red_vol / red_days if red_days > 0 else 0
    green_avg = green_vol / green_days if green_days > 0 else 0

    # 3. 阶段判定
    phase = "UNKNOWN"
    confidence = 0.5

    # 吸筹：低位、缩量震荡、红肥绿瘦（阳线量能 > 阴线）
    is_low = min(closes) <= max(closes) * 0.85
    is_shrink = avg_vol < sum(klines[i]['vol'] for i in range(-60, -30)) / 30 if len(klines) >= 60 else False
    if is_low and red_avg > green_avg * 1.2:
        phase = "吸筹"
        confidence = 0.75

    # 拉升：放量、连续上涨、趋势向上
    up_days = sum(1 for i in range(1, len(recent)) if recent[i]['close'] > recent[i-1]['close'])
    if trend == "UP" and avg_vol > (sum(klines[i]['vol'] for i in range(-60, -30)) / 30 if len(klines) >= 60 else avg_vol) * 1.3 and up_days >= 18:
        phase = "拉升"
        confidence = 0.8

    # 派发：高位、放量滞涨、绿肥红瘦
    is_high = closes[-1] >= max(closes[:20]) * 0.95
    if is_high and green_avg > red_avg * 1.1 and abs(closes[-1] - closes[0]) / closes[0] < 0.05:
        phase = "派发"
        confidence = 0.75

    # 回落：缩量下跌、无承接
    if trend == "DOWN" and avg_vol < (sum(klines[i]['vol'] for i in range(-60, -30)) / 30 if len(klines) >= 60 else avg_vol) * 0.8 and up_days < 10:
        phase = "回落"
        confidence = 0.7

    phase_map = {
        "吸筹": StrategyType.XISHOU,
        "拉升": StrategyType.LASHENG,
        "派发": StrategyType.PAIFA,
        "回落": StrategyType.LUOLUO,
        "UNKNOWN": None,
    }

    return {
        "phase": phase,
        "confidence": confidence,
        "strategy_type": phase_map.get(phase),
        "trend": trend,
        "red_avg_vol": round(red_avg, 2),
        "green_avg_vol": round(green_avg, 2),
        "avg_vol": round(avg_vol, 2),
    }


def get_latest_signal(ts_code: str, days: int = 120) -> Optional[StrategySignal]:
    """
    获取最新战法信号

    Args:
        ts_code: 股票代码
        days: 分析天数

    Returns:
        最新战法信号
    """
    signals = detect_all_strategies(ts_code, days)
    return signals[0] if signals else None


def format_signal(signal: StrategySignal) -> str:
    """格式化输出信号"""
    action_emoji = {
        'BUY': '[买入]',
        'SELL': '[卖出]',
        'HOLD': '[持有]',
        'WATCH': '[观望]',
    }

    return f"""
{'='*60}
{signal.strategy.value} 信号
{'='*60}
股票: {signal.ts_code}
日期: {signal.trade_date}
置信度: {signal.confidence*100:.0f}%
描述: {signal.description}

交易建议: {action_emoji.get(signal.action, signal.action)}
{f'目标价: {signal.target_price:.2f}' if signal.target_price else ''}
{f'止损价: {signal.stop_loss:.2f}' if signal.stop_loss else ''}

详细: {signal.details}
{'='*60}
"""


def analyze_with_strategies(ts_code: str, days: int = 120) -> Dict[str, Any]:
    """
    综合战法分析

    Returns:
        分析结果字典
    """
    signals = detect_all_strategies(ts_code, days)

    # 按战法类型分组统计
    strategy_stats = {}
    for s in signals:
        name = s.strategy.value
        if name not in strategy_stats:
            strategy_stats[name] = {
                'count': 0,
                'signals': []
            }
        strategy_stats[name]['count'] += 1
        strategy_stats[name]['signals'].append(s)

    # 最新信号
    latest = signals[0] if signals else None

    return {
        'ts_code': ts_code,
        'total_signals': len(signals),
        'strategy_stats': strategy_stats,
        'latest_signal': latest,
        'all_signals': signals[:20],  # 最近20个信号
    }


# ==================== 命令行工具 ====================

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Z哥 战法识别")
    parser.add_argument("ts_code", help="股票代码，如 000001.SZ")
    parser.add_argument("--days", type=int, default=120, help="分析天数")
    parser.add_argument("--latest", action="store_true", help="只看最新信号")

    args = parser.parse_args()

    if args.latest:
        signal = get_latest_signal(args.ts_code, args.days)
        if signal:
            print(format_signal(signal))
        else:
            print(f"{args.ts_code}: 近期无战法信号")
    else:
        result = analyze_with_strategies(args.ts_code, args.days)

        print(f"{'='*60}")
        print(f"股票: {result['ts_code']} 战法分析")
        print(f"{'='*60}")
        print(f"总信号数: {result['total_signals']}")

        print("\n各战法统计:")
        for name, stats in result['strategy_stats'].items():
            print(f"  {name}: {stats['count']}次")

        print("\n最近信号:")
        for s in result['all_signals'][:10]:
            print(f"  {s.trade_date} {s.strategy.value} {s.action} {s.description}")


if __name__ == "__main__":
    main()

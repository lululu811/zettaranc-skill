import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ..indicators import DailyData

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

    # 观察/提示
    WATCH = "观察"                # 阶段判断、提示信号

    # 砖形图信号
    BRICK_EXIT = "四块砖翻绿"      # 红砖翻绿 → 止损
    BRICK_REDUCE = "四块砖减仓"    # 红砖满4块 → 减仓一半
    BRICK_BOUNCE = "四块砖反弹"    # 绿砖满4块 → 可能止跌，观察B1

class Priority(Enum):
    """信号优先级"""
    CRITICAL = 3     # 紧急：止损、逃顶
    OPPORTUNITY = 2  # 机会：买点、战法
    OBSERVE = 1      # 观察：提示、减仓、阶段判断

class Action(Enum):
    """交易建议"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"

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

    # 扩展字段（部分策略使用）
    price: Optional[float] = None    # 信号产生时的价格
    reason: Optional[str] = None    # 信号原因说明

    # 信号优先级（由策略检测函数自动填入）
    priority: Priority = Priority.OBSERVE

def _resolve_db_path() -> Path:
    """动态解析数据库路径"""
    path_str = os.getenv("DB_PATH", "data/stock_data.db")
    path = Path(path_str)
    if not path.is_absolute():
        path = (Path(__file__).parent.parent.parent / path_str).resolve()
    return path

def get_db_connection() -> sqlite3.Connection:
    """获取数据库连接（动态读取 DB_PATH 环境变量）"""
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_kline_data(ts_code: str, days: int = 120) -> List[Dict]:
    """
    获取K线数据，并关联指标缓存与资金流数据
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 联表查询：K线 + 指标缓存(Bollinger/RSI/DMI) + 资金流
    cursor.execute("""
        SELECT 
            k.ts_code, k.trade_date, k.open, k.high, k.low, k.close, k.vol, k.amount, k.pct_chg,
            i.boll_upper, i.boll_mid, i.boll_lower, i.rsi6, i.adx, i.dmi_plus, i.dmi_minus,
            m.buy_lg_amount, m.buy_elg_amount, m.sell_lg_amount, m.sell_elg_amount, m.net_mf
        FROM daily_kline k
        LEFT JOIN indicator_cache i ON k.ts_code = i.ts_code AND k.trade_date = i.trade_date
        LEFT JOIN moneyflow m ON k.ts_code = m.ts_code AND k.trade_date = m.trade_date
        WHERE k.ts_code = ?
        ORDER BY k.trade_date ASC
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
            'is_rise': row['close'] > prev_close,
            'is_beidou': row['vol'] >= prev_vol * 2,
            'is_suoliang': row['vol'] <= prev_vol * 0.5,
            'is_jiayin': row['close'] < row['open'] and row['close'] > prev_close,
            'is_yinxian': row['close'] < prev_close,
            'is_fangliang_yinxian': row['close'] < prev_close and row['vol'] > prev_vol * 1.5,

            # MDC 扩展字段（LEFT JOIN 可能为 NULL，统一 fallback）
            'boll_upper': row['boll_upper'] or 0,
            'boll_mid': row['boll_mid'] or 0,
            'boll_lower': row['boll_lower'] or 0,
            'rsi6': row['rsi6'] or 0,
            'adx': row['adx'] or 0,
            'dmi_plus': row['dmi_plus'] or 0,
            'dmi_minus': row['dmi_minus'] or 0,
            'net_mf': row['net_mf'] or 0,
            'large_inflow': (row['buy_lg_amount'] or 0) + (row['buy_elg_amount'] or 0),
            'large_outflow': (row['sell_lg_amount'] or 0) + (row['sell_elg_amount'] or 0),
        })

    return data_list

def _dict_to_daily(klines: List[Dict]) -> List[Any]:
    """将 Dict K 线列表转换为 indicators.DailyData"""
    from ..indicators import DailyData
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
    from ..indicators import calculate_kdj
    daily = _dict_to_daily(klines)
    return calculate_kdj(daily)

def _calc_bbi(klines: List[Dict]) -> float:
    """通过 indicators.py 计算 BBI"""
    from ..indicators import calculate_bbi
    daily = _dict_to_daily(klines)
    return calculate_bbi(daily)

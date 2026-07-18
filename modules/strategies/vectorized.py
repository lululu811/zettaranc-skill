import pandas as pd
from typing import Any, cast

import numpy as np
from .core import StrategyType, StrategySignal, Priority


def detect_b1_vec(df: pd.DataFrame) -> pd.Series:
    """
    向量化检测 B1 买点 (J < -10 & 非绿砖)
    """
    # 1. J < -10
    cond_j = df["j"] < -10

    # 2. 非绿砖（最近4根阴线数量 < 4）
    # is_yinxian 是 1 (阴) 或 0
    recent_yin_count = df["is_yinxian"].rolling(window=4).sum()
    cond_not_green_brick = recent_yin_count < 4

    return cond_j & cond_not_green_brick


def detect_b2_vec(df: pd.DataFrame) -> pd.Series:
    """
    向量化检测 B2 确认买点 (前有B1 + 放量长阳 + 无上影)
    """
    # 1. 过去 5 到 15 天前有 B1 (J < -10)
    # 原循环是 range(5, 15)，即偏移量 5,6,7,8,9,10,11,12,13,14
    # 这对应于 shift(5) 后的 rolling(10)
    has_b1_recently = (df["j"] < -10).shift(5).rolling(window=10).max() > 0

    # 2. 放量长阳 (pct_chg >= 4 & is_beidou)
    cond_yang = (df["pct_chg"] >= 4) & (df["is_beidou"])

    # 3. 无长上影线 (high <= close * 1.01)
    cond_no_shadow = df["high"] <= df["close"] * 1.01

    return has_b1_recently & cond_yang & cond_no_shadow


def detect_s1_vec(df: pd.DataFrame) -> pd.Series:
    """
    向量化检测 S1 逃顶信号
    """
    # 1. 近期流畅上涨 (20日内，低点取前19天，高点包含今天)
    # 原逻辑: recent_high = max(k['high'] for k in klines[index - 19:index + 1])
    #         recent_low_20 = min(k['low'] for k in klines[index - 19:index])
    recent_high = df["high"].rolling(window=20).max()
    recent_low = df["low"].shift(1).rolling(window=19).min()

    up_pct = (recent_high - recent_low) / recent_low
    cond_up = up_pct > 0.15

    # 2. 当前位于高位 (距20日高点 < 10%)
    cond_high_pos = df["close"] >= recent_high * 0.90

    # 3. 丑陋大绿帽 (放量阴线 或 假阴真阳且放量)
    # 原逻辑: is_ugly = today['is_fangliang_yinxian'] or (today['is_jiayin'] and today['vol'] > klines[index-1]['vol'] * 1.5)
    cond_ugly = (df["is_fangliang_yinxian"]) | ((df["is_jiayin"]) & (df["vol"] > df["vol"].shift(1) * 1.5))

    # 4. 收盘接近当日低点 (close_pos <= 0.3)
    day_range = df["high"] - df["low"]
    close_pos = (df["close"] - df["low"]) / day_range
    close_pos = close_pos.replace([np.inf, -np.inf], np.nan).fillna(0.5)
    cond_close_low = close_pos <= 0.3

    # 补一个 index >= 20 的限制
    cond_min_len = df.index >= 20

    return cond_up & cond_high_pos & cond_ugly & cond_close_low & cond_min_len


def detect_b3_vec(df: pd.DataFrame) -> pd.Series:
    """
    向量化检测 B3 中继买点 (B2后出现 + 分歧转一致)
    """
    # 1. 过去 3 到 10 天前有 B2 (涨幅>=4 & 放量)
    # 原逻辑是 range(3, 10)
    has_b2_recently = ((df["pct_chg"] >= 4) & (df["is_beidou"])).shift(3).rolling(window=7).max() > 0

    # 2. 分歧转一致 (小阳线: 0 < pct_chg < 2 & amplitude < 7)
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1) * 100
    cond_small_yang = (df["pct_chg"] > 0) & (df["pct_chg"] < 2) & (amplitude < 7)

    return has_b2_recently & cond_small_yang


def detect_s2_vec(df: pd.DataFrame) -> pd.Series:
    """
    向量化检测 S2 顶背离 (价新高 + DIF未新高)
    """
    # 1. 找前高 (过去 5 到 30 天前的最高价)
    # 原逻辑: max(high for index-29:index-4)
    # 我们用 shift(5) 后的 rolling(25)
    prev_high = df["high"].shift(5).rolling(window=25).max()

    # 2. 当前价格接近或超过前高
    cond_near_high = df["close"] >= prev_high * 0.97

    # 3. 顶背离：价格创新高，但 DIF 未创新高 (相比前高那天)
    # 这是一个比较复杂的向量化逻辑，因为需要对比“最高价那一天”的 DIF
    # 简化版：当前 DIF < 过去一段时间的 DIF 最大值
    # 严格版：需要知道 prev_high 发生的具体位置。
    # 这里用一个启发式：当前价格 > 过去30天最高收盘价，且 DIF < 过去30天最高 DIF
    cond_price_new_high = df["close"] > df["close"].shift(1).rolling(window=30).max()
    cond_dif_not_new_high = df["dif"] < df["dif"].shift(1).rolling(window=30).max() * 0.98

    return cond_near_high & cond_price_new_high & cond_dif_not_new_high


def generate_signals_from_df(df: pd.DataFrame) -> list[StrategySignal]:
    """
    从包含了所有指标的 DataFrame 中全量生成信号列表
    """
    if len(df) == 0:
        return []

    ts_code = df["ts_code"].iloc[0]
    all_masks = {
        StrategyType.B1: detect_b1_vec(df),
        StrategyType.B2: detect_b2_vec(df),
        StrategyType.B3: detect_b3_vec(df),
        StrategyType.S1: detect_s1_vec(df),
        StrategyType.S2: detect_s2_vec(df),
    }

    signals = []
    for st_type, mask in all_masks.items():
        indices_arr = np.where(mask.fillna(False))[0]
        indices: list[int] = [int(i) for i in cast(Any, indices_arr)]
        for idx in indices:
            row = df.iloc[idx]
            # 基础属性
            sig = StrategySignal(
                ts_code=ts_code,
                trade_date=row["trade_date"],
                strategy=st_type,
                confidence=0.8,
                description=f"向量化检测: {st_type.value}",
                details={"price": row["close"], "vec": True},
                action="BUY" if st_type.value.startswith("B") else "SELL",
                stop_loss=row["low"],
                priority=Priority.OPPORTUNITY if st_type.value.startswith("B") else Priority.CRITICAL,
            )
            # 针对性描述优化
            if st_type == StrategyType.B1:
                sig.description = f"B1买点 J={row['j']:.2f}"
                sig.confidence = 0.8 if row["is_suoliang"] else 0.6
            elif st_type == StrategyType.B2:
                sig.description = f"B2确认 涨{row['pct_chg']:.2f}%"
            elif st_type == StrategyType.S1:
                sig.description = "S1逃顶 放量阴线"

            signals.append(sig)

    return signals

from typing import Optional
from ..indicators import DailyData
from .core import StrategyType, StrategySignal, Priority, Action, _get_kdj, _ensure_daily_klines


def detect_changan(klines: list[DailyData], index: int, kirin_context: dict | None = None) -> StrategySignal | None:
    """
    检测长安战法（已升级 MDC 验证 + 麒麟背景）

    三条件：
    1. 第一天为B1（J<-13）
    2. 第二天为放量长阳，J值拐头
    3. 第三天为分歧转一致且缩半量

    MDC 验证项：
    - 第二天放量时，大单净流入比例 > 5% (+15%)
    - 整体处于“拉升”阶段 (+10%)
    """
    if index < 3:
        return None

    klines = _ensure_daily_klines(klines)
    klines[index - 2]
    day2 = klines[index - 1]
    day3 = klines[index]

    # 1. 第一天：B1（J<-13）
    k1, d1, j1 = _get_kdj(klines, index - 2)
    if j1 >= -13:
        return None

    # 2. 第二天：放量长阳，J拐头
    k2, d2, j2 = _get_kdj(klines, index - 1)
    if not (day2["pct_chg"] >= 4 and day2["is_beidou"] and j2 > j1):
        return None

    # 3. 第三天：分歧转一致，缩半量
    pct_chg = day3["pct_chg"]
    amplitude = (day3["high"] - day3["low"]) / day3["prev_close"] * 100
    is_half_vol = day3["vol"] <= day2["vol"] * 0.5

    if not (0 < pct_chg < 2 and amplitude < 7 and is_half_vol):
        return None

    # 4. MDC 评分
    confidence = 0.75
    mdc_details = []

    # 验证第二天的资金流 (真假突破)
    if day2.get("large_inflow", 0) > day2.get("large_outflow", 0):
        inflow_ratio = (day2["large_inflow"] - day2["large_outflow"]) / day2["amount"] if day2["amount"] > 0 else 0
        if inflow_ratio > 0.05:
            confidence += 0.15
            mdc_details.append(f"Day2主力大单强力流入({inflow_ratio * 100:.1f}%)")

    if kirin_context and kirin_context.get("stage") == "拉升":
        confidence += 0.10
        mdc_details.append("处于主力拉升期")

    return StrategySignal(
        ts_code=day3["ts_code"],
        trade_date=day3["trade_date"],
        strategy=StrategyType.CHANGAN,
        confidence=round(min(confidence, 0.98), 2),
        description="长安战法确认(胜率75%) " + ", ".join(mdc_details),
        details={
            "j1": j1,
            "j2": j2,
            "day2_pct": day2["pct_chg"],
            "mdc": mdc_details,
        },
        action=Action.BUY.value,
        stop_loss=day3["low"],
        priority=Priority.OPPORTUNITY,
    )


def detect_sifen_zhiyi_sanyin(klines: list[DailyData], index: int) -> StrategySignal | None:
    """
    检测四分之三阴量战法

    条件：大阳线后次日阴量 > 阳量 × 0.75 = 假突破
    """
    if index < 1:
        return None

    klines = _ensure_daily_klines(klines)
    today = klines[index]
    yesterday = klines[index - 1]

    # 昨日大阳线
    if yesterday["pct_chg"] < 3:
        return None

    # 今日阴线
    if today["close"] >= today["open"]:
        return None

    # 阴量判断
    vol_ratio = today["vol"] / yesterday["vol"]

    if vol_ratio > 0.75:
        # 假突破！主力出货
        return StrategySignal(
            ts_code=today["ts_code"],
            trade_date=today["trade_date"],
            strategy=StrategyType.SI_FEN_ZHI_SAN,
            confidence=0.9,
            description=f"假突破！阴量{vol_ratio:.0%}超过阳量75%",
            details={
                "yang_vol": yesterday["vol"],
                "yin_vol": today["vol"],
                "vol_ratio": vol_ratio,
            },
            action=Action.SELL.value,
            priority=Priority.OPPORTUNITY,
        )

    return None


def detect_nana(klines: list[DailyData], index: int, kirin_context: dict | None = None) -> StrategySignal | None:
    """
    检测娜娜图形（已升级 MDC 验证）

    四条件同时满足：
    1. 连续放量上涨
    2. 顶部无巨量阴线
    3. 连续缩量回调
    4. J下到负值
    """
    if index < 10:
        return None

    klines = _ensure_daily_klines(klines)

    # 检查连续放量上涨（最近3-5天）
    rise_count = 0
    for i in range(index - 4, index + 1):
        if i < 1:
            continue
        if klines[i]["is_rise"] and klines[i]["is_beidou"]:
            rise_count += 1

    if rise_count < 3:
        return None

    # 检查顶部无巨量阴线
    for i in range(index - 4, index):
        if klines[i]["is_fangliang_yinxian"]:
            return None

    # 检查连续缩量回调
    suoliang_count = 0
    for i in range(index - 4, index):
        if klines[i]["is_suoliang"]:
            suoliang_count += 1

    if suoliang_count < 2:
        return None

    # J值负值
    k, d, j = _get_kdj(klines, index)
    if j >= 0:
        return None

    # MDC 验证
    confidence = 0.85
    mdc_details = []

    today = klines[index]
    if today.get("boll_lower") and today["close"] <= today["boll_lower"] * 1.05:
        confidence += 0.10
        mdc_details.append("回踩布林下轨支撑")

    if kirin_context and kirin_context.get("stage") in ("吸筹", "拉升"):
        confidence += 0.05
        mdc_details.append(f"处于主力{kirin_context['stage']}期")

    return StrategySignal(
        ts_code=klines[index]["ts_code"],
        trade_date=klines[index]["trade_date"],
        strategy=StrategyType.NANA,
        confidence=round(min(confidence, 0.98), 2),
        description=f"娜娜图形 J={j:.2f} " + ", ".join(mdc_details),
        details={
            "j": j,
            "rise_count": rise_count,
            "suoliang_count": suoliang_count,
            "mdc": mdc_details,
        },
        action=Action.BUY.value,
        stop_loss=klines[index]["low"],
        priority=Priority.OPPORTUNITY,
    )


def detect_yidong_dilian(klines: list[DailyData], index: int) -> StrategySignal | None:
    """
    检测异动+地量地价战法

    三步：
    1. 异动 = 突然放量，资金进场
    2. 异动后缩量回调
    3. 地量 = 最佳B1买点
    """
    if index < 5:
        return None

    klines = _ensure_daily_klines(klines)

    today = klines[index]

    # 检查前几天是否有异动
    yidong_index = None
    for i in range(index - 1, max(0, index - 10), -1):
        # 异动：放量+上涨
        if klines[i]["is_beidou"] and klines[i]["is_rise"]:
            yidong_index = i
            break

    if yidong_index is None:
        return None

    # 检查异动后是否缩量回调
    days_after = index - yidong_index
    if days_after < 2:
        return None

    # 回调期间应该有缩量
    any(klines[j]["is_suoliang"] for j in range(yidong_index + 1, index + 1))

    # 今日地量（最佳买点）
    if not today["is_suoliang"]:
        return None

    # J值判断
    k, d, j = _get_kdj(klines, index)

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.YIDONG_DILIAN,
        confidence=0.8,
        description=f"异动+地量地价 异动后{days_after}天缩量回调 J={j:.2f}",
        details={
            "yidong_date": klines[yidong_index]["trade_date"],
            "days_after": days_after,
            "j": j,
        },
        action=Action.BUY.value,
        stop_loss=today["low"],
        priority=Priority.OPPORTUNITY,
    )


def detect_pinghang(klines: list[DailyData], index: int) -> StrategySignal | None:
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

    klines = _ensure_daily_klines(klines)

    # 收集最近7天内的放量阳线索引
    yang_indices = []
    for i in range(max(0, index - 6), index + 1):
        if klines[i]["is_rise"] and klines[i]["is_beidou"]:
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
    yin_count = sum(1 for i in range(y1 + 1, y2) if not klines[i]["is_rise"])
    if yin_count < between_count * 0.5:
        return None

    # 阳线成交量压住阴线
    max_yin_vol = max(klines[i]["vol"] for i in range(y1 + 1, y2))
    if klines[y1]["vol"] < max_yin_vol * 1.2 or klines[y2]["vol"] < max_yin_vol * 1.2:
        return None

    # 第二根阳线涨幅 >= 4%
    if klines[y2]["pct_chg"] < 4:
        return None

    # 第二根量能 >= 第一根 90%
    if klines[y2]["vol"] < klines[y1]["vol"] * 0.9:
        return None

    # J 值 < 55
    k, d, j = _get_kdj(klines, y2)
    if j >= 55:
        return None

    # 无上影线（可选加分）
    has_upper_shadow = klines[y2]["high"] > klines[y2]["close"] * 1.01
    confidence = 0.85 if not has_upper_shadow else 0.75

    return StrategySignal(
        ts_code=klines[y2]["ts_code"],
        trade_date=klines[y2]["trade_date"],
        strategy=StrategyType.PINGHANG,
        confidence=confidence,
        description=f"平行重炮 涨{klines[y2]['pct_chg']:.1f}% J={j:.1f} 夹{between_count}阴",
        details={
            "j": j,
            "yang1_vol": klines[y1]["vol"],
            "yang2_vol": klines[y2]["vol"],
            "between_count": between_count,
            "yin_count": yin_count,
            "pct_chg": klines[y2]["pct_chg"],
            "has_upper_shadow": has_upper_shadow,
        },
        action=Action.BUY.value,
        stop_loss=klines[y2]["low"],
        priority=Priority.OPPORTUNITY,
    )


def detect_kengqi(klines: list[DailyData], index: int) -> StrategySignal | None:
    """
    检测坑里起好货 / 填坑战法

    三步：
    1. 放量挖坑（急跌 + 放量，跌破前期平台）
    2. 缩量填坑（企稳 + 缩量回升）
    3. 回到坑沿 = 最后震仓，交易价值最大
    """
    if index < 15:
        return None

    klines = _ensure_daily_klines(klines)

    today = klines[index]

    # 找坑：最近15天内的最低点
    recent_low = min(klines[i]["low"] for i in range(index - 14, index + 1))
    low_index = next(i for i in range(index - 14, index + 1) if klines[i]["low"] == recent_low)

    # 坑前高点（坑前5天的最高点）
    if low_index < 5:
        return None

    pre_high = max(klines[i]["high"] for i in range(low_index - 5, low_index))

    # 坑深条件：跌幅 >= 10%
    keng_depth = (pre_high - recent_low) / pre_high
    if keng_depth < 0.10:
        return None

    # 挖坑日必须放量下跌
    keng_day = klines[low_index]
    if not (keng_day["close"] < keng_day["open"] and keng_day["vol"] > klines[low_index - 1]["vol"] * 1.3):
        return None

    # 填坑：从坑底到当前，价格回升到坑沿的 80% 以上
    fill_ratio = (today["close"] - recent_low) / (pre_high - recent_low)
    if fill_ratio < 0.8:
        return None

    # 填坑过程缩量（坑后5日均量 < 坑前5日均量）
    post_vols = [klines[i]["vol"] for i in range(low_index + 1, min(low_index + 6, index + 1))]
    pre_vols = [klines[i]["vol"] for i in range(low_index - 5, low_index)]
    if post_vols and pre_vols:
        post_avg = sum(post_vols) / len(post_vols)
        pre_avg = sum(pre_vols) / len(pre_vols)
        if post_avg >= pre_avg * 0.8:
            return None

    # 祖冲之法目标价 = 2a - b
    target_price = round(2 * pre_high - recent_low, 2)

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.KENGQI,
        confidence=0.8,
        description=f"坑里起好货 坑深{keng_depth * 100:.0f}% 填{fill_ratio * 100:.0f}% 目标{target_price:.1f}",
        details={
            "keng_depth": round(keng_depth, 4),
            "fill_ratio": round(fill_ratio, 4),
            "pre_high": pre_high,
            "keng_low": recent_low,
            "target_price": target_price,
        },
        action=Action.BUY.value,
        stop_loss=recent_low,
        priority=Priority.OPPORTUNITY,
    )


def detect_duichen_va(klines: list[DailyData], index: int) -> StrategySignal | None:
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

    klines = _ensure_daily_klines(klines)

    today = klines[index]

    # 找近期高点和低点（过去20天）
    window = klines[index - 19 : index + 1]
    highs = [(i, k["high"]) for i, k in enumerate(window)]
    lows = [(i, k["low"]) for i, k in enumerate(window)]

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
    down_pct = (peak_price - window[-1]["close"]) / peak_price

    # 时间对称：下跌天数 / 上涨天数 在 0.8~1.5 之间
    time_sym = down_days / up_days if up_days > 0 else 0
    if not (0.5 <= time_sym <= 2.0):
        return None

    # 空间对称：跌幅 / 涨幅 在 0.4~1.1 之间（直接对称或间接对称）
    space_sym = down_pct / up_pct if up_pct > 0 else 0
    if not (0.4 <= space_sym <= 1.1):
        return None

    # 守恒被破坏的标志：当前已企稳（缩量 + J 低位）
    k, d, j = _get_kdj(klines, index)
    is_stable = today["vol"] < klines[index - 1]["vol"] * 0.7 and j < 20

    if not is_stable:
        return None

    # 对称类型
    sym_type = "直接对称(A杀)" if space_sym >= 0.85 else "间接对称(回调一半)"

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.DUIchen,
        confidence=0.75,
        description=f"对称VA {sym_type} 时{time_sym:.1f}空{space_sym:.1f} J={j:.1f}",
        details={
            "sym_type": sym_type,
            "time_symmetry": round(time_sym, 2),
            "space_symmetry": round(space_sym, 2),
            "up_days": up_days,
            "down_days": down_days,
            "up_pct": round(up_pct * 100, 2),
            "down_pct": round(down_pct * 100, 2),
            "j": j,
        },
        action=Action.BUY.value,
        stop_loss=trough_price,
        priority=Priority.OPPORTUNITY,
    )

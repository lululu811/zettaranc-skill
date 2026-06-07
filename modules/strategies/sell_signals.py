from typing import Optional
from .core import StrategyType, StrategySignal, Priority, _klines_dict_to_daily
from ..indicators import detect_four_brick_system


def detect_s1(klines: list[dict], index: int, kirin_context: dict | None = None) -> StrategySignal | None:
    """
    检测 S1 初级逃顶信号（已升级 MDC 验证 + 麒麟阶段背景）

    核心触发：
    1. 近期流畅上涨（20日内涨幅 > 15%，位于高位）
    2. 丑陋大绿帽：放量阴线或假阴真阳
    3. 收盘价接近当日低点

    MDC 验证项：
    - 处于麒麟会“派发”阶段 (+20%)
    - 主力大单大幅净流出 (+15%)
    - 跌破布林中轨 (-10%)
    """
    if index < 20:
        return None

    today = klines[index]
    yesterday = klines[index - 1]

    # 1. 流畅上涨与高位判断
    recent_high = max(k["high"] for k in klines[index - 19 : index + 1])
    recent_low_20 = min(k["low"] for k in klines[index - 19 : index])
    up_pct = (recent_high - recent_low_20) / recent_low_20

    if up_pct < 0.15:
        return None
    if today["close"] < recent_high * 0.90:
        return None

    # 2. 丑陋大绿帽形态
    is_ugly = today["is_fangliang_yinxian"] or (today["is_jiayin"] and today["vol"] > yesterday["vol"] * 1.5)
    if not is_ugly:
        return None

    day_range = today["high"] - today["low"]
    close_position = (today["close"] - today["low"]) / day_range if day_range > 0 else 0.5
    if close_position > 0.3:
        return None

    # 3. MDC 评分升级
    confidence = 0.60
    mdc_details = []

    # 麒麟阶段背景验证
    if kirin_context:
        stage = kirin_context.get("stage")
        if stage == "派发":
            confidence += 0.25
            mdc_details.append("处于主力派发期(高危)")
        elif stage == "拉升":
            confidence -= 0.10  # 拉升期的第一次大阴线可能是洗盘
            mdc_details.append("处于拉升中继(警惕洗盘)")

    # 资金流验证
    outflow_ratio = (
        (today.get("large_outflow", 0) - today.get("large_inflow", 0)) / today["amount"] if today["amount"] > 0 else 0
    )
    if outflow_ratio > 0.05:
        confidence += 0.15
        mdc_details.append(f"主力大单强力撤离({outflow_ratio * 100:.1f}%)")

    # 布林验证
    if today.get("boll_mid") and yesterday["close"] > yesterday["boll_mid"] and today["close"] < today["boll_mid"]:
        confidence += 0.10
        mdc_details.append("跌破布林中轨(趋势走坏)")

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.S1,
        confidence=round(min(max(confidence, 0.1), 0.98), 2),
        description="S1逃顶(丑陋大绿帽) " + ", ".join(mdc_details),
        details={
            "up_pct": round(up_pct * 100, 2),
            "close_position": round(close_position, 2),
            "mdc": mdc_details,
            "kirin_stage": kirin_context.get("stage") if kirin_context else None,
        },
        action="SELL",
        stop_loss=today["low"],
        priority=Priority.CRITICAL,
    )


def _calc_dif(klines: list[dict]) -> list[float]:
    """
    简化版 MACD DIF 计算（用于 S2 顶背离检测）
    EMA12 - EMA26
    """
    if len(klines) < 26:
        return []

    closes = [k["close"] for k in klines]

    def ema(data: list[float], period: int) -> list[float]:
        multiplier = 2 / (period + 1)
        result = [data[0]]
        for price in data[1:]:
            result.append(price * multiplier + result[-1] * (1 - multiplier))
        return result

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = [ema12[i] - ema26[i] for i in range(len(closes))]
    return dif


def detect_s2(klines: list[dict] | None, index: int, dif_list: list[float] = None) -> StrategySignal | None:
    """
    检测 S2 确认逃顶信号（MACD顶背离）

    触发条件：
    1. 股价挑战前高（close >= 近期高点 * 0.97）
    2. MACD 顶背离（价格创新高，DIF未创新高）

    dif_list: 可选的外部 MACD DIF 序列，避免重复计算
    """
    if klines is None or index < 30:
        return None

    today = klines[index]

    # 找前高（过去30天内的最高点，排除最近5天）
    prev_high = max(k["high"] for k in klines[index - 29 : index - 4])
    prev_high_idx = next(i for i in range(index - 29, index - 4) if klines[i]["high"] == prev_high)

    # 当前价格接近或超过前高
    if today["close"] < prev_high * 0.97:
        return None

    # 计算 DIF（如果没有外部传入）
    if dif_list is None or len(dif_list) < index + 1:
        dif_list = _calc_dif(klines)

    if not dif_list or len(dif_list) < index + 1:
        return None

    # 顶背离：价格创新高，DIF 未创新高
    current_dif = dif_list[index]
    prev_dif = dif_list[prev_high_idx]

    if today["close"] > klines[prev_high_idx]["close"] and current_dif < prev_dif * 0.98:
        return StrategySignal(
            ts_code=today["ts_code"],
            trade_date=today["trade_date"],
            strategy=StrategyType.S2,
            confidence=0.8,
            description="S2顶背离 价新高DIF未新高",
            details={
                "prev_high": prev_high,
                "prev_high_date": klines[prev_high_idx]["trade_date"],
                "current_dif": round(current_dif, 4),
                "prev_dif": round(prev_dif, 4),
            },
            action="SELL",
            stop_loss=klines[prev_high_idx]["low"],
            priority=Priority.CRITICAL,
        )

    return None


def detect_s3(klines: list[dict], index: int) -> StrategySignal | None:
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
        if klines[i].get("is_fangliang_yinxian", False) and klines[i]["close"] < klines[i]["open"]:
            s1_index = i
            break

    if s1_index is None:
        return None

    s1_high = klines[s1_index]["high"]
    s1_open = klines[s1_index]["open"]

    # 当前价格反弹到 S1 开盘价附近但未能突破 S1 高点
    if not (s1_open * 0.95 <= today["close"] <= s1_high * 1.02):
        return None

    # 反弹量能不足（小于 S1 当天量能的 70%）
    if today["vol"] > klines[s1_index]["vol"] * 0.7:
        return None

    # 当日涨幅受限（< 2%）
    if today["pct_chg"] > 2:
        return None

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.S3,
        confidence=0.7,
        description="S3最后逃生 反弹至S1下沿 量能不足",
        details={
            "s1_date": klines[s1_index]["trade_date"],
            "s1_high": s1_high,
            "rebound_pct": round((today["close"] - klines[s1_index]["close"]) / klines[s1_index]["close"] * 100, 2),
            "vol_ratio": round(today["vol"] / klines[s1_index]["vol"], 2),
        },
        action="SELL",
        stop_loss=klines[s1_index]["low"],
        priority=Priority.CRITICAL,
    )


def detect_brick_signals(klines: list[dict], index: int) -> StrategySignal | None:
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
    daily_list = _klines_dict_to_daily(klines[: index + 1])
    brick_today = detect_four_brick_system(daily_list)

    # 只关注重要操作状态
    action_today = brick_today.get("brick_action", "观望")
    if action_today in ("观望", "持有"):
        return None

    # 检测昨天状态（用于判断是否为状态变化首日）
    daily_yesterday = _klines_dict_to_daily(klines[:index])
    brick_yesterday = detect_four_brick_system(daily_yesterday)
    action_yesterday = brick_yesterday.get("brick_action", "观望")

    # 如果昨天已经是同样的重要状态，说明不是首日，不重复触发
    if action_yesterday == action_today:
        return None

    # 映射到 StrategyType
    strategy_map = {
        "止损": (StrategyType.BRICK_EXIT, "SELL", 0.85, Priority.CRITICAL),
        "减仓": (StrategyType.BRICK_REDUCE, "SELL", 0.75, Priority.OBSERVE),
        "禁止抄底": (StrategyType.BRICK_BOUNCE, "WATCH", 0.7, Priority.OBSERVE),
    }

    if action_today not in strategy_map:
        return None

    strategy_type, action, confidence, priority = strategy_map[action_today]

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=strategy_type,
        confidence=confidence,
        description=brick_today.get("brick_action_desc", action_today),
        details={
            "brick_consecutive": brick_today.get("brick_consecutive", 0),
            "is_brick_flip_green": brick_today.get("is_brick_flip_green", False),
            "prev_action": action_yesterday,
            "current_action": action_today,
        },
        action=action,
        stop_loss=today["low"],
        priority=priority,
    )


def detect_buy_exhaustion(klines: list[dict], index: int) -> StrategySignal | None:
    """
    检测买盘枯竭信号（上涨动能耗尽预警）

    来源：knowledge/key-candles.md

    触发条件（在上涨趋势中）：
    1. 上涨趋势：index-10 到 index-3 期间有明显上涨（>5%）
    2. 连续3天出现缩量小阳线
       - 小阳线：实体 (close-open)/open < 1%
       - 缩量：每天成交量 < 前一天
    """
    if index < 13:
        return None

    today = klines[index]

    # 1. 检查上涨趋势：index-10 到 index-3 期间涨幅 > 5%
    try:
        trend_low = min(k["low"] for k in klines[index - 10 : index - 2])
        trend_high = max(k["high"] for k in klines[index - 10 : index - 2])
        if trend_low <= 0:
            return None
        up_pct = (trend_high - trend_low) / trend_low
        if up_pct < 0.05:
            return None
    except (ValueError, IndexError):
        return None

    # 2. 检查最近3天是否为缩量小阳线
    for i in range(index - 2, index + 1):
        k = klines[i]
        # 小阳线：close >= open 且实体比例 < 1%
        if k["close"] < k["open"]:
            return None
        if k["open"] <= 0:
            return None
        body_pct = (k["close"] - k["open"]) / k["open"]
        if body_pct >= 0.01:
            return None

        # 缩量：每天成交量 < 前一天
        if i > 0 and k["vol"] >= klines[i - 1]["vol"]:
            return None

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.WATCH,
        confidence=0.65,
        description="买盘枯竭：连续3天缩量小阳线，上涨动能不足",
        details={
            "trend_up_pct": round(up_pct * 100, 2),
            "last_3_days_vol": [klines[i]["vol"] for i in range(index - 2, index + 1)],
        },
        action="WATCH",
        priority=Priority.OBSERVE,
    )


def detect_green_fat_red_thin(klines: list[dict], index: int) -> StrategySignal | None:
    """
    检测绿肥红瘦出货信号（主力出货）

    来源：knowledge/exit-strategies.md、knowledge/market-macro.md

    触发条件：
    近5天内阴线平均成交量 > 阳线平均成交量的1.5倍
    - 阴线：close < open
    - 阳线：close >= open
    - 至少有2根阴线和2根阳线才有意义
    """
    if index < 4:
        return None

    today = klines[index]
    recent = klines[index - 4 : index + 1]

    yin_vols = []
    yang_vols = []
    for k in recent:
        if k["close"] < k["open"]:
            yin_vols.append(k["vol"])
        else:
            yang_vols.append(k["vol"])

    # 至少2根阴线和2根阳线
    if len(yin_vols) < 2 or len(yang_vols) < 2:
        return None

    avg_yin = sum(yin_vols) / len(yin_vols)
    avg_yang = sum(yang_vols) / len(yang_vols)

    if avg_yang <= 0:
        return None

    ratio = avg_yin / avg_yang
    if ratio < 1.5:
        return None

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.S1,
        confidence=0.80,
        description="绿肥红瘦：阴线量能远超阳线，主力出货",
        details={
            "yin_count": len(yin_vols),
            "yang_count": len(yang_vols),
            "avg_yin_vol": round(avg_yin, 0),
            "avg_yang_vol": round(avg_yang, 0),
            "ratio": round(ratio, 2),
        },
        action="SELL",
        priority=Priority.CRITICAL,
    )


def detect_staircase_distribution(klines: list[dict], index: int) -> StrategySignal | None:
    """
    检测阶梯放量下跌信号（阶梯式出货）

    来源：knowledge/exit-strategies.md

    触发条件：
    连续3+天每天量增价跌
    - 量增：vol[i] > vol[i-1]
    - 价跌：close[i] < close[i-1]
    """
    if index < 2:
        return None

    today = klines[index]

    # 从 index 往前数连续量增价跌天数
    consecutive = 1
    for i in range(index, 0, -1):
        if klines[i]["vol"] > klines[i - 1]["vol"] and klines[i]["close"] < klines[i - 1]["close"]:
            consecutive += 1
        else:
            break

    if consecutive < 3:
        return None

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.S1,
        confidence=0.85,
        description=f"阶梯放量下跌：连续{consecutive}天量增价跌，主力出货",
        details={
            "consecutive_days": consecutive,
            "vol_sequence": [klines[i]["vol"] for i in range(max(0, index - consecutive + 1), index + 1)],
            "close_sequence": [klines[i]["close"] for i in range(max(0, index - consecutive + 1), index + 1)],
        },
        action="SELL",
        priority=Priority.CRITICAL,
    )


def detect_top_pinwheel(klines: list[dict], index: int) -> StrategySignal | None:
    """
    检测顶部大风车信号（S1 具体形态）

    来源：knowledge/exit-strategies.md

    触发条件：
    1. 在高位（近20天最高价附近，距高点<5%）
    2. 出现长上下影线 + 真阴线
    3. 上影线 > 实体×2 且 下影线 > 实体×2
    4. 阴线：close < open

    Args:
        klines: K线数据（dict格式）
        index: 当前K线索引

    Returns:
        StrategySignal 或 None
    """
    if index < 20:
        return None

    today = klines[index]

    # 1. 高位判断：当前价在近20天最高价附近（距高点<5%）
    recent_high = max(k["high"] for k in klines[index - 19 : index + 1])
    if today["close"] < recent_high * 0.95:
        return None

    # 2. 阴线判断：close < open
    if today["close"] >= today["open"]:
        return None

    # 3. 实体大小
    body = today["open"] - today["close"]  # 阴线，open > close

    # 4. 上下影线
    upper_shadow = today["high"] - today["open"]
    lower_shadow = today["close"] - today["low"]

    if body <= 0:
        return None

    # 5. 上影线 > 实体×2 且 下影线 > 实体×2
    if upper_shadow < body * 2 or lower_shadow < body * 2:
        return None

    return StrategySignal(
        ts_code=today["ts_code"],
        trade_date=today["trade_date"],
        strategy=StrategyType.S1,
        confidence=0.85,
        description="顶部大风车：高位长上下影阴线，S1形态",
        details={
            "recent_high": round(recent_high, 2),
            "body": round(body, 2),
            "upper_shadow": round(upper_shadow, 2),
            "lower_shadow": round(lower_shadow, 2),
            "upper_body_ratio": round(upper_shadow / body, 2),
            "lower_body_ratio": round(lower_shadow / body, 2),
        },
        action="SELL",
        stop_loss=today["high"],
        priority=Priority.CRITICAL,
    )

from typing import Optional
from ..indicators import DailyData
from .core import StrategyType, StrategySignal, Priority, Action, _get_kdj, _get_bbi, _ensure_daily_klines
from modules.self_optimizer.param_registry import get_active_param


def _safe_num(val, default=0):
    """Return val if it's a real number, otherwise default."""
    return val if val is not None else default


def detect_b1(klines: list[DailyData], index: int, kirin_context: dict | None = None) -> StrategySignal | None:
    """
    检测 B1 买点（已升级 MDC 多维验证 + 麒麟阶段背景）

    B1 核心条件：
    1. J < -10
    2. 缩量回调（最佳）
    3. 非绿砖状态（连续下跌 < 4天）

    MDC 加分项：
    - 价格处于麒麟会“吸筹”阶段 (+20%)
    - 价格处于麒麟会“回落”阶段末期 (+10%)
    - 处于“派发”阶段 (-30%, 一票否决)
    - 价格触及或低于布林下轨 (+15%)
    - 主力大单净流入为正 (+10%)
    - RSI6 < 20 (极度超卖, +10%)
    - ADX 高位动能竭尽 (+10%)
    """
    if index < 10:
        return None

    klines = _ensure_daily_klines(klines)
    today = klines[index]

    k, d, j = _get_kdj(klines, index)

    # 1. 核心条件判断（参数可被 self-optimizer 覆盖）
    j_threshold = get_active_param("b1", "j_threshold", -10)
    if j >= j_threshold:  # J 必须低于 threshold（默认 -10）
        return None

    # 检查是否在连续下跌中（绿砖状态）
    recent_4 = klines[index - 3 : index + 1]
    yin_count = sum(1 for k in recent_4 if k.is_yinxian)
    green_brick_limit = get_active_param("b1", "green_brick_limit", 4)
    if yin_count >= green_brick_limit:
        return None

    # 2. 基础置信度
    is_suoliang = today.is_suoliang
    confidence = 0.5 + (0.1 if is_suoliang else 0)

    mdc_details = []

    # 3. 麒麟阶段背景验证 (Contextual Validation)
    if kirin_context:
        stage = kirin_context.get("stage")
        if stage == "吸筹":
            confidence += 0.20
            mdc_details.append("处于主力吸筹期(高安全)")
        elif stage == "回落":
            confidence += 0.10
            mdc_details.append("处于回落寻底期")
        elif stage == "派发":
            confidence -= 0.30  # 处于派发阶段的 B1 极度危险
            mdc_details.append("处于主力派发期(高风险)")

    # 4. MDC 验证 - 布林带 (超跌验证)
    boll_lower = getattr(today, "boll_lower", None)
    if boll_lower and today.close <= boll_lower * 1.02:
        confidence += 0.15
        mdc_details.append("触及布林下轨(超跌)")

    # 5. MDC 验证 - 资金流 (主力意图)
    large_inflow = getattr(today, "large_inflow", None)
    large_outflow = getattr(today, "large_outflow", None)
    if _safe_num(large_inflow) > _safe_num(large_outflow):
        confidence += 0.10
        mdc_details.append("主力大单净流入")

    # 6. MDC 验证 - RSI (极端超卖，参数可被覆盖)
    rsi6_ceiling = get_active_param("b1", "rsi6_ceiling", 25)
    rsi6 = getattr(today, "rsi6", None)
    if (rsi6 or 50) < rsi6_ceiling:
        confidence += 0.05
        mdc_details.append("RSI极端超卖")

    # 7. MDC 验证 - DMI (趋势动能，参数可被覆盖)
    adx_floor = get_active_param("b1", "adx_floor", 40)
    adx = getattr(today, "adx", None)
    if _safe_num(adx) > adx_floor:
        confidence += 0.10
        mdc_details.append(f"ADX高位动能竭尽({_safe_num(adx):.1f})")

    confidence = max(0.1, min(confidence, 0.98))

    return StrategySignal(
        ts_code=today.ts_code,
        trade_date=today.trade_date,
        strategy=StrategyType.B1,
        confidence=round(confidence, 2),
        description=f"B1买点 J={j:.2f} " + ", ".join(mdc_details),
        details={
            "j": j,
            "k": k,
            "d": d,
            "is_suoliang": is_suoliang,
            "yin_count_4": yin_count,
            "price": today.close,
            "mdc": mdc_details,
            "kirin_stage": kirin_context.get("stage") if kirin_context else None,
        },
        action=Action.BUY.value,
        stop_loss=today.low,
        priority=Priority.OPPORTUNITY,
    )


def detect_b2(klines: list[DailyData], index: int, kirin_context: dict | None = None) -> StrategySignal | None:
    """
    检测 B2 买点（已升级 MDC 多维验证 + 麒麟阶段背景）

    B2 条件（B1后的确认信号）：
    1. 前几日有B1（J<-10）
    2. 放量长阳（涨幅>=4%）
    3. J值拐头（>-10）

    MDC 加分项：
    - 处于麒麟会“拉升”阶段 (+20%)
    - 处于麒麟会“吸筹”末期突破 (+10%)
    - 处于麒麟会“派发”阶段 (-40%, 高位诱多)
    - 有效突破布林中轨 (+15%)
    - 主力大单强力净流入比例高 (+15%)
    - DMI 趋势金叉 (+10%)
    - 布林开口向上 (+10%)
    """
    if index < 15:
        return None

    klines = _ensure_daily_klines(klines)
    today = klines[index]
    yesterday = klines[index - 1]

    # 1. 核心条件：检查是否有B1在前几日
    has_b1 = False
    for i in range(5, min(15, index)):
        pk, pd, pj = _get_kdj(klines, index - i)
        if pj < -10:
            has_b1 = True
            break

    if not has_b1:
        return None

    # 放量长阳
    is_beidou = today.is_beidou
    pct_chg = today.pct_chg
    b2_min_pct = get_active_param("b2", "min_pct", 4.0)
    is_long_yang = pct_chg >= b2_min_pct

    if not (is_long_yang and is_beidou):
        return None

    # 2. 基础置信度
    k, d, j = _get_kdj(klines, index)
    confidence = 0.60
    mdc_details = []

    # 3. 麒麟阶段背景验证
    if kirin_context:
        stage = kirin_context.get("stage")
        if stage == "拉升":
            confidence += 0.20
            mdc_details.append("处于主力拉升期(顺势)")
        elif stage == "吸筹":
            confidence += 0.10
            mdc_details.append("处于吸筹突破期")
        elif stage == "派发":
            confidence -= 0.40  # 派发阶段的假突破非常多
            mdc_details.append("处于主力派发期(假突破风险)")

    # 4. MDC 验证 - 布林带 (突破验证)
    boll_mid_today = getattr(today, "boll_mid", None)
    boll_mid_yesterday = getattr(yesterday, "boll_mid", None)
    if boll_mid_today and boll_mid_yesterday and yesterday.close < boll_mid_yesterday and today.close > boll_mid_today:
        confidence += 0.15
        mdc_details.append("突破布林中轨(走强)")

    boll_upper_today = getattr(today, "boll_upper", None)
    boll_lower_today = getattr(today, "boll_lower", None)
    boll_upper_yesterday = getattr(yesterday, "boll_upper", None)
    boll_lower_yesterday = getattr(yesterday, "boll_lower", None)
    if boll_upper_today and boll_lower_today and boll_upper_yesterday and boll_lower_yesterday:
        # 简单判断开口：width 增加
        today_width = (boll_upper_today - boll_lower_today) / boll_mid_today if boll_mid_today else 0
        prev_width = (boll_upper_yesterday - boll_lower_yesterday) / boll_mid_yesterday if boll_mid_yesterday else 0
        if today_width > prev_width * 1.05:
            confidence += 0.05
            mdc_details.append("布林开口向上")

    # 5. MDC 验证 - 资金流 (强力买入)
    total_amount = today.amount
    large_inflow = getattr(today, "large_inflow", 0)
    large_outflow = getattr(today, "large_outflow", 0)
    net_inflow = large_inflow - large_outflow
    if net_inflow > 0 and total_amount > 0:
        inflow_ratio = net_inflow / total_amount
        if _safe_num(inflow_ratio, 0) > 0.05:
            confidence += 0.15
            mdc_details.append(f"主力大单强力净流入({inflow_ratio * 100:.1f}%)")

    # 6. MDC 验证 - DMI (金叉验证)
    dmi_plus_today = getattr(today, "dmi_plus", None)
    dmi_minus_today = getattr(today, "dmi_minus", None)
    dmi_plus_yesterday = getattr(yesterday, "dmi_plus", None)
    dmi_minus_yesterday = getattr(yesterday, "dmi_minus", None)
    if dmi_plus_today and dmi_minus_today and dmi_plus_yesterday and dmi_minus_yesterday:
        if _safe_num(dmi_plus_yesterday) < _safe_num(dmi_minus_yesterday) and _safe_num(dmi_plus_today) > _safe_num(
            dmi_minus_today
        ):
            confidence += 0.10
            mdc_details.append("DMI趋势金叉")

    confidence = max(0.1, min(confidence, 0.98))

    return StrategySignal(
        ts_code=today.ts_code,
        trade_date=today.trade_date,
        strategy=StrategyType.B2,
        confidence=round(confidence, 2),
        description=f"B2确认 涨{pct_chg:.2f}% " + ", ".join(mdc_details),
        details={
            "j": j,
            "pct_chg": pct_chg,
            "is_beidou": is_beidou,
            "price": today.close,
            "mdc": mdc_details,
            "kirin_stage": kirin_context.get("stage") if kirin_context else None,
        },
        action=Action.BUY.value,
        stop_loss=today.low,
        priority=Priority.OPPORTUNITY,
    )


def detect_b3(klines: list[DailyData], index: int) -> StrategySignal | None:
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

    klines = _ensure_daily_klines(klines)
    today = klines[index]

    # 检查前几日是否有B2
    has_b2 = False
    for i in range(3, min(10, index)):
        if klines[index - i].pct_chg >= 4 and klines[index - i].is_beidou:
            has_b2 = True
            break

    if not has_b2:
        return None

    # B3：小阳线，分歧转一致
    pct_chg = today.pct_chg
    amplitude = (today.high - today.low) / today.prev_close * 100

    if not (0 < pct_chg < 2 and amplitude < 7):
        return None

    return StrategySignal(
        ts_code=today.ts_code,
        trade_date=today.trade_date,
        strategy=StrategyType.B3,
        confidence=0.7,
        description=f"B3中继 涨{pct_chg:.2f}% 振幅{amplitude:.2f}%",
        details={
            "pct_chg": pct_chg,
            "amplitude": amplitude,
            "price": today.close,
        },
        action=Action.BUY.value,
        stop_loss=today.low,
        priority=Priority.OPPORTUNITY,
    )


def detect_sb1(klines: list[DailyData], index: int) -> StrategySignal | None:
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

    klines = _ensure_daily_klines(klines)
    today = klines[index]
    prev_1 = klines[index - 1] if index >= 1 else None

    prev_2 = klines[index - 2] if index >= 2 else None

    if not (prev_1 and prev_2):
        return None

    # 检查前2天是否有放量下跌
    is_drop_vol = prev_2.close < prev_2.open and prev_2.vol > klines[index - 3].vol * 1.5

    if not is_drop_vol:
        return None

    # 今日缩量企稳
    is_suoliang = today.is_suoliang

    # J值
    k, d, j = _get_kdj(klines, index)

    sb1_j_threshold = get_active_param("sb1", "j_negative_threshold", -5)
    if j >= sb1_j_threshold:
        return None

    # 超级B1确认
    stop_loss = prev_2.low

    return StrategySignal(
        ts_code=today.ts_code,
        trade_date=today.trade_date,
        strategy=StrategyType.SB1,
        confidence=0.9,
        description=f"超级B1 J={j:.2f} 放量跌后缩量企稳",
        details={
            "j": j,
            "drop_vol": prev_2.vol,
            "is_suoliang": is_suoliang,
            "price": today.close,
        },
        action=Action.BUY.value,
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY,
    )

from ..core import DailyData, calculate_ma, calculate_sma_series, calculate_slope
from .base import calculate_zg_white


def calculate_brick_value(klines: list[DailyData]) -> float:
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
    var3a_list: list[float] = []
    for i in range(3, len(klines)):  # HHV/LLV 需要 4 天，所以从索引 3 开始
        hhv4 = max(highs[max(0, i - 3) : i + 1])
        llv4 = min(lows[max(0, i - 3) : i + 1])
        if hhv4 == llv4:
            v3 = 50.0
        else:
            v3 = (closes[i] - llv4) / (hhv4 - llv4) * 100
        var3a_list.append(v3)

    if len(var3a_list) < 6:
        return 0

    # VAR4A = SMA(VAR3A, 6, 1) —— 递推序列，每个点承接前一个结果
    var4a_list = calculate_sma_series(var3a_list, 6, 1)

    if len(var4a_list) < 6:
        return 0

    # VAR5A = SMA(VAR4A, 6, 1) + 100 —— 递推序列
    var5a_list = calculate_sma_series(var4a_list, 6, 1)
    var5a = var5a_list[-1] + 100

    # 构建 VAR1A 序列
    var1a_list = []
    for i in range(3, len(klines)):
        hhv4 = max(highs[max(0, i - 3) : i + 1])
        llv4 = min(lows[max(0, i - 3) : i + 1])
        if hhv4 == llv4:
            v1: float = -90.0
        else:
            v1 = (hhv4 - closes[i]) / (hhv4 - llv4) * 100 - 90.0
        var1a_list.append(v1)

    if len(var1a_list) < 4:
        var2a = (var1a_list[-1] if var1a_list else -90) + 100
    else:
        # VAR2A = SMA(VAR1A, 4, 1) + 100 —— 递推序列
        var2a_list = calculate_sma_series(var1a_list, 4, 1)
        var2a = var2a_list[-1] + 100

    # VAR6A = VAR5A - VAR2A
    var6a = var5a - var2a

    # 砖型图 = IF(VAR6A > 4, VAR6A - 4, 0)
    brick = var6a - 4 if var6a > 4 else 0

    return round(brick, 2)


def calculate_brick_history(klines: list[DailyData], lookback: int = 20) -> tuple[str, int]:
    """
    计算砖型图趋势（连续红砖/绿砖数量）

    通达信公式逻辑（与官方一致）：
    - 红砖：今日砖值 >= 昨日砖值（动量上涨）→ COLORRED
    - 绿砖：今日砖值 < 昨日砖值（动量下跌）→ COLOR00FF00

    Args:
        klines: K线数据
        lookback: 回溯天数

    Returns:
        (趋势状态: RED/GREEN/NEUTRAL, 连续砖数)
    """
    if len(klines) < 10:
        return "NEUTRAL", 0

    # 计算历史砖值序列（对比昨日大小判断红绿）
    # 1=红(涨), -1=绿(跌), 0=平
    brick_colors: list[int] = []
    prev_brick = None

    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)

        if prev_brick is not None:
            if brick_val >= prev_brick:
                brick_colors.append(1)  # 红砖 = 上涨
            else:
                brick_colors.append(-1)  # 绿砖 = 下跌
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


def detect_brick_trend(klines: list[DailyData]) -> bool:
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
        sub = closes[: i + 1]
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

    # 计算当前运值 and 命值
    current_ming = ming_values[-1]
    yun_zhi = calculate_zg_white(klines)

    return slope > -0.02 and yun_zhi > current_ming


def detect_four_brick_system(klines: list[DailyData]) -> dict:
    """
    四块砖交易体系检测

    通达信公式逻辑（与官方一致）：
    - 红砖 = 上涨动量（今日砖值 >= 昨日砖值）→ COLORRED
    - 绿砖 = 下跌动量（今日砖值 < 昨日砖值）→ COLOR00FF00

    规则：
    1. 红砖数满4块 → 减仓至少一半
    2. 红砖翻绿 → 立刻止损
    3. 绿砖下跌 → 绝不抄底，先数4块
    4. 买入后3天不涨 → 止损（DSZ铁律）
    """
    result = {
        "brick_consecutive": 0,  # 当前连续砖数
        "brick_action": "观望",  # 操作建议
        "brick_action_desc": "",  # 操作描述
        "is_brick_flip_green": False,  # 红砖刚翻绿（上涨转下跌）
    }

    if len(klines) < 10:
        result["brick_action_desc"] = "数据不足"
        return result

    # 计算历史砖值序列（至少需要8天才能开始算砖值）
    brick_history = []
    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)
        brick_history.append(brick_val)

    if len(brick_history) < 3:
        result["brick_action_desc"] = "数据不足"
        return result

    # 计算红绿砖：与官方公式一致
    # 1=红砖(上涨), -1=绿砖(下跌)
    colors = []
    for i in range(1, len(brick_history)):
        if brick_history[i] >= brick_history[i - 1]:
            colors.append(1)  # 红砖 = 上涨
        else:
            colors.append(-1)  # 绿砖 = 下跌

    if not colors:
        result["brick_action_desc"] = "无砖型数据"
        return result

    # 从最新往前数连续同色砖
    current_color = colors[-1]
    count = 1
    for i in range(len(colors) - 2, -1, -1):
        if colors[i] == current_color:
            count += 1
        else:
            break

    result["brick_consecutive"] = count

    # === 规则判断 ===

    # 1. 红砖翻绿（止损信号）- 上涨转下跌
    if current_color == -1 and len(colors) >= 2:
        prev_color = colors[-2] if len(colors) >= 2 else 1
        if prev_color == 1:
            # 刚翻绿
            result["is_brick_flip_green"] = True
            result["brick_action"] = "止损"
            result["brick_action_desc"] = f"红砖翻绿！立刻止损（连续红砖{count}块后翻绿）"
            return result

    # 2. 红砖数满4块 → 减仓（连续上涨）
    if current_color == 1 and count >= 4:
        result["brick_action"] = "减仓"
        if count == 4:
            result["brick_action_desc"] = "红砖已满4块，至少减仓一半"
        else:
            result["brick_action_desc"] = f"红砖已延续{count}块，趋势延续中，但未减仓需警惕"
        return result

    # 3. 绿砖下跌 → 禁止抄底（连续下跌）
    if current_color == -1:
        result["brick_action"] = "禁止抄底"
        if count >= 4:
            result["brick_action_desc"] = f"绿砖已连续{count}块，跌势可能接近尾声但仍禁止抄底"
        else:
            result["brick_action_desc"] = f"绿砖下跌中（{count}块），绝不抄底，先数4块"
        return result

    # 4. 红砖不足4块 → 持有/观察（上涨中）
    if current_color == 1 and count < 4:
        result["brick_action"] = "持有"
        result["brick_action_desc"] = f"红砖上涨中（{count}块），继续持有"
        return result

    result["brick_action"] = "观望"
    result["brick_action_desc"] = "中性"
    return result

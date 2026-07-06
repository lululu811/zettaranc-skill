"""
麒麟会四阶段识别模块（铁蝴蝶 / 学院派铁蝴蝶）

来源：knowledge/indicators.md 3.9 / knowledge/iron-butterfly.md
核心：吸 → 拉 → 派 → 落 四阶段状态机
"""

from .core import DailyData
from .price_patterns import calculate_zg_white, calculate_dg_yellow
from .volume_patterns import detect_chuhuo_wushi


def _calculate_ma(values: list[float], period: int) -> float:
    """简单移动平均"""
    if len(values) < period:
        return sum(values) / len(values) if values else 0.0
    return sum(values[-period:]) / period


def _calculate_red_green_ratio(klines: list[DailyData], period: int = 20) -> float:
    """
    红肥绿瘦 ratio = 阳线总成交量 / 阴线总成交量

    > 1.5：红肥绿瘦（吸筹/拉升特征）
    < 0.7：绿肥红瘦（派发特征）
    """
    segment = klines[-period:] if len(klines) >= period else klines
    if not segment:
        return 1.0

    red_vol = sum(k.vol for k in segment if k.close > k.open)
    green_vol = sum(k.vol for k in segment if k.close < k.open)

    if green_vol <= 0:
        return 3.0  # 全是阳线
    return red_vol / green_vol


def _detect_n_shape_raise(klines: list[DailyData]) -> tuple[bool, int]:
    """
    N 型逐步抬高检测

    检测最近是否有连续 3 个低点逐步抬高（允许轻微回撤）
    返回：(是否N型抬高, N型确认点索引)
    """
    if len(klines) < 20:
        return False, -1

    # 找最近 3 个局部低点
    lows = []
    for i in range(5, len(klines) - 5):
        if klines[i].low < klines[i - 1].low and klines[i].low < klines[i + 1].low:
            lows.append((i, klines[i].low))

    if len(lows) < 3:
        return False, -1

    # 取最近 3 个局部低点，检查是否逐步抬高
    recent_lows = lows[-3:]
    if recent_lows[0][1] < recent_lows[1][1] * 1.02 and recent_lows[1][1] < recent_lows[2][1] * 1.02:
        return True, recent_lows[0][0]

    return False, -1


def _detect_healthy_breathing(klines: list[DailyData]) -> bool:
    """
    呼吸节奏健康检测：放量涨 → 缩量调

    最近 10 日中，上涨日平均成交量 > 下跌日平均成交量 * 1.2
    """
    if len(klines) < 10:
        return False

    segment = klines[-10:]
    up_vols = [k.vol for k in segment if k.close > k.open]
    down_vols = [k.vol for k in segment if k.close < k.open]

    if not up_vols or not down_vols:
        return False

    avg_up = sum(up_vols) / len(up_vols)
    avg_down = sum(down_vols) / len(down_vols)

    return avg_up > avg_down * 1.2


def _calculate_position_ratio(klines: list[DailyData]) -> dict:
    """
    计算当前价格在 120 日区间中的位置

    返回：{'low': float, 'high': float, 'current': float,
           'from_low_pct': float, 'from_high_pct': float}
    """
    if len(klines) < 60:
        return {"from_low_pct": 50, "from_high_pct": 50}

    period = min(120, len(klines))
    segment = klines[-period:]
    low_price = min(k.low for k in segment)
    high_price = max(k.high for k in segment)
    current = klines[-1].close

    from_low = ((current - low_price) / (high_price - low_price) * 100) if high_price > low_price else 50
    from_high = ((high_price - current) / (high_price - low_price) * 100) if high_price > low_price else 50

    return {
        "low": low_price,
        "high": high_price,
        "current": current,
        "from_low_pct": from_low,
        "from_high_pct": from_high,
    }


def _is_white_above_yellow(klines: list[DailyData]) -> bool:
    """白线是否在黄线之上"""
    try:
        white = calculate_zg_white(klines)
        yellow = calculate_dg_yellow(klines)
        return white > yellow
    except Exception:
        return False


def _calculate_pull_speed(klines: list[DailyData]) -> float:
    """计算拉升速度：最近 20 日涨幅"""
    if len(klines) < 20:
        return 0.0
    return (klines[-1].close / klines[-20].close - 1) * 100


def _detect_volume_price_rise(klines: list[DailyData]) -> bool:
    """量价齐升：最近 10 日，收盘价和成交量都呈上升趋势"""
    if len(klines) < 10:
        return False

    segment = klines[-10:]
    # 简单判断：最近 5 日平均收盘价 > 前 5 日平均收盘价
    # 且最近 5 日平均成交量 > 前 5 日平均成交量
    recent_5_close = sum(k.close for k in segment[-5:]) / 5
    prev_5_close = sum(k.close for k in segment[:5]) / 5
    recent_5_vol = sum(k.vol for k in segment[-5:]) / 5
    prev_5_vol = sum(k.vol for k in segment[:5]) / 5

    return recent_5_close > prev_5_close and recent_5_vol > prev_5_vol


def _has_limit_up(klines: list[DailyData], days: int = 20) -> bool:
    """最近 days 日是否有涨停"""
    segment = klines[-days:] if len(klines) >= days else klines
    return any(k.pct_chg >= 9.9 for k in segment)


def _count_limit_up(klines: list[DailyData], days: int = 20) -> int:
    """最近 days 日涨停次数"""
    segment = klines[-days:] if len(klines) >= days else klines
    return sum(1 for k in segment if k.pct_chg >= 9.9)


def detect_kirin_stage(klines: list[DailyData]) -> dict:
    """
    识别麒麟会（庄家）当前所处阶段

    四阶段：吸筹 → 拉升 → 派发 → 回落
    子类型：铁蝴蝶（传统庄）/ 学院派铁蝴蝶（机构）

    采用评分制，每个阶段 0-100 分，取最高分。

    返回：
    {
        'stage': '吸筹' | '拉升' | '派发' | '回落' | '未知',
        'confidence': float,  # 0-1
        'sub_type': '铁蝴蝶' | '学院派铁蝴蝶' | '未知',
        'scores': {
            'xishou': float,
            'lasheng': float,
            'paifa': float,
            'luoluo': float,
        },
        'indicators': {
            'price_position': str,  # 低位/中位/高位
            'vol_pattern': str,     # 放量/缩量/正常
            'red_green_ratio': float,
            'n_shape': bool,
            'healthy_breathing': bool,
            'white_above_yellow': bool,
            'pull_speed': float,
            'limit_up_count': int,
        },
        'operation': str,  # 关注等B1 / 不追等回调 / 准备走人 / 不抄底 / 观望
    }
    """
    result = {
        "stage": "未知",
        "confidence": 0.0,
        "sub_type": "未知",
        "scores": {},
        "indicators": {},
        "operation": "观望",
    }

    if len(klines) < 60:
        return result

    # ========== 计算辅助指标 ==========
    position = _calculate_position_ratio(klines)
    red_green = _calculate_red_green_ratio(klines, period=20)
    n_shape, n_idx = _detect_n_shape_raise(klines)
    breathing = _detect_healthy_breathing(klines)
    white_above = _is_white_above_yellow(klines)
    pull_speed = _calculate_pull_speed(klines)
    vol_price_rise = _detect_volume_price_rise(klines)
    limit_up_count = _count_limit_up(klines, days=20)
    has_limit_up = limit_up_count > 0

    # 60 日均量
    avg_vol_60 = _calculate_ma([k.vol for k in klines], 60)
    recent_avg_vol = _calculate_ma([k.vol for k in klines[-10:]], 10)
    is_high_vol = recent_avg_vol > avg_vol_60 * 1.3 if avg_vol_60 > 0 else False
    is_low_vol = recent_avg_vol < avg_vol_60 * 0.8 if avg_vol_60 > 0 else False

    # 价格位置描述
    from_low_pct = position["from_low_pct"]
    from_high_pct = position["from_high_pct"]
    if from_low_pct < 30:
        price_pos = "低位"
    elif from_low_pct > 70:
        price_pos = "高位"
    else:
        price_pos = "中位"

    # 成交量描述
    if is_high_vol:
        vol_pattern = "放量"
    elif is_low_vol:
        vol_pattern = "缩量"
    else:
        vol_pattern = "正常"

    indicators = {
        "price_position": price_pos,
        "vol_pattern": vol_pattern,
        "red_green_ratio": round(red_green, 2),
        "n_shape": n_shape,
        "healthy_breathing": breathing,
        "white_above_yellow": white_above,
        "pull_speed": round(pull_speed, 2),
        "limit_up_count": limit_up_count,
        "from_low_pct": round(from_low_pct, 1),
        "from_high_pct": round(from_high_pct, 1),
    }
    result["indicators"] = indicators

    # ========== 吸筹阶段评分 ==========
    xishou_score = 0
    # 低位：从低点涨 < 30%
    if from_low_pct < 30:
        xishou_score += 30
    elif from_low_pct < 50:
        xishou_score += 15
    # 放量
    if is_high_vol:
        xishou_score += 20
    # N 型抬高
    if n_shape:
        xishou_score += 20
    # 红肥绿瘦
    if red_green > 1.3:
        xishou_score += 20
    elif red_green > 1.0:
        xishou_score += 10
    # 无涨停（吸筹期一般不拉涨停）
    if not has_limit_up:
        xishou_score += 10

    # ========== 拉升阶段评分 ==========
    lasheng_score = 0
    # 已从低位涨起来
    if from_low_pct > 30:
        lasheng_score += 20
    elif from_low_pct > 20:
        lasheng_score += 10
    # 涨速快
    if pull_speed > 30:
        lasheng_score += 25
    elif pull_speed > 20:
        lasheng_score += 15
    # 有涨停
    if limit_up_count >= 2:
        lasheng_score += 20
    elif has_limit_up:
        lasheng_score += 10
    # 量价齐升
    if vol_price_rise:
        lasheng_score += 15
    # 白线在黄线之上
    if white_above:
        lasheng_score += 10
    # 呼吸节奏健康
    if breathing:
        lasheng_score += 10

    # ========== 派发阶段评分 ==========
    paifa_score = 0
    # 高位
    if from_high_pct < 15:
        paifa_score += 30
    elif from_high_pct < 30:
        paifa_score += 15
    # 高位放量
    if is_high_vol and from_low_pct > 60:
        paifa_score += 20
    # 绿肥红瘦
    if red_green < 0.7:
        paifa_score += 20
    elif red_green < 1.0:
        paifa_score += 10
    # 出货信号
    try:
        chuhuo = detect_chuhuo_wushi(klines)
        if chuhuo.get("total_score", 0) >= 2:
            paifa_score += 30
    except Exception:
        pass

    # ========== 回落阶段评分 ==========
    luoluo_score = 0
    # 从高点跌下来
    if from_high_pct > 20:
        luoluo_score += 30
    elif from_high_pct > 10:
        luoluo_score += 15
    # 缩量
    if is_low_vol:
        luoluo_score += 25
    # 无承接（阳线少）
    recent_red = sum(1 for k in klines[-10:] if k.close > k.open)
    if recent_red < 3:
        luoluo_score += 20
    # 白线跌破黄线
    if not white_above:
        luoluo_score += 15
    # 无涨停
    if not has_limit_up:
        luoluo_score += 10

    scores = {
        "xishou": xishou_score,
        "lasheng": lasheng_score,
        "paifa": paifa_score,
        "luoluo": luoluo_score,
    }
    result["scores"] = scores

    # ========== 确定阶段 ==========
    max_score = max(scores.values())
    if max_score < 30:
        result["stage"] = "未知"
        result["confidence"] = round(max_score / 100, 2)
        result["operation"] = "观望"
        return result

    stage_map = {
        "xishou": ("吸筹", "关注，等B1"),
        "lasheng": ("拉升", "不追，等回调B1"),
        "paifa": ("派发", "准备走人"),
        "luoluo": ("回落", "不抄底"),
    }

    max_stage = max(scores, key=lambda k: scores[k])
    result["stage"] = stage_map[max_stage][0]
    result["confidence"] = round(min(max_score / 100, 1.0), 2)
    result["operation"] = stage_map[max_stage][1]

    # ========== 子类型判断 ==========
    # 铁蝴蝶 vs 学院派铁蝴蝶
    if result["stage"] == "拉升":
        # 拉升快、洗盘狠 = 铁蝴蝶
        # 拉升慢而稳 = 学院派
        if pull_speed > 40:
            result["sub_type"] = "铁蝴蝶"
        elif pull_speed < 25 and breathing:
            result["sub_type"] = "学院派铁蝴蝶"
        else:
            result["sub_type"] = "铁蝴蝶"
    elif result["stage"] == "派发":
        # A 杀快 = 铁蝴蝶，多重顶 = 学院派
        # 简化：看下跌速度
        recent_drop = (klines[-1].close / klines[-5].close - 1) * 100 if len(klines) >= 5 else 0
        if recent_drop < -15:
            result["sub_type"] = "铁蝴蝶"
        else:
            result["sub_type"] = "学院派铁蝴蝶"

    return result


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from modules.indicators import DailyData

    # 吸筹场景：底部放量，N型抬高，红肥绿瘦
    klines = []
    base = 100.0
    for i in range(80):
        # N型抬高：整体底部逐步抬高
        base *= 1.002
        low = base * (0.98 + i * 0.0005)  # 低点逐步抬高
        vol = 15000 if i % 3 == 0 else 8000  # 放量+缩量交替
        k = DailyData(
            ts_code="000001.SZ",
            trade_date=f"202601{i + 1:02d}",
            open=base * 0.99,
            high=base * 1.02,
            low=low,
            close=base,
            vol=vol,
            amount=base * vol,
            pct_chg=0.2,
            prev_close=base / 1.002,
        )
        klines.append(k)

    result = detect_kirin_stage(klines)
    print("吸筹测试:", result["stage"], result["confidence"], result["operation"])

    # 拉升场景：快速脱离，有涨停，量价齐升
    klines2 = []
    base = 100.0
    for i in range(60):
        if i < 30:
            base *= 1.005
            pct = 0.5
            vol = 10000
        else:
            base *= 1.025
            pct = 2.5
            vol = 25000
        k = DailyData(
            ts_code="000001.SZ",
            trade_date=f"202601{i + 1:02d}",
            open=base * 0.99,
            high=base * 1.05,
            low=base * 0.97,
            close=base,
            vol=vol,
            amount=base * vol,
            pct_chg=pct,
            prev_close=base / (1 + pct / 100),
        )
        klines2.append(k)

    result2 = detect_kirin_stage(klines2)
    print("拉升测试:", result2["stage"], result2["confidence"], result2["operation"], result2["sub_type"])

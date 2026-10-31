"""简单完美图形 —— 三种形态判定

来源：笔记《交易系统.md》§2.2.3「完美图形选股」（三种：经典 / 异动后的横盘 / 完美绿帽·W型）。
与现有「复杂完美图形」（`scoring.is_perfect_pattern`：BBI 之上 + 缩量 + 均线多头 + 非高位）
是两套独立逻辑，互不影响。

总前提（笔记原文）：异动 + 顶部无量 + 缩量回踩 + 绝对涨幅没有翻倍。

阈值分两类：
- **有出处**：笔记原文给出，或沿用仓库已有检测器的口径（见常量注释）
- **经验默认值**：笔记与代码均无依据，已注册到 `self_optimizer.param_registry`，供 Darwin 自优化调参
"""

from __future__ import annotations

import logging
from typing import Any

from ..indicators import calculate_macd
from ..indicators.price_patterns import white_line_series, yellow_line_series
from .data import _dict_to_daily

logger = logging.getLogger(__name__)

# ── 阈值：有出处 ──
SUOLIANG_RATIO = 0.5  # 笔记：「缩半量以上」
NOT_DOUBLED_RATIO = 2.0  # 笔记：「绝对涨幅没有翻倍」→ close / 60日最低 < 2.0
J_THRESHOLD = 0.0  # detect_nana（compound_strategies.py:164）：J < 0
FANGLIANG_PCT = 5.0  # detect_zaihou_chongjian：涨幅 > 5%
FANGLIANG_VOL_RATIO = 1.5  # detect_zaihou_chongjian：量 > 前5日均量 × 1.5
RANGE_WINDOW = 20  # detect_yueyu_yushi：近 20 天
RANGE_AMPLITUDE_MAX = 0.15  # detect_yueyu_yushi：振幅 < 15%
YELLOW_NEAR_TOL = 0.02  # detect_zaihou_chongjian：黄线附近 ±2%

# ── 阈值：经验默认值（无出处，供自优化调参）──
BOX_TOLERANCE = 0.08  # 异动后箱体 ±8%
BOX_MIN_BARS = 5  # 异动后至少横住 5 根
DIGEST_MIN_BARS = 20  # 绿帽后消化窗口
WAVE_MIN_GAIN = 0.20  # 一波流累计涨幅 ≥20%
DIGEST_VOL_RATIO = 0.7  # 消化期均量 ≤ 上涨段均量 × 0.7
NANA_SCAN_BARS = 20  # 类型A：娜娜形态的回溯窗口
RISE_VOL_RATIO = 1.2  # 类型A：温和放量（vol > 昨量 × 1.2，口径见 screener_helper.py:215）
PULLBACK_VOL_RATIO = 0.5  # 类型A：回调段均量 / 上涨段均量上限 = 笔记「缩半量」
PULLBACK_MIN_BARS = 1  # 类型A：缩量回调至少 1 根（笔记字面写 2 根，按实战口径取 1）
J_SCAN_BARS = 5  # 类型A：J 值达大负值的回溯窗口
DENSE_VOL_RATIO = 1.2  # 类型B：密集阳线单根量 ≥ 前5日均量 × 1.2
WAVE_LOOKBACK = 40  # 类型C：一波流起点（前低）的回溯窗口
PEAK_MIN_DISTANCE = 25  # 类型C：峰值距今天至少 25 根（需留出消化空间）
ZHUANG_LIMIT_UP_PCT = 9.8  # 涨停判定（主板 10%）
ZHUANG_LOW_VOL_RATIO = 0.7  # 缩量涨停：量 < 前5日均量 × 0.7
LOW_ZONE_TOL = 1.1  # 60 日低位区间：close ≤ 60日最低 × 1.1


def _active(strategy: str, name: str, fallback: float) -> float:
    """读取可被 Darwin 自优化覆盖的参数；注册表不可用时回落到出厂默认值

    strategy 与 criteria 同名（simple_perfect_1/2/3），三种形态各读各的参数组，
    避免选中某个策略时看到其它形态的参数。
    """
    try:
        from ..self_optimizer.param_registry import get_active_param

        value = get_active_param(strategy, name, fallback)
        return float(value)
    except (ImportError, TypeError, ValueError) as e:
        logger.debug("[simple_perfect] 读取参数 %s 失败，用默认值 %s: %s", name, fallback, e)
        return float(fallback)


def _vol_ma5(klines: list, i: int) -> float:
    """第 i 日的前 5 日均量（含当日）"""
    start = max(0, i - 4)
    window = [k.vol for k in klines[start : i + 1]]
    return sum(window) / len(window) if window else 0.0


def _find_rise_and_pullback(klines: list) -> tuple[int, int, float, int] | None:
    """找「温和放量上涨段 + 其后的缩量回调」

    返回 (上涨段起点, 上涨段终点, 上涨段均量, 缩量回调根数)；找不到返回 None。
    - 温和放量：vol ≥ 前5日均量 × RISE_VOL_RATIO（口径来自 screener_helper：vol > 昨量 × 1.2）
    - 缩量：vol ≤ 上涨段均量 × SUOLIANG_RATIO（笔记「缩半量以上」）
    """
    n = len(klines)
    pullback_ratio = _active("simple_perfect_1", "pullback_vol_ratio", PULLBACK_VOL_RATIO)
    pullback_min = int(_active("simple_perfect_1", "pullback_min_bars", PULLBACK_MIN_BARS))
    # 上涨段结束位置需给后面留出至少 pullback_min 根回调
    for end in range(n - (pullback_min + 1), max(0, n - 30) - 1, -1):
        if end < 1:
            break
        # 上涨段：从 end 往前回溯连续「收盘上行 + 温和放量」（量 > 昨量 × 1.2）
        i = end
        while i > 0 and klines[i].close > klines[i - 1].close:
            if klines[i].vol < klines[i - 1].vol * RISE_VOL_RATIO:
                break
            i -= 1
        if end - i + 1 < 2:
            continue

        # 「缩半量」的基准 = 上涨段内最大的那根量（笔记：长阳之后突然缩半量才是最好的）
        seg_peak_vol = max(k.vol for k in klines[i : end + 1])

        # 顶部无量：上涨段之后 3 根内无放量阴线
        if any(getattr(klines[j], "is_fangliang_yinxian", False) for j in range(end + 1, min(end + 4, n))):
            continue

        # 缩量回调：上涨段之后至少 pullback_min 根（默认 1 根），
        #   且回调段均量 ≤ 上涨段均量 × pullback_ratio（默认 0.5 = 笔记「缩半量」）。
        #   成交量是完美图形最看重的要素，缩量必须够狠：宁可少根数，也要真缩半量。
        for length in range(pullback_min, min(6, n - end)):
            window = klines[end + 1 : end + 1 + length]
            avg_vol = sum(x.vol for x in window) / len(window)
            if seg_peak_vol > 0 and avg_vol <= seg_peak_vol * pullback_ratio:
                return i, end, seg_peak_vol, length
    return None


def _not_doubled(klines: list) -> bool:
    """绝对涨幅未翻倍：close < 近 60 日最低价 × 2"""
    lows = [k.low for k in klines[-60:]]
    if not lows:
        return False
    return klines[-1].close < min(lows) * NOT_DOUBLED_RATIO


def _result(is_match: bool, reasons: list[str], details: dict[str, Any]) -> dict[str, Any]:
    return {"is_match": is_match, "reasons": reasons, "details": details}


# ==================== 类型 A：经典 ====================


def detect_simple_perfect_1(klines: list) -> dict[str, Any]:
    """简单完美图形-1（经典）

    笔记条件：
    1. 低点不断抬高、温和放量
    2. 缩量下跌后 J 到负值、MACD 的 DEA 或 DIF 往上走
    3. 连续放量、顶部无量、回调缩量（缩半量以上），放量/缩量周期各至少 2 根
    4. 绝对涨幅没有翻倍
    排除：低点不断降低（大爷图）

    放量/缩量/顶部无量的判定直接复用 `detect_nana`（其口径已落库为
    is_beidou / is_suoliang / is_fangliang_yinxian 标记）。
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)
    if len(klines) < 30:
        return _result(False, ["数据不足（需 ≥30 根）"], {})

    reasons: list[str] = []
    details: dict[str, Any] = {}

    # 1. 温和放量上涨 → 顶部无量 → 缩量回调（笔记 A 型三连）
    segment = _find_rise_and_pullback(klines)
    if segment is None:
        return _result(False, ["近 30 根内无「温和放量上涨 → 缩量回调」形态"], {})
    seg_start, seg_end, seg_vol, pullback = segment
    reasons.append(
        f"放量上涨({klines[seg_start].trade_date}~{klines[seg_end].trade_date})→顶部无量→缩量回调{pullback}根"
    )
    details["rise_start"] = klines[seg_start].trade_date
    details["rise_end"] = klines[seg_end].trade_date
    details["pullback_bars"] = pullback

    # 2. J 达大负值（近 J_SCAN_BARS 根内出现过）
    try:
        from ..indicators import precompute_kdj_sequence

        kdj_seq = precompute_kdj_sequence(klines)
        recent_j = [row[2] for row in kdj_seq[-J_SCAN_BARS:]]
    except (ImportError, IndexError, TypeError, ValueError) as e:
        logger.warning("[简单完美图形-1] KDJ 计算失败: %s", e)
        return _result(False, [f"KDJ 计算失败: {e}"], {})

    j_threshold = _active("simple_perfect_1", "j_threshold", J_THRESHOLD)
    if not any(j <= j_threshold for j in recent_j if j is not None):
        return _result(
            False,
            [f"近{J_SCAN_BARS}根内 J 未达 {j_threshold:.0f}"],
            {"recent_j": recent_j, "j_threshold": j_threshold},
        )
    reasons.append(f"J ≤ {j_threshold:.0f}")
    details["j_last"] = recent_j[-1] if recent_j else None

    # 3. 低点抬高（排除大爷图：低点不断降低）
    #    判据：回调段最低点高于上涨段起点的低点
    pullback_low = min(k.low for k in klines[seg_end + 1 : seg_end + 1 + pullback])
    base_low = klines[seg_start].low
    if pullback_low <= base_low:
        return _result(False, ["低点未抬高（疑似大爷图）"], {"pullback_low": pullback_low, "base_low": base_low})
    reasons.append("回调低点高于上涨段起点低点（低点抬高）")
    details["pullback_low"] = pullback_low
    details["base_low"] = base_low

    # 3. MACD 的 DIF 或 DEA 向上
    try:
        dif_list, dea_list, _ = calculate_macd(klines)
        dif_up = len(dif_list) >= 2 and dif_list[-1] > dif_list[-2]
        dea_up = len(dea_list) >= 2 and dea_list[-1] > dea_list[-2]
        if not (dif_up or dea_up):
            return _result(False, ["MACD 的 DIF/DEA 均未上行"], {})
    except (IndexError, TypeError, ValueError) as e:
        logger.warning("[简单完美图形-1] MACD 计算失败: %s", e)
        return _result(False, [f"MACD 计算失败: {e}"], {})
    reasons.append("MACD 的 DIF 或 DEA 上行")

    # 4. 绝对涨幅未翻倍
    if not _not_doubled(klines):
        return _result(False, ["绝对涨幅已翻倍（末端）"], {})
    reasons.append("绝对涨幅未翻倍")

    return _result(True, reasons, details)


# ==================== 类型 B：异动后的横盘 ====================


def detect_simple_perfect_2(klines: list) -> dict[str, Any]:
    """简单完美图形-2（异动后的横盘）

    笔记：长期横盘，突然一根放量大阳线或多根密集阳线（异动），之后仍横住。
    排除：底部区间缩量涨停的庄股（§2.3 选股避雷）。
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)
    box_min_bars = int(_active("simple_perfect_2", "box_min_bars", BOX_MIN_BARS))
    box_tolerance = _active("simple_perfect_2", "box_tolerance", BOX_TOLERANCE)

    if len(klines) < RANGE_WINDOW + box_min_bars:
        return _result(False, [f"数据不足（需 ≥{RANGE_WINDOW + box_min_bars} 根）"], {})

    reasons: list[str] = []
    details: dict[str, Any] = {}

    # 1. 长期横盘：近 20 根振幅 < 15%（沿用 detect_yueyu_yushi 口径）
    window = klines[-RANGE_WINDOW:]
    high_max = max(k.high for k in window)
    low_min = min(k.low for k in window)
    amplitude = (high_max - low_min) / low_min if low_min > 0 else 1.0
    if amplitude >= RANGE_AMPLITUDE_MAX:
        return _result(False, [f"非横盘（近{RANGE_WINDOW}根振幅{amplitude * 100:.0f}%）"], {"amplitude": amplitude})
    reasons.append(f"长期横盘（近{RANGE_WINDOW}根振幅{amplitude * 100:.0f}%）")
    details["amplitude"] = amplitude

    # 2. 异动：放量大阳线（涨幅 >5% 且量 ≥ 前5日均量 ×1.5）
    #    或「多根密集阳线」（笔记原文：连续阳线且带量，累计涨幅 >5%）
    yidong_idx = None
    for i in range(len(klines) - RANGE_WINDOW, len(klines) - box_min_bars + 1):
        if i < 1:
            continue
        k = klines[i]
        ma5 = _vol_ma5(klines, i)
        if ma5 <= 0:
            continue
        pct = (k.close - k.prev_close) / k.prev_close * 100 if k.prev_close else 0.0
        if pct > FANGLIANG_PCT and k.close > k.open and k.vol >= ma5 * FANGLIANG_VOL_RATIO:
            yidong_idx = i
            break
        if i + 1 < len(klines):
            nxt = klines[i + 1]
            ma5n = _vol_ma5(klines, i + 1)
            cum = (nxt.close - klines[i - 1].close) / klines[i - 1].close * 100 if klines[i - 1].close else 0.0
            if (
                cum > FANGLIANG_PCT
                and k.close > k.open
                and nxt.close > nxt.open
                and ma5n > 0
                and k.vol >= ma5 * DENSE_VOL_RATIO
                and nxt.vol >= ma5n * DENSE_VOL_RATIO
            ):
                yidong_idx = i + 1
                break

    if yidong_idx is None:
        return _result(False, ["横盘期间无放量异动阳线"], {})
    reasons.append(f"异动放量大阳（{klines[yidong_idx].trade_date}）")
    details["yidong_date"] = klines[yidong_idx].trade_date

    # 3. 异动后仍横住在箱体内
    after = klines[yidong_idx + 1 :]
    if len(after) < box_min_bars:
        return _result(False, ["异动后观察期不足"], {})
    base_high = klines[yidong_idx].high
    base_low = klines[yidong_idx].low
    box_high = max(k.high for k in after)
    box_low = min(k.low for k in after)
    if box_high > base_high * (1 + box_tolerance) or box_low < base_low * (1 - box_tolerance):
        return _result(
            False,
            [f"异动后未横住（箱体 {box_low:.2f}~{box_high:.2f} 超出 ±{box_tolerance * 100:.0f}%）"],
            {"box_high": box_high, "box_low": box_low},
        )
    reasons.append(f"异动后横住 {len(after)} 根（箱体{box_low:.2f}~{box_high:.2f}）")

    # 4. 排除：底部区间缩量涨停的庄股
    k = klines[yidong_idx]
    ma5 = _vol_ma5(klines, yidong_idx)
    low_zone = min(x.low for x in klines[-60:])
    pct = (k.close - k.prev_close) / k.prev_close * 100 if k.prev_close else 0.0
    if (
        pct >= ZHUANG_LIMIT_UP_PCT
        and ma5 > 0
        and k.vol < ma5 * ZHUANG_LOW_VOL_RATIO
        and k.close <= low_zone * LOW_ZONE_TOL
    ):
        return _result(False, ["底部区间缩量涨停（庄股，避雷）"], {"pct": pct})
    reasons.append("非底部缩量涨停")

    # 5. 绝对涨幅未翻倍
    if not _not_doubled(klines):
        return _result(False, ["绝对涨幅已翻倍（末端）"], {})
    reasons.append("绝对涨幅未翻倍")

    return _result(True, reasons, details)


# ==================== 类型 C：完美绿帽 / W型筑底 ====================


def detect_simple_perfect_3(klines: list) -> dict[str, Any]:
    """简单完美图形-3（完美绿帽 / W型筑底助消化）

    笔记：大哥线启动 → 放量 → 一波流 → 顶部放量下杀（大绿帽）→ 时间换空间消化；
    没跌破黄线，且白线没死叉。
    """
    if klines and isinstance(klines[0], dict):
        klines = _dict_to_daily(klines)
    if len(klines) < 120:
        return _result(False, ["数据不足（需 ≥120 根，黄线需 114 根窗口）"], {})

    reasons: list[str] = []
    details: dict[str, Any] = {}

    closes = [k.close for k in klines]
    yellow = yellow_line_series(closes)
    white = white_line_series(closes)

    wave_min_gain = _active("simple_perfect_3", "wave_min_gain", WAVE_MIN_GAIN)

    # 1. 定位一波流峰值（近 60 根内，且距今天至少 PEAK_MIN_DISTANCE 根，需留出消化空间）
    window_start = max(0, len(klines) - 60)
    peak_idx = max(range(window_start, len(klines)), key=lambda j: klines[j].close)
    if peak_idx > len(klines) - PEAK_MIN_DISTANCE:
        return _result(False, ["近 60 根内无完成的上涨波段（峰值距今天太近）"], {})

    # 2. 一波流：峰值相对其前 WAVE_LOOKBACK 根内最低点的涨幅 ≥ wave_min_gain
    low_start = max(0, peak_idx - WAVE_LOOKBACK)
    base_low = min(k.low for k in klines[low_start : peak_idx + 1])
    gain = (klines[peak_idx].close - base_low) / base_low if base_low > 0 else 0.0
    if gain < wave_min_gain:
        return _result(False, [f"一波流涨幅不足（{gain * 100:.0f}%）"], {"gain": gain})
    reasons.append(f"一波流上涨{gain * 100:.0f}%")
    details["gain"] = gain
    details["peak_date"] = klines[peak_idx].trade_date

    # 3. 大哥线启动：底部到峰值之间曾放量站上黄线
    start_idx = None
    for i in range(low_start, peak_idx + 1):
        y = yellow[i]
        if y is None or y <= 0:
            continue
        ma5 = _vol_ma5(klines, i)
        if ma5 <= 0:
            continue
        if klines[i].close > y and klines[i].vol >= ma5 * FANGLIANG_VOL_RATIO:
            start_idx = i
            break

    if start_idx is None:
        return _result(False, ["上涨波段内未出现放量站上大哥线"], {})
    reasons.append(f"放量站上大哥线（{klines[start_idx].trade_date}）")
    details["start_date"] = klines[start_idx].trade_date
    seg = klines[start_idx : peak_idx + 1]
    peak_idx_rel = peak_idx - start_idx

    # 4. 顶部放量下杀（大绿帽）
    green_hat = None
    for j in range(peak_idx, min(peak_idx + 3, len(klines))):
        prev = klines[j - 1] if j > 0 else None
        if prev and klines[j].close < prev.close and klines[j].vol > prev.vol * FANGLIANG_VOL_RATIO:
            green_hat = j
            break
    if green_hat is None:
        return _result(False, ["顶部未出现放量下杀（无大绿帽）"], {})
    reasons.append(f"顶部放量下杀（{klines[green_hat].trade_date}）")
    details["green_hat_date"] = klines[green_hat].trade_date

    # 4. 时间换空间：消化 ≥20 根且缩量、低点不再创新低
    digest_min_bars = int(_active("simple_perfect_3", "digest_min_bars", DIGEST_MIN_BARS))
    digest = klines[green_hat:]
    if len(digest) - 1 < digest_min_bars:
        return _result(False, [f"消化不足（{len(digest) - 1}根 < {digest_min_bars}根）"], {})
    seg_vol = sum(k.vol for k in seg[: peak_idx_rel + 1]) / max(1, peak_idx_rel + 1)
    digest_vol = sum(k.vol for k in digest) / len(digest)
    if seg_vol > 0 and digest_vol > seg_vol * DIGEST_VOL_RATIO:
        return _result(False, ["消化期未缩量"], {"digest_vol_ratio": digest_vol / seg_vol if seg_vol else 0})
    half = len(digest) // 2
    if half > 0:
        first_low = min(k.low for k in digest[:half])
        second_low = min(k.low for k in digest[half:])
        if second_low < first_low:
            return _result(False, ["消化期仍在创新低"], {"first_low": first_low, "second_low": second_low})
    reasons.append(f"消化{len(digest) - 1}根且缩量企稳")

    # 5. 未跌破黄线（±2% 容差，沿用 detect_zaihou_chongjian 口径）
    y_last = yellow[-1]
    if y_last is None or y_last <= 0:
        return _result(False, ["黄线不可用"], {})
    if klines[-1].close < y_last * (1 - YELLOW_NEAR_TOL):
        return _result(False, ["已跌破大哥线"], {"close": klines[-1].close, "yellow": y_last})
    reasons.append("未跌破大哥线")
    details["yellow"] = y_last

    # 6. 白线未死叉（白线在黄线之上）
    if white[-1] < y_last:
        return _result(False, ["白线已在黄线之下（死叉）"], {"white": white[-1], "yellow": y_last})
    reasons.append("白线未死叉黄线")

    # 7. 绝对涨幅未翻倍
    if not _not_doubled(klines):
        return _result(False, ["绝对涨幅已翻倍（末端）"], {})
    reasons.append("绝对涨幅未翻倍")

    return _result(True, reasons, details)

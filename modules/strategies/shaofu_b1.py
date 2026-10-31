"""少妇战法（shaofu）B1 入场检测 —— 战法层。

原先这套规则散在 :meth:`modules.loop_engine.ShaofuLoopEngine.check_entry` 里：
指标级的 B1 波检测（:func:`modules.indicators.detect_b1_today`）加上牛绳、
N 型结构、缩量回调、J 值阈值四个**策略**条件。指标层只该管指标，战法规则
该住在战法层——本 module 把它们收在一起，``ShaofuLoopEngine`` 改为调用这里。

与 :func:`modules.strategies.base_strategies.detect_b1`（通用战法 B1）是
**两套不同的策略**，不是同一规则的两种实现：

- 本检测器按少妇战法 SOP 判定：B1 波打分 + 牛绳（白线≥黄线）+ N 型上移 +
  缩量回调 + J 值阈值
- ``detect_b1`` 按 MDC 多维验证判定：J < -10 + 非绿砖 + 麒麟阶段等加分项

ADR-0002 曾把两者记为"重复实现"，实测在验收样本上两者命中重合度仅 3%
（少妇战法 6639 次 vs 通用战法 315 次，交集 201 次）。
"""

from __future__ import annotations

from typing import Any

from ..indicators import DailyData
from ..indicators.price_patterns import detect_b1_today
from ..indicators.price_patterns import calculate_dg_yellow, calculate_zg_white


def _check_n_structure(klines: list[DailyData], day_idx: int) -> bool:
    """检查 N 型上移结构。

    在近 20 天内寻找两个低点，后一个低点高于前一个（higher lows）。
    这是 B1 信号的辅助确认条件。

    判定方式：把窗口分成前后两半，比较各自的最低价，后半段低点 ≥ 前半段低点
    （允许 2% 容差）。数据不足时放行（返回 True）。

    Args:
        klines: K 线数据
        day_idx: 当前日索引

    Returns:
        是否形成 N 型上移
    """
    lookback = min(day_idx, 20)
    if lookback < 10:
        return True  # 数据不足时放行

    window = klines[day_idx - lookback : day_idx + 1]
    if len(window) < 10:
        return True

    # 将窗口分为前后两半，比较各自的最低价
    mid = len(window) // 2
    first_half = window[:mid]
    second_half = window[mid:]

    if not first_half or not second_half:
        return True

    first_low = min(k.low for k in first_half)
    second_low = min(k.low for k in second_half)

    # 后半段低点 >= 前半段低点（允许 2% 容差）
    return second_low >= first_low * 0.98


def detect_shaofu_b1(
    klines: list[DailyData],
    *,
    j_threshold: float,
    vol_shrink_threshold: float,
) -> dict[str, Any] | None:
    """少妇战法 B1 入场检测。

    判定条件（全部满足才命中）：

    1. **B1 波检测**：:func:`detect_b1_today` 的四项打分（J<13 / 振幅<4% /
       涨幅∈[-2%,1.8%] / 缩量）至少命中 3 项
    2. **J 值阈值**：J ≤ ``j_threshold``
    3. **牛绳**：白线在黄线之上才入场
    4. **缩量回调**：当日量 < 昨日量 × ``vol_shrink_threshold``
    5. **N 型上移结构**：近 20 日存在 higher lows

    Args:
        klines: 完整 K 线数据（按日期升序）。B1 波检测按 ``klines[-1]`` 取当日，
            因此调用方传入的应是**截至当日**的前缀。
        j_threshold: J 值上限（越大越宽松）。
        vol_shrink_threshold: 缩量回调的量能系数。

    Returns:
        命中时返回各判定事实（供调用方拼 reason），否则 ``None``。
    """
    if len(klines) < 30:
        return None

    # --- 1. B1 波检测（指标层）---
    b1 = detect_b1_today(klines)
    if not b1.get("is_b1"):
        return None

    j_val = b1.get("b1_j_value", 50)

    # --- 2. J 值阈值过滤 ---
    if j_val > j_threshold:
        return None

    # --- 3. 牛绳检查：白线在黄线上才入场 ---
    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    if white < yellow:
        return None

    # --- 4. 缩量回调 ---
    today = klines[-1]
    yesterday = klines[-2]
    vol_shrink = today.vol < yesterday.vol * vol_shrink_threshold

    # --- 5. N 型上移结构 ---
    n_structure_ok = _check_n_structure(klines, len(klines) - 1)

    if not (vol_shrink and n_structure_ok):
        return None

    return {
        "is_b1": True,
        "j_value": j_val,
        "b1_score": b1.get("b1_score", 0),
        "b1_amplitude": b1.get("b1_amplitude", 0),
        "vol_shrink": vol_shrink,
        "n_structure_ok": n_structure_ok,
        "entry_price": today.close,
    }


__all__ = ["detect_shaofu_b1"]

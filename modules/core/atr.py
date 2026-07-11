"""ATR（Average True Range，平均真实波幅）计算工具（v3.10.1 提取）

ATR 衡量价格波动幅度，常用于：
- 动态止损（高波动 → 宽止损；低波动 → 紧止损）
- 仓位管理（按波动率倒数缩放仓位）
- 动态滑点（高波动 → 大滑点）

公式：
  TR_i = max(high - low, |high - prev_close|, |low - prev_close|)
  ATR  = mean(TR[-window:])

之前在 `simulator/slippage_model._atr` 与 `simulator/position_sizer._calculate_atr`
中各有一份重复实现，本模块统一为单一来源。
"""
from __future__ import annotations

from collections.abc import Sequence

from ..indicators import DailyData


def calculate_atr(klines: Sequence[DailyData], window: int = 14) -> float:
    """计算最近 window 日的真实波动幅度均值（ATR）

    Args:
        klines: 按日期升序的 K 线序列，长度至少为 window + 1
        window: 计算窗口，常用 14 / 20

    Returns:
        ATR 值（绝对金额）；数据不足时返回 0.0
    """
    if len(klines) < window + 1:
        return 0.0
    true_ranges: list[float] = []
    for i in range(-window, 0):
        current = klines[i]
        previous = klines[i - 1]
        tr = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        true_ranges.append(tr)
    if not true_ranges:
        return 0.0
    return sum(true_ranges) / len(true_ranges)


def atr_pct(klines: Sequence[DailyData], window: int = 14) -> float:
    """ATR 占当前价格的比率（用于 ATR 仓位调整、波动率归一化）

    Args:
        klines: K 线序列
        window: ATR 窗口

    Returns:
        ATR / latest_close；价格不可用时返回 0.0
    """
    if not klines:
        return 0.0
    atr_value = calculate_atr(klines, window)
    last_close = klines[-1].close or 0.0
    if last_close <= 0:
        return 0.0
    return atr_value / last_close

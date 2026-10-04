#!/usr/bin/env python3
"""
B1 观察 + B2 确认策略的量化信号检测模块。

策略规则：
1. 出现 B1（KDJ J 值低于阈值，默认 -10）后进入观察期。
2. 观察期默认为 B1 后第 3~5 个交易日。
3. 观察期内出现 B2：当日涨幅 >= 阈值（默认 4%）且成交量 >= 前日倍数（默认 2 倍）。
4. 买入时点由回测层负责：B2 收盘确认后，次一交易日开盘买入。
5. 可选的次日高开过滤：开盘较前收高开超过阈值时放弃。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .core import _get_kdj


@dataclass
class B1B2Config:
    """B1 观察 + B2 确认策略的量化参数。"""

    # B1 触发阈值
    b1_j_threshold: float = -10.0

    # B1 出现后观察窗口（交易日）
    observe_min: int = 3
    observe_max: int = 5

    # B2 确认条件
    b2_min_pct: float = 4.0  # 当日涨幅下限（%）
    b2_min_vol_ratio: float = 2.0  # 当日量 / 前日量下限
    b2_j_max: float | None = 55.0  # B2 当日 J 值上限；None 表示不检查

    # 次日高开过滤：B2 次日开盘较前一交易日收盘高开超过该百分比则放弃；None 关闭
    max_gap_open_pct: float | None = 5.0

    def validate(self) -> None:
        """校验参数合法性。"""
        if self.observe_min < 1 or self.observe_max < self.observe_min:
            raise ValueError("observe_min/observe_max 必须满足 1 <= observe_min <= observe_max")
        if self.b2_min_pct <= 0:
            raise ValueError("b2_min_pct 必须 > 0")
        if self.b2_min_vol_ratio < 1.0:
            raise ValueError("b2_min_vol_ratio 必须 >= 1.0")
        if self.max_gap_open_pct is not None and self.max_gap_open_pct < 0:
            raise ValueError("max_gap_open_pct 必须 >= 0 或 None")
        if self.b2_j_max is not None and self.b2_j_max <= 0:
            raise ValueError("b2_j_max 必须 > 0 或 None")


def has_b1_in_window(klines, index: int, config: B1B2Config | None = None) -> bool:
    """判断 index 当天往前 observe_min~observe_max 个交易日内是否存在 B1。

    B1 的量化简化定义：KDJ J 值 < b1_j_threshold。
    """
    cfg = config or B1B2Config()
    if index < cfg.observe_min:
        return False

    for back in range(cfg.observe_min, min(cfg.observe_max + 1, index)):
        _, _, j = _get_kdj(klines, index - back)
        if j < cfg.b1_j_threshold:
            return True
    return False


def is_b2_signal(klines, index: int, config: B1B2Config | None = None) -> bool:
    """判断 index 当天是否为有效的 B2 确认信号。

    条件：
    - 当日涨幅 >= b2_min_pct
    - 当日量 / 前日量 >= b2_min_vol_ratio
    - 观察窗口内存在 B1
    - 可选：当日 J 值 < b2_j_max
    """
    cfg = config or B1B2Config()
    if index < 20:
        return False

    today = klines[index]
    yesterday = klines[index - 1]

    if today.pct_chg < cfg.b2_min_pct:
        return False

    vol_ratio = today.vol / yesterday.vol if yesterday.vol else 0.0
    if vol_ratio < cfg.b2_min_vol_ratio:
        return False

    if cfg.b2_j_max is not None:
        _, _, j = _get_kdj(klines, index)
        if j >= cfg.b2_j_max:
            return False

    return has_b1_in_window(klines, index, cfg)


def is_high_open_skip(
    klines,
    b2_idx: int,
    entry_idx: int,
    config: B1B2Config | None = None,
) -> bool:
    """判断 B2 次日是否因高开过多而跳过。

    Args:
        klines: 完整 K 线
        b2_idx: B2 信号日索引
        entry_idx: 计划买入日索引（通常为 b2_idx + 1）
        config: 策略配置
    """
    cfg = config or B1B2Config()
    if cfg.max_gap_open_pct is None:
        return False
    if entry_idx <= 0 or entry_idx >= len(klines):
        return False

    prev_close = klines[entry_idx - 1].close
    if prev_close <= 0:
        return False

    gap_pct = (klines[entry_idx].open / prev_close - 1.0) * 100.0
    return gap_pct > cfg.max_gap_open_pct

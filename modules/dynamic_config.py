"""
动态参数适配器 — 根据市场状态动态调整 LoopConfig

根据 MarketRegimeClassifier 输出的市场状态（BULL / BEAR / SIDEWAYS），
自动生成对应的 LoopConfig 参数组合。

设计思路：
  - base_config 提供所有参数的默认值（不随状态变化的参数由此继承）
  - regime_params 提供各状态下的参数覆盖（只覆盖需要差异化的参数）
  - get_config() 将两者合并，输出完整的 LoopConfig

参数映射表（默认值，可通过 regime_params 自定义 / 优化脚本搜索最优映射）：

  | 参数            | BULL (牛市) | SIDEWAYS (震荡) | BEAR (熊市) |
  |-----------------|-------------|-----------------|-------------|
  | j_threshold     | 18          | 12              | 5           |
  | stop_loss_pct   | -0.07       | -0.05           | -0.03       |
  | bbi_break_days  | 3           | 2               | 1           |
  | min_holding_days| 5           | 3               | 2           |
  | position_pct    | 0.30        | 0.20            | 0.15        |
  | lu_half         | True        | True            | False       |
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, fields, replace

from modules.loop_engine import LoopConfig
from modules.market_regime import TrendRegime
from .constants import (
    BACKTEST_BEAR_POSITION_PCT,
    BACKTEST_BULL_POSITION_PCT,
    BACKTEST_DEFAULT_STOP_LOSS_PCT,
    BACKTEST_HIGH_VOL_STOP_LOSS_PCT,
    BACKTEST_RANGE_POSITION_PCT,
    BACKTEST_TIGHT_STOP_LOSS_PCT,
)


@dataclass(frozen=True)
class MarketTimingWeights:
    """市场择时权重与阈值（v4.3+ 从 modules.market_timing 抽出可调参数）。

    - 6 个综合分权重：trend / breadth / moneyflow / risk / sentiment / amv,合计应为 1.0
    - 2 个状态分类阈值：composite >= strong_threshold 视为强势;
      composite <= weak_threshold 视为弱势;中间为震荡
    - 2 个强弱势阈值：单日涨跌幅 >= strong_up_pct 算强势上涨,
      <= strong_down_pct 算强势下跌(用于市场广度 / 情绪打分的子项)
    - 2 个涨跌停阈值:limit_up_pct / limit_down_pct(A 股硬性规则,默认 9.5% / -9.5%;
      注:涨跌停 ±10% / ±20% 是交易所规则,此处的 9.5% 留 0.5% buffer 是为了容错)
    """

    # 综合分权重(应合计 1.0)
    weight_trend: float = 0.25
    weight_breadth: float = 0.20
    weight_moneyflow: float = 0.15
    weight_risk: float = 0.15
    weight_sentiment: float = 0.10
    weight_amv: float = 0.15

    # 状态分类阈值
    strong_threshold: float = 65.0
    weak_threshold: float = 40.0

    # 强弱势涨跌阈值
    strong_up_pct: float = 5.0
    strong_down_pct: float = -5.0

    # 涨跌停阈值(A 股硬规则 + 0.5% buffer,用于 limit_up / limit_down 计数)
    limit_up_pct: float = 9.5
    limit_down_pct: float = -9.5

    def weights_sum(self) -> float:
        """综合分权重之和(应 ≈ 1.0;不强制,但若偏差大说明配置错了)。"""
        return (
            self.weight_trend
            + self.weight_breadth
            + self.weight_moneyflow
            + self.weight_risk
            + self.weight_sentiment
            + self.weight_amv
        )

    def validate(self) -> None:
        """校验参数合法性。"""
        if self.strong_threshold <= self.weak_threshold:
            raise ValueError(
                f"strong_threshold ({self.strong_threshold}) 必须 > weak_threshold ({self.weak_threshold})"
            )
        if self.strong_up_pct <= 0:
            raise ValueError(f"strong_up_pct 必须 > 0,实际 {self.strong_up_pct}")
        if self.strong_down_pct >= 0:
            raise ValueError(f"strong_down_pct 必须 < 0,实际 {self.strong_down_pct}")
        if self.limit_up_pct <= 0 or self.limit_down_pct >= 0:
            raise ValueError(
                f"limit_up_pct ({self.limit_up_pct}) 必须 > 0 且 limit_down_pct ({self.limit_down_pct}) 必须 < 0"
            )
        s = self.weights_sum()
        if abs(s - 1.0) > 0.01:
            raise ValueError(f"6 个综合分权重之和应为 1.0,实际 {s:.4f};权重偏差 > 0.01 时综合分会被异常放大或压缩")


# 项目默认权重(与原 modules/market_timing.py 内置 magic numbers 完全一致)
DEFAULT_MARKET_TIMING_WEIGHTS = MarketTimingWeights()


# 默认参数映射表：各市场状态下的参数覆盖
DEFAULT_REGIME_PARAMS: dict[str, dict] = {
    "BULL": {
        "j_threshold": 18,  # 牛市放宽 J 值阈值（允许追高）
        "stop_loss_pct": BACKTEST_HIGH_VOL_STOP_LOSS_PCT,  # 牛市放宽止损（容忍更大回撤）
        "bbi_break_days": 3,  # 牛市放宽 BBI 跌破天数（避免假跌破）
        "min_holding_days": 5,  # 牛市延长持仓（趋势持续性强）
        "position_pct": BACKTEST_BULL_POSITION_PCT,  # 牛市加大仓位
        "lu_half": True,  # 牛市启用卤煮减半
    },
    "SIDEWAYS": {
        "j_threshold": 12,  # 震荡市使用默认 J 值
        "stop_loss_pct": BACKTEST_DEFAULT_STOP_LOSS_PCT,  # 震荡市适中止损
        "bbi_break_days": 2,  # 震荡市使用默认 BBI 跌破天数
        "min_holding_days": 3,  # 震荡市使用默认持仓天数
        "position_pct": BACKTEST_RANGE_POSITION_PCT,  # 震荡市降低仓位
        "lu_half": True,  # 震荡市启用卤煮减半
    },
    "BEAR": {
        "j_threshold": 5,  # 熊市严格 J 值（只抓超跌反弹）
        "stop_loss_pct": BACKTEST_TIGHT_STOP_LOSS_PCT,  # 熊市收紧止损（快进快出）
        "bbi_break_days": 1,  # 熊市敏感 BBI 跌破（立即离场）
        "min_holding_days": 2,  # 熊市缩短持仓（减少 exposure）
        "position_pct": BACKTEST_BEAR_POSITION_PCT,  # 熊市轻仓试探
        "lu_half": False,  # 熊市关闭卤煮减半（保守策略）
    },
}

"""模拟器配置的规范装配点 —— CLI 与 API 共用同一份默认值与单位口径。

此前两个入口各写一份装配代码，默认值已经漂移：

=========================  ==================  ==================
字段                       CLI                API
=========================  ==================  ==================
position_score_threshold   70.0               60
max_position_pct           0.20               0.15
use_dynamic_slippage       False              True
cost_model                 "simple"/"advanced"  "zero"/"realistic"
min_resonance_score        0.35（0-1 分数）    50 ÷ 100（字段是 0-100）
=========================  ==================  ==================

两处最严重的问题：

1. **cost_model 词汇不同**，且"simple"与"zero"根本不是一回事——CLI 的 simple
   佣金 0.0003（非零），API 的 zero 全零。
2. **min_resonance_score 单位不同**：同一个 0.35 在 CLI 是 35 分，在 API 被
   除以 100 变成 0.0035 分——差 100 倍。

规范值以 :class:`modules.simulator.SimulationConfig` 自身的默认值与
:data:`modules.constants.BACKTEST_DEFAULT_MAX_POSITION_PCT` 为准（CLI 侧本来
就是对的，API 侧是离群值）。
"""

from __future__ import annotations

from typing import Any

from . import CostModel, SimulationConfig

# 规范默认值 —— 两个入口共用
SIMULATION_DEFAULTS: dict[str, Any] = {
    "initial_capital": 1_000_000.0,
    "max_positions": 5,
    "risk_per_trade": 0.02,
    "position_score_threshold": 70.0,
    "signal_min_count": 2,
    "benchmark_code": "000300.SH",
    "use_dynamic_slippage": False,
    "use_atr_sizing": False,
    "max_position_pct": 0.20,
    "allow_st": True,
    "t1_lock": True,
    "strategy_mode": "simple",
    "strategy_lookback_days": 5,
    # 0-1 分数口径（与 SimulationConfig.min_resonance_score、
    # param_space 的搜索区间 0.15~0.55 一致）
    "min_resonance_score": 0.35,
    "cost_model": "simple",
}

# 成本模型词汇 → 规范名
_COST_MODEL_ALIASES = {
    "advanced": "realistic",  # CLI 历史词汇
}


def build_cost_model(name: str = "simple") -> CostModel:
    """按规范词汇构造交易成本模型。

    - ``"zero"``：全零（无交易成本）
    - ``"simple"``：佣金 0.0003，免印花税与过户费
    - ``"realistic"``：完整 A 股成本模型（佣金 0.00025 / 最低 5 元 /
      印花税 0.0005 / 过户费）

    ``"advanced"`` 作为 ``"realistic"`` 的历史别名保留。
    """
    canonical = _COST_MODEL_ALIASES.get(name, name)
    if canonical == "zero":
        return CostModel(
            commission_rate=0,
            min_commission=0,
            stamp_duty_rate=0,
            transfer_fee_rate=0,
        )
    if canonical == "simple":
        return CostModel(
            commission_rate=0.0003,
            min_commission=0.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
            apply_stamp_duty_on_sell=False,
        )
    return CostModel()


def build_simulation_config(**overrides: Any) -> SimulationConfig:
    """按规范默认值装配 :class:`SimulationConfig`。

    未提供的字段取 :data:`SIMULATION_DEFAULTS`；``cost_model`` 传字符串时按
    规范词汇构造成本模型。CLI 与 API 都只传自己显式拿到的差异值——此后两者
    对同一组默认输入产出**完全相同**的配置。
    """
    values = {**SIMULATION_DEFAULTS, **overrides}
    cost_model = values.pop("cost_model", "simple")
    if isinstance(cost_model, str):
        cost_model = build_cost_model(cost_model)
    return SimulationConfig(cost_model=cost_model, **values)


__all__ = [
    "SIMULATION_DEFAULTS",
    "build_cost_model",
    "build_simulation_config",
]

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
from dataclasses import fields, replace

from modules.loop_engine import LoopConfig
from modules.market_regime import MarketRegime


# 默认参数映射表：各市场状态下的参数覆盖
DEFAULT_REGIME_PARAMS: dict[str, dict] = {
    "BULL": {
        "j_threshold": 18,        # 牛市放宽 J 值阈值（允许追高）
        "stop_loss_pct": -0.07,   # 牛市放宽止损（容忍更大回撤）
        "bbi_break_days": 3,      # 牛市放宽 BBI 跌破天数（避免假跌破）
        "min_holding_days": 5,    # 牛市延长持仓（趋势持续性强）
        "position_pct": 0.30,     # 牛市加大仓位
        "lu_half": True,          # 牛市启用卤煮减半
    },
    "SIDEWAYS": {
        "j_threshold": 12,        # 震荡市使用默认 J 值
        "stop_loss_pct": -0.05,   # 震荡市适中止损
        "bbi_break_days": 2,      # 震荡市使用默认 BBI 跌破天数
        "min_holding_days": 3,    # 震荡市使用默认持仓天数
        "position_pct": 0.20,     # 震荡市降低仓位
        "lu_half": True,          # 震荡市启用卤煮减半
    },
    "BEAR": {
        "j_threshold": 5,         # 熊市严格 J 值（只抓超跌反弹）
        "stop_loss_pct": -0.03,   # 熊市收紧止损（快进快出）
        "bbi_break_days": 1,      # 熊市敏感 BBI 跌破（立即离场）
        "min_holding_days": 2,    # 熊市缩短持仓（减少 exposure）
        "position_pct": 0.15,     # 熊市轻仓试探
        "lu_half": False,         # 熊市关闭卤煮减半（保守策略）
    },
}


class DynamicConfigAdapter:
    """
    动态参数适配器

    根据市场状态（BULL / BEAR / SIDEWAYS）动态生成 LoopConfig。
    支持自定义参数映射表，方便优化脚本搜索最优参数组合。

    Args:
        base_config: 基础配置（作为默认值），None 使用 LoopConfig() 默认值
        regime_params: 各状态的参数覆盖字典
                      格式: {"BULL": {"j_threshold": 18, ...}, "BEAR": {...}, "SIDEWAYS": {...}}
                      未提供的状态使用 DEFAULT_REGIME_PARAMS 中的默认值
                      未在覆盖字典中的参数继承自 base_config

    Example:
        >>> adapter = DynamicConfigAdapter()
        >>> config = adapter.get_config(MarketRegime.BULL)
        >>> config.j_threshold
        18
        >>> config.position_pct
        0.30
    """

    def __init__(
        self,
        base_config: LoopConfig | None = None,
        regime_params: dict[str, dict] | None = None,
    ):
        self.base_config = base_config if base_config is not None else LoopConfig()

        # 深拷贝默认映射，再用用户传入的覆盖
        self._regime_params: dict[str, dict] = copy.deepcopy(DEFAULT_REGIME_PARAMS)
        if regime_params is not None:
            for regime_key, params in regime_params.items():
                if regime_key in self._regime_params:
                    self._regime_params[regime_key].update(params)
                else:
                    self._regime_params[regime_key] = dict(params)

    def get_config(self, regime: MarketRegime) -> LoopConfig:
        """
        根据市场状态获取对应的 LoopConfig

        将 base_config 与对应状态的参数覆盖合并，返回新的 LoopConfig 实例。
        未在当前状态覆盖字典中出现的参数，继承自 base_config。

        Args:
            regime: 市场状态枚举值

        Returns:
            针对该市场状态调整后的 LoopConfig 实例（新对象，不影响 base_config）
        """
        overrides = self._regime_params.get(regime.value, {})
        # 只保留 LoopConfig 中实际存在的字段，忽略无效键
        valid_fields = {f.name for f in fields(LoopConfig)}
        filtered = {k: v for k, v in overrides.items() if k in valid_fields}
        return replace(self.base_config, **filtered)

    def set_regime_params(self, regime: str, params: dict) -> None:
        """
        设置/更新某个状态的参数映射

        只更新传入的参数字段，不影响该状态下已有的其他覆盖参数。
        若该状态尚无映射，则创建新映射。

        Args:
            regime: 市场状态名称（"BULL" / "BEAR" / "SIDEWAYS"）
            params: 要覆盖的参数字典
        """
        if regime in self._regime_params:
            self._regime_params[regime].update(params)
        else:
            self._regime_params[regime] = dict(params)

    def get_all_configs(self) -> dict[str, LoopConfig]:
        """
        获取所有状态的配置字典

        Returns:
            {状态名称: LoopConfig} 字典，包含 BULL / BEAR / SIDEWAYS 三种状态的完整配置
        """
        return {
            regime_key: self.get_config(MarketRegime(regime_key))
            for regime_key in self._regime_params
        }

    def get_regime_params(self, regime: str) -> dict:
        """
        获取某个状态的参数覆盖字典（只返回覆盖项，非完整 LoopConfig）

        Args:
            regime: 市场状态名称

        Returns:
            该状态的参数覆盖字典的副本
        """
        return dict(self._regime_params.get(regime, {}))

    def __repr__(self) -> str:
        regimes = ", ".join(self._regime_params.keys())
        return f"DynamicConfigAdapter(regimes=[{regimes}], base={self.base_config})"


# ──────────────────── 测试入口 ────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("动态参数适配器 — 测试")
    print("=" * 60)

    # 测试1: 默认参数映射
    print("\n【测试1】默认参数映射")
    adapter = DynamicConfigAdapter()

    for regime in MarketRegime:
        config = adapter.get_config(regime)
        print(f"\n  {regime.value}:")
        print(f"    j_threshold     = {config.j_threshold}")
        print(f"    stop_loss_pct   = {config.stop_loss_pct}")
        print(f"    bbi_break_days  = {config.bbi_break_days}")
        print(f"    min_holding_days= {config.min_holding_days}")
        print(f"    position_pct    = {config.position_pct}")
        print(f"    lu_half         = {config.lu_half}")

    # 测试2: 自定义 base_config
    print("\n【测试2】自定义 base_config")
    custom_base = LoopConfig(j_threshold=10, position_pct=0.25)
    adapter2 = DynamicConfigAdapter(base_config=custom_base)
    bear_config = adapter2.get_config(MarketRegime.BEAR)
    print(f"  BEAR j_threshold = {bear_config.j_threshold} (覆盖为5)")
    print(f"  BEAR position_pct = {bear_config.position_pct} (覆盖为0.15)")
    print(f"  BEAR stop_loss_method = {bear_config.stop_loss_method} (继承自base: entry_low)")

    # 测试3: 自定义 regime_params
    print("\n【测试3】自定义 regime_params 覆盖")
    adapter3 = DynamicConfigAdapter(regime_params={
        "BULL": {"j_threshold": 25, "position_pct": 0.5},
    })
    bull_config = adapter3.get_config(MarketRegime.BULL)
    print(f"  BULL j_threshold = {bull_config.j_threshold} (自定义为25)")
    print(f"  BULL position_pct = {bull_config.position_pct} (自定义为0.5)")
    print(f"  BULL stop_loss_pct = {bull_config.stop_loss_pct} (保留默认映射-0.07)")

    # 测试4: set_regime_params 动态更新
    print("\n【测试4】set_regime_params 动态更新")
    adapter.set_regime_params("BULL", {"j_threshold": 20, "new_param": 999})
    updated = adapter.get_config(MarketRegime.BULL)
    print(f"  BULL j_threshold = {updated.j_threshold} (更新为20)")

    # 测试5: get_all_configs
    print("\n【测试5】get_all_configs")
    all_configs = adapter.get_all_configs()
    for name, cfg in all_configs.items():
        print(f"  {name}: j_threshold={cfg.j_threshold}, position_pct={cfg.position_pct}")

    # 测试6: get_regime_params
    print("\n【测试6】get_regime_params")
    bull_params = adapter.get_regime_params("BULL")
    print(f"  BULL 覆盖参数: {bull_params}")

    print("\n" + "=" * 60)
    print("测试完成")

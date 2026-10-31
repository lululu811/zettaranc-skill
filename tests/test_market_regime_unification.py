"""市场状态判定的单一来源护栏。

此前同一组阈值（65 / 40 / 0.1 / -0.15 / 55 / 40）散在三处：
- ``core/market_context.py::classify_market_regime`` 的默认参数（**零生产调用方**）
- ``simulator/market_context.py`` 里**手抄的两份**判定逻辑
- ``dynamic_config.MarketTimingWeights`` 的状态分类阈值

现在阈值集中在 ``modules/constants.py``，判定集中在 ``classify_market_regime``。
"""

from __future__ import annotations

import inspect

import pytest

from modules.constants import (
    MARKET_REGIME_STRONG_BREADTH,
    MARKET_REGIME_STRONG_MONEYFLOW,
    MARKET_REGIME_STRONG_TREND,
    MARKET_REGIME_WEAK_BREADTH,
    MARKET_REGIME_WEAK_MONEYFLOW,
    MARKET_REGIME_WEAK_TREND,
)
from modules.core.market_context import MarketRegime, classify_market_regime


class TestThresholdSingleSource:
    def test_canonical_classifier_defaults_come_from_constants(self):
        params = inspect.signature(classify_market_regime).parameters
        assert params["strong_threshold"].default == MARKET_REGIME_STRONG_TREND
        assert params["weak_threshold"].default == MARKET_REGIME_WEAK_TREND
        assert params["breadth_strong"].default == MARKET_REGIME_STRONG_BREADTH
        assert params["breadth_weak"].default == MARKET_REGIME_WEAK_BREADTH
        assert params["moneyflow_strong"].default == MARKET_REGIME_STRONG_MONEYFLOW
        assert params["moneyflow_weak"].default == MARKET_REGIME_WEAK_MONEYFLOW

    def test_market_timing_weights_use_same_constants(self):
        from modules.dynamic_config import MarketTimingWeights

        weights = MarketTimingWeights()
        assert weights.strong_threshold == MARKET_REGIME_STRONG_TREND
        assert weights.weak_threshold == MARKET_REGIME_WEAK_TREND


class TestClassifyMarketRegime:
    """判定边界——共享实现的行为契约。"""

    def test_strong_requires_all_three_metrics(self):
        assert (
            classify_market_regime(
                trend_score=70.0,
                breadth=0.2,
                moneyflow_score=60.0,
            )
            is MarketRegime.STRONG
        )
        # 任一不足就退回中性
        assert (
            classify_market_regime(
                trend_score=70.0,
                breadth=0.05,
                moneyflow_score=60.0,
            )
            is MarketRegime.NEUTRAL
        )

    def test_weak_triggers_on_any_metric(self):
        assert (
            classify_market_regime(
                trend_score=30.0,
                breadth=0.2,
                moneyflow_score=60.0,
            )
            is MarketRegime.WEAK
        )
        assert (
            classify_market_regime(
                trend_score=70.0,
                breadth=0.2,
                moneyflow_score=30.0,
            )
            is MarketRegime.WEAK
        )

    def test_neutral_in_between(self):
        assert (
            classify_market_regime(
                trend_score=50.0,
                breadth=0.0,
                moneyflow_score=45.0,
            )
            is MarketRegime.NEUTRAL
        )


class TestSimulatorDelegatesToCanonical:
    def test_simulator_binds_the_canonical_function(self):
        """simulator 必须绑定 core 的 canonical 判定函数本身。

        身份断言：手抄副本必然是**另一个函数对象**，这里就会失败。
        比源码文本检查可靠，也不像行为探针那样要连真实数据源（慢 25 秒）。
        """
        import modules.simulator.market_context as sim
        from modules.core.market_context import classify_market_regime

        assert sim.classify_market_regime is classify_market_regime

"""多策略融合引擎测试（v3.10.0）"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from modules.backtest.portfolio import (
    EntrySignal,
    PortfolioConfig,
    PortfolioBacktestEngine,
    STRATEGY_DETECTORS,
)


def _score_candidate(
    signals: list[EntrySignal],
    weights: dict[str, float],
) -> float:
    """模块级包装：调用 PortfolioBacktestEngine._score_candidate"""
    return PortfolioBacktestEngine._score_candidate(signals, weights)


# ============================================================
# 测试数据工厂
# ============================================================


def _make_signal(strategy: str = "B1", confidence: float = 0.8) -> EntrySignal:
    return EntrySignal(
        strategy=strategy,
        confidence=confidence,
        reason=f"test {strategy} signal",
        stop_loss_price=90.0,
    )


# ============================================================
# EntrySignal 数据类测试
# ============================================================


class TestEntrySignal:
    def test_creation(self):
        sig = EntrySignal(strategy="B1", confidence=0.9, reason="J=-15", stop_loss_price=95.0)
        assert sig.strategy == "B1"
        assert sig.confidence == 0.9
        assert sig.reason == "J=-15"
        assert sig.stop_loss_price == 95.0

    def test_confidence_range(self):
        """置信度应在合理范围内"""
        sig = _make_signal(confidence=1.0)
        assert 0.0 <= sig.confidence <= 1.0


# ============================================================
# STRATEGY_DETECTORS 注册表测试
# ============================================================


class TestStrategyDetectors:
    def test_b1_registered(self):
        assert "B1" in STRATEGY_DETECTORS
        fn, weight = STRATEGY_DETECTORS["B1"]
        assert callable(fn)
        assert weight > 0

    def test_b2_registered(self):
        assert "B2" in STRATEGY_DETECTORS

    def test_sb1_registered(self):
        assert "SB1" in STRATEGY_DETECTORS

    def test_changan_registered(self):
        assert "长安" in STRATEGY_DETECTORS

    def test_all_detectors_callable(self):
        for name, (fn, weight) in STRATEGY_DETECTORS.items():
            assert callable(fn), f"{name} detector not callable"
            assert weight > 0, f"{name} weight must be positive"


# ============================================================
# _score_candidate 评分函数测试
# ============================================================


class TestScoreCandidate:
    def test_empty_signals(self):
        score = _score_candidate([], {})
        assert score == 0.0

    def test_single_signal(self):
        signals = [_make_signal("B1", confidence=0.8)]
        weights = {"B1": 1.0}
        score = _score_candidate(signals, weights)
        assert score == pytest.approx(0.8)

    def test_weighted_signal(self):
        signals = [_make_signal("B1", confidence=0.8)]
        weights = {"B1": 1.5}
        score = _score_candidate(signals, weights)
        assert score == pytest.approx(1.2)

    def test_multi_strategy_resonance_bonus(self):
        """多策略同时触发应有共振奖励"""
        signals = [
            _make_signal("B1", confidence=0.8),
            _make_signal("B2", confidence=0.6),
        ]
        weights = {"B1": 1.0, "B2": 0.8}
        score = _score_candidate(signals, weights)
        # base = 0.8*1.0 + 0.6*0.8 = 1.28, bonus = 0.1 * 1 = 0.1
        assert score == pytest.approx(1.28 + 0.1)

    def test_triple_strategy_resonance(self):
        """三策略共振奖励更大"""
        signals = [
            _make_signal("B1", confidence=0.8),
            _make_signal("B2", confidence=0.6),
            _make_signal("长安", confidence=0.7),
        ]
        weights = {"B1": 1.0, "B2": 0.8, "长安": 0.9}
        score = _score_candidate(signals, weights)
        # base = 0.8*1.0 + 0.6*0.8 + 0.7*0.9 = 1.91, bonus = 0.1 * 2 = 0.2
        assert score == pytest.approx(1.91 + 0.2)

    def test_fallback_weight(self):
        """未知策略应使用默认权重 1.0"""
        signals = [_make_signal("未知策略", confidence=0.5)]
        score = _score_candidate(signals, {})
        assert score == pytest.approx(0.5)


# ============================================================
# PortfolioConfig 多策略字段测试
# ============================================================


class TestPortfolioConfigMultiStrategy:
    def test_default_single_strategy(self):
        config = PortfolioConfig()
        assert config.enabled_strategies == ["B1"]

    def test_default_weights(self):
        config = PortfolioConfig()
        assert "B1" in config.strategy_weights
        assert config.strategy_weights["B1"] == 1.0

    def test_min_composite_score_default(self):
        config = PortfolioConfig()
        assert config.min_composite_score == 0.3

    def test_custom_strategies(self):
        config = PortfolioConfig(
            enabled_strategies=["B1", "B2", "长安"],
            strategy_weights={"B1": 1.0, "B2": 0.8, "长安": 0.9},
        )
        assert len(config.enabled_strategies) == 3
        assert "长安" in config.enabled_strategies


# ============================================================
# PortfolioBacktestEngine._check_multi_entry 测试
# ============================================================


class TestCheckMultiEntry:
    def setup_method(self):
        self.engine = PortfolioBacktestEngine()

    def test_no_signals_returns_empty(self):
        """无信号时应返回空列表"""
        # 构造一个空的 mock engine
        with patch.object(self.engine, "_check_multi_entry", return_value=[]):
            result = self.engine._check_multi_entry([], 50, ["B1"])
            assert result == []

    def test_unknown_strategy_skipped(self):
        """未知策略应被跳过不报错"""
        # 使用 mock klines，让检测函数返回 None
        with patch("modules.backtest.portfolio.detect_b1", return_value=None):
            result = self.engine._check_multi_entry([MagicMock()], 50, ["UNKNOWN"])
            assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

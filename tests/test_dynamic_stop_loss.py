"""动态止损策略测试（v3.10.1）

覆盖：
- core.atr.calculate_atr / atr_pct 计算正确性
- loop_engine._calc_stop_loss_price 新增 atr_based 模式
- loop_engine.calc_trailing_stop_price 工具
- ShaofuLoopEngine 集成移动止损（持仓期间 highest_after_entry 追踪 + 触发）
- LoopConfig 向后兼容
"""
from __future__ import annotations

import pytest

from modules.core.atr import calculate_atr, atr_pct
from modules.indicators import DailyData
from modules.loop_engine import (
    LoopConfig,
    LoopTrade,
    ShaofuLoopEngine,
    _calc_stop_loss_price,
    calc_trailing_stop_price,
)


# ============================================================
# 数据工厂
# ============================================================


def _make_kline(
    trade_date: str,
    close: float,
    high: float = 0.0,
    low: float = 0.0,
    prev_close: float | None = None,
) -> DailyData:
    """构造测试 K 线"""
    h = high or close + 1.0
    lo = low or close - 1.0
    return DailyData(
        ts_code="000001.SZ",
        trade_date=trade_date,
        open=close,
        high=h,
        low=lo,
        close=close,
        vol=1000.0,
        amount=close * 1000.0,
        pct_chg=0.0,
        prev_close=prev_close if prev_close is not None else close,
    )


def _generate_klines_with_known_tr(
    trs: list[float],
    base_close: float = 100.0,
) -> list[DailyData]:
    """生成 ATR 测试用 K 线：TR 序列明确，便于断言"""
    klines: list[DailyData] = []
    prev_close = base_close
    for i, tr in enumerate(trs):
        high = prev_close + tr / 2 + 0.5
        low = prev_close - tr / 2 - 0.5
        close = prev_close + (tr * 0.1)  # 收盘价略偏向上，TR 由 high-low 主导
        # 强制 TR = high - low ≈ tr
        high = prev_close + tr
        low = prev_close
        close = prev_close + 0.1
        klines.append(
            DailyData(
                ts_code="000001.SZ",
                trade_date=f"2026-{(i // 31) + 1:02d}-{(i % 31) + 1:02d}",
                open=close,
                high=high,
                low=low,
                close=close,
                vol=1000.0,
                amount=close * 1000.0,
                pct_chg=0.0,
                prev_close=prev_close,
            )
        )
        prev_close = close
    return klines


# ============================================================
# core.atr.calculate_atr 测试
# ============================================================


class TestCalculateAtr:
    def test_insufficient_data_returns_zero(self):
        """数据不足（len < window+1）时返回 0"""
        klines = _generate_klines_with_known_tr([1.0] * 5)
        # window=10 但只有 5 根
        assert calculate_atr(klines, window=10) == 0.0

    def test_basic_atr_computation(self):
        """简单 ATR 计算验证（手工期望值）"""
        # 第一根 prev 不能算，构造 6 根
        klines = _generate_klines_with_known_tr([2.0, 4.0, 6.0, 8.0, 10.0])
        # window=3 → 取最后 3 个 TR：[6.0, 8.0, 10.0] → ATR = 8.0
        atr = calculate_atr(klines, window=3)
        assert abs(atr - 8.0) < 1e-9

    def test_atr_window_5(self):
        """window=5 ATR"""
        klines = _generate_klines_with_known_tr([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        # 7 根 + window=5 → 取最后 5 个 TR：[3, 4, 5, 6, 7] → ATR = 5.0
        atr = calculate_atr(klines, window=5)
        assert abs(atr - 5.0) < 1e-9


class TestAtrPct:
    def test_atr_pct_basic(self):
        """ATR 占价格的比率"""
        klines = _generate_klines_with_known_tr([2.0] * 10, base_close=100.0)
        pct = atr_pct(klines, window=3)
        # TR=2, ATR=2.0, last_close ≈ 100 → 2/100 = 0.02
        assert 0.01 < pct < 0.05

    def test_empty_klines_returns_zero(self):
        assert atr_pct([], window=14) == 0.0


# ============================================================
# _calc_stop_loss_price 测试
# ============================================================


class TestCalcStopLossPrice:
    """测试所有止损方法"""

    def test_entry_low_default(self):
        """默认 entry_low：入场 low 下方 7%"""
        klines = _generate_klines_with_known_tr([1.0] * 10)
        # 第 5 根做入场，low=101.0
        stop = _calc_stop_loss_price(klines, day_idx=5, stop_loss_pct=-0.07)
        # 构造时 high=prev+1, low=prev, close=prev+0.1
        # 第 5 根：prev = 第 4 根 close = 100 + 0.1 * 4 = 100.4
        # 第 5 根 low = 100.4
        # stop = 100.4 * 0.93 = 93.372
        assert abs(stop - 100.4 * 0.93) < 1.0

    def test_atr_based_method(self):
        """atr_based 模式：止损价 = entry close - ATR × multiplier"""
        klines = _generate_klines_with_known_tr([2.0] * 10, base_close=100.0)
        # 第 5 根入场，ATR window=3，multiplier=2
        # entry close = 100 + 0.5 = 100.5
        # ATR = 2.0 (TR 都是 2)
        # stop = 100.5 - 2 * 2 = 96.5
        stop = _calc_stop_loss_price(
            klines, day_idx=5,
            method="atr_based",
            atr_multiplier=2.0,
            atr_window=3,
        )
        assert abs(stop - (100.5 - 4.0)) < 1.0

    def test_atr_based_fallback_on_empty_data(self, monkeypatch):
        """ATR 数据不足（force 返回 0）时 fallback 到 entry_low"""
        from modules.core import atr as atr_module
        # 强制 calculate_atr 返回 0 模拟 ATR 无法计算的场景
        monkeypatch.setattr(atr_module, "calculate_atr", lambda klines, window: 0.0)
        kline1 = _make_kline("20260101", close=100.0)
        kline2 = _make_kline("20260102", close=99.0)
        stop = _calc_stop_loss_price(
            [kline1, kline2], day_idx=1,
            method="atr_based",
            stop_loss_pct=-0.05,
            atr_multiplier=2.0,
            atr_window=14,
        )
        # fallback = entry_kline.low * 0.95
        entry_kline = kline2
        assert abs(stop - entry_kline.low * 0.95) < 1e-9


# ============================================================
# calc_trailing_stop_price 测试
# ============================================================


class TestTrailingStopPrice:
    def test_basic(self):
        """最高点 100，trailing 5% → 95"""
        assert abs(calc_trailing_stop_price(100.0, -0.05) - 95.0) < 1e-9

    def test_empty_highest_returns_zero(self):
        assert calc_trailing_stop_price(0.0, -0.05) == 0.0

    def test_works_with_various_pct(self):
        """各种 trailing 比例的正确性"""
        assert abs(calc_trailing_stop_price(100.0, -0.10) - 90.0) < 1e-9
        assert abs(calc_trailing_stop_price(50.0, -0.02) - 49.0) < 1e-9


# ============================================================
# LoopConfig 向后兼容测试
# ============================================================


class TestLoopConfigBackwardCompat:
    def test_default_config_has_new_fields(self):
        """v3.10.1 新增字段都有合理默认值"""
        cfg = LoopConfig()
        assert cfg.stop_loss_method == "entry_low"
        assert cfg.atr_stop_window == 14
        assert cfg.atr_stop_multiplier == 2.0
        assert cfg.trailing_stop_enabled is False  # 默认关闭
        assert cfg.trailing_stop_pct == -0.05


class TestLoopTradeHighestTracking:
    def test_highest_after_entry_default(self):
        """LoopTrade 默认 highest=0"""
        trade = LoopTrade(
            ts_code="000001.SZ",
            entry_date="20260101",
            entry_price=100.0,
            entry_reason="B1",
            stop_loss_price=93.0,
        )
        assert trade.highest_after_entry == 0.0


# ============================================================
# ShaofuLoopEngine 集成测试
# ============================================================


class TestTrailingStopIntegration:
    """移动止损在引擎中的集成"""

    def test_trailing_stop_not_triggered_when_disabled(self):
        """trailing_stop_enabled=False 时不影响行为"""
        cfg = LoopConfig(trailing_stop_enabled=False, min_holding_days=0)
        engine = ShaofuLoopEngine(cfg)
        # 假设 trade 已存在且 highest 已经 110，但当前价 95 高于原始止损 93
        current = _make_kline("20260102", close=95.0, high=110.0, low=94.0)
        kline1 = _make_kline("20260101", close=100.0)
        klines = [kline1, current]
        trade = LoopTrade(
            ts_code="000001.SZ",
            entry_date="20260101",
            entry_price=100.0,
            entry_reason="B1",
            stop_loss_price=93.0,
            highest_after_entry=110.0,
        )
        # 95 > 93 (原始止损)，trailing 又关闭 → 不触发
        assert engine._check_stop_loss_internal(klines, day_idx=1, trade=trade) is False

    def test_trailing_stop_triggered_when_enabled(self):
        """启用 trailing 时，从高点回落超阈值则止损"""
        cfg = LoopConfig(
            trailing_stop_enabled=True,
            trailing_stop_pct=-0.05,
            min_holding_days=0,
        )
        engine = ShaofuLoopEngine(cfg)
        klines = [_make_kline("20260101", close=100.0) for _ in range(2)]
        # trade.highest = 110, trailing_stop_price = 110 * 0.95 = 104.5
        # current.close = 104 < 104.5 → 触发
        current = _make_kline("20260102", close=104.0, high=104.0, low=103.0)
        klines[1] = current
        trade = LoopTrade(
            ts_code="000001.SZ",
            entry_date="20260101",
            entry_price=100.0,
            entry_reason="B1",
            stop_loss_price=80.0,  # 远低于当前价，不触发原始止损
            highest_after_entry=110.0,
        )
        assert engine._check_stop_loss_internal(klines, day_idx=1, trade=trade) is True

    def test_trailing_stop_not_triggered_within_buffer(self):
        """价格回落但未超过 trailing 阈值：不触发"""
        cfg = LoopConfig(
            trailing_stop_enabled=True,
            trailing_stop_pct=-0.05,
            min_holding_days=0,
        )
        engine = ShaofuLoopEngine(cfg)
        klines = [_make_kline("20260101", close=100.0) for _ in range(2)]
        # high=110, trailing = 104.5
        # 当前 close=105 > 104.5 → 不触发
        current = _make_kline("20260102", close=105.0, high=110.0, low=104.0)
        klines[1] = current
        trade = LoopTrade(
            ts_code="000001.SZ",
            entry_date="20260101",
            entry_price=100.0,
            entry_reason="B1",
            stop_loss_price=80.0,
            highest_after_entry=110.0,
        )
        assert engine._check_stop_loss_internal(klines, day_idx=1, trade=trade) is False

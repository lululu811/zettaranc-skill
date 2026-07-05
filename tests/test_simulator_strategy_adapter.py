#!/usr/bin/env python3
"""战法信号适配层单元测试。"""

from __future__ import annotations

import pytest

from modules.simulator import RawStrategySignal
from modules.simulator.strategy_adapter import adapt, deduplicate, filter_by_date
from modules.strategies import Action, Priority, StrategySignal, StrategyType


def test_adapt_maps_strategy_signal():
    sig = StrategySignal(
        ts_code="000001.SZ",
        trade_date="20240101",
        strategy=StrategyType.B1,
        action=Action.BUY.value,
        confidence=0.75,
        description="B1",
        price=10.0,
    )
    raw = adapt([sig])
    assert len(raw) == 1
    assert raw[0].strategy == "B1"
    assert raw[0].category == "rebound"
    assert raw[0].action == "BUY"


def test_filter_by_date_uses_lookback():
    signals = [
        RawStrategySignal("B1", "rebound", "BUY", 0.8, "20240101"),
        RawStrategySignal("B2", "breakout", "BUY", 0.7, "20240103"),
        RawStrategySignal("S1", "risk", "SELL", 0.9, "20240108"),
    ]
    result = filter_by_date(signals, "20240105", lookback_days=5)
    assert len(result) == 2
    assert all(s.trade_date <= "20240105" for s in result)


def test_deduplicate_keeps_highest_confidence():
    signals = [
        RawStrategySignal("B1", "rebound", "BUY", 0.6, "20240101"),
        RawStrategySignal("B1", "rebound", "BUY", 0.9, "20240101"),
    ]
    result = deduplicate(signals)
    assert len(result) == 1
    assert result[0].confidence == 0.9


def test_adapt_skips_unmapped_strategy():
    sig = StrategySignal(
        ts_code="000001.SZ",
        trade_date="20240101",
        strategy=StrategyType.WATCH,
        action=Action.WATCH.value,
        confidence=0.5,
        description="未知信号",
    )
    assert adapt([sig]) == []


def test_filter_by_date_excludes_older_than_lookback():
    signals = [
        RawStrategySignal("B1", "rebound", "BUY", 0.8, "20231225"),
        RawStrategySignal("B2", "breakout", "BUY", 0.7, "20240104"),
    ]
    result = filter_by_date(signals, "20240105", lookback_days=5)
    assert len(result) == 1
    assert result[0].strategy == "B2"


def test_deduplicate_preserves_different_dates():
    signals = [
        RawStrategySignal("B1", "rebound", "BUY", 0.6, "20240101"),
        RawStrategySignal("B1", "rebound", "BUY", 0.5, "20240102"),
    ]
    result = deduplicate(signals)
    assert len(result) == 2

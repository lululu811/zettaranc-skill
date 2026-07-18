"""Walk-forward 验证测试"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from modules.core.walk_forward import WalkForwardSplit
from modules.verify.walk_forward import (
    WFResult,
    _make_splits,
    walk_forward_verify,
)


@dataclass
class FakeMetrics:
    total_return_pct: float = 0.0
    sharpe: float = 0.0


def test_wf_split_dataclass_importable():
    assert WalkForwardSplit is not None
    assert WFResult is not None


def test_wf_split_count_for_250_days():
    """250 天 / 60 天 OOS ≈ 3-4 段"""
    splits = _make_splits(total_days=250, train_days=120, test_days=60)
    assert len(splits) >= 3
    for s in splits:
        assert s.test_end > s.test_start


def test_wf_result_oos_is_ratio_basic():
    """OOS/IS 比率 = oos.sharpe / is.sharpe"""
    is_m = FakeMetrics(sharpe=1.0)
    oos_m = FakeMetrics(sharpe=0.65)
    result = WFResult(
        splits=[],
        is_metrics=is_m,
        oos_metrics=oos_m,
        oos_is_ratio=0.65,
    )
    assert result.oos_is_ratio == 0.65
    assert result.oos_metrics.sharpe < result.is_metrics.sharpe


def test_wf_verify_degrades_when_too_few_splits(caplog):
    """切片数 < 3 时降级到单次回测（返回 WFResult 但 splits 为空 + warning）"""
    result = walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=60,
        wf_train_days=40,
        wf_test_days=20,
    )
    assert isinstance(result, WFResult)


# ============================================================
# v3.7.3: 真切片测试 — mock _backtest_with_window + K-lines
# production 签名：_backtest_with_window(code, klines, config)
# ============================================================


def _fake_klines(n: int) -> list[dict]:
    """构造 n 天伪 K 线"""
    return [
        {
            "ts_code": "000001.SZ",
            "trade_date": f"2024{(i // 30 + 1):02d}{(i % 30 + 1):02d}",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "vol": 1_000_000.0,
        }
        for i in range(n)
    ]


def _make_shaofu_result_mock(sharpe: float, win_rate: float, return_pct: float):
    """构造 ShaofuBacktestResult mock"""
    mock = MagicMock()
    mock.total_trades = 5
    mock.win_rate = win_rate
    mock.total_return = return_pct
    mock.sharpe_ratio = sharpe
    mock.max_drawdown = 0.15
    mock.trades = []
    return mock


def test_wf_segments_differ_when_windowed(monkeypatch):
    """真切片：IS 段 Sharpe=1.5 / OOS 段 Sharpe=1.0，oos_is_ratio ≈ 0.67"""
    monkeypatch.setattr(
        "modules.verify.walk_forward._load_windowed_klines",
        lambda code, days: _fake_klines(days),
    )

    def fake_backtest(code, klines, config):
        # IS 窗口 = 120, OOS 窗口 = 60（最后一段可能更短）
        window_len = len(klines)
        if window_len >= 120:
            return _make_shaofu_result_mock(sharpe=1.5, win_rate=0.6, return_pct=0.05)
        return _make_shaofu_result_mock(sharpe=1.0, win_rate=0.5, return_pct=0.03)

    monkeypatch.setattr(
        "modules.verify.walk_forward._backtest_with_window",
        fake_backtest,
    )

    result = walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=300,
        wf_train_days=120,
        wf_test_days=60,
    )

    assert not result.degraded, "300 天 + 120/60 应产出 3 段"
    assert len(result.splits) == 3
    assert result.is_metrics is not None
    assert result.oos_metrics is not None
    assert abs(result.is_metrics.sharpe - 1.5) < 1e-6
    assert abs(result.oos_metrics.sharpe - 1.0) < 1e-6
    assert abs(result.oos_is_ratio - (1.0 / 1.5)) < 1e-3


def test_wf_oos_is_ratio_is_not_one_when_oos_underperforms(monkeypatch):
    """回归：v3.7.1/v3.7.2 时期 oos_is_ratio 恒为 1.0，真切片必须让 ratio 反映两段差异"""
    monkeypatch.setattr(
        "modules.verify.walk_forward._load_windowed_klines",
        lambda code, days: _fake_klines(days),
    )

    def fake_backtest(code, klines, config):
        # IS 段好，OOS 段差
        window_len = len(klines)
        if window_len >= 120:
            return _make_shaofu_result_mock(sharpe=2.0, win_rate=0.7, return_pct=0.08)
        return _make_shaofu_result_mock(sharpe=0.5, win_rate=0.3, return_pct=-0.02)

    monkeypatch.setattr(
        "modules.verify.walk_forward._backtest_with_window",
        fake_backtest,
    )

    result = walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=300,
        wf_train_days=120,
        wf_test_days=60,
    )

    assert result.oos_is_ratio < 0.5, f"OOS/IS 必须 < 0.5 才能区分两段，实际={result.oos_is_ratio:.3f}"


def test_wf_each_segment_runs_separate_backtest(monkeypatch):
    """3 段 × 2 只股 × (IS+OOS) = 12 次 _backtest_with_window"""
    monkeypatch.setattr(
        "modules.verify.walk_forward._load_windowed_klines",
        lambda code, days: _fake_klines(days),
    )
    backtest_calls: list[int] = []

    def fake_backtest(code, klines, config):
        backtest_calls.append(len(klines))
        return _make_shaofu_result_mock(sharpe=1.0, win_rate=0.5, return_pct=0.02)

    monkeypatch.setattr(
        "modules.verify.walk_forward._backtest_with_window",
        fake_backtest,
    )

    walk_forward_verify(
        ts_codes=["000001.SZ", "600000.SH"],
        days=300,
        wf_train_days=120,
        wf_test_days=60,
    )

    assert len(backtest_calls) == 12
    # IS 段窗口 = 120，OOS 段窗口 ≤ 60
    assert all(d <= 120 for d in backtest_calls)
    assert any(d <= 60 for d in backtest_calls)


def test_wf_split_indices_correspond_to_kline_offset():
    """_make_splits 切出的索引必须能映射到 klines 切片"""
    splits = _make_splits(total_days=300, train_days=120, test_days=60)
    assert len(splits) == 3
    assert splits[0].train_start == 0
    assert splits[0].train_end == 120
    assert splits[0].test_start == 120
    assert splits[0].test_end == 180
    assert splits[1].train_start == 60
    assert splits[1].train_end == 180
    assert splits[2].test_end <= 300

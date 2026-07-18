"""五项硬指标判定测试"""

from __future__ import annotations

from modules.verify.gates import (
    THRESHOLDS,
    GateResult,
    check_gates,
)
from modules.verify.pipeline import AggregateMetrics


def test_thresholds_are_five_items():
    """5 项硬指标都要在 THRESHOLDS 里"""
    assert len(THRESHOLDS) == 5
    assert "sharpe" in THRESHOLDS
    assert "calmar" in THRESHOLDS
    assert "win_rate" in THRESHOLDS
    assert "max_drawdown" in THRESHOLDS
    assert "oos_is_ratio" in THRESHOLDS


def test_check_gates_sharpe_pass():
    """Sharpe ≥ 0.5 通过"""
    metrics = AggregateMetrics(sharpe=0.73)
    gates = check_gates(metrics, wf=None)
    assert gates["sharpe"].passed is True
    assert gates["sharpe"].value == 0.73


def test_check_gates_sharpe_fail():
    """Sharpe < 0.5 失败"""
    metrics = AggregateMetrics(sharpe=0.3)
    gates = check_gates(metrics, wf=None)
    assert gates["sharpe"].passed is False
    assert "Sharpe" in gates["sharpe"].message


def test_check_gates_max_drawdown_direction_is_lower():
    """MaxDD 阈值方向是 lower（不是 higher）"""
    assert THRESHOLDS["max_drawdown"]["direction"] == "lower"


def test_check_gates_win_rate_pass_fail():
    """WinRate 阈值 0.40"""
    assert check_gates(AggregateMetrics(win_rate=0.41), wf=None)["win_rate"].passed is True
    assert check_gates(AggregateMetrics(win_rate=0.39), wf=None)["win_rate"].passed is False


def test_check_gates_calmar_pass_fail():
    """Calmar 阈值 0.50"""
    assert check_gates(AggregateMetrics(calmar=0.6), wf=None)["calmar"].passed is True
    assert check_gates(AggregateMetrics(calmar=0.3), wf=None)["calmar"].passed is False


def test_check_gates_oos_is_skipped_when_no_wf():
    """没有 WF 结果时跳过 oos_is_ratio"""
    gates = check_gates(AggregateMetrics(), wf=None)
    assert "oos_is_ratio" not in gates

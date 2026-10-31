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


class TestOosIsRatioNotApplicable:
    """OOS/IS **算不出来**时必须标为"不适用"，不能伪装成"未达标"。

    此前：IS 段 Sharpe 非正 → ratio 留 0.0 → 报告显示 "OOS/IS 0.00 ❌"，
    并计入失败项。实际是比值在数学上就没有意义（负÷负的正号取决于绝对值大小，
    是噪声不是过拟合程度）。
    """

    def test_none_ratio_marks_gate_not_applicable(self):
        class _WF:
            oos_is_ratio = None

        gates = check_gates(AggregateMetrics(sharpe=-0.8), wf=_WF())
        gate = gates["oos_is_ratio"]
        assert gate.applicable is False
        assert gate.value is None, "不适用时 value 应为 None（0.0 会被读成'比值确实是 0'）"

    def test_zero_ratio_is_applicable_and_fails_threshold(self):
        """真的算出 0.0（IS 正、OOS 零）→ 适用且未达标。"""

        class _WF:
            oos_is_ratio = 0.0

        gates = check_gates(AggregateMetrics(sharpe=0.8), wf=_WF())
        gate = gates["oos_is_ratio"]
        assert gate.applicable is True
        assert gate.passed is False

    def test_valid_ratio_uses_normal_check(self):
        class _WF:
            oos_is_ratio = 0.8

        gates = check_gates(AggregateMetrics(sharpe=0.8), wf=_WF())
        gate = gates["oos_is_ratio"]
        assert gate.applicable is True
        assert gate.passed is True

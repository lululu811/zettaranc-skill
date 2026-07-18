"""V10VerifyScorer 单元测试"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from modules.verify.pipeline import GateResult, VerifyResult, AggregateMetrics
from modules.verify.scorer import V10VerifyScorer, V10ScoreResult


def _make_passed_gates() -> dict[str, GateResult]:
    """5 个 gate 全通过"""
    return {
        "sharpe": GateResult(name="sharpe", value=1.2, threshold=0.5, passed=True),
        "calmar": GateResult(name="calmar", value=0.8, threshold=0.5, passed=True),
        "win_rate": GateResult(name="win_rate", value=0.55, threshold=0.4, passed=True),
        "max_drawdown": GateResult(name="max_drawdown", value=0.15, threshold=0.25, passed=True),
        "oos_is_ratio": GateResult(name="oos_is_ratio", value=0.7, threshold=0.6, passed=True),
    }


def _make_failed_gates() -> dict[str, GateResult]:
    """5 个 gate 全失败"""
    return {
        "sharpe": GateResult(name="sharpe", value=-0.5, threshold=0.5, passed=False),
        "calmar": GateResult(name="calmar", value=-0.2, threshold=0.5, passed=False),
        "win_rate": GateResult(name="win_rate", value=0.2, threshold=0.4, passed=False),
        "max_drawdown": GateResult(name="max_drawdown", value=0.4, threshold=0.25, passed=False),
        "oos_is_ratio": GateResult(name="oos_is_ratio", value=0.1, threshold=0.6, passed=False),
    }


def _make_mock_result(gates: dict[str, GateResult], annualized_return: float = 0.10) -> MagicMock:
    """构造带 aggregate 的 VerifyResult mock"""
    mock_aggregate = AggregateMetrics(annualized_return=annualized_return)
    mock_result = MagicMock(spec=VerifyResult)
    mock_result.gates = gates
    mock_result.aggregate = mock_aggregate
    return mock_result


def test_score_with_all_gates_passed_returns_high_fit():
    """5/5 通过 → fit = 10*5 + 2*1.2 + 5*0.8 + 20*0.10 = 63.6"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    mock_result = _make_mock_result(_make_passed_gates(), annualized_return=0.10)

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result):
        out = scorer.score({"j_threshold": 8})

    assert isinstance(out, V10ScoreResult)
    assert out.passed_count == 5
    assert out.total_count == 5
    # fit = 10*5 + 2*1.2 + 5*0.8 + 20*0.10 = 50 + 2.4 + 4.0 + 2.0 = 58.4
    assert abs(out.fit - 58.4) < 1e-6
    assert out.calmar == 0.8
    assert out.annualized_return == 0.10
    assert out.error == ""


def test_score_with_all_gates_failed_returns_low_fit():
    """0/5 通过 + 全部负值 → fit ≥ 0（calmar/annualized_return 取 max(0, …)）"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    mock_result = _make_mock_result(_make_failed_gates(), annualized_return=-0.05)

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result):
        out = scorer.score({"stop_loss_pct": -0.07})

    assert out.passed_count == 0
    assert out.fit >= 0.0  # 所有项 max(0, x) 都 ≥ 0
    assert out.error == ""


def test_score_handles_pipeline_exception_without_crashing():
    """verify_v10_pipeline 抛异常 → 不传播，返回 fit=0+error"""
    pool = ["999999.SH"]  # 不存在
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    with patch(
        "modules.verify.scorer.verify_v10_pipeline",
        side_effect=RuntimeError("Tushare rate limit"),
    ):
        out = scorer.score({"j_threshold": 12})

    assert out.passed_count == 0
    assert "Tushare rate limit" in out.error
    assert out.fit == 0.0


def test_scorer_passes_use_portfolio_engine_to_pipeline():
    """V10VerifyScorer 默认把 use_portfolio_engine=True 传给 pipeline"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    mock_result = _make_mock_result(_make_passed_gates())

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result) as mock_pipe:
        scorer.score({"j_threshold": 12})

    call_kwargs = mock_pipe.call_args.kwargs
    assert call_kwargs.get("use_portfolio_engine") is True


def test_scorer_can_disable_portfolio_engine():
    """关闭组合引擎时传给 pipeline False"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240, use_portfolio_engine=False)

    mock_result = _make_mock_result(_make_passed_gates())

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result) as mock_pipe:
        scorer.score({"j_threshold": 12})

    call_kwargs = mock_pipe.call_args.kwargs
    assert call_kwargs.get("use_portfolio_engine") is False


def test_score_emits_partial_pass_count():
    """1/5 通过（max_drawdown）→ passed_count=1, 其余负值，fit = 10*1 + 0 + 0 + 0 = 10"""
    pool = ["600487.SH"]
    scorer = V10VerifyScorer(stock_pool=pool, days=240)

    gates = _make_passed_gates()
    gates["sharpe"].passed = False
    gates["sharpe"].value = -0.3
    gates["calmar"].passed = False
    gates["calmar"].value = -0.1
    gates["win_rate"].passed = False
    gates["win_rate"].value = 0.2
    gates["oos_is_ratio"].passed = False
    gates["oos_is_ratio"].value = 0.1
    # 只留 max_drawdown 通过；annualized_return 设成 -0.02（负值）

    mock_result = _make_mock_result(gates, annualized_return=-0.02)

    with patch("modules.verify.scorer.verify_v10_pipeline", return_value=mock_result):
        out = scorer.score({"j_threshold": 12})

    assert out.passed_count == 1
    assert out.total_count == 5
    # fit = 10*1 + 2*max(0, -0.3) + 5*max(0, -0.1) + 20*max(0, -0.02) = 10
    assert abs(out.fit - 10.0) < 1e-6

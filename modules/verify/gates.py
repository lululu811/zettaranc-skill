"""
五项硬指标自动达标判定

阈值集中化（spec：Sharpe/Calmar/WinRate/MaxDD/OOS_IS）

注意：GateResult 在 pipeline.py 定义（避免重复定义）
"""

from __future__ import annotations

from .pipeline import AggregateMetrics, GateResult


# 阈值集中化（spec Global Constraints）
THRESHOLDS: dict[str, dict] = {
    "sharpe": {"min": 0.5, "direction": "higher", "label": "Sharpe"},
    "calmar": {"min": 0.5, "direction": "higher", "label": "Calmar"},
    "win_rate": {"min": 0.40, "direction": "higher", "label": "WinRate"},
    "max_drawdown": {"max": 0.25, "direction": "lower", "label": "MaxDD"},
    "oos_is_ratio": {"min": 0.60, "direction": "higher", "label": "OOS/IS"},
}


__all__ = ["THRESHOLDS", "GateResult", "check_gates"]


def check_gates(
    metrics: AggregateMetrics,
    wf: object | None = None,  # WFResult, Task 6 定义
) -> dict[str, GateResult]:
    """
    五项硬指标自动判定：
    - 优先 4 项（Sharpe/Calmar/WinRate/MaxDD）从 metrics 取
    - OOS/IS 仅在 wf 不为 None 时判定
    - 失败时给改进建议
    """
    gates: dict[str, GateResult] = {}

    # 1. Sharpe
    gates["sharpe"] = _check_higher(
        "sharpe",
        metrics.sharpe,
        THRESHOLDS["sharpe"]["min"],
        "Sharpe",
        "增大收益弹性 / 降低波动",
    )

    # 2. Calmar
    gates["calmar"] = _check_higher(
        "calmar",
        metrics.calmar,
        THRESHOLDS["calmar"]["min"],
        "Calmar",
        "提升年化收益或降低回撤",
    )

    # 3. WinRate
    gates["win_rate"] = _check_higher(
        "win_rate",
        metrics.win_rate,
        THRESHOLDS["win_rate"]["min"],
        "WinRate",
        "收紧入场条件（如降低 j_threshold）",
    )

    # 4. MaxDD（方向是 lower）
    gates["max_drawdown"] = _check_lower(
        "max_drawdown",
        metrics.max_drawdown,
        THRESHOLDS["max_drawdown"]["max"],
        "MaxDD",
        "收紧止损至 -3%（当前 -5%）",
    )

    # 5. OOS/IS（仅在 wf 不为 None 时）
    if wf is not None and hasattr(wf, "oos_is_ratio"):
        gates["oos_is_ratio"] = _check_higher(
            "oos_is_ratio",
            wf.oos_is_ratio,
            THRESHOLDS["oos_is_ratio"]["min"],
            "OOS/IS",
            "减少过拟合风险（缩小参数搜索空间）",
        )

    return gates


def _check_higher(
    name: str,
    value: float,
    threshold: float,
    label: str,
    suggestion: str,
) -> GateResult:
    passed = value >= threshold
    msg = "" if passed else f"{label} {value:.2f} < {threshold:.2f}，建议：{suggestion}"
    return GateResult(
        name=name,
        value=value,
        threshold=threshold,
        passed=passed,
        message=msg,
    )


def _check_lower(
    name: str,
    value: float,
    threshold: float,
    label: str,
    suggestion: str,
) -> GateResult:
    passed = value <= threshold
    msg = "" if passed else f"{label} {value:.2%} > {threshold:.2%}，建议：{suggestion}"
    return GateResult(
        name=name,
        value=value,
        threshold=threshold,
        passed=passed,
        message=msg,
    )

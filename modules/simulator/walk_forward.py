#!/usr/bin/env python3
"""
Walk-forward 参数寻优执行层。

实现滚动窗口切分、参数搜索、OOS 拼接。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import statistics

from . import SimulationConfig, SimulationResult
from .param_space import ParamDimension, generate_grid, DEFAULT_PARAM_SPACE
from .simulator import run_simulation, _available_dates
from .metrics import PerformanceMetrics, calculate_metrics
from ..core.walk_forward import make_walk_forward_splits
from ..datasource import DataSource, get_datasource


@dataclass
class WalkForwardConfig:
    """Walk-forward 配置"""

    train_days: int = 120
    test_days: int = 60
    objective: str = "calmar"  # "calmar" | "sharpe" | "sortino" | "total_return"
    param_space: list[ParamDimension] = field(default_factory=lambda: DEFAULT_PARAM_SPACE.copy())
    anchored: bool = False  # True = 训练窗口从起点固定增长；False = 固定长度滑动


@dataclass
class WalkForwardWindow:
    """单个窗口的 IS/OOS 结果"""

    window_index: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str
    best_params: dict[str, Any]
    is_score: float
    oos_score: float
    is_result: SimulationResult
    oos_result: SimulationResult


@dataclass
class WalkForwardResult:
    """Walk-forward 完整结果"""

    config: WalkForwardConfig
    windows: list[WalkForwardWindow]
    oos_equity_curve: list[dict[str, Any]]
    oos_metrics: PerformanceMetrics
    overfit_ratio: float  # IS 平均收益 / OOS 平均收益


def _split_windows(
    dates: list[str],
    train_days: int,
    test_days: int,
    anchored: bool,
) -> list[tuple[int, int, int]]:
    """
    切分窗口。

    Returns:
        [(is_start_idx, oos_start_idx, oos_end_idx), ...]
    """
    total_days = len(dates)
    if not anchored:
        # 使用 core 模块的公共切分逻辑
        core_splits = make_walk_forward_splits(
            total_days=total_days,
            train_days=train_days,
            test_days=test_days,
            allow_partial_last=False,
        )
        return [(s.train_start, s.test_start, s.test_end) for s in core_splits]

    # anchored 模式：训练窗口从起点固定增长
    windows = []
    step = test_days
    for oos_end_idx in range(train_days + test_days, total_days + 1, step):
        oos_start_idx = oos_end_idx - test_days
        windows.append((0, oos_start_idx, oos_end_idx))
    return windows


def _evaluate(result: SimulationResult, objective: str) -> float:
    """根据目标函数计算得分。"""
    if not result.metrics:
        return 0.0

    if objective == "calmar":
        return result.metrics.calmar_ratio
    elif objective == "sharpe":
        return result.metrics.sharpe_ratio
    elif objective == "sortino":
        return result.metrics.sortino_ratio
    elif objective == "total_return":
        return result.metrics.total_return
    else:
        return 0.0


def _run_with_params(
    ts_codes: list[str] | None,
    dates: list[str],
    start_idx: int,
    end_idx: int,
    params: dict[str, Any],
    base_config: SimulationConfig,
    datasource: DataSource,
) -> SimulationResult:
    """用指定参数在指定日期范围内运行回测。"""
    # 合并参数
    config_dict = base_config.__dict__.copy()
    config_dict.update(params)
    config = SimulationConfig(**config_dict)

    # 截取日期范围
    start_date = dates[start_idx]
    end_date = dates[end_idx - 1]

    return run_simulation(
        ts_codes=ts_codes,
        days=end_idx - start_idx,
        config=config,
        datasource=datasource,
        start_date=start_date,
        end_date=end_date,
    )


def run_walk_forward(
    ts_codes: list[str] | None,
    total_days: int,
    wf_config: WalkForwardConfig,
    base_config: SimulationConfig,
    datasource: DataSource | None = None,
) -> WalkForwardResult:
    """
    执行 walk-forward 参数寻优。

    Args:
        ts_codes: 股票池
        total_days: 总回测天数
        wf_config: walk-forward 配置
        base_config: 基础模拟配置（不含待优化参数）
        datasource: 数据源

    Returns:
        WalkForwardResult
    """
    ds = datasource or get_datasource()

    # 获取总日期序列
    first_code = ts_codes[0] if ts_codes else "000001.SZ"
    dates = _available_dates(first_code, days=total_days, datasource=ds)

    if len(dates) < wf_config.train_days + wf_config.test_days:
        # 数据不足，返回空结果
        return WalkForwardResult(
            config=wf_config,
            windows=[],
            oos_equity_curve=[],
            oos_metrics=PerformanceMetrics(),
            overfit_ratio=1.0,
        )

    # 切分窗口
    windows_spec = _split_windows(dates, wf_config.train_days, wf_config.test_days, wf_config.anchored)

    # 生成参数网格
    param_grid = generate_grid(wf_config.param_space)

    # 执行每个窗口
    windows: list[WalkForwardWindow] = []
    all_oos_curves: list[dict[str, Any]] = []
    is_scores: list[float] = []
    oos_scores: list[float] = []

    for window_idx, (is_start_idx, oos_start_idx, oos_end_idx) in enumerate(windows_spec):
        # 在 IS 上搜索最佳参数
        best_params = None
        best_score = float("-inf")

        for params in param_grid:
            result = _run_with_params(ts_codes, dates, is_start_idx, oos_start_idx, params, base_config, ds)
            score = _evaluate(result, wf_config.objective)

            if score > best_score:
                best_score = score
                best_params = params

        # 用最佳参数在 OOS 上验证
        oos_result = _run_with_params(ts_codes, dates, oos_start_idx, oos_end_idx, best_params or {}, base_config, ds)
        oos_score = _evaluate(oos_result, wf_config.objective)

        # 记录 IS 结果（用最佳参数重新跑 IS 段）
        is_result = _run_with_params(ts_codes, dates, is_start_idx, oos_start_idx, best_params or {}, base_config, ds)

        windows.append(
            WalkForwardWindow(
                window_index=window_idx,
                is_start=dates[is_start_idx],
                is_end=dates[oos_start_idx - 1],
                oos_start=dates[oos_start_idx],
                oos_end=dates[oos_end_idx - 1],
                best_params=best_params or {},
                is_score=best_score,
                oos_score=oos_score,
                is_result=is_result,
                oos_result=oos_result,
            )
        )

        # 拼接 OOS 资金曲线（使用 equity_details 以保持 dict 格式供 calculate_metrics 使用）
        oos_details = getattr(oos_result, "equity_details", [])
        all_oos_curves.extend(oos_details if oos_details else [{"equity": v} for v in oos_result.equity_curve])
        is_scores.append(best_score)
        oos_scores.append(oos_score)

    # 计算 OOS 统计指标
    oos_metrics = calculate_metrics(all_oos_curves, [], [])

    # 计算过拟合比率
    mean_is = statistics.mean(is_scores) if is_scores else 0.0
    mean_oos = statistics.mean(oos_scores) if oos_scores else 0.0
    overfit_ratio = mean_is / max(mean_oos, 1e-6)

    return WalkForwardResult(
        config=wf_config,
        windows=windows,
        oos_equity_curve=all_oos_curves,
        oos_metrics=oos_metrics,
        overfit_ratio=overfit_ratio,
    )

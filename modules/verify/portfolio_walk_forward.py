"""
组合级 Walk-forward 验证（v3.7.7）+ v3.10.2 自适应参数寻优

基于 PortfolioBacktestEngine 的组合净值序列做真切片：
  - IS 段：用训练窗口内的交易日跑组合回测
  - OOS 段：用测试窗口内的交易日跑组合回测
  - OOS/IS 比率 = OOS Sharpe / IS Sharpe

与单股 walk_forward_verify 的区别：
  - 单股版：每段对每只股票独立跑 backtest_shaofu_single，再平均 Sharpe
  - 组合版：每段跑整个 PortfolioBacktestEngine，从组合净值曲线计算指标

v3.10.2 新增 `portfolio_grid_search_optimize`：在 IS 段上穷举参数网格，
按目标指标（如 calmar）选最优组合，避免 OOS 过拟合。
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from ..loop_engine import LoopConfig
from ..simulator.param_space import ParamDimension, generate_grid
from .pipeline import AggregateMetrics
from .portfolio_engine import PortfolioBacktestEngine, PortfolioBacktestResult, PortfolioConfig
from .walk_forward import WFResult, _make_splits

logger = logging.getLogger(__name__)


def portfolio_walk_forward_verify(
    ts_codes: list[str],
    days: int = 250,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: object | None = None,
    portfolio_config: PortfolioConfig | None = None,
) -> WFResult:
    """组合级 Walk-forward 验证

    Args:
        ts_codes: 候选股票池
        days: 总回测天数
        wf_train_days: IS 窗口长度
        wf_test_days: OOS 窗口长度
        config: LoopConfig（少妇战法参数）
        portfolio_config: PortfolioConfig（组合账户参数）

    Returns:
        WFResult（is_metrics / oos_metrics / oos_is_ratio / degraded）
    """
    engine = PortfolioBacktestEngine(
        portfolio_config=portfolio_config,
        loop_config=config,
    )

    klines_map, all_dates = engine.load_data(ts_codes, days)
    if not all_dates:
        logger.warning("组合 WF：无交易日数据，降级")
        return WFResult(splits=[], degraded=True)

    total_days = len(all_dates)
    splits = _make_splits(total_days, wf_train_days, wf_test_days)

    if len(splits) < 3:
        logger.warning(
            "组合 WF 切片数=%d < 3，降级为单次回测（不计算 OOS/IS）",
            len(splits),
        )
        return WFResult(splits=[], degraded=True)

    is_results: list[PortfolioBacktestResult] = []
    oos_results: list[PortfolioBacktestResult] = []

    for split in splits:
        is_start = all_dates[split.train_start]
        is_end = all_dates[split.train_end - 1]
        oos_start = all_dates[split.test_start]
        oos_end = all_dates[split.test_end - 1]

        logger.debug(
            "组合 WF 切片: IS[%s-%s] OOS[%s-%s]",
            is_start,
            is_end,
            oos_start,
            oos_end,
        )

        try:
            is_result = engine.run_with_data(
                klines_map,
                all_dates,
                start_date=is_start,
                end_date=is_end,
            )
            oos_result = engine.run_with_data(
                klines_map,
                all_dates,
                start_date=oos_start,
                end_date=oos_end,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("组合 WF 切片运行失败: %s", e)
            continue

        # 仅当段内有足够交易时才计入 Sharpe 等统计，避免 0 分母
        if is_result.total_trades >= 3:
            is_results.append(is_result)
        if oos_result.total_trades >= 3:
            oos_results.append(oos_result)

    is_metrics = _aggregate_portfolio_results(is_results)
    oos_metrics = _aggregate_portfolio_results(oos_results)

    oos_is_ratio = 0.0
    if is_metrics.sharpe > 0.001:
        oos_is_ratio = oos_metrics.sharpe / is_metrics.sharpe

    return WFResult(
        splits=splits,
        is_metrics=is_metrics,
        oos_metrics=oos_metrics,
        oos_is_ratio=oos_is_ratio,
        degraded=False,
    )


def _aggregate_portfolio_results(
    results: list[PortfolioBacktestResult],
) -> AggregateMetrics:
    """把多段组合回测结果聚合为 AggregateMetrics"""
    if not results:
        return AggregateMetrics()

    total_trades = sum(r.total_trades for r in results)
    wins = sum(r.win_count for r in results)
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    n = len(results)
    total_return = sum(r.total_return for r in results) / n
    annualized_return = sum(r.annualized_return for r in results) / n
    sharpe = sum(r.sharpe_ratio for r in results) / n
    calmar = sum(r.calmar for r in results) / n
    max_drawdown = max(r.max_drawdown for r in results) if results else 0.0

    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        annualized_return=annualized_return,
        sharpe=sharpe,
        calmar=calmar,
        max_drawdown=max_drawdown,
    )


# ============================================================
# v3.10.2：参数网格搜索寻优
# ============================================================


@dataclass
class GridSearchResult:
    """网格搜索单条结果（参数 + 在 IS 段的聚合指标）"""

    params: dict[str, Any] = field(default_factory=dict)
    metrics: AggregateMetrics = field(default_factory=AggregateMetrics)
    total_trades: int = 0


@dataclass
class GridSearchReport:
    """网格搜索完整报告（多条 GridSearchResult + 最佳）"""

    results: list[GridSearchResult] = field(default_factory=list)
    best: GridSearchResult | None = None
    objective: str = "sharpe"


# v3.10.2 默认参数空间：聚焦 LoopConfig 字段（战法核心参数）
DEFAULT_PORTFOLIO_PARAM_SPACE: list[ParamDimension] = [
    # J 值阈值（B1 入场）：负值更激进，12 是默认
    ParamDimension("j_threshold", "choice", choices=[6, 12, 18]),
    # 单笔仓位比例（0.20 / 0.30 / 0.40）
    ParamDimension("position_pct", "choice", choices=[0.20, 0.30, 0.40]),
    # 止损比例（-0.03 / -0.05 / -0.07 → 宽到紧）
    ParamDimension("stop_loss_pct", "choice", choices=[-0.03, -0.05, -0.07]),
    # ATR 止损距离倍数（1.5 / 2.0 / 3.0）
    ParamDimension("atr_stop_multiplier", "choice", choices=[1.5, 2.0, 3.0]),
]


# 允许通过参数名修改的 LoopConfig 字段白名单（防误改）
_LOOP_CONFIG_FIELDS = set(LoopConfig().__dict__.keys())


def portfolio_grid_search_optimize(
    ts_codes: list[str],
    days: int = 250,
    param_space: list[ParamDimension] | None = None,
    objective: str = "sharpe",
    base_loop_config: LoopConfig | None = None,
    base_portfolio_config: PortfolioConfig | None = None,
    min_trades_per_segment: int = 3,
) -> GridSearchReport:
    """组合回测参数网格搜索（v3.10.2）

    在 IS 训练段（默认前 60% 交易日）上穷举 param_space 的笛卡尔积，
    对每组参数跑一次 PortfolioBacktestEngine，按 objective 排序选最优。

    Args:
        ts_codes: 候选股票池
        days: 回测天数
        param_space: 参数维度列表，None 用 DEFAULT_PORTFOLIO_PARAM_SPACE
        objective: 排序目标（"sharpe"/"calmar"/"annualized_return"）
        base_loop_config: 基础 LoopConfig
        base_portfolio_config: 基础 PortfolioConfig
        min_trades_per_segment: 交易数低于此值不计入

    Returns:
        GridSearchReport（results + best + objective）
    """
    if param_space is None:
        param_space = DEFAULT_PORTFOLIO_PARAM_SPACE
    base_loop = base_loop_config or LoopConfig()
    base_portfolio = base_portfolio_config or PortfolioConfig()

    grid = generate_grid(param_space)
    logger.info(
        "v3.10.2 网格搜索：%d 个组合 × %d 只股票 × %d 天",
        len(grid),
        len(ts_codes),
        days,
    )

    # 预加载数据（避免每组参数重复拉取）
    probe = PortfolioBacktestEngine(
        portfolio_config=base_portfolio,
        loop_config=base_loop,
    )
    klines_map, all_dates = probe.load_data(ts_codes, days)
    if not all_dates:
        logger.warning("v3.10.2 网格搜索：无交易日数据")
        return GridSearchReport(objective=objective)

    # 用前 60% 作 IS（剩余 40% 留给 OOS 验证）
    cut_idx = max(int(len(all_dates) * 0.6), 30)
    is_start = all_dates[0]
    is_end = all_dates[cut_idx - 1]

    results: list[GridSearchResult] = []
    for params in grid:
        invalid = set(params.keys()) - _LOOP_CONFIG_FIELDS
        if invalid:
            logger.warning("网格参数 %s 不在 LoopConfig 中，跳过", invalid)
            continue
        try:
            loop_cfg = copy.deepcopy(base_loop)
            for k, v in params.items():
                setattr(loop_cfg, k, v)
            engine = PortfolioBacktestEngine(
                portfolio_config=base_portfolio,
                loop_config=loop_cfg,
            )
            is_result = engine.run_with_data(
                klines_map,
                all_dates,
                start_date=is_start,
                end_date=is_end,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("网格 %s 失败: %s", params, e)
            continue

        if is_result.total_trades >= min_trades_per_segment:
            metrics = _aggregate_portfolio_results([is_result])
        else:
            metrics = AggregateMetrics()
        results.append(
            GridSearchResult(
                params=params,
                metrics=metrics,
                total_trades=is_result.total_trades,
            )
        )

    def _score(r: GridSearchResult) -> float:
        if not hasattr(r.metrics, objective):
            return float("-inf")
        return float(getattr(r.metrics, objective))

    results.sort(key=_score, reverse=True)
    best = results[0] if results else None

    return GridSearchReport(results=results, best=best, objective=objective)


__all__ = [
    "portfolio_walk_forward_verify",
    "_aggregate_portfolio_results",
    "portfolio_grid_search_optimize",
    "GridSearchResult",
    "GridSearchReport",
    "DEFAULT_PORTFOLIO_PARAM_SPACE",
]

"""
v1.0 验收统一管线

调用现有 backtest_shaofu_portfolio / metrics / param_registry，
不修改任何现有模块的内部逻辑。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from modules.backtest_six_step import backtest_shaofu_single
from modules.core.metrics import TRADING_DAYS_PER_YEAR, compute_drawdown, compute_sharpe, daily_returns
from modules.datasource import get_datasource
from modules.loop_engine import LoopConfig, LoopTrade

logger = logging.getLogger(__name__)

MIN_KLINE_DAYS = 60  # 少于这个天数视为数据不足


@dataclass
class StockResult:
    """单股回测结果"""

    ts_code: str
    name: str
    trades: int
    win_rate: float
    return_pct: float
    sharpe: float
    max_drawdown: float
    skipped: bool = False
    skip_reason: str = ""
    equity_curve: list[float] = field(default_factory=list)  # v3.7.4 组合级指标用


@dataclass
class AggregateMetrics:
    """组合级聚合指标"""

    total_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    annualized_return: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0


@dataclass
class GateResult:
    """单项硬指标判定结果"""

    name: str
    value: float
    threshold: float
    passed: bool
    message: str = ""


@dataclass
class VerifyResult:
    """v1.0 验收聚合结果"""

    per_stock: list[StockResult] = field(default_factory=list)
    aggregate: AggregateMetrics = field(default_factory=AggregateMetrics)
    gates: dict[str, GateResult] = field(default_factory=dict)
    config_used: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def _load_klines_with_precheck(
    ts_codes: list[str],
    days: int,
) -> list[StockResult]:
    """
    加载 K 线 + 数据预检。
    返回 list[StockResult]，数据不足的股票标记 skipped=True。
    """
    ds = get_datasource(preferred="auto")
    results: list[StockResult] = []

    for code in ts_codes:
        try:
            klines = ds.get_kline_dicts(code, days=days)
            if not klines or len(klines) < MIN_KLINE_DAYS:
                results.append(
                    StockResult(
                        ts_code=code,
                        name="",
                        trades=0,
                        win_rate=0.0,
                        return_pct=0.0,
                        sharpe=0.0,
                        max_drawdown=0.0,
                        skipped=True,
                        skip_reason=f"K线<{MIN_KLINE_DAYS}天",
                    )
                )
                continue
            results.append(
                StockResult(
                    ts_code=code,
                    name="",
                    trades=0,
                    win_rate=0.0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_drawdown=0.0,
                    skipped=False,
                )
            )
        except Exception as e:  # noqa: BLE001 - 单股加载失败不应中断整个组合
            logger.warning("加载 %s 失败: %s", code, e)
            results.append(
                StockResult(
                    ts_code=code,
                    name="",
                    trades=0,
                    win_rate=0.0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_drawdown=0.0,
                    skipped=True,
                    skip_reason=f"加载异常: {e!s:.50}",
                )
            )

    return results


def _run_single_stock_backtest(
    ts_code: str,
    days: int,
    config: LoopConfig | None = None,
) -> StockResult:
    """调 backtest_shaofu_single 返回 StockResult

    v4.0.2：优先走 Rust bridge（`run_single_strategy_backtest_py`），
    Rust 不可用 / 抛错时 silent fallback 到 Python `backtest_shaofu_single`。
    任何回测异常都不抛出，整体捕获后返回 skipped=True 的 StockResult，
    保证组合回测中单股失败不会中断整个流水线。
    """
    try:
        # v4.0.2：bridge 层 silent fallback；Python 路径保留以兼容旧行为
        from modules.backtest._rust_bridge import (
            compute_func,
            is_rust_available,
        )

        # is_rust_available 内部捕获 RuntimeError（impl=rust 但模块缺失时），
        # 这里只关心"能不能走 Rust"，不让 RuntimeError 杀掉整个 verify 流水线。
        if is_rust_available():
            rust_fn = compute_func("run_single_strategy_backtest_py")
            if rust_fn is not None:
                try:
                    # 拉 K 线 → dict，调 Rust，schema 映射回 CLI dict
                    from modules.indicators import get_kline_data

                    klines = get_kline_data(ts_code, days)
                    if klines:
                        kline_dicts = [
                            k.model_dump() if hasattr(k, "model_dump")
                            else dict(k.__dict__) if hasattr(k, "__dict__")
                            else {
                                "trade_date": getattr(k, "trade_date", ""),
                                "open": getattr(k, "open", 0.0),
                                "high": getattr(k, "high", 0.0),
                                "low": getattr(k, "low", 0.0),
                                "close": getattr(k, "close", 0.0),
                                "vol": getattr(k, "vol", 0.0),
                            }
                            for k in klines
                        ]
                        rust_result = rust_fn({}, kline_dicts)
                        from modules.backtest._rust_bridge import (
                            rust_single_result_to_cli_dict,
                        )

                        equity_curve = rust_result.get("equity_curve", []) or []
                        cli_dict = rust_single_result_to_cli_dict(ts_code, rust_result)
                        return StockResult(
                            ts_code=ts_code,
                            name=getattr(rust_result, "name", ""),
                            trades=cli_dict["total_trades"],
                            win_rate=cli_dict["win_rate"],
                            return_pct=cli_dict["total_return"] / 100.0,
                            sharpe=cli_dict["sharpe_ratio"],
                            max_drawdown=cli_dict["max_drawdown"] / 100.0,
                            skipped=False,
                            equity_curve=list(equity_curve),
                        )
                except Exception as e:  # noqa: BLE001 - 单 Rust call 失败不应中断流水线
                    logger.warning(
                        "verify: Rust 回测 %s 失败，fallback Python: %s", ts_code, e
                    )

        # Python fallback
        # backtest_shaofu_single 返回 ShaofuBacktestResult（dataclass）
        result = backtest_shaofu_single(ts_code, days=days, config=config)
        # ShaofuBacktestResult 字段：total_trades, win_count, win_rate,
        # total_return, sharpe_ratio, max_drawdown, equity_curve
        return StockResult(
            ts_code=ts_code,
            name=getattr(result, "name", ""),
            trades=result.total_trades,
            win_rate=result.win_rate,
            return_pct=result.total_return,
            sharpe=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            skipped=False,
            equity_curve=list(getattr(result, "equity_curve", [])),
        )
    except Exception as e:  # noqa: BLE001 - 单股回测失败不应中断整个组合
        logger.warning("回测 %s 失败: %s", ts_code, e)
        return StockResult(
            ts_code=ts_code,
            name="",
            trades=0,
            win_rate=0.0,
            return_pct=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            skipped=True,
            skip_reason=f"回测异常: {e!s:.50}",
        )


def verify_v10_pipeline(
    ts_codes: list[str],
    days: int = 250,
    config: LoopConfig | None = None,
    walk_forward: bool = False,  # Task 6 实现
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    use_portfolio_engine: bool = False,  # v3.7.6 组合引擎
    portfolio_config: object | None = None,  # PortfolioConfig
) -> VerifyResult:
    """
    v1.0 验收流水线（完整版）：
    1. 加载 K 线（带数据预检）
    2. 逐股回测（调 backtest_shaofu_single）
    3. 聚合组合级指标
    4. （Task 5 加入 gates 判定）
    5. （Task 6 加入 walk_forward 分支）
    6. （v3.7.6 加入 use_portfolio_engine 分支）
    """
    logger.info(
        "verify_v10_pipeline 启动: stocks=%d, days=%d, wf=%s, portfolio=%s",
        len(ts_codes),
        days,
        walk_forward,
        use_portfolio_engine,
    )
    meta = {
        "ts_codes_count": len(ts_codes),
        "days": days,
        "walk_forward": walk_forward,
        "use_portfolio_engine": use_portfolio_engine,
        "skipped_count": 0,
    }

    # 0. config 为 None 时尝试从 registry 读，读不到再用 LoopConfig 默认值兜底
    if config is None:
        config = LoopConfig.from_registry("shaofu_v1") or LoopConfig()
        meta["config_source"] = "param_registry:shaofu_v1" if config is not None else "loop_engine:default"
    else:
        meta["config_source"] = "user:explicit"

    if not ts_codes:
        return VerifyResult(meta={**meta, "empty_input": True})

    # v3.7.6 分支：真实组合级回测引擎
    if use_portfolio_engine:
        return _run_portfolio_engine_branch(
            ts_codes=ts_codes,
            days=days,
            config=config,
            walk_forward=walk_forward,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            portfolio_config=portfolio_config,
            meta=meta,
        )

    # 1. 数据预检
    prechecked = _load_klines_with_precheck(ts_codes, days)
    skipped_count = sum(1 for r in prechecked if r.skipped)
    meta["skipped_count"] = skipped_count

    # 2. 逐股回测
    per_stock: list[StockResult] = []
    for pre in prechecked:
        if pre.skipped:
            per_stock.append(pre)
            continue
        result = _run_single_stock_backtest(pre.ts_code, days, config)
        per_stock.append(result)

    # 3. 聚合
    aggregate = _aggregate_metrics(per_stock, days)

    # 4. Gates 判定（Task 5）
    # 4.5 Walk-forward（如果启用，Task 6）
    wf_result = None
    if walk_forward and not meta.get("empty_input"):
        from .walk_forward import walk_forward_verify

        wf_result = walk_forward_verify(
            ts_codes=ts_codes,
            days=days,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            config=config,
        )
        meta["wf_degraded"] = wf_result.degraded
        meta["wf_splits"] = len(wf_result.splits)

    from .gates import check_gates

    gates = check_gates(aggregate, wf=wf_result)

    return VerifyResult(
        per_stock=per_stock,
        aggregate=aggregate,
        gates=gates,
        config_used=_config_to_dict(config),
        meta=meta,
    )


def _run_portfolio_engine_branch(
    ts_codes: list[str],
    days: int,
    config: LoopConfig,
    walk_forward: bool,
    wf_train_days: int,
    wf_test_days: int,
    portfolio_config: object | None,
    meta: dict,
) -> VerifyResult:
    """v3.7.6 组合引擎分支"""
    from .portfolio_engine import PortfolioBacktestEngine, PortfolioConfig

    config = config or LoopConfig()
    pc = portfolio_config or PortfolioConfig(
        initial_capital=1_000_000.0,
        max_positions=5,
        position_pct=config.position_pct,
    )
    engine = PortfolioBacktestEngine(portfolio_config=pc, loop_config=config)
    pb_result = engine.run(ts_codes, days=days)

    # 转换 AggregateMetrics
    aggregate = AggregateMetrics(
        total_trades=pb_result.total_trades,
        win_rate=pb_result.win_rate,
        total_return_pct=pb_result.total_return,
        annualized_return=pb_result.annualized_return,
        sharpe=pb_result.sharpe_ratio,
        calmar=pb_result.calmar,
        max_drawdown=pb_result.max_drawdown,
    )

    # per_stock：从组合交易的完成交易中分组聚合
    per_stock = _portfolio_trades_to_stock_results(pb_result.trades)

    # Walk-forward：组合引擎使用组合净值序列真切片
    wf_result = None
    if walk_forward:
        from .portfolio_walk_forward import portfolio_walk_forward_verify

        wf_result = portfolio_walk_forward_verify(
            ts_codes=ts_codes,
            days=days,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            config=config,
            portfolio_config=pc,
        )
        meta["wf_degraded"] = wf_result.degraded
        meta["wf_splits"] = len(wf_result.splits)
        meta["portfolio_engine_walk_forward_note"] = "组合净值序列真切片"

    from .gates import check_gates

    gates = check_gates(aggregate, wf=wf_result)

    return VerifyResult(
        per_stock=per_stock,
        aggregate=aggregate,
        gates=gates,
        config_used=_config_to_dict(config),
        meta=meta,
    )


def _portfolio_trades_to_stock_results(trades: list[LoopTrade]) -> list[StockResult]:
    """把组合引擎完成的 LoopTrade 按 ts_code 聚合为 StockResult 列表"""
    from collections import defaultdict

    grouped: dict[str, list[LoopTrade]] = defaultdict(list)
    for t in trades:
        grouped[t.ts_code].append(t)

    results: list[StockResult] = []
    for code, group in grouped.items():
        wins = sum(1 for t in group if t.pnl_pct > 0)
        total = len(group)

        # 单股资金曲线（按仓位复利）
        equity = 100.0
        curve = [equity]
        for t in group:
            pos_pct = getattr(t, "position_pct", 1.0) or 1.0
            equity *= 1 + (t.pnl_pct / 100.0) * pos_pct
            curve.append(equity)

        total_return = curve[-1] / curve[0] - 1.0 if curve else 0.0
        max_dd, _ = compute_drawdown(curve)

        results.append(
            StockResult(
                ts_code=code,
                name="",
                trades=total,
                win_rate=wins / total if total > 0 else 0.0,
                return_pct=total_return,
                sharpe=0.0,
                max_drawdown=max_dd,
                equity_curve=curve,
            )
        )
    return results


def _config_to_dict(config: LoopConfig | None) -> dict:
    """把 LoopConfig 序列化为 dict（便于 JSON 输出）"""
    if config is None:
        return {}
    return {
        "j_threshold": config.j_threshold,
        "stop_loss_pct": config.stop_loss_pct,
        "vol_shrink_threshold": config.vol_shrink_threshold,
        "bbi_break_days": config.bbi_break_days,
        "min_holding_days": config.min_holding_days,
        "lu_half": config.lu_half,
        "position_pct": config.position_pct,
    }


def _aggregate_metrics(per_stock: list[StockResult], days: int) -> AggregateMetrics:
    """从单股结果聚合到组合级 AggregateMetrics（v3.7.4：基于真实组合资金曲线）"""
    active = [r for r in per_stock if not r.skipped and r.trades > 0]
    if not active:
        return AggregateMetrics()

    total_trades = sum(r.trades for r in active)
    wins = sum(r.trades * r.win_rate for r in active)
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    # 组合级资金曲线：各股 equity_curve 按长度对齐后等权平均
    merged_curve = _merge_equity_curves([r.equity_curve for r in active if r.equity_curve])

    total_return = 0.0
    annualized_return = 0.0
    sharpe = 0.0
    max_drawdown = 0.0

    if merged_curve and len(merged_curve) > 1:
        total_return = merged_curve[-1] / merged_curve[0] - 1.0
        # 复合年化
        annualized_return = (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / max(days, 1)) - 1.0

        # 最大回撤（基于组合曲线）
        max_drawdown, _ = compute_drawdown(merged_curve)

        # Sharpe：基于组合曲线逐点收益率，按交易频率年化
        rets = daily_returns(merged_curve)
        if len(rets) > 1:
            # 交易频率年化：periods_per_year = 总交易期数 * 250 / days
            periods_per_year = len(rets) * TRADING_DAYS_PER_YEAR / max(days, 1)
            sharpe = compute_sharpe(rets, periods_per_year=periods_per_year)

    # Calmar = 年化收益 / 最大回撤
    calmar = annualized_return / max_drawdown if max_drawdown > 0.001 else 0.0

    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        annualized_return=annualized_return,
        sharpe=sharpe,
        calmar=calmar,
        sortino=0.0,
        max_drawdown=max_drawdown,
    )


def _merge_equity_curves(curves: list[list[float]]) -> list[float]:
    """把多条资金曲线按长度对齐后等权平均。

    对齐规则：长度不足的曲线用最后一个值向后填充，
    保证组合曲线反映所有股票的同期表现。
    """
    if not curves:
        return []
    max_len = max(len(c) for c in curves)
    merged: list[float] = []
    for i in range(max_len):
        total = 0.0
        for c in curves:
            point = c[i] if i < len(c) else c[-1]
            total += point
        merged.append(total / len(curves))
    return merged

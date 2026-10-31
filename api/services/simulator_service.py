"""模拟器服务"""

import dataclasses
import logging

from api.models.simulator import SimulationRequest

logger = logging.getLogger(__name__)


def _request_to_config(req: SimulationRequest):
    """将 API 请求转换为 SimulationConfig。"""
    from modules.simulator import SlippageModel
    from modules.simulator.config import build_cost_model, build_simulation_config
    from modules.simulator.walk_forward import WalkForwardConfig

    cost_model = build_cost_model(req.cost_model)

    use_dynamic_slippage = req.slippage == "dynamic"

    wf_config = None
    if req.walk_forward:
        wf_config = WalkForwardConfig(
            train_days=req.wf_train_days,
            test_days=req.wf_test_days,
            objective=req.wf_objective,
        )

    return build_simulation_config(
        initial_capital=req.capital,
        max_positions=req.max_positions,
        risk_per_trade=req.risk_per_trade,
        position_score_threshold=req.min_score,
        signal_min_count=req.min_signals,
        cost_model=cost_model,
        slippage_model=SlippageModel(),
        use_dynamic_slippage=use_dynamic_slippage,
        use_atr_sizing=req.atr_sizing,
        max_position_pct=req.max_position_pct,
        allow_st=not req.no_st,
        benchmark_code=req.benchmark,
        strategy_mode=req.strategy_mode,
        strategy_lookback_days=req.strategy_lookback,
        min_resonance_score=req.min_resonance_score,
        walk_forward=req.walk_forward,
        wf_config=wf_config,
    )


def run_simulation_service(req: SimulationRequest) -> dict:
    """运行普通模拟。"""
    from modules.simulator.simulator import run_simulation

    config = _request_to_config(req)
    # /run 忽略 walk_forward，强制普通模拟
    config.walk_forward = False
    config.wf_config = None

    result = run_simulation(
        ts_codes=req.ts_codes or None,
        days=req.days,
        config=config,
    )
    return _result_to_response(result)


def run_walk_forward_service(req: SimulationRequest) -> dict:
    """运行 Walk-forward 参数寻优。"""
    from modules.simulator.simulator import run_simulation
    from modules.simulator.walk_forward import WalkForwardConfig, run_walk_forward

    config = _request_to_config(req)
    config.walk_forward = False
    config.wf_config = None

    wf_config = WalkForwardConfig(
        train_days=req.wf_train_days,
        test_days=req.wf_test_days,
        objective=req.wf_objective,
    )

    result = run_walk_forward(
        ts_codes=req.ts_codes or None,
        total_days=req.days,
        wf_config=wf_config,
        base_config=config,
    )
    return _walk_forward_to_response(result)


# ── 内部序列化 ──


def _result_to_response(result) -> dict:
    """将 SimulationResult 转为 API 响应。"""
    metrics = None
    if result.metrics:
        metrics = dataclasses.asdict(result.metrics)

    # 优先使用 equity_details（含完整信息），否则从 equity_curve 构建
    equity_details = getattr(result, "equity_details", [])
    if equity_details:
        equity_curve = [
            {
                "date": p.get("date", ""),
                "equity": round(p.get("equity", 0), 2),
                "cash": round(p.get("cash", 0), 2),
                "positions": p.get("positions", 0),
                "regime": p.get("regime", ""),
            }
            for p in equity_details
        ]
    else:
        # 兼容旧格式：只有 equity_curve（list[float]）
        equity_curve = [
            {"date": "", "equity": round(v, 2), "cash": 0, "positions": 0, "regime": ""} for v in result.equity_curve
        ]

    benchmark_curve = []
    for p in result.benchmark_curve:
        benchmark_curve.append({"date": p.get("date", ""), "close": round(float(p.get("close", 0)), 2)})

    trades = []
    for t in result.trades:
        trades.append(
            {
                "action": t.action,
                "ts_code": t.ts_code,
                "date": t.date,
                "price": round(t.price, 3),
                "shares": t.shares,
                "pnl": round(t.pnl, 2) if t.pnl else None,
                "pnl_pct": round(t.pnl_pct * 100, 2) if t.pnl_pct else None,
                "fee": round(t.fee, 2),
                "stamp_duty": round(t.stamp_duty, 2),
                "transfer_fee": round(t.transfer_fee, 2),
                "reason": t.reason,
            }
        )

    positions = [dataclasses.asdict(p) for p in result.positions]

    summary = {
        "initial_capital": round(result.initial_capital, 2),
        "final_value": round(result.final_value, 2),
        "total_return": round(result.total_return * 100, 2),
        "total_trades": result.total_trades,
        "win_rate": round(result.win_rate, 3),
        "profit_factor": round(result.profit_factor, 2),
        "max_drawdown": round(result.max_drawdown * 100, 2),
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "avg_holding_days": round(result.avg_holding_days, 1),
        "unclosed_positions": len(result.positions),
    }

    return {
        "summary": summary,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "benchmark_curve": benchmark_curve,
        "trades": trades,
        "rejected_entries": result.rejected_entries or [],
        "resonance_summary": result.resonance_summary or {},
        "positions": positions,
    }


def _walk_forward_to_response(result) -> dict:
    """将 WalkForwardResult 转为 API 响应。"""
    windows = []
    for w in result.windows:
        windows.append(
            {
                "window_index": w.window_index,
                "is_start": w.is_start,
                "is_end": w.is_end,
                "oos_start": w.oos_start,
                "oos_end": w.oos_end,
                "best_params": w.best_params,
                "is_score": round(w.is_score, 4),
                "oos_score": round(w.oos_score, 4),
            }
        )

    oos_metrics = None
    if result.oos_metrics:
        oos_metrics = dataclasses.asdict(result.oos_metrics)

    oos_equity_curve = [
        {
            "date": p.get("date", ""),
            "equity": round(p.get("equity", 0), 2),
            "cash": round(p.get("cash", 0), 2),
            "positions": p.get("positions", 0),
            "regime": p.get("regime", ""),
        }
        for p in result.oos_equity_curve
    ]

    return {
        "summary": {
            "objective": result.config.objective,
            "train_days": result.config.train_days,
            "test_days": result.config.test_days,
            "windows": len(windows),
            "overfit_ratio": round(result.overfit_ratio, 4),
        },
        "metrics": oos_metrics,
        "equity_curve": oos_equity_curve,
        "windows": windows,
    }

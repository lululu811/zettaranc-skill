"""CLI simulate 子命令实现。"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any
from modules.core.errors import ErrorCode
from ._helpers import json_output

logger = logging.getLogger(__name__)


def _simulate_narrate_text(result: Any, wf_payload: dict[str, Any] | None) -> dict[str, Any]:
    """simulate 子命令的 --narrate 适配。"""
    if result is not None:
        try:
            from modules.simulator.narrator import generate_simulation_narrative

            return generate_simulation_narrative(result)
        except (ImportError, AttributeError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "[cli_commands] narrate 失败，使用兜底文案 (code=%s): %s",
                ErrorCode.CLI_COMMAND_FAILED.value,
                exc,
            )
            return {
                "simulation_id": "",
                "ts_codes": [],
                "days": 0,
                "narrative_text": f"[narrate 生成失败] {exc}",
                "generated_at": "",
                "model_used": "",
                "cached": False,
                "error": "narrate_failed",
            }

    if wf_payload is not None:
        oos = wf_payload.get("oos_metrics") or {}
        narrative_lines = [
            "【Walk-forward OOS 战绩】",
            f"- 窗口数: {len(wf_payload.get('windows') or [])}",
            f"- 训练/验证窗口: {wf_payload.get('config', {}).get('train_days')}/{wf_payload.get('config', {}).get('test_days')}",
            f"- 目标函数: {wf_payload.get('config', {}).get('objective', 'calmar')}",
            f"- OOS 年化: {oos.get('annualized_return', 0) * 100:+.2f}%",
            f"- OOS 夏普: {oos.get('sharpe_ratio', 0):.2f}",
            f"- OOS Calmar: {oos.get('calmar_ratio', 0):.2f}",
            f"- OOS 最大回撤: {oos.get('max_drawdown', 0) * 100:.2f}%",
            f"- 过拟合比率: {wf_payload.get('overfit_ratio', 1.0):.2f}（接近 1 = 不过拟合）",
            "",
            "（walk-forward 不调 LLM，直接看 OOS 拼接曲线与稳定性）",
        ]
        return {
            "simulation_id": "walk_forward",
            "ts_codes": [],
            "days": wf_payload.get("config", {}).get("train_days", 0)
            + wf_payload.get("config", {}).get("test_days", 0),
            "narrative_text": "\n".join(narrative_lines),
            "generated_at": "",
            "model_used": "",
            "cached": False,
        }

    return {}


def _simulate_print_narrative(narrative: dict[str, Any]) -> None:
    """非 JSON 输出模式：把 narrative 以人类可读形式追加到 stdout。"""
    print("\n" + "=" * 60)
    print("Z哥点评")
    print("=" * 60)
    text = narrative.get("narrative_text") if narrative else ""
    if not text:
        text = narrative.get("error", "点评生成失败") if narrative else "点评生成失败"
    print(text)


def cmd_simulate(args) -> None:
    """少女/少妇模拟器 CLI 入口（v0.2）。"""
    from modules.simulator import CostModel, SimulationConfig
    from modules.simulator.simulator import run_simulation, summary_text

    use_json = getattr(args, "json", False)
    days = getattr(args, "days", 250)
    codes_str = getattr(args, "codes", None)

    if getattr(args, "cost_model", "simple") == "advanced":
        cost_model = CostModel()
    else:
        cost_model = CostModel(
            commission_rate=0.0003,
            min_commission=0.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
            apply_stamp_duty_on_sell=False,
        )

    config = SimulationConfig(
        initial_capital=getattr(args, "capital", 1_000_000.0),
        max_positions=getattr(args, "max_positions", 5),
        risk_per_trade=getattr(args, "risk", 0.02),
        position_score_threshold=getattr(args, "score", 70.0),
        signal_min_count=getattr(args, "signals", 2),
        benchmark_code=getattr(args, "benchmark", "000300.SH"),
        cost_model=cost_model,
        use_dynamic_slippage=getattr(args, "slippage", "fixed") == "dynamic",
        use_atr_sizing=getattr(args, "atr_sizing", False),
        max_position_pct=getattr(args, "max_position_pct", 0.20),
        allow_st=not getattr(args, "no_st", False),
        t1_lock=getattr(args, "t1_lock", True),
        strategy_mode=getattr(args, "strategy_mode", "simple"),
        strategy_lookback_days=getattr(args, "strategy_lookback", 5),
        min_resonance_score=getattr(args, "min_resonance_score", 0.35),
    )

    ts_codes = None
    if codes_str:
        ts_codes = [c.strip() for c in codes_str.split(",") if c.strip()]

    if getattr(args, "walk_forward", False):
        from modules.simulator.optimizer_report import summary_text as wf_summary_text, to_dict as wf_to_dict
        from modules.simulator.walk_forward import WalkForwardConfig, run_walk_forward

        wf_config = WalkForwardConfig(
            train_days=getattr(args, "wf_train_days", 120),
            test_days=getattr(args, "wf_test_days", 60),
            objective=getattr(args, "wf_objective", "calmar"),
        )

        wf_result = run_walk_forward(
            ts_codes=ts_codes,
            total_days=days,
            wf_config=wf_config,
            base_config=config,
        )

        if use_json:
            payload = wf_to_dict(wf_result)
            if getattr(args, "narrate", False):
                payload["narrative"] = _simulate_narrate_text(result=None, wf_payload=payload)
            json_output(payload)
        else:
            print(wf_summary_text(wf_result))
            if getattr(args, "narrate", False):
                _simulate_print_narrative(_simulate_narrate_text(result=None, wf_payload=None))
        return

    result = run_simulation(ts_codes=ts_codes, days=days, config=config)

    metrics_dict = asdict(result.metrics) if result.metrics else None

    if use_json:
        output_dict = {
            "initial_capital": result.initial_capital,
            "final_value": result.final_value,
            "total_return": round(result.total_return * 100, 2),
            "max_drawdown": round(result.max_drawdown * 100, 2),
            "sharpe_ratio": round(result.sharpe_ratio, 2),
            "total_trades": result.total_trades,
            "win_rate": round(result.win_rate, 3),
            "profit_factor": round(result.profit_factor, 2),
            "avg_holding_days": round(result.avg_holding_days, 1),
            "open_positions": len(result.positions),
            "trades": [
                {
                    "ts_code": t.ts_code,
                    "action": t.action,
                    "date": t.date,
                    "price": t.price,
                    "shares": t.shares,
                    "pnl": t.pnl,
                    "pnl_pct": round(t.pnl_pct * 100, 2),
                    "reason": t.reason,
                }
                for t in result.trades
            ],
            "equity_curve_sample": result.equity_curve[:: max(1, len(result.equity_curve) // 30)],
            "metrics": metrics_dict,
            "benchmark_curve_sample": result.benchmark_curve[:: max(1, len(result.benchmark_curve) // 30)],
            "resonance_details": result.resonance_summary,
        }

        if getattr(args, "narrate", False):
            output_dict["narrative"] = _simulate_narrate_text(result=result, wf_payload=None)

        json_output(output_dict)
    else:
        print(summary_text(result))
        if getattr(args, "narrate", False):
            _simulate_print_narrative(_simulate_narrate_text(result=result, wf_payload=None))

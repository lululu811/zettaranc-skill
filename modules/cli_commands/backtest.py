"""CLI 回测/验证/模拟（backtest / verify / simulate）子命令。"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from ._helpers import error, json_output, warn
from .simulate import cmd_simulate

logger = logging.getLogger(__name__)


# ==================== 工具：序列化 ====================


def _shaofu_result_to_dict(result: Any) -> dict:
    """将 ShaofuBacktestResult 转换为可序列化的字典"""
    trades = []
    for t in result.trades:
        trades.append(
            {
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "pnl_pct": round(t.pnl_pct, 2),
                "holding_days": t.holding_days,
            }
        )

    return {
        "ts_code": result.ts_code,
        "total_trades": result.total_trades,
        "win_count": result.win_count,
        "win_rate": round(result.win_rate, 3),
        "avg_pnl": round(result.avg_pnl, 2),
        "max_win": round(result.max_win, 2),
        "max_loss": round(result.max_loss, 2),
        "profit_factor": round(result.profit_factor, 2),
        "total_return": round(result.total_return * 100, 2),
        "max_drawdown": round(result.max_drawdown * 100, 2),
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "avg_holding_days": round(result.avg_holding_days, 1),
        "trades": trades,
    }


def _portfolio_result_to_dict(result: Any) -> dict:
    """将 PortfolioBacktestResult 转换为可序列化的字典"""
    trades = []
    for t in result.trades:
        trades.append(
            {
                "ts_code": t.ts_code,
                "entry_date": t.entry_date,
                "entry_price": round(t.entry_price, 2),
                "exit_date": t.exit_date,
                "exit_price": round(t.exit_price, 2) if t.exit_price else None,
                "exit_reason": t.exit_reason,
                "pnl_pct": round(t.pnl_pct, 2),
            }
        )

    return {
        "initial_capital": result.initial_capital,
        "final_value": round(result.final_value, 2),
        "total_return": round(result.total_return * 100, 2),
        "annualized_return": round(result.annualized_return * 100, 2),
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "max_drawdown": round(result.max_drawdown * 100, 2),
        "win_rate": round(result.win_rate, 3),
        "profit_factor": round(result.profit_factor, 2),
        "total_trades": result.total_trades,
        "trades": trades,
    }


def _shaofu_portfolio_to_dict(result: dict) -> dict:
    """将 backtest_shaofu_portfolio 返回的 dict 清理为可序列化格式"""
    per_stock = []
    for r in result.get("results", []):
        per_stock.append(_shaofu_result_to_dict(r))

    return {
        "per_stock": per_stock,
        "total_return": round(result.get("total_return", 0) * 100, 2),
        "total_trades": result.get("total_trades", 0),
        "overall_win_rate": round(result.get("overall_win_rate", 0), 3),
        "max_drawdown": round(result.get("max_drawdown", 0) * 100, 2),
        "sharpe_ratio": round(result.get("sharpe_ratio", 0), 2),
    }


def _print_shaofu_summary(ts_code: str, dict_result: dict) -> None:
    """Rust 路径的 shaofu 回测结果 → 人类可读摘要。"""
    print(f"\n{'=' * 60}")
    print(f"回测结果: {ts_code}  [Rust 路径]")
    print(f"{'=' * 60}")
    print(f"总交易次数: {dict_result['total_trades']}")
    print(f"盈利次数:   {dict_result['win_count']}")
    print(f"胜率:       {dict_result['win_rate']:.1%}")
    print(f"盈亏比:     {dict_result['profit_factor']:.2f}")
    print(f"最大回撤:   {dict_result['max_drawdown']:.2f}%")
    print(f"总收益率:   {dict_result['total_return']:+.2f}%")
    print(f"夏普比率:   {dict_result['sharpe_ratio']:.2f}")
    print(f"平均持仓:   {dict_result['avg_holding_days']:.1f}天")
    print(f"{'=' * 60}")
    last_trades = dict_result.get("trades", [])[-5:]
    if last_trades:
        print("最近5笔交易:")
        for t in last_trades:
            status = "[+]" if t.get("pnl_pct", 0) > 0 else "[-]"
            print(
                f"  {status} {t.get('entry_date', '?')}→{t.get('exit_date') or '持有中'} "
                f"{t.get('pnl_pct', 0):+.2f}% ({t.get('exit_reason', '')})"
            )


def _b1_b2_pool_to_dict(pool) -> dict:
    """将 B1B2PoolResult 转换为可序列化字典。"""
    return {
        "ts_count": len(pool.ts_codes),
        "total_trades": pool.total_trades,
        "win_rate": round(pool.win_rate, 4),
        "avg_pnl": round(pool.avg_pnl, 4),
        "profit_factor": round(pool.profit_factor, 4) if pool.profit_factor else None,
        "stocks_with_trades": pool.stocks_with_trades,
        "avg_stock_return": round(pool.avg_stock_return, 4),
        "median_stock_return": round(pool.median_stock_return, 4),
        "per_stock": [
            {
                "ts_code": r.ts_code,
                "total_trades": r.total_trades,
                "win_rate": round(r.win_rate, 4),
                "total_return": round(r.total_return, 4),
            }
            for r in pool.results
            if r.total_trades > 0
        ],
    }


def _print_b1_b2_pool_summary(pool) -> None:
    """人类可读的 B1+B2 池级回测摘要。"""
    print(f"\n{'=' * 60}")
    print("B1观察 + B2确认策略 · 池级回测")
    print(f"{'=' * 60}")
    print(f"股票数量:       {len(pool.ts_codes)}")
    print(f"有交易股票数:   {pool.stocks_with_trades}")
    print(f"总交易次数:     {pool.total_trades}")
    print(f"胜率:           {pool.win_rate:.1%}")
    print(f"平均单笔盈亏:   {pool.avg_pnl:+.2f}%")
    print(f"盈亏比:         {pool.profit_factor:.2f}")
    print(f"有交易股票平均收益: {pool.avg_stock_return:+.2%}")
    print(f"有交易股票中位收益: {pool.median_stock_return:+.2%}")
    print(f"{'=' * 60}")
    for r in pool.results:
        if r.total_trades > 0:
            print(f"  {r.ts_code}: {r.total_trades}笔 胜率{r.win_rate:.0%} 收益{r.total_return:+.2%}")


# ==================== cmd_backtest ====================


def cmd_backtest(args) -> None:
    """回测命令（shaofu / multi / portfolio / b2-confirm）"""
    sub = getattr(args, "backtest_sub", None)
    use_json = getattr(args, "json", False)
    days = getattr(args, "days", 250)

    if not sub:
        error("请指定回测子命令: shaofu / multi / portfolio / b2-confirm")

    ts_code = getattr(args, "ts_code", None)

    # ── shaofu: 少妇战法单股回测 ──
    if sub == "shaofu":
        if not ts_code:
            error("请指定股票代码，如: backtest shaofu 600487.SH")

        from modules.backtest._rust_bridge import bridge_shaofu_single

        dict_result = bridge_shaofu_single(ts_code, days=days)

        if dict_result.get("total_trades", 0) == 0:
            warn(f"{ts_code} 在 {days} 天内无交易记录（数据不足或无信号触发）")
        if use_json:
            json_output(dict_result)
        else:
            _print_shaofu_summary(ts_code, dict_result)
        return

    # ── multi: 多策略融合回测 ──
    elif sub == "multi":
        if not ts_code:
            error("请指定股票代码，如: backtest multi 600487.SH")

        from modules.backtest import backtest_multi_strategy

        result_multi = backtest_multi_strategy(ts_code, days=days)

        if result_multi.total_trades == 0:
            warn(f"{ts_code} 在 {days} 天内无交易记录")

        if use_json:
            json_output(_portfolio_result_to_dict(result_multi))
        else:
            print(result_multi.summary())

    # ── portfolio: 组合回测 ──
    elif sub == "portfolio":
        codes_str = getattr(args, "codes", None)
        if not codes_str:
            error("请指定股票代码列表（逗号分隔），如: backtest portfolio 600487.SH,601318.SH")

        ts_codes = [c.strip() for c in codes_str.split(",") if c.strip()]
        if not ts_codes:
            error("股票代码列表为空")

        if len(ts_codes) == 1:
            from modules.backtest._rust_bridge import bridge_shaofu_single

            dict_single = bridge_shaofu_single(ts_codes[0], days=days)
            if dict_single.get("total_trades", 0) == 0:
                warn(f"{ts_codes[0]} 在 {days} 天内无交易记录（数据不足或无信号触发）")
            if use_json:
                json_output(dict_single)
            else:
                _print_shaofu_summary(ts_codes[0], dict_single)
        else:
            from modules.backtest_six_step import backtest_shaofu_portfolio

            result_port = backtest_shaofu_portfolio(ts_codes, days=days)
            if use_json:
                json_output(_shaofu_portfolio_to_dict(result_port))
            else:
                print(f"{'=' * 60}")
                print("少妇战法组合回测结果")
                print(f"{'=' * 60}")
                print(f"股票数量:     {len(ts_codes)}")
                print(f"总交易次数:   {result_port['total_trades']}")
                print(f"整体胜率:     {result_port['overall_win_rate']:.1%}")
                print(f"累计收益:     {result_port['total_return']:+.2%}")
                print(f"最大回撤:     {result_port['max_drawdown']:.2%}")
                print(f"夏普比率:     {result_port['sharpe_ratio']:.2f}")
                print(f"{'=' * 60}")
                for r in result_port.get("results", []):
                    status = "有交易" if r.total_trades > 0 else "无交易"
                    print(f"  {r.ts_code}: {status} {r.total_trades}笔 胜率{r.win_rate:.0%} 收益{r.total_return:+.2%}")

    # ── b2-confirm: B1观察+B2确认+次日开盘回测 ──
    elif sub == "b2-confirm":
        from modules.strategies.b1_b2 import B1B2Config
        from modules.backtest.b1_b2_backtest import (
            run_b1_b2_single,
            run_b1_b2_pool,
            run_b1_b2_walkforward,
        )
        from modules.loop_engine import LoopConfig

        codes_str = getattr(args, "codes", None)
        if codes_str:
            ts_codes = [c.strip() for c in codes_str.split(",") if c.strip()]
        elif ts_code:
            ts_codes = [ts_code]
        else:
            error("请指定股票代码，如: backtest b2-confirm 600487.SH 或 b2-confirm 000001.SZ,000002.SZ")

        b2_j_max = getattr(args, "b2_j_max", None)
        cfg = B1B2Config(
            b1_j_threshold=getattr(args, "b1_j_threshold", -10.0),
            observe_min=getattr(args, "observe_min", 3),
            observe_max=getattr(args, "observe_max", 5),
            b2_min_pct=getattr(args, "b2_min_pct", 4.0),
            b2_min_vol_ratio=getattr(args, "b2_min_vol", 2.0),
            b2_j_max=b2_j_max,
            max_gap_open_pct=getattr(args, "max_gap_open_pct", 5.0),
        )
        lc_cfg = LoopConfig(
            stop_loss_pct=getattr(args, "stop_loss_pct", -0.05),
            bbi_break_days=getattr(args, "bbi_days", 2),
            min_holding_days=getattr(args, "min_hold", 2),
            position_pct=1.0,
        )
        active_mv_enabled = getattr(args, "active_mv_gate", False)
        active_mv_duckdb = getattr(args, "active_mv_duckdb", None)
        active_mv_path = getattr(args, "active_mv_path", None)

        if getattr(args, "walk_forward", False):
            wf = run_b1_b2_walkforward(
                ts_codes,
                days=days,
                folds=getattr(args, "folds", 4),
                window=getattr(args, "window", 120),
                config=cfg,
                loop_config=lc_cfg,
                active_mv_enabled=active_mv_enabled,
                active_mv_duckdb_path=active_mv_duckdb,
                active_mv_path=active_mv_path,
            )
            if use_json:
                json_output(wf)
            else:
                print(f"\n{'=' * 60}")
                print("B1观察 + B2确认 · Walk-forward 样本外验证")
                print(f"{'=' * 60}")
                for fold in wf.get("folds", []):
                    pf = fold.get("profit_factor")
                    print(
                        f"Fold {fold['fold']}  {fold['range']}  "
                        f"交易{fold['total_trades']}笔 胜率{fold['win_rate']:.1%} "
                        f"平均单笔{fold['avg_pnl']:+.2f}% 盈亏比{pf if pf is not None else '-'}"
                    )
            return

        if len(ts_codes) == 1:
            result = run_b1_b2_single(
                ts_codes[0],
                days=days,
                config=cfg,
                loop_config=lc_cfg,
                active_mv_enabled=active_mv_enabled,
                active_mv_duckdb_path=active_mv_duckdb,
                active_mv_path=active_mv_path,
            )
            if use_json:
                json_output(
                    {
                        "ts_code": result.ts_code,
                        "total_trades": result.total_trades,
                        "win_rate": round(result.win_rate, 4),
                        "avg_pnl": round(result.avg_pnl, 4),
                        "profit_factor": round(result.profit_factor, 4) if result.profit_factor else None,
                        "total_return": round(result.total_return, 4),
                        "max_drawdown": round(result.max_drawdown, 4),
                        "sharpe_ratio": round(result.sharpe_ratio, 4),
                        "trades": [
                            {
                                "entry_date": t.entry_date,
                                "exit_date": t.exit_date,
                                "entry_price": round(t.entry_price, 2),
                                "exit_price": round(t.exit_price, 2),
                                "pnl_pct": round(t.pnl_pct, 2),
                                "exit_reason": t.exit_reason,
                            }
                            for t in result.trades
                        ],
                    }
                )
            else:
                print(f"\n{'=' * 60}")
                print(f"B1观察+B2确认单股回测: {ts_codes[0]}")
                print(f"{'=' * 60}")
                print(f"总交易次数: {result.total_trades}")
                print(f"胜率:       {result.win_rate:.1%}")
                print(f"平均单笔:   {result.avg_pnl:+.2f}%")
                print(f"盈亏比:     {result.profit_factor:.2f}")
                print(f"总收益率:   {result.total_return:+.2%}")
                print(f"最大回撤:   {result.max_drawdown:.2%}")
                print(f"夏普比率:   {result.sharpe_ratio:.2f}")
        else:
            pool = run_b1_b2_pool(
                ts_codes,
                days=days,
                config=cfg,
                loop_config=lc_cfg,
                active_mv_enabled=active_mv_enabled,
                active_mv_duckdb_path=active_mv_duckdb,
                active_mv_path=active_mv_path,
            )
            if use_json:
                json_output(_b1_b2_pool_to_dict(pool))
            else:
                _print_b1_b2_pool_summary(pool)

    else:
        error(f"未知回测子命令: {sub}")


# ==================== cmd_verify_v10 ====================


def cmd_verify_v10(args) -> int:
    """少妇战法 v1.0 验收子命令"""
    from modules.core.paths import REPORTS_DIR
    from modules.verify.cli import main as verify_main

    argv = []
    if args.limit != 50:
        argv.extend(["--limit", str(args.limit)])
    if args.days != 250:
        argv.extend(["--days", str(args.days)])
    if getattr(args, "walk_forward", False):
        argv.append("--walk-forward")
    if getattr(args, "wf_train", 120) != 120:
        argv.extend(["--wf-train", str(args.wf_train)])
    if getattr(args, "wf_test", 60) != 60:
        argv.extend(["--wf-test", str(args.wf_test)])
    if getattr(args, "ts_codes", None):
        argv.extend(["--ts-codes", args.ts_codes])
    if getattr(args, "json", False):
        argv.append("--json")
    if getattr(args, "no_markdown", False):
        argv.append("--no-markdown")
    return verify_main(argv)


def add_verify_v10_parser(subparsers) -> None:
    """注册 verify v1.0 验收子命令"""
    from modules.core.paths import REPORTS_DIR

    p_verify = subparsers.add_parser("verify", help="v1.0 验收")
    p_verify.add_argument("version", choices=["v1.0"], help="验收版本")
    p_verify.add_argument("--limit", type=int, default=50)
    p_verify.add_argument("--days", type=int, default=250)
    p_verify.add_argument("--walk-forward", action="store_true")
    p_verify.add_argument("--wf-train", type=int, default=120)
    p_verify.add_argument("--wf-test", type=int, default=60)
    p_verify.add_argument("--ts-codes", type=str, default=None, help="指定股票列表（逗号分隔）")
    p_verify.add_argument("--output", type=str, default=str(REPORTS_DIR), help="报告输出目录")
    p_verify.add_argument("--json", action="store_true")
    p_verify.add_argument("--no-markdown", action="store_true")
    p_verify.set_defaults(func=cmd_verify_v10)


__all__ = [
    "cmd_backtest",
    "cmd_simulate",
    "cmd_verify_v10",
    "add_verify_v10_parser",
    "_shaofu_result_to_dict",
    "_portfolio_result_to_dict",
    "_shaofu_portfolio_to_dict",
    "_b1_b2_pool_to_dict",
]

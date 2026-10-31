"""策略回测服务"""

import logging
from modules.backtest.single import multi_strategy_result_to_dict
from modules.backtest.shaofu import shaofu_result_to_dict

logger = logging.getLogger(__name__)


def run_shaofu(ts_code: str, days: int = 250, **kwargs) -> dict:
    """少妇战法单股回测"""
    try:
        from modules.backtest import backtest_shaofu_single

        result = backtest_shaofu_single(ts_code, days=days)
        return _shaofu_to_response(ts_code, result)
    except ImportError:
        # 如果没有 backtest_six_step，回退到基础回测
        logger.warning("backtest_six_step 不可用，使用基础回测")
        return run_multi(ts_code, days=days, **kwargs)


def run_multi(
    ts_code: str,
    days: int = 240,
    initial_capital: float = 100000,
    position_pct: float = 0.3,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> dict:
    """多策略融合回测"""
    from modules.backtest import backtest_multi_strategy

    result = backtest_multi_strategy(
        ts_code,
        days=days,
        initial_capital=initial_capital,
        position_pct=position_pct,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )
    return _portfolio_to_response(ts_code, result)


def run_portfolio(
    ts_codes: list[str],
    days: int = 240,
    initial_capital: float = 100000,
    position_pct: float = 0.2,
    stop_loss_pct: float = 0.07,
    take_profit_pct: float = 0.15,
) -> dict:
    """多股票组合回测"""
    from modules.backtest import backtest_portfolio

    stock_configs = [{"ts_code": code} for code in ts_codes]
    result = backtest_portfolio(
        stock_configs,
        days=days,
        initial_capital=initial_capital,
        position_pct=position_pct,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )
    return _portfolio_to_response("portfolio", result)


# ── 内部序列化 ──


def _shaofu_to_response(ts_code: str, result) -> dict:
    """将少妇战法结果转为 API 响应。

    字段集与取值来自 ``ShaofuBacktestResult.to_dict()``——CLI 与 API 共用同一份
    规范字典，只是嵌套方式不同（CLI 扁平、API 用 summary 嵌套）。
    """
    d = shaofu_result_to_dict(result)

    # 构建资金曲线（从 trades 推算）
    equity_curve = _build_equity_curve_from_trades(result.trades, getattr(result, "initial_capital", 100000))

    return {
        "ts_code": ts_code,
        "summary": {
            "total_trades": d["total_trades"],
            "win_rate": d["win_rate"],
            "profit_factor": d["profit_factor"],
            "total_return": d["total_return"],
            "max_drawdown": d["max_drawdown"],
            "sharpe_ratio": d["sharpe_ratio"],
            "avg_holding_days": d["avg_holding_days"],
            # 少妇战法路径的资金曲线是【交易序】而非日序，无法按日频年化——
            # 该指标不可得，0 表示"不可得"而非"年化 0%"。
            "annualized_return": 0,
            "win_count": d["win_count"],
            "loss_count": d["loss_count"],
            "avg_pnl": d["avg_pnl"],
            "avg_win": d["avg_win"],
            "avg_loss": d["avg_loss"],
            "max_win": d["max_win"],
            "max_loss": d["max_loss"],
        },
        "equity_curve": equity_curve,
        "trades": d["trades"],
    }


def _portfolio_to_response(ts_code: str, result) -> dict:
    """将组合回测结果转为 API 响应。

    字段集与取值来自 ``MultiStrategyBacktestResult.to_dict()``——CLI 与 API 共用
    同一份规范字典。此前这里把 avg_holding_days / win_count / max_win /
    max_loss / avg_pnl 全部硬编码成 0，而 CLI 侧根本不输出这些字段——
    同一份结果，两个出口给出的是两套数。现在统一。
    """
    d = multi_strategy_result_to_dict(result)

    # 资金曲线
    equity_curve = []
    equity_dates = getattr(result, "equity_dates", [])
    values = getattr(result, "equity_curve", [])
    for i, value in enumerate(values):
        date = equity_dates[i] if i < len(equity_dates) else ""
        equity_curve.append([date, round(value, 2)])

    return {
        "ts_code": ts_code,
        "summary": {
            "total_trades": d["total_trades"],
            "win_rate": d["win_rate"],
            "profit_factor": d["profit_factor"],
            "total_return": d["total_return"],
            "max_drawdown": d["max_drawdown"],
            "sharpe_ratio": d["sharpe_ratio"],
            "avg_holding_days": d["avg_holding_days"],
            "annualized_return": d["annualized_return"],
            "win_count": d["win_count"],
            "loss_count": d["loss_count"],
            "avg_pnl": d["avg_pnl"],
            "avg_win": d["avg_win"],
            "avg_loss": d["avg_loss"],
            "max_win": d["max_win"],
            "max_loss": d["max_loss"],
        },
        "equity_curve": equity_curve,
        "trades": d["trades"],
        "per_stock": _per_stock_responses(ts_code, result, d),
    }


def _per_stock_responses(ts_code: str, result, canonical: dict) -> list[dict]:
    """按标的分组的逐股摘要 —— PortfolioBacktestResponse.per_stock 此前恒为空。"""
    from modules.core.metrics import calc_curve_metrics, calc_trade_stats

    grouped: dict[str, list[dict]] = {}
    obj_groups: dict[str, list] = {}
    for td, t in zip(canonical["trades"], result.trades):
        code = td.get("ts_code") or ts_code
        grouped.setdefault(code, []).append(td)
        obj_groups.setdefault(code, []).append(t)

    per_stock: list[dict] = []
    for code, tds in grouped.items():
        stats = calc_trade_stats([t["pnl_pct"] for t in tds])
        curve = _build_equity_curve_from_trades(obj_groups[code], getattr(result, "initial_capital", 100000))
        values = [v for _, v in curve]
        cm = calc_curve_metrics(values, trading_days=len(values)) if len(values) > 1 else None
        per_stock.append(
            {
                "ts_code": code,
                "summary": {
                    "total_trades": stats.total_trades,
                    "win_rate": round(stats.win_rate, 3),
                    "profit_factor": round(stats.profit_factor, 2),
                    "total_return": round(cm.total_return * 100, 2) if cm else 0.0,
                    "max_drawdown": round(cm.max_drawdown * 100, 2) if cm else 0.0,
                    "sharpe_ratio": round(cm.sharpe_ratio, 2) if cm else 0.0,
                    "avg_holding_days": round(stats.avg_holding_days, 1),
                    "annualized_return": round(cm.annualized_return * 100, 2) if cm else 0.0,
                    "win_count": stats.win_count,
                    "loss_count": stats.loss_count,
                    "avg_pnl": round(stats.avg_pnl, 2),
                    "avg_win": round(stats.avg_win, 2),
                    "avg_loss": round(stats.avg_loss, 2),
                    "max_win": round(stats.max_win, 2),
                    "max_loss": round(stats.max_loss, 2),
                },
                "equity_curve": curve,
                "trades": tds,
            }
        )
    return per_stock


def _build_equity_curve_from_trades(trades, initial_capital: float) -> list:
    """从交易列表推算简易资金曲线"""
    if not trades:
        return []

    capital = initial_capital
    curve = []
    for t in trades:
        # LoopTrade.pnl_pct 是百分数（10.0 = +10%），复利需换算成小数
        pnl = (getattr(t, "pnl_pct", 0) or 0) / 100.0
        capital *= 1 + pnl
        exit_date = getattr(t, "exit_date", None) or getattr(t, "entry_date", "")
        curve.append([exit_date, round(capital, 2)])

    return curve

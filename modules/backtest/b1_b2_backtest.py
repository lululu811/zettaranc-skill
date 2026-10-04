#!/usr/bin/env python3
"""
B1 观察 + B2 确认策略的回测封装。

回测口径：
- B2 信号在 T 日收盘确认；
- T+1 日开盘价买入（避免当日追高与前视偏差）；
- 可选的 T+1 高开过滤；
- 离场复用 ShaofuLoopEngine：止损 / BBI 破位 / 白线破位 / 白线死叉黄线。
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from ..indicators import DailyData, get_kline_data
from ..loop_engine import LoopConfig, LoopTrade, ShaofuLoopEngine, _calc_stop_loss_price
from ..backtest_six_step import ShaofuBacktestResult, _calc_metrics
from ..strategies.b1_b2 import B1B2Config, is_b2_signal, is_high_open_skip

logger = logging.getLogger(__name__)


@dataclass
class B1B2PoolResult:
    """B1+B2 策略的池级回测结果。"""

    ts_codes: list[str] = field(default_factory=list)
    total_trades: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    profit_factor: float = 0.0
    stocks_with_trades: int = 0
    avg_stock_return: float = 0.0
    median_stock_return: float = 0.0
    results: list[ShaofuBacktestResult] = field(default_factory=list)


def _default_loop_config() -> LoopConfig:
    """B1+B2 策略推荐的离场参数。"""
    return LoopConfig(
        stop_loss_pct=-0.05,
        bbi_break_days=2,
        min_holding_days=2,
        position_pct=1.0,
    )


def _run_stock_klines(
    klines: list[DailyData],
    config: B1B2Config,
    loop_config: LoopConfig,
    start_date: str | None = None,
    end_date: str | None = None,
    active_mv_enabled: bool = False,
    active_mv_duckdb_path: str | None = None,
    active_mv_path: str | None = None,
) -> list[LoopTrade]:
    """对单只股票的 K 线运行 B1+B2 策略，返回完成交易列表。

    Args:
        klines: 升序 K 线。
        config: B1/B2 信号参数。
        loop_config: 离场参数。
        start_date: 可选，仅允许该日期（含）后买入。
        end_date: 可选，仅允许该日期（含）前买入。
        active_mv_enabled: 是否启用活跃市值全局闸门。
        active_mv_duckdb_path: 活跃市值 DuckDB 路径。
        active_mv_path: 活跃市值 CSV 路径。
    """
    if not klines or len(klines) < 35:
        return []

    engine = ShaofuLoopEngine(loop_config)
    trades: list[LoopTrade] = []
    current: LoopTrade | None = None
    n = len(klines)
    i = 20

    def _gate(date: str):
        """活跃市值闸门判定(v4.3+ 统一走 apply_active_mv_gate)。"""
        from modules.active_market_value import apply_active_mv_gate

        return apply_active_mv_gate(
            date,
            enabled=active_mv_enabled,
            duckdb_path=active_mv_duckdb_path,
            path=active_mv_path,
        )

    while i < n - 1:
        if current is not None:
            # 活跃市值 CLEAR：无条件清仓
            if _gate(klines[i].trade_date).value == "CLEAR":
                last = klines[i]
                pnl_pct = (
                    (last.close - current.entry_price) / current.entry_price * 100.0 if current.entry_price else 0.0
                )
                current.exit_date = last.trade_date
                current.exit_price = last.close
                current.exit_reason = "活跃市值清仓"
                current.pnl_pct = pnl_pct
                trades.append(current)
                current = None
                i += 1
                continue

            current, completed = engine.process_day(klines[i].ts_code, klines, i, current)
            if completed is not None:
                trades.append(completed)
                current = None
                i += 1
                continue
        else:
            if is_b2_signal(klines, i, config):
                entry_idx = i + 1
                entry_k = klines[entry_idx]

                # 日期窗口过滤（任意一端为 None 则跳过该端，避免与 None 比较抛 TypeError）
                if start_date is not None and entry_k.trade_date < start_date:
                    i += 1
                    continue
                if end_date is not None and entry_k.trade_date > end_date:
                    i += 1
                    continue

                # 高开过滤
                if is_high_open_skip(klines, i, entry_idx, config):
                    i += 1
                    continue

                # 活跃市值闸门：非 OPEN 不允许开仓
                if _gate(entry_k.trade_date) != "OPEN":
                    i += 1
                    continue

                entry_price = entry_k.open
                if entry_price <= 0:
                    i += 1
                    continue

                stop_loss = _calc_stop_loss_price(
                    klines,
                    entry_idx,
                    method="entry_low",
                    stop_loss_pct=loop_config.stop_loss_pct,
                )
                current = LoopTrade(
                    ts_code=klines[i].ts_code,
                    entry_date=entry_k.trade_date,
                    entry_price=entry_price,
                    entry_reason=f"B2确认(前B1 {config.observe_min}-{config.observe_max}日) 涨{klines[i].pct_chg:.2f}%",
                    stop_loss_price=stop_loss,
                    position_pct=loop_config.position_pct,
                )
                # 入场当天也按收盘价检查离场
                current, completed = engine.process_day(klines[i].ts_code, klines, entry_idx, current)
                if completed is not None:
                    trades.append(completed)
                    current = None
        i += 1

    # 数据末尾强制平仓
    if current is not None and n:
        last = klines[-1]
        pnl_pct = (last.close - current.entry_price) / current.entry_price * 100.0
        current.exit_date = last.trade_date
        current.exit_price = last.close
        current.exit_reason = "数据末尾"
        current.pnl_pct = pnl_pct
        trades.append(current)

    return trades


def run_b1_b2_single(
    ts_code: str,
    days: int = 500,
    config: B1B2Config | None = None,
    loop_config: LoopConfig | None = None,
    active_mv_enabled: bool = False,
    active_mv_duckdb_path: str | None = None,
    active_mv_path: str | None = None,
) -> ShaofuBacktestResult:
    """单只股票 B1+B2 策略回测。"""
    cfg = config or B1B2Config()
    cfg.validate()
    lc = loop_config or _default_loop_config()

    klines = get_kline_data(ts_code, days)
    result = ShaofuBacktestResult(ts_code=ts_code)
    if not klines or len(klines) < 35:
        return result

    trades = _run_stock_klines(
        klines,
        cfg,
        lc,
        active_mv_enabled=active_mv_enabled,
        active_mv_duckdb_path=active_mv_duckdb_path,
        active_mv_path=active_mv_path,
    )
    result.trades = trades
    _calc_metrics(result)
    return result


def _aggregate_pool(results: list[ShaofuBacktestResult], ts_codes: list[str]) -> B1B2PoolResult:
    """从单股结果聚合池级统计。"""
    pool = B1B2PoolResult(ts_codes=ts_codes, results=results)
    all_trades = [t for r in results for t in r.trades]
    rets = [r.total_return for r in results if r.trades]

    if not all_trades:
        return pool

    pool.total_trades = len(all_trades)
    wins = sum(1 for t in all_trades if t.pnl_pct > 0)
    pool.win_rate = wins / len(all_trades)
    pool.avg_pnl = statistics.mean(t.pnl_pct for t in all_trades)

    total_profit = sum(t.pnl_pct for t in all_trades if t.pnl_pct > 0)
    total_loss = abs(sum(t.pnl_pct for t in all_trades if t.pnl_pct < 0))
    pool.profit_factor = total_profit / total_loss if total_loss > 0 else 0.0

    pool.stocks_with_trades = len(rets)
    if rets:
        pool.avg_stock_return = statistics.mean(rets)
        pool.median_stock_return = statistics.median(rets)

    return pool


def run_b1_b2_pool(
    ts_codes: list[str],
    days: int = 500,
    config: B1B2Config | None = None,
    loop_config: LoopConfig | None = None,
    active_mv_enabled: bool = False,
    active_mv_duckdb_path: str | None = None,
    active_mv_path: str | None = None,
) -> B1B2PoolResult:
    """多只股票 B1+B2 策略回测。"""
    cfg = config or B1B2Config()
    cfg.validate()
    lc = loop_config or _default_loop_config()

    results: list[ShaofuBacktestResult] = []
    for code in ts_codes:
        try:
            results.append(
                run_b1_b2_single(
                    code,
                    days=days,
                    config=cfg,
                    loop_config=lc,
                    active_mv_enabled=active_mv_enabled,
                    active_mv_duckdb_path=active_mv_duckdb_path,
                    active_mv_path=active_mv_path,
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("B1+B2 回测 %s 失败: %s", code, e)

    return _aggregate_pool(results, ts_codes)


def run_b1_b2_walkforward(
    ts_codes: list[str],
    days: int = 800,
    folds: int = 4,
    window: int = 120,
    config: B1B2Config | None = None,
    loop_config: LoopConfig | None = None,
    active_mv_enabled: bool = False,
    active_mv_duckdb_path: str | None = None,
    active_mv_path: str | None = None,
) -> dict[str, Any]:
    """滚动窗口 Walk-forward 验证。

    使用第一只股票的交易日历切分样本外窗口，每个窗口只统计在该窗口内买入的交易。
    """
    cfg = config or B1B2Config()
    cfg.validate()
    lc = loop_config or _default_loop_config()

    if not ts_codes:
        return {"folds": [], "error": "ts_codes 为空"}

    base_klines = get_kline_data(ts_codes[0], days)
    if len(base_klines) < folds * window + 50:
        return {"folds": [], "error": "交易日数据不足，请增大 days 或减少 folds/window"}

    dates = [k.trade_date for k in base_klines]
    train_len = len(dates) - folds * window
    folds_out: list[dict[str, Any]] = []

    for f in range(folds):
        start_idx = train_len + f * window
        end_idx = start_idx + window - 1
        start_date = dates[start_idx]
        end_date = dates[end_idx]

        fold_trades: list[LoopTrade] = []
        for code in ts_codes:
            klines = get_kline_data(code, days)
            if not klines or len(klines) < 35:
                continue
            fold_trades.extend(
                _run_stock_klines(
                    klines,
                    cfg,
                    lc,
                    start_date,
                    end_date,
                    active_mv_enabled=active_mv_enabled,
                    active_mv_duckdb_path=active_mv_duckdb_path,
                    active_mv_path=active_mv_path,
                )
            )

        if not fold_trades:
            folds_out.append(
                {
                    "fold": f + 1,
                    "range": f"{start_date}~{end_date}",
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "avg_pnl": 0.0,
                    "profit_factor": None,
                }
            )
            continue

        wins = sum(1 for t in fold_trades if t.pnl_pct > 0)
        total_profit = sum(t.pnl_pct for t in fold_trades if t.pnl_pct > 0)
        total_loss = abs(sum(t.pnl_pct for t in fold_trades if t.pnl_pct < 0))
        folds_out.append(
            {
                "fold": f + 1,
                "range": f"{start_date}~{end_date}",
                "total_trades": len(fold_trades),
                "win_rate": round(wins / len(fold_trades), 4),
                "avg_pnl": round(statistics.mean(t.pnl_pct for t in fold_trades), 4),
                "profit_factor": round(total_profit / total_loss, 4) if total_loss > 0 else None,
            }
        )

    return {"folds": folds_out, "days": days, "folds_count": folds, "window": window}

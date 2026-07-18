"""
Walk-forward 验证（少妇六步适配版，v3.7.3 真切片版）

IS 寻优 + OOS 拼接（步长 = test_days，OOS 段不重叠）：
  [IS: 0-120][OOS: 120-180]
  [IS: 60-180][OOS: 180-240]
  [IS: 120-240][OOS: 240-300]

每段独立跑窗口化回测：IS 段用 klines[train_start:train_end]，OOS 段用
klines[test_start:test_end]。OOS/IS 比率 = 各 OOS 段 sharpe / 各 IS 段 sharpe。

最少 3 个 OOS 段才合法，否则降级（degraded=True，oos_is_ratio=0.0）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core.walk_forward import WalkForwardSplit, make_walk_forward_splits
from .pipeline import (
    AggregateMetrics,
    StockResult,
)

logger = logging.getLogger(__name__)


@dataclass
class WFResult:
    """Walk-forward 验证结果"""

    splits: list[WalkForwardSplit] = field(default_factory=list)
    is_metrics: AggregateMetrics | None = None
    oos_metrics: AggregateMetrics | None = None
    oos_is_ratio: float = 0.0
    degraded: bool = False  # True = 切片数 < 3，降级单次回测


def _make_splits(
    total_days: int,
    train_days: int,
    test_days: int,
) -> list[WalkForwardSplit]:
    """滚动窗口切片，步长 = test_days（让 OOS 段不重叠）

    最后一段允许部分覆盖（test_end 截断到 total_days）以保留更多切片。
    """
    return make_walk_forward_splits(
        total_days=total_days,
        train_days=train_days,
        test_days=test_days,
        allow_partial_last=True,
    )


# ============================================================
# v3.7.3 真切片：注入式 K-line 加载 + 窗口化回测
# ============================================================


def _load_windowed_klines(ts_code: str, days: int) -> list[Any]:
    """加载单只股票的 K 线（DailyData 列表，按日期升序）。

    切入口：`modules.datasource.get_datasource("auto").get_kline_dicts(code, days)`
    拿 dict，再转 `DailyData`（backtest_shaofu_single 接受的是 DailyData）。
    """
    from modules.datasource import get_datasource
    from modules.indicators.core import DailyData

    ds = get_datasource(preferred="auto")
    raw = ds.get_kline_dicts(ts_code, days=days) or []
    out: list[Any] = []
    for d in raw:
        try:
            out.append(
                DailyData(
                    ts_code=d.get("ts_code", ts_code),
                    trade_date=d.get("trade_date", ""),
                    open=float(d.get("open", 0.0)),
                    high=float(d.get("high", 0.0)),
                    low=float(d.get("low", 0.0)),
                    close=float(d.get("close", 0.0)),
                    vol=float(d.get("vol", 0.0)),
                    amount=float(d.get("amount", 0.0)),
                    pct_chg=float(d.get("pct_chg", 0.0)),
                    prev_close=float(d.get("prev_close", 0.0)),
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("WF K线转换失败 %s: %s", ts_code, e)
    return out


def _backtest_with_window(
    ts_code: str,
    klines: list[Any],
    config: object | None,
) -> Any:
    """对一段 K 线窗口跑回测。

    切入口：`modules.backtest_six_step.backtest_shaofu_single`。
    返回 ShaofuBacktestResult，调用方负责字段抽取。
    """
    from modules.backtest_six_step import backtest_shaofu_single

    days = len(klines)
    return backtest_shaofu_single(ts_code, days=days, config=config, klines=klines)


def _stockresult_from_shaofu(
    ts_code: str,
    shaofu_result: Any,
) -> StockResult:
    """把 ShaofuBacktestResult 转成 StockResult（pipeline 内部表示）。"""
    if shaofu_result is None or getattr(shaofu_result, "total_trades", 0) == 0:
        return StockResult(
            ts_code=ts_code,
            name="",
            trades=0,
            win_rate=0.0,
            return_pct=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            skipped=False,
        )
    return StockResult(
        ts_code=ts_code,
        name=getattr(shaofu_result, "name", "") or "",
        trades=shaofu_result.total_trades,
        win_rate=shaofu_result.win_rate,
        return_pct=shaofu_result.total_return,
        sharpe=shaofu_result.sharpe_ratio,
        max_drawdown=shaofu_result.max_drawdown,
        skipped=False,
    )


def walk_forward_verify(
    ts_codes: list[str],
    days: int = 250,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: object | None = None,
) -> WFResult:
    """
    Walk-forward 验证（v3.7.3 真切片版）。

    每段 IS / OOS 独立跑窗口化回测（klines 切片传入 backtest_shaofu_single），
    产出真正不同的 IS metrics 和 OOS metrics，避免 v3.7.1/v3.7.2 时期
    oos_is_ratio ≈ 1.0 的假切片 bug。

    切片数 < 3 时降级（degraded=True，oos_is_ratio=0.0）。
    """
    splits = _make_splits(days, wf_train_days, wf_test_days)

    if len(splits) < 3:
        logger.warning(
            "WF 切片数=%d < 3，降级为单次回测（不计算 OOS/IS）",
            len(splits),
        )
        return WFResult(splits=[], degraded=True)

    is_per_stock: list[StockResult] = []
    oos_per_stock: list[StockResult] = []

    for code in ts_codes:
        klines = _load_windowed_klines(code, days)
        if not klines or len(klines) < wf_train_days:
            # 数据不足以撑起一段 IS 窗口，跳过该股
            continue

        for split in splits:
            # IS 窗口：klines[train_start:train_end]
            is_window = klines[split.train_start : split.train_end]
            # OOS 窗口：klines[test_start:test_end]
            oos_window = klines[split.test_start : split.test_end]

            # IS 段回测
            if len(is_window) >= 30:  # backtest 最低 K 线要求
                try:
                    is_shaofu = _backtest_with_window(code, is_window, config)
                    is_per_stock.append(_stockresult_from_shaofu(code, is_shaofu))
                except Exception as e:  # noqa: BLE001
                    logger.warning("WF IS 段 %s 失败: %s", code, e)

            # OOS 段回测
            if len(oos_window) >= 30:
                try:
                    oos_shaofu = _backtest_with_window(code, oos_window, config)
                    oos_per_stock.append(_stockresult_from_shaofu(code, oos_shaofu))
                except Exception as e:  # noqa: BLE001
                    logger.warning("WF OOS 段 %s 失败: %s", code, e)

    is_active = [r for r in is_per_stock if r.trades >= 3]
    oos_active = [r for r in oos_per_stock if r.trades >= 3]
    # 段内交易数 < 3 的不计入（_calc_metrics 要求 trades>=3 才计算 sharpe），
    # 避免 0 分母导致 oos_is_ratio 永远为 0
    is_metrics = _aggregate(is_active) if is_active else AggregateMetrics()
    oos_metrics = _aggregate(oos_active) if oos_active else AggregateMetrics()

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


def _aggregate(per_stock: list[StockResult]) -> AggregateMetrics:
    """复用 pipeline._aggregate_metrics 的简化版"""
    if not per_stock:
        return AggregateMetrics()
    total_trades = sum(r.trades for r in per_stock)
    wins = sum(r.trades * r.win_rate for r in per_stock)
    win_rate = wins / total_trades if total_trades > 0 else 0.0
    return_pcts = [r.return_pct for r in per_stock]
    total_return = sum(return_pcts) / len(return_pcts) if return_pcts else 0.0
    sharpes = [r.sharpe for r in per_stock]
    avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
    drawdowns = [r.max_drawdown for r in per_stock]
    max_drawdown = max(drawdowns) if drawdowns else 0.0
    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        sharpe=avg_sharpe,
        max_drawdown=max_drawdown,
    )


__all__ = [
    "WFResult",
    "_make_splits",
    "walk_forward_verify",
    "_aggregate",
    "_load_windowed_klines",
    "_backtest_with_window",
    "_stockresult_from_shaofu",
]

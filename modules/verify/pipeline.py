"""
v1.0 验收统一管线

调用现有 backtest_shaofu_portfolio / metrics / param_registry，
不修改任何现有模块的内部逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from modules.datasource import get_datasource

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


@dataclass
class AggregateMetrics:
    """组合级聚合指标"""
    total_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    annual_return_pct: float = 0.0
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


def verify_v10_pipeline(
    ts_codes: list[str],
    days: int = 250,
    config: object | None = None,
    walk_forward: bool = False,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
) -> VerifyResult:
    """v1.0 验收流水线骨架（Task 2-4 补完内部逻辑）"""
    logger.info(
        "verify_v10_pipeline 启动: stocks=%d, days=%d, wf=%s",
        len(ts_codes),
        days,
        walk_forward,
    )
    if not ts_codes:
        return VerifyResult(meta={"empty_input": True})
    # TODO Task 2-4: 实现数据加载 + 回测 + 指标计算 + gates 判定
    return VerifyResult(meta={"stub": True})

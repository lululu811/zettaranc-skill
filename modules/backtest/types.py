"""回测公共类型定义。

提供统一的 BacktestResult 接口，供各回测引擎使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..loop_engine import LoopTrade


@dataclass
class BacktestResult:
    """统一回测结果接口 —— 所有回测路径返回此类型或其子集。

    字段口径：
    - pnl_pct / avg_pnl / avg_win / avg_loss / max_win / max_loss 为百分数
    - win_rate 为分数 (0.45 = 45%)
    - total_return / max_drawdown / annualized_return 为分数

    这是 ADR 0002（回测引擎归一）的类型层体现：
    所有回测引擎统一输出 (trades: list[LoopTrade], equity_curve: list[float])，
    然后由 calculate_metrics_unified 计算指标。
    """

    ts_code: str = ""
    trades: list[LoopTrade] = field(default_factory=list)

    # 交易统计（百分数口径）
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0  # 正值（幅度）
    max_win: float = 0.0
    max_loss: float = 0.0  # 正值（幅度）
    profit_factor: float = 0.0
    avg_holding_days: float = 0.0

    # 曲线指标（分数口径）
    total_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # 资金曲线
    equity_curve: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（CLI/API 输出用）。"""
        return {
            "ts_code": self.ts_code,
            "total_trades": self.total_trades,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": round(self.win_rate, 3),
            "avg_pnl": round(self.avg_pnl, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "max_win": round(self.max_win, 2),
            "max_loss": round(self.max_loss, 2),
            "profit_factor": round(self.profit_factor, 2),
            "avg_holding_days": round(self.avg_holding_days, 1),
            "total_return": round(self.total_return, 4),
            "annualized_return": round(self.annualized_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
        }


__all__ = ["BacktestResult"]

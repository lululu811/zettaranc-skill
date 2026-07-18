#!/usr/bin/env python3
"""
少女/少妇模拟器 v0.1

把「择时 → 选股 → 等信号 → 仓位 → 买入 → 卖出」串成可回测的端到端闭环。
基于已有战法/指标/评分体系，不做新预测模型，只做规则执行与资金管理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

from ..core.market_context import MarketRegime

if TYPE_CHECKING:
    from .walk_forward import WalkForwardConfig


class SignalVerdict(Enum):
    """单票信号评审结果"""

    PASS = "通过"
    NO_SIGNAL = "无信号"
    LOW_SCORE = "评分不足"
    HIGH_RISK = "风险过高"
    BAD_STAGE = "阶段不利"


@dataclass
class CostModel:
    """真实交易成本模型"""

    commission_rate: float = 0.00025
    min_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    apply_stamp_duty_on_sell: bool = True


@dataclass
class SlippageModel:
    """动态滑点模型"""

    base_slippage: float = 0.001
    volatility_multiplier: float = 0.5
    volume_penalty: float = 0.001


@dataclass
class MarketContext:
    """每日市场环境快照"""

    date: str
    regime: MarketRegime
    index_trend: float  # 大盘指数趋势得分 0-100
    breadth: float  # 涨跌家数比，-1 ~ 1
    moneyflow_score: float  # 资金流向得分 0-100
    notes: list[str] = field(default_factory=list)


@dataclass
class RawStrategySignal:
    """标准化后的战法信号"""

    strategy: str
    category: str
    action: str
    confidence: float
    trade_date: str
    reason: str = ""


@dataclass
class ResonanceScore:
    """战法共振评分结果"""

    ts_code: str
    name: str
    date: str
    total_score: float
    buy_score: float
    risk_score: float
    matched_strategies: list[str]
    conflicts: list[str]
    verdict: SignalVerdict


@dataclass
class SignalScore:
    """单只股票在某日的综合信号评分"""

    ts_code: str
    name: str
    date: str
    score: float  # 综合评分 0-100
    b1_score: float
    trend_score: float
    volume_score: float
    risk_score: float
    signals: list[str]  # 触发的战法/指标标签
    reasons: list[str]
    warnings: list[str]
    verdict: SignalVerdict = SignalVerdict.NO_SIGNAL
    resonance: ResonanceScore | None = None


@dataclass
class Position:
    """持仓头寸"""

    ts_code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    stop_loss: float
    take_profit: float
    risk_amount: float  # 单笔承担风险金额
    partial_exited: bool = False
    can_sell_date: str = ""  # T+1 最早可卖出日
    entry_commission: float = 0.0  # 买入时佣金
    is_st: bool = False  # 是否为 ST/*ST
    notes: list[str] = field(default_factory=list)  # 持仓过程中的备注/锁定原因


@dataclass
class TradeRecord:
    """模拟成交记录"""

    ts_code: str
    name: str
    action: str  # BUY / SELL / PARTIAL_SELL
    date: str
    price: float
    shares: int
    pnl: float = 0  # 仅 SELL 时有效，金额盈亏
    pnl_pct: float = 0  # 仅 SELL 时有效，百分比盈亏
    reason: str = ""  # 成交原因
    fee: float = 0
    stamp_duty: float = 0.0  # 印花税
    transfer_fee: float = 0.0  # 过户费
    notes: list[str] = field(default_factory=list)


@dataclass
class SimulationConfig:
    """模拟器配置"""

    initial_capital: float = 1_000_000.0
    start_date: str = ""  # 空表示从数据最早日期
    end_date: str = ""  # 空表示到数据最晚日期
    max_positions: int = 5  # 最大同时持仓
    risk_per_trade: float = 0.02  # 单笔风险占净值比例
    risk_per_trade_min: float = 0.01
    commission_rate: float = 0.0003  # 手续费（双向）
    slippage: float = 0.001  # 滑点（买入 +0.1%，卖出 -0.1%）
    position_score_threshold: float = 70.0  # 入选信号最低综合评分
    signal_min_count: int = 2  # 至少需要 N 个共振标签
    partial_take_profit_rr: float = 2.0  # 卤煮：达到 2R 减半
    trailing_ma_days: int = 20  # 移动止盈参考 MA
    allow_short: bool = False  # v0.1 仅做多
    market_neutral_max_positions: int = 2  # 弱势环境下最大持仓
    # v0.2 新增：真实 A 股约束与进阶模型
    cost_model: CostModel = field(default_factory=CostModel)
    slippage_model: SlippageModel = field(default_factory=SlippageModel)
    use_dynamic_slippage: bool = False
    use_atr_sizing: bool = False
    atr_window: int = 20
    max_position_pct: float = 0.20
    cash_utilization_limit: float = 0.95
    allow_st: bool = False
    t1_lock: bool = True
    benchmark_code: str = "000300.SH"
    apply_price_limit: bool = True
    apply_halt_filter: bool = True
    # v0.3 新增：战法共振配置
    strategy_mode: str = "simple"
    strategy_lookback_days: int = 5
    min_resonance_score: float = 0.35
    strategy_category_weights: dict[str, float] = field(default_factory=dict)
    # v0.4 新增：walk-forward 参数寻优配置
    walk_forward: bool = False
    wf_config: WalkForwardConfig | None = None


@dataclass
class SimulationResult:
    """模拟回测结果"""

    config: SimulationConfig
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)  # 资金曲线（仅数值，用于指标计算）
    equity_details: list[dict[str, Any]] = field(
        default_factory=list
    )  # 每日详细数据（含日期、现金、持仓数等，用于绘图/API）
    positions: list[Position] = field(default_factory=list)  # 最终未平仓
    initial_capital: float = 0
    final_value: float = 0
    total_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    win_rate: float = 0
    profit_factor: float = 0
    total_trades: int = 0
    avg_holding_days: float = 0
    # v0.2 新增：专业绩效指标、基准曲线、被拒买入
    metrics: Any | None = None
    benchmark_curve: list[dict[str, Any]] = field(default_factory=list)
    rejected_entries: list[dict[str, Any]] = field(default_factory=list)
    # v0.3 新增：战法共振统计摘要
    resonance_summary: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "MarketRegime",
    "SignalVerdict",
    "CostModel",
    "SlippageModel",
    "MarketContext",
    "RawStrategySignal",
    "ResonanceScore",
    "SignalScore",
    "Position",
    "TradeRecord",
    "SimulationConfig",
    "SimulationResult",
]

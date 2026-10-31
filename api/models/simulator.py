"""模拟器模型"""

from pydantic import BaseModel, Field


class SimulationRequest(BaseModel):
    ts_codes: list[str] = Field(default_factory=list)  # empty = all stocks
    days: int = Field(default=250, ge=30, le=1000)
    capital: float = Field(default=1_000_000, ge=10_000)
    max_positions: int = Field(default=5, ge=1, le=20)
    risk_per_trade: float = Field(default=0.02, ge=0.001, le=0.1)
    min_score: float = Field(default=70, ge=0, le=100)
    min_signals: int = Field(default=2, ge=1, le=10)
    atr_sizing: bool = Field(default=False)
    max_position_pct: float = Field(default=0.20, ge=0.01, le=0.5)
    benchmark: str = Field(default="000300.SH")
    # 成本模型词汇：zero / simple / realistic（"advanced" 为历史别名）
    cost_model: str = Field(default="simple")
    slippage: str = Field(default="fixed")
    no_st: bool = Field(default=False)
    strategy_mode: str = Field(default="simple")  # "simple" | "resonance"
    strategy_lookback: int = Field(default=5, ge=1, le=20)
    # 0-1 分数口径（与 SimulationConfig / param_space 一致）。
    # v4.10.0 起由 0-100 改为 0-1——此前同一个 0.35 在 CLI 是 35 分、在 API
    # 却被除以 100 变成 0.0035 分，差 100 倍。
    min_resonance_score: float = Field(default=0.35, ge=0, le=1)
    walk_forward: bool = Field(default=False)
    wf_train_days: int = Field(default=120, ge=30, le=500)
    wf_test_days: int = Field(default=60, ge=10, le=200)
    wf_objective: str = Field(default="calmar")


class SimulationMetrics(BaseModel):
    total_return: float
    annualized_return: float
    benchmark_return: float | None = None
    alpha: float | None = None
    beta: float | None = None
    sharpe_ratio: float
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    max_drawdown: float
    max_drawdown_duration: int | None = None
    win_rate: float
    profit_factor: float
    avg_win: float | None = None
    avg_loss: float | None = None
    gain_loss_ratio: float | None = None
    max_consecutive_wins: int | None = None
    max_consecutive_losses: int | None = None
    volatility_annual: float | None = None


class SimulationTrade(BaseModel):
    action: str
    ts_code: str
    date: str
    price: float
    shares: int
    pnl: float | None = None
    pnl_pct: float | None = None
    fee: float = 0
    stamp_duty: float = 0
    transfer_fee: float = 0
    reason: str = ""


class SimulationEquityPoint(BaseModel):
    date: str
    equity: float
    cash: float
    positions: int
    regime: str


class SimulationResponse(BaseModel):
    summary: dict
    metrics: SimulationMetrics | None = None
    equity_curve: list[SimulationEquityPoint]
    benchmark_curve: list[dict] = []
    trades: list[SimulationTrade]
    rejected_entries: list[dict] = []
    resonance_summary: dict = {}
    positions: list[dict] = []

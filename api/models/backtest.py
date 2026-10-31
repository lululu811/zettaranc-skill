"""回测模型"""

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    ts_code: str
    days: int = Field(default=250, ge=30, le=1000)
    initial_capital: float = Field(default=100000, ge=10000)
    stop_loss_pct: float = Field(default=0.07, ge=0.01, le=0.5)
    take_profit_pct: float = Field(default=0.15, ge=0.01, le=1.0)
    position_pct: float = Field(default=1.0, ge=0.1, le=1.0)


class MultiBacktestRequest(BaseModel):
    ts_code: str
    days: int = Field(default=240, ge=30, le=1000)
    initial_capital: float = Field(default=100000, ge=10000)
    position_pct: float = Field(default=0.3, ge=0.1, le=1.0)
    stop_loss_pct: float = Field(default=0.07, ge=0.01, le=0.5)
    take_profit_pct: float = Field(default=0.15, ge=0.01, le=1.0)


class PortfolioBacktestRequest(BaseModel):
    ts_codes: list[str]
    days: int = Field(default=240, ge=30, le=1000)
    initial_capital: float = Field(default=100000, ge=10000)
    position_pct: float = Field(default=0.2, ge=0.05, le=1.0)
    stop_loss_pct: float = Field(default=0.07, ge=0.01, le=0.5)
    take_profit_pct: float = Field(default=0.15, ge=0.01, le=1.0)


class BacktestTradeItem(BaseModel):
    entry_date: str
    entry_price: float
    exit_date: str | None = None
    exit_price: float | None = None
    exit_reason: str = ""
    pnl_pct: float = 0
    holding_days: int = 0


class BacktestSummary(BaseModel):
    total_trades: int = 0
    win_rate: float = 0
    profit_factor: float = 0
    total_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    avg_holding_days: float = 0
    annualized_return: float = 0
    win_count: int = 0
    loss_count: int = 0
    avg_pnl: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    max_win: float = 0
    max_loss: float = 0


class BacktestResponse(BaseModel):
    ts_code: str
    summary: BacktestSummary
    equity_curve: list[list] = []  # [[date, value], ...]
    trades: list[BacktestTradeItem] = []


class PortfolioBacktestResponse(BaseModel):
    # ts_code 此前未声明 → service 返回的 ts_code 被 Pydantic 静默丢弃
    ts_code: str = ""
    summary: BacktestSummary
    equity_curve: list[list] = []
    trades: list[dict] = []
    # 按标的分组的逐股摘要——此前声明了却从不填充，恒为 []
    per_stock: list[BacktestResponse] = []

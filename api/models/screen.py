"""选股筛选模型"""

from pydantic import BaseModel, Field


class ScreenRequest(BaseModel):
    strategy: str = Field(
        default="B1", description="策略名称（B1/B2/B3/完美图形/超级B1/长安战法/建仓波/吸筹/安全/超跌/突破）"
    )
    limit: int = Field(default=20, ge=1, le=500, description="返回数量上限")
    use_parallel: bool = Field(default=True, description="是否启用多进程")


class StockScoreItem(BaseModel):
    ts_code: str
    name: str = ""
    score: float = 0
    b1_score: float = 0
    trend_score: float = 0
    volume_score: float = 0
    risk_score: float = 0
    rating: str = ""
    reasons: list[str] = []
    warnings: list[str] = []


class ScreenResponse(BaseModel):
    strategy: str
    criteria: str
    count: int
    stocks: list[StockScoreItem] = []


class StrategyInfo(BaseModel):
    alias: str
    criteria: str
    description: str = ""

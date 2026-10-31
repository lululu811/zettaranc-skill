"""选股筛选模型"""

from typing import Any

from pydantic import BaseModel, Field


class ScreenRequest(BaseModel):
    strategy: str = Field(default="B1", description="策略名称（B1/B2/B3/完美图形/超级B1/长安战法/建仓波/吸筹/安全/超跌/突破/简单完美图形-1~3…）")
    limit: int = Field(default=100, ge=0, le=20000, description="扫描多少只股票（不是返回条数；股票池按 ts_code 排序取前 N 只），0=全市场")
    top: int = Field(default=0, ge=0, le=500, description="返回条数上限，0=返回全部命中")
    use_parallel: bool = Field(default=True, description="是否启用多进程")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数覆盖，如 {\"j_threshold\": 20}；键名取自 /strategies 返回的 params[].name",
    )


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
    scanned: int = 0
    matched: int = 0
    params: dict[str, Any] = {}
    stocks: list[StockScoreItem] = []


class StrategyParam(BaseModel):
    """策略可调参数（来自 modules/self_optimizer/param_registry）"""

    name: str
    default: float | int = 0
    min: float | int = 0
    max: float | int = 0
    step: float | int = 1
    description: str = ""


class StrategyInfo(BaseModel):
    alias: str
    criteria: str
    description: str = ""
    params: list[StrategyParam] = []

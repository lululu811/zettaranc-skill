"""选股筛选路由"""

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException

from api.models.screen import ScreenRequest, ScreenResponse, StrategyInfo
from api.services import screen_service

router = APIRouter()


@router.get("/strategies", response_model=list[StrategyInfo])
def list_strategies():
    """列出所有可用选股策略"""
    return screen_service.get_strategies()


@router.post("/run", response_model=ScreenResponse)
def run_screen(req: ScreenRequest):
    """执行选股筛选"""
    try:
        return screen_service.run_screen(
            strategy=req.strategy,
            limit=req.limit,
            use_parallel=req.use_parallel,
        )
    except Exception as e:
        raise_api_error(e, prefix="筛选失败")

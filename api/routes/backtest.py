"""策略回测路由"""

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException

from api.models.backtest import (
    BacktestRequest,
    BacktestResponse,
    MultiBacktestRequest,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
)
from api.services import backtest_service

router = APIRouter()


@router.post("/shaofu", response_model=BacktestResponse)
def run_shaofu(req: BacktestRequest):
    """少妇战法单股回测"""
    try:
        return backtest_service.run_shaofu(
            ts_code=req.ts_code,
            days=req.days,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
            position_pct=req.position_pct,
        )
    except Exception as e:
        raise_api_error(e, prefix="回测失败")


@router.post("/multi", response_model=BacktestResponse)
def run_multi(req: MultiBacktestRequest):
    """多策略融合回测"""
    try:
        return backtest_service.run_multi(
            ts_code=req.ts_code,
            days=req.days,
            initial_capital=req.initial_capital,
            position_pct=req.position_pct,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
        )
    except Exception as e:
        raise_api_error(e, prefix="回测失败")


@router.post("/portfolio", response_model=PortfolioBacktestResponse)
def run_portfolio(req: PortfolioBacktestRequest):
    """多股票组合回测"""
    try:
        return backtest_service.run_portfolio(
            ts_codes=req.ts_codes,
            days=req.days,
            initial_capital=req.initial_capital,
            position_pct=req.position_pct,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
        )
    except Exception as e:
        raise_api_error(e, prefix="回测失败")

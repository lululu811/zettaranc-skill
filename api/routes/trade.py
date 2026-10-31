"""交易记录路由"""

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException, Query

from api.models.trade import (
    TradeAddRequest,
    TradeListResponse,
    TradeParseResult,
    TradeStatsResponse,
)
from api.models.common import StatusResponse
from api.services import trade_service

router = APIRouter()


@router.get("/", response_model=TradeListResponse)
def list_trades(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ts_code: str | None = Query(default=None),
):
    """列出交易记录"""
    try:
        return trade_service.list_trades(page=page, page_size=page_size, ts_code=ts_code)
    except Exception as e:
        raise_api_error(e, prefix="获取列表失败")


@router.post("/parse", response_model=TradeParseResult)
def parse_trade(req: TradeAddRequest):
    """解析口语化交易描述（不保存）"""
    try:
        return trade_service.parse_trade(req.text)
    except Exception as e:
        raise_api_error(e, prefix="解析失败")


@router.post("/")
def add_trade(req: TradeAddRequest):
    """解析并保存交易记录"""
    try:
        return trade_service.add_trade(req.text)
    except Exception as e:
        raise_api_error(e, prefix="保存失败")


@router.put("/{trade_id}", response_model=StatusResponse)
def update_trade(trade_id: int, updates: dict):
    """更新交易记录"""
    try:
        return trade_service.update_trade(trade_id, updates)
    except Exception as e:
        raise_api_error(e, prefix="更新失败")


@router.delete("/{trade_id}", response_model=StatusResponse)
def delete_trade(trade_id: int):
    """删除交易记录"""
    try:
        return trade_service.delete_trade(trade_id)
    except Exception as e:
        raise_api_error(e, prefix="删除失败")


@router.get("/stats", response_model=TradeStatsResponse)
def get_stats(ts_code: str | None = Query(default=None)):
    """获取交易统计"""
    try:
        return trade_service.get_stats(ts_code=ts_code)
    except Exception as e:
        raise_api_error(e, prefix="获取统计失败")

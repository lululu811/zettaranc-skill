"""股票分析路由"""

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException, Query

from api.models.stock import (
    StockAnalysisResponse,
    KlineChartResponse,
    FullIndicatorResponse,
    StockSearchResponse,
)
from api.services import stock_service

router = APIRouter()


@router.get("/search", response_model=StockSearchResponse)
def search_stocks(q: str = Query(default="", max_length=32), limit: int = Query(default=10, ge=1, le=50)):
    """股票联想搜索：代码前缀 / 中文名称 / 拼音（首字母或全拼）"""
    try:
        items = stock_service.search_stocks(q, limit)
        return {"query": q, "total": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")


@router.get("/analyze/{ts_code}", response_model=StockAnalysisResponse)
def analyze_stock(ts_code: str, days: int = Query(default=120, ge=10, le=1000)):
    """全量分析：指标 + 战法 + 评分 + 诊断"""
    try:
        return stock_service.get_full_analysis(ts_code, days)
    except Exception as e:
        raise_api_error(e, prefix="分析失败")


@router.get("/analyze/{ts_code}/klines", response_model=KlineChartResponse)
def get_klines(ts_code: str, days: int = Query(default=120, ge=10, le=1000)):
    """获取 K 线图表数据（ECharts 列式格式）"""
    try:
        return stock_service.get_kline_chart_data(ts_code, days)
    except Exception as e:
        raise_api_error(e, prefix="获取 K 线失败")


@router.get("/analyze/{ts_code}/signals")
def get_signals(ts_code: str, days: int = Query(default=120, ge=10, le=1000)):
    """获取战法信号列表"""
    try:
        return stock_service.get_signals(ts_code, days)
    except Exception as e:
        raise_api_error(e, prefix="获取信号失败")


@router.get("/score/{ts_code}")
def get_score(ts_code: str):
    """获取综合评分"""
    try:
        return stock_service.get_score(ts_code)
    except Exception as e:
        raise_api_error(e, prefix="获取评分失败")

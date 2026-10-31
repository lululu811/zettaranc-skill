"""Z哥点评路由"""

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException, Query

from api.models.commentary import CommentaryResponse
from api.services import stock_service
from modules import commentary_service

router = APIRouter()


@router.post("/commentary/{ts_code}", response_model=CommentaryResponse)
def generate_commentary(
    ts_code: str,
    days: int = Query(default=120, ge=10, le=1000),
):
    """生成 Z哥风格股票点评（LLM）"""
    try:
        analysis = stock_service.get_full_analysis(ts_code, days)
    except Exception as e:
        raise_api_error(e, prefix="分析数据获取失败")

    result = commentary_service.generate_commentary(analysis)

    if result.get("error") == "llm_not_configured":
        raise HTTPException(status_code=503, detail=result["commentary_text"])

    if result.get("error") == "llm_failed":
        raise HTTPException(status_code=502, detail=result["commentary_text"])

    return result

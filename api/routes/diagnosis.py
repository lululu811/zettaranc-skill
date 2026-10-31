"""持仓诊断路由"""

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException, Query

from api.models.diagnosis import DiagnosisResponse
from api.services import diagnosis_service

router = APIRouter()


@router.get("/{ts_code}", response_model=DiagnosisResponse)
def diagnose_stock(ts_code: str, days: int = Query(default=120, ge=10, le=1000)):
    """对单只股票进行完整持仓诊断"""
    try:
        return diagnosis_service.diagnose(ts_code, days)
    except Exception as e:
        raise_api_error(e, prefix="诊断失败")

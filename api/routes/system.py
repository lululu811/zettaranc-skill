"""系统路由 — 健康检查 + 数据同步"""

import logging
from pathlib import Path

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException

from api.models.common import StatusResponse
from api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health_check():
    """健康检查"""
    db_path = Path(settings.db_path)
    db_exists = db_path.exists()
    return {
        "status": "ok",
        "data_mode": settings.data_mode,
        "db_exists": db_exists,
        "version": "1.0.0",
    }


@router.get("/sync/status")
def sync_status():
    """获取数据同步状态"""
    try:
        from modules.database import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT data_type, ts_code, last_date, status, message FROM sync_log ORDER BY id DESC LIMIT 50"
            ).fetchall()

        logs = []
        for row in rows:
            logs.append(
                {
                    "data_type": row[0],
                    "ts_code": row[1],
                    "last_date": row[2],
                    "status": row[3],
                    "message": row[4],
                }
            )
        return {"logs": logs}
    except Exception as e:
        raise_api_error(e, prefix="获取同步状态失败")


@router.post("/sync/{ts_code}", response_model=StatusResponse)
def sync_stock(ts_code: str, days: int = 730, indicators: bool = True):
    """触发单只股票数据同步"""
    try:
        from modules.data_sync import DataSyncer

        syncer = DataSyncer()
        syncer.sync_daily_kline(ts_code, days=days)
        if indicators:
            syncer.sync_indicator_cache(ts_code, days=days)
        return StatusResponse(status="ok", message=f"{ts_code} 同步完成")
    except Exception as e:
        raise_api_error(e, prefix="同步失败")

#!/usr/bin/env python3
"""Z哥量化 API — FastAPI 入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.routes.backtest import router as backtest_router
from api.routes.commentary import router as commentary_router
from api.routes.diagnosis import router as diagnosis_router
from api.routes.screen import router as screen_router
from api.routes.simulator import router as simulator_router
from api.routes.stock import router as stock_router
from api.routes.system import router as system_router
from api.routes.trade import router as trade_router
from api.routes.watchlist import router as watchlist_router
from api.utils.errors import ApiError
from modules.core.command_result import http_status_for
from modules.core.errors import ZettarancError

logger = logging.getLogger("zettaranc-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动 / 关闭生命周期"""
    logger.info("Z哥量化 API 启动 (mode=%s, db=%s)", settings.data_mode, settings.db_path)
    yield
    logger.info("Z哥量化 API 关闭")


app = FastAPI(
    title="Z哥量化 API",
    description="zettaranc 量化交易工具 REST API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    """API 统一错误外壳 —— 扁平结构，与 CLI ``--json`` 的形状一致。

    FastAPI 默认会把 ``HTTPException.detail`` 包进 ``{"detail": ...}``，那样
    响应体就变成 ``{"detail": {"ok": false, ...}}``，与 CLI 的
    ``{"ok": false, ...}`` 不同形，宿主要写两套解析。这里直接输出扁平外壳。
    """
    return JSONResponse(status_code=exc.status_code, content=exc.payload)


@app.exception_handler(ZettarancError)
async def zettaranc_error_handler(request: Request, exc: ZettarancError):
    """结构化错误 → 带 error_code 的 HTTP 响应。

    路由层的 ``except Exception`` 已把这类异常转成 ``ApiError``（状态码按错误码
    判定）；这个处理器兜底那些没进路由 try 块的路径（如中间件、依赖注入）。
    """
    from modules.core.command_result import exception_to_dict

    logger.warning("结构化错误: %s", exc)
    return JSONResponse(
        status_code=http_status_for(exc),
        content=exception_to_dict(exc),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未分类异常兜底 —— 仍输出统一外壳，错误码为 INTERNAL_ERROR。"""
    from modules.core.command_result import exception_to_dict

    logger.exception("未处理异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content=exception_to_dict(exc),
    )


# ── 注册路由 ──
prefix = settings.api_prefix
app.include_router(stock_router, prefix=f"{prefix}/stock", tags=["stock"])
app.include_router(screen_router, prefix=f"{prefix}/screen", tags=["screen"])
app.include_router(watchlist_router, prefix=f"{prefix}/watchlist", tags=["watchlist"])
app.include_router(diagnosis_router, prefix=f"{prefix}/diagnosis", tags=["diagnosis"])
app.include_router(backtest_router, prefix=f"{prefix}/backtest", tags=["backtest"])
app.include_router(simulator_router, prefix=f"{prefix}/simulator", tags=["simulator"])
app.include_router(trade_router, prefix=f"{prefix}/trade", tags=["trade"])
app.include_router(system_router, prefix=f"{prefix}/system", tags=["system"])
app.include_router(commentary_router, prefix=f"{prefix}", tags=["commentary"])


def start_web():
    """启动 API 服务，供 zt-web 快捷指令调用"""
    import uvicorn

    print("=" * 60)
    print("  Z哥量化 PC 看板后端 API 服务已启动")
    print(f"  地址: http://127.0.0.1:{settings.api_port}")
    print("  请打开 React 前端项目 (npm run dev) 进行数据可视化浏览")
    print("=" * 60)
    uvicorn.run("api.main:app", host="0.0.0.0", port=settings.api_port, reload=False)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=settings.api_port, reload=True)

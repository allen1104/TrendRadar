"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import configure_logging
from app.core.middleware import TraceIdMiddleware
from app.core.redis import redis_client
from app.modules.ai.api import router as ai_admin_router
from app.modules.auth.api import admin_router as auth_admin_router
from app.modules.auth.api import router as auth_router
from app.modules.source.api import router as source_admin_router

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("app.startup", env=settings.APP_ENV)
    yield
    await redis_client.aclose()
    log.info("app.shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI 驱动的全球科技热点发现平台",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    headers = {}
    if retry_after := exc.extra.get("retryAfter"):
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "errorCode": exc.error_code, **exc.extra},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求参数校验失败",
            "errorCode": "VALIDATION_ERROR",
            "errors": [
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
            ],
        },
    )


@app.get("/api/v1/health", tags=["health"], summary="存活探针")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready", tags=["health"], summary="就绪探针")
async def ready() -> JSONResponse:
    from sqlalchemy import text

    from app.db.session import engine

    checks: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc.__class__.__name__}"
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"

    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )


app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(ai_admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(source_admin_router, prefix=settings.API_V1_PREFIX)

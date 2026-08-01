"""为每个请求注入 trace_id，并记录访问日志。"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger()


def _client_ip(request: Request) -> str:
    """取真实客户端 IP（考虑反向代理）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "http.error", method=request.method, path=request.url.path, trace_id=trace_id
            )
            structlog.contextvars.clear_contextvars()
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Trace-Id"] = trace_id
        log.info(
            "http.access",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        structlog.contextvars.clear_contextvars()
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """把客户端 IP / User-Agent 写到 request.state + structlog context，

    供 AuditService 写入 audit_log 时取。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ip = _client_ip(request)
        ua = request.headers.get("user-agent", "")[:500]
        request.state.client_ip = ip
        request.state.user_agent = ua
        structlog.contextvars.bind_contextvars(client_ip=ip, user_agent=ua[:80])
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("client_ip", "user_agent")
        return response

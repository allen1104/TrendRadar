"""统一异常体系。业务异常继承 AppException，由全局 handler 转 HTTP 响应。"""

from typing import Any


class AppException(Exception):  # noqa: N818 (intentionally abstract)
    """所有业务异常的基类。

    约定：status_code 用 RESTful 原生语义，error_code 用大写下划线常量。
    响应体统一 {"detail": ..., "errorCode": ...}
    """

    status_code: int = 400
    error_code: str = "BAD_REQUEST"
    detail: str = "请求错误"

    def __init__(
        self,
        detail: str | None = None,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.detail
        self.error_code = error_code or self.error_code
        self.status_code = status_code or self.status_code
        self.extra = extra or {}
        super().__init__(self.detail)


class NotFoundError(AppException):
    status_code = 404
    error_code = "NOT_FOUND"
    detail = "资源不存在"


class ConflictError(AppException):
    status_code = 409
    error_code = "CONFLICT"
    detail = "资源冲突"


class UnauthorizedError(AppException):
    status_code = 401
    error_code = "UNAUTHORIZED"
    detail = "未登录或登录已失效"


class ForbiddenError(AppException):
    status_code = 403
    error_code = "FORBIDDEN"
    detail = "权限不足"


class RateLimitError(AppException):
    status_code = 429
    error_code = "TOO_MANY_REQUESTS"
    detail = "请求过于频繁，请稍后重试"


class ExternalServiceError(AppException):
    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"
    detail = "外部服务调用失败"

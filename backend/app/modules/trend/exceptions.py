"""trend 业务异常。"""

from __future__ import annotations

from app.core.exceptions import AppException


class TrendWindowInvalidError(AppException):
    """window 参数非法。"""

    status_code = 400
    error_code = "TREND_WINDOW_INVALID"
    detail = "时间窗口参数无效"


class TrendMetricInvalidError(AppException):
    """metric 参数非法。"""

    status_code = 400
    error_code = "TREND_METRIC_INVALID"
    detail = "排行指标参数无效"


class EntityTypeInvalidError(AppException):
    """entityType 参数非法。"""

    status_code = 400
    error_code = "ENTITY_TYPE_INVALID"
    detail = "实体类型参数无效"


class TrendLimitOutOfRangeError(AppException):
    """limit 超出 [1, 300] 范围。"""

    status_code = 400
    error_code = "TREND_LIMIT_OUT_OF_RANGE"
    detail = "limit 必须在 1-300 之间"

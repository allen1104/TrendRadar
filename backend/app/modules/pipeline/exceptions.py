"""pipeline 业务异常。"""

from __future__ import annotations

from app.core.exceptions import AppException


class ArticleNotFoundError(AppException):
    status_code = 404
    error_code = "ARTICLE_NOT_FOUND"
    detail = "文章不存在"


class EventNotFoundError(AppException):
    status_code = 404
    error_code = "EVENT_NOT_FOUND"
    detail = "事件不存在"


class ArticleNotInEventError(AppException):
    status_code = 400
    error_code = "ARTICLE_NOT_IN_EVENT"
    detail = "指定文章不属于该事件"


class CannotSplitAllError(AppException):
    status_code = 400
    error_code = "CANNOT_SPLIT_ALL"
    detail = "不能把事件的所有文章全部拆走"


class CannotMergeSelfError(AppException):
    status_code = 400
    error_code = "CANNOT_MERGE_SELF"
    detail = "源事件与目标事件不能相同"


class FullRerunRequiresSinceError(AppException):
    status_code = 400
    error_code = "FULL_RERUN_REQUIRES_SINCE"
    detail = "全量重跑必须指定 since 时间范围"


class InvalidPipelineStageError(AppException):
    status_code = 400
    error_code = "INVALID_PIPELINE_STAGE"
    detail = "非法 pipeline 阶段"
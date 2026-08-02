"""creation 模块业务异常。

按 SPEC-creation.md「错误情况」对齐到 AppException 的 status_code + error_code + detail。
"""

from __future__ import annotations

from app.core.exceptions import AppException


class DraftNotFoundError(AppException):
    status_code = 404
    error_code = "DRAFT_NOT_FOUND"
    detail = "草稿不存在"


class EventNotAnalyzedError(AppException):
    status_code = 409
    error_code = "EVENT_NOT_ANALYZED"
    detail = "事件尚未完成 AI 分析，无法生成草稿"


class InvalidPlatformError(AppException):
    status_code = 400
    error_code = "INVALID_PLATFORM"
    detail = "platform 不合法"


class InvalidStyleError(AppException):
    status_code = 400
    error_code = "INVALID_STYLE"
    detail = "style 不合法"


class TargetWordsOutOfRangeError(AppException):
    status_code = 400
    error_code = "TARGET_WORDS_OUT_OF_RANGE"
    detail = "目标字数超出该平台范围的 ±50%"


class TooManyRegenerationsError(AppException):
    status_code = 400
    error_code = "TOO_MANY_REGENERATIONS"
    detail = "已达重新生成上限 5 次"


class QuotaExceededError(AppException):
    status_code = 400
    error_code = "QUOTA_EXCEEDED"
    detail = "草稿数量已达上限 500"


class InvalidExportFormatError(AppException):
    status_code = 400
    error_code = "INVALID_EXPORT_FORMAT"
    detail = "导出格式不合法"
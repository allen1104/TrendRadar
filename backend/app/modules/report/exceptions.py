"""report 模块业务异常。
按 SPEC-report.md「错误情况」对齐到 AppException 的 status_code + error_code + detail。
"""

from __future__ import annotations

from app.core.exceptions import AppException


class ReportNotFoundError(AppException):
    status_code = 404
    error_code = "REPORT_NOT_FOUND"
    detail = "日报不存在"


class ReportItemNotFoundError(AppException):
    status_code = 404
    error_code = "REPORT_ITEM_NOT_FOUND"
    detail = "日报条目不存在"


class ReportAlreadyExistsError(AppException):
    status_code = 409
    error_code = "REPORT_ALREADY_EXISTS"
    detail = "该日期该类型日报已存在"


class ReportAlreadyPublishedError(AppException):
    status_code = 400
    error_code = "REPORT_ALREADY_PUBLISHED"
    detail = "日报已发布"


class ReportHasNoItemsError(AppException):
    status_code = 400
    error_code = "REPORT_HAS_NO_ITEMS"
    detail = "日报条目数为 0，无法发布"


class InvalidReportTypeError(AppException):
    status_code = 400
    error_code = "INVALID_REPORT_TYPE"
    detail = "日报类型不合法"


class InvalidExportFormatError(AppException):
    status_code = 400
    error_code = "INVALID_EXPORT_FORMAT"
    detail = "导出格式不合法"


class WebhookUrlRequiredError(AppException):
    status_code = 400
    error_code = "WEBHOOK_URL_REQUIRED"
    detail = "channel=WEBHOOK 时必须填写 webhookUrl"


class CandidatesInsufficientError(AppException):
    """候选池不足最小条目数 → 跳过当日生成。"""

    status_code = 200  # 不算错误，但抛错便于上层区分处理
    error_code = "CANDIDATES_INSUFFICIENT"
    detail = "候选事件不足，跳过当日日报"

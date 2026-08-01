"""collection 模块业务异常。"""

from __future__ import annotations

from app.core.exceptions import AppException

# ----------------------------------------------------------------- 收藏夹


class FolderNotFoundError(AppException):
    status_code = 404
    error_code = "FOLDER_NOT_FOUND"
    detail = "收藏夹不存在"


class FolderNameExistsError(AppException):
    status_code = 409
    error_code = "FOLDER_NAME_EXISTS"
    detail = "同名收藏夹已存在"


class FolderNameRequiredError(AppException):
    status_code = 400
    error_code = "FOLDER_NAME_REQUIRED"
    detail = "收藏夹名称不能为空"


class CannotDeleteDefaultFolderError(AppException):
    status_code = 400
    error_code = "CANNOT_DELETE_DEFAULT_FOLDER"
    detail = "不能删除默认收藏夹"


class FolderQuotaExceededError(AppException):
    status_code = 400
    error_code = "QUOTA_EXCEEDED"
    detail = "收藏夹数量已达上限（50 个）"


# ----------------------------------------------------------------- 条目


class ItemNotFoundError(AppException):
    status_code = 404
    error_code = "ITEM_NOT_FOUND"
    detail = "收藏条目不存在"


class AlreadyCollectedError(AppException):
    status_code = 409
    error_code = "ALREADY_COLLECTED"
    detail = "该事件已在收藏中"


class ItemQuotaExceededError(AppException):
    status_code = 400
    error_code = "QUOTA_EXCEEDED"
    detail = "收藏条目已达上限（10000 个）"


class EventNotFoundForCollectError(AppException):
    status_code = 404
    error_code = "EVENT_NOT_FOUND"
    detail = "要收藏的事件不存在"


class InvalidBatchActionError(AppException):
    status_code = 400
    error_code = "INVALID_BATCH_ACTION"
    detail = "批量操作类型无效"
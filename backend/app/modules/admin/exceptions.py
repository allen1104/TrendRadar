"""admin 模块业务异常。"""

from __future__ import annotations

from app.core.exceptions import AppException


# ----------------------------------------------------------------- 配置


class ConfigNotFoundError(AppException):
    status_code = 404
    error_code = "CONFIG_NOT_FOUND"
    detail = "系统配置项不存在"


class ConfigReadOnlyError(AppException):
    status_code = 403
    error_code = "CONFIG_READONLY"
    detail = "该配置项不允许后台修改"


class ConfigValueOutOfRangeError(AppException):
    status_code = 400
    error_code = "CONFIG_VALUE_OUT_OF_RANGE"
    detail = "配置值超出允许范围"


class ConfigTypeMismatchError(AppException):
    status_code = 400
    error_code = "CONFIG_TYPE_MISMATCH"
    detail = "配置值类型与声明不符"


class RankWeightsSumInvalidError(AppException):
    status_code = 400
    error_code = "RANK_WEIGHTS_SUM_INVALID"
    detail = "rank_weights 四项之和必须等于 1"


# ----------------------------------------------------------------- 任务


class TaskNotFoundError(AppException):
    status_code = 400
    error_code = "TASK_NOT_FOUND"
    detail = "Celery 任务未注册"


class TaskNotTriggerableError(AppException):
    status_code = 403
    error_code = "TASK_NOT_MANUALLY_TRIGGERABLE"
    detail = "该任务不支持手动触发"


class TaskAlreadyRunningError(AppException):
    status_code = 409
    error_code = "TASK_ALREADY_RUNNING"
    detail = "任务正在运行中，请等待完成"


class TaskNotFailedError(AppException):
    status_code = 400
    error_code = "TASK_NOT_FAILED"
    detail = "只能重试状态为 FAILED 的任务"
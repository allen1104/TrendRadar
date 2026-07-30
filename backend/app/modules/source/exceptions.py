"""source 模块业务异常。"""

from app.core.exceptions import AppException


class SourceNotFoundError(AppException):
    status_code = 404
    error_code = "SOURCE_NOT_FOUND"
    detail = "采集源不存在"


class SourceNameExistsError(AppException):
    status_code = 409
    error_code = "SOURCE_NAME_EXISTS"
    detail = "采集源名称已被使用"


class PluginNotFoundError(AppException):
    status_code = 400
    error_code = "PLUGIN_NOT_FOUND"
    detail = "plugin_key 未注册，请确认模块已安装且导入"


class InvalidCronError(AppException):
    status_code = 400
    error_code = "INVALID_CRON"
    detail = "cron 表达式非法（标准 5 段式）"


class SourceAutoDisabledError(AppException):
    status_code = 400
    error_code = "SOURCE_AUTO_DISABLED"
    detail = "采集源连续失败次数已达上限，已自动禁用"


class RunLogNotFoundError(AppException):
    status_code = 404
    error_code = "RUN_LOG_NOT_FOUND"
    detail = "运行日志不存在"

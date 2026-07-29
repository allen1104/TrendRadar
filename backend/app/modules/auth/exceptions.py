"""auth 模块业务异常。"""

from app.core.exceptions import AppException


class EmailExistsError(AppException):
    status_code = 409
    error_code = "EMAIL_EXISTS"
    detail = "该邮箱已被注册"


class UsernameExistsError(AppException):
    status_code = 409
    error_code = "USERNAME_EXISTS"
    detail = "该用户名已被占用"


class WeakPasswordError(AppException):
    status_code = 400
    error_code = "WEAK_PASSWORD"
    detail = "密码至少 8 位，且需同时包含大写字母、小写字母和数字"


class InvalidCredentialsError(AppException):
    status_code = 401
    error_code = "INVALID_CREDENTIALS"
    # 不区分"邮箱不存在"和"密码错误"，防用户枚举
    detail = "邮箱或密码错误"


class AccountDisabledError(AppException):
    status_code = 403
    error_code = "ACCOUNT_DISABLED"
    detail = "账号已被禁用，请联系管理员"


class InvalidRefreshTokenError(AppException):
    status_code = 401
    error_code = "INVALID_REFRESH_TOKEN"
    detail = "登录已失效，请重新登录"


class WrongOldPasswordError(AppException):
    status_code = 400
    error_code = "WRONG_OLD_PASSWORD"
    detail = "原密码错误"


class UserNotFoundError(AppException):
    status_code = 404
    error_code = "USER_NOT_FOUND"
    detail = "用户不存在"


class CannotModifySelfRoleError(AppException):
    status_code = 400
    error_code = "CANNOT_MODIFY_SELF_ROLE"
    detail = "不能修改自己的角色或状态"


class LastAdminProtectedError(AppException):
    status_code = 400
    error_code = "LAST_ADMIN_PROTECTED"
    detail = "系统必须保留至少一个启用中的管理员"


class InvalidSortFieldError(AppException):
    status_code = 400
    error_code = "INVALID_SORT_FIELD"
    detail = "不支持的排序字段"

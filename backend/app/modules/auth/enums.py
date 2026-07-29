"""auth 模块枚举。

全局约定：枚举用大写下划线字符串存储，不用数字。
"""

from enum import StrEnum


class Role(StrEnum):
    """单角色 RBAC，权限自上而下包含：GUEST < USER < EDITOR < ADMIN。"""

    GUEST = "GUEST"
    USER = "USER"
    EDITOR = "EDITOR"
    ADMIN = "ADMIN"


ROLE_LEVEL: dict[Role, int] = {
    Role.GUEST: 0,
    Role.USER: 10,
    Role.EDITOR: 20,
    Role.ADMIN: 30,
}

# 可分配给用户的角色（GUEST 不落库，只表示匿名请求）
ASSIGNABLE_ROLES = (Role.USER, Role.EDITOR, Role.ADMIN)


def role_level(role: Role | str) -> int:
    return ROLE_LEVEL.get(Role(role), 0)


def has_role(actual: Role | str, required: Role | str) -> bool:
    """角色包含判断，用数值比较实现。"""
    return role_level(actual) >= role_level(required)


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class DefaultScope(StrEnum):
    """用户偏好里的默认时间维度，与 hotspot 的 scope 对齐。"""

    TODAY = "TODAY"
    WEEK = "WEEK"
    MONTH = "MONTH"

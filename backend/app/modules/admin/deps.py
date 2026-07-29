"""admin 模块依赖。转发到 auth 模块以避免循环 import。"""

from app.modules.auth.deps import (  # noqa: F401
    AdminUser,
    DbSession,
    EditorUser,
)

__all__ = ["AdminUser", "DbSession", "EditorUser"]

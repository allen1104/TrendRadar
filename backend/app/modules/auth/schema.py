"""auth 模块 DTO。

全局约定：出参 camelCase（CamelModel 自动转），时间 ISO 8601 带时区。
"""

from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.core.schema import CamelModel
from app.modules.auth.enums import ASSIGNABLE_ROLES, DefaultScope, Role, UserStatus

# ---------------------------------------------------------------- 请求


class RegisterRequest(CamelModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("用户名不能为空")
        return v


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(CamelModel):
    refresh_token: str = Field(min_length=1)


class UpdateProfileRequest(CamelModel):
    username: str | None = Field(default=None, min_length=2, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(CamelModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UpdatePreferenceRequest(CamelModel):
    default_scope: DefaultScope | None = None
    followed_categories: list[str] | None = Field(default=None, max_length=20)
    followed_tags: list[int] | None = Field(default=None, max_length=100)
    muted_sources: list[int] | None = Field(default=None, max_length=100)
    daily_report_opt_in: bool | None = None


class AdminUpdateUserRequest(CamelModel):
    role: Role | None = None
    status: UserStatus | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_assignable(cls, v: Role | None) -> Role | None:
        if v is not None and v not in ASSIGNABLE_ROLES:
            raise ValueError("GUEST 不是可分配的角色")
        return v


# ---------------------------------------------------------------- 响应


class PreferenceResponse(CamelModel):
    default_scope: DefaultScope
    followed_categories: list[str]
    followed_tags: list[int]
    muted_sources: list[int]
    daily_report_opt_in: bool


class UserBrief(CamelModel):
    """登录响应中的精简用户信息。"""

    user_id: int
    email: EmailStr
    username: str
    avatar_url: str | None = None
    role: Role


class RegisterResponse(CamelModel):
    user_id: int
    email: EmailStr
    username: str
    role: Role


class TokenResponse(CamelModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105 (HTTP token type, not a password)
    expires_in: int
    user: UserBrief


class MeResponse(CamelModel):
    user_id: int
    email: EmailStr
    username: str
    avatar_url: str | None = None
    role: Role
    last_login_at: datetime | None = None
    preference: PreferenceResponse


class AdminUserItem(CamelModel):
    user_id: int
    email: EmailStr
    username: str
    avatar_url: str | None = None
    role: Role
    status: UserStatus
    last_login_at: datetime | None = None
    created_at: datetime

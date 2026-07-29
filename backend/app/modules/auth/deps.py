"""认证与权限依赖。其他模块统一从这里 import。

用法：
    @router.get("/x")
    async def x(user: CurrentUser): ...                     # 需登录
    @router.get("/y", dependencies=[Depends(require_role(Role.EDITOR))])
    async def y(): ...                                      # 需 EDITOR 及以上
    async def z(user: OptionalUser): ...                    # GUEST 可访问
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import TokenPayload, decode_token
from app.db.session import get_db
from app.modules.auth.enums import Role, UserStatus, has_role
from app.modules.auth.model import User
from app.modules.auth.repository import UserRepository
from app.modules.auth.service import AuthService

_bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db)]
_Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def get_token_payload(credentials: _Credentials) -> TokenPayload:
    """解析并校验 access token（不查库）。"""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError
    payload = decode_token(credentials.credentials, "access")
    if payload is None:
        raise UnauthorizedError
    return payload


async def get_current_user(
    payload: Annotated[TokenPayload, Depends(get_token_payload)],
    session: DbSession,
) -> User:
    """需登录。校验黑名单 + 账号状态。"""
    service = AuthService(session)
    if await service.is_token_blacklisted(payload.jti):
        raise UnauthorizedError("登录已失效，请重新登录")

    user = await UserRepository(session).get_by_id(payload.user_id)
    if user is None:
        raise UnauthorizedError
    if user.status != UserStatus.ACTIVE.value:
        raise ForbiddenError("账号已被禁用，请联系管理员", error_code="ACCOUNT_DISABLED")
    return user


async def get_current_user_optional(
    credentials: _Credentials,
    session: DbSession,
) -> User | None:
    """GUEST 可访问的接口用这个。无 Token 或 Token 无效一律返回 None，不抛异常。"""
    if credentials is None or not credentials.credentials:
        return None
    payload = decode_token(credentials.credentials, "access")
    if payload is None:
        return None
    if await AuthService(session).is_token_blacklisted(payload.jti):
        return None
    user = await UserRepository(session).get_by_id(payload.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        return None
    return user


def require_role(min_role: Role):
    """角色门槛依赖。GUEST < USER < EDITOR < ADMIN，数值比较。"""

    async def _dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not has_role(user.role, min_role):
            raise ForbiddenError(f"需要 {min_role.value} 及以上权限")
        return user

    return _dependency


def current_role(user: User | None) -> Role:
    """把可选用户折叠成角色，便于统一做可见性判断。"""
    return Role(user.role) if user is not None else Role.GUEST


async def request_ip(request: Request) -> str:
    from app.core.rate_limit import client_ip

    return client_ip(request)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
CurrentTokenPayload = Annotated[TokenPayload, Depends(get_token_payload)]
EditorUser = Annotated[User, Depends(require_role(Role.EDITOR))]
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]

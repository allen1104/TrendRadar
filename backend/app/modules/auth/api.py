"""auth 模块路由。

接口定义见 doc/SPEC-auth.md「后端接口」。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.pagination import PageParams, page_params
from app.core.rate_limit import check_rate_limit, client_ip
from app.core.schema import Page
from app.modules.auth.deps import (
    AdminUser,
    CurrentTokenPayload,
    CurrentUser,
    DbSession,
)
from app.modules.auth.enums import Role, UserStatus
from app.modules.auth.schema import (
    AdminUpdateUserRequest,
    AdminUserItem,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    PreferenceResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UpdatePreferenceRequest,
    UpdateProfileRequest,
)
from app.modules.auth.service import AdminUserService, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin/users", tags=["admin:users"])


# ---------------------------------------------------------------- 公开


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
)
async def register(
    payload: RegisterRequest, request: Request, session: DbSession
) -> RegisterResponse:
    await check_rate_limit("register", client_ip(request), limit=10, window=60)
    return await AuthService(session).register(payload)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    await check_rate_limit("login", client_ip(request), limit=10, window=60)
    return await AuthService(session).login(payload)


@router.post("/refresh", response_model=TokenResponse, summary="刷新 Token（旋转）")
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenResponse:
    return await AuthService(session).refresh(payload.refresh_token)


# ---------------------------------------------------------------- 需登录


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="登出")
async def logout(token: CurrentTokenPayload, session: DbSession) -> None:
    await AuthService(session).logout(token)


@router.get("/me", response_model=MeResponse, summary="获取当前用户信息")
async def get_me(user: CurrentUser, session: DbSession) -> MeResponse:
    return await AuthService(session).get_me(user)


@router.patch("/me", response_model=MeResponse, summary="修改个人资料")
async def update_me(
    payload: UpdateProfileRequest, user: CurrentUser, session: DbSession
) -> MeResponse:
    return await AuthService(session).update_profile(user, payload)


@router.put(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="修改密码（成功后所有 Token 作废）",
)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    session: DbSession,
    token: CurrentTokenPayload,
) -> None:
    await AuthService(session).change_password(user, payload, current_token=token)


@router.put("/me/preference", response_model=PreferenceResponse, summary="更新个人偏好")
async def update_preference(
    payload: UpdatePreferenceRequest, user: CurrentUser, session: DbSession
) -> PreferenceResponse:
    return await AuthService(session).update_preference(user, payload)


# ---------------------------------------------------------------- 仅 ADMIN


@admin_router.get("", response_model=Page[AdminUserItem], summary="用户列表")
async def list_users(
    _: AdminUser,
    session: DbSession,
    pagination: Annotated[PageParams, Depends(page_params)],
    keyword: Annotated[str | None, Query(max_length=100, description="匹配邮箱或用户名")] = None,
    role: Annotated[Role | None, Query(description="角色过滤")] = None,
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None,
    sort: Annotated[str, Query(description="createdAt / lastLoginAt，前缀 - 倒序")] = "-createdAt",
) -> Page[AdminUserItem]:
    return await AdminUserService(session).list_users(
        keyword=keyword,
        role=role,
        status=user_status,
        sort=sort,
        page=pagination.page,
        size=pagination.size,
    )


@admin_router.patch("/{user_id}", response_model=AdminUserItem, summary="修改用户角色或状态")
async def update_user(
    user_id: int,
    payload: AdminUpdateUserRequest,
    operator: AdminUser,
    session: DbSession,
) -> AdminUserItem:
    return await AdminUserService(session).update_user(
        target_id=user_id, payload=payload, operator=operator
    )

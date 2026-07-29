"""auth 模块业务层。

业务规则见 doc/SPEC-auth.md「业务规则」。
"""

import re

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import RedisKey, redis_client
from app.core.schema import Page
from app.core.security import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.modules.auth.enums import Role, UserStatus
from app.modules.auth.exceptions import (
    AccountDisabledError,
    CannotModifySelfRoleError,
    EmailExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidSortFieldError,
    LastAdminProtectedError,
    UsernameExistsError,
    UserNotFoundError,
    WeakPasswordError,
    WrongOldPasswordError,
)
from app.modules.auth.model import User, UserPreference
from app.modules.auth.repository import (
    SORT_FIELDS,
    UserPreferenceRepository,
    UserRepository,
)
from app.modules.auth.schema import (
    AdminUpdateUserRequest,
    AdminUserItem,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    PreferenceResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UpdatePreferenceRequest,
    UpdateProfileRequest,
    UserBrief,
)

log = structlog.get_logger()

LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW = 15 * 60  # 15 分钟


def validate_password_strength(password: str) -> None:
    """≥8 位，且同时含大写字母、小写字母、数字。"""
    if (
        len(password) < 8
        or not re.search(r"[a-z]", password)
        or not re.search(r"[A-Z]", password)
        or not re.search(r"\d", password)
    ):
        raise WeakPasswordError


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis | None = None) -> None:
        self.session = session
        self.redis = redis or redis_client
        self.users = UserRepository(session)
        self.prefs = UserPreferenceRepository(session)

    # ------------------------------------------------------------ 注册

    async def register(self, payload: RegisterRequest) -> RegisterResponse:
        validate_password_strength(payload.password)

        email = payload.email.lower()
        if await self.users.email_exists(email):
            raise EmailExistsError
        if await self.users.username_exists(payload.username):
            raise UsernameExistsError

        user = await self.users.create(
            email=email,
            username=payload.username,
            password_hash=hash_password(payload.password),
            role=Role.USER,
        )
        await self.prefs.create_default(user.id)

        log.info("auth.register", user_id=user.id, email=email)
        return RegisterResponse(
            user_id=user.id, email=user.email, username=user.username, role=Role(user.role)
        )

    # ------------------------------------------------------------ 登录

    async def login(self, payload: LoginRequest) -> TokenResponse:
        email = payload.email.lower()
        await self._assert_not_locked(email)

        user = await self.users.get_by_email(email)
        if user is None or not verify_password(payload.password, user.password_hash):
            await self._record_login_failure(email)
            raise InvalidCredentialsError

        if user.status != UserStatus.ACTIVE.value:
            raise AccountDisabledError

        await self._clear_login_failures(email)

        # 哈希参数升级时静默重算
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)

        await self.users.touch_last_login(user)
        log.info("auth.login", user_id=user.id)
        return await self._issue_tokens(user)

    async def _assert_not_locked(self, email: str) -> None:
        raw = await self.redis.get(RedisKey.login_fail(email))
        if raw is not None and int(raw) >= LOGIN_FAIL_LIMIT:
            ttl = await self.redis.ttl(RedisKey.login_fail(email))
            from app.core.exceptions import RateLimitError

            raise RateLimitError(
                f"登录失败次数过多，请 {max(ttl, 1)} 秒后重试",
                error_code="TOO_MANY_ATTEMPTS",
                extra={"retryAfter": max(ttl, 1)},
            )

    async def _record_login_failure(self, email: str) -> None:
        key = RedisKey.login_fail(email)
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, LOGIN_FAIL_WINDOW)

    async def _clear_login_failures(self, email: str) -> None:
        await self.redis.delete(RedisKey.login_fail(email))

    # ------------------------------------------------------------ Token

    async def _issue_tokens(self, user: User) -> TokenResponse:
        access_token, _, expires_in = create_access_token(user.id, user.role)
        refresh_token, refresh_jti, refresh_ttl = create_refresh_token(user.id)
        await self.redis.setex(
            RedisKey.refresh_whitelist(user.id, refresh_jti), refresh_ttl, "1"
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            user=UserBrief(
                user_id=user.id,
                email=user.email,
                username=user.username,
                avatar_url=user.avatar_url,
                role=Role(user.role),
            ),
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        token = decode_token(refresh_token, "refresh")
        if token is None:
            raise InvalidRefreshTokenError

        key = RedisKey.refresh_whitelist(token.user_id, token.jti)
        # 旋转：原子取出并删除。取不到说明已被使用过或已登出
        consumed = await self.redis.getdel(key)
        if consumed is None:
            # 签名有效但不在白名单 → 判定为泄露复用，作废该用户全部 refresh token
            await self._revoke_all_refresh(token.user_id)
            log.warning("auth.refresh_reuse_detected", user_id=token.user_id, jti=token.jti)
            raise InvalidRefreshTokenError

        user = await self.users.get_by_id(token.user_id)
        if user is None:
            raise InvalidRefreshTokenError
        if user.status != UserStatus.ACTIVE.value:
            raise AccountDisabledError

        return await self._issue_tokens(user)

    async def logout(self, access_payload: TokenPayload) -> None:
        """access token 加黑名单；该用户全部 refresh token 作废。"""
        ttl = access_payload.ttl_seconds
        if ttl > 0:
            await self.redis.setex(RedisKey.token_blacklist(access_payload.jti), ttl, "1")
        await self._revoke_all_refresh(access_payload.user_id)
        log.info("auth.logout", user_id=access_payload.user_id)

    async def _revoke_all_refresh(self, user_id: int) -> None:
        pattern = RedisKey.refresh_user_pattern(user_id)
        keys = [key async for key in self.redis.scan_iter(match=pattern, count=200)]
        if keys:
            await self.redis.delete(*keys)

    async def is_token_blacklisted(self, jti: str) -> bool:
        return await self.redis.exists(RedisKey.token_blacklist(jti)) > 0

    # ------------------------------------------------------------ 当前用户

    async def get_me(self, user: User) -> MeResponse:
        pref = await self.prefs.get_or_create(user.id)
        return self._to_me(user, pref)

    async def update_profile(self, user: User, payload: UpdateProfileRequest) -> MeResponse:
        if payload.username is not None:
            username = payload.username.strip()
            if await self.users.username_exists(username, exclude_id=user.id):
                raise UsernameExistsError
            user.username = username
        if payload.avatar_url is not None:
            user.avatar_url = payload.avatar_url or None
        await self.session.flush()

        pref = await self.prefs.get_or_create(user.id)
        return self._to_me(user, pref)

    async def change_password(
        self, user: User, payload: ChangePasswordRequest, current_token: TokenPayload | None = None
    ) -> None:
        if not verify_password(payload.old_password, user.password_hash):
            raise WrongOldPasswordError
        validate_password_strength(payload.new_password)

        user.password_hash = hash_password(payload.new_password)
        await self.session.flush()
        # 改密后所有 refresh token 立即作废（其他设备拿不到新 access token）
        await self._revoke_all_refresh(user.id)
        # 当前设备的 access token 也加入黑名单（强制立即重新登录）
        if current_token is not None:
            ttl = current_token.ttl_seconds
            if ttl > 0:
                await self.redis.setex(RedisKey.token_blacklist(current_token.jti), ttl, "1")
        log.info("auth.password_changed", user_id=user.id)

    async def update_preference(
        self, user: User, payload: UpdatePreferenceRequest
    ) -> PreferenceResponse:
        pref = await self.prefs.get_or_create(user.id)
        if payload.default_scope is not None:
            pref.default_scope = payload.default_scope.value
        if payload.followed_categories is not None:
            pref.followed_categories = _dedupe_str(payload.followed_categories)
        if payload.followed_tags is not None:
            pref.followed_tags = _dedupe_int(payload.followed_tags)
        if payload.muted_sources is not None:
            pref.muted_sources = _dedupe_int(payload.muted_sources)
        if payload.daily_report_opt_in is not None:
            pref.daily_report_opt_in = payload.daily_report_opt_in
        await self.session.flush()
        return PreferenceResponse.model_validate(pref)

    @staticmethod
    def _to_me(user: User, pref: UserPreference) -> MeResponse:
        return MeResponse(
            user_id=user.id,
            email=user.email,
            username=user.username,
            avatar_url=user.avatar_url,
            role=Role(user.role),
            last_login_at=user.last_login_at,
            preference=PreferenceResponse.model_validate(pref),
        )


class AdminUserService:
    """用户管理（仅 ADMIN）。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def list_users(
        self,
        *,
        keyword: str | None,
        role: Role | None,
        status: UserStatus | None,
        sort: str,
        page: int,
        size: int,
    ) -> Page[AdminUserItem]:
        descending = sort.startswith("-")
        field = sort.lstrip("-")
        if field not in SORT_FIELDS:
            raise InvalidSortFieldError(f"不支持的排序字段：{field}")

        rows, total = await self.users.search(
            keyword=keyword,
            role=role,
            status=status,
            sort_field=field,
            descending=descending,
            offset=(page - 1) * size,
            limit=size,
        )
        items = [
            AdminUserItem(
                user_id=u.id,
                email=u.email,
                username=u.username,
                avatar_url=u.avatar_url,
                role=Role(u.role),
                status=UserStatus(u.status),
                last_login_at=u.last_login_at,
                created_at=u.created_at,
            )
            for u in rows
        ]
        return Page.create(items, total, page, size)

    async def update_user(
        self, *, target_id: int, payload: AdminUpdateUserRequest, operator: User
    ) -> AdminUserItem:
        if target_id == operator.id:
            raise CannotModifySelfRoleError

        user = await self.users.get_by_id(target_id)
        if user is None:
            raise UserNotFoundError

        will_lose_admin = user.role == Role.ADMIN.value and (
            (payload.role is not None and payload.role != Role.ADMIN)
            or payload.status == UserStatus.DISABLED
        )
        if will_lose_admin and await self.users.count_active_admins(exclude_id=user.id) == 0:
            raise LastAdminProtectedError

        if payload.role is not None:
            user.role = payload.role.value
        if payload.status is not None:
            user.status = payload.status.value
        await self.session.flush()

        log.info(
            "auth.admin_update_user",
            operator_id=operator.id,
            target_id=user.id,
            role=user.role,
            status=user.status,
        )
        # TODO(admin 模块): AuditService.record("USER_ROLE_CHANGE", ...)
        return AdminUserItem(
            user_id=user.id,
            email=user.email,
            username=user.username,
            avatar_url=user.avatar_url,
            role=Role(user.role),
            status=UserStatus(user.status),
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )


def _dedupe_str(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _dedupe_int(values: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out

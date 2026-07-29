"""auth 模块数据访问层。只有这一层能碰 ORM Session。

全局约定：所有查询默认带 is_deleted = false；删除一律软删除。
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import Role, UserStatus
from app.modules.auth.model import User, UserPreference

# 列表排序白名单（见 doc/SPEC-auth.md GET /admin/users）
SORT_FIELDS: dict[str, Any] = {
    "createdAt": User.created_at,
    "lastLoginAt": User.last_login_at,
    "username": User.username,
    "email": User.email,
}


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self) -> Select[tuple[User]]:
        return select(User).where(User.is_deleted.is_(False))

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(self._base().where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(self._base().where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(self._base().where(User.username == username))
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(
                User.is_deleted.is_(False), User.email == email.lower()
            )
        )
        return (result.scalar_one() or 0) > 0

    async def username_exists(self, username: str, *, exclude_id: int | None = None) -> bool:
        stmt = select(func.count()).select_from(User).where(
            User.is_deleted.is_(False), User.username == username
        )
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        result = await self.session.execute(stmt)
        return (result.scalar_one() or 0) > 0

    async def create(
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
        role: Role = Role.USER,
    ) -> User:
        user = User(
            email=email.lower(),
            username=username,
            password_hash=password_hash,
            role=role.value,
            status=UserStatus.ACTIVE.value,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def touch_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        await self.session.flush()

    async def count_active_admins(self, *, exclude_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(User).where(
            User.is_deleted.is_(False),
            User.role == Role.ADMIN.value,
            User.status == UserStatus.ACTIVE.value,
        )
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def search(
        self,
        *,
        keyword: str | None,
        role: Role | None,
        status: UserStatus | None,
        sort_field: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        stmt = self._base()
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(User.email.ilike(like), User.username.ilike(like)))
        if role is not None:
            stmt = stmt.where(User.role == role.value)
        if status is not None:
            stmt = stmt.where(User.status == status.value)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        column = SORT_FIELDS[sort_field]
        order = column.desc() if descending else column.asc()
        # 稳定 tiebreaker，避免翻页重复/漏项
        stmt = stmt.order_by(order, User.id.desc()).offset(offset).limit(limit)

        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total


class UserPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: int) -> UserPreference | None:
        result = await self.session.execute(
            select(UserPreference).where(
                UserPreference.is_deleted.is_(False), UserPreference.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create_default(self, user_id: int) -> UserPreference:
        pref = UserPreference(
            user_id=user_id,
            followed_categories=[],
            followed_tags=[],
            muted_sources=[],
            daily_report_opt_in=False,
        )
        self.session.add(pref)
        await self.session.flush()
        return pref

    async def get_or_create(self, user_id: int) -> UserPreference:
        return await self.get_by_user_id(user_id) or await self.create_default(user_id)

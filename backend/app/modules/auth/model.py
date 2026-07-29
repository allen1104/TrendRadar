"""auth 模块 ORM 模型：user / user_preference。

字段定义见 doc/SPEC-auth.md「数据库设计」。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.modules.auth.enums import DefaultScope, Role, UserStatus

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class User(Base, TimestampMixin):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{Role.USER.value}'")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{UserStatus.ACTIVE.value}'")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    preference: Mapped["UserPreference"] = relationship(
        back_populates="user", uselist=False, lazy="selectin"
    )

    __table_args__ = (
        # 软删除下的唯一性：只对未删除记录生效
        Index(
            "uk_user_email",
            "email",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "uk_user_username",
            "username",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_user_role_status", "role", "status"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


class UserPreference(Base, TimestampMixin):
    __tablename__ = "user_preference"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    default_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{DefaultScope.TODAY.value}'")
    )
    followed_categories: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    followed_tags: Mapped[list[int]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    muted_sources: Mapped[list[int]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    daily_report_opt_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    user: Mapped[User] = relationship(back_populates="preference")

    __table_args__ = (
        Index(
            "uk_user_pref_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "default_scope": self.default_scope,
            "followed_categories": self.followed_categories,
            "followed_tags": self.followed_tags,
            "muted_sources": self.muted_sources,
            "daily_report_opt_in": self.daily_report_opt_in,
        }

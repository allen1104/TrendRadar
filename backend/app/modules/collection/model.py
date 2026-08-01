"""collection ORM 模型。

字段全量按 doc/SPEC-collection.md §数据库设计。
两张表都继承 Base, TimestampMixin（自带 id / created_at / updated_at / is_deleted）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.collection.enums import ReadStatus

_JSONB = JSONB().with_variant(JSON(), "sqlite")


# ----------------------------------------------------------------- 收藏夹


class CollectionFolder(Base, TimestampMixin):
    """用户收藏夹。"""

    __tablename__ = "collection_folder"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        Index(
            "uk_folder_user_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_folder_user", "user_id", "sort_order"),
    )


# ----------------------------------------------------------------- 条目


class CollectionItem(Base, TimestampMixin):
    """收藏条目。"""

    __tablename__ = "collection_item"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    folder_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("collection_folder.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event.id", ondelete="RESTRICT"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_tags: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    read_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{ReadStatus.UNREAD.value}'")
    )
    read_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "uk_item_user_event",
            "user_id",
            "event_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_item_folder", "folder_id", "created_at"),
        Index("idx_item_read_status", "user_id", "read_status"),
        # GIN 索引写在迁移里（SQLAlchemy 不直接支持 GIN DSL 表达）
    )
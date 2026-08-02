"""creation ORM 模型。字段定义见 doc/SPEC-creation.md「数据库设计」。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.creation.enums import DraftStatus

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class CreationDraft(Base, TimestampMixin):
    """用户对某事件生成的内容草稿。一对一绑定 (user, event, platform, style)。"""

    __tablename__ = "creation_draft"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, server_default=text("''"))
    # content：AI 原始输出，**永不被用户编辑覆盖**
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    # content_edited：用户编辑后的正文；为空表示未编辑
    content_edited: Mapped[str | None] = mapped_column(Text, nullable=True)
    outline: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    cover_suggestion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags_suggestion: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # extra_params：生成参数（targetWords / audience / extraRequirement）
    extra_params: Mapped[dict[str, Any]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'{}'")
    )
    model_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 6), nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{DraftStatus.GENERATING.value}'")
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    regenerate_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index("idx_draft_user_time", "user_id", "created_at"),
        Index("idx_draft_event", "event_id"),
        Index("idx_draft_user_platform", "user_id", "platform"),
    )
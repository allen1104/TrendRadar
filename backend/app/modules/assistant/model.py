"""assistant ORM 模型。

字段定义见 doc/SPEC-assistant.md「数据库设计」。
两张表：assistant_thread（会话）+ assistant_message（消息，含 USER / ASSISTANT）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
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
from app.modules.assistant.enums import MessageRole, MessageStatus

_JSONB = JSONB().with_variant(JSON(), "sqlite")


# ----------------------------------------------------------------- 会话


class AssistantThread(Base, TimestampMixin):
    """用户对某事件的问 AI 会话。同一 user × event 可多个 thread（不同话题分开问）。"""

    __tablename__ = "assistant_thread"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, server_default=text("'新对话'"))
    message_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 6), nullable=False, server_default=text("0")
    )
    last_message_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_thread_user_event", "user_id", "event_id", "created_at"),
        Index("idx_thread_user_time", "user_id", "last_message_at"),
    )


# ----------------------------------------------------------------- 消息


class AssistantMessage(Base, TimestampMixin):
    """会话内一条消息：USER 提问 或 ASSISTANT 回复（含 citations + 成本/耗时）。"""

    __tablename__ = "assistant_message"

    thread_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assistant_thread.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{MessageRole.USER.value}'")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    quick_question_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # citations：ASSISTANT 消息才有；格式 [{articleId, title, url, sourceName}, ...]
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    model_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 6), nullable=False, server_default=text("0")
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{MessageStatus.PENDING.value}'")
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("idx_msg_thread", "thread_id", "created_at"),
    )
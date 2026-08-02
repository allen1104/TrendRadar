"""ai-engine ORM 模型：ai_provider / ai_model / prompt_template / ai_call_log / event_analysis。

字段定义见 doc/SPEC-ai-engine.md「数据库设计」。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.modules.ai.enums import (
    CallStatus,
    ModelType,
    ProviderKey,
)

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class AIProvider(Base, TimestampMixin):
    __tablename__ = "ai_provider"

    provider_key: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text(f"'{ProviderKey.OPENAI_COMPATIBLE.value}'")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_config: Mapped[dict[str, Any]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'{}'")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )

    models: Mapped[list["AIModel"]] = relationship(back_populates="provider", lazy="selectin")

    __table_args__ = (
        Index(
            "uk_ai_provider_name",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )


class AIModel(Base, TimestampMixin):
    __tablename__ = "ai_model"

    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ai_provider.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{ModelType.CHAT.value}'")
    )
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("128000"))
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4096"))
    supports_json_schema: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    price_input_per_1m: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False, server_default=text("0")
    )
    price_output_per_1m: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False, server_default=text("0")
    )
    embedding_dim: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )

    provider: Mapped[AIProvider] = relationship(back_populates="models")

    __table_args__ = (
        Index(
            "uk_ai_model_alias",
            "alias",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_ai_model_provider_type", "provider_id", "model_type"),
    )


class PromptTemplate(Base, TimestampMixin):
    __tablename__ = "prompt_template"

    task_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    model_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.3")
    )
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index(
            "uk_prompt_task_version",
            "task_key",
            "version",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        # 同一 task_key 有且仅有一个 is_active
        Index(
            "uk_prompt_task_active",
            "task_key",
            unique=True,
            postgresql_where=text("is_active = true AND is_deleted = false"),
            sqlite_where=text("is_active = 1 AND is_deleted = 0"),
        ),
    )


class AICallLog(Base, TimestampMixin):
    __tablename__ = "ai_call_log"

    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model_alias: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, server_default=text("0"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{CallStatus.SUCCESS.value}'")
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        Index("idx_call_log_time", "created_at"),
        Index("idx_call_log_model_time", "model_alias", "created_at"),
        Index("idx_call_log_target", "target_type", "target_id"),
    )


class EventAnalysis(Base, TimestampMixin):
    __tablename__ = "event_analysis"

    event_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    summary_one_line: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    innovations: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    audience: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    categories: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    tags: Mapped[list[dict[str, Any]]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    value_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    originality_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    trend_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    worth_article: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    worth_article_why: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worth_research: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    worth_research_why: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_alias: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # 一个事件一条最新分析
        Index(
            "uk_event_analysis_event",
            "event_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

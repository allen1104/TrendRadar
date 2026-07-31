"""pipeline 模块 ORM 模型。

字段定义见 doc/SPEC-pipeline.md「数据库设计」。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    Float,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.modules.pipeline.enums import ArticleStatus, EventRegion, EventStatus, MatchLevel

_JSONB = JSONB().with_variant(JSON(), "sqlite")


# ---------------------------------------------------------------- 文章


class Article(Base, TimestampMixin):
    """采集到的原始文章。每个采集源一条记录，url_hash 全局唯一。"""

    __tablename__ = "article"

    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    url_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'en'"))
    keywords: Mapped[list[str]] = mapped_column(_JSONB, nullable=False, server_default=text("'[]'"))
    metrics: Mapped[dict[str, Any]] = mapped_column(_JSONB, nullable=False, server_default=text("'{}'"))
    extra: Mapped[dict[str, Any]] = mapped_column(_JSONB, nullable=False, server_default=text("'{}'"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{ArticleStatus.RAW.value}'")
    )
    fail_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # event_id 冗余字段（权威关系在 event_article 表）
    event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("event.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("uk_article_url_hash", "url_hash", unique=True),
        Index("idx_article_status", "status"),
        Index("idx_article_title_hash", "title_hash"),
        Index("idx_article_published", "published_at"),
        # GIN trgm 索引（创建迁移时通过 op.execute 建）
        Index("idx_article_event", "event_id"),
    )


class ArticleEmbedding(Base, TimestampMixin):
    """文章向量（pgvector）。一篇一最新向量。"""

    __tablename__ = "article_embedding"

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("article.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    dim: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1024"))
    # 1024 维向量；列在迁移里用 op.execute 创建（pgvector 扩展）。
    # ORM 不建模此列，repository 用原生 SQL 写入。
    __table_args__ = (
        Index("uk_art_emb_article", "article_id", unique=True),
    )


# ---------------------------------------------------------------- 事件


class Event(Base, TimestampMixin):
    """热点事件（聚合单元）。一篇或多篇 article 挂在一个 event 下。"""

    __tablename__ = "event"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary_one_line: Mapped[str | None] = mapped_column(String(300), nullable=True)
    primary_article_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    region: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{EventRegion.GLOBAL.value}'")
    )
    categories: Mapped[list[str]] = mapped_column(_JSONB, nullable=False, server_default=text("'[]'"))
    source_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    article_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    heat_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    value_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    originality_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    trend_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    recommend_index: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{EventStatus.PENDING_AI.value}'")
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_manually_edited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    manual_locked_fields: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )

    __table_args__ = (
        Index("idx_event_status", "status"),
        Index(
            "idx_event_recommend",
            "recommend_index",
            "last_seen_at",
            postgresql_where=text("is_deleted = false AND is_hidden = false"),
        ),
        Index("idx_event_heat", "heat_score"),
        Index("idx_event_last_seen", "last_seen_at"),
    )


class EventArticle(Base, TimestampMixin):
    """事件-文章多对多关联。"""

    __tablename__ = "event_article"

    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("article.id", ondelete="CASCADE"), nullable=False
    )
    match_level: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text(f"'{MatchLevel.FINGERPRINT.value}'")
    )
    similarity: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        Index("uk_event_article", "event_id", "article_id", unique=True),
        Index("idx_ea_article", "article_id"),
    )


# ---------------------------------------------------------------- 标签


class Tag(Base, TimestampMixin):
    """标签字典。"""

    __tablename__ = "tag"

    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 归一化：lowercase
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'OTHER'")
    )
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        Index(
            "uk_tag_name",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_tag_count", "event_count"),
    )


class EventTag(Base, TimestampMixin):
    """事件-标签关联。"""

    __tablename__ = "event_tag"

    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tag.id", ondelete="CASCADE"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, server_default=text("1.0"))

    __table_args__ = (
        Index("uk_event_tag", "event_id", "tag_id", unique=True),
        Index("idx_et_tag", "tag_id"),
    )
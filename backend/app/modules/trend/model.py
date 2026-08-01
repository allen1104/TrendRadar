"""trend ORM 模型。

3 张表：
- event_daily_snapshot：事件每日快照（rank_task 写入）
- keyword_trend：关键词按日统计（aggregate_task 写）
- entity_trend：实体按日统计（aggregate_task 写）

字段全量按 doc/SPEC-trend.md §数据库设计。
所有表继承 Base, TimestampMixin（自带 id / created_at / updated_at / is_deleted）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# ----------------------------------------------------------------- event_daily_snapshot


class EventDailySnapshot(Base, TimestampMixin):
    """事件每日快照，是所有趋势计算的基础事实表。"""

    __tablename__ = "event_daily_snapshot"

    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    stat_date: Mapped[Any] = mapped_column(Date, nullable=False)
    heat_score: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    recommend_index: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    source_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    article_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index(
            "uk_snapshot_event_date",
            "event_id",
            "stat_date",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_snapshot_date", "stat_date"),
    )


# ----------------------------------------------------------------- keyword_trend


class KeywordTrend(Base, TimestampMixin):
    """关键词按日统计。"""

    __tablename__ = "keyword_trend"

    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    stat_date: Mapped[Any] = mapped_column(Date, nullable=False)
    event_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    article_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    heat_sum: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index(
            "uk_kw_trend",
            "keyword",
            "stat_date",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_kw_trend_date", "stat_date", "event_count"),
    )


# ----------------------------------------------------------------- entity_trend


class EntityTrend(Base, TimestampMixin):
    """实体按日统计（公司 / 项目 / 技术 / 人物）。"""

    __tablename__ = "entity_trend"

    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tag.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    stat_date: Mapped[Any] = mapped_column(Date, nullable=False)
    event_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    heat_sum: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    avg_value_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    __table_args__ = (
        Index(
            "uk_entity_trend",
            "tag_id",
            "stat_date",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_entity_trend_type_date", "entity_type", "stat_date", "event_count"),
    )

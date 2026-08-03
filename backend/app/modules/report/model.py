"""report ORM 模型。
字段定义见 doc/SPEC-report.md「数据库设计」。
三张表：report（日报）/ report_item（条目）/ report_subscription（订阅）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.report.enums import (
    ReportStatus,
    SubscriptionChannel,
)

_JSONB = JSONB().with_variant(JSON(), "sqlite")


# ============================================================ report


class Report(Base, TimestampMixin):
    """一份日报（AI/TECH/GITHUB/AGENT × 日期）。

    唯一约束 (report_type, report_date)：同日同类型唯一。
    """

    __tablename__ = "report"

    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, server_default=text("''"))
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)
    outro: Mapped[str | None] = mapped_column(Text, nullable=True)
    # content_md：AI 生成的完整 Markdown
    content_md: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    # content_edited：EDITOR 编辑后的正文（用于展示与导出）
    content_edited: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text(f"'{ReportStatus.GENERATING.value}'"),
    )
    published_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    model_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 6), nullable=False, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "report_type",
            "report_date",
            name="uk_report_type_date",
        ),
        Index("idx_report_status_date", "status", "report_date"),
    )


# ============================================================ report_item


class ReportItem(Base, TimestampMixin):
    """日报内一条内容。section 字段记板块（如「头条」）。"""

    __tablename__ = "report_item"

    report_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("report.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("event.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    sort_order: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    headline: Mapped[str] = mapped_column(String(300), nullable=False, server_default=text("''"))
    brief: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_top: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    __table_args__ = (
        Index("idx_report_item", "report_id", "section", "sort_order"),
        Index("idx_report_item_event", "event_id"),
    )


# ============================================================ report_subscription


class ReportSubscription(Base, TimestampMixin):
    """用户的日报订阅。一行 = 一个用户的全部订阅设置（含渠道与 RSS 令牌）。"""

    __tablename__ = "report_subscription"

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    report_types: Mapped[list[str]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'[]'")
    )
    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text(f"'{SubscriptionChannel.SITE.value}'"),
    )
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rss_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    __table_args__ = (
        Index("uk_subscription_user", "user_id", unique=True),
        Index("uk_subscription_rss_token", "rss_token", unique=True),
    )

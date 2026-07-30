"""source ORM 模型：source / source_run_log。

字段定义见 doc/SPEC-source.md「数据库设计」。
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.source.enums import RunStatus, SourceCategory, TriggerType

_JSONB = JSONB().with_variant(JSON(), "sqlite")


class Source(Base, TimestampMixin):
    __tablename__ = "source"

    plugin_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'GLOBAL'")
    )
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'NEWS'")
    )
    home_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config: Mapped[dict] = mapped_column(
        _JSONB, nullable=False, server_default=text("'{}'")
    )
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("5")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    consecutive_fails: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index(
            "uk_source_name",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
        Index("idx_source_enabled_cron", "enabled", "cron"),
        Index("idx_source_plugin_key", "plugin_key"),
    )


class SourceRunLog(Base, TimestampMixin):
    __tablename__ = "source_run_log"

    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'SCHEDULED'")
    )
    triggered_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'PENDING'")
    )
    fetched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    new_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_run_log_source_time", "source_id", "started_at"),
    )

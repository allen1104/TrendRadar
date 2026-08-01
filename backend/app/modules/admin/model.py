"""admin 模块 ORM 模型。

3 张表：
- system_config：KV 全局配置
- task_run_log：Celery 任务运行日志
- audit_log：操作审计日志
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
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

_JSONB = JSONB().with_variant(JSON(), "sqlite")


# ----------------------------------------------------------------- system_config


class SystemConfig(Base, TimestampMixin):
    """系统配置（22 项；ADMIN 可改部分）。"""

    __tablename__ = "system_config"

    config_key: Mapped[str] = mapped_column(String(100), nullable=False)
    config_value: Mapped[Any] = mapped_column(_JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'STRING'")
    )
    group_name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    min_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    is_editable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    requires_rerun: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    __table_args__ = (
        Index("uk_config_key", "config_key", unique=True),
        Index("idx_config_group", "group_name"),
    )


# ----------------------------------------------------------------- task_run_log


class TaskRunLog(Base, TimestampMixin):
    """Celery 任务运行日志。保留 30 天，由 cleanup_task 物理删除。"""

    __tablename__ = "task_run_log"

    task_name: Mapped[str] = mapped_column(String(120), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'SCHEDULED'")
    )
    triggered_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    args_summary: Mapped[dict[str, Any]] = mapped_column(
        _JSONB, nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'PENDING'")
    )
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(_JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uk_task_run_task_id", "task_id", unique=True),
        Index("idx_task_run_name_time", "task_name", "started_at"),
        Index("idx_task_run_status", "status"),
    )


# ----------------------------------------------------------------- audit_log


class AuditLog(Base, TimestampMixin):
    """操作审计日志。保留 180 天，只增不改不删。"""

    __tablename__ = "audit_log"

    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    before_value: Mapped[dict[str, Any] | None] = mapped_column(_JSONB, nullable=True)
    after_value: Mapped[dict[str, Any] | None] = mapped_column(_JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("idx_audit_time", "created_at"),
        Index("idx_audit_user", "user_id", "created_at"),
        Index("idx_audit_target", "target_type", "target_id"),
        Index("idx_audit_action", "action"),
    )
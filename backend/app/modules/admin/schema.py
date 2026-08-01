"""admin 模块 DTO。字段名对外一律 camelCase。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.schema import CamelModel
from app.modules.admin.enums import (
    AlertLevel,
    AuditAction,
    ConfigGroup,
    TaskRunStatus,
    TargetType,
    TriggerType,
    ValueType,
)


# ----------------------------------------------------------------- system_config


class ConfigItem(CamelModel):
    id: int
    config_key: str
    config_value: Any
    value_type: ValueType
    group_name: ConfigGroup
    display_name: str
    description: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    is_editable: bool
    requires_rerun: bool
    updated_at: datetime


class ConfigUpdateRequest(CamelModel):
    config_value: Any


# ----------------------------------------------------------------- task_run_log


class TaskRunLogItem(CamelModel):
    id: int
    task_name: str
    task_id: str | None = None
    trigger_type: TriggerType
    triggered_by: int | None = None
    status: TaskRunStatus
    duration_ms: int | None = None
    retry_count: int
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class TaskRunLogDetail(TaskRunLogItem):
    args_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] | None = None
    traceback: str | None = None


class TaskDefinitionItem(CamelModel):
    task_name: str
    display_name: str
    cron: str | None = None
    enabled: bool = True
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: TaskRunStatus | None = None
    manual_triggerable: bool = True
    is_running: bool = False


class TaskTriggerRequest(CamelModel):
    task_name: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class TaskTriggerResponse(CamelModel):
    task_id: str
    run_log_id: int


# ----------------------------------------------------------------- audit_log


class AuditLogItem(CamelModel):
    id: int
    user_id: int | None = None
    username: str | None = None
    action: AuditAction
    target_type: TargetType
    target_id: int | None = None
    ip: str | None = None
    trace_id: str | None = None
    note: str | None = None
    created_at: datetime


class AuditLogDetail(AuditLogItem):
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    user_agent: str | None = None


# ----------------------------------------------------------------- dashboard


class OverviewCard(CamelModel):
    total_events: int
    total_articles: int
    today_new_events: int
    today_new_articles: int
    active_sources: int
    total_users: int


class PipelineHealth(CamelModel):
    article_by_status: dict[str, int] = Field(default_factory=dict)
    event_by_status: dict[str, int] = Field(default_factory=dict)
    today_failed_articles: int
    pending_clean: int
    pending_embed: int
    pending_ai: int
    avg_source_per_event: float
    dedupe_rate: float


class AiCostCard(CamelModel):
    today_usd: float
    month_usd: float
    daily_limit_usd: float
    limit_reached: bool


class SourceStatusItem(CamelModel):
    id: int
    name: str
    enabled: bool
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    today_count: int
    consecutive_fails: int


class AlertItem(CamelModel):
    id: int
    level: AlertLevel
    message: str
    created_at: datetime


class TrendPoint(CamelModel):
    date: str
    articles: int
    events: int
    ai_cost_usd: float


class DashboardResponse(CamelModel):
    overview: OverviewCard
    pipeline_health: PipelineHealth
    ai_cost: AiCostCard
    source_status: list[SourceStatusItem] = Field(default_factory=list)
    recent_alerts: list[AlertItem] = Field(default_factory=list)
    trend7d: list[TrendPoint] = Field(default_factory=list)


# ----------------------------------------------------------------- health


class HealthCheck(CamelModel):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)
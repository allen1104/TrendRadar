"""source DTO。"""

from datetime import datetime

from pydantic import Field, field_validator

from app.core.schema import CamelModel
from app.modules.source.enums import Region, RunStatus, SourceCategory, TriggerType

# ---------------------------------------------------------------- 请求


class SourceCreateRequest(CamelModel):
    plugin_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    region: Region = Region.GLOBAL
    category: SourceCategory = SourceCategory.NEWS
    home_url: str | None = Field(default=None, max_length=500)
    config: dict = Field(default_factory=dict)
    cron: str = Field(min_length=9, max_length=64)
    weight: int = Field(default=5, ge=1, le=10)
    enabled: bool = False

    @field_validator("cron")
    @classmethod
    def cron_must_have_5_fields(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError("cron 必须是 5 段：分 时 日 月 周")
        return v.strip()


class SourceUpdateRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    region: Region | None = None
    category: SourceCategory | None = None
    home_url: str | None = Field(default=None, max_length=500)
    config: dict | None = None
    cron: str | None = Field(default=None, min_length=9, max_length=64)
    weight: int | None = Field(default=None, ge=1, le=10)
    enabled: bool | None = None


# ---------------------------------------------------------------- 响应


class SourceResponse(CamelModel):
    id: int
    plugin_key: str
    name: str
    region: Region
    category: SourceCategory
    home_url: str | None
    config: dict
    cron: str
    weight: int
    enabled: bool
    last_run_at: datetime | None
    last_run_status: RunStatus | None
    consecutive_fails: int
    next_run_preview: str | None = None  # cron 下一次执行时间（ISO）
    created_at: datetime
    updated_at: datetime


class SourceListItem(CamelModel):
    id: int
    plugin_key: str
    name: str
    region: Region
    category: SourceCategory
    cron: str
    weight: int
    enabled: bool
    last_run_at: datetime | None
    last_run_status: RunStatus | None
    consecutive_fails: int
    today_count: int = 0
    created_at: datetime


class RegisteredPluginInfo(CamelModel):
    plugin_key: str
    display_name: str
    region: Region
    category: SourceCategory
    default_cron: str
    default_weight: int
    config_schema: dict = Field(default_factory=dict)
    implemented: bool  # False = 还是 stub


class SourceTestResponse(CamelModel):
    success: bool
    fetched_count: int = 0
    duration_ms: int = 0
    preview: list[dict] = Field(default_factory=list)  # 前 N 条 RawItem 的 dict 形式
    error_message: str | None = None


class SourceRunResponse(CamelModel):
    task_id: str | None = None  # 异步任务 ID
    run_log_id: int | None = None
    status: str  # "queued" / "running" / ...


class RunLogResponse(CamelModel):
    id: int
    source_id: int
    task_id: str | None
    trigger_type: TriggerType
    status: RunStatus
    fetched_count: int
    new_count: int
    duration_ms: int | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime

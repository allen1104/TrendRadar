"""ai-engine DTO。"""

from datetime import datetime

from pydantic import AliasChoices, Field, field_validator

from app.core.schema import CamelModel
from app.modules.ai.enums import (
    CallStatus,
    ModelType,
    ProviderKey,
    TaskKey,
)

# ---------------------------------------------------------------- Provider


class ProviderCreateRequest(CamelModel):
    provider_key: ProviderKey
    name: str = Field(min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = None
    extra_config: dict = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("名称不能为空")
        return v


class ProviderUpdateRequest(CamelModel):
    name: str | None = Field(default=None, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = None  # 传 null 表示不修改；空字符串表示清空
    extra_config: dict | None = None
    enabled: bool | None = None


class ProviderResponse(CamelModel):
    id: int
    provider_key: ProviderKey
    name: str
    base_url: str | None
    api_key: str | None  # 已脱敏
    extra_config: dict
    enabled: bool
    model_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProviderListItem(CamelModel):
    id: int
    provider_key: ProviderKey
    name: str
    base_url: str | None
    api_key: str | None
    extra_config: dict
    enabled: bool
    model_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProviderTestResponse(CamelModel):
    success: bool
    latency_ms: int | None
    message: str
    available_models: list[str] = Field(default_factory=list)


class RegisteredProviderInfo(CamelModel):
    provider_key: str
    display_name: str
    region: str
    config_schema: dict = Field(default_factory=dict)


# ---------------------------------------------------------------- Model


class ModelCreateRequest(CamelModel):
    provider_id: int
    model_name: str = Field(min_length=1, max_length=120)
    alias: str = Field(min_length=1, max_length=100)
    model_type: ModelType = ModelType.CHAT
    context_window: int = Field(default=128000, ge=1000)
    max_output_tokens: int = Field(default=4096, ge=1)
    supports_json_schema: bool = False
    price_input_per_1m: float = Field(default=0, ge=0)
    price_output_per_1m: float = Field(default=0, ge=0)
    embedding_dim: int | None = Field(default=None, ge=1, le=4096)
    enabled: bool = True


class ModelUpdateRequest(CamelModel):
    model_name: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_json_schema: bool | None = None
    price_input_per_1m: float | None = None
    price_output_per_1m: float | None = None
    embedding_dim: int | None = None
    enabled: bool | None = None


class ModelResponse(CamelModel):
    id: int
    provider_id: int
    provider_name: str
    model_name: str
    alias: str
    model_type: ModelType
    context_window: int
    max_output_tokens: int
    supports_json_schema: bool
    price_input_per_1m: float
    price_output_per_1m: float
    embedding_dim: int | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- Prompt


class PromptCreateRequest(CamelModel):
    task_key: TaskKey
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    model_alias: str | None = None
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=500)


class PromptUpdateRequest(CamelModel):
    system_prompt: str | None = None
    user_prompt: str | None = None
    variables: list[str] | None = None
    model_alias: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    note: str | None = None


class PromptResponse(CamelModel):
    id: int
    task_key: TaskKey
    version: int
    system_prompt: str
    user_prompt: str
    variables: list[str]
    model_alias: str | None
    temperature: float
    max_tokens: int | None
    is_active: bool
    note: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class PromptListItem(CamelModel):
    id: int
    task_key: TaskKey
    version: int
    model_alias: str | None
    temperature: float
    is_active: bool
    note: str | None
    variables: list[str]
    created_at: datetime
    updated_at: datetime


class PromptDryRunRequest(CamelModel):
    target_type: str | None = None  # EVENT / ARTICLE / THREAD / REPORT
    target_id: int | None = None
    variables: dict | None = None  # 直接传入变量的 dry-run（不走 DB）


class PromptDryRunResponse(CamelModel):
    rendered_system_prompt: str
    rendered_user_prompt: str
    output: dict | str
    model_alias: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    parse_success: bool


# ---------------------------------------------------------------- Cost / Log


class CostSeriesPoint(CamelModel):
    key: str
    cost_usd: float
    calls: int
    prompt_tokens: int
    completion_tokens: int


class CostStatsResponse(CamelModel):
    total_cost_usd: float
    total_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    success_rate: float
    series: list[CostSeriesPoint] = Field(default_factory=list)
    by_model: list[CostSeriesPoint] = Field(default_factory=list)
    by_task: list[CostSeriesPoint] = Field(default_factory=list)


class CallLogItem(CamelModel):
    id: int
    trace_id: str
    task_key: str
    model_alias: str
    prompt_version: int | None
    target_type: str | None
    target_id: int | None
    user_id: int | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int | None
    status: CallStatus
    retry_count: int
    error_message: str | None
    created_at: datetime


# ---------------------------------------------------------------- Event Analysis


class EventAnalysisResult(CamelModel):
    """事件 AI 分析的结构化输出（强 schema 约束）。"""

    summary_one_line: str = Field(max_length=300)
    summary: str
    key_points: list[str] = Field(min_length=3, max_length=5)
    innovations: list[str] = Field(max_length=5, default_factory=list)
    audience: list[str]
    categories: list[str] = Field(default_factory=list, max_length=4)
    tags: list[dict] = Field(max_length=8, default_factory=list)
    value_score: int = Field(ge=0, le=100)
    originality_score: int = Field(ge=0, le=100)
    trend_score: int = Field(ge=0, le=100)
    worth_article: bool
    # 模型常把 reason/why 混用或省略；选填，UI 兜底默认文案
    worth_article_why: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("worth_article_why", "worth_article_reason"),
    )
    worth_research: bool
    worth_research_why: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("worth_research_why", "worth_research_reason"),
    )


class EventAnalysisRequest(CamelModel):
    event_id: int
    force: bool = False

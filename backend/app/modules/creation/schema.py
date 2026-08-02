"""creation DTO。字段名对外一律 camelCase（CamelModel 统一处理）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.schema import CamelModel, Page
from app.modules.creation.enums import DraftStatus, ExportFormat, Platform, Style

# ----------------------------------------------------------------- 请求


class DraftCreateRequest(CamelModel):
    """POST /creation/drafts."""

    event_id: int
    platform: Platform
    style: Style
    target_words: int | None = Field(default=None, ge=100, le=20000)
    audience: str | None = Field(default=None, max_length=200)
    extra_requirement: str | None = Field(default=None, max_length=500)


class DraftRegenerateRequest(CamelModel):
    """POST /creation/drafts/{id}/regenerate（可换风格/参数）。"""

    style: Style | None = None
    target_words: int | None = Field(default=None, ge=100, le=20000)
    audience: str | None = Field(default=None, max_length=200)
    extra_requirement: str | None = Field(default=None, max_length=500)


class DraftUpdateRequest(CamelModel):
    """PATCH /creation/drafts/{id}（保存编辑）。"""

    title: str | None = Field(default=None, max_length=300)
    content_edited: str | None = Field(default=None, max_length=100_000)


# ----------------------------------------------------------------- 响应


class OutlineItem(CamelModel):
    heading: str
    points: list[str] = Field(default_factory=list)


class PlatformOption(CamelModel):
    key: Platform
    name: str
    icon: str
    target_words: list[int]  # [min, max]
    description: str


class StyleOption(CamelModel):
    key: Style
    name: str
    description: str


class OptionsResponse(CamelModel):
    platforms: list[PlatformOption]
    styles: list[StyleOption]


class DraftSummary(CamelModel):
    """草稿列表项（轻量；不含 content 正文）。"""

    id: int
    event_id: int
    event_title: str | None = None
    platform: Platform
    style: Style
    title: str
    word_count: int
    is_edited: bool
    status: DraftStatus
    regenerate_count: int
    cost_usd: float
    created_at: datetime


class DraftDetail(CamelModel):
    """草稿详情（含完整正文）。"""

    id: int
    user_id: int
    event_id: int
    platform: Platform
    style: Style
    title: str
    content: str
    content_edited: str | None = None
    outline: list[OutlineItem] = Field(default_factory=list)
    cover_suggestion: str | None = None
    tags_suggestion: list[str] = Field(default_factory=list)
    word_count: int
    extra_params: dict[str, Any] = Field(default_factory=dict)
    model_alias: str | None = None
    prompt_version: int | None = None
    cost_usd: float
    status: DraftStatus
    error_message: str | None = None
    regenerate_count: int
    created_at: datetime
    updated_at: datetime


class DraftListResponse(Page[DraftSummary]):
    """分页的草稿列表。"""


# ----------------------------------------------------------------- 流式 SSE 事件


class StreamStartData(CamelModel):
    draft_id: int
    model_alias: str | None = None


class StreamOutlineData(CamelModel):
    outline: list[OutlineItem]


class StreamDeltaData(CamelModel):
    content: str


class StreamDoneData(CamelModel):
    draft_id: int
    title: str
    word_count: int
    cover_suggestion: str | None = None
    tags_suggestion: list[str] = Field(default_factory=list)
    cost_usd: float
    latency_ms: int


class StreamErrorData(CamelModel):
    error_code: str
    detail: str


# ----------------------------------------------------------------- 导出


class ExportResponseMeta(CamelModel):
    """导出接口的元信息（用于响应头）。前端一般用 Content-Disposition 而非 body。"""

    filename: str
    format: ExportFormat
    size_bytes: int
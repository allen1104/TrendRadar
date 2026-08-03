"""report DTO。字段名对外一律 camelCase（CamelModel 统一处理）。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.core.schema import CamelModel, Page
from app.modules.report.enums import (
    ReportStatus,
    ReportType,
    SubscriptionChannel,
)

# ============================================================ 请求


class ReportGenerateRequest(CamelModel):
    """POST /admin/reports/generate."""

    report_type: ReportType
    report_date: date
    force: bool = False


class ReportUpdateRequest(CamelModel):
    """PATCH /admin/reports/{id}."""

    title: str | None = Field(default=None, max_length=300)
    intro: str | None = None
    outro: str | None = None
    content_edited: str | None = None


class ReportItemUpdateRequest(CamelModel):
    """PATCH /admin/reports/{id}/items/{itemId}."""

    headline: str | None = Field(default=None, max_length=300)
    brief: str | None = None
    comment: str | None = None
    section: str | None = Field(default=None, max_length=64)
    sort_order: int | None = None
    is_top: bool | None = None


class ReportItemAddRequest(CamelModel):
    """POST /admin/reports/{id}/items."""

    event_id: int
    section: str = Field(default="头条", max_length=64)
    headline: str | None = Field(default=None, max_length=300)
    brief: str | None = None


class SubscriptionPutRequest(CamelModel):
    """PUT /reports/subscription."""

    report_types: list[ReportType] = Field(default_factory=list)
    channel: SubscriptionChannel = SubscriptionChannel.SITE
    webhook_url: str | None = Field(default=None, max_length=500)
    enabled: bool = True


# ============================================================ 响应


class ReportItemSummary(CamelModel):
    """日报条目（列表/详情通用）。"""

    id: int
    event_id: int
    section: str
    sort_order: int
    headline: str
    brief: str
    comment: str | None = None
    is_top: bool


class ReportItemEventInfo(CamelModel):
    """日报条目携带的事件简要信息（详情页用）。"""

    id: int
    recommend_index: float
    source_count: int
    categories: list[str] = Field(default_factory=list)
    primary_article_url: str | None = None


class ReportItemWithEvent(ReportItemSummary):
    event: ReportItemEventInfo | None = None


class ReportSection(CamelModel):
    name: str
    items: list[ReportItemWithEvent]


class ReportSummary(CamelModel):
    """日报列表项。"""

    id: int
    report_type: ReportType
    report_date: date
    title: str
    intro: str | None = None
    item_count: int
    status: ReportStatus
    published_at: datetime | None = None
    view_count: int


class ReportDetail(CamelModel):
    """日报详情（含 sections + 完整正文）。"""

    id: int
    report_type: ReportType
    report_date: date
    title: str
    intro: str | None = None
    outro: str | None = None
    content_md: str
    content_edited: str | None = None
    item_count: int
    status: ReportStatus
    published_at: datetime | None = None
    view_count: int
    model_alias: str | None = None
    cost_usd: float
    sections: list[ReportSection] = Field(default_factory=list)


class ReportListResponse(Page[ReportSummary]):
    """分页日报列表。"""


class ReportLatestItem(CamelModel):
    """GET /reports/latest 单条。"""

    report_type: ReportType
    id: int
    title: str
    report_date: date
    item_count: int
    published_at: datetime | None = None


class SubscriptionResponse(CamelModel):
    report_types: list[ReportType]
    channel: SubscriptionChannel
    webhook_url: str | None = None
    rss_token: str | None = None
    rss_url: str | None = None
    enabled: bool


class RssTokenResetResponse(CamelModel):
    rss_token: str
    rss_url: str


# ============================================================ 流式 SSE 事件（手动生成 / 重跑）


class StreamStartData(CamelModel):
    report_id: int
    model_alias: str | None = None


class StreamDeltaData(CamelModel):
    content: str


class StreamDoneData(CamelModel):
    report_id: int
    title: str
    item_count: int
    cost_usd: float
    latency_ms: int


class StreamErrorData(CamelModel):
    error_code: str
    detail: str

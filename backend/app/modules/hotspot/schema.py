"""hotspot DTO。字段名对外一律 camelCase（CamelModel 统一处理）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.schema import CamelModel


# ------------------------------------------------------------------ 公共片段


class SourceBrief(CamelModel):
    id: int
    name: str
    home_url: str | None = None
    weight: int | None = None


class TagItem(CamelModel):
    id: int
    display_name: str
    type: str
    weight: float | None = None
    event_count: int | None = None


# ------------------------------------------------------------------ 榜单


class EventListItem(CamelModel):
    id: int
    title: str
    summary_one_line: str | None = None
    region: str
    categories: list[str] = Field(default_factory=list)
    tags: list[TagItem] = Field(default_factory=list)
    source_count: int
    article_count: int
    sources: list[SourceBrief] = Field(default_factory=list)
    heat_score: float
    value_score: int | None = None
    originality_score: int | None = None
    trend_score: int | None = None
    recommend_index: float
    worth_article: bool = False
    primary_article_url: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    status: str
    is_pinned: bool
    is_hidden: bool
    is_manually_edited: bool
    is_collected: bool = False


# ------------------------------------------------------------------ 详情


class EventAnalysisDetail(CamelModel):
    summary_one_line: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    innovations: list[str] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=list)
    value_score: int
    originality_score: int
    trend_score: int
    worth_article: bool
    worth_article_why: str | None = None
    worth_research: bool
    worth_research_why: str | None = None
    model_alias: str
    prompt_version: int
    analyzed_at: datetime


class EventArticleItem(CamelModel):
    id: int
    title: str
    url: str
    author: str | None = None
    lang: str
    published_at: datetime
    summary: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    source: SourceBrief | None = None
    is_primary: bool = False
    match_level: str | None = None
    similarity: float | None = None


class EventDetail(CamelModel):
    id: int
    title: str
    region: str
    categories: list[str] = Field(default_factory=list)
    tags: list[TagItem] = Field(default_factory=list)
    source_count: int
    article_count: int
    heat_score: float
    recommend_index: float
    value_score: int | None = None
    originality_score: int | None = None
    trend_score: int | None = None
    status: str
    is_pinned: bool
    is_hidden: bool
    is_manually_edited: bool
    manual_locked_fields: list[str] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime
    analysis: EventAnalysisDetail | None = None
    articles: list[EventArticleItem] = Field(default_factory=list)
    is_collected: bool = False


# ------------------------------------------------------------------ 趋势 / 相关


class EventTrendPoint(CamelModel):
    date: str
    heat_score: float
    source_count: int
    article_count: int


class EventTrendResponse(CamelModel):
    event_id: int
    points: list[EventTrendPoint] = Field(default_factory=list)


class RelatedEventItem(CamelModel):
    id: int
    title: str
    summary_one_line: str | None = None
    recommend_index: float
    last_seen_at: datetime
    similarity: float | None = None


# ------------------------------------------------------------------ 运营


class EventUpdateRequest(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    summary_one_line: str | None = Field(default=None, max_length=300)
    categories: list[str] | None = None
    is_pinned: bool | None = None
    is_hidden: bool | None = None

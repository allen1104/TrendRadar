"""pipeline DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.schema import CamelModel


class PipelineRerunRequest(CamelModel):
    stage: str = Field(description="CLEAN / EMBED / DEDUPE / RANK")
    scope: str = Field(description="ARTICLE / EVENT / SOURCE / ALL")
    ids: list[int] | None = None
    since: datetime | None = None


class PipelineRerunResponse(CamelModel):
    task_id: str | None = None
    queued_count: int = 0


class PipelineStats(CamelModel):
    article_by_status: dict[str, int]
    event_by_status: dict[str, int]
    today_new_articles: int
    today_new_events: int
    avg_source_per_event: float
    dedupe_rate: float
    match_level_distribution: dict[str, int]


class EventSplitRequest(CamelModel):
    article_ids: list[int] = Field(min_length=1)
    new_event_title: str = Field(min_length=1, max_length=500)


class EventMergeRequest(CamelModel):
    source_id: int
    target_id: int


class SplitResult(CamelModel):
    source_event: dict[str, Any]
    new_event: dict[str, Any]
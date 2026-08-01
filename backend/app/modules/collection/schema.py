"""collection DTO。字段名对外一律 camelCase（CamelModel 统一处理）。"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field, field_validator

from app.core.schema import CamelModel
from app.modules.collection.enums import ReadStatus

_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# ----------------------------------------------------------------- 收藏夹


class FolderCreateRequest(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = None  # hex 颜色，#fff 或 #ffffff

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name 不能为空白")
        return v

    @field_validator("color")
    @classmethod
    def _validate_color(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _HEX_COLOR_RE.match(v):
            raise ValueError("color 必须是 hex 格式（#fff 或 #ffffff）")
        return v


class FolderUpdateRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = None
    sort_order: int | None = None

    @field_validator("color")
    @classmethod
    def _validate_color(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _HEX_COLOR_RE.match(v):
            raise ValueError("color 必须是 hex 格式")
        return v


class FolderResponse(CamelModel):
    id: int
    name: str
    description: str | None = None
    color: str | None = None
    sort_order: int
    is_default: bool
    item_count: int
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------- 条目（嵌套 event 简要）


class EventBrief(CamelModel):
    """条目列表里嵌入的事件简要（避免前端二次请求）。"""

    id: int
    title: str
    summary_one_line: str | None = None
    categories: list[str] = Field(default_factory=list)
    recommend_index: float
    source_count: int
    last_seen_at: datetime | None = None


class ItemCreateRequest(CamelModel):
    event_id: int
    folder_id: int | None = None  # None → 默认收藏夹
    note: str | None = Field(default=None, max_length=20000)
    user_tags: list[str] = Field(default_factory=list)
    read_status: ReadStatus = ReadStatus.UNREAD

    @field_validator("user_tags")
    @classmethod
    def _clean_tags(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for t in v:
            t = (t or "").strip()
            if not t or len(t) > 20 or t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out[:10]


class ItemUpdateRequest(CamelModel):
    folder_id: int | None = None
    note: str | None = Field(default=None, max_length=20000)
    user_tags: list[str] | None = None
    read_status: ReadStatus | None = None

    @field_validator("user_tags")
    @classmethod
    def _clean_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        seen: set[str] = set()
        for t in v:
            t = (t or "").strip()
            if not t or len(t) > 20 or t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out[:10]


class ItemResponse(CamelModel):
    id: int
    folder_id: int
    folder_name: str
    note: str | None = None
    user_tags: list[str] = Field(default_factory=list)
    read_status: ReadStatus
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    event: EventBrief


# ----------------------------------------------------------------- 批量


class BatchItemRequest(CamelModel):
    item_ids: list[int] = Field(min_length=1, max_length=200)
    action: str  # MOVE / DELETE / MARK_READ / ADD_TAG / REMOVE_TAG
    target_folder_id: int | None = None
    tag: str | None = None

    @field_validator("action")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        if v not in {"MOVE", "DELETE", "MARK_READ", "ADD_TAG", "REMOVE_TAG"}:
            raise ValueError(
                "action 必须是 MOVE / DELETE / MARK_READ / ADD_TAG / REMOVE_TAG 之一"
            )
        return v


class BatchItemResponse(CamelModel):
    affected_count: int


# ----------------------------------------------------------------- 统计


class CategoryCount(CamelModel):
    category: str
    count: int


class MonthCount(CamelModel):
    month: str  # YYYY-MM
    count: int


class StatsResponse(CamelModel):
    total_items: int
    unread_count: int
    later_count: int
    read_count: int
    folder_count: int
    by_category: list[CategoryCount] = Field(default_factory=list)
    recent_months: list[MonthCount] = Field(default_factory=list)


# ----------------------------------------------------------------- hotspot 集成


class CollectedEventIdsResponse(CamelModel):
    """hotspot 内部用：返回当前用户已收藏的 event_id 集合。"""

    event_ids: list[int]

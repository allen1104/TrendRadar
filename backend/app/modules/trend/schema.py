"""trend DTO。字段名对外一律 camelCase（CamelModel 统一处理）。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.core.schema import CamelModel

# ----------------------------------------------------------------- 关键词趋势


class KeywordPoint(CamelModel):
    """单个关键词在某天的指标。"""

    date: date
    event_count: int
    article_count: int | None = None
    heat_sum: float | None = None


class KeywordTrendItem(CamelModel):
    """关键词趋势排行榜一项。"""

    keyword: str
    display_name: str
    current: int
    previous: int
    growth_rate: float  # 相对增长率（截断到 5.0）
    growth_abs: int
    growth_score: float
    heat_sum: float
    is_new: bool
    series: list[KeywordPoint] = Field(default_factory=list)


class KeywordTrendResponse(CamelModel):
    """关键词趋势排行榜。"""

    window: str
    metric: str
    items: list[KeywordTrendItem] = Field(default_factory=list)
    newcomers: list[KeywordTrendItem] = Field(default_factory=list)


# ----------------------------------------------------------------- 实体趋势


class EntityTrendItem(CamelModel):
    """实体趋势排行榜一项。"""

    tag_id: int
    display_name: str
    entity_type: str
    current: int
    previous: int
    growth_rate: float
    growth_abs: int
    growth_score: float
    heat_sum: float
    avg_value_score: float | None = None
    series: list[KeywordPoint] = Field(default_factory=list)


class EntityTrendResponse(CamelModel):
    """实体趋势排行榜。"""

    window: str
    entity_type: str
    items: list[EntityTrendItem] = Field(default_factory=list)


# ----------------------------------------------------------------- 词云


class WordCloudItem(CamelModel):
    """词云一项。"""

    text: str
    value: float  # 归一化到 0-100
    type: str  # TECH / COMPANY / PRODUCT / PERSON / KEYWORD
    growth_rate: float | None = None
    tag_id: int | None = None


class WordCloudResponse(CamelModel):
    """词云数据。"""

    window: str
    items: list[WordCloudItem] = Field(default_factory=list)


# ----------------------------------------------------------------- 总览


class TrendSummary(CamelModel):
    """总览聚合指标。"""

    total_events: int
    total_articles: int
    avg_events_per_day: float
    event_growth_rate: float


class DailySeriesPoint(CamelModel):
    """每日趋势点。"""

    date: date
    event_count: int
    article_count: int
    avg_recommend: float | None = None


class CategoryDistribution(CamelModel):
    """分类分布项。"""

    category: str
    count: int
    growth_rate: float


class RegionDistribution(CamelModel):
    """区域分布项。"""

    region: str
    count: int


class RisingItem(CamelModel):
    """上升最快项（关键词/公司/项目）。"""

    display_name: str
    growth_rate: float
    current: int | None = None


class OverviewResponse(CamelModel):
    """总览响应。"""

    window: str
    summary: TrendSummary
    daily_series: list[DailySeriesPoint] = Field(default_factory=list)
    category_distribution: list[CategoryDistribution] = Field(default_factory=list)
    region_distribution: list[RegionDistribution] = Field(default_factory=list)
    top_rising_keywords: list[RisingItem] = Field(default_factory=list)
    top_companies: list[RisingItem] = Field(default_factory=list)
    top_projects: list[RisingItem] = Field(default_factory=list)


# ----------------------------------------------------------------- 关键词下钻


class RelatedKeyword(CamelModel):
    """共现关键词。"""

    display_name: str
    co_occurrence: int


class RelatedEvent(CamelModel):
    """相关事件。"""

    id: int
    title: str
    recommend_index: float
    last_seen_at: datetime | None = None


class TrendPoint(CamelModel):
    """单点（用于下钻/对比的曲线）。"""

    date: date
    event_count: int
    article_count: int | None = None
    heat_sum: float | None = None


class KeywordDetailResponse(CamelModel):
    """关键词下钻响应。"""

    keyword: str
    display_name: str
    window: str
    series: list[TrendPoint] = Field(default_factory=list)
    growth_rate: float
    related_keywords: list[RelatedKeyword] = Field(default_factory=list)
    top_events: list[RelatedEvent] = Field(default_factory=list)

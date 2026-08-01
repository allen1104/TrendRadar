"""trend 业务逻辑。

聚合任务：aggregate_task 每日 02:00 计算前一天 keyword_trend / entity_trend。
查询接口：关键词趋势 / 实体趋势 / 词云 / 总览 / 关键词下钻。
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trend.enums import EntityType, TrendMetric, TrendWindow
from app.modules.trend.exceptions import (
    EntityTypeInvalidError,
    TrendLimitOutOfRangeError,
    TrendMetricInvalidError,
    TrendWindowInvalidError,
)
from app.modules.trend.model import EntityTrend, KeywordTrend
from app.modules.trend.repository import (
    EntityTrendRepository,
    KeywordTrendRepository,
)
from app.modules.trend.schema import (
    CategoryDistribution,
    DailySeriesPoint,
    EntityTrendItem,
    EntityTrendResponse,
    KeywordDetailResponse,
    KeywordPoint,
    KeywordTrendItem,
    KeywordTrendResponse,
    OverviewResponse,
    RegionDistribution,
    RelatedEvent,
    RelatedKeyword,
    RisingItem,
    TrendPoint,
    TrendSummary,
    WordCloudItem,
    WordCloudResponse,
)

# ============================================================ 窗口换算

_WINDOW_DAYS: dict[TrendWindow, int] = {
    TrendWindow.D7: 7,
    TrendWindow.D30: 30,
    TrendWindow.Y1: 365,
}

# 增长率上限截断（SPEC §噪声抑制）
GROWTH_RATE_CAP = 5.0

# 最小入榜事件数（SPEC §噪声抑制，可后台配置）
DEFAULT_MIN_EVENT_COUNT = 3


def window_to_days(window: TrendWindow | str) -> int:
    """window → 天数。"""
    if isinstance(window, str):
        try:
            window = TrendWindow(window)
        except ValueError as e:
            raise TrendWindowInvalidError(
                "window 必须是 7D/30D/1Y 之一", extra={"window": window}
            ) from e
    if window not in _WINDOW_DAYS:
        raise TrendWindowInvalidError(
            "window 必须是 7D/30D/1Y 之一", extra={"window": window.value}
        )
    return _WINDOW_DAYS[window]


def window_to_dates(
    window: TrendWindow | str, *, today: date | None = None
) -> tuple[date, date, date]:
    """返回 (current_start, current_end, previous_start)。

    current_end = today；current_start = today - window+1。
    previous_end = current_start - 1；previous_start = previous_end - window + 1。
    """
    d = window_to_days(window)
    end = today or datetime.now(UTC).date()
    start = end - timedelta(days=d - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=d - 1)
    return start, end, prev_start


# ============================================================ 关键词归一化


_KEYWORD_NORMALIZE_RE = re.compile(r"[\s_\-]+")

# 停用词（SPEC §噪声抑制，可后台配置覆盖）
DEFAULT_STOPWORDS = {"ai", "技术", "模型", "the", "a", "an"}


def normalize_keyword(s: str) -> str:
    """统一小写、去首尾空白、连字符/下划线/空格归一为 '-'。

    'gpt-5' / 'gpt_5' / 'GPT 5' / 'gpt - 5' → 'gpt-5'
    """
    s = (s or "").strip().lower()
    s = _KEYWORD_NORMALIZE_RE.sub("-", s)
    return s.strip("-")


def is_stopword(keyword: str, stopwords: set[str] | None = None) -> bool:
    """单字符 / 停用词过滤。"""
    k = keyword.strip()
    if len(k) <= 1:
        return True
    sw = stopwords if stopwords is not None else DEFAULT_STOPWORDS
    return k in sw


# ============================================================ 增长率算法


def _smooth(series: list[float], window: int = 3) -> list[float]:
    """3 日移动平均（边界以外照常算，序列长度 < window 时返回原序列）。"""
    n = len(series)
    if n == 0:
        return []
    if n < window:
        return list(series)
    out: list[float] = [0.0] * n
    for i in range(n):
        if i < window - 1:
            out[i] = sum(series[: i + 1]) / (i + 1)
        else:
            out[i] = sum(series[i - window + 1 : i + 1]) / window
    return out


def growth_score(current: int, previous: int) -> tuple[float, int, float]:
    """计算 (growth_rate, growth_abs, growth_score)。

    SPEC §增长率算法：
      growth_rate = (current - previous) / max(previous, 1)  # 截断到 5.0
      growth_abs  = current - previous
      growth_score = log10(1 + current) × min(growth_rate, 5.0)
    """
    if previous < 0:
        previous = 0
    if current < 0:
        current = 0
    raw_rate = (current - previous) / max(previous, 1)
    rate = min(raw_rate, GROWTH_RATE_CAP)
    abs_growth = current - previous
    score = math.log10(1 + current) * min(rate, GROWTH_RATE_CAP)
    return round(rate, 4), abs_growth, round(score, 4)


def is_new_keyword(current: int, previous: int) -> bool:
    """emerging 标记：previous == 0 且 current >= 3。"""
    return previous == 0 and current >= 3


# ============================================================ TrendService


class TrendService:
    """趋势分析业务编排。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.kw_repo = KeywordTrendRepository(session)
        self.ent_repo = EntityTrendRepository(session)

    # ============================================================ 聚合任务

    async def aggregate_keyword(self, stat_date: date) -> int:
        """聚合某一日期的关键词统计。

        步骤：
        1. 找到当天 ANALYZED 的 event
        2. 累计每个 event 的 keywords + heat_score，分配到 keyword
        3. upsert keyword_trend
        """
        from app.modules.pipeline.model import Event

        # 拉当天窗口里 status=ANALYZED 的 event
        # 衰减判定：last_seen_at 在 [stat_date, stat_date+1d)
        start = datetime.combine(stat_date, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)
        stmt = select(Event.id, Event.keywords, Event.heat_score).where(
            Event.status == "ANALYZED",
            Event.is_hidden.is_(False),
            Event.is_deleted.is_(False),
            Event.last_seen_at >= start,
            Event.last_seen_at < end,
        )
        rows = (await self.session.execute(stmt)).all()

        # 聚合：keyword -> {event_count, article_count, heat_sum, display}
        agg: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"event_count": 0, "article_count": 0, "heat_sum": 0.0, "display": ""}
        )
        for _event_id, keywords, heat_score in rows:
            for kw in keywords or []:
                norm = normalize_keyword(kw)
                if not norm or is_stopword(norm):
                    continue
                a = agg[norm]
                a["event_count"] += 1
                a["article_count"] += 1
                a["heat_sum"] += float(heat_score or 0.0)
                if not a["display"]:
                    a["display"] = kw  # 保留展示名（首条）

        # upsert
        rows_written = 0
        for norm, a in agg.items():
            res = await self.kw_repo.upsert(
                keyword=norm,
                display_name=a["display"] or norm,
                stat_date=stat_date,
                event_count=a["event_count"],
                article_count=a["article_count"],
                heat_sum=round(a["heat_sum"], 2),
            )
            rows_written += res
        return rows_written

    async def aggregate_entity(self, stat_date: date) -> int:
        """聚合某一日期的实体统计（按 tag + tag.type 维度）。"""
        from app.modules.ai.model import EventAnalysis
        from app.modules.pipeline.model import Event, event_tag_table
        from app.modules.pipeline.model import tag as tag_table

        start = datetime.combine(stat_date, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)

        # 拉当天活跃 event 的 tag 关联 + tag.type + event.heat_score + event_analysis.value_score
        stmt = (
            select(
                tag_table.c.id,
                tag_table.c.type,
                Event.heat_score,
                EventAnalysis.value_score,
            )
            .select_from(
                event_tag_table.join(tag_table, event_tag_table.c.tag_id == tag_table.c.id)
                .join(Event, Event.id == event_tag_table.c.event_id)
                .outerjoin(
                    EventAnalysis,
                    EventAnalysis.event_id == Event.id,
                )
            )
            .where(
                Event.status == "ANALYZED",
                Event.is_hidden.is_(False),
                Event.is_deleted.is_(False),
                Event.last_seen_at >= start,
                Event.last_seen_at < end,
                tag_table.c.is_deleted.is_(False),
            )
        )
        rows = (await self.session.execute(stmt)).all()

        agg: dict[int, dict[str, Any]] = defaultdict(
            lambda: {"type": "", "event_count": 0, "heat_sum": 0.0, "value_sum": 0.0, "value_n": 0}
        )
        for tag_id, tag_type, heat_score, value_score in rows:
            a = agg[tag_id]
            a["type"] = tag_type
            a["event_count"] += 1
            a["heat_sum"] += float(heat_score or 0.0)
            if value_score is not None:
                a["value_sum"] += float(value_score)
                a["value_n"] += 1

        rows_written = 0
        for tag_id, a in agg.items():
            value_avg = round(a["value_sum"] / a["value_n"], 2) if a["value_n"] > 0 else None
            res = await self.ent_repo.upsert(
                tag_id=tag_id,
                entity_type=a["type"],
                stat_date=stat_date,
                event_count=a["event_count"],
                heat_sum=round(a["heat_sum"], 2),
                avg_value_score=value_avg,
            )
            rows_written += res
        return rows_written

    async def snapshot_event_daily(self, stat_date: date) -> int:
        """写当日 event 快照（供下游 event_daily_snapshot / 详情页 7 日曲线）。"""
        from app.modules.pipeline.model import Event

        # 拉当天 ANALYZED 的 event
        start = datetime.combine(stat_date, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)
        stmt = select(
            Event.id,
            Event.heat_score,
            Event.recommend_index,
            Event.source_count,
            Event.article_count,
        ).where(
            Event.status == "ANALYZED",
            Event.is_deleted.is_(False),
            Event.last_seen_at >= start,
            Event.last_seen_at < end,
        )
        rows = (await self.session.execute(stmt)).all()
        from app.modules.trend.repository import EventDailySnapshotRepository

        repo = EventDailySnapshotRepository(self.session)
        for r in rows:
            await repo.upsert(
                event_id=r.id,
                stat_date=stat_date,
                heat_score=float(r.heat_score or 0.0),
                recommend_index=float(r.recommend_index or 0.0),
                source_count=int(r.source_count or 0),
                article_count=int(r.article_count or 0),
            )
        return len(rows)

    # ============================================================ 关键词趋势

    async def get_keyword_trends(
        self,
        window: TrendWindow | str = TrendWindow.D7,
        metric: TrendMetric | str = TrendMetric.GROWTH,
        limit: int = 20,
        include_new: bool = True,
        min_event_count: int = DEFAULT_MIN_EVENT_COUNT,
    ) -> KeywordTrendResponse:
        window = self._validate_window(window)
        metric = self._validate_metric(metric)
        limit = self._validate_limit(limit)
        start, end, prev_start = window_to_dates(window)

        # 拉当前窗口 + 上一窗口的全部 keyword 行
        cur_rows = list(await self.kw_repo.list_by_window(start, end))
        prev_rows = list(
            await self.kw_repo.list_by_window(
                prev_start, end - timedelta(days=1) if False else start - timedelta(days=1)
            )
        )

        # 聚合：keyword -> {event_count, heat_sum, days_present}
        cur_agg: dict[str, dict[str, Any]] = _aggregate_keyword_rows(cur_rows)
        prev_agg: dict[str, dict[str, Any]] = _aggregate_keyword_rows(prev_rows)

        all_kws = set(cur_agg) | set(prev_agg)
        items: list[KeywordTrendItem] = []
        newcomers: list[KeywordTrendItem] = []
        for kw in all_kws:
            cur = cur_agg.get(kw, {"event_count": 0, "heat_sum": 0.0, "display": kw})
            prv = prev_agg.get(kw, {"event_count": 0, "heat_sum": 0.0})
            if cur["event_count"] < min_event_count and prv["event_count"] == 0:
                continue
            rate, abs_g, score = growth_score(cur["event_count"], prv["event_count"])
            is_new = is_new_keyword(cur["event_count"], prv["event_count"])
            ci = KeywordTrendItem(
                keyword=kw,
                display_name=cur["display"],
                current=cur["event_count"],
                previous=prv["event_count"],
                growth_rate=rate,
                growth_abs=abs_g,
                growth_score=score,
                heat_sum=round(cur["heat_sum"], 2),
                is_new=is_new,
                series=_series_from_rows(cur_rows, kw, start, end),
            )
            if is_new and include_new:
                newcomers.append(ci)
            else:
                items.append(ci)

        # 排序
        if metric == TrendMetric.GROWTH:
            items.sort(key=lambda x: x.growth_score, reverse=True)
            newcomers.sort(key=lambda x: x.current, reverse=True)
        else:  # HOT
            items.sort(key=lambda x: x.heat_sum, reverse=True)

        # 截断
        items = items[:limit]
        newcomers = newcomers[:limit]

        return KeywordTrendResponse(
            window=window.value,
            metric=metric.value,
            items=items,
            newcomers=newcomers,
        )

    # ============================================================ 实体趋势

    async def get_entity_trends(
        self,
        window: TrendWindow | str = TrendWindow.D30,
        entity_type: EntityType | str = EntityType.COMPANY,
        limit: int = 20,
        min_event_count: int = DEFAULT_MIN_EVENT_COUNT,
    ) -> EntityTrendResponse:
        window = self._validate_window(window)
        entity_type = self._validate_entity_type(entity_type)
        limit = self._validate_limit(limit)
        start, end, prev_start = window_to_dates(window)

        ty = None if entity_type == EntityType.ALL else entity_type.value
        cur_rows = [
            r
            for r in (await self.ent_repo.list_by_window(start, end))
            if ty is None or r.entity_type == ty
        ]
        prev_rows = [
            r
            for r in (await self.ent_repo.list_by_window(prev_start, start - timedelta(days=1)))
            if ty is None or r.entity_type == ty
        ]

        cur_agg = _aggregate_entity_rows(cur_rows)
        prev_agg = _aggregate_entity_rows(prev_rows)

        items: list[EntityTrendItem] = []
        for tag_id, cur in cur_agg.items():
            prv = prev_agg.get(
                tag_id,
                {
                    "event_count": 0,
                    "heat_sum": 0.0,
                    "entity_type": cur["entity_type"],
                    "value_sum": 0.0,
                    "value_n": 0,
                },
            )
            if cur["event_count"] < min_event_count and prv["event_count"] == 0:
                continue
            rate, abs_g, score = growth_score(cur["event_count"], prv["event_count"])
            value_avg = round(cur["value_sum"] / cur["value_n"], 2) if cur["value_n"] > 0 else None
            items.append(
                EntityTrendItem(
                    tag_id=tag_id,
                    display_name=cur["display"],
                    entity_type=cur["entity_type"],
                    current=cur["event_count"],
                    previous=prv["event_count"],
                    growth_rate=rate,
                    growth_abs=abs_g,
                    growth_score=score,
                    heat_sum=round(cur["heat_sum"], 2),
                    avg_value_score=value_avg,
                    series=_series_from_rows(cur_rows, tag_id, start, end),
                )
            )

        items.sort(key=lambda x: x.growth_score, reverse=True)
        items = items[:limit]

        return EntityTrendResponse(
            window=window.value,
            entity_type=entity_type.value,
            items=items,
        )

    # ============================================================ 词云

    async def get_wordcloud(
        self,
        window: TrendWindow | str = TrendWindow.D7,
        limit: int = 100,
        type_: str = "ALL",
    ) -> WordCloudResponse:
        window = self._validate_window(window)
        limit = min(max(limit, 1), 300)
        start, end, _ = window_to_dates(window)
        rows = list(await self.kw_repo.list_by_window(start, end))

        items: list[WordCloudItem] = []
        heat_max = max((r.heat_sum for r in rows), default=0.0) or 1.0
        for r in rows:
            items.append(
                WordCloudItem(
                    text=r.display_name,
                    value=round(float(r.heat_sum) / heat_max * 100.0, 2),
                    growth_rate=0.0,
                    type=type_
                    if type_ in {"KEYWORD", "COMPANY", "PRODUCT", "TECH", "PERSON"}
                    else "KEYWORD",
                    tag_id=None,
                )
            )
        items.sort(key=lambda x: x.value, reverse=True)
        return WordCloudResponse(window=window.value, items=items[:limit])

    # ============================================================ 总览

    async def get_overview(self, window: TrendWindow | str = TrendWindow.D7) -> OverviewResponse:
        """趋势总览：4 个指标卡 + 每日时序 + 分类分布 + 区域分布 + Top 列表。"""
        from app.modules.pipeline.model import Event

        window = self._validate_window(window)
        start, end, prev_start = window_to_dates(window)
        start_d = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        end_d = datetime.combine(end, datetime.min.time(), tzinfo=UTC) + timedelta(days=1)
        prev_start_d = datetime.combine(prev_start, datetime.min.time(), tzinfo=UTC)
        prev_end_d = start_d

        # 当前窗口：事件数 / 文章数 / avg_recommend
        cur_stmt = select(
            Event.id,
            Event.last_seen_at,
            Event.recommend_index,
            Event.categories,
            Event.region,
        ).where(
            Event.status == "ANALYZED",
            Event.is_deleted.is_(False),
            Event.last_seen_at >= start_d,
            Event.last_seen_at < end_d,
        )
        cur_rows = (await self.session.execute(cur_stmt)).all()

        # 上一窗口：事件数（计算增长率）
        prev_count = (
            await self.session.execute(
                select(func.count(Event.id)).where(
                    Event.status == "ANALYZED",
                    Event.is_deleted.is_(False),
                    Event.last_seen_at >= prev_start_d,
                    Event.last_seen_at < prev_end_d,
                )
            )
        ).scalar() or 0

        events_total = len(cur_rows)

        # 每日时序
        daily_map: dict[date, dict[str, int]] = defaultdict(
            lambda: {"event_count": 0, "recommend_sum": 0.0}
        )
        for r in cur_rows:
            d = r.last_seen_at.date() if r.last_seen_at else start
            daily_map[d]["event_count"] += 1
            daily_map[d]["recommend_sum"] += float(r.recommend_index or 0.0)
        daily_series: list[DailySeriesPoint] = []
        for d in sorted(daily_map):
            n = daily_map[d]["event_count"]
            avg_r = round(daily_map[d]["recommend_sum"] / n, 2) if n > 0 else 0.0
            daily_series.append(
                DailySeriesPoint(
                    date=d,
                    event_count=n,
                    article_count=n,  # 简化：每日事件数 = 文章数（无更细粒度）
                    avg_recommend=avg_r,
                )
            )

        # 分类分布
        cat_map: dict[str, int] = defaultdict(int)
        for r in cur_rows:
            for c in r.categories or []:
                cat_map[c] += 1
        cat_total = sum(cat_map.values()) or 1
        category_distribution: list[CategoryDistribution] = []
        for c, n in sorted(cat_map.items(), key=lambda x: x[1], reverse=True):
            category_distribution.append(
                CategoryDistribution(
                    category=c,
                    count=n,
                    growth_rate=round(n / cat_total, 4),
                )
            )

        # 区域分布
        region_map: dict[str, int] = defaultdict(int)
        for r in cur_rows:
            region_map[r.region or "GLOBAL"] += 1
        region_distribution = [
            RegionDistribution(region=reg, count=n)
            for reg, n in sorted(region_map.items(), key=lambda x: x[1], reverse=True)
        ]

        # Top 上升关键词 / 公司 / 项目
        top_rising = await self.get_keyword_trends(
            window=window, metric=TrendMetric.GROWTH, limit=5
        )
        top_companies = await self.get_entity_trends(
            window=window, entity_type=EntityType.COMPANY, limit=5
        )
        top_projects = await self.get_entity_trends(
            window=window, entity_type=EntityType.PRODUCT, limit=5
        )

        # event_growth_rate
        growth_rate, _, _ = growth_score(events_total, int(prev_count))

        summary = TrendSummary(
            total_events=events_total,
            total_articles=events_total,  # 简化
            avg_events_per_day=round(events_total / max(len(daily_series), 1), 2),
            event_growth_rate=growth_rate,
        )

        return OverviewResponse(
            window=window.value,
            summary=summary,
            daily_series=daily_series,
            category_distribution=category_distribution[:10],
            region_distribution=region_distribution,
            top_rising_keywords=[
                RisingItem(
                    display_name=it.display_name,
                    growth_rate=it.growth_rate,
                    current=it.current,
                )
                for it in top_rising.items
            ],
            top_companies=[
                RisingItem(
                    display_name=it.display_name,
                    growth_rate=it.growth_rate,
                    current=it.current,
                )
                for it in top_companies.items
            ],
            top_projects=[
                RisingItem(
                    display_name=it.display_name,
                    growth_rate=it.growth_rate,
                    current=it.current,
                )
                for it in top_projects.items
            ],
        )

    # ============================================================ 关键词下钻

    async def get_keyword_detail(
        self, keyword: str, window: TrendWindow | str = TrendWindow.D30
    ) -> KeywordDetailResponse:
        window = self._validate_window(window)
        norm = normalize_keyword(keyword)
        if not norm:
            raise TrendWindowInvalidError("keyword 不能为空", extra={"keyword": keyword})

        start, end, _ = window_to_dates(window)
        rows = [r for r in (await self.kw_repo.list_by_window(start, end)) if r.keyword == norm]
        series = [
            TrendPoint(
                date=r.stat_date,
                event_count=r.event_count,
                article_count=r.article_count,
                heat_sum=float(r.heat_sum),
            )
            for r in sorted(rows, key=lambda x: x.stat_date)
        ]

        # 增长率
        d = window_to_days(window)
        prev_start = start - timedelta(days=d)
        prev_end = start - timedelta(days=1)
        prev_rows = [
            r
            for r in (await self.kw_repo.list_by_window(prev_start, prev_end))
            if r.keyword == norm
        ]
        current_event_count = sum(r.event_count for r in rows)
        previous_event_count = sum(r.event_count for r in prev_rows)
        rate, _, _ = growth_score(current_event_count, previous_event_count)

        # 共现关键词（与本关键词同日出现的其他关键词 Top 10）—— 简化：返回同时段相邻 Top 5
        related_keywords: list[RelatedKeyword] = []
        all_kw_window = await self.kw_repo.list_by_window(start, end)
        co_counter: dict[str, int] = defaultdict(int)
        target_dates = {r.stat_date for r in rows}
        for r in all_kw_window:
            if r.keyword == norm or r.stat_date not in target_dates:
                continue
            co_counter[r.keyword] += r.event_count
        for kw, n in sorted(co_counter.items(), key=lambda x: x[1], reverse=True)[:10]:
            # 找 display_name
            display = next((x.display_name for x in rows if x.keyword == kw), kw)
            related_keywords.append(RelatedKeyword(display_name=display, co_occurrence=n))

        # 相关事件：取 recommend_index 最高的 5 个 event
        from app.modules.pipeline.model import Event

        ev_stmt = (
            select(Event.id, Event.title, Event.recommend_index, Event.last_seen_at)
            .where(
                Event.keywords.contains([norm]),
                Event.status == "ANALYZED",
                Event.is_deleted.is_(False),
            )
            .order_by(Event.recommend_index.desc())
            .limit(5)
        )
        ev_rows = (await self.session.execute(ev_stmt)).all()
        top_events = [
            RelatedEvent(
                id=r.id,
                title=r.title,
                recommend_index=float(r.recommend_index or 0.0),
                last_seen_at=r.last_seen_at,
            )
            for r in ev_rows
        ]

        # display_name
        display_name = rows[0].display_name if rows else norm

        return KeywordDetailResponse(
            keyword=norm,
            display_name=display_name,
            window=window.value,
            series=series,
            growth_rate=rate,
            related_keywords=related_keywords,
            top_events=top_events,
        )

    # ============================================================ 校验

    def _validate_window(self, window: TrendWindow | str) -> TrendWindow:
        if isinstance(window, TrendWindow):
            return window
        try:
            return TrendWindow(window)
        except ValueError as e:
            raise TrendWindowInvalidError(
                "window 必须是 7D/30D/1Y 之一", extra={"window": window}
            ) from e

    def _validate_metric(self, metric: TrendMetric | str) -> TrendMetric:
        if isinstance(metric, TrendMetric):
            return metric
        try:
            return TrendMetric(metric)
        except ValueError as e:
            raise TrendMetricInvalidError(
                "metric 必须是 GROWTH/HOT 之一", extra={"metric": metric}
            ) from e

    def _validate_entity_type(self, entity_type: EntityType | str) -> EntityType:
        if isinstance(entity_type, EntityType):
            return entity_type
        try:
            return EntityType(entity_type)
        except ValueError as e:
            raise EntityTypeInvalidError(
                "entityType 必须是 COMPANY/PRODUCT/TECH/PERSON/ALL 之一",
                extra={"entityType": entity_type},
            ) from e

    def _validate_limit(self, limit: int) -> int:
        if limit < 1 or limit > 300:
            raise TrendLimitOutOfRangeError("limit 必须在 1-300 之间", extra={"limit": limit})
        return limit


# ============================================================ 私有聚合工具


def _aggregate_keyword_rows(rows: list[KeywordTrend]) -> dict[str, dict[str, Any]]:
    """把 keyword_trend 多日行汇总成 keyword → 指标。"""
    out: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"event_count": 0, "heat_sum": 0.0, "display": ""}
    )
    for r in rows:
        o = out[r.keyword]
        o["event_count"] += int(r.event_count or 0)
        o["heat_sum"] += float(r.heat_sum or 0.0)
        if not o["display"]:
            o["display"] = r.display_name
    return out


def _aggregate_entity_rows(rows: list[EntityTrend]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "event_count": 0,
            "heat_sum": 0.0,
            "entity_type": "",
            "display": "",
            "value_sum": 0.0,
            "value_n": 0,
        }
    )
    for r in rows:
        o = out[r.tag_id]
        o["event_count"] += int(r.event_count or 0)
        o["heat_sum"] += float(r.heat_sum or 0.0)
        if not o["entity_type"]:
            o["entity_type"] = r.entity_type
    return out


def _series_from_rows(rows: list[Any], key: Any, start: date, end: date) -> list[KeywordPoint]:
    """按天连续展开单个 keyword/entity 的 series（缺日补 0）。"""
    by_date: dict[date, dict[str, int]] = {}
    for r in rows:
        if getattr(r, "keyword", None) is not None and getattr(r, "keyword", None) != key:
            continue
        if getattr(r, "tag_id", None) is not None and getattr(r, "tag_id", None) != key:
            continue
        by_date[r.stat_date] = {
            "event_count": int(r.event_count or 0),
            "article_count": int(r.article_count or 0) if hasattr(r, "article_count") else None,
            "heat_sum": float(r.heat_sum or 0.0),
        }
    out: list[KeywordPoint] = []
    cur = start
    while cur <= end:
        v = by_date.get(cur, {"event_count": 0, "article_count": None, "heat_sum": 0.0})
        out.append(
            KeywordPoint(
                date=cur,
                event_count=v["event_count"],
                article_count=v["article_count"],
                heat_sum=v["heat_sum"] if v["heat_sum"] else None,
            )
        )
        cur += timedelta(days=1)
    return out

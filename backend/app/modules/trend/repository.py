"""trend 数据访问层。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trend.model import EntityTrend, EventDailySnapshot, KeywordTrend


class EventDailySnapshotRepository:
    """事件每日快照。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(EventDailySnapshot).where(EventDailySnapshot.is_deleted.is_(False))

    async def get(self, event_id: int, stat_date: date) -> EventDailySnapshot | None:
        return (
            await self.session.execute(
                self._base().where(
                    EventDailySnapshot.event_id == event_id,
                    EventDailySnapshot.stat_date == stat_date,
                )
            )
        ).scalar_one_or_none()

    async def list_by_event_in_window(
        self, event_id: int, start: date, end: date
    ) -> Sequence[EventDailySnapshot]:
        """单个事件在某窗口内的快照。"""
        return list(
            (
                await self.session.execute(
                    self._base()
                    .where(
                        EventDailySnapshot.event_id == event_id,
                        EventDailySnapshot.stat_date >= start,
                        EventDailySnapshot.stat_date <= end,
                    )
                    .order_by(EventDailySnapshot.stat_date)
                )
            )
            .scalars()
            .all()
        )

    async def upsert(
        self,
        *,
        event_id: int,
        stat_date: date,
        heat_score: float,
        recommend_index: float,
        source_count: int,
        article_count: int,
    ) -> int:
        """幂等 upsert。重复执行不产生重复数据。

        PG：ON CONFLICT DO UPDATE。SQLite 等测试库：纯 INSERT，依赖前置清理。
        """
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = pg_insert(EventDailySnapshot).values(
                event_id=event_id,
                stat_date=stat_date,
                heat_score=heat_score,
                recommend_index=recommend_index,
                source_count=source_count,
                article_count=article_count,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["event_id", "stat_date"],
                set_={
                    "heat_score": stmt.excluded.heat_score,
                    "recommend_index": stmt.excluded.recommend_index,
                    "source_count": stmt.excluded.source_count,
                    "article_count": stmt.excluded.article_count,
                },
            )
            await self.session.execute(stmt)
            return 1
        else:
            # SQLite：先删后插（每个 (event_id, stat_date) 唯一）
            existing = await self.get(event_id, stat_date)
            if existing is not None:
                existing.heat_score = heat_score
                existing.recommend_index = recommend_index
                existing.source_count = source_count
                existing.article_count = article_count
                await self.session.flush()
                return 1
            snap = EventDailySnapshot(
                event_id=event_id,
                stat_date=stat_date,
                heat_score=heat_score,
                recommend_index=recommend_index,
                source_count=source_count,
                article_count=article_count,
            )
            self.session.add(snap)
            await self.session.flush()
            return 1

    async def bulk_upsert(self, rows: list[dict[str, Any]]) -> int:
        """批量 upsert（来自 rank_task）。"""
        n = 0
        for r in rows:
            await self.upsert(**r)
            n += 1
        return n


class KeywordTrendRepository:
    """关键词按日统计（聚合任务写入）。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(KeywordTrend).where(KeywordTrend.is_deleted.is_(False))

    async def get(self, keyword: str, stat_date: date) -> KeywordTrend | None:
        return (
            await self.session.execute(
                self._base().where(
                    KeywordTrend.keyword == keyword,
                    KeywordTrend.stat_date == stat_date,
                )
            )
        ).scalar_one_or_none()

    async def list_by_window(
        self,
        start: date,
        end: date,
    ) -> Sequence[KeywordTrend]:
        return list(
            (
                await self.session.execute(
                    self._base()
                    .where(
                        KeywordTrend.stat_date >= start,
                        KeywordTrend.stat_date <= end,
                    )
                    .order_by(KeywordTrend.stat_date, KeywordTrend.keyword)
                )
            )
            .scalars()
            .all()
        )

    async def list_all_for_keyword(self, keyword: str, days: int) -> Sequence[KeywordTrend]:
        """单关键词的最近 N 天明细（下钻用）。"""

        cutoff = func.current_date() - days
        return list(
            (
                await self.session.execute(
                    self._base()
                    .where(
                        KeywordTrend.keyword == keyword,
                        KeywordTrend.stat_date >= cutoff,
                    )
                    .order_by(KeywordTrend.stat_date)
                )
            )
            .scalars()
            .all()
        )

    async def upsert(
        self,
        *,
        keyword: str,
        display_name: str,
        stat_date: date,
        event_count: int,
        article_count: int,
        heat_sum: float,
    ) -> int:
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = pg_insert(KeywordTrend).values(
                keyword=keyword,
                display_name=display_name,
                stat_date=stat_date,
                event_count=event_count,
                article_count=article_count,
                heat_sum=heat_sum,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["keyword", "stat_date"],
                set_={
                    "event_count": stmt.excluded.event_count,
                    "article_count": stmt.excluded.article_count,
                    "heat_sum": stmt.excluded.heat_sum,
                },
            )
            await self.session.execute(stmt)
            return 1
        else:
            existing = await self.get(keyword, stat_date)
            if existing is not None:
                existing.event_count = event_count
                existing.article_count = article_count
                existing.heat_sum = heat_sum
                existing.display_name = display_name
                await self.session.flush()
                return 1
            row = KeywordTrend(
                keyword=keyword,
                display_name=display_name,
                stat_date=stat_date,
                event_count=event_count,
                article_count=article_count,
                heat_sum=heat_sum,
            )
            self.session.add(row)
            await self.session.flush()
            return 1

    async def bulk_upsert(self, rows: list[dict[str, Any]]) -> int:
        n = 0
        for r in rows:
            await self.upsert(**r)
            n += 1
        return n


class EntityTrendRepository:
    """实体按日统计。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(EntityTrend).where(EntityTrend.is_deleted.is_(False))

    async def get(self, tag_id: int, stat_date: date) -> EntityTrend | None:
        return (
            await self.session.execute(
                self._base().where(
                    EntityTrend.tag_id == tag_id,
                    EntityTrend.stat_date == stat_date,
                )
            )
        ).scalar_one_or_none()

    async def list_by_window(
        self,
        start: date,
        end: date,
    ) -> Sequence[EntityTrend]:
        return list(
            (
                await self.session.execute(
                    self._base()
                    .where(
                        EntityTrend.stat_date >= start,
                        EntityTrend.stat_date <= end,
                    )
                    .order_by(EntityTrend.stat_date, EntityTrend.tag_id)
                )
            )
            .scalars()
            .all()
        )

    async def upsert(
        self,
        *,
        tag_id: int,
        entity_type: str,
        stat_date: date,
        event_count: int,
        heat_sum: float,
        avg_value_score: float | None,
    ) -> int:
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = pg_insert(EntityTrend).values(
                tag_id=tag_id,
                entity_type=entity_type,
                stat_date=stat_date,
                event_count=event_count,
                heat_sum=heat_sum,
                avg_value_score=avg_value_score,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["tag_id", "stat_date"],
                set_={
                    "event_count": stmt.excluded.event_count,
                    "heat_sum": stmt.excluded.heat_sum,
                    "avg_value_score": stmt.excluded.avg_value_score,
                },
            )
            await self.session.execute(stmt)
            return 1
        else:
            existing = await self.get(tag_id, stat_date)
            if existing is not None:
                existing.event_count = event_count
                existing.heat_sum = heat_sum
                existing.avg_value_score = avg_value_score
                existing.entity_type = entity_type
                await self.session.flush()
                return 1
            row = EntityTrend(
                tag_id=tag_id,
                entity_type=entity_type,
                stat_date=stat_date,
                event_count=event_count,
                heat_sum=heat_sum,
                avg_value_score=avg_value_score,
            )
            self.session.add(row)
            await self.session.flush()
            return 1

    async def bulk_upsert(self, rows: list[dict[str, Any]]) -> int:
        n = 0
        for r in rows:
            await self.upsert(**r)
            n += 1
        return n

    async def list_distinct_tags_in_window(
        self, start: date, end: date, entity_type: str | None = None
    ) -> Sequence[int]:
        """返回窗口内出现过的 tag_id 去重列表（用于下钻 / 共现统计）。"""
        stmt = (
            select(EntityTrend.tag_id)
            .where(
                EntityTrend.stat_date >= start,
                EntityTrend.stat_date <= end,
                EntityTrend.is_deleted.is_(False),
            )
            .group_by(EntityTrend.tag_id)
        )
        if entity_type:
            stmt = stmt.where(EntityTrend.entity_type == entity_type)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

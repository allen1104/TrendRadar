"""source 数据访问层。"""

from datetime import datetime
from typing import Any, Sequence

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.source.model import Source, SourceRunLog

log = structlog.get_logger()


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, source_id: int) -> Source | None:
        return await self.session.get(Source, source_id)

    async def get_by_name(self, name: str) -> Source | None:
        result = await self.session.execute(
            select(Source).where(Source.is_deleted.is_(False), Source.name == name)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        region: str | None = None,
        category: str | None = None,
        enabled_only: bool = False,
        keyword: str | None = None,
    ) -> Sequence[Source]:
        stmt = select(Source).where(Source.is_deleted.is_(False))
        if region:
            stmt = stmt.where(Source.region == region)
        if category:
            stmt = stmt.where(Source.category == category)
        if enabled_only:
            stmt = stmt.where(Source.enabled.is_(True))
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(Source.name.ilike(like))
        stmt = stmt.order_by(Source.id.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, **kwargs: Any) -> Source:
        s = Source(**kwargs)
        self.session.add(s)
        await self.session.flush()
        return s

    async def save(self, source: Source) -> None:
        await self.session.flush()

    async def soft_delete(self, source: Source) -> None:
        source.is_deleted = True
        await self.session.flush()


class SourceRunLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs: Any) -> SourceRunLog:
        row = SourceRunLog(**kwargs)
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(self, run_log_id: int, **fields: Any) -> SourceRunLog | None:
        row = await self.get(run_log_id)
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        await self.session.flush()
        return row

    async def get(self, run_log_id: int) -> SourceRunLog | None:
        return await self.session.get(SourceRunLog, run_log_id)

    async def list(
        self,
        *,
        source_id: int | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[SourceRunLog], int]:
        stmt = select(SourceRunLog).where(SourceRunLog.is_deleted.is_(False))
        if source_id is not None:
            stmt = stmt.where(SourceRunLog.source_id == source_id)
        if status:
            stmt = stmt.where(SourceRunLog.status == status)
        if start_date:
            stmt = stmt.where(SourceRunLog.started_at >= start_date)
        if end_date:
            stmt = stmt.where(SourceRunLog.started_at < end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        rows = (
            (
                await self.session.execute(
                    stmt.order_by(SourceRunLog.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def today_count(self, source_id: int) -> int:
        """返回某个 source 今日成功 + 部分成功的采集数。"""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.coalesce(func.sum(SourceRunLog.new_count), 0)).where(
                SourceRunLog.source_id == source_id,
                SourceRunLog.started_at >= today_start,
                SourceRunLog.status.in_(["SUCCESS", "PARTIAL"]),
                SourceRunLog.is_deleted.is_(False),
            )
        )
        return int(result.scalar_one() or 0)


def preview_next_run(cron_expr: str, *, from_dt: datetime | None = None) -> str | None:
    """cron 表达式 → 下一次执行时间（ISO 8601），用于 UI 预览。

    解析失败（croniter 未装）时返回 None，不影响其他功能。
    """
    try:
        from croniter import croniter  # type: ignore

        base = from_dt or datetime.utcnow()
        nxt = croniter(cron_expr, base).get_next(datetime)
        return nxt.isoformat() + "Z"
    except Exception as exc:  # noqa: BLE001
        log.warning("cron.parse_failed", cron=cron_expr, error=str(exc))
        return None

"""trend Celery 任务。

- aggregate_task：每日 02:00 计算前一天的 keyword_trend / entity_trend / event_daily_snapshot
- cleanup_old_trends：每日 04:00 物理删 400 天前的 trend 数据
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.worker.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="trend.aggregate_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def aggregate_task(self, stat_date: str | None = None) -> dict[str, Any]:
    """聚合前一天的 trend 数据。"""
    from app.db.session import AsyncSessionLocal, engine
    from app.modules.trend.service import TrendService

    async def _run() -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            svc = TrendService(session)
            d = (
                datetime.fromisoformat(stat_date).date()
                if stat_date
                else (datetime.now(UTC).date() - timedelta(days=1))
            )
            kw_n = await svc.aggregate_keyword(d)
            ent_n = await svc.aggregate_entity(d)
            snap_n = await svc.snapshot_event_daily(d)
            await session.commit()
            return {
                "keyword": kw_n,
                "entity": ent_n,
                "snapshot": snap_n,
                "date": d.isoformat(),
            }

    try:
        try:
            return asyncio.run(_run())
        finally:
            # Celery solo 跨多次 asyncio.run 共享连接池，旧 loop 关闭后 asyncpg 连接失效
            asyncio.run(engine.dispose())
    except Exception as e:
        log.exception("trend.aggregate_task failed", error=str(e))
        raise self.retry(exc=e) from e


@celery_app.task(
    name="trend.cleanup_old_trends",
    bind=True,
    max_retries=1,
)
def cleanup_old_trends(self, retention_days: int = 400) -> dict[str, int]:
    """物理删除 retention_days 之前的 trend 数据（按 created_at 切）。"""
    from sqlalchemy import update

    from app.db.session import AsyncSessionLocal, engine
    from app.modules.trend.model import EntityTrend, KeywordTrend

    async def _run() -> dict[str, int]:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with AsyncSessionLocal() as session:
            kw_del = await session.execute(
                update(KeywordTrend)
                .where(
                    KeywordTrend.created_at < cutoff,
                    KeywordTrend.is_deleted.is_(False),
                )
                .values(is_deleted=True)
            )
            ent_del = await session.execute(
                update(EntityTrend)
                .where(
                    EntityTrend.created_at < cutoff,
                    EntityTrend.is_deleted.is_(False),
                )
                .values(is_deleted=True)
            )
            await session.commit()
            return {
                "keyword_marked": int(kw_del.rowcount or 0),  # type: ignore[attr-defined]
                "entity_marked": int(ent_del.rowcount or 0),  # type: ignore[attr-defined]
            }

    try:
        try:
            return asyncio.run(_run())
        finally:
            asyncio.run(engine.dispose())
    except Exception as e:
        log.exception("trend.cleanup_old_trends failed", error=str(e))
        raise self.retry(exc=e) from e
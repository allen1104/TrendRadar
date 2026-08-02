"""creation Celery 任务。

- cleanup_failed_drafts：每日 03:30 软删 status=FAILED 且超过 7 天的 draft。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog

from app.worker.celery_app import celery_app

log = structlog.get_logger()

FAILED_DRAFT_RETENTION_DAYS = 7


@celery_app.task(
    name="creation.cleanup_failed_drafts",
    bind=True,
    max_retries=1,
)
def cleanup_failed_drafts(
    self, retention_days: int = FAILED_DRAFT_RETENTION_DAYS
) -> dict[str, int]:
    """软删 FAILED 状态且超过 retention_days 天的 draft。"""
    from sqlalchemy import update

    from app.db.session import AsyncSessionLocal, engine
    from app.modules.creation.enums import DraftStatus
    from app.modules.creation.model import CreationDraft

    async def _run() -> dict[str, int]:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(CreationDraft)
                .where(
                    CreationDraft.is_deleted.is_(False),
                    CreationDraft.status == DraftStatus.FAILED.value,
                    CreationDraft.created_at < cutoff,
                )
                .values(is_deleted=True)
            )
            n = int(result.rowcount or 0)  # type: ignore[attr-defined]
            await session.commit()
            return {"draft_marked": n}

    try:
        try:
            return asyncio.run(_run())
        finally:
            asyncio.run(engine.dispose())
    except Exception as exc:
        log.exception("creation.cleanup_failed_drafts failed", error=str(exc))
        raise self.retry(exc=exc) from exc
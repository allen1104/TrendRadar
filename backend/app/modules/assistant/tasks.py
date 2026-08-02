"""assistant Celery 任务。

- cleanup_old_threads：每日 04:00 软删 180 天前的 thread + 级联 message。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog

from app.worker.celery_app import celery_app

log = structlog.get_logger()

ASSISTANT_RETENTION_DAYS = 180


@celery_app.task(
    name="assistant.cleanup_old_threads",
    bind=True,
    max_retries=1,
)
def cleanup_old_threads(self, retention_days: int = ASSISTANT_RETENTION_DAYS) -> dict[str, int]:
    """180 天前的 thread 全部软删（cascade 软删其下 message）。"""
    from sqlalchemy import update

    from app.db.session import AsyncSessionLocal, engine
    from app.modules.assistant.model import AssistantMessage, AssistantThread

    async def _run() -> dict[str, int]:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with AsyncSessionLocal() as session:
            # 1. 软删超期 thread
            t_result = await session.execute(
                update(AssistantThread)
                .where(
                    AssistantThread.is_deleted.is_(False),
                    AssistantThread.created_at < cutoff,
                )
                .values(is_deleted=True)
            )
            thread_n = int(t_result.rowcount or 0)  # type: ignore[attr-defined]
            # 2. 软删这些 thread 的剩余 message（一次性清干净）
            m_result = await session.execute(
                update(AssistantMessage)
                .where(
                    AssistantMessage.is_deleted.is_(False),
                    AssistantMessage.created_at < cutoff,
                )
                .values(is_deleted=True)
            )
            msg_n = int(m_result.rowcount or 0)  # type: ignore[attr-defined]
            await session.commit()
            return {"thread_marked": thread_n, "message_marked": msg_n}

    try:
        try:
            return asyncio.run(_run())
        finally:
            asyncio.run(engine.dispose())
    except Exception as e:
        log.exception("assistant.cleanup_old_threads failed", error=str(e))
        raise self.retry(exc=e) from e
"""collection Celery 任务：每日 cleanup_task 校正 item_count。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select, update

from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.admin.decorator import tracked_task
from app.modules.collection.model import CollectionFolder, CollectionItem
from app.worker.celery_app import celery_app

configure_logging()
log = structlog.get_logger()


def _run(coro):
    from app.db.session import engine

    try:
        return asyncio.run(coro)
    finally:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            pass


@tracked_task(manual_triggerable=False, display_name="collection 每日清理")
@celery_app.task(name="collection.cleanup", bind=True)
def cleanup_task(self) -> dict[str, int]:
    """每日 03:00：
    - 校正所有 folder.item_count vs 实际 item 数
    - 物理删 is_deleted=true 超过 30 天的 folders / items
    """
    result = _run(_async_cleanup())
    log.info("collection.cleanup.done", **result)
    return result


async def _async_cleanup() -> dict[str, int]:
    deleted = {"folders": 0, "items": 0, "count_corrected": 0}
    cutoff = datetime.now(UTC) - timedelta(days=30)
    async with AsyncSessionLocal() as session:
        # 1. 校正 item_count
        rows = (
            await session.execute(
                select(
                    CollectionFolder.id,
                    CollectionFolder.item_count,
                    func.count(CollectionItem.id),
                )
                .outerjoin(
                    CollectionItem,
                    (CollectionItem.folder_id == CollectionFolder.id)
                    & CollectionItem.is_deleted.is_(False),
                )
                .where(CollectionFolder.is_deleted.is_(False))
                .group_by(CollectionFolder.id, CollectionFolder.item_count)
            )
        ).all()
        for fid, declared, actual in rows:
            if declared != actual:
                await session.execute(
                    update(CollectionFolder)
                    .where(CollectionFolder.id == fid)
                    .values(item_count=actual)
                )
                deleted["count_corrected"] += 1

        # 2. 物理删 30 天前已 soft-deleted 的
        f = (
            await session.execute(
                delete(CollectionFolder).where(
                    CollectionFolder.is_deleted.is_(True),
                    CollectionFolder.updated_at < cutoff,
                )
            )
        )
        deleted["folders"] = f.rowcount or 0
        i = (
            await session.execute(
                delete(CollectionItem).where(
                    CollectionItem.is_deleted.is_(True),
                    CollectionItem.updated_at < cutoff,
                )
            )
        )
        deleted["items"] = i.rowcount or 0

        await session.commit()
    return deleted
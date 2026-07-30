"""source 模块 Celery 任务。"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.source.enums import RunStatus, TriggerType
from app.modules.source.plugins import (
    RawItem,
    get_plugin_class,
)
from app.modules.source.service import SourceService
from app.worker.celery_app import celery_app

configure_logging()
log = structlog.get_logger()


@celery_app.task(name="source.fetch", bind=True, max_retries=2, default_retry_delay=60)
def fetch_task(self, source_id: int, trigger_type: str = "SCHEDULED", triggered_by: int | None = None):
    """单源采集任务。Celery worker 内运行。

    异步写入 source_run_log 并更新 source.last_run_*。
    """
    asyncio.run(_async_fetch(self, source_id, trigger_type, triggered_by))


async def _async_fetch(task_instance, source_id: int, trigger_type: str, triggered_by: int | None):
    from app.modules.source.exceptions import PluginNotFoundError, SourceNotFoundError

    start = time.perf_counter()
    async with AsyncSessionLocal() as session:
        service = SourceService(session)
        source = await service.repo.get(source_id)
        if source is None:
            log.warning("source.fetch.skip", reason="not found", id=source_id)
            return
        if not source.enabled:
            log.info("source.fetch.skip", reason="disabled", id=source_id)
            return

        # 写一条 RUNNING 日志
        run_log_id = await service.record_run(
            source_id=source_id,
            trigger_type=TriggerType(trigger_type),
            triggered_by=triggered_by,
            run_status=RunStatus.RUNNING,
            fetched=0,
            new=0,
            duration_ms=0,
            error=None,
        )

        try:
            plugin_cls = get_plugin_class(source.plugin_key)
        except KeyError as exc:
            err = f"plugin_key '{source.plugin_key}' 未注册: {exc}"
            log.warning("source.fetch.plugin_missing", id=source_id, error=err)
            await service.record_run(
                source_id=source_id,
                trigger_type=TriggerType(trigger_type),
                triggered_by=triggered_by,
                run_status=RunStatus.FAILED,
                fetched=0,
                new=0,
                duration_ms=int((time.perf_counter() - start) * 1000),
                error=err,
            )
            return

        plugin = plugin_cls(source.config or {})

        items: list[RawItem] = []
        try:
            items = await asyncio.wait_for(plugin.run(), timeout=180)
            run_status = RunStatus.SUCCESS if items else RunStatus.SUCCESS  # 0 也算 SUCCESS
            err = None
        except Exception as exc:  # noqa: BLE001
            run_status = RunStatus.FAILED
            items = []
            err = f"{exc.__class__.__name__}: {exc}"
            log.warning("source.fetch.failed", id=source_id, error=err)
        finally:
            await plugin.close()

        duration_ms = int((time.perf_counter() - start) * 1000)

        # 把 RawItem 灌到 article 表（pipeline 模块尚未实现，先记到日志）
        # pipeline 实现后，这里调 article_repository.upsert_many(items)
        new_count = 0
        try:
            from app.modules.pipeline.service import (  # type: ignore
                ArticleRepository,
            )
            new_count = await ArticleRepository(session).upsert_many_from_raw(items)
        except Exception:  # noqa: BLE001
            # pipeline 还没实现 → 不入库，仅记 log
            new_count = 0

        await service.record_run(
            source_id=source_id,
            trigger_type=TriggerType(trigger_type),
            triggered_by=triggered_by,
            run_status=run_status,
            fetched=len(items),
            new=new_count,
            duration_ms=duration_ms,
            error=err,
        )
        log.info(
            "source.fetch.done",
            id=source_id,
            fetched=len(items),
            new=new_count,
            duration=duration_ms,
            status=run_status.value,
        )

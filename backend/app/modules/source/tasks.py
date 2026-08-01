"""source 模块 Celery 任务。"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.admin.decorator import tracked_task
from app.modules.source.enums import RunStatus, TriggerType
from app.modules.source.plugins import (
    RawItem,
    get_plugin_class,
)
from app.modules.source.service import SourceService
from app.worker.celery_app import celery_app

configure_logging()
log = structlog.get_logger()


def _run(coro):  # type: ignore[no-untyped-def]
    """跨 Celery solo 的 asyncio.run 桥接：每次关 loop 后 dispose 引擎，
    否则 asyncpg 连接绑死旧 loop，下一次 run 报 "Event loop is closed"。
    """
    from app.db.session import engine

    try:
        return asyncio.run(coro)
    finally:
        try:
            asyncio.run(engine.dispose())
        except Exception:  # noqa: BLE001
            pass


@tracked_task(manual_triggerable=True, display_name="单源采集")
@celery_app.task(name="source.fetch", bind=True, max_retries=2, default_retry_delay=60)
def fetch_task(self, source_id: int, trigger_type: str = "SCHEDULED", triggered_by: int | None = None):
    """单源采集任务。Celery worker 内运行。

    异步写入 source_run_log 并更新 source.last_run_*。
    """
    _run(_async_fetch(self, source_id, trigger_type, triggered_by))


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
                run_log_id=run_log_id,  # 更新 RUNNING 那条，不新建
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

        # 把 RawItem 灌到 article 表（pipeline 模块接管）+ 链式触发 clean_task
        from app.modules.pipeline.repository import ArticleRepository
        from app.modules.pipeline.tasks import clean_task

        new_count = 0
        new_article_ids: list[int] = []
        if items:
            try:
                new_count, new_article_ids = await ArticleRepository(session).upsert_many_from_raw(
                    items, source_id=source_id
                )
                log.info(
                    "article.upsert.ok",
                    id=source_id,
                    total=len(items),
                    new=new_count,
                    affected=len(new_article_ids),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "article.upsert.failed",
                    id=source_id,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
                # 采集本身成功，写库失败不算采集失败 → new_count 留 0，但 run_status 不变

        # 链式触发清洗：把"受影响"的 article 全送过去（不论 inserted 还是已存在）
        if new_article_ids:
            try:
                clean_task.delay(new_article_ids)
                log.info("pipeline.clean.queued", count=len(new_article_ids))
            except Exception as exc:  # noqa: BLE001
                log.warning("pipeline.clean.queue_failed", error=f"{exc.__class__.__name__}: {exc}")

        await service.record_run(
            source_id=source_id,
            trigger_type=TriggerType(trigger_type),
            triggered_by=triggered_by,
            run_status=run_status,
            fetched=len(items),
            new=new_count,
            duration_ms=duration_ms,
            error=err,
            run_log_id=run_log_id,  # 更新 RUNNING 那条，不新建
        )
        log.info(
            "source.fetch.done",
            id=source_id,
            fetched=len(items),
            new=new_count,
            duration=duration_ms,
            status=run_status.value,
        )


# ---------------------------------------------------------------- 动态调度

def _cron_should_fire_now(cron: str, now) -> bool:
    """判定 cron 在当前分钟（精确到分）是否该触发。

    用 croniter 从「1 年前」开始推进，找 ≤ now 的最近一次 firing，
    若它落在当前这一分钟（now - 60s < firing ≤ now）→ 该触发。
    这样即使 beat 跨分钟延迟触发，只要 firing 在窗口内都生效。
    """
    from datetime import datetime, timezone
    from croniter import croniter

    try:
        anchor = now.replace(year=now.year - 1)
        it = croniter(cron, anchor)
        last_fire = None
        while True:
            nxt = it.get_next(datetime)
            if nxt > now:
                break
            last_fire = nxt
        if last_fire is None:
            return False
        return (now - last_fire).total_seconds() < 60
    except Exception as exc:  # noqa: BLE001
        log.warning("source.schedule.invalid_cron", cron=cron, error=str(exc))
        return False


@tracked_task(manual_triggerable=False, display_name="采集源调度扫描")
@celery_app.task(name="source.schedule", bind=True)
def schedule_sources_task(self) -> dict[str, int]:
    """每分钟由 Beat 触发。扫一遍 enabled source，按各自 cron 判定是否该跑。

    简单实现：每分钟查 cron 表达式；若当前分钟内该 cron 该触发，则派发 fetch_task。
    """
    from datetime import datetime, timezone
    from sqlalchemy import select

    from app.modules.source.model import Source

    now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)

    async def _go() -> dict[str, int]:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(Source).where(Source.is_deleted.is_(False), Source.enabled.is_(True))
                )
            ).scalars().all()
        triggered = 0
        for src in rows:
            if _cron_should_fire_now(src.cron, now):
                fetch_task.delay(src.id, TriggerType.SCHEDULED.value, None)
                triggered += 1
        log.info("source.schedule.scanned", total=len(rows), triggered=triggered)
        return {"total": len(rows), "triggered": triggered}

    return _run(_go())

"""source 业务层。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.source.enums import Region, RunStatus, SourceCategory, TriggerType
from app.modules.source.exceptions import (
    InvalidCronError,
    PluginNotFoundError,
    SourceAutoDisabledError,
    SourceNameExistsError,
    SourceNotFoundError,
)
from app.modules.source.model import Source, SourceRunLog
from app.modules.source.plugins import (
    RawItem,
    get_plugin_class,
    list_registered_plugins,
)
from app.modules.source.plugins.base import utcnow
from app.modules.source.repository import (
    SourceRepository,
    SourceRunLogRepository,
    preview_next_run,
)
from app.modules.source.schema import (
    RegisteredPluginInfo,
    RunLogResponse,
    SourceCreateRequest,
    SourceListItem,
    SourceResponse,
    SourceTestResponse,
    SourceUpdateRequest,
)

log = structlog.get_logger()

PREVIEW_LIMIT = 10
FETCH_TIMEOUT_SEC = 180
CONSECUTIVE_FAIL_THRESHOLD = 5


def _to_response(source: Source) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        plugin_key=source.plugin_key,
        name=source.name,
        region=source.region,  # type: ignore[arg-type]
        category=source.category,  # type: ignore[arg-type]
        home_url=source.home_url,
        config=source.config,
        cron=source.cron,
        weight=source.weight,
        enabled=source.enabled,
        last_run_at=source.last_run_at,
        last_run_status=source.last_run_status,  # type: ignore[arg-type]
        consecutive_fails=source.consecutive_fails,
        next_run_preview=preview_next_run(source.cron),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


class SourceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SourceRepository(session)
        self.log_repo = SourceRunLogRepository(session)

    async def list(
        self,
        *,
        region: Region | None = None,
        category: SourceCategory | None = None,
        enabled_only: bool = False,
        keyword: str | None = None,
    ) -> list[SourceListItem]:
        rows = await self.repo.list(
            region=region.value if region else None,
            category=category.value if category else None,
            enabled_only=enabled_only,
            keyword=keyword,
        )
        items: list[SourceListItem] = []
        for s in rows:
            today = await self.log_repo.today_count(s.id)
            items.append(
                SourceListItem(
                    id=s.id,
                    plugin_key=s.plugin_key,
                    name=s.name,
                    region=s.region,  # type: ignore[arg-type]
                    category=s.category,  # type: ignore[arg-type]
                    cron=s.cron,
                    weight=s.weight,
                    enabled=s.enabled,
                    last_run_at=s.last_run_at,
                    last_run_status=s.last_run_status,  # type: ignore[arg-type]
                    consecutive_fails=s.consecutive_fails,
                    today_count=today,
                    created_at=s.created_at,
                )
            )
        return items

    async def get(self, source_id: int) -> SourceResponse:
        source = await self.repo.get(source_id)
        if source is None:
            raise SourceNotFoundError
        return _to_response(source)

    async def create(self, payload: SourceCreateRequest, *, user: User | None = None) -> SourceResponse:
        # 校验 plugin_key 已注册
        try:
            get_plugin_class(payload.plugin_key)
        except KeyError as exc:
            raise PluginNotFoundError from exc

        if await self.repo.get_by_name(payload.name):
            raise SourceNameExistsError

        source = await self.repo.create(
            plugin_key=payload.plugin_key,
            name=payload.name,
            region=payload.region.value,
            category=payload.category.value,
            home_url=payload.home_url,
            config=payload.config,
            cron=payload.cron,
            weight=payload.weight,
            enabled=payload.enabled,
        )
        log.info("source.created", id=source.id, name=source.name)
        # 审计
        if user is not None:
            from app.modules.admin.enums import AuditAction, TargetType
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action=AuditAction.SOURCE_CREATE,
                target_type=TargetType.SOURCE,
                target_id=source.id,
                after={
                    "name": source.name,
                    "plugin_key": source.plugin_key,
                    "cron": source.cron,
                    "enabled": source.enabled,
                    "weight": source.weight,
                },
                actor=user,
            )
        return _to_response(source)

    async def update(
        self, source_id: int, payload: SourceUpdateRequest, *, user: User | None = None
    ) -> SourceResponse:
        source = await self.repo.get(source_id)
        if source is None:
            raise SourceNotFoundError
        # 仅把 user 实际填的字段更新
        fields = [
            "name",
            "region",
            "category",
            "home_url",
            "config",
            "cron",
            "weight",
            "enabled",
        ]
        before: dict = {}
        after: dict = {}
        for f in fields:
            v = getattr(payload, f)
            if v is not None:
                if f in ("region", "category"):
                    new_val = v.value
                else:
                    new_val = v
                old_val = getattr(source, f)
                if old_val != new_val:
                    before[f] = old_val
                    after[f] = new_val
                setattr(source, f, new_val)
        await self.repo.save(source)
        # flush 后属性过期，refresh 再读
        await self.session.refresh(source)
        log.info("source.updated", id=source.id)
        # 审计
        if user is not None and after:
            from app.modules.admin.enums import AuditAction, TargetType
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action=AuditAction.SOURCE_UPDATE,
                target_type=TargetType.SOURCE,
                target_id=source_id,
                before=before,
                after=after,
                actor=user,
            )
        return _to_response(source)

    async def delete(self, source_id: int, *, user: User | None = None) -> None:
        source = await self.repo.get(source_id)
        if source is None:
            raise SourceNotFoundError
        before_snapshot = {
            "name": source.name,
            "plugin_key": source.plugin_key,
            "enabled": source.enabled,
        }
        await self.repo.soft_delete(source)
        log.info("source.deleted", id=source_id)
        if user is not None:
            from app.modules.admin.enums import AuditAction, TargetType
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action=AuditAction.SOURCE_DELETE,
                target_type=TargetType.SOURCE,
                target_id=source_id,
                before=before_snapshot,
                after=None,
                actor=user,
            )

    async def list_registered(self) -> list[RegisteredPluginInfo]:
        out: list[RegisteredPluginInfo] = []
        for key, cls in list_registered_plugins():
            try:
                get_plugin_class(key)  # 验证可实例化
                from .plugins.base import SourcePlugin as _SP

                # implemented = 父类不是 _StubPlugin
                is_stub = cls.__base__.__name__ == "_StubPlugin"
                out.append(
                    RegisteredPluginInfo(
                        plugin_key=key,
                        display_name=cls.display_name,
                        region=cls.region,  # type: ignore[arg-type]
                        category=cls.category,  # type: ignore[arg-type]
                        default_cron=cls.default_cron,
                        default_weight=cls.default_weight,
                        config_schema=cls.config_schema,
                        implemented=not is_stub,
                    )
                )
            except KeyError:
                pass
        return out

    async def test_connection(
        self, source_id: int, override_config: dict | None = None
    ) -> SourceTestResponse:
        """试跑一次：fetch → parse → normalize，返回前 N 条预览 + 错误信息。

        不写库，不消耗 ai/ pipeline 资源（除非 pipeline 已开发好）。
        """
        source = await self.repo.get(source_id)
        if source is None:
            raise SourceNotFoundError
        try:
            plugin_cls = get_plugin_class(source.plugin_key)
        except KeyError as exc:
            raise PluginNotFoundError from exc

        cfg = {**(source.config or {}), **(override_config or {})}
        plugin = plugin_cls(cfg)

        start = time.perf_counter()
        try:
            items: list[RawItem] = await plugin.run()
        except Exception as exc:  # noqa: BLE001
            duration = int((time.perf_counter() - start) * 1000)
            log.warning("source.test_failed", id=source_id, error=str(exc))
            return SourceTestResponse(
                success=False,
                fetched_count=0,
                duration_ms=duration,
                error_message=f"{exc.__class__.__name__}: {exc}",
            )
        finally:
            await plugin.close()

        duration = int((time.perf_counter() - start) * 1000)
        preview_items = [
            {
                "externalId": it.external_id,
                "title": it.title,
                "url": it.url,
                "author": it.author,
                "publishedAt": it.published_at.isoformat() if it.published_at else None,
                "lang": it.lang,
                "metrics": it.metrics,
            }
            for it in items[:PREVIEW_LIMIT]
        ]
        log.info("source.test_ok", id=source_id, count=len(items), duration=duration)
        return SourceTestResponse(
            success=True,
            fetched_count=len(items),
            duration_ms=duration,
            preview=preview_items,
        )

    async def record_run(
        self,
        *,
        source_id: int,
        trigger_type: TriggerType,
        triggered_by: int | None,
        run_status: RunStatus,
        fetched: int,
        new: int,
        duration_ms: int,
        error: str | None,
        run_log_id: int | None = None,
    ) -> int:
        """写/更新一条 source_run_log，更新 source 的 last_run_* 与 consecutive_fails。

        传 run_log_id 则更新同一条记录（保留 started_at + RUNNING 状态），
        不传则新建。一次 fetch 只该产生一条日志。
        """
        if run_log_id is None:
            now_naive = utcnow().replace(tzinfo=None)
            row = await self.log_repo.create(
                source_id=source_id,
                trigger_type=trigger_type.value,
                triggered_by=triggered_by,
                status=run_status.value,
                fetched_count=fetched,
                new_count=new,
                duration_ms=duration_ms,
                error_message=error,
                started_at=now_naive,
                finished_at=now_naive if run_status != RunStatus.RUNNING else None,
            )
            log_id = row.id
        else:
            updated = await self.log_repo.update(
                run_log_id,
                status=run_status.value,
                fetched_count=fetched,
                new_count=new,
                duration_ms=duration_ms,
                error_message=error,
                finished_at=utcnow().replace(tzinfo=None),
            )
            log_id = updated.id if updated else run_log_id

        source = await self.repo.get(source_id)
        if source is not None:
            source.last_run_at = utcnow().replace(tzinfo=None)
            source.last_run_status = run_status.value
            if run_status in (RunStatus.FAILED,):
                source.consecutive_fails += 1
                if source.consecutive_fails >= CONSECUTIVE_FAIL_THRESHOLD:
                    source.enabled = False
                    log.warning(
                        "source.auto_disabled",
                        id=source_id,
                        name=source.name,
                        fails=source.consecutive_fails,
                    )
            else:
                # SUCCESS / PARTIAL / RUNNING 都视为成功
                source.consecutive_fails = 0
            await self.repo.save(source)
        await self.session.commit()
        return log_id

    async def list_logs(
        self,
        *,
        source_id: int | None,
        status: RunStatus | None,
        start_date: datetime | None,
        end_date: datetime | None,
        page: int,
        size: int,
    ) -> tuple[list[RunLogResponse], int]:
        rows, total = await self.log_repo.list(
            source_id=source_id,
            status=status.value if status else None,
            start_date=start_date,
            end_date=end_date,
            offset=(page - 1) * size,
            limit=size,
        )
        return [_to_log(r) for r in rows], total

    async def get_log(self, log_id: int) -> RunLogResponse:
        row = await self.log_repo.get(log_id)
        if row is None:
            raise SourceNotFoundError
        return _to_log(row)


def _to_log(r: SourceRunLog) -> RunLogResponse:
    return RunLogResponse(
        id=r.id,
        source_id=r.source_id,
        task_id=r.task_id,
        trigger_type=r.trigger_type,  # type: ignore[arg-type]
        status=r.status,  # type: ignore[arg-type]
        fetched_count=r.fetched_count,
        new_count=r.new_count,
        duration_ms=r.duration_ms,
        error_message=r.error_message,
        started_at=r.started_at,
        finished_at=r.finished_at,
        created_at=r.created_at,
    )

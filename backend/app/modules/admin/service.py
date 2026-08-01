"""admin 业务编排层。

- ConfigService：系统配置读 + 写 + 热生效
- AuditService：审计写入（try/except 隔离，敏感字段脱敏）
- TaskRunLogService：Celery 任务日志查询
- DashboardService：仪表盘聚合
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import RedisKey, redis_client
from app.modules.admin.enums import (
    AuditAction,
    ConfigGroup,
    TargetType,
    ValueType,
)
from app.modules.admin.exceptions import (
    ConfigNotFoundError,
    ConfigReadOnlyError,
    ConfigTypeMismatchError,
    ConfigValueOutOfRangeError,
    RankWeightsSumInvalidError,
)
from app.modules.admin.model import AuditLog, SystemConfig, TaskRunLog
from app.modules.admin.repository import (
    AuditLogRepository,
    SystemConfigRepository,
    TaskRunLogRepository,
)
from app.modules.admin.schema import (
    AiCostCard,
    AlertItem,
    AuditLogDetail,
    AuditLogItem,
    ConfigItem,
    ConfigUpdateRequest,
    DashboardResponse,
    HealthCheck,
    OverviewCard,
    PipelineHealth,
    SourceStatusItem,
    TaskRunLogDetail,
    TaskRunLogItem,
    TrendPoint,
)
from app.modules.auth.model import User

log = structlog.get_logger()

CONFIG_CACHE_TTL = 60
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "password",
        "password_hash",
        "token",
        "secret",
        "access_token",
        "refresh_token",
    }
)
_RANK_WEIGHTS_KEY = "rank_weights"
_RANK_WEIGHT_FIELDS = ("heat", "value", "originality", "trend")


# ----------------------------------------------------------------- 工具


def _coerce_and_check_type(row: SystemConfig, value: Any) -> Any:
    """按 value_type 强转 + 范围校验。失败抛 ConfigTypeMismatchError / ConfigValueOutOfRangeError。"""
    vt = row.value_type
    if vt == ValueType.INT.value:
        if not isinstance(value, int) or isinstance(value, bool):
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ConfigTypeMismatchError(
                    f"该配置需要 INT，实际收到 {type(value).__name__}"
                ) from exc
        if row.min_value is not None and value < float(row.min_value):
            raise ConfigValueOutOfRangeError(
                f"值 {value} 小于下限 {row.min_value}",
                extra={"min": float(row.min_value), "max": float(row.max_value) if row.max_value else None},
            )
        if row.max_value is not None and value > float(row.max_value):
            raise ConfigValueOutOfRangeError(
                f"值 {value} 大于上限 {row.max_value}",
                extra={"min": float(row.min_value), "max": float(row.max_value)},
            )
    elif vt == ValueType.FLOAT.value:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise ConfigTypeMismatchError(
                    f"该配置需要 FLOAT，实际收到 {type(value).__name__}"
                ) from exc
        else:
            value = float(value)
        if row.min_value is not None and value < float(row.min_value):
            raise ConfigValueOutOfRangeError(
                f"值 {value} 小于下限 {row.min_value}",
                extra={"min": float(row.min_value), "max": float(row.max_value) if row.max_value else None},
            )
        if row.max_value is not None and value > float(row.max_value):
            raise ConfigValueOutOfRangeError(
                f"值 {value} 大于上限 {row.max_value}",
                extra={"min": float(row.min_value), "max": float(row.max_value)},
            )
    elif vt == ValueType.BOOL.value:
        if not isinstance(value, bool):
            raise ConfigTypeMismatchError("该配置需要 BOOL")
    elif vt == ValueType.STRING.value:
        if not isinstance(value, str):
            raise ConfigTypeMismatchError("该配置需要 STRING")
    elif vt == ValueType.JSON.value:
        if not isinstance(value, (dict, list)):
            raise ConfigTypeMismatchError("该配置需要 JSON 对象或数组")
    return value


def _redact_sensitive(data: Any) -> Any:
    """递归脱敏敏感字段。"""

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: ("***" if k.lower() in SENSITIVE_KEYS else _walk(v))
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [_walk(x) for x in node]
        return node

    return _walk(data)


def _row_to_item(row: SystemConfig) -> ConfigItem:
    return ConfigItem(
        id=row.id,
        config_key=row.config_key,
        config_value=row.config_value,
        value_type=ValueType(row.value_type),
        group_name=ConfigGroup(row.group_name),
        display_name=row.display_name,
        description=row.description,
        min_value=float(row.min_value) if row.min_value is not None else None,
        max_value=float(row.max_value) if row.max_value is not None else None,
        is_editable=row.is_editable,
        requires_rerun=row.requires_rerun,
        updated_at=row.updated_at,
    )


# ----------------------------------------------------------------- ConfigService


class ConfigService:
    """系统配置：get 走 Redis 60s 缓存 + 内存兜底；update 写库 + 失效 + 触发 beat reload。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SystemConfigRepository(session)
        self._mem_cache: dict[str, Any] = {}

    async def list_configs(self, *, group: str | None = None) -> list[ConfigItem]:
        rows = await self.repo.list(group=group)
        return [_row_to_item(r) for r in rows]

    async def get(self, key: str, default: Any = None) -> Any:
        """业务读取：先内存 → Redis → DB。"""
        if key in self._mem_cache:
            return self._mem_cache[key]
        try:
            cached = await redis_client.get(RedisKey.config_cache(key))
            if cached is not None:
                val = json.loads(cached)
                self._mem_cache[key] = val
                return val
        except Exception:  # noqa: BLE001
            pass
        row = await self.repo.get_by_key(key)
        if row is None:
            return default
        self._mem_cache[key] = row.config_value
        try:
            await redis_client.set(
                RedisKey.config_cache(key),
                json.dumps(row.config_value),
                ex=CONFIG_CACHE_TTL,
            )
        except Exception:  # noqa: BLE001
            pass
        return row.config_value

    async def update(
        self, key: str, payload: ConfigUpdateRequest
    ) -> ConfigItem:
        row = await self.repo.get_by_key(key)
        if row is None:
            raise ConfigNotFoundError
        if not row.is_editable:
            raise ConfigReadOnlyError

        value = payload.config_value
        value = _coerce_and_check_type(row, value)

        # rank_weights 四项和必须 = 1
        if row.config_key == _RANK_WEIGHTS_KEY and isinstance(value, dict):
            total = sum(float(value.get(k, 0)) for k in _RANK_WEIGHT_FIELDS)
            if abs(total - 1.0) > 1e-6:
                raise RankWeightsSumInvalidError(
                    f"rank_weights 四项之和必须等于 1，当前为 {total:.4f}",
                    extra={"sum": total, "fields": list(value.keys())},
                )

        before = row.config_value
        await self.repo.update_value(key, value)
        await self.session.commit()

        # 失效 Redis 缓存 + 内存
        self._mem_cache.pop(key, None)
        try:
            await redis_client.delete(RedisKey.config_cache(key))
        except Exception:  # noqa: BLE001
            pass

        # cron 类配置改完后通知 Beat
        is_cron = row.group_name == ConfigGroup.SCHEDULE.value or "_cron" in key
        if is_cron:
            try:
                await redis_client.publish(
                    RedisKey.beat_reload_channel(),
                    json.dumps({"reason": key, "ts": datetime.now(UTC).isoformat()}),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("admin.beat_reload.publish_failed", error=str(exc))

        log.info(
            "admin.config.updated",
            key=key,
            before=before if isinstance(before, (int, float, str, bool)) else type(before).__name__,
            after=value if isinstance(value, (int, float, str, bool)) else type(value).__name__,
        )
        # refresh 拿最新行（含 updated_at）
        await self.session.refresh(row)
        return _row_to_item(row)

    async def invalidate_all(self) -> None:
        self._mem_cache.clear()
        try:
            async for k in redis_client.scan_iter(match="config:cache:*", count=200):
                await redis_client.delete(k)
        except Exception:  # noqa: BLE001
            pass


# ----------------------------------------------------------------- AuditService


class AuditService:
    """审计写入：try/except 隔离，写入失败只 log 不抛，避免污染业务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AuditLogRepository(session)

    async def record(
        self,
        *,
        action: AuditAction,
        target_type: TargetType,
        target_id: int | None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        actor: User | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        trace_id: str | None = None,
        note: str | None = None,
    ) -> None:
        try:
            await self.repo.create(
                user_id=actor.id if actor else None,
                username=actor.username if actor else None,
                action=action.value,
                target_type=target_type.value,
                target_id=target_id,
                before_value=_redact_sensitive(before) if before else None,
                after_value=_redact_sensitive(after) if after else None,
                ip=(ip or "")[:64] or None,
                user_agent=(user_agent or "")[:500] or None,
                trace_id=(trace_id or "")[:64] or None,
                note=(note or "")[:500] or None,
            )
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001 — 审计失败不阻断业务
            log.warning("admin.audit.write_failed", error=str(exc), action=action.value)
            try:
                await self.session.rollback()
            except Exception:  # noqa: BLE001
                pass

    async def list_logs(
        self,
        *,
        user_id: int | None,
        action: str | None,
        target_type: str | None,
        target_id: int | None,
        start_date: datetime | None,
        end_date: datetime | None,
        page: int,
        size: int,
    ) -> tuple[list[AuditLogItem], int]:
        rows, total = await self.repo.list(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            start_date=start_date,
            end_date=end_date,
            offset=(page - 1) * size,
            limit=size,
        )
        items = [
            AuditLogItem(
                id=r.id,
                user_id=r.user_id,
                username=r.username,
                action=AuditAction(r.action),
                target_type=TargetType(r.target_type),
                target_id=r.target_id,
                ip=r.ip,
                trace_id=r.trace_id,
                note=r.note,
                created_at=r.created_at,
            )
            for r in rows
        ]
        return items, total

    async def get_detail(self, audit_id: int) -> AuditLogDetail:
        row = await self.repo.get(audit_id)
        if row is None:
            from app.modules.admin.exceptions import ConfigNotFoundError  # 复用 404 语义
            raise ConfigNotFoundError("audit 日志不存在")
        return AuditLogDetail(
            id=row.id,
            user_id=row.user_id,
            username=row.username,
            action=AuditAction(row.action),
            target_type=TargetType(row.target_type),
            target_id=row.target_id,
            ip=row.ip,
            trace_id=row.trace_id,
            note=row.note,
            created_at=row.created_at,
            before_value=row.before_value,
            after_value=row.after_value,
            user_agent=row.user_agent,
        )


# ----------------------------------------------------------------- TaskRunLogService


class TaskRunLogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TaskRunLogRepository(session)

    async def list_logs(
        self,
        *,
        task_name: str | None,
        status: str | None,
        trigger_type: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        page: int,
        size: int,
    ) -> tuple[list[TaskRunLogItem], int]:
        rows, total = await self.repo.list(
            task_name=task_name,
            status=status,
            trigger_type=trigger_type,
            start_date=start_date,
            end_date=end_date,
            offset=(page - 1) * size,
            limit=size,
        )
        return [_to_item(r) for r in rows], total

    async def get_detail(self, run_id: int) -> TaskRunLogDetail:
        row = await self.repo.get(run_id)
        if row is None:
            from app.modules.admin.exceptions import ConfigNotFoundError
            raise ConfigNotFoundError("任务日志不存在")
        return TaskRunLogDetail(
            id=row.id,
            task_name=row.task_name,
            task_id=row.task_id,
            trigger_type=row.trigger_type,
            triggered_by=row.triggered_by,
            status=row.status,
            duration_ms=row.duration_ms,
            retry_count=row.retry_count,
            error_message=row.error_message,
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.created_at,
            args_summary=row.args_summary or {},
            result_summary=row.result_summary,
            traceback=row.traceback,
        )


def _to_item(row: TaskRunLog) -> TaskRunLogItem:
    return TaskRunLogItem(
        id=row.id,
        task_name=row.task_name,
        task_id=row.task_id,
        trigger_type=row.trigger_type,
        triggered_by=row.triggered_by,
        status=row.status,
        duration_ms=row.duration_ms,
        retry_count=row.retry_count,
        error_message=row.error_message,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )


# ----------------------------------------------------------------- DashboardService


class DashboardService:
    """聚合 overview / pipelineHealth / aiCost / sourceStatus / recentAlerts / trend7d。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.config_svc = ConfigService(session)

    async def build(self) -> DashboardResponse:
        return DashboardResponse(
            overview=await self._overview(),
            pipeline_health=await self._pipeline_health(),
            ai_cost=await self._ai_cost(),
            source_status=await self._source_status(),
            recent_alerts=await self._recent_alerts(),
            trend7d=await self._trend7d(),
        )

    async def health(self) -> HealthCheck:
        """就绪检查：PG + Redis + Celery broker（同 Redis）+ pipeline dedupe 队列积压。"""
        from sqlalchemy import text

        from app.db.session import engine

        checks: dict[str, str] = {}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["postgres"] = f"error: {exc.__class__.__name__}"
        try:
            await redis_client.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc.__class__.__name__}"

        healthy = all(v == "ok" for v in checks.values())
        return HealthCheck(
            status="ok" if healthy else "degraded",
            checks=checks,
        )

    async def _overview(self) -> OverviewCard:
        from sqlalchemy import func, select
        from app.modules.auth.model import User
        from app.modules.pipeline.model import Article, Event
        from app.modules.source.model import Source

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        async def _count(model, *, where=None) -> int:
            stmt = select(func.count(model.id)).where(model.is_deleted.is_(False))
            if where is not None:
                stmt = stmt.where(where)
            return int((await self.session.execute(stmt)).scalar() or 0)

        total_events = await _count(Event)
        total_articles = await _count(Article)
        total_users = await _count(User)
        active_sources = await _count(Source, where=Source.enabled.is_(True))
        today_new_events = await _count(Event, where=Event.created_at >= today_start)
        today_new_articles = await _count(Article, where=Article.created_at >= today_start)
        return OverviewCard(
            total_events=total_events,
            total_articles=total_articles,
            today_new_events=today_new_events,
            today_new_articles=today_new_articles,
            active_sources=active_sources,
            total_users=total_users,
        )

    async def _pipeline_health(self) -> PipelineHealth:
        from sqlalchemy import func, select
        from app.modules.pipeline.enums import ArticleStatus, EventStatus
        from app.modules.pipeline.model import Article, Event

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        article_rows = (
            await self.session.execute(
                select(Article.status, func.count(Article.id)).where(
                    Article.is_deleted.is_(False)
                ).group_by(Article.status)
            )
        ).all()
        event_rows = (
            await self.session.execute(
                select(Event.status, func.count(Event.id)).where(
                    Event.is_deleted.is_(False)
                ).group_by(Event.status)
            )
        ).all()

        article_by = {s: int(c) for s, c in article_rows}
        event_by = {s: int(c) for s, c in event_rows}

        total_embedded = article_by.get(ArticleStatus.EMBEDDED.value, 0)
        total_clustered = article_by.get(ArticleStatus.CLUSTERED.value, 0)
        dedupe_rate = (
            1.0 - (total_clustered / total_embedded) if total_embedded > 0 else 0.0
        )

        avg_source = (
            await self.session.execute(
                select(func.coalesce(func.avg(Event.source_count), 0)).where(
                    Event.is_deleted.is_(False)
                )
            )
        ).scalar() or 0

        today_failed = int(
            (
                await self.session.execute(
                    select(func.count(Article.id)).where(
                        Article.is_deleted.is_(False),
                        Article.status == ArticleStatus.FAILED.value,
                        Article.created_at >= today_start,
                    )
                )
            ).scalar()
            or 0
        )

        return PipelineHealth(
            article_by_status=article_by,
            event_by_status=event_by,
            today_failed_articles=today_failed,
            pending_clean=article_by.get(ArticleStatus.RAW.value, 0),
            pending_embed=article_by.get(ArticleStatus.CLEANED.value, 0),
            pending_ai=event_by.get(EventStatus.PENDING_AI.value, 0),
            avg_source_per_event=float(avg_source),
            dedupe_rate=round(float(dedupe_rate), 4),
        )

    async def _ai_cost(self) -> AiCostCard:
        from sqlalchemy import func, select
        from app.modules.ai.model import AICallLog

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)

        today_usd = float(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(AICallLog.cost_usd), 0)).where(
                        AICallLog.created_at >= today_start
                    )
                )
            ).scalar()
            or 0
        )
        month_usd = float(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(AICallLog.cost_usd), 0)).where(
                        AICallLog.created_at >= month_start
                    )
                )
            ).scalar()
            or 0
        )
        daily_limit = float(await self.config_svc.get("ai_daily_cost_limit_usd", 20.0))
        limit_reached = today_usd >= daily_limit
        return AiCostCard(
            today_usd=round(today_usd, 4),
            month_usd=round(month_usd, 4),
            daily_limit_usd=daily_limit,
            limit_reached=limit_reached,
        )

    async def _source_status(self) -> list[SourceStatusItem]:
        from sqlalchemy import select
        from app.modules.source.model import Source
        from app.modules.source.repository import SourceRunLogRepository

        rows = (
            (await self.session.execute(select(Source).where(Source.is_deleted.is_(False))))
            .scalars()
            .all()
        )
        log_repo = SourceRunLogRepository(self.session)
        items: list[SourceStatusItem] = []
        for s in rows:
            today = await log_repo.today_count(s.id)
            items.append(
                SourceStatusItem(
                    id=s.id,
                    name=s.name,
                    enabled=s.enabled,
                    last_run_status=s.last_run_status,
                    last_run_at=s.last_run_at,
                    today_count=today,
                    consecutive_fails=s.consecutive_fails,
                )
            )
        return items

    async def _recent_alerts(self) -> list[AlertItem]:
        from app.modules.admin.enums import AlertLevel

        rows = await AuditLogRepository(self.session).recent_alerts(limit=10)
        out: list[AlertItem] = []
        for r in rows:
            note = r.note or ""
            level = AlertLevel.WARN
            if "ERROR" in note.upper() or "AUTO_DISABLED" in r.action:
                level = AlertLevel.ERROR
            elif "REACHED" in r.action:
                level = AlertLevel.ERROR
            out.append(
                AlertItem(
                    id=r.id,
                    level=level,
                    message=note or r.action,
                    created_at=r.created_at,
                )
            )
        return out

    async def _trend7d(self) -> list[TrendPoint]:
        from sqlalchemy import func, select
        from app.modules.ai.model import AICallLog
        from app.modules.pipeline.model import Article, Event

        today = datetime.now(UTC).date()
        start = today - timedelta(days=6)
        article_rows = (
            await self.session.execute(
                select(func.date(Article.created_at).label("d"), func.count(Article.id)).where(
                    Article.is_deleted.is_(False),
                    Article.created_at >= start,
                ).group_by("d")
            )
        ).all()
        event_rows = (
            await self.session.execute(
                select(func.date(Event.created_at).label("d"), func.count(Event.id)).where(
                    Event.is_deleted.is_(False),
                    Event.created_at >= start,
                ).group_by("d")
            )
        ).all()
        cost_rows = (
            await self.session.execute(
                select(
                    func.date(AICallLog.created_at).label("d"),
                    func.coalesce(func.sum(AICallLog.cost_usd), 0),
                ).where(AICallLog.created_at >= start).group_by("d")
            )
        ).all()

        a_map = {d: int(c) for d, c in article_rows}
        e_map = {d: int(c) for d, c in event_rows}
        c_map = {d: float(c) for d, c in cost_rows}

        out: list[TrendPoint] = []
        for i in range(7):
            d = start + timedelta(days=i)
            out.append(
                TrendPoint(
                    date=d.isoformat(),
                    articles=a_map.get(d, 0),
                    events=e_map.get(d, 0),
                    ai_cost_usd=round(c_map.get(d, 0.0), 4),
                )
            )
        return out
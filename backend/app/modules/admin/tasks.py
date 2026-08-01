"""admin 模块 Celery 任务：cleanup_task / health_check_task。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.redis import RedisKey, redis_client
from app.db.session import AsyncSessionLocal
from app.modules.admin.decorator import tracked_task
from app.modules.admin.enums import (
    AlertLevel,
    AuditAction,
    TargetType,
    TaskRunStatus,
)
from app.modules.admin.model import AuditLog, SystemConfig, TaskRunLog
from app.modules.admin.repository import AuditLogRepository
from app.modules.ai.model import AICallLog
from app.modules.pipeline.enums import ArticleStatus
from app.modules.pipeline.model import Article
from app.modules.source.model import Source, SourceRunLog
from app.modules.source.repository import SourceRunLogRepository
from app.worker.celery_app import celery_app

configure_logging()
log = structlog.get_logger()


def _run(coro):  # type: ignore[no-untyped-def]
    """跨 Celery solo 的 asyncio.run 桥接。"""
    from app.db.session import engine

    try:
        return asyncio.run(coro)
    finally:
        try:
            asyncio.run(engine.dispose())
        except Exception:  # noqa: BLE001
            pass


def _record_system_alert(action: AuditAction, note: str, level: AlertLevel) -> None:
    """写一条 SYSTEM 告警审计（在独立 session 里）。"""
    async def _go() -> None:
        async with AsyncSessionLocal() as session:
            await AuditLogRepository(session).create(
                action=action.value,
                target_type=TargetType.SYSTEM.value,
                target_id=None,
                note=f"[{level.value}] {note}",
            )
            await session.commit()

    try:
        _run(_go())
    except Exception as exc:  # noqa: BLE001
        log.warning("admin.alert.write_failed", error=str(exc))


# ----------------------------------------------------------------- cleanup_task


@tracked_task(manual_triggerable=False, display_name="清理过期日志")
@celery_app.task(name="admin.cleanup", bind=True)
def cleanup_task(self) -> dict[str, int]:
    """清理：
    - source_run_log / task_run_log 保留 30 天
    - ai_call_log 保留 90 天
    - audit_log 保留 180 天
    - article.status=DISCARDED 保留 30 天
    """

    async def _go() -> dict[str, int]:
        now = datetime.now(UTC)
        cutoff_30 = now - timedelta(days=30)
        cutoff_90 = now - timedelta(days=90)
        cutoff_180 = now - timedelta(days=180)
        deleted = {"source_run_log": 0, "task_run_log": 0, "ai_call_log": 0, "audit_log": 0, "discarded_articles": 0}

        async with AsyncSessionLocal() as session:
            for label, model, cutoff in [
                ("source_run_log", SourceRunLog, cutoff_30),
                ("task_run_log", TaskRunLog, cutoff_30),
            ]:
                while True:
                    res = await session.execute(
                        delete(model)
                        .where(model.created_at < cutoff)
                        .execution_options(synchronize_session=False)
                        .limit(5000)
                    )
                    await session.commit()
                    n = res.rowcount or 0
                    deleted[label] += n
                    if n < 5000:
                        break

            while True:
                res = await session.execute(
                    delete(AICallLog)
                    .where(AICallLog.created_at < cutoff_90)
                    .execution_options(synchronize_session=False)
                    .limit(5000)
                )
                await session.commit()
                n = res.rowcount or 0
                deleted["ai_call_log"] += n
                if n < 5000:
                    break

            while True:
                res = await session.execute(
                    delete(AuditLog)
                    .where(AuditLog.created_at < cutoff_180)
                    .execution_options(synchronize_session=False)
                    .limit(5000)
                )
                await session.commit()
                n = res.rowcount or 0
                deleted["audit_log"] += n
                if n < 5000:
                    break

            while True:
                res = await session.execute(
                    delete(Article)
                    .where(
                        Article.status == ArticleStatus.DISCARDED.value,
                        Article.created_at < cutoff_30,
                    )
                    .execution_options(synchronize_session=False)
                    .limit(5000)
                )
                await session.commit()
                n = res.rowcount or 0
                deleted["discarded_articles"] += n
                if n < 5000:
                    break

        log.info("admin.cleanup.done", **deleted)
        return deleted

    return _run(_go())


# ----------------------------------------------------------------- health_check_task


@tracked_task(manual_triggerable=False, display_name="健康检查与告警")
@celery_app.task(name="admin.health_check", bind=True)
def health_check_task(self) -> dict[str, Any]:
    """5 类告警：
    - 采集源连续失败 ≥3 → WARN
    - 采集源被自动禁用 → ERROR
    - AI 当日费用 >80% 限额 → WARN；>100% → ERROR + 暂停系统任务
    - Celery 队列积压 > 1000 → WARN
    - article.status=FAILED 今日新增 > 50 → WARN
    """

    async def _check() -> dict[str, Any]:
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        alerts: list[dict[str, str]] = []
        running = 0

        async with AsyncSessionLocal() as session:
            # ---------- 1. source 连续失败
            src_rows = (
                await session.execute(
                    select(Source).where(Source.is_deleted.is_(False))
                )
            ).scalars().all()
            for s in src_rows:
                if s.consecutive_fails >= 3 and s.enabled:
                    alerts.append(
                        {
                            "level": AlertLevel.WARN.value,
                            "message": f"采集源「{s.name}」连续失败 {s.consecutive_fails} 次",
                        }
                    )
                if not s.enabled and s.consecutive_fails >= 5:
                    alerts.append(
                        {
                            "level": AlertLevel.ERROR.value,
                            "message": f"采集源「{s.name}」已被自动禁用",
                        }
                    )

            # ---------- 2. AI 当日费用
            daily_limit_val = 20.0
            daily_limit_row = (
                await session.execute(
                    select(SystemConfig).where(
                        SystemConfig.config_key == "ai_daily_cost_limit_usd",
                        SystemConfig.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if daily_limit_row is not None:
                try:
                    daily_limit_val = float(daily_limit_row.config_value)
                except (TypeError, ValueError):
                    pass

            today_usd = float(
                (
                    await session.execute(
                        select(func.coalesce(func.sum(AICallLog.cost_usd), 0)).where(
                            AICallLog.created_at >= today_start
                        )
                    )
                ).scalar()
                or 0
            )
            pct = (today_usd / daily_limit_val) if daily_limit_val > 0 else 0.0
            if pct >= 1.0:
                alerts.append(
                    {
                        "level": AlertLevel.ERROR.value,
                        "message": f"AI 当日费用 {today_usd:.4f} USD 已达 {pct*100:.1f}% 限额（{daily_limit_val}），系统任务已暂停",
                    }
                )
                # 暂停：写一条 SYSTEM_TASK_PAUSED 审计 + 改 system_config 标志（用 audit_log 表达）
                _record_system_alert(
                    AuditAction.AI_DAILY_LIMIT_REACHED,
                    f"today={today_usd:.4f}usd limit={daily_limit_val}usd pct={pct:.2%}",
                    AlertLevel.ERROR,
                )
            elif pct >= 0.8:
                alerts.append(
                    {
                        "level": AlertLevel.WARN.value,
                        "message": f"AI 当日费用 {today_usd:.4f} USD 已用 {pct*100:.1f}% 限额",
                    }
                )

            # ---------- 3. Celery 队列积压
            running_count = (
                await session.execute(
                    select(func.count(TaskRunLog.id)).where(
                        TaskRunLog.status == TaskRunStatus.RUNNING.value,
                        TaskRunLog.is_deleted.is_(False),
                    )
                )
            ).scalar() or 0
            running = int(running_count)
            if running > 1000:
                alerts.append(
                    {
                        "level": AlertLevel.WARN.value,
                        "message": f"Celery 任务运行中 {running} 条，超阈值 1000",
                    }
                )

            # ---------- 4. article FAILED 今日新增
            failed_today = (
                await session.execute(
                    select(func.count(Article.id)).where(
                        Article.is_deleted.is_(False),
                        Article.status == ArticleStatus.FAILED.value,
                        Article.created_at >= today_start,
                    )
                )
            ).scalar() or 0
            if int(failed_today) > 50:
                alerts.append(
                    {
                        "level": AlertLevel.WARN.value,
                        "message": f"今日 article FAILED 新增 {failed_today} 条，超阈值 50",
                    }
                )

        # 写告警到 audit_log（每条一条）
        for a in alerts:
            action = (
                AuditAction.SOURCE_AUTO_DISABLED
                if a["level"] == AlertLevel.ERROR.value and "自动禁用" in a["message"]
                else AuditAction.SYSTEM_ALERT
            )
            _record_system_alert(action, a["message"], AlertLevel(a["level"]))

        return {"alerts_count": len(alerts), "running_tasks": running, "today_ai_cost_usd": today_usd}

    return _run(_check())
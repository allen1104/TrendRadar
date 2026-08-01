"""admin 数据访问层。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.model import AuditLog, SystemConfig, TaskRunLog
from app.modules.admin.enums import TaskRunStatus

log = structlog.get_logger()


# ----------------------------------------------------------------- system_config


class SystemConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_key(self, key: str) -> SystemConfig | None:
        return (
            await self.session.execute(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )
        ).scalar_one_or_none()

    async def list(
        self, *, group: str | None = None
    ) -> Sequence[SystemConfig]:
        stmt = select(SystemConfig).where(SystemConfig.is_deleted.is_(False))
        if group:
            stmt = stmt.where(SystemConfig.group_name == group)
        stmt = stmt.order_by(SystemConfig.group_name, SystemConfig.config_key)
        return (await self.session.execute(stmt)).scalars().all()

    async def update_value(self, key: str, value: Any) -> SystemConfig | None:
        row = await self.get_by_key(key)
        if row is None:
            return None
        row.config_value = value
        await self.session.flush()
        return row


# ----------------------------------------------------------------- task_run_log


class TaskRunLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields: Any) -> TaskRunLog:
        row = TaskRunLog(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(self, run_id: int, **fields: Any) -> TaskRunLog | None:
        row = await self.get(run_id)
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        await self.session.flush()
        return row

    async def get(self, run_id: int) -> TaskRunLog | None:
        return await self.session.get(TaskRunLog, run_id)

    async def get_by_task_id(self, task_id: str) -> TaskRunLog | None:
        return (
            await self.session.execute(
                select(TaskRunLog).where(TaskRunLog.task_id == task_id)
            )
        ).scalar_one_or_none()

    async def list(
        self,
        *,
        task_name: str | None = None,
        status: str | None = None,
        trigger_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[TaskRunLog], int]:
        stmt = select(TaskRunLog).where(TaskRunLog.is_deleted.is_(False))
        if task_name:
            stmt = stmt.where(TaskRunLog.task_name == task_name)
        if status:
            stmt = stmt.where(TaskRunLog.status == status)
        if trigger_type:
            stmt = stmt.where(TaskRunLog.trigger_type == trigger_type)
        if start_date:
            stmt = stmt.where(TaskRunLog.started_at >= start_date)
        if end_date:
            stmt = stmt.where(TaskRunLog.started_at < end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)

        rows = (
            (
                await self.session.execute(
                    stmt.order_by(TaskRunLog.id.desc()).offset(offset).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def latest_for_task(self, task_name: str) -> TaskRunLog | None:
        return (
            await self.session.execute(
                select(TaskRunLog)
                .where(TaskRunLog.task_name == task_name)
                .order_by(TaskRunLog.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def running_count(self) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count(TaskRunLog.id)).where(
                        TaskRunLog.status == TaskRunStatus.RUNNING.value,
                        TaskRunLog.is_deleted.is_(False),
                    )
                )
            ).scalar()
            or 0
        )

    async def delete_older_than(self, cutoff: datetime, *, batch_size: int = 5000) -> int:
        """物理删除（保留窗口外的旧日志），分批避免长事务。"""
        total = 0
        while True:
            res = await self.session.execute(
                delete(TaskRunLog)
                .where(TaskRunLog.created_at < cutoff)
                .execution_options(synchronize_session=False)
                .limit(batch_size)
            )
            await self.session.commit()
            n = res.rowcount or 0
            total += n
            if n < batch_size:
                break
        return total


# ----------------------------------------------------------------- audit_log


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields: Any) -> AuditLog:
        row = AuditLog(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, audit_id: int) -> AuditLog | None:
        return await self.session.get(AuditLog, audit_id)

    async def list(
        self,
        *,
        user_id: int | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog).where(AuditLog.is_deleted.is_(False))
        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if target_type:
            stmt = stmt.where(AuditLog.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(AuditLog.target_id == target_id)
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditLog.created_at < end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)

        rows = (
            (
                await self.session.execute(
                    stmt.order_by(AuditLog.id.desc()).offset(offset).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def recent_alerts(self, limit: int = 10) -> list[AuditLog]:
        """最近告警（SYSTEM_ALERT / AI_DAILY_LIMIT_REACHED / SYSTEM_TASK_PAUSED）。"""
        from app.modules.admin.enums import AuditAction

        return list(
            (
                await self.session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.action.in_(
                            [
                                AuditAction.SYSTEM_ALERT.value,
                                AuditAction.AI_DAILY_LIMIT_REACHED.value,
                                AuditAction.SOURCE_AUTO_DISABLED.value,
                            ]
                        )
                    )
                    .order_by(AuditLog.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def delete_older_than(self, cutoff: datetime, *, batch_size: int = 5000) -> int:
        total = 0
        while True:
            res = await self.session.execute(
                delete(AuditLog)
                .where(AuditLog.created_at < cutoff)
                .execution_options(synchronize_session=False)
                .limit(batch_size)
            )
            await self.session.commit()
            n = res.rowcount or 0
            total += n
            if n < batch_size:
                break
        return total
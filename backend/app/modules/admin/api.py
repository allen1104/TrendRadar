"""admin 路由：dashboard / configs / tasks / audit / trigger。

健康探针由 main.py 直接注册（不再重复）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import PageParams, page_params
from app.core.redis import RedisKey, redis_client
from app.core.schema import Page
from app.modules.admin.decorator import TASK_REGISTRY, get_task_metadata
from app.modules.admin.enums import TaskRunStatus, TriggerType
from app.modules.admin.exceptions import (
    TaskAlreadyRunningError,
    TaskNotFailedError,
    TaskNotFoundError,
    TaskNotTriggerableError,
)
from app.modules.admin.model import TaskRunLog
from app.modules.admin.repository import TaskRunLogRepository
from app.modules.admin.schema import (
    AuditLogDetail,
    AuditLogItem,
    ConfigItem,
    ConfigUpdateRequest,
    DashboardResponse,
    TaskDefinitionItem,
    TaskRunLogDetail,
    TaskRunLogItem,
    TaskTriggerRequest,
    TaskTriggerResponse,
)
from app.modules.admin.service import (
    AuditService,
    ConfigService,
    DashboardService,
    TaskRunLogService,
)
from app.modules.auth.deps import AdminUser, DbSession, EditorUser

router = APIRouter(prefix="/admin", tags=["admin"])


# ----------------------------------------------------------------- dashboard


@router.get("/dashboard", response_model=DashboardResponse, summary="总览仪表盘（EDITOR+）")
async def dashboard(session: DbSession, _user: EditorUser) -> DashboardResponse:
    return await DashboardService(session).build()


# ----------------------------------------------------------------- configs


@router.get(
    "/configs",
    response_model=list[ConfigItem],
    summary="系统配置列表（ADMIN）",
)
async def list_configs(
    session: DbSession,
    _user: AdminUser,
    group: Annotated[str | None, Query(description="按分组过滤")] = None,
) -> list[ConfigItem]:
    return await ConfigService(session).list_configs(group=group)


@router.put(
    "/configs/{config_key}",
    response_model=ConfigItem,
    summary="修改系统配置（ADMIN）",
)
async def update_config(
    config_key: str,
    payload: ConfigUpdateRequest,
    session: DbSession,
    _user: AdminUser,
) -> ConfigItem:
    return await ConfigService(session).update(config_key, payload)


# ----------------------------------------------------------------- tasks


def _get_task_definitions_sync() -> list[TaskDefinitionItem]:
    """扫描 Celery 注册表 + 最近一次日志 + 锁状态。同步函数（内含 asyncio.run）。"""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.worker.celery_app import celery_app

    async def _latest(name: str) -> dict[str, Any] | None:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(TaskRunLog)
                    .where(TaskRunLog.task_name == name)
                    .order_by(TaskRunLog.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return {"last_run_at": row.started_at, "last_run_status": row.status}

    out: list[TaskDefinitionItem] = []
    for name, task in sorted(celery_app.tasks.items()):
        if not name.startswith(("source.", "pipeline.", "ai.", "admin.")):
            continue
        if name.endswith((".schedule",)) or name == "source.schedule":
            continue

        # 元数据从 TASK_REGISTRY 取（tracked_task 装饰时注册）
        meta = get_task_metadata(name)
        manual = meta["manual_triggerable"]
        display = meta["display_name"]

        cron: str | None = None
        for entry in celery_app.conf.beat_schedule.values():
            if entry.get("task") == name:
                sched = entry.get("schedule")
                cron = str(sched) if sched else None
                break

        try:
            last = asyncio.run(_latest(name))
        except Exception:  # noqa: BLE001
            last = None
        try:
            is_running = bool(asyncio.run(redis_client.exists(RedisKey.task_running_lock(name))))
        except Exception:  # noqa: BLE001
            is_running = False

        out.append(
            TaskDefinitionItem(
                task_name=name,
                display_name=display,
                cron=cron,
                enabled=True,
                next_run_at=None,
                last_run_at=last["last_run_at"] if last else None,
                last_run_status=TaskRunStatus(last["last_run_status"]) if last else None,
                manual_triggerable=manual,
                is_running=is_running,
            )
        )
    return out


@router.get(
    "/tasks/definitions",
    response_model=list[TaskDefinitionItem],
    summary="任务定义列表（EDITOR+）",
)
async def task_definitions(_user: EditorUser) -> list[TaskDefinitionItem]:
    return _get_task_definitions_sync()


@router.get(
    "/tasks",
    response_model=Page[TaskRunLogItem],
    summary="任务运行日志（EDITOR+）",
)
async def list_task_logs(
    session: DbSession,
    _user: EditorUser,
    pagination: Annotated[PageParams, Depends(page_params)],
    task_name: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    trigger_type: Annotated[str | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
) -> Page[TaskRunLogItem]:
    rows, total = await TaskRunLogService(session).list_logs(
        task_name=task_name,
        status=status,
        trigger_type=trigger_type,
        start_date=start_date,
        end_date=end_date,
        page=pagination.page,
        size=pagination.size,
    )
    return Page[TaskRunLogItem].create(items=rows, total=total, page=pagination.page, size=pagination.size)


@router.get(
    "/tasks/{run_id}",
    response_model=TaskRunLogDetail,
    summary="任务日志详情（EDITOR+）",
)
async def get_task_log(
    run_id: int,
    session: DbSession,
    _user: EditorUser,
) -> TaskRunLogDetail:
    return await TaskRunLogService(session).get_detail(run_id)


@router.post(
    "/tasks/trigger",
    response_model=TaskTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="手动触发任务（EDITOR+）",
)
async def trigger_task(
    payload: TaskTriggerRequest,
    user: EditorUser,
) -> TaskTriggerResponse:
    from app.db.session import AsyncSessionLocal
    from app.worker.celery_app import celery_app

    # autodiscover_tasks 只在 worker 进程里跑，API 进程需要显式 import 模块
    import importlib

    for mod in (
        "app.modules.admin.tasks",
        "app.modules.source.tasks",
        "app.modules.pipeline.tasks",
    ):
        try:
            importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            pass

    task = celery_app.tasks.get(payload.task_name)
    if task is None:
        raise TaskNotFoundError
    # 元数据从 TASK_REGISTRY 取（Celery @task 不会保留装饰器自定义属性）
    meta = get_task_metadata(payload.task_name)
    if not meta["manual_triggerable"]:
        raise TaskNotTriggerableError

    lock_key = RedisKey.task_running_lock(payload.task_name)
    locked = await redis_client.set(lock_key, "1", ex=600, nx=True)
    if not locked:
        raise TaskAlreadyRunningError

    try:
        async_result = task.apply_async(args=payload.args, kwargs=payload.kwargs)
    except Exception:
        try:
            await redis_client.delete(lock_key)
        except Exception:  # noqa: BLE001
            pass
        raise

    async def _insert_log() -> int:
        # 复用 tracked_task 的独立 NullPool engine，跨 loop 安全
        from app.modules.admin.decorator import _LOG_SESSION_LOCAL

        async with _LOG_SESSION_LOCAL() as session:
            row = await TaskRunLogRepository(session).create(
                task_name=payload.task_name,
                task_id=str(async_result.id),
                trigger_type=TriggerType.MANUAL.value,
                triggered_by=user.id,
                args_summary={"args": payload.args, "kwargs": payload.kwargs},
                status=TaskRunStatus.PENDING.value,
                started_at=datetime.utcnow(),
            )
            await session.commit()
            return row.id

    try:
        run_id = asyncio.run(_insert_log())
    except Exception:  # noqa: BLE001
        run_id = 0
    return TaskTriggerResponse(task_id=str(async_result.id), run_log_id=run_id)


@router.post(
    "/tasks/{run_id}/retry",
    response_model=TaskTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重试失败任务（EDITOR+）",
)
async def retry_task(
    run_id: int,
    session: DbSession,
    _user: EditorUser,
) -> TaskTriggerResponse:
    from app.worker.celery_app import celery_app

    svc = TaskRunLogService(session)
    detail = await svc.get_detail(run_id)
    if detail.status != TaskRunStatus.FAILED.value:
        raise TaskNotFailedError(f"当前状态 {detail.status}，仅 FAILED 可重试")

    task = celery_app.tasks.get(detail.task_name)
    if task is None:
        raise TaskNotFoundError

    args = detail.args_summary.get("args", []) if detail.args_summary else []
    kwargs = detail.args_summary.get("kwargs", {}) if detail.args_summary else {}
    safe_kwargs = {
        k: v for k, v in kwargs.items() if isinstance(v, (int, float, str, bool))
    }
    async_result = task.apply_async(args=args, kwargs=safe_kwargs)
    return TaskTriggerResponse(task_id=str(async_result.id), run_log_id=run_id)


# ----------------------------------------------------------------- audit


@router.get(
    "/audit-logs",
    response_model=Page[AuditLogItem],
    summary="审计日志（ADMIN）",
)
async def list_audit_logs(
    session: DbSession,
    _user: AdminUser,
    pagination: Annotated[PageParams, Depends(page_params)],
    user_id: Annotated[int | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    target_id: Annotated[int | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
) -> Page[AuditLogItem]:
    rows, total = await AuditService(session).list_logs(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        start_date=start_date,
        end_date=end_date,
        page=pagination.page,
        size=pagination.size,
    )
    return Page[AuditLogItem].create(items=rows, total=total, page=pagination.page, size=pagination.size)


@router.get(
    "/audit-logs/{audit_id}",
    response_model=AuditLogDetail,
    summary="审计日志详情（ADMIN）",
)
async def get_audit_log(
    audit_id: int,
    session: DbSession,
    _user: AdminUser,
) -> AuditLogDetail:
    return await AuditService(session).get_detail(audit_id)
"""tracked_task 装饰器 + task_run_log 写入。

实现策略（修复跨 event loop bug 后）：
1. `@tracked_task(...)` 仅注册元数据（display_name / manual_triggerable）
   到 TASK_REGISTRY，并透传 Celery Task 接口（delay / apply_async / name 等）
2. task_run_log 写入走 Celery signal（task_prerun / task_success / task_failure）。
3. signal handler 是同步的（Celery solo worker），用独立的 NullPool engine + 短生命周期
   asyncpg 连接跑一次 asyncio.run() 写入，避开业务 engine 的连接池跨 loop 问题。
"""

from __future__ import annotations

import asyncio
import functools
import time
from datetime import UTC, datetime
from typing import Any, Callable

import structlog
from celery import signals
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import configure_logging

log = structlog.get_logger()
configure_logging()


# 元数据注册表：task_name → {"display_name": ..., "manual_triggerable": bool, "trigger_type": ...}
TASK_REGISTRY: dict[str, dict[str, Any]] = {}

# 当前 task 的运行时上下文（prerun 写入 → success/failure 读取）
_RUN_CONTEXT: dict[str, dict[str, Any]] = {}


def get_task_metadata(task_name: str) -> dict[str, Any]:
    """admin API 取任务元数据用。"""
    return TASK_REGISTRY.get(
        task_name,
        {"display_name": task_name, "manual_triggerable": True, "trigger_type": "SCHEDULED"},
    )


def _summarize_args(args: tuple, kwargs: dict) -> dict[str, Any]:
    """入参摘要：不存大对象，只存键名 + 类型 + 长度上限。"""

    def _one(v: Any) -> Any:
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        if isinstance(v, (list, tuple)):
            return {"type": type(v).__name__, "len": len(v)}
        if isinstance(v, dict):
            return {"type": "dict", "keys": list(v.keys())[:20]}
        return {"type": type(v).__name__}

    return {
        "args": [_one(a) for a in args[:10]],
        "kwargs": {k: _one(v) for k, v in list(kwargs.items())[:10]},
    }


def tracked_task(
    *,
    manual_triggerable: bool = True,
    display_name: str | None = None,
    trigger_type: str = "SCHEDULED",
) -> Callable:
    """装饰 Celery task 函数，仅注册元数据。

    task_run_log 写入由 task_prerun / task_success / task_failure signal 完成。
    """

    def decorator(func: Callable) -> Callable:
        task_name = getattr(func, "name", None) or func.__name__
        TASK_REGISTRY[task_name] = {
            "display_name": display_name or func.__name__,
            "manual_triggerable": manual_triggerable,
            "trigger_type": trigger_type,
        }

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)

        # 透传 Celery Task 接口（delay / apply_async / name 等）
        for attr in (
            "delay",
            "apply_async",
            "name",
            "max_retries",
            "default_retry_delay",
            "acks_late",
            "time_limit",
            "soft_time_limit",
        ):
            if hasattr(func, attr):
                try:
                    setattr(wrapper, attr, getattr(func, attr))
                except (AttributeError, TypeError):
                    pass

        wrapper.__wrapped__ = func
        wrapper._tracked_task_metadata = TASK_REGISTRY[task_name]
        return wrapper

    return decorator


# ----------------------------------------------------------------- Celery signals

# 独立 engine：NullPool + 短生命周期连接，避免与业务 session 共享连接池时的
# "Event loop is closed" 问题。每次写日志开新 loop → 开新连接 → 关闭。
_LOG_ENGINE = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)
_LOG_SESSION_LOCAL = async_sessionmaker(
    _LOG_ENGINE, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


def _run_coroutine_safely(coro) -> Any:
    """在全新的 event loop 上跑 coroutine，避免与业务 loop 冲突。"""
    try:
        return asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001
        import traceback

        log.warning(
            "admin.tracked_task.log_failed",
            error=str(exc),
            tb=traceback.format_exc()[:500],
        )
        return None


@signals.task_prerun.connect
def _on_task_prerun(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra) -> None:  # noqa: ANN001
    """任务开始：插 RUNNING 行，run_id 缓存在 _RUN_CONTEXT。"""
    if task is None:
        return
    task_name = task.name
    meta = TASK_REGISTRY.get(task_name, {"trigger_type": "SCHEDULED"})
    trigger_type = meta.get("trigger_type", "SCHEDULED")
    if not isinstance(trigger_type, str):
        trigger_type = "SCHEDULED"
    triggered_by = (kwargs or {}).get("triggered_by") if kwargs else None
    if triggered_by is None and args and len(args) >= 2 and isinstance(args[1], int):
        triggered_by = args[1]
    args_summary = _summarize_args(tuple(args or ()), kwargs or {})

    async def _do() -> int:
        from app.modules.admin.enums import TaskRunStatus
        from app.modules.admin.repository import TaskRunLogRepository

        async with _LOG_SESSION_LOCAL() as session:
            repo = TaskRunLogRepository(session)
            row = await repo.create(
                task_name=task_name,
                task_id=task_id,
                trigger_type=trigger_type,
                triggered_by=triggered_by if isinstance(triggered_by, int) else None,
                args_summary=args_summary,
                status=TaskRunStatus.RUNNING.value,
                started_at=datetime.now(UTC),
            )
            await session.commit()
            return row.id

    run_id = _run_coroutine_safely(_do()) or 0
    _RUN_CONTEXT[task_id] = {
        "run_id": run_id,
        "task_name": task_name,
        "start": time.perf_counter(),
    }


def _finalize_sync(
    task_id: str,
    status_value: str,
    *,
    result: dict | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
    traceback_str: str | None = None,
) -> None:
    ctx = _RUN_CONTEXT.pop(task_id, None)
    if not ctx:
        log.warning("admin.tracked_task.finalize_no_ctx", task_id=task_id, status=status_value)
        return
    run_id = ctx.get("run_id", 0)
    if not run_id:
        log.warning("admin.tracked_task.finalize_no_run_id", task_id=task_id, status=status_value)
        return
    log.info(
        "admin.tracked_task.finalize",
        task_id=task_id,
        run_id=run_id,
        status=status_value,
        duration_ms=duration_ms,
    )

    async def _do() -> None:
        from app.modules.admin.repository import TaskRunLogRepository

        async with _LOG_SESSION_LOCAL() as session:
            repo = TaskRunLogRepository(session)
            await repo.update(
                run_id,
                status=status_value,
                result_summary=result,
                duration_ms=duration_ms,
                error_message=(error_message or "")[:4000] or None,
                traceback=(traceback_str or "")[:8000] or None,
                finished_at=datetime.now(UTC),
            )
            await session.commit()

    _run_coroutine_safely(_do())


@signals.task_success.connect
def _on_task_success(sender=None, result=None, **extra) -> None:  # noqa: ANN001
    # task_id 在 sender.request.id（不是 extra）
    task_id = getattr(getattr(sender, "request", None), "id", None) or extra.get("task_id")
    log.info(
        "admin.tracked_task.success_signal",
        task_id=task_id,
        task_id_type=type(task_id).__name__,
        ctx_keys=list(_RUN_CONTEXT.keys()),
        has_key=task_id in _RUN_CONTEXT,
    )
    if not task_id:
        return
    ctx = _RUN_CONTEXT.pop(task_id, None)
    if not ctx:
        log.warning(
            "admin.tracked_task.success_no_ctx",
            task_id=task_id,
            ctx_keys=list(_RUN_CONTEXT.keys()),
        )
        return
    duration_ms = None
    if ctx.get("start") is not None:
        duration_ms = int((time.perf_counter() - ctx["start"]) * 1000)
    summary: dict[str, Any] | None = None
    if isinstance(result, dict):
        summary = {
            k: v for k, v in result.items() if isinstance(v, (int, float, str, bool))
        }
    _finalize_sync(
        task_id,
        "SUCCESS",
        result=summary,
        duration_ms=duration_ms,
    )


@signals.task_failure.connect
def _on_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    einfo=None,
    **extra,
) -> None:  # noqa: ANN001
    # task_failure 的 task_id 在 sender.request.id（不是 kwargs）
    if not task_id:
        task_id = getattr(getattr(sender, "request", None), "id", None)
    if not task_id:
        return
    ctx = _RUN_CONTEXT.pop(task_id, None)
    if not ctx:
        return
    duration_ms = None
    if ctx.get("start") is not None:
        duration_ms = int((time.perf_counter() - ctx["start"]) * 1000)
    err_msg = f"{exception.__class__.__name__}: {exception}" if exception else "task failed"
    tb = einfo.traceback if einfo and getattr(einfo, "traceback", None) else None
    _finalize_sync(
        task_id,
        "FAILED",
        duration_ms=duration_ms,
        error_message=err_msg,
        traceback_str=tb,
    )


# 兼容旧代码里的可能引用
MANUAL_TRIGGERABLE_ATTR = "manual_triggerable"
DISPLAY_NAME_ATTR = "display_name"

__all__ = [
    "TASK_REGISTRY",
    "tracked_task",
    "get_task_metadata",
    "MANUAL_TRIGGERABLE_ATTR",
    "DISPLAY_NAME_ATTR",
]
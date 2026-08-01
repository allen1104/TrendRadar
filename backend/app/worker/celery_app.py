"""Celery 应用与调度配置。"""

from typing import Any

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "trendradar",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,
    result_expires=3600,
)

# 模块任务在此注册（随模块开发逐步放开）
celery_app.autodiscover_tasks(
    [
        "app.modules.admin",
        "app.modules.auth",
        "app.modules.ai",
        "app.modules.source",
        "app.modules.pipeline",
    ]
)


# ---------------------------------------------------------------- worker 启动 hook
# 1. 绑定 Celery worker 的 event loop 到全局，便于 admin.decorator 的 signal handler
#    用 run_coroutine_threadsafe 在主 loop 上跑 asyncpg 操作
# 2. 显式 connect admin.decorator 的 Celery signal（autodiscover 已 import 了 module，
#    signal 通过 @signals.task_prerun.connect 装饰器自动注册；但为确保 worker_process_init
#    时连接已就绪，再显式 import 模块一次）
import asyncio as _asyncio

from celery import signals as _celery_signals
from celery.signals import worker_process_init as _wp_init


@_wp_init.connect
def _bind_worker_loop(**_: Any) -> None:
    """把 Celery worker 进程的 event loop 绑到 db.session 全局。

    Celery solo 模式下 worker 没有显式 event loop；本函数用 try/except 兜底：
    - 若 worker 是 prefork / threads（有 loop）→ 用它
    - 否则 → 留 None，decorator 走 asyncio.run 兜底
    """
    try:
        loop = _asyncio.get_event_loop()
        from app.db.session import set_worker_loop

        set_worker_loop(loop)
    except RuntimeError:
        # 无 loop（线程模式）→ 跳过；decorator 会降级用 asyncio.run
        pass


# 显式触发 admin.decorator 模块加载（让 Celery signal @connect 注册生效）
import app.modules.admin.decorator as _admin_decorator  # noqa: F401

# 静态调度：流水线周期任务
# 采集源各自独立的 cron 走「动态调度」：每分钟跑一次 source.schedule_task，
# 它查 source 表，按 cron 表达式判定哪些该跑，触发 source.fetch_task.delay(source_id)。
celery_app.conf.beat_schedule = {
    # 每分钟扫描一次 source 表，按各自 cron 触发采集（动态调度）
    "schedule-sources-every-minute": {
        "task": "source.schedule",
        "schedule": crontab(minute="*"),
    },
    # 聚合去重每 20 分钟跑一次（全局锁，多 worker 也只一个实例运行）
    "pipeline-dedupe": {
        "task": "pipeline.dedupe",
        "schedule": crontab(minute="*/20"),
    },
    # 评分入榜每 6 小时跑一次
    "pipeline-rank": {
        "task": "pipeline.rank",
        "schedule": crontab(minute="10", hour="*/6"),
    },
    # 事件归档每小时跑一次
    "pipeline-archive": {
        "task": "pipeline.archive",
        "schedule": crontab(minute="0"),
    },
    # 健康检查每 5 分钟
    "admin-health-check": {
        "task": "admin.health_check",
        "schedule": crontab(minute="*/5"),
    },
    # 日志清理每日 03:00
    "admin-cleanup": {
        "task": "admin.cleanup",
        "schedule": crontab(minute="0", hour="3"),
    },
}
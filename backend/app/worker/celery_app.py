"""Celery 应用与调度配置。"""

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
        "app.modules.auth",
        "app.modules.ai",
        "app.modules.source",
        "app.modules.pipeline",
        # "app.modules.admin",
    ]
)

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
}
"""Celery 应用与调度配置。"""

from celery import Celery

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
        # "app.modules.source",
        # "app.modules.pipeline",
        # "app.modules.ai",
        # "app.modules.admin",
    ]
)

# 静态调度；动态调度（每个采集源的 cron）由 Beat 从数据库加载
celery_app.conf.beat_schedule = {}

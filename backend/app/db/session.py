"""异步数据库会话管理。"""

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core.config import settings

# Celery worker 用 asyncio.run() 跨任务桥接，每次 run() 会关闭 loop。
# 让 pool_pre_ping + pool_recycle 处理跨 loop 的连接复用问题。
engine = create_async_engine(
    settings.database_url,
    echo=settings.DATABASE_ECHO,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

# Celery worker 主 event loop（在 worker_process_init 时绑定）
_WORKER_LOOP: asyncio.AbstractEventLoop | None = None


def set_worker_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Celery worker_process_init 信号调用一次。"""
    global _WORKER_LOOP
    _WORKER_LOOP = loop


def get_worker_loop() -> asyncio.AbstractEventLoop | None:
    """返回 worker 的事件循环（admin/decorator 用于跑 coroutine）。"""
    return _WORKER_LOOP


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：按请求生命周期提供数据库会话。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
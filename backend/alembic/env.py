from logging.config import fileConfig

from alembic import context
from app.core.config import settings
from app.db.base import Base

# 各模块的 model 在此 import，Alembic autogenerate 才能发现它们
from app.modules.admin import model as _admin_model  # noqa: F401
from app.modules.ai import model as _ai_model  # noqa: F401
from app.modules.assistant import model as _assistant_model  # noqa: F401
from app.modules.auth import model as _auth_model  # noqa: F401
from app.modules.collection import model as _collection_model  # noqa: F401
from app.modules.creation import model as _creation_model  # noqa: F401
from app.modules.pipeline import model as _pipeline_model  # noqa: F401
from app.modules.source import model as _source_model  # noqa: F401
from app.modules.trend import model as _trend_model  # noqa: F401
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

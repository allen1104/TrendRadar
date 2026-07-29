"""初始化脚本：系统配置、Prompt 模板、初始管理员。

用法：
    uv run python -m app.scripts.seed
    docker compose exec api python -m app.scripts.seed

幂等：重复执行不会产生重复数据（已存在的跳过）。
"""

import asyncio

import structlog

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.modules.auth.enums import Role
from app.modules.auth.repository import UserPreferenceRepository, UserRepository

configure_logging()
log = structlog.get_logger()


async def seed_admin_user() -> None:
    """创建初始 ADMIN 账号（见 doc/SPEC-auth.md）。"""
    async with AsyncSessionLocal() as session:
        users = UserRepository(session)
        email = settings.INITIAL_ADMIN_EMAIL.lower()
        if await users.get_by_email(email):
            log.info("seed.admin_user.exists", email=email)
            return

        user = await users.create(
            email=email,
            username=settings.INITIAL_ADMIN_USERNAME,
            password_hash=hash_password(settings.INITIAL_ADMIN_PASSWORD),
            role=Role.ADMIN,
        )
        await UserPreferenceRepository(session).create_default(user.id)
        await session.commit()
        log.info("seed.admin_user.created", email=email, user_id=user.id)


async def seed_system_configs() -> None:
    """写入 doc/SPEC-admin.md「系统配置项清单」中的 22 项配置。"""
    log.info("seed.system_configs.skipped", reason="admin 模块尚未实现")


async def seed_prompt_templates() -> None:
    """写入各 task_key 的 v1 Prompt 模板（见 doc/SPEC-ai-engine.md）。

    模板用占位符 {{var}}；PromptService.dry_run 可用任意 dict 渲染。
    """
    from app.core.security import hash_password  # noqa: F401  # 触发依赖
    from sqlalchemy import select
    from app.modules.ai.enums import TaskKey
    from app.modules.ai.model import PromptTemplate
    from app.modules.ai.repository import PromptTemplateRepository

    templates = [
        {
            "task_key": TaskKey.EVENT_ANALYSIS.value,
            "version": 1,
            "system_prompt": (
                "你是一名资深科技趋势分析师，擅长从多源信息中识别真正值得关注的事件。"
                "对每个事件给出客观、精确、可信的结构化分析。"
            ),
            "user_prompt": (
                "# 事件\n"
                "标题：{{eventTitle}}\n"
                "摘要：{{eventSummary}}\n"
                "\n"
                "# 来源文章\n"
                "{% for a in articles %}"
                "- [{{ loop.index }}] {{ a.title }}（{{ a.source_name }}）\n"
                "{% endfor %}\n"
                "\n"
                "请输出 JSON 格式的完整分析。"
            ),
            "variables": ["eventTitle", "eventSummary", "articles", "categoriesEnum"],
            "model_alias": "default-chat",
            "temperature": 0.3,
            "max_tokens": 2000,
            "is_active": True,
            "note": "v1 初始版本：通用科技事件分析",
        },
        {
            "task_key": TaskKey.EMBEDDING.value,
            "version": 1,
            "system_prompt": "你是一个文本向量化助手。",
            "user_prompt": "{{text}}",
            "variables": ["text"],
            "model_alias": "local-bge-m3",
            "temperature": 0.0,
            "max_tokens": 16,
            "is_active": True,
            "note": "v1 占位：embedding 实际由本地 ONNX 模型处理",
        },
    ]
    async with AsyncSessionLocal() as session:
        repo = PromptTemplateRepository(session)
        for tpl in templates:
            existing = await repo.get_active(tpl["task_key"])
            if existing and existing.version >= tpl["version"]:
                log.info("seed.prompt.exists", task_key=tpl["task_key"], version=existing.version)
                continue
            await repo.create(**tpl)
            log.info("seed.prompt.created", task_key=tpl["task_key"], version=tpl["version"])
        await session.commit()


async def seed_sources() -> None:
    """写入一期 8 个采集源配置（见 doc/SPEC-source.md）。"""
    log.info("seed.sources.skipped", reason="source 模块尚未实现")


async def main() -> None:
    await seed_admin_user()
    await seed_prompt_templates()
    await seed_system_configs()
    await seed_sources()
    log.info("seed.done")


if __name__ == "__main__":
    asyncio.run(main())

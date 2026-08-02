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
    from app.modules.admin.enums import ConfigGroup, ValueType
    from app.modules.admin.model import SystemConfig
    from sqlalchemy import select

    items: list[dict] = [
        # group: DEDUPE
        {
            "config_key": "dedupe_title_threshold",
            "config_value": 0.75,
            "value_type": ValueType.FLOAT.value,
            "group_name": ConfigGroup.DEDUPE.value,
            "display_name": "标题相似度直接合并阈值",
            "description": "pg_trgm 相似度超过此值直接判定为同一事件。调高更保守（少合并），调低更激进（易误合并）",
            "min_value": 0.5,
            "max_value": 0.99,
            "requires_rerun": False,
        },
        {
            "config_key": "dedupe_title_candidate",
            "config_value": 0.35,
            "value_type": ValueType.FLOAT.value,
            "group_name": ConfigGroup.DEDUPE.value,
            "display_name": "进入向量判定的候选阈值",
            "description": "标题相似度高于此值进入 L3 向量精判",
            "min_value": 0.1,
            "max_value": 0.9,
            "requires_rerun": False,
        },
        {
            "config_key": "dedupe_vector_threshold",
            "config_value": 0.85,
            "value_type": ValueType.FLOAT.value,
            "group_name": ConfigGroup.DEDUPE.value,
            "display_name": "向量相似度合并阈值",
            "description": "余弦相似度超过此值判定为同一事件",
            "min_value": 0.5,
            "max_value": 0.99,
            "requires_rerun": False,
        },
        {
            "config_key": "dedupe_time_window_hours",
            "config_value": 72,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.DEDUPE.value,
            "display_name": "聚合时间窗口（小时）",
            "description": "只在该时间窗口内的 article 参与合并",
            "min_value": 1,
            "max_value": 168,
            "requires_rerun": False,
        },
        {
            "config_key": "event_archive_hours",
            "config_value": 72,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.DEDUPE.value,
            "display_name": "事件归档阈值（小时）",
            "description": "超过该小时无新来源则归档",
            "min_value": 12,
            "max_value": 720,
            "requires_rerun": False,
        },
        {
            "config_key": "article_max_age_days",
            "config_value": 7,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.DEDUPE.value,
            "display_name": "超龄文章丢弃阈值（天）",
            "description": "首次入库 N 天前的 article 标 DISCARDED",
            "min_value": 1,
            "max_value": 30,
            "requires_rerun": False,
        },
        # group: RANK
        {
            "config_key": "rank_weights",
            "config_value": {"heat": 0.35, "value": 0.30, "originality": 0.20, "trend": 0.15},
            "value_type": ValueType.JSON.value,
            "group_name": ConfigGroup.RANK.value,
            "display_name": "推荐指数权重",
            "description": "四项之和必须等于 1。改后需重跑评分才生效",
            "requires_rerun": True,
        },
        {
            "config_key": "metric_weights",
            "config_value": {"points": 1.0, "comments": 2.0, "stars": 0.5, "upvotes": 1.0},
            "value_type": ValueType.JSON.value,
            "group_name": ConfigGroup.RANK.value,
            "display_name": "互动指标权重",
            "description": "各互动指标的归一化权重",
            "requires_rerun": True,
        },
        # group: AI
        {
            "config_key": "default_chat_model",
            "config_value": "default-chat",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "默认对话模型别名",
            "description": "未在 prompt 指定 model_alias 时使用",
            "requires_rerun": False,
        },
        {
            "config_key": "default_embedding_model",
            "config_value": "local-bge-m3",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "默认 embedding 模型别名",
            "description": "切换为不同维度的模型需全量重算向量",
            "requires_rerun": True,
        },
        {
            "config_key": "ai_fallback_chain",
            "config_value": [],
            "value_type": ValueType.JSON.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "降级链（模型别名数组）",
            "description": "主模型失败后依次尝试的备用模型",
            "requires_rerun": False,
        },
        {
            "config_key": "ai_single_call_cost_limit_usd",
            "config_value": 0.5,
            "value_type": ValueType.FLOAT.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "单次调用费用上限（USD）",
            "description": "超过则直接拒绝执行",
            "min_value": 0.01,
            "max_value": 10.0,
            "requires_rerun": False,
        },
        {
            "config_key": "ai_daily_cost_limit_usd",
            "config_value": 20.0,
            "value_type": ValueType.FLOAT.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "单日费用上限（USD）",
            "description": "超限暂停所有系统触发的 AI 任务",
            "min_value": 1.0,
            "max_value": 1000.0,
            "requires_rerun": False,
        },
        {
            "config_key": "ai_user_rate_limit",
            "config_value": 20,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "单用户 AI 调用频率（每小时）",
            "description": "用户触发的 AI 调用每窗口允许次数",
            "min_value": 1,
            "max_value": 1000,
            "requires_rerun": False,
        },
        # group: SCHEDULE
        {
            "config_key": "analyze_batch_cron",
            "config_value": "0 */6 * * *",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.SCHEDULE.value,
            "display_name": "事件分析任务调度",
            "description": "AI 批量分析 PENDING_AI 事件的 cron",
            "requires_rerun": False,
        },
        {
            "config_key": "rank_cron",
            "config_value": "10 */6 * * *",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.SCHEDULE.value,
            "display_name": "评分入榜任务调度",
            "description": "热度与推荐指数计算的 cron",
            "requires_rerun": False,
        },
        {
            "config_key": "cleanup_cron",
            "config_value": "0 3 * * *",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.SCHEDULE.value,
            "display_name": "日志清理任务调度",
            "description": "过期日志物理删除的 cron",
            "requires_rerun": False,
        },
        # group: SEARCH
        {
            "config_key": "search_text_config",
            "config_value": "simple",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.SEARCH.value,
            "display_name": "PG 全文检索配置",
            "description": "simple（无中文分词）/ zhparser（需部署扩展）",
            "requires_rerun": True,
        },
        # group: GENERAL
        {
            "config_key": "title_blacklist",
            "config_value": [],
            "value_type": ValueType.JSON.value,
            "group_name": ConfigGroup.GENERAL.value,
            "display_name": "标题垃圾词黑名单",
            "description": "命中标题的 article 会被 DISCARDED",
            "requires_rerun": False,
        },
        {
            "config_key": "site_notice",
            "config_value": "",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.GENERAL.value,
            "display_name": "全站公告",
            "description": "前台顶部横幅内容",
            "requires_rerun": False,
        },
        {
            "config_key": "fallback_embedding_model",
            "config_value": "local-bge-m3",
            "value_type": ValueType.STRING.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "Embedding 降级模型",
            "description": "本地 ONNX bge-m3 不可用时回退",
            "requires_rerun": False,
        },
        {
            "config_key": "max_pipeline_retry",
            "config_value": 2,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.GENERAL.value,
            "display_name": "Pipeline 任务最大重试次数",
            "description": "celery 任务 max_retries 覆盖值",
            "min_value": 0,
            "max_value": 10,
            "requires_rerun": False,
        },
        # group: TREND（trend 模块）
        {
            "config_key": "keyword_aliases",
            "config_value": {"大语言模型": "llm", "大模型": "llm", "AI 助手": "ai-assistant"},
            "value_type": ValueType.JSON.value,
            "group_name": ConfigGroup.TREND.value,
            "display_name": "关键词同义词映射",
            "description": "{别名: 归一化词}，聚合时把别名映射到归一化词",
            "requires_rerun": True,
        },
        {
            "config_key": "keyword_stopwords",
            "config_value": ["ai", "技术", "模型", "the", "a", "an"],
            "value_type": ValueType.JSON.value,
            "group_name": ConfigGroup.TREND.value,
            "display_name": "关键词停用词",
            "description": "停用词不进排行（去掉过泛词噪声）",
            "requires_rerun": True,
        },
        {
            "config_key": "trend_min_event_count",
            "config_value": 3,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.TREND.value,
            "display_name": "趋势最低事件数",
            "description": "关联事件数低于此值的关键词不进排行榜",
            "min_value": 1,
            "max_value": 100,
            "requires_rerun": False,
        },
        # group: AI / assistant 模块（assistant 配置与 AI 限额共用 AI 组）
        {
            "config_key": "assistant_max_context_tokens",
            "config_value": 24000,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "assistant 上下文 token 上限",
            "description": "单次提问输入 prompt + articles + history 的总 token 上限；超出触发三级裁剪",
            "min_value": 4000,
            "max_value": 128000,
            "requires_rerun": False,
        },
        {
            "config_key": "assistant_thread_cost_limit_usd",
            "config_value": 0.5,
            "value_type": ValueType.FLOAT.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "assistant 单会话成本上限（USD）",
            "description": "累计费用达到此值后禁止继续提问，提示用户新建会话",
            "min_value": 0.05,
            "max_value": 10.0,
            "requires_rerun": False,
        },
        {
            "config_key": "assistant_quick_questions",
            "config_value": [
                {"key": "why_important", "label": "为什么重要？",
                 "question": "这件事为什么重要？它对行业意味着什么？"},
                {"key": "relation", "label": "和我有什么关系？",
                 "question": "这件事和 AI 应用开发者的日常工作有什么关系？会影响哪些技术选型？"},
                {"key": "innovation", "label": "有什么创新？",
                 "question": "这件事的技术创新点具体是什么？和已有方案相比强在哪？"},
                {"key": "worth_learn", "label": "适合学习吗？",
                 "question": "如果我想深入学习这个方向，应该从哪里入手？需要什么前置知识？"},
                {"key": "worth_write", "label": "值得写文章吗？",
                 "question": "这个话题适合写成公众号文章吗？切入角度可以是什么？"},
                {"key": "business", "label": "有商业价值吗？",
                 "question": "这件事有什么商业机会？独立开发者能做什么产品？"},
            ],
            "value_type": ValueType.JSON.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "assistant 快捷问题列表",
            "description": "事件详情页问 AI 抽屉的预设问题，ADMIN 可增删改",
            "requires_rerun": False,
        },
        # creation 上下文 token 上限
        {
            "config_key": "creation_max_context_tokens",
            "config_value": 20000,
            "value_type": ValueType.INT.value,
            "group_name": ConfigGroup.AI.value,
            "display_name": "creation 上下文 token 上限",
            "description": "单次生成输入 event + articles + 参数的总 token 上限；超出触发三级裁剪",
            "min_value": 4000,
            "max_value": 128000,
            "requires_rerun": False,
        },
    ]

    async with AsyncSessionLocal() as session:
        existing = set(
            (await session.execute(select(SystemConfig.config_key))).scalars().all()
        )
        created = 0
        for item in items:
            if item["config_key"] in existing:
                continue
            session.add(SystemConfig(**item, is_editable=True))
            created += 1
        await session.commit()
        log.info("seed.system_configs.done", total=len(items), created=created)


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
        {
            "task_key": TaskKey.ASSISTANT_QA.value,
            "version": 1,
            "system_prompt": (
                "你是一名严谨的科技资讯编辑，正在帮助用户深入理解一个特定的科技热点事件。\n"
                "回答必须严格遵守以下规则：\n"
                "1. 只基于【来源文章】提供的材料回答，**绝不编造**任何具体数字、产品名、公司名或细节。\n"
                "2. 如果材料中没有提到某个信息，明确说明「提供的资料中没有提到」。\n"
                "3. 引用具体事实时用 `[编号]` 标注来源编号（编号见【来源文章】列表中的 `[1] [2] ...`）。\n"
                "4. 保持客观、中立，避免营销腔；可以使用 Markdown 格式（列表、加粗、引用）。\n"
                "5. 回答长度控制在 300-800 字之间，不要过长。"
            ),
            "user_prompt": (
                "# 当前事件\n"
                "标题：{{eventTitle}}\n"
                "\n"
                "已有分析（参考）：\n"
                "{{eventSummary}}\n"
                "\n"
                "# 来源文章\n"
                "{% for a in articles %}"
                "- [{{ loop.index }}] {{ a.title }}（{{ a.source_name }}）\n"
                "  链接：{{ a.url }}\n"
                "  正文摘要：{{ a.content }}\n"
                "{% endfor %}\n"
                "\n"
                "# 之前的对话（仅参考）\n"
                "{% for h in history %}"
                "- {{ h.role }}：{{ h.content }}\n"
                "{% endfor %}\n"
                "\n"
                "# 当前问题\n"
                "{{question}}\n"
                "\n"
                "请基于上述材料回答，记得用 `[编号]` 标注引用。"
            ),
            "variables": [
                "eventTitle", "eventSummary", "articles", "history", "question",
            ],
            "model_alias": "default-chat",
            "temperature": 0.4,
            "max_tokens": 1500,
            "is_active": True,
            "note": "v1 初始版本：事件问答 + 引用标注 + 不编造约束",
        },
    ]
    # creation 平台 × 风格 = 30 个 prompt 模板
    creation_templates = _build_creation_prompts()
    templates.extend(creation_templates)
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
    """写入一期 6 个采集源配置（见 doc/SPEC-source.md）。

    - hacker_news / github_trending / arxiv / huggingface（GLOBAL，4 个）
    - jiqizhixin / qbitai（CN，2 个）—— 满足 SPEC「6-8 个」最低要求
    """
    from app.modules.source.enums import RunStatus
    from app.modules.source.model import Source

    presets = [
        {
            "plugin_key": "hacker_news",
            "name": "Hacker News",
            "region": "GLOBAL",
            "category": "NEWS",
            "home_url": "https://news.ycombinator.com",
            "config": {"limit": 100},
            "cron": "0 * * * *",
            "weight": 9,
            "enabled": True,
        },
        {
            "plugin_key": "arxiv",
            "name": "arXiv",
            "region": "GLOBAL",
            "category": "PAPER",
            "home_url": "https://arxiv.org",
            "config": {"categories": ["cs.AI", "cs.CL", "cs.LG"], "max_results": 50},
            "cron": "0 */2 * * *",
            "weight": 8,
            "enabled": True,
        },
        {
            "plugin_key": "github_trending",
            "name": "GitHub Trending",
            "region": "GLOBAL",
            "category": "CODE",
            "home_url": "https://github.com/trending",
            "config": {"since": "daily"},
            "cron": "30 * * * *",
            "weight": 9,
            "enabled": True,
        },
        {
            "plugin_key": "huggingface",
            "name": "HuggingFace Models",
            "region": "GLOBAL",
            "category": "MODEL",
            "home_url": "https://huggingface.co/models",
            "config": {"limit": 30},
            "cron": "15 * * * *",
            "weight": 8,
            "enabled": True,
        },
        {
            "plugin_key": "jiqizhixin",
            "name": "机器之心",
            "region": "CN",
            "category": "NEWS",
            "home_url": "https://www.jiqizhixin.com",
            "config": {"feed_url": "https://www.jiqizhixin.com/rss", "limit": 30},
            "cron": "10 * * * *",
            "weight": 8,
            "enabled": True,
        },
        {
            "plugin_key": "qbitai",
            "name": "量子位",
            "region": "CN",
            "category": "NEWS",
            "home_url": "https://www.qbitai.com",
            "config": {"feed_url": "https://www.qbitai.com/feed", "limit": 30},
            "cron": "20 * * * *",
            "weight": 7,
            "enabled": True,
        },
    ]

    async with AsyncSessionLocal() as session:
        for p in presets:
            existing = await session.execute(
                Source.__table__.select().where(Source.name == p["name"])
            )
            if existing.first():
                log.info("seed.source.exists", name=p["name"])
                continue
            session.add(Source(**p))
        await session.commit()
        log.info("seed.sources.done", total=len(presets))


def _build_creation_prompts() -> list[dict]:
    """构造 creation 6 平台 × 5 风格 = 30 个 prompt 模板。

    System prompt：定义角色 + 平台 + 风格
    User prompt：用 Jinja2 模板渲染事件上下文 + 平台规格 + 风格规格 + 用户参数
    输出约定：
      - 文首第一行写 `# 标题`
      - 紧随可写 `COVER: 描述` 与 `TAGS: tag1, tag2`
      - 然后是 Markdown 正文
    """
    from app.modules.ai.enums import TaskKey

    platforms = [
        ("WECHAT", "微信公众号", 1500, 3000,
         "带钩子开头与小标题分段，结尾引导关注；不用 Markdown 表格；语言流畅、有节奏感"),
        ("BLOG", "技术博客", 2000, 4000,
         "标准 Markdown、代码块、表格、公式、结尾附参考链接"),
        ("WEIBO", "微博", 60, 140,
         "≤140 字；带 #话题# 标签 2-3 个；可分 2-3 条短串，每条独立成段"),
        ("XHS", "小红书", 300, 600,
         "emoji 分段、口语化、有画面感；结尾 #话题# 标签 5-8 个"),
        ("ZHIHU", "知乎回答", 800, 2000,
         "先给结论，再分点论述；适度引用数据与文献；避免营销腔；语言克制有逻辑"),
        ("MARKDOWN", "纯 Markdown", 1000, 3000,
         "无平台修饰；纯技术记录；可含代码块、表格、引用块"),
    ]
    styles = [
        ("TECHNICAL", "技术分析",
         "冷静客观、重原理与实现、少形容词；可含伪代码与架构图描述；目标读者是开发者"),
        ("MARKETING", "营销风格",
         "强钩子、痛点切入、场景化、有行动号召；多用感叹与对比；目标读者是潜在用户"),
        ("DEEP_DIVE", "深度解读",
         "背景→现状→影响→展望；长段论述；引用多方观点；适合公众号/技术博客深度文章"),
        ("NEWS", "新闻报道",
         "倒金字塔、5W1H、中立陈述、时间线清晰；开头给出核心事实；不评论"),
        ("CASUAL", "轻松科普",
         "类比通俗、少术语、有画面感、像讲故事；适合非技术读者"),
    ]

    system_common = (
        "你是一名资深内容创作者，正在把一个科技热点事件改写成指定平台与风格的稿件。\n"
        "硬性要求：\n"
        "1. 只基于【来源文章】与【事件已有分析】写作，**绝不编造**未在材料中出现的数据、产品名、公司名或细节。\n"
        "2. 严格遵守目标平台的字数区间（写作时心里有数，输出尽量落在区间内）。\n"
        "3. 输出格式约定：\n"
        "   - 第一行：`# 标题`（不超过 30 字，不带其他符号）\n"
        "   - 第二行（可选）：`COVER: 封面图建议描述`\n"
        "   - 第三行（可选）：`TAGS: tag1, tag2, tag3`（≤8 个，用英文逗号分隔）\n"
        "   - 第四行起：Markdown 正文\n"
        "4. 不出现 `参考资料`、`编辑注` 等元说明文字——直接产出可发布的稿件。\n"
        "5. 中文输出；专有名词可保留英文（如 GPT-5、LangGraph）。"
    )

    out: list[dict] = []
    for plat_key, plat_name, lo, hi, plat_desc in platforms:
        for style_key, style_name, style_desc in styles:
            user_prompt = (
                f"# 目标平台\n{plat_name}（{plat_key}）\n"
                f"- 字数区间：{lo}-{hi} 字\n"
                f"- 平台约束：{plat_desc}\n\n"
                f"# 目标风格\n{style_name}（{style_key}）\n"
                f"- 风格要求：{style_desc}\n\n"
                f"# 事件信息\n"
                f"- 标题：{{{{ eventTitle }}}}\n"
                f"- AI 已有分析：\n{{{{ eventAnalysis }}}}\n\n"
                f"# 来源文章（按权重与篇幅排序）\n"
                f"{{% for a in articles %}}"
                f"- [{{{{ loop.index }}}}] {{{{ a.title }}}}（{{{{ a.source_name }}}}）\n"
                f"  正文：{{{{ a.content }}}}\n"
                f"{{% endfor %}}\n\n"
                f"# 用户额外要求\n"
                f"{{% if extraRequirement %}}- 附加要求：{{{{ extraRequirement }}}}{{% endif %}}\n"
                f"{{% if audience %}}- 目标读者：{{{{ audience }}}}{% endif %}\n"
                f"- 目标字数：{{{{ targetWords }}}}\n\n"
                f"请按上述约定输出完整稿件。"
            )
            task_key_str = f"creation_{plat_key.lower()}"
            out.append(
                {
                    "task_key": task_key_str,
                    "version": 1,
                    "system_prompt": system_common,
                    "user_prompt": user_prompt,
                    "variables": [
                        "eventTitle",
                        "eventAnalysis",
                        "articles",
                        "targetWords",
                        "audience",
                        "extraRequirement",
                        "style",
                        "platform",
                    ],
                    "model_alias": "default-chat",
                    "temperature": 0.55,
                    "max_tokens": 4000,
                    "is_active": True,
                    "note": f"v1 初始版本：{plat_name} × {style_name}",
                }
            )
    return out
    await seed_admin_user()
    await seed_prompt_templates()
    await seed_system_configs()
    await seed_sources()
    log.info("seed.done")


if __name__ == "__main__":
    asyncio.run(main())

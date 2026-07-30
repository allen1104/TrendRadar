"""用设计好的 v2 内容覆盖冒烟测试的简化版。"""

import asyncio
import structlog

from sqlalchemy import select

from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.ai.model import PromptTemplate

configure_logging()
log = structlog.get_logger()

V2_SYSTEM = """你是一名资深科技趋势分析师，拥有 10 年以上的技术媒体和投资研究经验。
你擅长从多源信息中识别真正值得关注的事件，能区分营销噪音和实质性突破。

分析原则：
1. 客观 — 基于来源材料事实说话，材料中未提及的不能编造。
2. 精确 — 数字、人名、产品名要忠于原文，不要近似化处理。
3. 有判断 — 给出明确的价值判断（值得/不值得）和理由。
4. 结构化 — 严格按指定的 JSON schema 输出，每个字段都要填。

反例：
- 看到 OpenAI 发新模型就一律 value_score=90；没有具体数据就别给 95+ 的高分。
- 见到'首个'/'首创'/'革命性'就照抄；这些词在材料中实际出现才写。
- 看到 GitHub 项目一律 categories=[OPENSOURCE, PROGRAMMING]；如果本质是 AI 框架，应该是 [AI, OPENSOURCE]。"""


V2_USER = """# 待分析事件
标题：{{ eventTitle }}
{% if eventSummary %}摘要：{{ eventSummary }}
{% endif %}
# 来源材料（共 {{ articles | length }} 篇）
{% for a in articles %}[{{ loop.index }}] {{ a.title }}（{{ a.source_name }}）
{% if a.content %}{{ a.content | truncate(800) }}
{% endif %}{% endfor %}
# 分类枚举
必须从以下 11 个分类中选 1-4 个最匹配的（严格匹配，不要自造）：
{{ categoriesEnum | join('、') }}

# 输出要求
请输出一个 JSON 对象，每个字段的含义与评判标准：
1. summary_one_line：一句话说清核心事件，≤ 30 字，不带形容词堆砌。
2. summary：200-400 字。结构：背景 → 发生了什么 → 为什么重要。
3. key_points：3-5 条核心观点，每条一句话。
4. innovations：0-5 条技术创新点（无则空数组，禁止编造）。
5. audience：1-3 类适合阅读的受众（如'AI 应用开发者'）。
6. categories：从枚举中选，严格匹配枚举值。
7. tags：实体标签数组，每条 {name, type}，type ∈ {COMPANY, PRODUCT, TECH, PERSON}。
8. value_score：0-100 整数。参考：
   - 90+ 行业首创/重大范式转变
   - 70-89 重要改进/新模型/重要发布
   - 50-69 一般更新/值得关注的进展
   - 30-49 小更新/边缘案例
   - <30 营销噪音/旧闻翻炒/无实质信息
9. originality_score：0-100 整数，原创性越高分越高。
10. trend_score：0-100 整数，代表未来趋势代表性。
11. worth_article / worth_research：布尔值，不模糊，理由各 ≤ 50 字。"""


V2_VARIABLES = ["eventTitle", "eventSummary", "articles", "categoriesEnum"]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        v2 = (
            await session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.task_key == "event_analysis",
                    PromptTemplate.version == 2,
                    PromptTemplate.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if v2 is None:
            log.error("update_v2.not_found")
            return
        v2.system_prompt = V2_SYSTEM
        v2.user_prompt = V2_USER
        v2.variables = V2_VARIABLES
        v2.temperature = 0.3
        v2.max_tokens = 2000
        v2.note = "v2: 完整角色定义 + 字段评判标准 + 反例（覆盖 v1 简化版）"
        await session.commit()
        log.info(
            "update_v2.done",
            system_len=len(v2.system_prompt),
            user_len=len(v2.user_prompt),
            is_active=v2.is_active,
        )


if __name__ == "__main__":
    asyncio.run(main())

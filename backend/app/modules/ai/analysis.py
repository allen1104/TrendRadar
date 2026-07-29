"""事件分析业务逻辑（pipeline 模块尚未实现，先放 ai-engine 内部）。

调用流程：
  ① 构造 event 上下文（标题 + 来源文章摘要 + 已有分析）→ 传给 prompt
  ② 调 gateway.call(task_key=event_analysis, response_schema=EventAnalysisResult)
  ③ 把结果写 event_analysis 表，并按 manual_locked_fields 跳过回写 event 表
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.gateway.gateway import LLMGateway
from app.modules.ai.model import PromptTemplate
from app.modules.ai.repository import EventAnalysisRepository
from app.modules.ai.schema import EventAnalysisResult

log = structlog.get_logger()


class EventAnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EventAnalysisRepository(session)

    async def analyze_event(self, event_id: int, *, force: bool = False) -> "EventAnalysisResultView":
        # 构造 prompt 变量
        # 简化版：从 article / event 表读上下文（pipeline 模块尚未实现，容忍为空）
        event = await self._load_event(event_id)
        if event is None:
            raise ValueError(f"事件 {event_id} 不存在")

        existing = None if force else await self.repo.get_by_event(event_id)
        if existing is not None and not force:
            log.info("ai.event_analysis.skip_existing", event_id=event_id)
            return EventAnalysisResultView.from_model(existing)

        variables = {
            "eventTitle": event.get("title", ""),
            "eventSummary": event.get("summary", ""),
            "articles": event.get("articles", []),
        }
        gateway = LLMGateway(self.session)
        prompt = await self.session.execute(
            select(PromptTemplate).where(
                PromptTemplate.is_active.is_(True),
                PromptTemplate.task_key == "event_analysis",
            )
        )
        prompt_row = prompt.scalar_one_or_none()
        if prompt_row is None:
            raise RuntimeError("event_analysis prompt not configured")
        variables["categoriesEnum"] = [
            "AI", "AGENT", "LLM", "MCP", "PROGRAMMING",
            "OPENSOURCE", "PAPER", "STARTUP", "HARDWARE", "INTERNET", "BUSINESS",
        ]

        resp = await gateway.call(
            task_key="event_analysis",
            variables=variables,
            target_type="EVENT",
            target_id=event_id,
            response_schema=EventAnalysisResult,
        )
        assert resp.parsed is not None

        result_obj = resp.parsed
        saved = await self.repo.upsert(
            event_id=event_id,
            result_obj=result_obj,
            model_alias=(prompt_row.model_alias or "default-chat"),
            prompt_version=prompt_row.version,
        )
        log.info("ai.event_analysis.done", event_id=event_id, value=result_obj.value_score)
        return EventAnalysisResultView.from_model(saved)

    async def _load_event(self, event_id: int) -> dict | None:
        """pipeline 模块尚未实现，placeholder：返回空 context 让 prompt 自己处理。

        pipeline 实现后：读 event + article + event_article 拼成上下文。
        """
        # 真实实现需要 pipeline 模块就绪
        return {
            "title": f"event-{event_id}",
            "summary": "",
            "articles": [],
        }


class EventAnalysisResultView:
    """只读视图，用于 API 响应（替代 model 直接序列化）。"""

    def __init__(
        self,
        summary_one_line: str,
        value_score: int,
        model_alias: str,
    ) -> None:
        self.summary_one_line = summary_one_line
        self.value_score = value_score
        self.model_alias = model_alias

    @classmethod
    def from_model(cls, m) -> "EventAnalysisResultView":
        return cls(
            summary_one_line=m.summary_one_line,
            value_score=m.value_score,
            model_alias=m.model_alias,
        )

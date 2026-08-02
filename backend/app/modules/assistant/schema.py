"""assistant DTO。字段名对外一律 camelCase（CamelModel 统一处理）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.core.schema import CamelModel
from app.modules.assistant.enums import Feedback, MessageRole, MessageStatus

# ----------------------------------------------------------------- 请求


class ThreadCreateRequest(CamelModel):
    """POST /events/{id}/assistant/threads（空 body 也行；当前前端不传字段）。"""

    title: str | None = Field(default=None, max_length=200)


class MessageCreateRequest(CamelModel):
    """POST /assistant/threads/{id}/messages"""

    # 不在 Pydantic 层加 max_length：让 service 层抛 QuestionTooLongError → 400
    # 而不是 Pydantic 自动的 422（不符合 SPEC「400 QUESTION_TOO_LONG」）
    question: str | None = Field(default=None)
    quick_question_key: str | None = Field(default=None, max_length=64)

    @field_validator("question")
    @classmethod
    def _strip_question(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class FeedbackRequest(CamelModel):
    """POST /assistant/messages/{id}/feedback"""

    feedback: Feedback | None = None  # null = 取消


# ----------------------------------------------------------------- 响应


class ThreadSummary(CamelModel):
    """thread 列表项（轻量）。"""

    id: int
    title: str
    message_count: int
    last_message_at: datetime | None = None
    created_at: datetime


class ThreadCreateResponse(CamelModel):
    """POST thread 响应（仅含 id + 初始 title）。"""

    id: int
    title: str
    message_count: int


class CitationItem(CamelModel):
    """ASSISTANT 消息引用的来源文章。"""

    index: int  # [1] [2] 里的数字
    article_id: int
    title: str
    url: str
    source_name: str


class MessageResponse(CamelModel):
    """单条消息全字段。USER 消息 citations/cost 永远为空/0。"""

    id: int
    role: MessageRole
    content: str
    quick_question_key: str | None = None
    citations: list[CitationItem] = Field(default_factory=list)
    model_alias: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0
    latency_ms: int | None = None
    status: MessageStatus
    error_message: str | None = None
    feedback: Feedback | None = None
    created_at: datetime


class QuickQuestionItem(CamelModel):
    """快捷问题（从 system_config JSON 解析）。"""

    key: str
    label: str
    question: str


class QuickQuestionsResponse(CamelModel):
    items: list[QuickQuestionItem] = Field(default_factory=list)


# ----------------------------------------------------------------- 流式 SSE 事件 DTO


class StreamStartData(CamelModel):
    message_id: int
    model_alias: str | None = None


class StreamDeltaData(CamelModel):
    content: str


class StreamCitationsData(CamelModel):
    citations: list[CitationItem] = Field(default_factory=list)


class StreamDoneData(CamelModel):
    message_id: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0
    latency_ms: int = 0


class StreamErrorData(CamelModel):
    error_code: str
    detail: str
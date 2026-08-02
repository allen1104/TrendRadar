"""assistant 业务编排层。

业务流程（SPEC-assistant.md）：
  ① 上下文构造：event 标题 + event_analysis + 来源文章（带编号）+ 历史 + 当前问题
  ② 三级裁剪：总 token ≤ assistant_max_context_tokens（默认 24000）
  ③ LLM 流式生成：start 事件落库 STREAMING → delta 逐块更新 → 解析 citations → DONE
  ④ 引用解析：从全文提取 `[n]` 标注，越界丢弃，重复去重
  ⑤ 三重限流：用户级 / 会话轮数 / 会话成本
  ⑥ ai_call_log 自动记账（target_type=EVENT, target_id=event_id）
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RateLimitError
from app.core.redis import redis_client
from app.modules.admin.service import ConfigService
from app.modules.ai.enums import CallStatus, TaskKey
from app.modules.ai.gateway.gateway import LLMGateway
from app.modules.ai.gateway.types import LLMRequest
from app.modules.ai.model import AICallLog, AIModel, PromptTemplate
from app.modules.assistant.enums import Feedback, MessageRole, MessageStatus
from app.modules.assistant.exceptions import (
    EventNotAnalyzedError,
    MessageNotFoundError,
    NotAssistantMessageError,
    QuestionRequiredError,
    QuestionTooLongError,
    ThreadCostLimitExceededError,
    ThreadNotFoundError,
    ThreadTurnLimitExceededError,
)
from app.modules.assistant.model import AssistantMessage, AssistantThread
from app.modules.assistant.repository import (
    AssistantMessageRepository,
    AssistantThreadRepository,
)
from app.modules.assistant.schema import (
    CitationItem,
    QuickQuestionItem,
)

log = structlog.get_logger()

THREAD_TURN_LIMIT = 30  # 单会话 ASSISTANT 消息最多 30 轮（SPEC §业务规则）
USER_RATE_LIMIT_KEY_PREFIX = "assistant:user_rate"
USER_RATE_LIMIT_WINDOW = 3600  # 1 小时

# 上下文裁剪（SPEC §上下文构造）
CONTEXT_MAX_TOKENS_DEFAULT = 24000
ARTICLE_TRIM_STEPS = (2000, 1000, 500)
ARTICLE_KEEP_MAX = 5
HISTORY_KEEP_FIRST = 1
HISTORY_KEEP_RECENT = 4

# 引用 [n] 解析
_CITATION_RE = re.compile(r"\[(\d+)\]")


# ============================================================ 纯函数


def _truncate(s: str, limit: int) -> str:
    """按字符截断（粗略对应 token）。"""
    if not s:
        return ""
    return s if len(s) <= limit else s[:limit]


def estimate_tokens(s: str) -> int:
    """极简 token 估算：英文 4 字符 / token，中文 1.5 字符 / token。
    不要求精度，只用来裁剪。
    """
    if not s:
        return 0
    ascii_chars = sum(1 for c in s if ord(c) < 128)
    cjk_chars = len(s) - ascii_chars
    return int(ascii_chars / 4 + cjk_chars / 1.5)


def trim_article_content(content: str, step: int) -> str:
    return _truncate(content or "", step)


def select_top_articles(
    articles: list[dict[str, Any]], keep: int
) -> list[dict[str, Any]]:
    """按 source_name 权重 + content 长度挑前 keep 篇。
    优先级：source.weight 高的（plugin 默认 8-9）优先，正文长的优先。
    """
    if len(articles) <= keep:
        return articles

    def _score(a: dict[str, Any]) -> tuple[int, int]:
        # tuple 是 (weight, length) — Python 按字典序比较，正好满足"权重优先 + 同权取更长"
        return (int(a.get("source_weight") or 0), len(a.get("content") or ""))

    return sorted(articles, key=_score, reverse=True)[:keep]


def trim_history(
    history: list[dict[str, Any]],
    *,
    keep_first: int = HISTORY_KEEP_FIRST,
    keep_recent: int = HISTORY_KEEP_RECENT,
) -> list[dict[str, Any]]:
    """压缩历史：保留首轮 + 最近 N 轮。"""
    if len(history) <= keep_first + keep_recent:
        return history
    return history[:keep_first] + history[-keep_recent:]


def build_context(
    *,
    event_title: str,
    event_summary: str,
    articles: list[dict[str, Any]],
    history: list[dict[str, Any]],
    question: str,
    max_tokens: int = CONTEXT_MAX_TOKENS_DEFAULT,
) -> dict[str, Any]:
    """三级裁剪构造 prompt 变量。

    articles 元素 dict：{index, title, source_name, url, content, lang, published_at}
    history 元素 dict：{role, content}

    超出 max_tokens 时按 SPEC §上下文构造顺序降级：
      1. 缩短每篇 content（2000 → 1000 → 500）
      2. 只保留权重最高的 5 篇
      3. 压缩历史（首轮 + 最近 4 轮）
    """
    # 步骤 1：先按最长正文逐级缩短
    trimmed_articles = [dict(a) for a in articles]
    for step in ARTICLE_TRIM_STEPS:
        total = (
            estimate_tokens(event_title)
            + estimate_tokens(event_summary)
            + estimate_tokens(question)
        )
        for a in trimmed_articles:
            total += estimate_tokens(a.get("content") or "")
            total += estimate_tokens(a.get("title") or "")
        for a in history:
            total += estimate_tokens(a.get("content") or "")
        if total <= max_tokens:
            return {
                "eventTitle": event_title,
                "eventSummary": event_summary,
                "articles": [
                    {
                        "index": a["index"],
                        "title": a["title"],
                        "source_name": a.get("source_name", ""),
                        "url": a.get("url", ""),
                        "content": a.get("content") or "",
                    }
                    for a in trimmed_articles
                ],
                "history": history,
                "question": question,
            }
        for a in trimmed_articles:
            a["content"] = trim_article_content(a.get("content") or "", step)

    # 步骤 2：只保留权重最高的 5 篇
    trimmed_articles = select_top_articles(trimmed_articles, ARTICLE_KEEP_MAX)
    total = (
        estimate_tokens(event_title)
        + estimate_tokens(event_summary)
        + estimate_tokens(question)
    )
    for a in trimmed_articles:
        total += estimate_tokens(a.get("content") or "") + estimate_tokens(a.get("title") or "")
    for a in history:
        total += estimate_tokens(a.get("content") or "")
    if total <= max_tokens:
        return {
            "eventTitle": event_title,
            "eventSummary": event_summary,
            "articles": [
                {
                    "index": a["index"],
                    "title": a["title"],
                    "source_name": a.get("source_name", ""),
                    "url": a.get("url", ""),
                    "content": a.get("content") or "",
                }
                for a in trimmed_articles
            ],
            "history": history,
            "question": question,
        }

    # 步骤 3：压缩历史
    history = trim_history(history)
    return {
        "eventTitle": event_title,
        "eventSummary": event_summary,
        "articles": [
            {
                "index": a["index"],
                "title": a["title"],
                "source_name": a.get("source_name", ""),
                "url": a.get("url", ""),
                "content": a.get("content") or "",
            }
            for a in trimmed_articles
        ],
        "history": history,
        "question": question,
    }


def parse_citations(
    content: str, articles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """从 AI 输出的全文中提取 `[n]` 标注，转换为 citations 数组。
    越界编号（如 [9] 但只有 5 篇）直接丢弃；重复编号去重。

    articles 元素需含 {index, article_id, title, url, source_name}
    """
    if not content or not articles:
        return []
    max_index = max((int(a["index"]) for a in articles), default=0)
    if max_index <= 0:
        return []
    seen: set[int] = set()
    by_index: dict[int, dict[str, Any]] = {
        int(a["index"]): a for a in articles if "index" in a
    }
    out: list[dict[str, Any]] = []
    for m in _CITATION_RE.finditer(content):
        n = int(m.group(1))
        if n <= 0 or n > max_index or n in seen:
            continue
        a = by_index.get(n)
        if a is None:
            continue
        seen.add(n)
        out.append(
            {
                "index": n,
                "article_id": int(a["article_id"]),
                "title": a.get("title") or "",
                "url": a.get("url") or "",
                "source_name": a.get("source_name") or "",
            }
        )
    return out


def parse_quick_questions(raw: Any) -> list[QuickQuestionItem]:
    """从 system_config.assistant_quick_questions（JSON 数组）解析为 DTO。
    格式：[{key, label, question}, ...]
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[QuickQuestionItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        k = item.get("key")
        lbl = item.get("label")
        q = item.get("question")
        if not isinstance(k, str) or not isinstance(lbl, str) or not isinstance(q, str):
            continue
        if not k.strip() or not q.strip():
            continue
        out.append(QuickQuestionItem(key=k, label=lbl, question=q))
    return out


# ============================================================ Service


class AssistantService:
    """assistant 业务编排。

    流式调用约定：
      send_message / regenerate_message 是 async generator（不返回响应对象），
      由 api 层包成 StreamingResponse。生成器内部自己维护 AsyncSession 生命周期
      （使用 AsyncSessionLocal 直接开 session，不依赖 FastAPI get_db，因为
      StreamingResponse 已经返回响应头，request 依赖的 session 可能被关闭）。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.thread_repo = AssistantThreadRepository(session)
        self.message_repo = AssistantMessageRepository(session)

    # ============================================================ 列表

    async def list_threads(
        self, user_id: int, event_id: int
    ) -> list[dict[str, Any]]:
        rows = await self.thread_repo.list_for_user_event(user_id, event_id)
        return [
            {
                "id": t.id,
                "title": t.title,
                "message_count": t.message_count,
                "last_message_at": t.last_message_at,
                "created_at": t.created_at,
            }
            for t in rows
        ]

    async def list_messages(
        self, user_id: int, thread_id: int
    ) -> list[dict[str, Any]]:
        thread = await self.thread_repo.get_for_user(user_id, thread_id)
        if thread is None:
            raise ThreadNotFoundError
        rows = await self.message_repo.list_for_thread(thread_id)
        return [_message_to_dict(m) for m in rows]

    async def get_quick_questions(self) -> list[QuickQuestionItem]:
        """读 system_config.assistant_quick_questions。"""
        cfg = ConfigService(self.session)
        raw = await cfg.get("assistant_quick_questions", [])
        return parse_quick_questions(raw)

    # ============================================================ thread CRUD

    async def create_thread(
        self, user_id: int, event_id: int, title: str | None = None
    ) -> AssistantThread:
        """创建空 thread（不发消息）。event 必须 ANALYZED。"""
        await self._ensure_event_analyzed(event_id)
        init_title = title or "新对话"
        t = await self.thread_repo.create(
            user_id=user_id,
            event_id=event_id,
            title=init_title,
            message_count=0,
            total_cost_usd=0,
            last_message_at=None,
        )
        await self.session.commit()
        return t

    async def delete_thread(self, user_id: int, thread_id: int) -> None:
        thread = await self.thread_repo.get_for_user(user_id, thread_id)
        if thread is None:
            raise ThreadNotFoundError
        await self.thread_repo.soft_delete_cascade(thread_id)
        await self.session.commit()

    # ============================================================ 反馈

    async def set_feedback(
        self, user_id: int, message_id: int, feedback: Feedback | None
    ) -> None:
        msg = await self.message_repo.get(message_id)
        if msg is None:
            raise MessageNotFoundError
        # 验证 thread 属于该 user
        thread = await self.thread_repo.get_for_user(user_id, msg.thread_id)
        if thread is None:
            raise MessageNotFoundError
        if msg.role != MessageRole.ASSISTANT.value:
            raise NotAssistantMessageError
        await self.message_repo.set_feedback(message_id, feedback.value if feedback else None)
        await self.session.commit()

    # ============================================================ 流式生成

    async def stream_message(
        self,
        *,
        user_id: int,
        thread_id: int,
        question: str | None,
        quick_question_key: str | None,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式生成回复。返回 SSE 事件字典：
          {"event": "start", "data": {...}}
          {"event": "delta", "data": {...}}
          {"event": "citations", "data": {...}}
          {"event": "done", "data": {...}}
          {"event": "error", "data": {...}}
        """
        thread = await self.thread_repo.get_for_user(user_id, thread_id)
        if thread is None:
            raise ThreadNotFoundError

        # 1. 解析最终问题（quick_question_key 优先回查）
        resolved_question = await self._resolve_question(question, quick_question_key)

        # 2. 校验：长度 / 事件分析状态 / 会话轮数 / 会话成本
        if len(resolved_question) > 1000:
            raise QuestionTooLongError
        await self._ensure_event_analyzed(thread.event_id)

        # 3. 会话轮数上限
        turns = await self.message_repo.count_assistant_turns(thread_id)
        if turns >= THREAD_TURN_LIMIT:
            raise ThreadTurnLimitExceededError(
                extra={"turnLimit": THREAD_TURN_LIMIT, "turns": turns}
            )

        # 4. 会话成本上限
        cost_limit = float(
            await ConfigService(self.session).get(
                "assistant_thread_cost_limit_usd", 0.5
            )
        )
        if float(thread.total_cost_usd or 0) >= cost_limit:
            raise ThreadCostLimitExceededError(
                extra={"costLimitUsd": cost_limit, "usedUsd": float(thread.total_cost_usd)}
            )

        # 5. 用户限流（滑动窗口；命中 Redis 失败降级放行）
        await self._check_user_rate_limit(user_id)

        # 6. 写 USER message + 创建 STREAMING ASSISTANT message
        user_msg = await self.message_repo.create(
            thread_id=thread_id,
            role=MessageRole.USER.value,
            content=resolved_question,
            quick_question_key=quick_question_key,
            status=MessageStatus.DONE.value,
        )
        assistant_msg = await self.message_repo.create(
            thread_id=thread_id,
            role=MessageRole.ASSISTANT.value,
            content="",
            quick_question_key=quick_question_key,
            citations=[],
            model_alias=None,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0,
            latency_ms=None,
            status=MessageStatus.STREAMING.value,
        )
        await self.session.commit()
        await self.session.refresh(user_msg)
        await self.session.refresh(assistant_msg)

        # 7. 组装上下文
        event_ctx = await self._load_event_context(thread.event_id)
        history = await self._load_history(thread_id, limit=10)
        max_tokens = int(
            await ConfigService(self.session).get(
                "assistant_max_context_tokens", CONTEXT_MAX_TOKENS_DEFAULT
            )
        )
        variables = build_context(
            event_title=event_ctx["title"],
            event_summary=event_ctx["summary"],
            articles=event_ctx["articles"],
            history=history,
            question=resolved_question,
            max_tokens=max_tokens,
        )

        # 8. start 事件（携带 messageId + modelAlias）
        prompt_alias = await self._get_active_model_alias()
        yield {
            "event": "start",
            "data": {
                "messageId": assistant_msg.id,
                "modelAlias": prompt_alias,
            },
        }

        # 9. 流式生成
        full_content = ""
        last_flush_len = 0
        last_flush_at = datetime.now(UTC).timestamp()
        prompt_tokens = 0
        completion_tokens = 0
        cost_usd = 0.0
        latency_ms = 0
        model_alias_used: str | None = prompt_alias
        error_msg: str | None = None
        start_ts = datetime.now(UTC).timestamp()

        try:
            # 9.1 拿到 prompt + model + provider（复用 gateway 内部方法）
            gateway = LLMGateway(self.session)
            prompt = await gateway._get_active_prompt(TaskKey.ASSISTANT_QA.value)
            chain = await gateway._build_chain(prompt, None)
            primary_alias = chain[0]
            model = await gateway._get_model_by_alias(primary_alias)
            provider = await gateway._build_provider(model.provider)
            model_alias_used = model.alias

            # 9.2 构造请求
            rendered_system = _render(prompt.system_prompt, variables)
            rendered_user = _render(prompt.user_prompt, variables)
            messages = [
                {"role": "system", "content": rendered_system},
                {"role": "user", "content": rendered_user},
            ]
            request = LLMRequest(
                messages=messages,
                model=model.model_name,
                temperature=float(prompt.temperature or 0.3),
                max_tokens=prompt.max_tokens,
                response_schema=None,  # 自由文本（非结构化）
                supports_json_schema=False,
            )

            # 9.3 流式遍历
            async for delta in provider.stream_chat(request):
                if not delta:
                    continue
                if is_disconnected is not None and await is_disconnected():
                    log.info(
                        "assistant.stream.client_disconnected",
                        message_id=assistant_msg.id,
                        partial_len=len(full_content),
                    )
                    error_msg = "client disconnected"
                    break
                full_content += delta
                yield {"event": "delta", "data": {"content": delta}}

                # 每 200 字符或 2 秒 flush 一次（减少 IO）
                now = datetime.now(UTC).timestamp()
                if (
                    len(full_content) - last_flush_len >= 200
                    or now - last_flush_at >= 2
                ):
                    try:
                        await self.message_repo.update_content_incremental(
                            assistant_msg.id, content=full_content
                        )
                        await self.session.commit()
                    except Exception as exc:
                        log.warning("assistant.flush_failed", error=str(exc))
                    last_flush_len = len(full_content)
                    last_flush_at = now

            # 9.4 完成：解析 citations + 写终态
            citations = parse_citations(full_content, variables["articles"])
            citations_dicts = citations  # 已是 dict 列表
            # streaming 下 token 数来自 provider 最后一次 chunk
            # （如果有 stream_options=include_usage）；否则 0，不阻塞主流程
            prompt_tokens = getattr(provider, "_last_prompt_tokens", 0) or 0
            completion_tokens = getattr(provider, "_last_completion_tokens", 0) or 0
            latency_ms = int((datetime.now(UTC).timestamp() - start_ts) * 1000)
            cost_usd = (
                float(model.price_input_per_1m or 0) * prompt_tokens / 1e6
                + float(model.price_output_per_1m or 0) * completion_tokens / 1e6
            )

            # 客户端断连也视作 DONE（已保存部分）；唯一 FAILED 走下方 except
            final_status = MessageStatus.DONE.value

            await self.message_repo.update_content_incremental(
                assistant_msg.id,
                content=full_content,
                citations=citations_dicts,
                status=final_status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                model_alias=model_alias_used,
                error_message=error_msg,
            )

            # 9.5 更新 thread（title / message_count / total_cost / last_message_at）
            new_title = thread.title if thread.title != "新对话" else resolved_question[:50]
            await self.thread_repo.touch(
                thread_id,
                title=new_title if thread.title == "新对话" else None,
                message_count_delta=2,  # USER + ASSISTANT 各一条
                cost_delta=cost_usd,
                last_message_at=datetime.now(UTC),
            )
            await self.session.commit()

            # 9.6 citations 事件（紧跟 done 之前）
            if citations_dicts:
                yield {
                    "event": "citations",
                    "data": {"citations": citations_dicts},
                }

            yield {
                "event": "done",
                "data": {
                    "messageId": assistant_msg.id,
                    "promptTokens": prompt_tokens,
                    "completionTokens": completion_tokens,
                    "costUsd": round(cost_usd, 6),
                    "latencyMs": latency_ms,
                },
            }

            # 9.7 写 ai_call_log（写失败不影响主流程）
            await self._log_ai_call(
                model_alias=model_alias_used or "unknown",
                prompt_version=prompt.version,
                event_id=thread.event_id,
                user_id=user_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                status=CallStatus.SUCCESS.value,
            )
        except Exception as exc:
            log.exception("assistant.stream.error", message_id=assistant_msg.id, error=str(exc))
            try:
                await self.message_repo.update_content_incremental(
                    assistant_msg.id,
                    content=full_content,
                    status=MessageStatus.FAILED.value,
                    error_message=str(exc)[:500],
                    latency_ms=int((datetime.now(UTC).timestamp() - start_ts) * 1000),
                )
                await self.session.commit()
            except Exception:
                try:  # noqa: SIM105
                    await self.session.rollback()
                except Exception:  # noqa: S110
                    pass
            yield {
                "event": "error",
                "data": {
                    "errorCode": "LLM_UNAVAILABLE",
                    "detail": f"生成失败：{exc}"[:200],
                },
            }

    async def regenerate_message(
        self,
        *,
        user_id: int,
        message_id: int,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """删除原 ASSISTANT 消息，按相同上下文重新生成。"""
        msg = await self.message_repo.get(message_id)
        if msg is None:
            raise MessageNotFoundError
        if msg.role != MessageRole.ASSISTANT.value:
            raise NotAssistantMessageError
        thread = await self.thread_repo.get_for_user(user_id, msg.thread_id)
        if thread is None:
            raise ThreadNotFoundError
        # 删除原 message；thread cost 减去原 cost
        await self.message_repo.soft_delete_id(message_id)
        await self.thread_repo.touch(
            thread.id,
            message_count_delta=-1,
            cost_delta=-float(msg.cost_usd or 0),
            last_message_at=datetime.now(UTC),
        )
        await self.session.commit()
        # 找到该 thread 中最近一条 USER 消息
        history_msgs = await self.message_repo.list_for_thread(thread.id)
        user_msgs = [
            m for m in history_msgs if m.role == MessageRole.USER.value and not m.is_deleted
        ]
        if not user_msgs:
            raise NotAssistantMessageError("找不到原问题")
        last_user = user_msgs[-1]
        # 走 send 路径
        async for ev in self.stream_message(
            user_id=user_id,
            thread_id=thread.id,
            question=last_user.content,
            quick_question_key=last_user.quick_question_key,
            is_disconnected=is_disconnected,
        ):
            yield ev

    # ============================================================ 内部

    async def _resolve_question(
        self, question: str | None, quick_question_key: str | None
    ) -> str:
        """quick_question_key 命中时回查配置；否则用 question。
        都为空 → QuestionRequiredError。
        """
        if question and question.strip():
            return question.strip()
        if quick_question_key:
            items = await self.get_quick_questions()
            for q in items:
                if q.key == quick_question_key:
                    return q.question
        raise QuestionRequiredError

    async def _ensure_event_analyzed(self, event_id: int) -> None:
        from app.modules.pipeline.enums import EventStatus
        from app.modules.pipeline.model import Event

        ev = (
            await self.session.execute(
                select(Event).where(Event.id == event_id, Event.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if ev is None:
            raise EventNotAnalyzedError("事件不存在")
        if ev.status != EventStatus.ANALYZED.value:
            raise EventNotAnalyzedError(
                f"事件当前状态 {ev.status}，需 ANALYZED"
            )

    async def _load_event_context(self, event_id: int) -> dict[str, Any]:
        """加载 event + 所有 article + event_analysis 的 event_analysis 信息，
        转成 articles 列表（含 source_name）。"""
        from sqlalchemy import select as _select

        from app.modules.ai.model import EventAnalysis
        from app.modules.pipeline.model import Article, Event, EventArticle
        from app.modules.source.model import Source

        ev = (
            await self.session.execute(
                select(Event).where(Event.id == event_id, Event.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if ev is None:
            return {"title": "", "summary": "", "articles": []}

        analysis = (
            await self.session.execute(
                select(EventAnalysis).where(
                    EventAnalysis.event_id == event_id,
                    EventAnalysis.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()

        summary_parts: list[str] = []
        if analysis is not None:
            if analysis.summary:
                summary_parts.append(analysis.summary)
            if analysis.key_points:
                summary_parts.append(
                    "核心观点：\n" + "\n".join(f"- {p}" for p in (analysis.key_points or [])[:5])
                )
            if analysis.innovations:
                summary_parts.append(
                    "创新点：\n" + "\n".join(f"- {p}" for p in (analysis.innovations or [])[:5])
                )
        summary_text = "\n\n".join(summary_parts) or (ev.summary_one_line or "")

        rows = (
            (
                await self.session.execute(
                    _select(Article, EventArticle, Source)
                    .join(EventArticle, EventArticle.article_id == Article.id)
                    .join(Source, Source.id == Article.source_id)
                    .where(
                        EventArticle.event_id == event_id,
                        EventArticle.is_deleted.is_(False),
                        Article.is_deleted.is_(False),
                        Source.is_deleted.is_(False),
                    )
                    .order_by(EventArticle.is_primary.desc(), Article.published_at.asc())
                    .limit(15)
                )
            )
            .all()
        )

        articles: list[dict[str, Any]] = []
        for idx, (art, ea, src) in enumerate(rows, start=1):
            content = (art.content or "")[:2000]
            articles.append(
                {
                    "index": idx,
                    "title": art.title,
                    "source_name": src.name,
                    "url": art.url,
                    "content": content,
                    "source_weight": int(src.weight or 0),
                    "lang": art.lang,
                    "published_at": art.published_at.isoformat() if art.published_at else "",
                    "is_primary": bool(ea.is_primary),
                }
            )
        return {
            "title": ev.title,
            "summary": summary_text,
            "articles": articles,
        }

    async def _load_history(
        self, thread_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """取 thread 最近 limit 条消息，按 created_at 升序 → history 列表。
        跳过 STREAMING / FAILED 的 ASSISTANT 消息（避免半成品注入）。
        """
        rows = await self.message_repo.list_for_thread(thread_id)
        # list_for_thread 已经按 created_at asc 返回；只保留 status=DONE 的
        kept: list[AssistantMessage] = []
        for m in rows:
            if m.is_deleted:
                continue
            if m.role == MessageRole.ASSISTANT.value and m.status != MessageStatus.DONE.value:
                continue
            kept.append(m)
        recent = kept[-limit:]
        out: list[dict[str, Any]] = []
        for m in recent:
            role = "user" if m.role == MessageRole.USER.value else "assistant"
            out.append({"role": role, "content": m.content})
        return out

    async def _check_user_rate_limit(self, user_id: int) -> None:
        limit = int(
            await ConfigService(self.session).get("ai_user_rate_limit", 20)
        )
        try:
            key = f"{USER_RATE_LIMIT_KEY_PREFIX}:{user_id}"
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, USER_RATE_LIMIT_WINDOW)
            if count > limit:
                # 计算剩余 TTL → Retry-After
                ttl = await redis_client.ttl(key)
                retry_after = max(int(ttl or 0), 1)
                raise RateLimitError(
                    f"本小时 AI 调用已达 {limit} 次上限",
                    error_code="AI_RATE_LIMIT_EXCEEDED",
                    extra={"retryAfter": retry_after, "limit": limit},
                )
        except RateLimitError:
            raise
        except Exception as exc:
            # Redis 故障 → 降级放行（避免单点故障把整个问 AI 拖死）
            log.warning("assistant.ratelimit.redis_failed", error=str(exc))

    async def _get_active_model_alias(self) -> str | None:
        try:
            prompt = (
                await self.session.execute(
                    select(PromptTemplate).where(
                        PromptTemplate.is_active.is_(True),
                        PromptTemplate.is_deleted.is_(False),
                        PromptTemplate.task_key == TaskKey.ASSISTANT_QA.value,
                    )
                )
            ).scalar_one_or_none()
            if prompt is None:
                return None
            return prompt.model_alias or "default-chat"
        except Exception:
            return None

    async def _log_ai_call(
        self,
        *,
        model_alias: str,
        prompt_version: int | None,
        event_id: int,
        user_id: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        status: str,
    ) -> None:
        try:
            # 查 model_id（可能为 None）
            model_row = (
                await self.session.execute(
                    select(AIModel).where(
                        AIModel.alias == model_alias,
                        AIModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            log_row = AICallLog(
                trace_id="",  # ai_engine 写时用 uuid，这里简化
                task_key=TaskKey.ASSISTANT_QA.value,
                model_id=model_row.id if model_row else None,
                model_alias=model_alias,
                prompt_version=prompt_version,
                target_type="EVENT",
                target_id=event_id,
                user_id=user_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                status=status,
            )
            self.session.add(log_row)
            await self.session.commit()
        except Exception as exc:
            log.warning("assistant.ai_call_log_failed", error=str(exc))
            try:  # noqa: SIM105
                await self.session.rollback()
            except Exception:  # noqa: S110
                pass


def _render(template: str, variables: dict[str, Any]) -> str:
    """简单的 Jinja2 渲染（不依赖 ai.gateway 内部函数，避免循环 import）。"""
    from jinja2 import Environment, StrictUndefined, TemplateError

    # autoescape=False：assistant prompt 由 AI 渲染，prompt 内本身不该含 HTML
    env = Environment(undefined=StrictUndefined, autoescape=False)  # noqa: S701
    try:
        return env.from_string(template).render(**variables)
    except TemplateError as exc:
        raise ValueError(f"Prompt 渲染失败：{exc}") from exc


def _message_to_dict(m: AssistantMessage) -> dict[str, Any]:
    """DB model → dict（schema 在 api 层包成 MessageResponse）。"""
    citations = m.citations or []
    return {
        "id": m.id,
        "role": MessageRole(m.role),
        "content": m.content,
        "quick_question_key": m.quick_question_key,
        "citations": [CitationItem(**c) for c in citations] if citations else [],
        "model_alias": m.model_alias,
        "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens,
        "cost_usd": float(m.cost_usd or 0),
        "latency_ms": m.latency_ms,
        "status": MessageStatus(m.status),
        "error_message": m.error_message,
        "feedback": Feedback(m.feedback) if m.feedback else None,
        "created_at": m.created_at,
    }
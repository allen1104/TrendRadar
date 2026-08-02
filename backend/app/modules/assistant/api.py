"""assistant 路由。

8 端点按 SPEC-assistant.md「后端接口」：
  GET    /events/{event_id}/assistant/threads
  POST   /events/{event_id}/assistant/threads
  GET    /assistant/threads/{thread_id}/messages
  POST   /assistant/threads/{thread_id}/messages           (SSE)
  POST   /assistant/messages/{message_id}/regenerate       (SSE)
  POST   /assistant/messages/{message_id}/feedback
  DELETE /assistant/threads/{thread_id}
  GET    /assistant/quick-questions                        (GUEST)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession as _AS  # noqa: N814

from app.db.session import get_db
from app.modules.assistant.schema import (
    FeedbackRequest,
    MessageCreateRequest,
    MessageResponse,
    QuickQuestionsResponse,
    ThreadCreateRequest,
    ThreadCreateResponse,
    ThreadSummary,
)
from app.modules.assistant.service import AssistantService
from app.modules.auth.deps import CurrentUser, OptionalUser

DbSession = Annotated[_AS, Depends(get_db)]

# 路由前缀：
# - /events/{event_id}/assistant/threads 用 hotspot_router 风格的 path params
#   但单独挂一个 events_assistant_router 让 main.py 一次性 include
events_assistant_router = APIRouter(prefix="/events/{event_id}/assistant", tags=["assistant"])
threads_router = APIRouter(prefix="/assistant", tags=["assistant"])


# ----------------------------------------------------------------- SSE helper


async def _sse_stream(
    event_iter: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[str]:
    """把 service 层生成的 {event, data} 字典序列化为 SSE 字符串。

    SSE 协议：
      event: <event_name>\n
      data: <json_str>\n
      \n
    """
    async for item in event_iter:
        ev = item["event"]
        payload = item["data"]
        # data 必须是单行（不能含未转义的 \\n）；用 ensure_ascii=False 保留中文
        line = json.dumps(payload, ensure_ascii=False)
        yield f"event: {ev}\ndata: {line}\n\n"


async def _make_disconnect_check(request: Request) -> Callable[[], Awaitable[bool]]:
    """包装 request.is_disconnected 为异步回调，供 service 层在每次 yield 前探测。"""

    async def _check() -> bool:
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    return _check


# ----------------------------------------------------------------- threads on event


@events_assistant_router.get(
    "/threads",
    response_model=list[ThreadSummary],
    summary="当前用户在某事件下的会话列表（登录可见）",
)
async def list_threads(
    event_id: int,
    session: DbSession,
    user: CurrentUser,
) -> list[ThreadSummary]:
    rows = await AssistantService(session).list_threads(user.id, event_id)
    return [ThreadSummary(**r) for r in rows]


@events_assistant_router.post(
    "/threads",
    response_model=ThreadCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建空会话",
)
async def create_thread(
    event_id: int,
    session: DbSession,
    user: CurrentUser,
    payload: ThreadCreateRequest | None = None,
) -> ThreadCreateResponse:
    title = payload.title if payload else None
    t = await AssistantService(session).create_thread(user.id, event_id, title=title)
    return ThreadCreateResponse(
        id=t.id, title=t.title, message_count=t.message_count
    )


# ----------------------------------------------------------------- messages


@threads_router.get(
    "/threads/{thread_id}/messages",
    response_model=list[MessageResponse],
    summary="会话消息列表（需本人）",
)
async def list_messages(
    thread_id: int,
    session: DbSession,
    user: CurrentUser,
) -> list[MessageResponse]:
    rows = await AssistantService(session).list_messages(user.id, thread_id)
    return [MessageResponse(**r) for r in rows]


@threads_router.post(
    "/threads/{thread_id}/messages",
    summary="发送问题（SSE 流式）",
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "SSE 流：start / delta / citations / done / error",
        }
    },
)
async def send_message(
    thread_id: int,
    payload: MessageCreateRequest,
    session: DbSession,
    user: CurrentUser,
    request: Request,
) -> StreamingResponse:
    from app.modules.assistant.exceptions import QuestionTooLongError

    # 长度校验提到 api 层（避免在 StreamingResponse 中抛 → 无法改 status code）
    if payload.question and len(payload.question) > 1000:
        raise QuestionTooLongError

    svc = AssistantService(session)
    disconnect = await _make_disconnect_check(request)
    event_iter = svc.stream_message(
        user_id=user.id,
        thread_id=thread_id,
        question=payload.question,
        quick_question_key=payload.quick_question_key,
        is_disconnected=disconnect,
    )
    # SSE 强制 nginx 不要缓冲（前端 SPEC 要求）
    return StreamingResponse(
        _sse_stream(event_iter),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@threads_router.post(
    "/messages/{message_id}/regenerate",
    summary="重新生成（删除原 ASSISTANT 消息重发，SSE 流式）",
)
async def regenerate_message(
    message_id: int,
    session: DbSession,
    user: CurrentUser,
    request: Request,
) -> StreamingResponse:

    svc = AssistantService(session)
    disconnect = await _make_disconnect_check(request)
    event_iter = svc.regenerate_message(
        user_id=user.id, message_id=message_id, is_disconnected=disconnect
    )
    return StreamingResponse(
        _sse_stream(event_iter),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@threads_router.post(
    "/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="点赞/点踩/取消",
)
async def set_feedback(
    message_id: int,
    payload: FeedbackRequest,
    session: DbSession,
    user: CurrentUser,
) -> Response:
    await AssistantService(session).set_feedback(user.id, message_id, payload.feedback)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@threads_router.delete(
    "/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除会话（级联软删 message）",
)
async def delete_thread(
    thread_id: int,
    session: DbSession,
    user: CurrentUser,
) -> Response:
    await AssistantService(session).delete_thread(user.id, thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------- quick questions


@threads_router.get(
    "/quick-questions",
    response_model=QuickQuestionsResponse,
    summary="快捷问题列表（GUEST 可访问）",
)
async def get_quick_questions(
    session: DbSession,
    _user: OptionalUser,  # GUEST 也可读
) -> QuickQuestionsResponse:
    items = await AssistantService(session).get_quick_questions()
    return QuickQuestionsResponse(items=items)
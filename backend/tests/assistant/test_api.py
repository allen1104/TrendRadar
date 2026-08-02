"""assistant API 路由测试（FastAPI TestClient + 依赖覆盖）。

不连数据库 — service 用 MagicMock，session 用 AsyncMock 走通。
覆盖 SPEC「后端接口」的所有 8 个端点的 status code 路径。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.modules.assistant.api import (
    events_assistant_router,
    threads_router,
)
from app.modules.assistant.enums import MessageStatus
from app.modules.assistant.exceptions import (
    MessageNotFoundError,
    NotAssistantMessageError,
    ThreadNotFoundError,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ============================================================ 依赖覆盖


def _fake_user(user_id: int = 6) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.username = "tester"
    u.email = "t@e.com"
    u.role = "USER"
    return u


def _build_app(*, with_user: bool = True) -> FastAPI:
    """构造一个最小 app，只挂 assistant 路由，便于单独测试。"""
    from app.core.exceptions import AppException
    from fastapi.responses import JSONResponse

    app = FastAPI()
    app.include_router(events_assistant_router, prefix="/api/v1")
    app.include_router(threads_router, prefix="/api/v1")

    # 注册 AppException handler（与生产 app/main.py 一致）
    @app.exception_handler(AppException)
    async def _app_exc_handler(_request: Any, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "errorCode": exc.error_code, **exc.extra},
        )

    # 覆盖 get_db（直接给个 AsyncMock session 即可）
    fake_session = MagicMock()

    async def _override_db():
        yield fake_session

    from app.db.session import get_db

    app.dependency_overrides[get_db] = _override_db

    # 覆盖 get_current_user（注意不是覆盖 CurrentUser alias，必须 override 真实函数）
    from app.modules.auth.deps import get_current_user

    if with_user:

        async def _override_user():
            return _fake_user()

        app.dependency_overrides[get_current_user] = _override_user

    return app


# ============================================================ threads on event


class TestListThreads:
    def test_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        rows = [
            {
                "id": 1,
                "title": "t",
                "message_count": 0,
                "last_message_at": None,
                "created_at": "2026-08-02T00:00:00Z",
            }
        ]
        with patch(
            "app.modules.assistant.api.AssistantService.list_threads",
            AsyncMock(return_value=rows),
        ):
            r = client.get("/api/v1/events/88/assistant/threads")
        assert r.status_code == 200
        assert r.json()[0]["id"] == 1


class TestCreateThread:
    def test_201(self) -> None:
        app = _build_app()
        client = TestClient(app)
        fake_thread = MagicMock(id=1, title="新对话", message_count=0)
        with patch(
            "app.modules.assistant.api.AssistantService.create_thread",
            AsyncMock(return_value=fake_thread),
        ):
            r = client.post(
                "/api/v1/events/88/assistant/threads", json={"title": "t"}
            )
        assert r.status_code == 201
        assert r.json()["id"] == 1

    def test_event_not_analyzed_409(self) -> None:
        from app.modules.assistant.exceptions import EventNotAnalyzedError

        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.create_thread",
            AsyncMock(side_effect=EventNotAnalyzedError("待分析")),
        ):
            r = client.post("/api/v1/events/88/assistant/threads", json={})
        assert r.status_code == 409
        assert r.json()["errorCode"] == "EVENT_NOT_ANALYZED"


# ============================================================ messages


class TestListMessages:
    def test_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.list_messages",
            AsyncMock(
                return_value=[
                    {"id": 11, "role": "USER", "content": "q", "citations": [],
                     "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0,
                     "status": MessageStatus.DONE, "feedback": None,
                     "quick_question_key": None, "model_alias": None,
                     "latency_ms": None, "error_message": None, "created_at": "2026-08-02T00:00:00Z"},
                ]
            ),
        ):
            r = client.get("/api/v1/assistant/threads/1/messages")
        assert r.status_code == 200
        assert r.json()[0]["content"] == "q"

    def test_thread_not_found_404(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.list_messages",
            AsyncMock(side_effect=ThreadNotFoundError),
        ):
            r = client.get("/api/v1/assistant/threads/999/messages")
        assert r.status_code == 404
        assert r.json()["errorCode"] == "THREAD_NOT_FOUND"


class TestSendMessageValidation:
    def test_question_too_long_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        # api 层会在进入 StreamingResponse 之前先校验长度
        r = client.post(
            "/api/v1/assistant/threads/1/messages",
            json={"question": "x" * 1001},
        )
        assert r.status_code == 400
        assert r.json()["errorCode"] == "QUESTION_TOO_LONG"


# ============================================================ feedback


class TestSetFeedback:
    def test_204(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.set_feedback", AsyncMock()
        ):
            r = client.post(
                "/api/v1/assistant/messages/10/feedback", json={"feedback": "LIKE"}
            )
        assert r.status_code == 204

    def test_null_clears_feedback(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.set_feedback", AsyncMock()
        ) as mocked:
            r = client.post(
                "/api/v1/assistant/messages/10/feedback", json={"feedback": None}
            )
        assert r.status_code == 204
        # 验证 set_feedback 收到 None
        args, kwargs = mocked.call_args
        assert kwargs.get("feedback") is None or (len(args) >= 3 and args[2] is None)

    def test_not_assistant_message_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.set_feedback",
            AsyncMock(side_effect=NotAssistantMessageError),
        ):
            r = client.post(
                "/api/v1/assistant/messages/10/feedback", json={"feedback": "LIKE"}
            )
        assert r.status_code == 400
        assert r.json()["errorCode"] == "NOT_ASSISTANT_MESSAGE"

    def test_message_not_found_404(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.set_feedback",
            AsyncMock(side_effect=MessageNotFoundError),
        ):
            r = client.post(
                "/api/v1/assistant/messages/999/feedback", json={"feedback": "LIKE"}
            )
        assert r.status_code == 404


# ============================================================ delete thread


class TestDeleteThread:
    def test_204(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.delete_thread", AsyncMock()
        ):
            r = client.delete("/api/v1/assistant/threads/1")
        assert r.status_code == 204

    def test_404_cross_user(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.assistant.api.AssistantService.delete_thread",
            AsyncMock(side_effect=ThreadNotFoundError),
        ):
            r = client.delete("/api/v1/assistant/threads/999")
        assert r.status_code == 404


# ============================================================ quick questions


class TestGetQuickQuestions:
    def test_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        items = [
            {"key": "why", "label": "为什么", "question": "why?"},
        ]
        with patch(
            "app.modules.assistant.api.AssistantService.get_quick_questions",
            AsyncMock(return_value=items),
        ):
            r = client.get("/api/v1/assistant/quick-questions")
        assert r.status_code == 200
        assert r.json()["items"][0]["key"] == "why"


# ============================================================ SSE


class TestSendMessageSSE:
    def test_streams_5_event_types(self) -> None:
        """验证 POST messages 返回 text/event-stream，且 5 种事件齐全。"""
        app = _build_app()
        client = TestClient(app)

        async def fake_stream(*_args: Any, **_kwargs: Any):
            yield {"event": "start", "data": {"messageId": 100, "modelAlias": "default-chat"}}
            yield {"event": "delta", "data": {"content": "hello "}}
            yield {"event": "delta", "data": {"content": "world"}}
            yield {
                "event": "citations",
                "data": {"citations": [{"index": 1, "articleId": 88, "title": "t", "url": "u", "sourceName": "s"}]},
            }
            yield {
                "event": "done",
                "data": {"messageId": 100, "promptTokens": 10, "completionTokens": 5, "costUsd": 0.001, "latencyMs": 1000},
            }

        # 模拟 service.stream_message 返回 async generator
        from app.modules.assistant import api as api_mod

        class _Svc:
            def __init__(self, _s: Any) -> None:
                pass

            def stream_message(self, **_kw: Any) -> Any:
                return fake_stream()

        with patch.object(api_mod, "AssistantService", _Svc):
            r = client.post(
                "/api/v1/assistant/threads/1/messages",
                json={"question": "why"},
            )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        body = r.text
        assert "event: start" in body
        assert "event: delta" in body
        assert "event: citations" in body
        assert "event: done" in body


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
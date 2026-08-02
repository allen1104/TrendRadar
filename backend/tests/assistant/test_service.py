"""assistant 业务规则 + 纯函数测试。

覆盖：
- 纯函数：build_context 三级裁剪 / parse_citations 引用解析 / parse_quick_questions / trim_history
- 业务：thread CRUD / 跨用户 404 / feedback 越界 / regenerate / quick_questions 配置
- 限流：超 threshold → RateLimitError（mock Redis）

不连真实数据库 — service 接受 repo + session，repo 用 AsyncMock。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.exceptions import RateLimitError
from app.modules.assistant.enums import Feedback, MessageStatus
from app.modules.assistant.exceptions import (
    EventNotAnalyzedError,
    MessageNotFoundError,
    NotAssistantMessageError,
    QuestionRequiredError,
    ThreadCostLimitExceededError,
    ThreadNotFoundError,
    ThreadTurnLimitExceededError,
)
from app.modules.assistant.model import AssistantMessage, AssistantThread
from app.modules.assistant.schema import QuickQuestionItem
from app.modules.assistant.service import (
    AssistantService,
    build_context,
    estimate_tokens,
    parse_citations,
    parse_quick_questions,
    select_top_articles,
    trim_history,
)

# ============================================================ 纯函数


class TestEstimateTokens:
    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_ascii(self) -> None:
        # 'hello world' = 11 chars / 4 = 2.75 → 2
        assert estimate_tokens("hello world") == 2

    def test_cjk(self) -> None:
        # 中文 4 字符 / 1.5 ≈ 2.67 → 2
        s = "中文测试"
        assert estimate_tokens(s) == 2


class TestParseCitations:
    def test_basic(self) -> None:
        articles = [
            {"index": 1, "article_id": 100, "title": "A", "url": "u1", "source_name": "S1"},
            {"index": 2, "article_id": 101, "title": "B", "url": "u2", "source_name": "S2"},
            {"index": 3, "article_id": 102, "title": "C", "url": "u3", "source_name": "S3"},
        ]
        cits = parse_citations("see [1] [2][1] [3]", articles)
        # [1] 出现 2 次只取 1 次
        assert len(cits) == 3
        assert [c["index"] for c in cits] == [1, 2, 3]
        assert cits[0]["article_id"] == 100

    def test_out_of_range_dropped(self) -> None:
        articles = [{"index": i, "article_id": i * 10} for i in range(1, 4)]
        # [5] [9] 越界全丢
        assert parse_citations("[5] [9]", articles) == []

    def test_empty_content(self) -> None:
        articles = [{"index": 1, "article_id": 100}]
        assert parse_citations("", articles) == []
        assert parse_citations("no refs", articles) == []

    def test_empty_articles(self) -> None:
        assert parse_citations("see [1]", []) == []

    def test_no_citation_brackets(self) -> None:
        articles = [{"index": 1, "article_id": 100}]
        assert parse_citations("normal text without refs", articles) == []


class TestTrimHistory:
    def test_short_history_unchanged(self) -> None:
        hist = [{"role": "u", "content": "a"}] * 3
        assert trim_history(hist, keep_first=1, keep_recent=4) == hist

    def test_long_history_keeps_first_and_recent(self) -> None:
        hist = [{"role": "u", "content": str(i)} for i in range(20)]
        trimmed = trim_history(hist, keep_first=1, keep_recent=4)
        assert len(trimmed) == 5
        assert trimmed[0]["content"] == "0"
        assert trimmed[-1]["content"] == "19"

    def test_boundary(self) -> None:
        # 长度恰好 = keep_first + keep_recent → 原样
        hist = [{"role": "u", "content": str(i)} for i in range(5)]
        assert trim_history(hist, keep_first=1, keep_recent=4) == hist


class TestSelectTopArticles:
    def test_short_unchanged(self) -> None:
        articles = [{"index": 1, "source_weight": 5, "content": "a"}]
        assert select_top_articles(articles, 5) == articles

    def test_picks_top_by_weight_then_length(self) -> None:
        articles = [
            {"index": 1, "source_weight": 5, "content": "x" * 100},
            {"index": 2, "source_weight": 9, "content": "y" * 50},
            {"index": 3, "source_weight": 8, "content": "z" * 200},
            {"index": 4, "source_weight": 5, "content": "w" * 300},
        ]
        top = select_top_articles(articles, 2)
        # weight 9 (idx=2) 和 8 (idx=3) 胜出
        assert [a["index"] for a in top] == [2, 3]

    def test_same_weight_picks_longer(self) -> None:
        articles = [
            {"index": 1, "source_weight": 5, "content": "x" * 100},
            {"index": 2, "source_weight": 5, "content": "y" * 200},
        ]
        top = select_top_articles(articles, 1)
        assert top[0]["index"] == 2


class TestBuildContext:
    def _big_articles(self, n: int = 10, content_size: int = 10000) -> list[dict]:
        return [
            {
                "index": i + 1,
                "title": f"T{i}",
                "source_name": f"S{i}",
                "url": f"u{i}",
                "content": "x" * content_size,
                "source_weight": 5,
                "lang": "en",
            }
            for i in range(n)
        ]

    def test_step1_trims_content_to_500(self) -> None:
        """max_tokens=200，10 篇 10000 字 → step 1 全部截到 500，但保留 10 篇。"""
        articles = self._big_articles(10, 10000)
        ctx = build_context(
            event_title="EVT",
            event_summary="SUM",
            articles=articles,
            history=[{"role": "user", "content": "hi"}],
            question="why?",
            max_tokens=200,
        )
        # step 2 cap 5 篇（200 tokens 容纳不下 10×125=1250）
        assert len(ctx["articles"]) == 5
        assert all(len(a["content"]) <= 500 for a in ctx["articles"])

    def test_step2_caps_to_5_articles(self) -> None:
        """超 token 时按 weight + length 排序取前 5。"""
        articles = self._big_articles(10, 5000)
        ctx = build_context(
            event_title="EVT",
            event_summary="SUM",
            articles=articles,
            history=[{"role": "user", "content": "q"}],
            question="why?",
            max_tokens=500,
        )
        assert len(ctx["articles"]) <= 5

    def test_step3_trims_history(self) -> None:
        """极端：1 篇文章 + 20 条大 history → history 压缩。"""
        big_history = [{"role": "user", "content": "x" * 2000} for _ in range(20)]
        ctx = build_context(
            event_title="EVT",
            event_summary="SUM",
            articles=[
                {
                    "index": 1,
                    "title": "t",
                    "source_name": "s",
                    "url": "u",
                    "content": "x" * 5000,
                }
            ],
            history=big_history,
            question="q",
            max_tokens=200,
        )
        assert len(ctx["history"]) <= 5

    def test_no_trim_when_fits(self) -> None:
        ctx = build_context(
            event_title="EVT",
            event_summary="SUM",
            articles=[
                {"index": 1, "title": "t", "source_name": "s", "url": "u", "content": "small"}
            ],
            history=[{"role": "user", "content": "q"}],
            question="q",
            max_tokens=10000,
        )
        assert ctx["articles"][0]["content"] == "small"
        assert ctx["history"] == [{"role": "user", "content": "q"}]

    def test_articles_only_have_required_fields(self) -> None:
        ctx = build_context(
            event_title="EVT",
            event_summary="SUM",
            articles=[
                {
                    "index": 1,
                    "title": "t",
                    "source_name": "s",
                    "url": "u",
                    "content": "x",
                    "source_weight": 5,
                    "lang": "en",
                    "extra_field": "should_be_dropped",
                }
            ],
            history=[],
            question="q",
            max_tokens=10000,
        )
        # 不会传 extra 字段
        assert "extra_field" not in ctx["articles"][0]
        assert set(ctx["articles"][0].keys()) == {"index", "title", "source_name", "url", "content"}


class TestParseQuickQuestions:
    def test_json_string(self) -> None:
        raw = json.dumps(
            [
                {"key": "why", "label": "l1", "question": "q1"},
                {"key": "what", "label": "l2", "question": "q2"},
            ]
        )
        items = parse_quick_questions(raw)
        assert len(items) == 2
        assert items[0].key == "why"
        assert items[1].key == "what"

    def test_filter_invalid_items(self) -> None:
        raw = json.dumps(
            [
                {"key": "good", "label": "l", "question": "q"},
                {"key": "bad"},  # 缺 label/question
                {"key": "   ", "label": "x", "question": "y"},  # 空 key
                "not a dict",
                {"key": "k", "label": "l", "question": "   "},  # 空 question
            ]
        )
        items = parse_quick_questions(raw)
        assert len(items) == 1
        assert items[0].key == "good"

    def test_non_json_or_none(self) -> None:
        assert parse_quick_questions(None) == []
        assert parse_quick_questions("not json") == []
        assert parse_quick_questions({"k": "v"}) == []
        assert parse_quick_questions(123) == []


# ============================================================ 业务规则（mock repo）


def _thread(**kw) -> AssistantThread:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    defaults = dict(
        id=1, user_id=6, event_id=88, title="新对话",
        message_count=0, total_cost_usd=0, last_message_at=None,
        created_at=now, updated_at=now, is_deleted=False,
    )
    defaults.update(kw)
    return AssistantThread(**defaults)


def _msg(**kw) -> AssistantMessage:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    defaults = dict(
        id=10, thread_id=1, role="USER", content="q",
        quick_question_key=None, citations=[], model_alias=None,
        prompt_tokens=0, completion_tokens=0, cost_usd=0,
        latency_ms=None, status="DONE", error_message=None, feedback=None,
        created_at=now, updated_at=now, is_deleted=False,
    )
    defaults.update(kw)
    return AssistantMessage(**defaults)


def _mock_event(*, status_value: str = "ANALYZED") -> MagicMock:
    ev = MagicMock()
    ev.id = 88
    ev.title = "Test Event"
    ev.status = status_value
    ev.is_deleted = False
    return ev


def _service_with_repos() -> tuple[AssistantService, AsyncMock, AsyncMock]:
    session = AsyncMock()
    thread_repo = AsyncMock()
    message_repo = AsyncMock()
    svc = AssistantService(session)
    svc.thread_repo = thread_repo  # type: ignore[method-assign]
    svc.message_repo = message_repo  # type: ignore[method-assign]
    return svc, thread_repo, message_repo


class TestListThreads:
    async def test_returns_summaries(self) -> None:
        svc, thread_repo, _ = _service_with_repos()
        thread_repo.list_for_user_event.return_value = [_thread(id=1), _thread(id=2, title="t2")]
        rows = await svc.list_threads(user_id=6, event_id=88)
        assert len(rows) == 2
        assert rows[0]["id"] == 1
        assert rows[1]["title"] == "t2"


class TestListMessages:
    async def test_cross_user_404(self) -> None:
        svc, thread_repo, _ = _service_with_repos()
        thread_repo.get_for_user.return_value = None
        with pytest.raises(ThreadNotFoundError):
            await svc.list_messages(user_id=6, thread_id=999)

    async def test_returns_message_dicts(self) -> None:
        svc, thread_repo, message_repo = _service_with_repos()
        thread_repo.get_for_user.return_value = _thread()
        message_repo.list_for_thread.return_value = [
            _msg(id=11, role="USER", content="q"),
            _msg(id=12, role="ASSISTANT", content="a", status="DONE"),
        ]
        rows = await svc.list_messages(user_id=6, thread_id=1)
        assert len(rows) == 2
        assert rows[0]["content"] == "q"
        assert rows[1]["status"] == MessageStatus.DONE


class TestCreateThread:
    async def test_event_not_analyzed_409(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch(
            "app.modules.assistant.service.AssistantService._ensure_event_analyzed",
            AsyncMock(side_effect=EventNotAnalyzedError("待分析")),
        ), pytest.raises(EventNotAnalyzedError):
            await svc.create_thread(user_id=6, event_id=88)

    async def test_success(self) -> None:
        svc, thread_repo, _ = _service_with_repos()
        with patch(
            "app.modules.assistant.service.AssistantService._ensure_event_analyzed",
            AsyncMock(),
        ):
            thread_repo.create.return_value = _thread()
            t = await svc.create_thread(user_id=6, event_id=88)
            assert t.user_id == 6
            assert t.event_id == 88


class TestDeleteThread:
    async def test_cross_user_404(self) -> None:
        svc, thread_repo, _ = _service_with_repos()
        thread_repo.get_for_user.return_value = None
        with pytest.raises(ThreadNotFoundError):
            await svc.delete_thread(user_id=6, thread_id=999)

    async def test_cascade_soft_delete(self) -> None:
        svc, thread_repo, _ = _service_with_repos()
        thread_repo.get_for_user.return_value = _thread()
        thread_repo.soft_delete_cascade.return_value = 5
        await svc.delete_thread(user_id=6, thread_id=1)
        thread_repo.soft_delete_cascade.assert_awaited_once_with(1)


class TestSetFeedback:
    async def test_message_not_found(self) -> None:
        svc, _, message_repo = _service_with_repos()
        message_repo.get.return_value = None
        with pytest.raises(MessageNotFoundError):
            await svc.set_feedback(user_id=6, message_id=999, feedback=Feedback.LIKE)

    async def test_cross_user_404(self) -> None:
        svc, thread_repo, message_repo = _service_with_repos()
        message_repo.get.return_value = _msg(role="ASSISTANT")
        thread_repo.get_for_user.return_value = None
        with pytest.raises(MessageNotFoundError):
            await svc.set_feedback(user_id=6, message_id=10, feedback=Feedback.LIKE)

    async def test_user_message_rejected(self) -> None:
        svc, thread_repo, message_repo = _service_with_repos()
        message_repo.get.return_value = _msg(role="USER")
        thread_repo.get_for_user.return_value = _thread()
        with pytest.raises(NotAssistantMessageError):
            await svc.set_feedback(user_id=6, message_id=10, feedback=Feedback.LIKE)

    async def test_assistant_message_feedback_ok(self) -> None:
        svc, thread_repo, message_repo = _service_with_repos()
        message_repo.get.return_value = _msg(role="ASSISTANT")
        thread_repo.get_for_user.return_value = _thread()
        await svc.set_feedback(user_id=6, message_id=10, feedback=Feedback.LIKE)
        message_repo.set_feedback.assert_awaited_once_with(10, "LIKE")


class TestResolveQuestion:
    async def test_question_stripped(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch.object(svc, "get_quick_questions", AsyncMock(return_value=[])):
            q = await svc._resolve_question("  hello  ", None)
        assert q == "hello"

    async def test_quick_key_lookup(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch.object(
            svc,
            "get_quick_questions",
            AsyncMock(return_value=[QuickQuestionItem(key="why", label="l", question="why this?")]),
        ):
            q = await svc._resolve_question(None, "why")
        assert q == "why this?"

    async def test_quick_key_not_found_uses_question(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch.object(svc, "get_quick_questions", AsyncMock(return_value=[])):
            q = await svc._resolve_question("fallback q", "missing_key")
        assert q == "fallback q"

    async def test_empty_question_and_key_raises(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch.object(svc, "get_quick_questions", AsyncMock(return_value=[])):
            with pytest.raises(QuestionRequiredError):
                await svc._resolve_question(None, None)
        with patch.object(svc, "get_quick_questions", AsyncMock(return_value=[])):
            with pytest.raises(QuestionRequiredError):
                await svc._resolve_question("   ", None)


class TestStreamMessageGuards:
    """测试 stream_message 在各种前置校验失败时抛对应异常（不在流式过程）。"""

    async def test_thread_not_found_raises(self) -> None:
        svc, thread_repo, _ = _service_with_repos()
        thread_repo.get_for_user.return_value = None
        with pytest.raises(ThreadNotFoundError):
            async for _ in svc.stream_message(
                user_id=6, thread_id=999, question="q", quick_question_key=None
            ):
                pass

    async def test_question_too_long_raises(self) -> None:
        svc, thread_repo, _ = _service_with_repos()
        thread_repo.get_for_user.return_value = _thread()
        with pytest.raises(Exception):  # QuestionTooLongError
            async for _ in svc.stream_message(
                user_id=6, thread_id=1, question="x" * 1001, quick_question_key=None
            ):
                pass

    async def test_turn_limit_raises(self) -> None:
        svc, thread_repo, message_repo = _service_with_repos()
        thread_repo.get_for_user.return_value = _thread()
        message_repo.count_assistant_turns.return_value = 30  # 已达上限
        # cost_limit check 通过、rate_limit 通过 → 到 turn_limit
        with patch.object(svc, "_ensure_event_analyzed", AsyncMock()):
            with patch.object(svc, "_check_user_rate_limit", AsyncMock()):
                with pytest.raises(ThreadTurnLimitExceededError):
                    async for _ in svc.stream_message(
                        user_id=6, thread_id=1, question="q", quick_question_key=None
                    ):
                        pass

    async def test_cost_limit_raises(self) -> None:
        svc, thread_repo, message_repo = _service_with_repos()
        thread_repo.get_for_user.return_value = _thread(total_cost_usd=0.6)
        message_repo.count_assistant_turns.return_value = 0
        with patch.object(svc, "_ensure_event_analyzed", AsyncMock()):
            with patch.object(svc, "_check_user_rate_limit", AsyncMock()):
                with patch(
                    "app.modules.assistant.service.ConfigService.get",
                    AsyncMock(return_value=0.5),
                ):
                    with pytest.raises(ThreadCostLimitExceededError):
                        async for _ in svc.stream_message(
                            user_id=6, thread_id=1, question="q", quick_question_key=None
                        ):
                            pass


class TestUserRateLimit:
    async def test_first_call_passes(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch(
            "app.modules.assistant.service.redis_client.incr", AsyncMock(return_value=1)
        ), patch(
            "app.modules.assistant.service.redis_client.expire", AsyncMock()
        ), patch(
            "app.modules.assistant.service.ConfigService.get", AsyncMock(return_value=20)
        ):
            await svc._check_user_rate_limit(user_id=6)
            # OK 不抛

    async def test_over_limit_raises_with_retry_after(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch(
            "app.modules.assistant.service.redis_client.incr", AsyncMock(return_value=21)
        ), patch(
            "app.modules.assistant.service.redis_client.expire", AsyncMock()
        ), patch(
            "app.modules.assistant.service.redis_client.ttl", AsyncMock(return_value=1234)
        ), patch(
            "app.modules.assistant.service.ConfigService.get", AsyncMock(return_value=20)
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await svc._check_user_rate_limit(user_id=6)
            assert exc_info.value.extra["retryAfter"] == 1234
            assert exc_info.value.extra["limit"] == 20

    async def test_redis_failure_degrades_pass(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch(
            "app.modules.assistant.service.redis_client.incr",
            AsyncMock(side_effect=ConnectionError("redis down")),
        ), patch(
            "app.modules.assistant.service.ConfigService.get", AsyncMock(return_value=20)
        ):
            # 不抛，降级放行
            await svc._check_user_rate_limit(user_id=6)


class TestGetQuickQuestions:
    async def test_reads_from_config(self) -> None:
        svc, _, _ = _service_with_repos()
        cfg_data = [
            {"key": "why", "label": "l1", "question": "q1"},
        ]
        with patch(
            "app.modules.assistant.service.ConfigService.get",
            AsyncMock(return_value=cfg_data),
        ):
            items = await svc.get_quick_questions()
        assert len(items) == 1 and items[0].key == "why"

    async def test_empty_when_not_configured(self) -> None:
        svc, _, _ = _service_with_repos()
        with patch(
            "app.modules.assistant.service.ConfigService.get", AsyncMock(return_value=[])
        ):
            assert await svc.get_quick_questions() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
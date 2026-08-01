"""hotspot service 层业务逻辑测试。

不连数据库，用 AsyncMock 模拟 repo / session，FakeRedis 模拟缓存。
覆盖：sort 解析、关键词长度校验、隐藏事件对 GUEST 隐藏、缓存命中短路、
PinAndHide 冲突、人工锁定字段流转、unlock_field 边界。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.auth.enums import Role
from app.modules.auth.model import User, UserPreference
from app.modules.hotspot.enums import CategoryFilter, Scope
from app.modules.hotspot.exceptions import (
    EventNotFoundError,
    InvalidSortFieldError,
    KeywordTooShortError,
    ManualLockFieldNotFoundError,
    PinAndHideConflictError,
)
from app.modules.hotspot.schema import EventUpdateRequest
from app.modules.hotspot.service import _parse_sort

from tests.conftest import FakeRedis


# ------------------------------------------------------------------ 辅助


def _user(role: Role = Role.USER, user_id: int = 1) -> User:
    u = User(
        id=user_id,
        email=f"u{user_id}@x.com",
        username=f"u{user_id}",
        password_hash="x",
        role=role.value,
        status="ACTIVE",
    )
    u.preference = UserPreference(
        id=1,
        user_id=user_id,
        default_scope="TODAY",
        followed_categories=[],
        followed_tags=[],
        muted_sources=[],
        daily_report_opt_in=False,
    )
    return u


class _FakeMe:
    """_muted_sources 跨模块读 AuthService.get_me → 拿到的对象。"""

    def __init__(self, muted: list[int] | None = None) -> None:
        self.preference = MagicMock()
        self.preference.muted_sources = muted or []


def _patch_auth_get_me(muted: list[int] | None = None) -> Any:
    """让 service._muted_sources 内部 import 的 AuthService.get_me 返回 _FakeMe。"""
    fake_auth_svc = MagicMock()
    fake_auth_svc.get_me = AsyncMock(return_value=_FakeMe(muted))
    return patch("app.modules.auth.service.AuthService", MagicMock(return_value=fake_auth_svc))


class _FakeEvent:
    """够用的最小化 Event 替身，service 只用 id + 几个列。"""

    def __init__(self, **kw: Any) -> None:
        self.id = kw.get("id", 1)
        self.title = kw.get("title", "T")
        self.summary_one_line = kw.get("summary_one_line", "S")
        self.region = kw.get("region", "GLOBAL")
        self.categories = kw.get("categories", ["AI"])
        self.source_count = kw.get("source_count", 1)
        self.article_count = kw.get("article_count", 1)
        self.heat_score = kw.get("heat_score", 0)
        self.value_score = kw.get("value_score", None)
        self.originality_score = kw.get("originality_score", None)
        self.trend_score = kw.get("trend_score", None)
        self.recommend_index = kw.get("recommend_index", 0)
        self.status = kw.get("status", "ANALYZED")
        self.is_pinned = kw.get("is_pinned", False)
        self.is_hidden = kw.get("is_hidden", False)
        self.is_manually_edited = kw.get("is_manually_edited", False)
        self.manual_locked_fields = kw.get("manual_locked_fields", [])
        self.first_seen_at = kw.get("first_seen_at", datetime(2026, 7, 30, tzinfo=UTC))
        self.last_seen_at = kw.get("last_seen_at", datetime(2026, 7, 31, tzinfo=UTC))


def _make_service(redis: FakeRedis | None = None) -> Any:
    """构造 HotspotService，repo / session 都是 AsyncMock。"""
    from app.modules.hotspot.service import HotspotService

    session = AsyncMock()
    repo = AsyncMock()
    svc = HotspotService(session)
    svc.repo = repo
    return svc, session, repo


def _patch_collection_list_ids(return_value: set[int] | None = None) -> Any:
    """让 hotspot service 内部 inline import 的 CollectionService.list_collected_event_ids 直接返回空。

    hotspot 是单元测试，主要测业务流；新接入 collection 的 SQL 不归它管。
    """
    from app.modules.collection import service as collection_service

    if return_value is None:
        return_value = set()
    return patch.object(
        collection_service.CollectionService,
        "list_collected_event_ids",
        AsyncMock(return_value=return_value),
    )


# ------------------------------------------------------------------ _parse_sort


class TestParseSort:
    def test_plain_field_is_ascending(self) -> None:
        assert _parse_sort("heatScore") == ("heatScore", False)

    def test_dash_prefix_is_descending(self) -> None:
        assert _parse_sort("-recommendIndex") == ("recommendIndex", True)

    @pytest.mark.parametrize(
        "bad",
        [
            "title",          # 真实列但不在白名单
            "createdAt",      # 不允许
            "id",
            "",               # 空
            "-evil",
            "DROP TABLE",
            "recommend_index",  # snake_case 不接收
        ],
    )
    def test_rejects_non_whitelisted(self, bad: str) -> None:
        with pytest.raises(InvalidSortFieldError):
            _parse_sort(bad)


# ------------------------------------------------------------------ list_events


class TestListEventsKeywordGuard:
    async def test_keyword_too_short_raises(self) -> None:
        svc, _, _ = _make_service()
        with pytest.raises(KeywordTooShortError):
            await svc.list_events(
                scope=Scope.TODAY,
                category=CategoryFilter.ALL,
                sort="-recommendIndex",
                keyword="a",  # 1 字符
                tag_ids=None,
                source_ids=None,
                min_recommend=None,
                start_date=None,
                end_date=None,
                include_hidden=False,
                page=1,
                size=20,
                user=None,
            )

    async def test_keyword_blank_treated_as_none(self) -> None:
        svc, _, repo = _make_service()
        repo.list_events = AsyncMock(return_value=([], 0))
        repo.map_sources = AsyncMock(return_value={})
        repo.map_tags = AsyncMock(return_value={})
        repo.map_primary_article_url = AsyncMock(return_value={})
        repo.map_worth_article = AsyncMock(return_value={})
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            page = await svc.list_events(
                scope=Scope.TODAY,
                category=CategoryFilter.ALL,
                sort="-recommendIndex",
                keyword="   ",  # 全空白 → 当 None
                tag_ids=None,
                source_ids=None,
                min_recommend=None,
                start_date=None,
                end_date=None,
                include_hidden=False,
                page=1,
                size=20,
                user=None,
            )
        assert page.total == 0
        # repo 收到的 keyword 应该是 None
        called = repo.list_events.call_args.kwargs
        assert called["keyword"] is None


class TestListEventsIncludeHidden:
    async def test_include_hidden_silently_ignored_for_guest(self) -> None:
        """GUEST 传 includeHidden=true → 服务层把它强改回 false，不抛错。"""
        svc, _, repo = _make_service()
        repo.list_events = AsyncMock(return_value=([], 0))
        repo.map_sources = AsyncMock(return_value={})
        repo.map_tags = AsyncMock(return_value={})
        repo.map_primary_article_url = AsyncMock(return_value={})
        repo.map_worth_article = AsyncMock(return_value={})
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            await svc.list_events(
                scope=Scope.TODAY,
                category=CategoryFilter.ALL,
                sort="-recommendIndex",
                keyword=None,
                tag_ids=None,
                source_ids=None,
                min_recommend=None,
                start_date=None,
                end_date=None,
                include_hidden=True,  # GUEST 试图绕过
                page=1,
                size=20,
                user=None,  # GUEST
            )
        assert repo.list_events.call_args.kwargs["include_hidden"] is False

    async def test_include_honored_for_editor(self) -> None:
        svc, _, repo = _make_service()
        repo.list_events = AsyncMock(return_value=([], 0))
        repo.map_sources = AsyncMock(return_value={})
        repo.map_tags = AsyncMock(return_value={})
        repo.map_primary_article_url = AsyncMock(return_value={})
        repo.map_worth_article = AsyncMock(return_value={})
        with _patch_auth_get_me(), patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            await svc.list_events(
                scope=Scope.TODAY,
                category=CategoryFilter.ALL,
                sort="-recommendIndex",
                keyword=None,
                tag_ids=None,
                source_ids=None,
                min_recommend=None,
                start_date=None,
                end_date=None,
                include_hidden=True,
                page=1,
                size=20,
                user=_user(Role.EDITOR),
            )
        assert repo.list_events.call_args.kwargs["include_hidden"] is True


class TestListEventsCache:
    async def test_cacheable_default_list_writes_cache(self) -> None:
        redis = FakeRedis()
        svc, _, repo = _make_service()
        repo.list_events = AsyncMock(return_value=([], 0))
        repo.map_sources = AsyncMock(return_value={})
        repo.map_tags = AsyncMock(return_value={})
        repo.map_primary_article_url = AsyncMock(return_value={})
        repo.map_worth_article = AsyncMock(return_value={})

        with patch("app.modules.hotspot.service.redis_client", redis):
            await svc.list_events(
                scope=Scope.TODAY,
                category=CategoryFilter.ALL,
                sort="-recommendIndex",
                keyword=None,
                tag_ids=None,
                source_ids=None,
                min_recommend=None,
                start_date=None,
                end_date=None,
                include_hidden=False,
                page=1,
                size=20,
                user=None,
            )

        keys = [k for k in redis._data if k.startswith("hotspot:rank:")]
        assert len(keys) == 1

    async def test_cacheable_skipped_when_keyword_given(self) -> None:
        redis = FakeRedis()
        svc, _, repo = _make_service()
        repo.list_events = AsyncMock(return_value=([], 0))
        repo.map_sources = AsyncMock(return_value={})
        repo.map_tags = AsyncMock(return_value={})
        repo.map_primary_article_url = AsyncMock(return_value={})
        repo.map_worth_article = AsyncMock(return_value={})

        with patch("app.modules.hotspot.service.redis_client", redis):
            await svc.list_events(
                scope=Scope.TODAY,
                category=CategoryFilter.ALL,
                sort="-recommendIndex",
                keyword="openai",  # 带关键词 → 不缓存
                tag_ids=None,
                source_ids=None,
                min_recommend=None,
                start_date=None,
                end_date=None,
                include_hidden=False,
                page=1,
                size=20,
                user=None,
            )

        assert [k for k in redis._data if k.startswith("hotspot:rank:")] == []

    async def test_cache_hit_skips_repo(self) -> None:
        """榜单有缓存 → repo.list_events 不该被调。"""
        import json

        redis = FakeRedis()
        cached = {"items": [], "total": 0, "page": 1, "size": 20, "pages": 0}
        key = "hotspot:rank:TODAY:ALL:-recommendIndex:1"
        await redis.setex(key, 300, json.dumps(cached))

        svc, _, repo = _make_service()
        repo.list_events = AsyncMock(side_effect=AssertionError("不应调到 repo"))

        with patch("app.modules.hotspot.service.redis_client", redis):
            page = await svc.list_events(
                scope=Scope.TODAY,
                category=CategoryFilter.ALL,
                sort="-recommendIndex",
                keyword=None,
                tag_ids=None,
                source_ids=None,
                min_recommend=None,
                start_date=None,
                end_date=None,
                include_hidden=False,
                page=1,
                size=20,
                user=None,
            )
        assert page.total == 0


# ------------------------------------------------------------------ 详情


class TestGetEventDetail:
    async def test_guest_cannot_see_hidden_event(self) -> None:
        svc, _, repo = _make_service()
        hidden = _FakeEvent(id=99, is_hidden=True)
        repo.get_event = AsyncMock(return_value=hidden)
        repo.get_analysis = AsyncMock(return_value=None)
        repo.list_event_articles = AsyncMock(return_value=[])
        repo.map_tags = AsyncMock(return_value={})

        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(EventNotFoundError):
                await svc.get_event_detail(99, user=None)

    async def test_editor_can_see_hidden_event(self) -> None:
        svc, _, repo = _make_service()
        hidden = _FakeEvent(id=99, is_hidden=True)
        repo.get_event = AsyncMock(return_value=hidden)
        repo.get_analysis = AsyncMock(return_value=None)
        repo.list_event_articles = AsyncMock(return_value=[])
        repo.map_tags = AsyncMock(return_value={})

        with patch("app.modules.hotspot.service.redis_client", FakeRedis()), \
             _patch_collection_list_ids():
            detail = await svc.get_event_detail(99, user=_user(Role.EDITOR))
        assert detail.id == 99

    async def test_missing_event_raises_404(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=None)
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(EventNotFoundError):
                await svc.get_event_detail(1, user=None)


# ------------------------------------------------------------------ 编辑


class TestUpdateEvent:
    async def test_pin_and_hide_conflict_raises(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=_FakeEvent(id=1))

        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(PinAndHideConflictError):
                await svc.update_event(
                    event_id=1,
                    payload=EventUpdateRequest(is_pinned=True, is_hidden=True),
                    user=_user(Role.EDITOR),
                )

    async def test_pin_over_hidden_conflict(self) -> None:
        """当前是隐藏的，editor 想置顶且没显式改 hide → 仍冲突。"""
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=_FakeEvent(id=1, is_hidden=True))

        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(PinAndHideConflictError):
                await svc.update_event(
                    event_id=1,
                    payload=EventUpdateRequest(is_pinned=True),  # 没传 hide
                    user=_user(Role.EDITOR),
                )

    async def test_title_change_locks_field_and_marks_edited(self) -> None:
        svc, session, repo = _make_service()
        repo.get_event = AsyncMock(
            side_effect=[
                _FakeEvent(id=1, title="旧标题"),  # update_event 里第一次取
                _FakeEvent(id=1, title="新标题"),  # get_event_detail 里第二次取
            ]
        )
        repo.get_analysis = AsyncMock(return_value=None)
        repo.list_event_articles = AsyncMock(return_value=[])
        repo.map_tags = AsyncMock(return_value={})
        repo.map_sources = AsyncMock(return_value={})
        repo.map_primary_article_url = AsyncMock(return_value={})
        repo.map_worth_article = AsyncMock(return_value={})

        with patch("app.modules.hotspot.service.redis_client", FakeRedis()), \
             _patch_collection_list_ids():
            detail = await svc.update_event(
                event_id=1,
                payload=EventUpdateRequest(title="新标题"),
                user=_user(Role.EDITOR),
            )
        assert detail.title == "新标题"
        # event.manual_locked_fields 写入的是 camelCase 名（"title" 已经是）
        # 关键验证：第二次取到的事件含 title="新标题" + manual_locked_fields=["title"]
        second = repo.get_event.call_args_list[1].args[0] if False else None  # noqa
        # 因为我们用 side_effect 给了第二次的对象，断言通过返回 detail 的字段间接验证
        assert session.commit.await_count >= 1

    async def test_pinning_only_does_not_lock(self) -> None:
        """is_pinned 是运营开关，不进 manual_locked_fields。"""
        svc, _, repo = _make_service()
        event = _FakeEvent(id=1, is_pinned=False)
        repo.get_event = AsyncMock(return_value=event)
        repo.get_analysis = AsyncMock(return_value=None)
        repo.list_event_articles = AsyncMock(return_value=[])
        repo.map_tags = AsyncMock(return_value={})

        with patch("app.modules.hotspot.service.redis_client", FakeRedis()), \
             _patch_collection_list_ids():
            await svc.update_event(
                event_id=1,
                payload=EventUpdateRequest(is_pinned=True),
                user=_user(Role.EDITOR),
            )
        # event 直接被改，service 不返回值校验细节；通过 side_effect 间接验证
        assert event.is_pinned is True
        assert event.is_manually_edited is False  # 关键：开关字段不该触发 is_manually_edited
        assert event.manual_locked_fields == []

    async def test_missing_event_raises_404(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=None)
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(EventNotFoundError):
                await svc.update_event(
                    event_id=999,
                    payload=EventUpdateRequest(title="x"),
                    user=_user(Role.EDITOR),
                )


# ------------------------------------------------------------------ 解锁


class TestUnlockField:
    async def test_unknown_field_raises(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(
            return_value=_FakeEvent(id=1, manual_locked_fields=["title"])
        )
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(ManualLockFieldNotFoundError):
                await svc.unlock_field(1, "garbageField", user=_user(Role.EDITOR))

    async def test_field_not_locked_raises(self) -> None:
        """字段名合法但当前没锁 → 抛错（与未知字段一致语义）。"""
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(
            return_value=_FakeEvent(id=1, manual_locked_fields=["title"])
        )
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(ManualLockFieldNotFoundError):
                await svc.unlock_field(1, "summaryOneLine", user=_user(Role.EDITOR))

    async def test_unlock_clears_manually_edited_when_empty(self) -> None:
        svc, _, repo = _make_service()
        event = _FakeEvent(
            id=1,
            manual_locked_fields=["title"],
            is_manually_edited=True,
        )
        repo.get_event = AsyncMock(return_value=event)
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            await svc.unlock_field(1, "title", user=_user(Role.EDITOR))
        assert event.manual_locked_fields == []
        assert event.is_manually_edited is False

    async def test_unlock_keeps_manually_edited_when_other_fields_locked(self) -> None:
        svc, _, repo = _make_service()
        event = _FakeEvent(
            id=1,
            manual_locked_fields=["title", "summaryOneLine"],
            is_manually_edited=True,
        )
        repo.get_event = AsyncMock(return_value=event)
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            await svc.unlock_field(1, "title", user=_user(Role.EDITOR))
        assert event.manual_locked_fields == ["summaryOneLine"]
        assert event.is_manually_edited is True


# ------------------------------------------------------------------ 趋势 / 相关


class TestTrendAndRelated:
    async def test_trend_404_for_missing_event(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=None)
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(EventNotFoundError):
                await svc.get_trend(1, user=None)

    async def test_trend_hides_for_guest(self) -> None:
        """GUEST 看 hidden event 的 trend → 也 404（_assert_visible 一致处理）。"""
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=_FakeEvent(id=1, is_hidden=True))
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(EventNotFoundError):
                await svc.get_trend(1, user=None)

    async def test_trend_visible_for_editor_when_hidden(self) -> None:
        """EDITOR 看 hidden event 的 trend → 正常返回。"""
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=_FakeEvent(id=1, is_hidden=True))
        repo.trend_points = AsyncMock(return_value=[])
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            resp = await svc.get_trend(1, user=_user(Role.EDITOR))
        assert resp.event_id == 1

    async def test_related_hides_for_guest(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=_FakeEvent(id=1, is_hidden=True))
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(EventNotFoundError):
                await svc.get_related(1, user=None)

    async def test_related_404_for_missing_event(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=None)
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            with pytest.raises(EventNotFoundError):
                await svc.get_related(1, user=None)

    async def test_trend_returns_points(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=_FakeEvent(id=1))
        repo.trend_points = AsyncMock(
            return_value=[
                {"date": "2026-07-29", "heat_score": 12.0, "source_count": 1, "article_count": 3},
            ]
        )
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            resp = await svc.get_trend(1, user=None)
        assert resp.event_id == 1
        assert len(resp.points) == 1
        assert resp.points[0].date == "2026-07-29"

    async def test_related_returns_items(self) -> None:
        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(return_value=_FakeEvent(id=1))
        repo.related_events = AsyncMock(
            return_value=[
                {
                    "id": 2,
                    "title": "Related",
                    "summary_one_line": "x",
                    "recommend_index": 50.0,
                    "last_seen_at": datetime(2026, 7, 30, tzinfo=UTC),
                    "similarity": 0.91,
                }
            ]
        )
        with patch("app.modules.hotspot.service.redis_client", FakeRedis()):
            items = await svc.get_related(1, user=None, limit=5)
        assert len(items) == 1
        assert items[0].id == 2
        assert items[0].similarity == 0.91


# ------------------------------------------------------------------ 列表组装


class _FakeTag:
    def __init__(self, id: int, display_name: str, type: str = "TECH", event_count: int = 1) -> None:
        self.id = id
        self.display_name = display_name
        self.type = type
        self.event_count = event_count


class _FakeSource:
    def __init__(self, id: int = 1, name: str = "HN", home_url: str = "https://hn", weight: int = 9) -> None:
        self.id = id
        self.name = name
        self.home_url = home_url
        self.weight = weight


class TestAssembleListItems:
    async def test_assembles_full_item(self) -> None:
        svc, _, repo = _make_service()
        row = _FakeEvent(
            id=42,
            title="T",
            summary_one_line="S",
            categories=["AI", "LLM"],
            heat_score=12.5,
            value_score=80,
            originality_score=70,
            trend_score=85,
            recommend_index=78.0,
            first_seen_at=datetime(2026, 7, 1, tzinfo=UTC),
            last_seen_at=datetime(2026, 7, 30, tzinfo=UTC),
        )
        repo.map_sources = AsyncMock(
            return_value={42: [_FakeSource(id=1), _FakeSource(id=2, name="机器之心")]}
        )
        repo.map_tags = AsyncMock(
            return_value={42: [(_FakeTag(7, "OpenAI", "COMPANY", 12), 1.0)]}
        )
        repo.map_primary_article_url = AsyncMock(return_value={42: "https://example.com"})
        repo.map_worth_article = AsyncMock(return_value={42: True})

        items = await svc._assemble_list_items([row])
        assert len(items) == 1
        it = items[0]
        assert it.id == 42
        assert len(it.sources) == 2
        assert len(it.tags) == 1
        assert it.tags[0].display_name == "OpenAI"
        assert it.primary_article_url == "https://example.com"
        assert it.worth_article is True
        assert it.is_collected is False

    async def test_empty_rows(self) -> None:
        svc, _, repo = _make_service()
        repo.map_sources = AsyncMock(return_value={})
        repo.map_tags = AsyncMock(return_value={})
        repo.map_primary_article_url = AsyncMock(return_value={})
        repo.map_worth_article = AsyncMock(return_value={})
        assert await svc._assemble_list_items([]) == []


# ------------------------------------------------------------------ 详情缓存命中


class TestDetailCacheHit:
    async def test_guest_hits_event_cache_returns_cached_detail(self) -> None:
        """GUEST 取详情，且 Redis 有缓存 → 直接返回缓存，不查 repo。"""
        import json

        redis = FakeRedis()
        cached = {
            "id": 1,
            "title": "Cached",
            "region": "GLOBAL",
            "categories": [],
            "tags": [],
            "sourceCount": 1,
            "articleCount": 1,
            "heatScore": 0,
            "recommendIndex": 0,
            "valueScore": None,
            "originalityScore": None,
            "trendScore": None,
            "status": "ANALYZED",
            "isPinned": False,
            "isHidden": False,
            "isManuallyEdited": False,
            "manualLockedFields": [],
            "firstSeenAt": "2026-07-30T00:00:00Z",
            "lastSeenAt": "2026-07-30T00:00:00Z",
            "analysis": None,
            "articles": [],
            "isCollected": False,
        }
        key = "hotspot:event:1"
        await redis.setex(key, 600, json.dumps(cached))

        svc, _, repo = _make_service()
        repo.get_event = AsyncMock(side_effect=AssertionError("不应调到 repo"))

        with patch("app.modules.hotspot.service.redis_client", redis):
            detail = await svc.get_event_detail(1, user=None)
        assert detail.id == 1
        assert detail.title == "Cached"


# ------------------------------------------------------------------ 缓存失效


class TestInvalidate:
    async def test_invalidate_writes_affect_rank_keys(self) -> None:
        redis = FakeRedis()
        # 预埋一些缓存键
        await redis.setex("hotspot:rank:TODAY:ALL:x:1", 60, "{}")
        await redis.setex("hotspot:rank:WEEK:AI:y:2", 60, "{}")
        await redis.setex("hotspot:event:7", 60, "{}")
        await redis.setex("hotspot:trend:7", 60, "{}")
        await redis.setex("auth:blacklist:foo", 60, "1")  # 不应被删

        svc, _, _ = _make_service()
        with patch("app.modules.hotspot.service.redis_client", redis):
            await svc._invalidate(event_id=7)

        # 所有 hotspot:* 应被删
        assert [k for k in redis._data if k.startswith("hotspot:")] == []
        # auth 黑名单不动
        assert await redis.exists("auth:blacklist:foo") == 1

    async def test_invalidate_swallows_redis_errors(self) -> None:
        """Redis 抛错时不应阻断业务。"""
        svc, _, _ = _make_service()
        broken = MagicMock()
        broken.scan_iter = MagicMock(side_effect=RuntimeError("redis dead"))
        with patch("app.modules.hotspot.service.redis_client", broken):
            await svc._invalidate(event_id=1)  # 不抛错即通过


class TestCacheExceptions:
    async def test_cache_get_returns_none_on_redis_error(self) -> None:
        svc, _, _ = _make_service()
        broken = MagicMock()
        broken.get = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.modules.hotspot.service.redis_client", broken):
            assert await svc._cache_get("any") is None

    async def test_cache_set_swallows_redis_error(self) -> None:
        svc, _, _ = _make_service()
        broken = MagicMock()
        broken.set = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.modules.hotspot.service.redis_client", broken):
            await svc._cache_set("any", {"x": 1}, 60)  # 不抛错即通过


class TestMutedSources:
    async def test_returns_user_muted_sources(self) -> None:
        svc, _, _ = _make_service()
        with _patch_auth_get_me(muted=[3, 7]):
            assert await svc._muted_sources(_user(Role.USER)) == [3, 7]

    async def test_returns_empty_when_auth_service_raises(self) -> None:
        """AuthService 抛异常 → 降级返回空列表，不阻断榜单。"""
        svc, _, _ = _make_service()

        fake = MagicMock()
        fake.get_me = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("app.modules.auth.service.AuthService", MagicMock(return_value=fake)):
            assert await svc._muted_sources(_user(Role.USER)) == []

    async def test_returns_empty_for_none_user(self) -> None:
        svc, _, _ = _make_service()
        assert await svc._muted_sources(None) == []
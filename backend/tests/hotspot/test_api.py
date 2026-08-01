"""hotspot API 路由层测试。

用 FastAPI TestClient + 依赖注入覆盖，把 service 整个 mock 掉，
验证路由参数解析 / 校验 / 权限门槛 / 错误码。

注意：app.modules.auth.deps.require_role(min_role) 是工厂函数，
每次调用返回新函数，FastAPI 按 identity 匹配 override 不会命中。
所以我们 override 更基础的 get_current_user / get_current_user_optional。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppException, ForbiddenError, UnauthorizedError
from app.modules.auth.deps import (
    DbSession,
    get_current_user,
    get_current_user_optional,
)
from app.modules.auth.enums import Role
from app.modules.auth.model import User
from app.modules.hotspot.api import router, tags_router
from app.modules.hotspot.schema import (
    EventDetail,
    EventTrendResponse,
    RelatedEventItem,
    TagItem,
)
from datetime import datetime, UTC


def _empty_event_detail(event_id: int = 1) -> EventDetail:
    now = datetime(2026, 7, 30, tzinfo=UTC)
    return EventDetail(
        id=event_id,
        title="X",
        region="GLOBAL",
        categories=[],
        tags=[],
        source_count=1,
        article_count=1,
        heat_score=0,
        recommend_index=0,
        value_score=None,
        originality_score=None,
        trend_score=None,
        status="ANALYZED",
        is_pinned=False,
        is_hidden=False,
        is_manually_edited=False,
        manual_locked_fields=[],
        first_seen_at=now,
        last_seen_at=now,
        analysis=None,
        articles=[],
        is_collected=False,
    )


def _empty_trend(event_id: int = 1) -> EventTrendResponse:
    return EventTrendResponse(event_id=event_id, points=[])


def _empty_related() -> list[RelatedEventItem]:
    return []


# ------------------------------------------------------------------ 假依赖


class _FakeHotspotService:
    """所有方法都是 AsyncMock，调用时返回指定值或抛指定异常。"""

    def __init__(self) -> None:
        self.list_events = AsyncMock(
            return_value={"items": [], "total": 0, "page": 1, "size": 20, "pages": 0}
        )
        self.get_event_detail = AsyncMock(side_effect=lambda *a, **kw: _empty_event_detail(1))
        self.get_trend = AsyncMock(side_effect=lambda *a, **kw: _empty_trend(1))
        self.get_related = AsyncMock(side_effect=lambda *a, **kw: _empty_related())
        self.update_event = AsyncMock(side_effect=lambda *a, **kw: _empty_event_detail(1))
        self.unlock_field = AsyncMock(return_value=None)
        self.list_tags = AsyncMock(return_value=[])


def _build_app(user: User | None, svc: _FakeHotspotService) -> FastAPI:
    """挂 router + 注入假 user / session / service。

    把 app.modules.hotspot.api 模块里的 HotspotService.* 方法替换为 svc 的 mock，
    通过 monkeypatch 在 fixture 退出时自动还原，避免污染其他测试。
    """
    from contextlib import ExitStack
    from fastapi.responses import JSONResponse
    from app.modules.hotspot import api as api_module

    app = FastAPI()
    app.include_router(router)
    app.include_router(tags_router)

    @app.exception_handler(UnauthorizedError)
    async def _unauth(_request, _exc):
        return JSONResponse(
            status_code=401, content={"detail": _exc.detail, "errorCode": _exc.error_code}
        )

    @app.exception_handler(ForbiddenError)
    async def _forbid(_request, _exc):
        return JSONResponse(
            status_code=403, content={"detail": _exc.detail, "errorCode": _exc.error_code}
        )

    @app.exception_handler(AppException)
    async def _app_exc(_request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "errorCode": exc.error_code},
        )

    async def _override_session() -> Any:
        return MagicMock()

    async def _override_optional() -> Any:
        return user

    async def _override_required() -> Any:
        if user is None:
            raise UnauthorizedError
        if user.role not in ("USER", "EDITOR", "ADMIN"):
            raise ForbiddenError
        return user

    app.dependency_overrides[DbSession] = _override_session
    app.dependency_overrides[get_current_user_optional] = _override_optional
    app.dependency_overrides[get_current_user] = _override_required

    # 用 ExitStack 管理多个 patch 在 fixture 退出时统一还原
    stack = ExitStack()
    for attr in (
        "list_events",
        "get_event_detail",
        "get_trend",
        "get_related",
        "update_event",
        "unlock_field",
        "list_tags",
    ):
        stack.callback(setattr, api_module.HotspotService, attr, getattr(api_module.HotspotService, attr))
        setattr(api_module.HotspotService, attr, getattr(svc, attr))

    app.state._restore_stack = stack
    return app


def _make_user(role: Role, user_id: int = 3) -> User:
    return User(
        id=user_id,
        email=f"u{user_id}@x.com",
        username=f"u{user_id}",
        password_hash="x",
        role=role.value,
        status="ACTIVE",
    )


@pytest.fixture
def client_guest() -> Any:
    svc = _FakeHotspotService()
    app = _build_app(None, svc)
    with TestClient(app) as c:
        yield c, svc
    app.state._restore_stack.close()


@pytest.fixture
def client_editor() -> Any:
    svc = _FakeHotspotService()
    app = _build_app(_make_user(Role.EDITOR), svc)
    with TestClient(app) as c:
        yield c, svc
    app.state._restore_stack.close()


@pytest.fixture
def client_user() -> Any:
    """普通 USER（用于验证 EDITOR-only 路由被挡）。"""
    svc = _FakeHotspotService()
    app = _build_app(_make_user(Role.USER), svc)
    with TestClient(app) as c:
        yield c, svc
    app.state._restore_stack.close()


# ------------------------------------------------------------------ /events 列表


class TestListEventsRoute:
    def test_guest_can_list(self, client_guest: Any) -> None:
        c, _ = client_guest
        r = c.get("/events")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_camelcase_aliases(self, client_guest: Any) -> None:
        """前端用 camelCase 查询参数：tagIds / sourceIds / minRecommend / startDate 等。"""
        c, svc = client_guest
        r = c.get(
            "/events?tagIds=1&tagIds=2&sourceIds=10&minRecommend=80"
            "&startDate=2026-07-01T00:00:00Z&endDate=2026-07-30T00:00:00Z"
            "&includeHidden=false"
        )
        assert r.status_code == 200
        # service 收到的 kwargs 应该被解析为 list[int] 等
        kw = svc.list_events.call_args.kwargs
        assert kw["tag_ids"] == [1, 2]
        assert kw["source_ids"] == [10]
        assert kw["min_recommend"] == 80

    def test_invalid_sort_field_returns_400(self, client_guest: Any) -> None:
        from app.modules.hotspot.exceptions import InvalidSortFieldError

        c, svc = client_guest

        async def boom(*_a, **_kw):
            raise InvalidSortFieldError

        svc.list_events.side_effect = boom
        r = c.get("/events?sort=evilField")
        assert r.status_code == 400
        assert r.json()["errorCode"] == "INVALID_SORT_FIELD"

    def test_keyword_too_short_returns_400(self, client_guest: Any) -> None:
        from app.modules.hotspot.exceptions import KeywordTooShortError

        c, svc = client_guest

        async def boom(*_a, **_kw):
            raise KeywordTooShortError

        svc.list_events.side_effect = boom
        r = c.get("/events?keyword=a")
        assert r.status_code == 400
        assert r.json()["errorCode"] == "KEYWORD_TOO_SHORT"


# ------------------------------------------------------------------ /events/{id}


class TestGetEventRoute:
    def test_guest_can_get(self, client_guest: Any) -> None:
        c, _ = client_guest
        r = c.get("/events/1")
        assert r.status_code == 200

    def test_event_not_found_returns_404(self, client_guest: Any) -> None:
        from app.modules.hotspot.exceptions import EventNotFoundError

        c, svc = client_guest

        async def boom(*_a, **_kw):
            raise EventNotFoundError

        svc.get_event_detail.side_effect = boom
        r = c.get("/events/999")
        assert r.status_code == 404
        assert r.json()["errorCode"] == "EVENT_NOT_FOUND"


class TestTrendAndRelatedRoutes:
    def test_trend(self, client_guest: Any) -> None:
        c, _ = client_guest
        r = c.get("/events/1/trend")
        assert r.status_code == 200

    def test_related(self, client_guest: Any) -> None:
        c, _ = client_guest
        r = c.get("/events/1/related")
        assert r.status_code == 200


# ------------------------------------------------------------------ PATCH /events/{id}


class TestUpdateEventRoute:
    def test_user_role_cannot_patch(self, client_user: Any) -> None:
        c, _ = client_user
        r = c.patch("/events/1", json={"title": "x"})
        # USER < EDITOR → 403
        assert r.status_code == 403

    def test_editor_can_patch(self, client_editor: Any) -> None:
        c, _ = client_editor
        r = c.patch("/events/1", json={"title": "新标题"})
        assert r.status_code == 200

    def test_pin_and_hide_conflict_returns_400(self, client_editor: Any) -> None:
        from app.modules.hotspot.exceptions import PinAndHideConflictError

        c, svc = client_editor

        async def boom(*_a, **_kw):
            raise PinAndHideConflictError

        svc.update_event.side_effect = boom
        r = c.patch("/events/1", json={"isPinned": True, "isHidden": True})
        assert r.status_code == 400
        assert r.json()["errorCode"] == "PIN_AND_HIDE_CONFLICT"

    def test_event_not_found_returns_404(self, client_editor: Any) -> None:
        from app.modules.hotspot.exceptions import EventNotFoundError

        c, svc = client_editor

        async def boom(*_a, **_kw):
            raise EventNotFoundError

        svc.update_event.side_effect = boom
        r = c.patch("/events/999", json={"title": "x"})
        assert r.status_code == 404

    def test_title_too_long_rejected_by_pydantic(self, client_editor: Any) -> None:
        c, _ = client_editor
        r = c.patch("/events/1", json={"title": "x" * 501})
        assert r.status_code == 422


# ------------------------------------------------------------------ DELETE manual-lock/{field}


class TestUnlockRoute:
    def test_user_role_cannot_unlock(self, client_user: Any) -> None:
        c, _ = client_user
        r = c.delete("/events/1/manual-lock/title")
        assert r.status_code == 403

    def test_unknown_field_returns_404(self, client_editor: Any) -> None:
        from app.modules.hotspot.exceptions import ManualLockFieldNotFoundError

        c, svc = client_editor

        async def boom(*_a, **_kw):
            raise ManualLockFieldNotFoundError

        svc.unlock_field.side_effect = boom
        r = c.delete("/events/1/manual-lock/garbage")
        assert r.status_code == 404
        assert r.json()["errorCode"] == "MANUAL_LOCK_FIELD_NOT_FOUND"

    def test_success_returns_204(self, client_editor: Any) -> None:
        c, _ = client_editor
        r = c.delete("/events/1/manual-lock/title")
        assert r.status_code == 204


# ------------------------------------------------------------------ /tags


class TestTagsRoute:
    def test_list_tags_default(self, client_guest: Any) -> None:
        c, _ = client_guest
        r = c.get("/tags")
        assert r.status_code == 200
        assert r.json() == []

    def test_tags_with_filters(self, client_guest: Any) -> None:
        from app.modules.hotspot.schema import TagItem

        c, svc = client_guest

        async def fake(*_a, **_kw):
            return [TagItem(id=1, display_name="OpenAI", type="COMPANY", event_count=12)]

        svc.list_tags.side_effect = fake
        r = c.get("/tags?type=COMPANY&limit=10&keyword=open")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["displayName"] == "OpenAI"
        assert body[0]["eventCount"] == 12

    def test_tags_limit_validation(self, client_guest: Any) -> None:
        """limit > 200 应被 FastAPI Query(le=200) 拦下 → 422。"""
        c, _ = client_guest
        r = c.get("/tags?limit=99999")
        assert r.status_code == 422
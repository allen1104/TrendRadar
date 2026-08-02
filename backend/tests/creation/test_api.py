"""creation API 路由测试（FastAPI TestClient + 依赖覆盖）。

不连数据库 — service 用 AsyncMock 覆盖。
覆盖 SPEC「后端接口」的所有 7 个端点的 status code 路径。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppException
from app.modules.creation.api import router
from app.modules.creation.enums import Platform, Style
from app.modules.creation.exceptions import (
    DraftNotFoundError,
    EventNotAnalyzedError,
    InvalidExportFormatError,
    InvalidPlatformError,
    InvalidStyleError,
    QuotaExceededError,
    TargetWordsOutOfRangeError,
    TooManyRegenerationsError,
)
from app.modules.creation.schema import (
    DraftCreateRequest,
    DraftRegenerateRequest,
    DraftUpdateRequest,
)


# ============================================================ 依赖覆盖


def _fake_user(user_id: int = 6) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.username = "tester"
    u.email = "t@e.com"
    u.role = "USER"
    return u


def _build_app(*, with_user: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    @app.exception_handler(AppException)
    async def _app_exc_handler(_request: Any, exc: AppException):  # noqa: ANN202
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "errorCode": exc.error_code, **exc.extra},
        )

    fake_session = MagicMock()

    async def _override_db():
        yield fake_session

    from app.db.session import get_db

    app.dependency_overrides[get_db] = _override_db

    from app.modules.auth.deps import get_current_user

    if with_user:

        async def _override_user():
            return _fake_user()

        app.dependency_overrides[get_current_user] = _override_user

    return app


# ============================================================ options


class TestGetOptions:
    def test_200_returns_all_platforms(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.get_options",
            AsyncMock(
                return_value=__import__(
                    "app.modules.creation.service", fromlist=["OptionsResponse"]
                ).OptionsResponse(
                    platforms=[
                        __import__(
                            "app.modules.creation.service", fromlist=["PlatformOption"]
                        ).PlatformOption(
                            key=Platform.WECHAT,
                            name="微信公众号",
                            icon="wechat",
                            target_words=[1500, 3000],
                            description="x",
                        )
                    ],
                    styles=[],
                )
            ),
        ):
            r = client.get("/api/v1/creation/options")
        assert r.status_code == 200
        body = r.json()
        assert len(body["platforms"]) >= 1


# ============================================================ list drafts


class TestListDrafts:
    def test_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.list_drafts",
            AsyncMock(return_value=([], 0)),
        ):
            r = client.get("/api/v1/creation/drafts?page=1&size=20")
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["size"] == 20
        assert body["total"] == 0
        assert body["items"] == []

    def test_size_too_large_returns_422(self) -> None:
        app = _build_app()
        client = TestClient(app)
        r = client.get("/api/v1/creation/drafts?size=200")
        # Pydantic 校验：size > 100
        assert r.status_code == 422


# ============================================================ create draft (SSE stub)


class TestCreateDraft:
    def test_invalid_platform_returns_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        # Pydantic 直接拒非法 enum → 422
        r = client.post(
            "/api/v1/creation/drafts",
            json={"eventId": 1, "platform": "BOGUS", "style": "TECHNICAL"},
        )
        assert r.status_code == 422

    def test_target_words_out_of_range_returns_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.stream_create",
            MagicMock(side_effect=TargetWordsOutOfRangeError()),
        ):
            # target_words 须在 Pydantic 范围内；用 4600（WECHAT 上限 3000*1.5=4500 → 超范围）
            r = client.post(
                "/api/v1/creation/drafts",
                json={
                    "eventId": 1, "platform": "WECHAT", "style": "TECHNICAL",
                    "targetWords": 4600,
                },
            )
        assert r.status_code == 400
        assert r.json()["errorCode"] == "TARGET_WORDS_OUT_OF_RANGE"

    def test_event_not_analyzed_returns_409(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.stream_create",
            MagicMock(side_effect=EventNotAnalyzedError()),
        ):
            r = client.post(
                "/api/v1/creation/drafts",
                json={"eventId": 1, "platform": "WECHAT", "style": "TECHNICAL"},
            )
        assert r.status_code == 409
        assert r.json()["errorCode"] == "EVENT_NOT_ANALYZED"

    def test_quota_exceeded_returns_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.stream_create",
            MagicMock(side_effect=QuotaExceededError()),
        ):
            r = client.post(
                "/api/v1/creation/drafts",
                json={"eventId": 1, "platform": "WECHAT", "style": "TECHNICAL"},
            )
        assert r.status_code == 400
        assert r.json()["errorCode"] == "QUOTA_EXCEEDED"


# ============================================================ get draft


class TestGetDraft:
    def test_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        detail = {
            "id": 1, "user_id": 6, "event_id": 88,
            "platform": Platform.WECHAT, "style": Style.TECHNICAL,
            "title": "t", "content": "c", "content_edited": None,
            "outline": [], "cover_suggestion": None, "tags_suggestion": [],
            "word_count": 1, "extra_params": {}, "model_alias": None,
            "prompt_version": None, "cost_usd": 0.0,
            "status": "DONE", "error_message": None, "regenerate_count": 0,
            "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-02T00:00:00Z",
        }
        with patch(
            "app.modules.creation.api.CreationService.get_draft",
            AsyncMock(return_value=detail),
        ):
            r = client.get("/api/v1/creation/drafts/1")
        assert r.status_code == 200
        assert r.json()["id"] == 1

    def test_not_found_returns_404(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.get_draft",
            AsyncMock(side_effect=DraftNotFoundError()),
        ):
            r = client.get("/api/v1/creation/drafts/999")
        assert r.status_code == 404
        assert r.json()["errorCode"] == "DRAFT_NOT_FOUND"


# ============================================================ update draft


class TestUpdateDraft:
    def test_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        detail = {
            "id": 1, "user_id": 6, "event_id": 88,
            "platform": Platform.WECHAT, "style": Style.TECHNICAL,
            "title": "改后标题", "content": "c", "content_edited": "改后",
            "outline": [], "cover_suggestion": None, "tags_suggestion": [],
            "word_count": 1, "extra_params": {}, "model_alias": None,
            "prompt_version": None, "cost_usd": 0.0,
            "status": "DONE", "error_message": None, "regenerate_count": 0,
            "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-02T00:00:00Z",
        }
        with patch(
            "app.modules.creation.api.CreationService.update_draft",
            AsyncMock(return_value=detail),
        ):
            r = client.patch(
                "/api/v1/creation/drafts/1",
                json={"title": "改后标题", "contentEdited": "改后"},
            )
        assert r.status_code == 200
        assert r.json()["title"] == "改后标题"

    def test_not_found_returns_404(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.update_draft",
            AsyncMock(side_effect=DraftNotFoundError()),
        ):
            r = client.patch(
                "/api/v1/creation/drafts/999",
                json={"title": "x"},
            )
        assert r.status_code == 404


# ============================================================ delete draft


class TestDeleteDraft:
    def test_204(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.delete_draft",
            AsyncMock(return_value=None),
        ):
            r = client.delete("/api/v1/creation/drafts/1")
        assert r.status_code == 204

    def test_not_found_returns_404(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.delete_draft",
            AsyncMock(side_effect=DraftNotFoundError()),
        ):
            r = client.delete("/api/v1/creation/drafts/999")
        assert r.status_code == 404


# ============================================================ regenerate (SSE stub)


class TestRegenerate:
    def test_too_many_returns_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.stream_regenerate",
            MagicMock(side_effect=TooManyRegenerationsError()),
        ):
            r = client.post(
                "/api/v1/creation/drafts/1/regenerate",
                json={},
            )
        assert r.status_code == 400
        assert r.json()["errorCode"] == "TOO_MANY_REGENERATIONS"

    def test_invalid_style_returns_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.stream_regenerate",
            MagicMock(side_effect=InvalidStyleError()),
        ):
            r = client.post(
                "/api/v1/creation/drafts/1/regenerate",
                json={"style": "BOGUS"},
            )
        assert r.status_code == 422  # Pydantic 先拦截

    def test_not_found_returns_404(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.stream_regenerate",
            MagicMock(side_effect=DraftNotFoundError()),
        ):
            r = client.post(
                "/api/v1/creation/drafts/999/regenerate",
                json={},
            )
        assert r.status_code == 404


# ============================================================ export


class TestExport:
    def test_markdown_export_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.export_draft",
            AsyncMock(
                return_value=(b"# title\n\nbody", "text/markdown; charset=utf-8", "t.md")
            ),
        ):
            r = client.get("/api/v1/creation/drafts/1/export?format=MARKDOWN")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "attachment" in r.headers["content-disposition"]
        assert r.content == b"# title\n\nbody"

    def test_html_export_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.export_draft",
            AsyncMock(return_value=(b"<html/>", "text/html; charset=utf-8", "t.html")),
        ):
            r = client.get("/api/v1/creation/drafts/1/export?format=HTML")
        assert r.status_code == 200

    def test_wechat_html_export_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.export_draft",
            AsyncMock(return_value=(b"<section/>", "text/html; charset=utf-8", "t.html")),
        ):
            r = client.get("/api/v1/creation/drafts/1/export?format=WECHAT_HTML")
        assert r.status_code == 200

    def test_txt_export_200(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.export_draft",
            AsyncMock(return_value=(b"plain text", "text/plain; charset=utf-8", "t.txt")),
        ):
            r = client.get("/api/v1/creation/drafts/1/export?format=TXT")
        assert r.status_code == 200

    def test_invalid_format_returns_400(self) -> None:
        app = _build_app()
        client = TestClient(app)
        # Pydantic enum 拒 → 422
        r = client.get("/api/v1/creation/drafts/1/export?format=PDF")
        assert r.status_code == 422

    def test_not_found_returns_404(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch(
            "app.modules.creation.api.CreationService.export_draft",
            AsyncMock(side_effect=DraftNotFoundError()),
        ):
            r = client.get("/api/v1/creation/drafts/999/export?format=MARKDOWN")
        assert r.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
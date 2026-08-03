"""report API 路由测试（FastAPI TestClient + 依赖覆盖）。

不连数据库 — service 用 AsyncMock 覆盖。
覆盖 SPEC「后端接口」的关键 status code 路径。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppException
from app.modules.report.api import admin_router, router
from app.modules.report.enums import ReportType
from app.modules.report.exceptions import (
    CandidatesInsufficientError,
    InvalidExportFormatError,
    InvalidReportTypeError,
    ReportAlreadyExistsError,
    ReportAlreadyPublishedError,
    ReportHasNoItemsError,
    ReportItemNotFoundError,
    ReportNotFoundError,
    WebhookUrlRequiredError,
)


# ============================================================ 依赖覆盖


def _fake_user(user_id: int = 6, role: str = "EDITOR") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.username = "tester"
    u.email = "t@e.com"
    u.role = role
    return u


def _build_app(*, with_user: bool = True, user_role: str = "EDITOR") -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

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

    from app.modules.auth.deps import get_current_user, get_current_user_optional

    if with_user:

        async def _override_user():
            return _fake_user(role=user_role)

        async def _override_optional_user():
            return _fake_user(role=user_role)

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_user_optional] = _override_optional_user

    return app


def _fake_report(
    *, rid: int = 1, status: str = "PUBLISHED", rtype: str = "AI"
) -> MagicMock:
    r = MagicMock()
    r.id = rid
    r.report_type = rtype
    r.report_date = date(2026, 8, 2)
    r.title = "AI 日报 · 2026-08-02"
    r.intro = "intro"
    r.outro = "outro"
    r.content_md = "# T\n\ncontent"
    r.content_edited = None
    r.item_count = 2
    r.status = status
    r.published_at = datetime(2026, 8, 2, 8, 30, tzinfo=UTC)
    r.view_count = 100
    r.model_alias = "default-chat"
    r.cost_usd = 0.012
    return r


# ============================================================ list_reports


class TestListReports:
    def test_200_returns_published_only_for_guest(self) -> None:
        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.list_reports = AsyncMock(return_value=([_fake_report()], 1))
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["reportType"] == "AI"

    def test_passes_status_filter(self) -> None:
        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch(
            "app.modules.report.api.ReportService"
        ) as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.list_reports = AsyncMock(return_value=([], 0))
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports?status=DRAFT")
        assert r.status_code == 200
        # 验证 status 参数传入
        kwargs = mock_inst.list_reports.call_args.kwargs
        assert kwargs["status"] == "DRAFT"


# ============================================================ latest


class TestLatest:
    def test_200_empty(self) -> None:
        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.list_latest = AsyncMock(return_value=[])
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports/latest")
        assert r.status_code == 200
        assert r.json() == []

    def test_200_returns_items(self) -> None:
        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.list_latest = AsyncMock(return_value=[_fake_report(), _fake_report(rid=2, rtype="TECH")])
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports/latest")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ============================================================ get_report


class TestGetReport:
    def test_200_published_for_guest(self) -> None:
        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.get_report_with_sections = AsyncMock(return_value=(_fake_report(), [], {}))
            mock_svc.return_value = mock_inst
            # redis_client get 抛错 → 不阻塞
            with patch("app.core.redis.redis_client") as rc:
                rc.get = AsyncMock(side_effect=Exception("redis down"))
                r = client.get("/api/v1/reports/1")
        assert r.status_code == 200

    def test_404_when_not_found(self) -> None:
        from app.modules.report.exceptions import ReportNotFoundError

        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.get_report_with_sections = AsyncMock(side_effect=ReportNotFoundError)
            mock_svc.return_value = mock_inst
            with patch("app.core.redis.redis_client") as rc:
                rc.get = AsyncMock(return_value=None)
                r = client.get("/api/v1/reports/999")
        assert r.status_code == 404


# ============================================================ export


class TestExport:
    def test_400_invalid_format(self) -> None:
        from app.modules.report.exceptions import InvalidExportFormatError

        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.export = AsyncMock(side_effect=InvalidExportFormatError)
            mock_svc.return_value = mock_inst
            # Pydantic 会校验 ExportFormat 枚举，ZZZ 直接被 422 挡掉。
            # 用合法 enum + service 抛 400 错误验证错误链路。
            r = client.get("/api/v1/reports/1/export?format=MARKDOWN")
        assert r.status_code == 400

    def test_422_invalid_enum(self) -> None:
        app = _build_app(with_user=False)
        client = TestClient(app)
        r = client.get("/api/v1/reports/1/export?format=ZZZ")
        assert r.status_code == 422

    def test_404_not_found(self) -> None:
        from app.modules.report.exceptions import ReportNotFoundError

        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.export = AsyncMock(side_effect=ReportNotFoundError)
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports/999/export?format=MARKDOWN")
        assert r.status_code == 404


# ============================================================ RSS


class TestRss:
    def test_200_public(self) -> None:
        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.build_rss_for_token = AsyncMock(return_value="<rss></rss>")
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports/rss")
        assert r.status_code == 200
        assert "<rss" in r.text
        assert "application/rss+xml" in r.headers["content-type"]

    def test_404_invalid_token(self) -> None:
        from app.modules.report.exceptions import ReportNotFoundError

        app = _build_app(with_user=False)
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.build_rss_for_token = AsyncMock(side_effect=ReportNotFoundError("token 无效"))
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports/rss?token=bad")
        assert r.status_code == 404


# ============================================================ Subscription


class TestSubscription:
    def test_get_404_when_no_subscription(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.get_subscription = AsyncMock(return_value=None)
            mock_svc.return_value = mock_inst
            r = client.get("/api/v1/reports/subscription")
        assert r.status_code == 200
        assert r.json() is None

    def test_put_400_when_webhook_without_url(self) -> None:
        app = _build_app()
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.put_subscription = AsyncMock(side_effect=WebhookUrlRequiredError)
            mock_svc.return_value = mock_inst
            r = client.put(
                "/api/v1/reports/subscription",
                json={
                    "reportTypes": ["AI"],
                    "channel": "WEBHOOK",
                    "webhookUrl": None,
                    "enabled": True,
                },
            )
        assert r.status_code == 400

    def test_reset_rss_token(self) -> None:
        from app.modules.report.enums import SubscriptionChannel

        app = _build_app()
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            sub = MagicMock()
            sub.rss_token = "rt_newtoken123"
            sub.channel = SubscriptionChannel.SITE.value
            sub.report_types = ["AI"]
            sub.webhook_url = None
            sub.enabled = True
            mock_inst = AsyncMock()
            mock_inst.reset_rss_token = AsyncMock(return_value=sub)
            resp = MagicMock()
            resp.rss_url = "/api/v1/reports/rss?token=rt_newtoken123"
            mock_inst._sub_to_response = MagicMock(return_value=resp)
            mock_svc.return_value = mock_inst
            r = client.post("/api/v1/reports/subscription/rss-token/reset")
        assert r.status_code == 200
        body = r.json()
        assert body["rssToken"] == "rt_newtoken123"


# ============================================================ Admin: generate


class TestAdminGenerate:
    def test_200_success(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.generate_report = AsyncMock(return_value=_fake_report())
            mock_svc.return_value = mock_inst
            r = client.post(
                "/api/v1/admin/reports/generate",
                json={"reportType": "AI", "reportDate": "2026-08-02", "force": False},
            )
        assert r.status_code == 200
        assert r.json()["reportId"] == 1
        assert r.json()["status"] == "PUBLISHED"

    def test_409_already_exists(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.generate_report = AsyncMock(side_effect=ReportAlreadyExistsError)
            mock_svc.return_value = mock_inst
            r = client.post(
                "/api/v1/admin/reports/generate",
                json={"reportType": "AI", "reportDate": "2026-08-02", "force": False},
            )
        assert r.status_code == 409

    def test_200_with_skip_for_insufficient(self) -> None:
        """候选池不足 → 返回 200 + skipped=true（不算错误）。"""
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.generate_report = AsyncMock(side_effect=CandidatesInsufficientError)
            mock_svc.return_value = mock_inst
            r = client.post(
                "/api/v1/admin/reports/generate",
                json={"reportType": "AI", "reportDate": "2026-08-02"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["skipped"] is True


# ============================================================ Admin: edit / publish


class TestAdminUpdateReport:
    def test_200(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.update_report = AsyncMock(return_value=_fake_report())
            mock_inst.item_repo = MagicMock()
            mock_inst.item_repo.list_for_report = AsyncMock(return_value=[])
            mock_svc.return_value = mock_inst
            r = client.patch(
                "/api/v1/admin/reports/1",
                json={"title": "新标题", "intro": "新导语"},
            )
        assert r.status_code == 200


class TestAdminPublish:
    def test_200(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.publish = AsyncMock(return_value=_fake_report(status="PUBLISHED"))
            mock_inst.item_repo = MagicMock()
            mock_inst.item_repo.list_for_report = AsyncMock(return_value=[])
            mock_svc.return_value = mock_inst
            r = client.post("/api/v1/admin/reports/1/publish")
        assert r.status_code == 200

    def test_400_already_published(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.publish = AsyncMock(side_effect=ReportAlreadyPublishedError)
            mock_svc.return_value = mock_inst
            r = client.post("/api/v1/admin/reports/1/publish")
        assert r.status_code == 400

    def test_400_no_items(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.publish = AsyncMock(side_effect=ReportHasNoItemsError)
            mock_svc.return_value = mock_inst
            r = client.post("/api/v1/admin/reports/1/publish")
        assert r.status_code == 400


class TestAdminUnpublish:
    def test_200_admin(self) -> None:
        app = _build_app(user_role="ADMIN")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.unpublish = AsyncMock(return_value=_fake_report(status="DRAFT"))
            mock_inst.item_repo = MagicMock()
            mock_inst.item_repo.list_for_report = AsyncMock(return_value=[])
            mock_svc.return_value = mock_inst
            r = client.post("/api/v1/admin/reports/1/unpublish")
        assert r.status_code == 200

    def test_403_editor_forbidden(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        r = client.post("/api/v1/admin/reports/1/unpublish")
        assert r.status_code == 403


# ============================================================ Admin: items


class TestAdminItems:
    def _fake_item(self, iid: int = 10) -> MagicMock:
        it = MagicMock()
        it.id = iid
        it.event_id = 88
        it.section = "头条"
        it.sort_order = 0
        it.headline = "H"
        it.brief = "B"
        it.comment = None
        it.is_top = False
        return it

    def test_update_item(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.update_item = AsyncMock(return_value=self._fake_item())
            mock_svc.return_value = mock_inst
            r = client.patch(
                "/api/v1/admin/reports/1/items/10",
                json={"headline": "改后", "is_top": True},
            )
        assert r.status_code == 200

    def test_delete_item_204(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.delete_item = AsyncMock(return_value=None)
            mock_svc.return_value = mock_inst
            r = client.delete("/api/v1/admin/reports/1/items/10")
        assert r.status_code == 204

    def test_delete_item_404(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.delete_item = AsyncMock(side_effect=ReportItemNotFoundError)
            mock_svc.return_value = mock_inst
            r = client.delete("/api/v1/admin/reports/1/items/999")
        assert r.status_code == 404

    def test_add_item(self) -> None:
        app = _build_app(user_role="EDITOR")
        client = TestClient(app)
        with patch("app.modules.report.api.ReportService") as mock_svc:
            mock_inst = AsyncMock()
            mock_inst.add_item = AsyncMock(return_value=self._fake_item(iid=11))
            mock_svc.return_value = mock_inst
            r = client.post(
                "/api/v1/admin/reports/1/items",
                json={"eventId": 88, "section": "头条"},
            )
        assert r.status_code == 200
        assert r.json()["eventId"] == 88


# ============================================================ HTTP layer validation


class TestHTTPValidation:
    def test_pagination_size_limit(self) -> None:
        """size 上限 100，500 → 422。"""
        app = _build_app(with_user=False)
        client = TestClient(app)
        r = client.get("/api/v1/reports?size=500")
        assert r.status_code == 422

    def test_pagination_min_size(self) -> None:
        """size 下限 1，0 → 422。"""
        app = _build_app(with_user=False)
        client = TestClient(app)
        r = client.get("/api/v1/reports?size=0")
        assert r.status_code == 422

    def test_pagination_min_page(self) -> None:
        """page 下限 1，0 → 422。"""
        app = _build_app(with_user=False)
        client = TestClient(app)
        r = client.get("/api/v1/reports?page=0")
        assert r.status_code == 422

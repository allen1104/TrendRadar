"""collection API 路由错误码测试（FastAPI TestClient + 依赖覆盖）。

策略：patch app.modules.collection.api.CollectionService 的方法为 AsyncMock，
用 `with patch(...)` 上下文管理器确保 undo，避免污染其他测试。

注意 mock 返回值必须与 service 层真实签名保持一致：
- list_collected_event_ids → set[int]，因为 service 里 `sorted(int(i) for i in matched)`
- 其他 → 对应 DTO（FolderResponse / ItemResponse / BatchItemResponse / StatsResponse）
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.exceptions import AppException
from app.modules.auth.model import User
from app.modules.collection.api import (
    folders_router,
    items_router,
    stats_router,
)
from app.db.session import get_db


# ============================================================ helpers


def _user(user_id: int = 6) -> User:
    return User(
        id=user_id, email=f"u{user_id}@x.com", username=f"u{user_id}",
        password_hash="x", role="USER", status="ACTIVE",
    )


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppException)
    async def _app_exc(_request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "errorCode": exc.error_code, **exc.extra},
        )

    @app.exception_handler(RequestValidationError)
    async def _val(_request, exc: RequestValidationError):
        errors = [
            {
                "loc": list(e.get("loc", [])),
                "msg": str(e.get("msg", "")),
                "type": e.get("type", ""),
            }
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": "参数校验失败", "errorCode": "VALIDATION_ERROR", "errors": errors},
        )

    async def _current_user() -> User:
        return _user()

    async def _fake_db() -> Any:
        return AsyncMock()

    from app.modules.auth.deps import get_current_user

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_db] = _fake_db

    for router in (folders_router, items_router, stats_router):
        app.include_router(router, prefix="/api/v1/collections")
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


@contextmanager
def _patch_method(method_name: str, **kw):
    """对 CollectionService 的方法打 AsyncMock patch。with 退出时自动 undo。"""
    mock = AsyncMock(**kw)
    with patch(f"app.modules.collection.api.CollectionService.{method_name}", mock):
        yield mock


# ============================================================ folders


def test_list_folders_200(client: TestClient) -> None:
    from app.modules.collection.schema import FolderResponse
    fr = FolderResponse(
        id=1, name="我的收藏", description=None, color="#3b82f6",
        sort_order=0, is_default=True, item_count=0,
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    with _patch_method("list_folders", return_value=[fr]) as mock:
        r = client.get("/api/v1/collections/folders")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "我的收藏"
    mock.assert_awaited_once()


def test_create_folder_201(client: TestClient) -> None:
    from app.modules.collection.schema import FolderResponse
    fr = FolderResponse(
        id=2, name="new", description=None, color=None,
        sort_order=0, is_default=False, item_count=0,
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    with _patch_method("create_folder", return_value=fr):
        r = client.post("/api/v1/collections/folders", json={"name": "new"})
    assert r.status_code == 201
    assert r.json()["name"] == "new"


def test_create_folder_empty_name_422(client: TestClient) -> None:
    r = client.post("/api/v1/collections/folders", json={"name": ""})
    assert r.status_code == 422


def test_create_folder_invalid_color_422(client: TestClient) -> None:
    r = client.post("/api/v1/collections/folders", json={"name": "x", "color": "red"})
    assert r.status_code == 422


def test_update_folder_not_found_404(client: TestClient) -> None:
    from app.modules.collection.exceptions import FolderNotFoundError
    with _patch_method("update_folder", side_effect=FolderNotFoundError):
        r = client.patch("/api/v1/collections/folders/99", json={"name": "x"})
    assert r.status_code == 404
    assert r.json()["errorCode"] == "FOLDER_NOT_FOUND"


def test_update_folder_default_rename_400(client: TestClient) -> None:
    from app.modules.collection.exceptions import CannotDeleteDefaultFolderError
    with _patch_method("update_folder", side_effect=CannotDeleteDefaultFolderError):
        r = client.patch("/api/v1/collections/folders/1", json={"name": "new"})
    assert r.status_code == 400
    assert r.json()["errorCode"] == "CANNOT_DELETE_DEFAULT_FOLDER"


def test_delete_folder_204(client: TestClient) -> None:
    with _patch_method("delete_folder", return_value=None):
        r = client.delete("/api/v1/collections/folders/2")
    assert r.status_code == 204


# ============================================================ items


def test_get_item_404(client: TestClient) -> None:
    from app.modules.collection.exceptions import ItemNotFoundError
    with _patch_method("get_item", side_effect=ItemNotFoundError):
        r = client.get("/api/v1/collections/items/99")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "ITEM_NOT_FOUND"


def test_create_item_409_already_collected(client: TestClient) -> None:
    from app.modules.collection.exceptions import AlreadyCollectedError
    with _patch_method(
        "create_item", side_effect=AlreadyCollectedError(extra={"existingItemId": 99})
    ):
        r = client.post("/api/v1/collections/items", json={"eventId": 9})
    assert r.status_code == 409
    assert r.json()["errorCode"] == "ALREADY_COLLECTED"
    assert r.json()["existingItemId"] == 99


def test_create_item_quota_400(client: TestClient) -> None:
    from app.modules.collection.exceptions import ItemQuotaExceededError
    with _patch_method(
        "create_item", side_effect=ItemQuotaExceededError(extra={"quota": 10000})
    ):
        r = client.post("/api/v1/collections/items", json={"eventId": 9})
    assert r.status_code == 400
    assert r.json()["errorCode"] == "QUOTA_EXCEEDED"


def test_delete_item_204(client: TestClient) -> None:
    with _patch_method("delete_item", return_value=None):
        r = client.delete("/api/v1/collections/items/10")
    assert r.status_code == 204


def test_list_items_returns_page(client: TestClient) -> None:
    from app.modules.collection.schema import ItemResponse, EventBrief
    it = ItemResponse(
        id=10, folder_id=1, folder_name="我的收藏", note=None,
        user_tags=[], read_status="UNREAD", read_at=None,
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
        event=EventBrief(
            id=9, title="Test", summary_one_line=None, categories=[],
            recommend_index=80.0, source_count=3, last_seen_at=None,
        ),
    )
    with _patch_method("list_items", return_value=([it], 1)):
        r = client.get("/api/v1/collections/items")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == 10


def test_batch_items_invalid_action_422(client: TestClient) -> None:
    """action 不在白名单内 → Pydantic 422。"""
    r = client.post(
        "/api/v1/collections/items/batch",
        json={"itemIds": [1], "action": "INVALID"},
    )
    assert r.status_code == 422


def test_batch_items_move_200(client: TestClient) -> None:
    from app.modules.collection.schema import BatchItemResponse
    with _patch_method("batch_items", return_value=BatchItemResponse(affected_count=3)):
        r = client.post(
            "/api/v1/collections/items/batch",
            json={"itemIds": [1, 2, 3], "action": "MOVE", "targetFolderId": 5},
        )
    assert r.status_code == 200
    assert r.json()["affectedCount"] == 3


def test_collected_event_ids(client: TestClient) -> None:
    # service 层返回 set[int]，mock 直接给 set
    with _patch_method("list_collected_event_ids", return_value={1, 5, 9}):
        r = client.get("/api/v1/collections/items/event-ids?eventIds=1,2,5,9")
    assert r.status_code == 200
    assert sorted(r.json()["eventIds"]) == [1, 5, 9]


def test_collected_event_ids_empty(client: TestClient) -> None:
    with _patch_method("list_collected_event_ids", return_value=set()):
        r = client.get("/api/v1/collections/items/event-ids?eventIds=1,2")
    assert r.status_code == 200
    assert r.json()["eventIds"] == []


def test_stats(client: TestClient) -> None:
    from app.modules.collection.schema import StatsResponse, CategoryCount, MonthCount
    stats = StatsResponse(
        total_items=10, unread_count=5, later_count=2, read_count=3,
        folder_count=2,
        by_category=[CategoryCount(category="AI", count=8)],
        recent_months=[MonthCount(month="2026-07", count=10)],
    )
    with _patch_method("get_stats", return_value=stats):
        r = client.get("/api/v1/collections/stats")
    assert r.status_code == 200
    assert r.json()["totalItems"] == 10
    assert r.json()["folderCount"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

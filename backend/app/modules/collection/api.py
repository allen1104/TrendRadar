"""collection 路由：folders + items + batch + stats + event-ids。"""

from __future__ import annotations

from typing import Annotated
from typing import Annotated as _Ann

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi import Depends as _Depends
from sqlalchemy.ext.asyncio import AsyncSession as _AS

from app.core.pagination import PageParams, page_params
from app.core.schema import Page
from app.db.session import get_db
from app.modules.auth.deps import CurrentUser
from app.modules.collection.enums import ReadStatus
from app.modules.collection.schema import (
    BatchItemRequest,
    BatchItemResponse,
    CollectedEventIdsResponse,
    FolderCreateRequest,
    FolderResponse,
    FolderUpdateRequest,
    ItemCreateRequest,
    ItemResponse,
    ItemUpdateRequest,
    StatsResponse,
)
from app.modules.collection.service import CollectionService

DbSession = _Ann[_AS, _Depends(get_db)]

folders_router = APIRouter(prefix="/folders", tags=["collection"])
items_router = APIRouter(prefix="/items", tags=["collection"])


# ----------------------------------------------------------------- folders


@folders_router.get("", response_model=list[FolderResponse], summary="我的收藏夹列表")
async def list_folders(session: DbSession, user: CurrentUser) -> list[FolderResponse]:
    return await CollectionService(session).list_folders(user.id)


@folders_router.post(
    "",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新建收藏夹（≤50）",
)
async def create_folder(
    payload: FolderCreateRequest, session: DbSession, user: CurrentUser
) -> FolderResponse:
    return await CollectionService(session).create_folder(user.id, payload, actor=user)


@folders_router.patch(
    "/{folder_id}", response_model=FolderResponse, summary="修改收藏夹"
)
async def update_folder(
    folder_id: int,
    payload: FolderUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> FolderResponse:
    return await CollectionService(session).update_folder(
        user.id, folder_id, payload, actor=user
    )


@folders_router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除收藏夹（默认不可删；items 迁到默认）",
)
async def delete_folder(
    folder_id: int, session: DbSession, user: CurrentUser
) -> Response:
    await CollectionService(session).delete_folder(user.id, folder_id, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------- items


@items_router.get("", response_model=Page[ItemResponse], summary="我的收藏条目")
async def list_items(
    session: DbSession,
    user: CurrentUser,
    pagination: Annotated[PageParams, Depends(page_params)],
    folder_id: Annotated[int | None, Query()] = None,
    read_status: Annotated[ReadStatus | None, Query()] = None,
    user_tag: Annotated[str | None, Query(max_length=20)] = None,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[str, Query(description="-createdAt / -updatedAt / -readAt")] = "-createdAt",
) -> Page[ItemResponse]:
    rows, total = await CollectionService(session).list_items(
        user.id,
        folder_id=folder_id,
        read_status=read_status.value if read_status else None,
        user_tag=user_tag,
        keyword=keyword,
        sort=sort,
        page=pagination.page,
        size=pagination.size,
    )
    return Page[ItemResponse].create(
        items=rows, total=total, page=pagination.page, size=pagination.size
    )


@items_router.get(
    "/event-ids",
    response_model=CollectedEventIdsResponse,
    summary="hotspot 内部用：当前用户已收藏的 event_id 集合（批量查）",
    include_in_schema=False,
)
async def get_collected_event_ids(
    session: DbSession,
    user: CurrentUser,
    event_ids: Annotated[str, Query(alias="eventIds", description="event id，逗号分隔")],
) -> CollectedEventIdsResponse:
    """hotspot 内部用：当前用户已收藏的 event_id 集合（批量查）。

    接受逗号分隔字符串，避免 FastAPI list[int] 参数在客户端调用时要重复多次。
    """
    ids: list[int] = []
    for tok in (event_ids or "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            ids.append(int(tok))
    matched = await CollectionService(session).list_collected_event_ids(user.id, ids)
    # matched 是 set[int]（service 层约定）；显式 int() 防止 sorted() 把 Pydantic 模型当 dict 展开
    return CollectedEventIdsResponse(event_ids=sorted(int(i) for i in matched))


@items_router.get("/{item_id}", response_model=ItemResponse, summary="收藏条目详情")
async def get_item(
    item_id: int, session: DbSession, user: CurrentUser
) -> ItemResponse:
    return await CollectionService(session).get_item(user.id, item_id)


@items_router.post(
    "",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="收藏一个事件（≤10000）",
)
async def create_item(
    payload: ItemCreateRequest, session: DbSession, user: CurrentUser
) -> ItemResponse:
    return await CollectionService(session).create_item(user.id, payload, actor=user)


@items_router.patch(
    "/{item_id}", response_model=ItemResponse, summary="修改收藏条目"
)
async def update_item(
    item_id: int,
    payload: ItemUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> ItemResponse:
    return await CollectionService(session).update_item(
        user.id, item_id, payload, actor=user
    )


@items_router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="取消收藏",
)
async def delete_item(
    item_id: int, session: DbSession, user: CurrentUser
) -> Response:
    await CollectionService(session).delete_item(user.id, item_id, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@items_router.post(
    "/batch",
    response_model=BatchItemResponse,
    summary="批量操作（MOVE / DELETE / MARK_READ / ADD_TAG / REMOVE_TAG）",
)
async def batch_items(
    payload: BatchItemRequest, session: DbSession, user: CurrentUser
) -> BatchItemResponse:
    return await CollectionService(session).batch_items(user.id, payload, actor=user)


# ----------------------------------------------------------------- stats


stats_router = APIRouter(tags=["collection"])


@stats_router.get("/stats", response_model=StatsResponse, summary="我的收藏统计")
async def get_stats(session: DbSession, user: CurrentUser) -> StatsResponse:
    return await CollectionService(session).get_stats(user.id)
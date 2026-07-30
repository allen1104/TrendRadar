"""source 路由（仅 ADMIN 写，EDITOR 可试跑 + 触发）。"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import PageParams, page_params
from app.core.schema import Page
from app.modules.admin.deps import AdminUser, DbSession, EditorUser
from app.modules.source.enums import Region, RunStatus, SourceCategory, TriggerType
from app.modules.source.schema import (
    RegisteredPluginInfo,
    RunLogResponse,
    SourceCreateRequest,
    SourceListItem,
    SourceResponse,
    SourceRunResponse,
    SourceTestResponse,
    SourceUpdateRequest,
)
from app.modules.source.service import SourceService

router = APIRouter(prefix="/admin/sources", tags=["admin:sources"])


# ------------------------------------------- 插件与采集源元数据


@router.get("/plugins", response_model=list[RegisteredPluginInfo], summary="可注册的采集器插件")
async def list_plugins(_: EditorUser, session: DbSession) -> list[RegisteredPluginInfo]:
    return await SourceService(session).list_registered()


@router.get(
    "",
    response_model=Page[SourceListItem],
    summary="采集源列表",
)
async def list_sources(
    _: EditorUser,
    session: DbSession,
    pagination: Annotated[PageParams, Depends(page_params)],
    region: Annotated[Region | None, Query()] = None,
    category: Annotated[SourceCategory | None, Query()] = None,
    enabled_only: Annotated[bool, Query(description="只看启用中")] = False,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[SourceListItem]:
    items = await SourceService(session).list(
        region=region,
        category=category,
        enabled_only=enabled_only,
        keyword=keyword,
    )
    total = len(items)
    return Page.create(items, total, pagination.page, pagination.size)


@router.get("/{source_id}", response_model=SourceResponse, summary="采集源详情")
async def get_source(source_id: int, _: EditorUser, session: DbSession) -> SourceResponse:
    return await SourceService(session).get(source_id)


# ------------------------------------------- CRUD（仅 ADMIN）


@router.post(
    "",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新建采集源",
)
async def create_source(
    payload: SourceCreateRequest, _: AdminUser, session: DbSession
) -> SourceResponse:
    return await SourceService(session).create(payload)


@router.patch(
    "/{source_id}", response_model=SourceResponse, summary="修改采集源"
)
async def update_source(
    source_id: int,
    payload: SourceUpdateRequest,
    _: AdminUser,
    session: DbSession,
) -> SourceResponse:
    return await SourceService(session).update(source_id, payload)


@router.delete(
    "/{source_id}", status_code=status.HTTP_204_NO_CONTENT, summary="软删除采集源"
)
async def delete_source(source_id: int, _: AdminUser, session: DbSession) -> None:
    await SourceService(session).delete(source_id)


# ------------------------------------------- 试跑 + 立即运行 + 日志


@router.post(
    "/{source_id}/test",
    response_model=SourceTestResponse,
    summary="试跑（不写库，跑一次真采集）",
)
async def test_source(
    source_id: int, _: EditorUser, session: DbSession
) -> SourceTestResponse:
    return await SourceService(session).test_connection(source_id)


@router.post(
    "/{source_id}/run",
    response_model=SourceRunResponse,
    summary="立即触发一次采集（异步 Celery 任务）",
)
async def run_source_now(
    source_id: int, _: EditorUser, session: DbSession
) -> SourceRunResponse:
    from app.modules.source.tasks import fetch_task

    task = fetch_task.delay(source_id, trigger_type=TriggerType.MANUAL.value)
    return SourceRunResponse(task_id=task.id, status="queued")


@router.get(
    "/{source_id}/logs",
    response_model=Page[RunLogResponse],
    summary="某采集源的运行日志",
)
async def list_source_logs(
    source_id: int,
    _: EditorUser,
    session: DbSession,
    pagination: Annotated[PageParams, Depends(page_params)],
    status: Annotated[RunStatus | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
) -> Page[RunLogResponse]:
    items, total = await SourceService(session).list_logs(
        source_id=source_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=pagination.page,
        size=pagination.size,
    )
    return Page.create(items, total, pagination.page, pagination.size)


@router.get(
    "/logs/{log_id}",
    response_model=RunLogResponse,
    summary="运行日志详情",
)
async def get_run_log(log_id: int, _: EditorUser, session: DbSession) -> RunLogResponse:
    return await SourceService(session).get_log(log_id)

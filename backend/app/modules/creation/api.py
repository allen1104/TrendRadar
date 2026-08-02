"""creation 路由。

7 端点按 SPEC-creation.md「后端接口」：
  GET    /creation/options                  (GUEST)
  POST   /creation/drafts                   (SSE 流式)
  GET    /creation/drafts                   (分页列表)
  GET    /creation/drafts/{id}              (详情)
  PATCH  /creation/drafts/{id}              (保存编辑)
  DELETE /creation/drafts/{id}
  POST   /creation/drafts/{id}/regenerate   (SSE 流式)
  GET    /creation/drafts/{id}/export       (4 种格式)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession as _AS  # noqa: N814

from app.db.session import get_db
from app.modules.auth.deps import CurrentUser, OptionalUser
from app.modules.creation.enums import ExportFormat, Platform, Style
from app.modules.creation.schema import (
    DraftCreateRequest,
    DraftDetail,
    DraftListResponse,
    DraftRegenerateRequest,
    DraftSummary,
    DraftUpdateRequest,
    OptionsResponse,
)
from app.modules.creation.service import CreationService

DbSession = Annotated[_AS, Depends(get_db)]

router = APIRouter(prefix="/creation", tags=["creation"])


# ----------------------------------------------------------------- SSE helper


async def _sse_stream(
    event_iter: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[str]:
    async for item in event_iter:
        ev = item["event"]
        payload = item["data"]
        line = json.dumps(payload, ensure_ascii=False)
        yield f"event: {ev}\ndata: {line}\n\n"


async def _make_disconnect_check(request: Request) -> Callable[[], Awaitable[bool]]:
    async def _check() -> bool:
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    return _check


# ----------------------------------------------------------------- options (GUEST)


@router.get(
    "/options",
    response_model=OptionsResponse,
    summary="平台与风格选项（GUEST 可访问）",
)
async def get_options(
    session: DbSession,
    _user: OptionalUser,
) -> OptionsResponse:
    return await CreationService(session).get_options()


# ----------------------------------------------------------------- 列表


@router.get(
    "/drafts",
    response_model=DraftListResponse,
    summary="我的草稿列表（分页）",
)
async def list_drafts(
    session: DbSession,
    user: CurrentUser,
    event_id: int | None = None,
    platform: Platform | None = None,
    style: Style | None = None,
    keyword: str | None = None,
    sort: Annotated[str, Query()] = "-created_at",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DraftListResponse:
    svc = CreationService(session)
    rows, total = await svc.list_drafts(
        user.id,
        event_id=event_id,
        platform=platform.value if platform else None,
        style=style.value if style else None,
        keyword=keyword,
        sort=sort,
        page=page,
        size=size,
    )
    return DraftListResponse(
        items=[DraftSummary(**r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
    )


# ----------------------------------------------------------------- 创建（SSE）


@router.post(
    "/drafts",
    summary="生成草稿（SSE 流式：start / outline / delta / done / error）",
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "SSE 流",
        }
    },
)
async def create_draft(
    payload: DraftCreateRequest,
    session: DbSession,
    user: CurrentUser,
    request: Request,
) -> StreamingResponse:
    svc = CreationService(session)
    disconnect = await _make_disconnect_check(request)
    event_iter = svc.stream_create(
        user_id=user.id,
        payload=payload,
        is_disconnected=disconnect,
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


# ----------------------------------------------------------------- 详情


@router.get(
    "/drafts/{draft_id}",
    response_model=DraftDetail,
    summary="草稿详情（仅本人）",
)
async def get_draft(
    draft_id: int,
    session: DbSession,
    user: CurrentUser,
) -> DraftDetail:
    d = await CreationService(session).get_draft(user.id, draft_id)
    return DraftDetail(**d)


# ----------------------------------------------------------------- 编辑保存


@router.patch(
    "/drafts/{draft_id}",
    response_model=DraftDetail,
    summary="保存编辑（title / content_edited）",
)
async def update_draft(
    draft_id: int,
    payload: DraftUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> DraftDetail:
    d = await CreationService(session).update_draft(user.id, draft_id, payload)
    return DraftDetail(**d)


# ----------------------------------------------------------------- 删除


@router.delete(
    "/drafts/{draft_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除草稿（本人）",
)
async def delete_draft(
    draft_id: int,
    session: DbSession,
    user: CurrentUser,
) -> Response:
    await CreationService(session).delete_draft(user.id, draft_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------- 重新生成（SSE）


@router.post(
    "/drafts/{draft_id}/regenerate",
    summary="重新生成（SSE 流式）",
)
async def regenerate_draft(
    draft_id: int,
    payload: DraftRegenerateRequest,
    session: DbSession,
    user: CurrentUser,
    request: Request,
) -> StreamingResponse:
    svc = CreationService(session)
    disconnect = await _make_disconnect_check(request)
    event_iter = svc.stream_regenerate(
        user_id=user.id,
        draft_id=draft_id,
        payload=payload,
        is_disconnected=disconnect,
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


# ----------------------------------------------------------------- 导出


@router.get(
    "/drafts/{draft_id}/export",
    summary="导出草稿（MARKDOWN / HTML / WECHAT_HTML / TXT）",
    responses={
        200: {
            "content": {
                "text/markdown": {},
                "text/html": {},
                "text/plain": {},
            },
            "description": "文件下载",
        }
    },
)
async def export_draft(
    draft_id: int,
    session: DbSession,
    user: CurrentUser,
    format: Annotated[ExportFormat, Query()],
) -> Response:
    data, content_type, filename = await CreationService(session).export_draft(
        user.id, draft_id, format.value
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )
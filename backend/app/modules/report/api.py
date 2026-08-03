"""report 路由。

按 SPEC-report.md「后端接口」共 ~14 端点：

  公开（GUEST）：
    GET    /reports                       列表（只返回 PUBLISHED）
    GET    /reports/latest                各类型最新
    GET    /reports/{id}                  详情
    GET    /reports/{id}/export           导出（4 格式）
    GET    /reports/rss                   RSS XML

  登录用户：
    GET    /reports/subscription          我的订阅
    PUT    /reports/subscription          保存订阅
    POST   /reports/subscription/rss-token/reset  重置 RSS 令牌

  EDITOR 及以上：
    POST   /admin/reports/generate        手动触发生成
    PATCH  /admin/reports/{id}            编辑日报
    POST   /admin/reports/{id}/publish    发布
    POST   /admin/reports/{id}/unpublish  撤回
    PATCH  /admin/reports/{id}/items/{itemId}  编辑条目
    DELETE /admin/reports/{id}/items/{itemId}  删除条目
    POST   /admin/reports/{id}/items      添加条目
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import Response as FastResponse
from sqlalchemy.ext.asyncio import AsyncSession as _AS  # noqa: N814

from app.db.session import get_db
from app.modules.auth.deps import CurrentUser, OptionalUser
from app.modules.report.enums import ExportFormat, ReportType
from app.modules.report.model import Report
from app.modules.report.schema import (
    ReportDetail,
    ReportGenerateRequest,
    ReportItemAddRequest,
    ReportItemSummary,
    ReportItemUpdateRequest,
    ReportLatestItem,
    ReportListResponse,
    ReportSection,
    ReportSummary,
    ReportUpdateRequest,
    RssTokenResetResponse,
    SubscriptionPutRequest,
    SubscriptionResponse,
)
from app.modules.report.service import ReportService

DbSession = Annotated[_AS, Depends(get_db)]

router = APIRouter(prefix="/reports", tags=["report"])
admin_router = APIRouter(prefix="/admin/reports", tags=["admin-report"])


# ============================================================ 工具


def _report_summary(r: Report) -> ReportSummary:
    return ReportSummary(
        id=r.id,
        report_type=ReportType(r.report_type),
        report_date=r.report_date,
        title=r.title,
        intro=r.intro,
        item_count=int(r.item_count or 0),
        status=r.status,  # type: ignore[arg-type]
        published_at=r.published_at,
        view_count=int(r.view_count or 0),
    )


def _report_detail(
    r: Report, sections: list[ReportSection]
) -> ReportDetail:
    return ReportDetail(
        id=r.id,
        report_type=ReportType(r.report_type),
        report_date=r.report_date,
        title=r.title,
        intro=r.intro,
        outro=r.outro,
        content_md=r.content_md,
        content_edited=r.content_edited,
        item_count=int(r.item_count or 0),
        status=r.status,  # type: ignore[arg-type]
        published_at=r.published_at,
        view_count=int(r.view_count or 0),
        model_alias=r.model_alias,
        cost_usd=float(r.cost_usd or 0),
        sections=sections,
    )


# ============================================================ 公开：列表


@router.get(
    "",
    response_model=ReportListResponse,
    summary="日报列表（GUEST 只看 PUBLISHED；EDITOR 可按 status 过滤）",
)
async def list_reports(
    session: DbSession,
    _user: OptionalUser,
    report_type: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReportListResponse:
    svc = ReportService(session)
    # 校验 report_type
    if report_type is not None and report_type not in {t.value for t in ReportType}:
        from app.modules.report.exceptions import InvalidReportTypeError

        raise InvalidReportTypeError
    rows, total = await svc.list_reports(
        report_type=report_type,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
        only_published=True,  # GUEST 默认只看 PUBLISHED
        page=page,
        size=size,
    )
    return ReportListResponse(
        items=[_report_summary(r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
    )


@router.get(
    "/latest",
    response_model=list[ReportLatestItem],
    summary="各类型最新一期日报（首页卡片用）",
)
async def latest_reports(session: DbSession) -> list[ReportLatestItem]:
    svc = ReportService(session)
    rows = await svc.list_latest()
    return [
        ReportLatestItem(
            report_type=ReportType(r.report_type),
            id=r.id,
            title=r.title,
            report_date=r.report_date,
            item_count=int(r.item_count or 0),
            published_at=r.published_at,
        )
        for r in rows
    ]


# ============================================================ 公开：RSS（必须在 /{report_id} 之前注册，否则被匹配为 report_id）


@router.get(
    "/rss",
    summary="RSS 2.0 源（无 token 公开；有 token 私有）",
    response_class=FastResponse,
)
async def rss_feed(
    session: DbSession,
    token: Annotated[str | None, Query()] = None,
) -> Response:
    svc = ReportService(session)
    xml_text = await svc.build_rss_for_token(token)
    return Response(
        content=xml_text,
        media_type="application/rss+xml; charset=utf-8",
    )


# ============================================================ 登录：订阅（必须在 /{report_id} 之前注册）


@router.get(
    "/subscription",
    response_model=SubscriptionResponse | None,
    summary="我的订阅设置",
)
async def get_my_subscription(
    session: DbSession,
    user: CurrentUser,
) -> SubscriptionResponse | None:
    return await ReportService(session).get_subscription(user.id)


@router.put(
    "/subscription",
    response_model=SubscriptionResponse,
    summary="保存订阅设置",
)
async def put_my_subscription(
    payload: SubscriptionPutRequest,
    session: DbSession,
    user: CurrentUser,
) -> SubscriptionResponse:
    return await ReportService(session).put_subscription(
        user_id=user.id,
        report_types=[t.value for t in payload.report_types],
        channel=payload.channel.value,
        webhook_url=payload.webhook_url,
        enabled=payload.enabled,
    )


@router.post(
    "/subscription/rss-token/reset",
    response_model=RssTokenResetResponse,
    summary="重置 RSS 令牌（旧链接立即失效）",
)
async def reset_rss_token(
    session: DbSession,
    user: CurrentUser,
) -> RssTokenResetResponse:
    sub = await ReportService(session).reset_rss_token(user.id)
    from app.modules.report.service import ReportService as _RS

    resp = _RS(session)._sub_to_response(sub)  # type: ignore[attr-defined]
    return RssTokenResetResponse(
        rss_token=sub.rss_token or "",
        rss_url=resp.rss_url or "",
    )


# ============================================================ 公开：详情（动态路由在所有字面量之后）


@router.get(
    "/{report_id}",
    response_model=ReportDetail,
    summary="日报详情（含 sections）",
)
async def get_report(
    report_id: int,
    session: DbSession,
    request: Request,
    user: OptionalUser,
) -> ReportDetail:
    from app.core.redis import redis_client

    svc = ReportService(session)
    is_editor = user is not None and user.role in {"EDITOR", "ADMIN"}
    r, sections, _ = await svc.get_report_with_sections(
        report_id, is_editor=is_editor
    )
    # view_count 自增（同一 IP 10 分钟内只计一次）
    try:
        ip = request.client.host if request.client else "unknown"
        key = f"report:view:{report_id}:{ip}"
        seen = await redis_client.get(key)
        if not seen:
            await svc.report_repo.increment_view_count(report_id)
            await session.commit()
            await redis_client.set(key, "1", ex=600)
    except Exception:
        pass
    return _report_detail(r, sections)


# ============================================================ 公开：导出


@router.get(
    "/{report_id}/export",
    summary="导出日报（MARKDOWN / HTML / PDF / WECHAT_HTML）",
    responses={
        200: {
            "content": {
                "text/markdown": {},
                "text/html": {},
                "application/pdf": {},
            },
            "description": "文件下载",
        }
    },
)
async def export_report(
    report_id: int,
    session: DbSession,
    _user: OptionalUser,
    format: Annotated[ExportFormat, Query()],
) -> Response:
    svc = ReportService(session)
    data, content_type, filename = await svc.export(
        report_id=report_id,
        format=format.value,
        is_editor=False,
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )


# ============================================================ EDITOR：管理


@admin_router.post(
    "/generate",
    summary="手动触发生成日报",
    responses={
        200: {
            "description": "生成完成",
        },
        202: {"description": "已加入异步队列"},
    },
)
async def admin_generate(
    payload: ReportGenerateRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict[str, Any]:
    """手动生成：同步路径（LLM 调用可能 30s+）。由调用方控制是否走 Celery 异步。
    一期直接同步生成。
    """
    svc = ReportService(session)
    try:
        r = await svc.generate_report(
            report_type=payload.report_type.value,
            report_date=payload.report_date,
            force=payload.force,
            user_id=user.id,
        )
        return {"reportId": r.id, "status": r.status}
    except Exception as exc:
        # CandidatesInsufficientError 也走这里
        from app.modules.report.exceptions import CandidatesInsufficientError

        if isinstance(exc, CandidatesInsufficientError):
            return {
                "skipped": True,
                "reportType": payload.report_type.value,
                "reportDate": str(payload.report_date),
                "detail": exc.detail,
            }
        raise


@admin_router.patch(
    "/{report_id}",
    response_model=ReportDetail,
    summary="编辑日报（标题/导语/结尾/正文）",
)
async def admin_update_report(
    report_id: int,
    payload: ReportUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> ReportDetail:
    svc = ReportService(session)
    r = await svc.update_report(
        user_id=user.id,
        report_id=report_id,
        title=payload.title,
        intro=payload.intro,
        outro=payload.outro,
        content_edited=payload.content_edited,
    )
    sections, _ = await svc.item_repo.list_for_report(r.id), None
    # 简化：编辑后 sections 与原 item 列表一致
    items = await svc.item_repo.list_for_report(r.id)
    from app.modules.report.service import ReportSection

    grouped: dict[str, list[ReportItemSummary]] = {}
    for it in items:
        grouped.setdefault(it.section, []).append(
            ReportItemSummary(
                id=it.id,
                event_id=it.event_id,
                section=it.section,
                sort_order=it.sort_order,
                headline=it.headline,
                brief=it.brief,
                comment=it.comment,
                is_top=it.is_top,
            )
        )
    sec_objs = [ReportSection(name=n, items=grouped[n]) for n in grouped]
    return _report_detail(r, sec_objs)


@admin_router.post(
    "/{report_id}/publish",
    response_model=ReportDetail,
    summary="发布日报",
)
async def admin_publish(
    report_id: int,
    session: DbSession,
    user: CurrentUser,
) -> ReportDetail:
    svc = ReportService(session)
    r = await svc.publish(user_id=user.id, report_id=report_id)
    items = await svc.item_repo.list_for_report(r.id)
    from app.modules.report.service import ReportSection

    grouped: dict[str, list[ReportItemSummary]] = {}
    for it in items:
        grouped.setdefault(it.section, []).append(
            ReportItemSummary(
                id=it.id,
                event_id=it.event_id,
                section=it.section,
                sort_order=it.sort_order,
                headline=it.headline,
                brief=it.brief,
                comment=it.comment,
                is_top=it.is_top,
            )
        )
    sec_objs = [ReportSection(name=n, items=grouped[n]) for n in grouped]
    return _report_detail(r, sec_objs)


@admin_router.post(
    "/{report_id}/unpublish",
    response_model=ReportDetail,
    summary="撤回发布（仅 ADMIN）",
)
async def admin_unpublish(
    report_id: int,
    session: DbSession,
    user: CurrentUser,
) -> ReportDetail:
    from app.modules.auth.enums import Role

    if user.role != Role.ADMIN.value:
        from app.core.exceptions import AppException

        raise AppException(
            status_code=403,
            error_code="ADMIN_ONLY",
            detail="仅 ADMIN 可撤回发布",
        )
    svc = ReportService(session)
    r = await svc.unpublish(user_id=user.id, report_id=report_id)
    items = await svc.item_repo.list_for_report(r.id)
    from app.modules.report.service import ReportSection

    grouped: dict[str, list[ReportItemSummary]] = {}
    for it in items:
        grouped.setdefault(it.section, []).append(
            ReportItemSummary(
                id=it.id,
                event_id=it.event_id,
                section=it.section,
                sort_order=it.sort_order,
                headline=it.headline,
                brief=it.brief,
                comment=it.comment,
                is_top=it.is_top,
            )
        )
    sec_objs = [ReportSection(name=n, items=grouped[n]) for n in grouped]
    return _report_detail(r, sec_objs)


@admin_router.patch(
    "/{report_id}/items/{item_id}",
    response_model=ReportItemSummary,
    summary="编辑日报条目",
)
async def admin_update_item(
    report_id: int,
    item_id: int,
    payload: ReportItemUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> ReportItemSummary:
    svc = ReportService(session)
    it = await svc.update_item(
        user_id=user.id,
        report_id=report_id,
        item_id=item_id,
        headline=payload.headline,
        brief=payload.brief,
        comment=payload.comment,
        section=payload.section,
        sort_order=payload.sort_order,
        is_top=payload.is_top,
    )
    return ReportItemSummary(
        id=it.id,
        event_id=it.event_id,
        section=it.section,
        sort_order=it.sort_order,
        headline=it.headline,
        brief=it.brief,
        comment=it.comment,
        is_top=it.is_top,
    )


@admin_router.delete(
    "/{report_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除日报条目",
)
async def admin_delete_item(
    report_id: int,
    item_id: int,
    session: DbSession,
    user: CurrentUser,
) -> Response:
    await ReportService(session).delete_item(
        user_id=user.id, report_id=report_id, item_id=item_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/{report_id}/items",
    response_model=ReportItemSummary,
    summary="添加日报条目",
)
async def admin_add_item(
    report_id: int,
    payload: ReportItemAddRequest,
    session: DbSession,
    user: CurrentUser,
) -> ReportItemSummary:
    svc = ReportService(session)
    it = await svc.add_item(
        user_id=user.id,
        report_id=report_id,
        event_id=payload.event_id,
        section=payload.section,
        headline=payload.headline,
        brief=payload.brief,
    )
    return ReportItemSummary(
        id=it.id,
        event_id=it.event_id,
        section=it.section,
        sort_order=it.sort_order,
        headline=it.headline,
        brief=it.brief,
        comment=it.comment,
        is_top=it.is_top,
    )

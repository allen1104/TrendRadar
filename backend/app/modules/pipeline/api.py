"""pipeline 模块路由：运维 / 编辑。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.core.pagination import PageParams, page_params
from app.db.session import AsyncSessionLocal
from app.modules.admin.deps import DbSession, EditorUser
from app.modules.pipeline.enums import ArticleStatus, EventStatus, MatchLevel
from app.modules.pipeline.exceptions import (
    ArticleNotInEventError,
    CannotMergeSelfError,
    CannotSplitAllError,
    EventNotFoundError,
    FullRerunRequiresSinceError,
    InvalidPipelineStageError,
)
from app.modules.pipeline.model import (
    Article,
    Event,
    EventArticle,
    Tag,
)
from app.modules.pipeline.repository import ArticleRepository
from app.modules.pipeline.schema import (
    EventMergeRequest,
    EventSplitRequest,
    PipelineRerunRequest,
    PipelineRerunResponse,
    PipelineStats,
    SplitResult,
)

router = APIRouter(prefix="/admin/pipeline", tags=["admin:pipeline"])
events_router = APIRouter(prefix="/events", tags=["pipeline:events"])


# ------------------------------------------- 运维


@router.post(
    "/rerun",
    response_model=PipelineRerunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="手动重跑流水线某个阶段",
)
async def rerun(
    payload: PipelineRerunRequest, _: EditorUser
) -> PipelineRerunResponse:
    from app.modules.pipeline.tasks import rerun_task

    if payload.stage not in ("CLEAN", "EMBED", "DEDUPE", "RANK"):
        raise InvalidPipelineStageError
    if payload.scope == "ALL" and not payload.since:
        raise FullRerunRequiresSinceError
    task = rerun_task.delay(
        stage=payload.stage,
        scope=payload.scope,
        ids=payload.ids,
        since=payload.since.isoformat() if payload.since else None,
    )
    return PipelineRerunResponse(task_id=task.id, queued_count=len(payload.ids or []))


@router.get("/stats", response_model=PipelineStats, summary="流水线健康度")
async def stats(_: EditorUser, session: DbSession) -> PipelineStats:
    from app.modules.pipeline.model import Event as EventModel

    # article by status
    art_rows = (await session.execute(
        select(Article.status, func.count(Article.id))
        .where(Article.is_deleted.is_(False))
        .group_by(Article.status)
    )).all()
    art_by = {s: c for s, c in art_rows}
    # event by status
    ev_rows = (await session.execute(
        select(EventModel.status, func.count(EventModel.id))
        .where(EventModel.is_deleted.is_(False))
        .group_by(EventModel.status)
    )).all()
    ev_by = {s: c for s, c in ev_rows}
    # today new articles / events
    today = datetime.utcnow().date()
    today_articles = (await session.execute(
        select(func.count(Article.id)).where(
            Article.is_deleted.is_(False),
            func.date(Article.created_at) == today,
        )
    )).scalar() or 0
    today_events = (await session.execute(
        select(func.count(EventModel.id)).where(
            EventModel.is_deleted.is_(False),
            func.date(EventModel.created_at) == today,
        )
    )).scalar() or 0
    # avg source per event
    avg_spe = (await session.execute(
        select(func.avg(EventModel.source_count)).where(EventModel.is_deleted.is_(False))
    )).scalar() or 0
    # dedupe rate
    total_articles = sum(art_by.values()) or 1
    clustered = art_by.get(ArticleStatus.CLUSTERED.value, 0)
    dedupe_rate = clustered / total_articles
    # match level distribution
    match_rows = (await session.execute(
        select(EventArticle.match_level, func.count(EventArticle.id))
        .where(EventArticle.is_deleted.is_(False))
        .group_by(EventArticle.match_level)
    )).all()
    match_dist = {s: c for s, c in match_rows}

    return PipelineStats(
        article_by_status=art_by,
        event_by_status=ev_by,
        today_new_articles=today_articles,
        today_new_events=today_events,
        avg_source_per_event=float(avg_spe),
        dedupe_rate=dedupe_rate,
        match_level_distribution=match_dist,
    )


# ------------------------------------------- 事件编辑（拆分 / 合并）


@events_router.post(
    "/{event_id}/split",
    response_model=SplitResult,
    summary="把指定文章从事件拆出来，新立一个事件",
)
async def split_event(
    event_id: int, payload: EventSplitRequest, _: EditorUser, session: DbSession
) -> SplitResult:
    src = await session.get(Event, event_id)
    if src is None or src.is_deleted:
        raise EventNotFoundError

    # 校验所有文章属于源 event
    rows = (await session.execute(
        select(Article).where(
            Article.id.in_(payload.article_ids),
            Article.event_id == event_id,
            Article.is_deleted.is_(False),
        )
    )).scalars().all()
    if len(rows) != len(payload.article_ids):
        raise ArticleNotInEventError

    # 拆走 = 所有文章
    total_in_event = (await session.execute(
        select(func.count(Article.id)).where(
            Article.event_id == event_id, Article.is_deleted.is_(False),
        )
    )).scalar() or 0
    if len(payload.article_ids) >= total_in_event:
        raise CannotSplitAllError

    # 新建目标 event
    new_event = Event(
        title=payload.new_event_title[:500],
        primary_article_id=payload.article_ids[0],
        region=src.region,
        categories=src.categories,
        source_count=1,
        article_count=len(payload.article_ids),
        first_seen_at=min(a.published_at for a in rows),
        last_seen_at=max(a.published_at for a in rows),
        status=EventStatus.PENDING_AI.value,
    )
    session.add(new_event)
    await session.flush()

    # 搬 article + 写 event_article
    for a in rows:
        a.event_id = new_event.id
        # 新建 event_article 记录
        session.add(EventArticle(
            event_id=new_event.id, article_id=a.id,
            match_level=MatchLevel.MANUAL.value, is_primary=(a.id == payload.article_ids[0]),
        ))
    # 删源 event 的 event_article 行
    await session.execute(
        EventArticle.__table__.delete().where(
            EventArticle.event_id == event_id,
            EventArticle.article_id.in_(payload.article_ids),
        )
    )
    # 重算源 event 计数
    src.article_count = total_in_event - len(payload.article_ids)
    src.last_seen_at = (
        await session.execute(
            select(func.max(Article.published_at)).where(
                Article.event_id == event_id, Article.is_deleted.is_(False),
            )
        )
    ).scalar() or src.last_seen_at
    await session.commit()
    return SplitResult(
        source_event={"id": src.id, "article_count": src.article_count},
        new_event={"id": new_event.id, "article_count": new_event.article_count, "status": new_event.status},
    )


@events_router.post(
    "/merge",
    summary="合并两个事件",
)
async def merge_events(
    payload: EventMergeRequest, _: EditorUser, session: DbSession
) -> dict:
    if payload.source_id == payload.target_id:
        raise CannotMergeSelfError
    src = await session.get(Event, payload.source_id)
    tgt = await session.get(Event, payload.target_id)
    if src is None or src.is_deleted:
        raise EventNotFoundError
    if tgt is None or tgt.is_deleted:
        raise EventNotFoundError

    # 把 source 的所有 article 移到 target
    articles = (await session.execute(
        select(Article).where(
            Article.event_id == payload.source_id, Article.is_deleted.is_(False),
        )
    )).scalars().all()
    for a in articles:
        a.event_id = payload.target_id
        # 重新写一条 event_article（MATCH_LEVEL=MANUAL）
        session.add(EventArticle(
            event_id=payload.target_id, article_id=a.id,
            match_level=MatchLevel.MANUAL.value, is_primary=False,
        ))
    # 删 source 的 event_article
    await session.execute(
        EventArticle.__table__.delete().where(
            EventArticle.event_id == payload.source_id,
        )
    )
    # 重算 target 计数
    tgt.article_count = (await session.execute(
        select(func.count(Article.id)).where(
            Article.event_id == payload.target_id, Article.is_deleted.is_(False),
        )
    )).scalar() or 0
    tgt.source_count = (await session.execute(
        select(func.count(func.distinct(Article.source_id))).where(
            Article.event_id == payload.target_id, Article.is_deleted.is_(False),
        )
    )).scalar() or 1
    tgt.last_seen_at = max(
        (await session.execute(
            select(func.max(Article.published_at)).where(
                Article.event_id == payload.target_id, Article.is_deleted.is_(False),
            )
        )).scalar() or tgt.last_seen_at,
        tgt.last_seen_at,
    )
    # 软删除 source event
    src.is_deleted = True
    await session.commit()
    return {"target_event_id": payload.target_id, "merged_articles": len(articles)}
"""pipeline 模块 Celery 任务：clean / embed / dedupe / analyze / rank / archive / rerun。"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.pipeline.enums import (
    ArticleStatus,
    EventRegion,
    EventStatus,
    MatchLevel,
)
from app.modules.pipeline.model import Article, ArticleEmbedding, Event, EventArticle
from app.modules.pipeline.repository import (
    ArticleEmbeddingRepository,
    ArticleRepository,
)
from app.modules.pipeline.service import PipelineService
from app.modules.admin.decorator import tracked_task
from app.worker.celery_app import celery_app

configure_logging()
log = structlog.get_logger()


def _run(coro):  # type: ignore[no-untyped-def]
    """同步 Celery 任务里跑 async 协程。完成后 dispose 引擎，释放绑定到已关闭 loop 的连接。"""
    from app.db.session import engine
    try:
        return asyncio.run(coro)
    finally:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            pass


# ---------------------------------------------------------------- 清洗


@tracked_task(manual_triggerable=True, display_name="清洗 RAW 文章")
@celery_app.task(name="pipeline.clean", bind=True, max_retries=2, default_retry_delay=30)
def clean_task(self, article_ids: list[int]) -> dict[str, int]:
    """清洗 RAW → CLEANED。成功后链式触发 embed_task。"""
    start = time.perf_counter()
    async def _go():
        async with AsyncSessionLocal() as session:
            svc = PipelineService(session)
            return await svc.clean_articles(article_ids)

    try:
        cleaned, discarded, failed = _run(_go())
        log.info(
            "pipeline.clean.done",
            input=len(article_ids),
            cleaned=cleaned,
            discarded=discarded,
            failed=failed,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
        # 链式触发 embed：仅送 CLEANED 的
        from app.modules.pipeline.repository import ArticleRepository
        from app.modules.pipeline.enums import ArticleStatus

        async def _collect_cleaned():
            async with AsyncSessionLocal() as session:
                arts = await ArticleRepository(session).list_by_status(
                    ArticleStatus.CLEANED, limit=500
                )
                # 仅本次涉及的 ids
                s = set(article_ids)
                return [a.id for a in arts if a.id in s]

        cleaned_ids = _run(_collect_cleaned())
        if cleaned_ids:
            embed_task.delay(cleaned_ids)
            log.info("pipeline.embed.queued", count=len(cleaned_ids))
        return {"cleaned": cleaned, "discarded": discarded, "failed": failed}
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline.clean.error", error=f"{exc.__class__.__name__}: {exc}")
        raise self.retry(exc=exc) from exc


# ---------------------------------------------------------------- 向量化


@tracked_task(manual_triggerable=True, display_name="生成向量")
@celery_app.task(name="pipeline.embed", bind=True, max_retries=3, default_retry_delay=30)
def embed_task(self, article_ids: list[int], model_alias: str = "local-bge-m3") -> dict[str, int]:
    """CLEANED → EMBEDDED。批量 32 条调 LocalEmbeddingProvider。

    失败重试；3 次仍失败 → 置 FAILED。
    注意：直接走 LocalEmbeddingProvider（不走 LLMGateway），避免 ai_provider 关系的异步懒加载问题。
    """
    start = time.perf_counter()

    async def _go():
        from app.modules.ai.providers.local_embedding import LocalEmbeddingProvider
        from app.modules.ai.gateway.base import get_provider_class

        async with AsyncSessionLocal() as session:
            art_repo = ArticleRepository(session)
            emb_repo = ArticleEmbeddingRepository(session)
            articles = await art_repo.list_by_ids(article_ids)
            if not articles:
                return 0, 0
            # 仅处理 CLEANED
            targets = [a for a in articles if a.status == ArticleStatus.CLEANED.value]
            if not targets:
                return 0, 0
            # 拼文本
            texts = [f"{(a.title or '').strip()}\n{(a.summary or '')[:500]}" for a in targets]
            BATCH = 32
            succeeded = 0
            failed = 0
            provider = LocalEmbeddingProvider(dim=1024)
            for i in range(0, len(targets), BATCH):
                batch_arts = targets[i : i + BATCH]
                batch_texts = texts[i : i + BATCH]
                try:
                    vectors = await provider.embed(batch_texts, model="bge-m3")
                    for art, vec in zip(batch_arts, vectors, strict=True):
                        try:
                            await emb_repo.upsert(
                                art.id, model=model_alias, embedding=vec, dim=len(vec)
                            )
                            await art_repo.update_status(art.id, ArticleStatus.EMBEDDED)
                            succeeded += 1
                        except Exception as exc:  # noqa: BLE001
                            log.warning(
                                "pipeline.embed.row_failed",
                                article_id=art.id,
                                error=f"{exc.__class__.__name__}: {exc}",
                            )
                            failed += 1
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "pipeline.embed.batch_failed",
                        size=len(batch_arts),
                        error=f"{exc.__class__.__name__}: {exc}",
                    )
                    failed += len(batch_arts)
            await session.commit()
            return succeeded, failed

    try:
        succeeded, failed = _run(_go())
        log.info(
            "pipeline.embed.done",
            succeeded=succeeded,
            failed=failed,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
        # 链式触发 dedupe
        dedupe_task.delay()
        return {"succeeded": succeeded, "failed": failed}
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline.embed.error", error=f"{exc.__class__.__name__}: {exc}")
        raise self.retry(exc=exc) from exc


# ---------------------------------------------------------------- 去重聚合


@tracked_task(manual_triggerable=True, display_name="三级去重聚合")
@celery_app.task(name="pipeline.dedupe", bind=True, max_retries=2, default_retry_delay=60)
def dedupe_task(self) -> dict[str, int]:
    """三级级联去重：指纹 → pg_trgm 标题 → pgvector 余弦。

    EMBEDDED → CLUSTERED；新建 event(status=PENDING_AI)。
    末尾触发 analyze_event_task 对 PENDING_AI 事件做 AI 分析。
    """
    start = time.perf_counter()
    result = _run(_async_dedupe())
    log.info(
        "pipeline.dedupe.done",
        duration_ms=int((time.perf_counter() - start) * 1000),
        **result,
    )
    return result


async def _async_dedupe() -> dict[str, int]:
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    merged = 0
    created = 0
    failed = 0
    async with AsyncSessionLocal() as session:
        art_repo = ArticleRepository(session)
        # 1. 拿所有 EMBEDDED 的 article（按 published_at 升序）
        articles = await art_repo.list_by_status(ArticleStatus.EMBEDDED, limit=500)
        for art in articles:
            try:
                outcome = await _cluster_one(session, art)
                if outcome == "merged":
                    merged += 1
                elif outcome == "created":
                    created += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "pipeline.dedupe.row_failed",
                    article_id=art.id,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
                failed += 1
        await session.commit()

        # 2. 给所有 PENDING_AI 的 event 排队 AI 分析
        from app.modules.pipeline.model import Event as EventModel

        pending_stmt = select(EventModel.id).where(
            EventModel.status == EventStatus.PENDING_AI.value,
            EventModel.is_deleted.is_(False),
        )
        pending_ids = [r[0] for r in (await session.execute(pending_stmt)).all()]

    # 在 celery 任务里串行分析（本地 embedding 0 token，但防止 LLM 风暴用每事件 1 任务）
    for eid in pending_ids:
        analyze_event_task.delay(eid)

    # 链式触发 rank
    if merged or created:
        rank_task.delay()

    return {"merged": merged, "created": created, "failed": failed, "pending_ai": len(pending_ids)}


async def _cluster_one(session, art: Article) -> str:
    """单篇 article 的聚合决策：返回 "merged" / "created"。"""
    from sqlalchemy import select, update, func

    from app.modules.pipeline.model import (
        Event as EventModel,
        EventArticle as EventArticleModel,
    )

    # ----- Level 1 — 指纹：title_hash 或 url_hash 命中 -----
    fp_stmt = (
        select(EventArticleModel.event_id, EventArticleModel.event_id.label("eid"))
        .join(EventModel, EventModel.id == EventArticleModel.event_id)
        .where(
            EventArticleModel.is_deleted.is_(False),
            EventModel.is_deleted.is_(False),
            EventModel.is_hidden.is_(False),
            EventModel.status != EventStatus.ARCHIVED.value,
        )
        .join(Article, Article.id == EventArticleModel.article_id)
        .where(Article.title_hash == art.title_hash)
        .limit(1)
    )
    row = (await session.execute(fp_stmt)).first()
    if row is not None:
        return await _merge_into_event(session, art, row[0], MatchLevel.FINGERPRINT, None)

    # url_hash 已在入库时去重 → 不用再查

    # ----- Level 2 — pg_trgm 标题相似 -----
    # 仅查近 7 天活跃事件（聚合时间窗口 72h 取更宽以照顾旧文）
    since = datetime.now(timezone.utc) - timedelta(days=7)
    trgm_sql = select(
        EventModel.id,
        EventModel.last_seen_at,
        func.similarity(EventModel.title, art.title).label("sim"),
    ).where(
        EventModel.is_deleted.is_(False),
        EventModel.is_hidden.is_(False),
        EventModel.last_seen_at >= since,
        func.similarity(EventModel.title, art.title) > 0.35,
    ).order_by(func.similarity(EventModel.title, art.title).desc()).limit(20)

    rows = (await session.execute(trgm_sql)).all()
    if rows:
        best = rows[0]
        if best.sim > 0.75:
            return await _merge_into_event(session, art, best[0], MatchLevel.TITLE, float(best.sim))

    # ----- Level 3 — pgvector 余弦 -----
    from app.modules.pipeline.repository import ArticleEmbeddingRepository

    emb_repo = ArticleEmbeddingRepository(session)
    emb_vec = await emb_repo.get_embedding(art.id)
    if emb_vec is not None and rows:
        vec_sql = select(
            EventModel.id,
            EventArticleModel.similarity,
        ).join(
            EventArticleModel, EventArticleModel.event_id == EventModel.id
        ).join(
            ArticleEmbedding, ArticleEmbedding.article_id == EventArticleModel.article_id
        ).where(
            EventModel.is_deleted.is_(False),
            EventModel.is_hidden.is_(False),
            EventModel.last_seen_at >= since,
            sa_text("article_embedding.embedding IS NOT NULL"),
            EventArticleModel.is_primary.is_(True),
        ).order_by(
            sa_text("article_embedding.embedding <=> CAST(:vec AS vector)")
        ).limit(5)
        vec_rows = (await session.execute(vec_sql, {"vec": "[" + ",".join(f"{v:.6f}" for v in emb_vec) + "]"})).all()
        for vid, prev_sim in vec_rows:
            # 计算真实余弦
            cos_row = (
                await session.execute(
                    sa_text(
                        "SELECT 1 - (embedding <=> CAST(:vec AS vector)) FROM article_embedding WHERE article_id = :aid AND is_deleted = false"
                    ),
                    {"vec": "[" + ",".join(f"{v:.6f}" for v in emb_vec) + "]", "aid": art.id},
                )
            ).first()
            cos = cos_row[0] if cos_row else 0.0
            if cos > 0.85:
                return await _merge_into_event(session, art, vid, MatchLevel.VECTOR, float(cos))

    # ----- 新建 event -----
    new_event = EventModel(
        title=art.title[:500],
        primary_article_id=art.id,
        region=EventRegion.GLOBAL.value,  # 来源 region 由调用方补；简化版默认 GLOBAL
        categories=[],
        source_count=1,
        article_count=1,
        first_seen_at=art.published_at,
        last_seen_at=art.published_at,
        status=EventStatus.PENDING_AI.value,
    )
    session.add(new_event)
    await session.flush()
    ea = EventArticleModel(
        event_id=new_event.id,
        article_id=art.id,
        match_level=MatchLevel.FINGERPRINT.value,
        similarity=None,
        is_primary=True,
    )
    session.add(ea)
    art.event_id = new_event.id
    art.status = ArticleStatus.CLUSTERED.value
    await session.flush()
    return "created"


async def _merge_into_event(session, art: Article, event_id: int, level: MatchLevel, sim: float | None) -> str:
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.modules.pipeline.model import (
        Event as EventModel,
        EventArticle as EventArticleModel,
    )

    # 是否已挂过（idempotent）
    exists = (
        await session.execute(
            select(EventArticleModel.id).where(
                EventArticleModel.event_id == event_id,
                EventArticleModel.article_id == art.id,
                EventArticleModel.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        art.event_id = event_id
        art.status = ArticleStatus.CLUSTERED.value
        return "merged"

    ea = EventArticleModel(
        event_id=event_id,
        article_id=art.id,
        match_level=level.value,
        similarity=sim,
        is_primary=False,
    )
    session.add(ea)
    art.event_id = event_id
    art.status = ArticleStatus.CLUSTERED.value

    # 重算 event 计数 + last_seen + status
    ev = await session.get(EventModel, event_id)
    if ev is None:
        return "merged"
    # 重新统计 source_count / article_count
    src_count = (
        await session.execute(
            select(func.count(func.distinct(Article.source_id))).where(
                Article.event_id == event_id,
                Article.is_deleted.is_(False),
            )
        )
    ).scalar() or 0
    art_count = (
        await session.execute(
            select(func.count(Article.id)).where(
                Article.event_id == event_id,
                Article.is_deleted.is_(False),
            )
        )
    ).scalar() or 0
    ev.source_count = src_count or 1
    ev.article_count = art_count or 1
    ev.last_seen_at = max(ev.last_seen_at or art.published_at, art.published_at)
    # ANALYZED 状态有新来源 → 重置为 PENDING_AI
    if ev.status == EventStatus.ANALYZED.value and ev.source_count > 0:
        ev.status = EventStatus.PENDING_AI.value
    return "merged"


# ---------------------------------------------------------------- AI 分析


@tracked_task(manual_triggerable=True, display_name="事件 AI 分析")
@celery_app.task(name="pipeline.analyze_event", bind=True, max_retries=2, default_retry_delay=30)
def analyze_event_task(self, event_id: int, force: bool = False) -> dict[str, Any]:
    """调用 ai-engine 的 EventAnalysisService 分析一个事件。"""
    from app.modules.ai.analysis import EventAnalysisService

    async def _go():
        async with AsyncSessionLocal() as session:
            svc = EventAnalysisService(session)
            try:
                res = await svc.analyze_event(event_id=event_id, force=force)
                return {"ok": True, "event_id": event_id}
            except Exception as exc:  # noqa: BLE001
                # 标 AI_FAILED
                from app.modules.pipeline.model import Event as EventModel

                ev = await session.get(EventModel, event_id)
                if ev is not None:
                    ev.status = EventStatus.AI_FAILED.value
                    await session.commit()
                raise

    try:
        return _run(_go())
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "pipeline.analyze.failed",
            event_id=event_id,
            error=f"{exc.__class__.__name__}: {exc}",
        )
        raise self.retry(exc=exc) from exc


# ---------------------------------------------------------------- 评分入榜


@tracked_task(manual_triggerable=True, display_name="评分入榜")
@celery_app.task(name="pipeline.rank", bind=True, max_retries=2, default_retry_delay=30)
def rank_task(self) -> dict[str, int]:
    """给 72h 活跃事件计算 heat_score + recommend_index。"""
    start = time.perf_counter()
    result = _run(_async_rank())
    log.info(
        "pipeline.rank.done",
        duration_ms=int((time.perf_counter() - start) * 1000),
        **result,
    )
    return result


async def _async_rank() -> dict[str, int]:
    from sqlalchemy import select, update
    from app.modules.ai.model import EventAnalysis as AnalysisModel
    from app.modules.pipeline.model import (
        Article as ArticleModel,
        Event as EventModel,
        EventArticle as EventArticleModel,
    )

    RANK_WEIGHTS = {"heat": 0.35, "value": 0.30, "originality": 0.20, "trend": 0.15}
    METRIC_WEIGHTS = {"points": 1.0, "comments": 2.0, "stars": 0.5, "upvotes": 1.0}
    ARCHIVE_HOURS = 72

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ARCHIVE_HOURS)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # 1. 计算所有活跃事件的 raw heat
        events_stmt = select(EventModel).where(
            EventModel.is_deleted.is_(False),
            EventModel.is_hidden.is_(False),
            EventModel.last_seen_at >= cutoff,
            EventModel.status != EventStatus.ARCHIVED.value,
        )
        events = list((await session.execute(events_stmt)).scalars())
        raw_heats: list[tuple[int, float]] = []
        for ev in events:
            # 取关联 articles
            arts = list(
                (
                    await session.execute(
                        select(ArticleModel).join(
                            EventArticleModel,
                            EventArticleModel.article_id == ArticleModel.id,
                        ).where(
                            EventArticleModel.event_id == ev.id,
                            ArticleModel.is_deleted.is_(False),
                        )
                    )
                ).scalars()
            )
            if not arts:
                continue
            # 关联 source weights
            from app.modules.source.model import Source as SourceModel

            src_ids = list({a.source_id for a in arts})
            sources = list(
                (
                    await session.execute(
                        select(SourceModel).where(SourceModel.id.in_(src_ids))
                    )
                ).scalars()
            )
            src_weight_map = {s.id: (s.weight or 1) for s in sources}
            source_weight_sum = sum(src_weight_map.get(a.source_id, 1) for a in arts)
            source_diversity = 1.0
            if len(src_ids) > 1:
                source_diversity = 1 + (len(src_ids) ** 0.5) * 0.5
            engagement = 1.0
            for a in arts:
                m = dict(a.metrics or {})
                for k, v in m.items():
                    try:
                        engagement += float(v) * float(METRIC_WEIGHTS.get(k, 1.0))
                    except Exception:
                        pass
            engagement = 1 + (engagement ** 0.5)
            delta_h = (now - (ev.last_seen_at or now)).total_seconds() / 3600.0
            freshness = 2.718281828 ** (-delta_h / 24.0)
            raw = source_weight_sum * source_diversity * engagement * freshness
            raw_heats.append((ev.id, raw))

        # 2. min-max 归一化到 [0, 100]
        if not raw_heats:
            return {"ranked": 0}
        vals = [v for _, v in raw_heats]
        vmin, vmax = min(vals), max(vals)
        span = vmax - vmin or 1.0

        # 3. 写回 event
        for eid, raw in raw_heats:
            heat = round(((raw - vmin) / span) * 100, 2)
            ev = next((e for e in events if e.id == eid), None)
            if ev is None:
                continue
            ev.heat_score = heat
            # recommend_index 用 AI 分（若有）
            v = ev.value_score or 0
            o = ev.originality_score or 0
            t = ev.trend_score or 0
            ev.recommend_index = round(
                RANK_WEIGHTS["heat"] * heat
                + RANK_WEIGHTS["value"] * v
                + RANK_WEIGHTS["originality"] * o
                + RANK_WEIGHTS["trend"] * t,
                2,
            )
        await session.commit()

        # 4. 归档 72h 内无新来源的事件
        archive_stmt = (
            update(EventModel)
            .where(
                EventModel.is_deleted.is_(False),
                EventModel.last_seen_at < cutoff,
                EventModel.status != EventStatus.ARCHIVED.value,
            )
            .values(status=EventStatus.ARCHIVED.value)
            .execution_options(synchronize_session=False)
        )
        archived = (await session.execute(archive_stmt)).rowcount or 0

    return {"ranked": len(raw_heats), "archived": archived}


# ---------------------------------------------------------------- 重跑


@tracked_task(manual_triggerable=True, display_name="手动重跑流水线")
@celery_app.task(name="pipeline.rerun", bind=True)
def rerun_task(self, stage: str, scope: str, ids: list[int] | None = None, since: str | None = None) -> dict[str, Any]:
    """手动重跑某个阶段。

    stage: CLEAN | EMBED | DEDUPE | RANK
    scope: ARTICLE | EVENT | SOURCE | ALL
    """
    log.info("pipeline.rerun.start", stage=stage, scope=scope, ids=ids, since=since)
    async def _go():
        async with AsyncSessionLocal() as session:
            art_repo = ArticleRepository(session)
            ids_to_process: list[int] = []
            if scope == "ALL":
                if not since:
                    raise ValueError("scope=ALL requires since")
                from sqlalchemy import select, update
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                if stage == "CLEAN":
                    stmt = select(Article.id).where(
                        Article.fetched_at >= since_dt,
                        Article.is_deleted.is_(False),
                    )
                elif stage == "EMBED":
                    stmt = select(Article.id).where(
                        Article.fetched_at >= since_dt,
                        Article.status == ArticleStatus.CLEANED.value,
                        Article.is_deleted.is_(False),
                    )
                else:
                    stmt = select(Article.id).limit(0)
                ids_to_process = [r[0] for r in (await session.execute(stmt)).all()]
            elif scope == "ARTICLE" and ids:
                ids_to_process = ids
            else:
                raise ValueError(f"unsupported scope={scope}")
            return ids_to_process

    article_ids = _run(_go())
    if stage == "CLEAN":
        clean_task.delay(article_ids)
    elif stage == "EMBED":
        embed_task.delay(article_ids)
    elif stage in ("DEDUPE", "RANK"):
        if stage == "DEDUPE":
            dedupe_task.delay()
        else:
            rank_task.delay()
    return {"stage": stage, "scope": scope, "queued": len(article_ids)}

# ---------------------------------------------------------------- 事件归档

@tracked_task(manual_triggerable=True, display_name="事件归档")
@celery_app.task(name="pipeline.archive", bind=True)
def archive_task(self) -> dict[str, int]:
    """每小时跑一次：把 last_seen_at 超过 72 小时且未归档的事件标 ARCHIVED。"""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update
    from app.db.session import AsyncSessionLocal
    from app.modules.pipeline.enums import EventStatus
    from app.modules.pipeline.model import Event

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=72)

    async def _go() -> int:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                update(Event)
                .where(
                    Event.last_seen_at < cutoff,
                    Event.status != EventStatus.ARCHIVED.value,
                    Event.is_deleted.is_(False),
                )
                .values(status=EventStatus.ARCHIVED.value)
            )
            await session.commit()
            return res.rowcount or 0

    archived = _run(_go())
    log.info("pipeline.archive.done", archived=archived)
    return {"archived": archived}

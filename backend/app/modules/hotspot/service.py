"""hotspot 业务编排层。

职责：榜单查询 / 事件详情 / 趋势 / 相关推荐 / 标签 / EDITOR 运营干预 + Redis 缓存。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import RedisKey, redis_client
from app.core.schema import Page
from app.modules.auth.enums import Role, has_role
from app.modules.auth.model import User
from app.modules.hotspot.enums import (
    LOCKABLE_FIELDS,
    SORT_WHITELIST,
    CategoryFilter,
    Scope,
)
from app.modules.hotspot.exceptions import (
    EventNotFoundError,
    InvalidSortFieldError,
    KeywordTooShortError,
    ManualLockFieldNotFoundError,
    PinAndHideConflictError,
)
from app.modules.hotspot.repository import HotspotRepository
from app.modules.hotspot.schema import (
    EventAnalysisDetail,
    EventArticleItem,
    EventDetail,
    EventListItem,
    EventTrendPoint,
    EventTrendResponse,
    EventUpdateRequest,
    RelatedEventItem,
    SourceBrief,
    TagItem,
)
from app.modules.pipeline.enums import EventStatus

log = structlog.get_logger()

RANK_CACHE_TTL = 300  # 5 分钟
EVENT_CACHE_TTL = 600  # 10 分钟
TREND_CACHE_TTL = 3600  # 1 小时
CACHEABLE_PAGES = 3  # 只缓存默认榜单前 3 页


def _parse_sort(raw: str) -> tuple[str, bool]:
    """`-recommendIndex` → ("recommendIndex", True)。字段必须在白名单内。"""
    descending = raw.startswith("-")
    field = raw[1:] if descending else raw
    if field not in SORT_WHITELIST:
        raise InvalidSortFieldError
    return field, descending


class HotspotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = HotspotRepository(session)

    # ============================================================== 榜单

    async def list_events(
        self,
        *,
        scope: Scope,
        category: CategoryFilter,
        sort: str,
        keyword: str | None,
        tag_ids: list[int] | None,
        source_ids: list[int] | None,
        min_recommend: int | None,
        start_date: datetime | None,
        end_date: datetime | None,
        include_hidden: bool,
        page: int,
        size: int,
        user: User | None,
    ) -> Page[EventListItem]:
        field, descending = _parse_sort(sort)
        if keyword is not None:
            keyword = keyword.strip()
            if not keyword:
                keyword = None
            elif len(keyword) < 2:
                raise KeywordTooShortError

        # 权限：只有 EDITOR 及以上才能看隐藏事件
        is_editor = user is not None and has_role(user.role, Role.EDITOR)
        include_hidden = include_hidden and is_editor

        muted = await self._muted_sources(user)

        # 只缓存「无关键词 / 无自定义筛选 / 无个性化屏蔽 / 仅 GUEST」的默认榜单前 3 页
        cacheable = (
            user is None  # 登录用户的 is_collected 个性化
            and keyword is None
            and not tag_ids
            and not source_ids
            and min_recommend is None
            and start_date is None
            and end_date is None
            and not include_hidden
            and not muted
            and page <= CACHEABLE_PAGES
        )
        cache_key = RedisKey.hotspot_rank(scope.value, category.value, sort, page)
        if cacheable and (cached := await self._cache_get(cache_key)):
            return Page[EventListItem].model_validate(cached)

        rows, total = await self.repo.list_events(
            scope=scope,
            category=category,
            sort=field,
            descending=descending,
            keyword=keyword,
            tag_ids=tag_ids,
            source_ids=source_ids,
            min_recommend=min_recommend,
            start_date=start_date,
            end_date=end_date,
            include_hidden=include_hidden,
            muted_source_ids=muted,
            offset=(page - 1) * size,
            limit=size,
        )

        items = await self._assemble_list_items(rows, user)
        result = Page[EventListItem].create(items=items, total=total, page=page, size=size)
        if cacheable:
            await self._cache_set(cache_key, result.model_dump(mode="json"), RANK_CACHE_TTL)
        return result

    async def _assemble_list_items(
        self, rows: list[Any], user: User | None = None
    ) -> list[EventListItem]:
        """一次批量查询后在内存组装，避免 N+1。"""
        event_ids = [e.id for e in rows]
        sources_map = await self.repo.map_sources(event_ids)
        tags_map = await self.repo.map_tags(event_ids)
        url_map = await self.repo.map_primary_article_url(event_ids)
        worth_map = await self.repo.map_worth_article(event_ids)
        # 已登录用户：批量查 isCollected（一次性单 SQL）
        collected_ids: set[int] = set()
        if user is not None and event_ids:
            from app.modules.collection.service import CollectionService

            collected_ids = await CollectionService(
                self.session
            ).list_collected_event_ids(user.id, event_ids)

        items: list[EventListItem] = []
        for e in rows:
            items.append(
                EventListItem(
                    id=e.id,
                    title=e.title,
                    summary_one_line=e.summary_one_line,
                    region=e.region,
                    categories=e.categories or [],
                    tags=[
                        TagItem(
                            id=t.id,
                            display_name=t.display_name,
                            type=t.type,
                            weight=w,
                            event_count=t.event_count,
                        )
                        for t, w in tags_map.get(e.id, [])
                    ],
                    source_count=e.source_count,
                    article_count=e.article_count,
                    sources=[
                        SourceBrief(id=s.id, name=s.name, home_url=s.home_url, weight=s.weight)
                        for s in sources_map.get(e.id, [])
                    ],
                    heat_score=float(e.heat_score or 0),
                    value_score=e.value_score,
                    originality_score=e.originality_score,
                    trend_score=e.trend_score,
                    recommend_index=float(e.recommend_index or 0),
                    worth_article=worth_map.get(e.id, False),
                    primary_article_url=url_map.get(e.id),
                    first_seen_at=e.first_seen_at,
                    last_seen_at=e.last_seen_at,
                    status=e.status,
                    is_pinned=e.is_pinned,
                    is_hidden=e.is_hidden,
                    is_manually_edited=e.is_manually_edited,
                    is_collected=(e.id in collected_ids) if user else False,
                )
            )
        return items

    # ============================================================== 详情

    async def get_event_detail(self, event_id: int, user: User | None) -> EventDetail:
        is_editor = user is not None and has_role(user.role, Role.EDITOR)
        # 登录用户（含 USER）的 is_collected 个性化，不进缓存（避免给 A 用户的收藏被 B 用户复用）
        use_cache = user is None
        if use_cache and (cached := await self._cache_get(RedisKey.hotspot_event(event_id))):
            return EventDetail.model_validate(cached)

        event = await self.repo.get_event(event_id)
        if event is None:
            raise EventNotFoundError
        # 隐藏事件对非 EDITOR 不暴露存在性
        if event.is_hidden and not is_editor:
            raise EventNotFoundError

        analysis = await self.repo.get_analysis(event_id)
        articles = await self.repo.list_event_articles(event_id)
        tags_map = await self.repo.map_tags([event_id])

        # 已登录用户单查 is_collected
        is_collected = False
        if user is not None:
            from app.modules.collection.service import CollectionService

            collected = await CollectionService(
                self.session
            ).list_collected_event_ids(user.id, [event_id])
            is_collected = event_id in collected

        detail = EventDetail(
            id=event.id,
            title=event.title,
            region=event.region,
            categories=event.categories or [],
            tags=[
                TagItem(
                    id=t.id,
                    display_name=t.display_name,
                    type=t.type,
                    weight=w,
                    event_count=t.event_count,
                )
                for t, w in tags_map.get(event_id, [])
            ],
            source_count=event.source_count,
            article_count=event.article_count,
            heat_score=float(event.heat_score or 0),
            recommend_index=float(event.recommend_index or 0),
            value_score=event.value_score,
            originality_score=event.originality_score,
            trend_score=event.trend_score,
            status=event.status,
            is_pinned=event.is_pinned,
            is_hidden=event.is_hidden,
            is_manually_edited=event.is_manually_edited,
            manual_locked_fields=event.manual_locked_fields or [],
            first_seen_at=event.first_seen_at,
            last_seen_at=event.last_seen_at,
            analysis=(
                EventAnalysisDetail(
                    summary_one_line=analysis.summary_one_line,
                    summary=analysis.summary,
                    key_points=analysis.key_points or [],
                    innovations=analysis.innovations or [],
                    audience=analysis.audience or [],
                    value_score=analysis.value_score,
                    originality_score=analysis.originality_score,
                    trend_score=analysis.trend_score,
                    worth_article=analysis.worth_article,
                    worth_article_why=analysis.worth_article_why,
                    worth_research=analysis.worth_research,
                    worth_research_why=analysis.worth_research_why,
                    model_alias=analysis.model_alias,
                    prompt_version=analysis.prompt_version,
                    analyzed_at=analysis.analyzed_at,
                )
                if analysis is not None and event.status == EventStatus.ANALYZED.value
                else None
            ),
            articles=[
                EventArticleItem(
                    id=a.id,
                    title=a.title,
                    url=a.url,
                    author=a.author,
                    lang=a.lang,
                    published_at=a.published_at,
                    summary=a.summary,
                    metrics=a.metrics or {},
                    source=(
                        SourceBrief(id=s.id, name=s.name, home_url=s.home_url, weight=s.weight)
                        if s is not None
                        else None
                    ),
                    is_primary=bool(ea.is_primary) if ea is not None else False,
                    match_level=ea.match_level if ea is not None else None,
                    similarity=float(ea.similarity) if ea is not None and ea.similarity else None,
                )
                for a, s, ea in articles
            ],
            is_collected=is_collected,
        )

        if use_cache:  # 仅匿名请求可缓存（登录用户的 is_collected 个性化）
            await self._cache_set(
                RedisKey.hotspot_event(event_id), detail.model_dump(mode="json"), EVENT_CACHE_TTL
            )
        return detail

    # ============================================================== 趋势 / 相关

    async def get_trend(self, event_id: int, user: User | None) -> EventTrendResponse:
        await self._assert_visible(event_id, user)
        key = f"hotspot:trend:{event_id}"
        if cached := await self._cache_get(key):
            return EventTrendResponse.model_validate(cached)
        points = await self.repo.trend_points(event_id)
        resp = EventTrendResponse(
            event_id=event_id, points=[EventTrendPoint(**p) for p in points]
        )
        await self._cache_set(key, resp.model_dump(mode="json"), TREND_CACHE_TTL)
        return resp

    async def get_related(
        self, event_id: int, user: User | None, limit: int = 5
    ) -> list[RelatedEventItem]:
        await self._assert_visible(event_id, user)
        rows = await self.repo.related_events(event_id, limit=limit)
        return [RelatedEventItem(**r) for r in rows]

    # ============================================================== 标签

    async def list_tags(
        self, *, keyword: str | None, tag_type: str | None, limit: int
    ) -> list[TagItem]:
        rows = await self.repo.list_tags(keyword=keyword, tag_type=tag_type, limit=limit)
        return [
            TagItem(
                id=t.id, display_name=t.display_name, type=t.type, event_count=t.event_count
            )
            for t in rows
        ]

    # ============================================================== 运营干预

    async def update_event(
        self, event_id: int, payload: EventUpdateRequest, user: User
    ) -> EventDetail:
        event = await self.repo.get_event(event_id)
        if event is None:
            raise EventNotFoundError

        data = payload.model_dump(exclude_unset=True)
        if data.get("is_pinned") and data.get("is_hidden"):
            raise PinAndHideConflictError
        if data.get("is_pinned") and event.is_hidden and data.get("is_hidden") is not False:
            raise PinAndHideConflictError
        if data.get("is_hidden") and event.is_pinned and data.get("is_pinned") is not False:
            raise PinAndHideConflictError

        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        locked = list(event.manual_locked_fields or [])

        # snake_case → camelCase 的锁定字段名映射
        lock_name = {"title": "title", "summary_one_line": "summaryOneLine", "categories": "categories"}

        for attr in ("title", "summary_one_line", "categories", "is_pinned", "is_hidden"):
            if attr not in data or data[attr] is None:
                continue
            old = getattr(event, attr)
            new = data[attr]
            if old == new:
                continue
            before[attr] = old
            after[attr] = new
            setattr(event, attr, new)
            # 内容类字段编辑 → 加人工锁
            if attr in lock_name:
                event.is_manually_edited = True
                if lock_name[attr] not in locked:
                    locked.append(lock_name[attr])

        event.manual_locked_fields = locked
        await self.session.commit()
        await self._invalidate(event_id)

        log.info(
            "hotspot.event.updated",
            event_id=event_id,
            user_id=user.id,
            before=before,
            after=after,
        )
        # 审计：content 字段变更 → EVENT_EDIT；仅 is_pinned/hide 开关 → EVENT_PIN/EVENT_HIDE
        if before or after:
            from app.modules.admin.enums import AuditAction, TargetType
            from app.modules.admin.service import AuditService

            action = AuditAction.EVENT_EDIT
            if set(before.keys()) | set(after.keys()) <= {"is_pinned"}:
                action = AuditAction.EVENT_PIN
            elif set(before.keys()) | set(after.keys()) <= {"is_hidden"}:
                action = AuditAction.EVENT_HIDE
            await AuditService(self.session).record(
                action=action,
                target_type=TargetType.EVENT,
                target_id=event_id,
                before=before,
                after=after,
                actor=user,
            )
        return await self.get_event_detail(event_id, user)

    async def unlock_field(self, event_id: int, field: str, user: User) -> None:
        event = await self.repo.get_event(event_id)
        if event is None:
            raise EventNotFoundError
        if field not in LOCKABLE_FIELDS:
            raise ManualLockFieldNotFoundError
        locked = list(event.manual_locked_fields or [])
        if field not in locked:
            raise ManualLockFieldNotFoundError
        locked.remove(field)
        event.manual_locked_fields = locked
        if not locked:
            event.is_manually_edited = False
        await self.session.commit()
        await self._invalidate(event_id)
        log.info("hotspot.event.unlock", event_id=event_id, field=field, user_id=user.id)

        from app.modules.admin.enums import AuditAction, TargetType
        from app.modules.admin.service import AuditService

        await AuditService(self.session).record(
            action=AuditAction.EVENT_EDIT,
            target_type=TargetType.EVENT,
            target_id=event_id,
            before={"manual_locked_fields": locked + [field]},
            after={"manual_locked_fields": locked},
            actor=user,
            note=f"unlock field {field}",
        )

    # ============================================================== 内部工具

    async def _assert_visible(self, event_id: int, user: User | None) -> None:
        event = await self.repo.get_event(event_id)
        if event is None:
            raise EventNotFoundError
        is_editor = user is not None and has_role(user.role, Role.EDITOR)
        if event.is_hidden and not is_editor:
            raise EventNotFoundError

    async def _muted_sources(self, user: User | None) -> list[int]:
        """读用户偏好里的屏蔽源。跨模块只走 auth 的 service 层。"""
        if user is None:
            return []
        try:
            from app.modules.auth.service import AuthService

            me = await AuthService(self.session).get_me(user)
            return list(me.preference.muted_sources or [])
        except Exception:  # noqa: BLE001 — 偏好读失败不该阻断榜单
            log.warning("hotspot.muted_sources.failed", user_id=user.id)
            return []

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = await redis_client.get(key)
            return json.loads(raw) if raw else None
        except Exception:  # noqa: BLE001 — 缓存故障降级直查
            return None

    async def _cache_set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        try:
            await redis_client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception:  # noqa: BLE001
            log.warning("hotspot.cache.set.failed", key=key)

    async def _invalidate(self, event_id: int | None = None) -> None:
        """事件被编辑 / rank_task 跑完 → 失效榜单与详情缓存。"""
        try:
            if event_id is not None:
                await redis_client.delete(
                    RedisKey.hotspot_event(event_id), f"hotspot:trend:{event_id}"
                )
            keys = [k async for k in redis_client.scan_iter(match="hotspot:rank:*", count=500)]
            if keys:
                await redis_client.delete(*keys)
        except Exception:  # noqa: BLE001
            log.warning("hotspot.cache.invalidate.failed", event_id=event_id)

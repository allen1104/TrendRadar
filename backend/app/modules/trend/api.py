"""trend 路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.trend.enums import EntityType, TrendMetric, TrendWindow
from app.modules.trend.schema import (
    EntityTrendResponse,
    KeywordDetailResponse,
    KeywordTrendResponse,
    OverviewResponse,
    WordCloudResponse,
)
from app.modules.trend.service import TrendService

router = APIRouter(prefix="/trends", tags=["trend"])


def _db() -> AsyncSession:
    return Depends(get_db)


@router.get(
    "/keywords",
    response_model=KeywordTrendResponse,
    summary="关键词趋势排行（GUEST 可访问）",
)
async def get_keywords(
    session: Annotated[AsyncSession, _db()],
    window: Annotated[str, Query()] = TrendWindow.D7.value,
    metric: Annotated[str, Query()] = TrendMetric.GROWTH.value,
    limit: Annotated[int, Query(ge=1, le=300)] = 20,
    include_new: Annotated[bool, Query()] = True,
) -> KeywordTrendResponse:
    return await TrendService(session).get_keyword_trends(
        window=window, metric=metric, limit=limit, include_new=include_new
    )


@router.get(
    "/entities",
    response_model=EntityTrendResponse,
    summary="实体趋势排行（GUEST 可访问）",
)
async def get_entities(
    session: Annotated[AsyncSession, _db()],
    window: Annotated[str, Query()] = TrendWindow.D30.value,
    entity_type: Annotated[str, Query()] = EntityType.COMPANY.value,
    limit: Annotated[int, Query(ge=1, le=300)] = 20,
) -> EntityTrendResponse:
    return await TrendService(session).get_entity_trends(
        window=window, entity_type=entity_type, limit=limit
    )


@router.get(
    "/wordcloud",
    response_model=WordCloudResponse,
    summary="词云数据（GUEST 可访问）",
)
async def get_wordcloud(
    session: Annotated[AsyncSession, _db()],
    window: Annotated[str, Query()] = TrendWindow.D7.value,
    limit: Annotated[int, Query(ge=1, le=300)] = 100,
    type: Annotated[str, Query()] = "ALL",
) -> WordCloudResponse:
    return await TrendService(session).get_wordcloud(window=window, limit=limit, type_=type)


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="趋势总览（GUEST 可访问）",
)
async def get_overview(
    session: Annotated[AsyncSession, _db()],
    window: Annotated[str, Query()] = TrendWindow.D7.value,
) -> OverviewResponse:
    return await TrendService(session).get_overview(window=window)


@router.get(
    "/keywords/{keyword}",
    response_model=KeywordDetailResponse,
    summary="关键词下钻（GUEST 可访问）",
)
async def get_keyword_detail(
    keyword: str,
    session: Annotated[AsyncSession, _db()],
    window: Annotated[str, Query()] = TrendWindow.D30.value,
) -> KeywordDetailResponse:
    return await TrendService(session).get_keyword_detail(keyword=keyword, window=window)

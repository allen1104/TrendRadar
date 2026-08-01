"""trend 路由集成测试（mock repo，免 DB）。"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.trend.schema import (
    EntityTrendItem,
    EntityTrendResponse,
    KeywordDetailResponse,
    KeywordTrendItem,
    KeywordTrendResponse,
    OverviewResponse,
    WordCloudItem,
    WordCloudResponse,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _kw_item(**kw) -> KeywordTrendItem:
    defaults = dict(
        keyword="llm",
        display_name="LLM",
        current=10,
        previous=5,
        growth_rate=1.0,
        growth_abs=5,
        growth_score=1.04,
        heat_sum=320.0,
        is_new=False,
        series=[],
    )
    defaults.update(kw)
    return KeywordTrendItem(**defaults)


def _ent_item(**kw) -> EntityTrendItem:
    defaults = dict(
        tag_id=12,
        display_name="OpenAI",
        entity_type="COMPANY",
        current=8,
        previous=4,
        growth_rate=1.0,
        growth_abs=4,
        growth_score=1.0,
        heat_sum=200.0,
        avg_value_score=80.0,
        series=[],
    )
    defaults.update(kw)
    return EntityTrendItem(**defaults)


def _kw_resp(**kw) -> KeywordTrendResponse:
    defaults = dict(window="7D", metric="GROWTH", items=[], newcomers=[])
    defaults.update(kw)
    return KeywordTrendResponse(**defaults)


def _ent_resp(**kw) -> EntityTrendResponse:
    defaults = dict(window="30D", entity_type="COMPANY", items=[])
    defaults.update(kw)
    return EntityTrendResponse(**defaults)


def _wc_resp(**kw) -> WordCloudResponse:
    defaults = dict(window="7D", items=[])
    defaults.update(kw)
    return WordCloudResponse(**defaults)


def _overview(**kw) -> OverviewResponse:
    from app.modules.trend.schema import TrendSummary

    defaults = dict(
        window="7D",
        summary=TrendSummary(
            total_events=100,
            total_articles=100,
            avg_events_per_day=14.0,
            event_growth_rate=0.2,
        ),
        daily_series=[],
        category_distribution=[],
        region_distribution=[],
        top_rising_keywords=[],
        top_companies=[],
        top_projects=[],
    )
    defaults.update(kw)
    return OverviewResponse(**defaults)


def _kw_detail(**kw) -> KeywordDetailResponse:
    defaults = dict(
        keyword="llm",
        display_name="LLM",
        window="30D",
        series=[],
        growth_rate=0.5,
        related_keywords=[],
        top_events=[],
    )
    defaults.update(kw)
    return KeywordDetailResponse(**defaults)


# ============================================================ /trends/keywords


class TestKeywordsEndpoint:
    def test_get_keywords_default(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(return_value=_kw_resp(items=[_kw_item()]))
            mp.setattr(svc_mod.TrendService, "get_keyword_trends", fake)
            r = client.get("/api/v1/trends/keywords")
        assert r.status_code == 200
        body = r.json()
        assert body["window"] == "7D"
        assert body["metric"] == "GROWTH"
        assert len(body["items"]) == 1
        assert body["items"][0]["keyword"] == "llm"

    def test_get_keywords_with_window_metric(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(return_value=_kw_resp(window="30D", metric="HOT"))
            mp.setattr(svc_mod.TrendService, "get_keyword_trends", fake)
            r = client.get("/api/v1/trends/keywords?window=30D&metric=HOT&limit=10")
        assert r.status_code == 200
        body = r.json()
        assert body["window"] == "30D"
        assert body["metric"] == "HOT"

    def test_get_keywords_invalid_window(self, client: TestClient) -> None:
        r = client.get("/api/v1/trends/keywords?window=2D")
        assert r.status_code == 400
        assert r.json()["errorCode"] == "TREND_WINDOW_INVALID"

    def test_get_keywords_invalid_metric(self, client: TestClient) -> None:
        r = client.get("/api/v1/trends/keywords?metric=WEIRD")
        assert r.status_code == 400
        assert r.json()["errorCode"] == "TREND_METRIC_INVALID"

    def test_get_keywords_limit_out_of_range(self, client: TestClient) -> None:
        # FastAPI Query(ge=1, le=300) 在依赖层就拦截，返回 422
        r = client.get("/api/v1/trends/keywords?limit=500")
        assert r.status_code == 422

    def test_get_keywords_limit_too_small(self, client: TestClient) -> None:
        r = client.get("/api/v1/trends/keywords?limit=0")
        assert r.status_code == 422


# ============================================================ /trends/entities


class TestEntitiesEndpoint:
    def test_get_entities_default(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(return_value=_ent_resp(items=[_ent_item()]))
            mp.setattr(svc_mod.TrendService, "get_entity_trends", fake)
            r = client.get("/api/v1/trends/entities")
        assert r.status_code == 200
        body = r.json()
        assert body["entityType"] == "COMPANY"
        assert len(body["items"]) == 1
        assert body["items"][0]["displayName"] == "OpenAI"

    def test_get_entities_invalid_type(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(side_effect=EntityTypeInvalidError("bad type"))
            mp.setattr(svc_mod.TrendService, "get_entity_trends", fake)
            r = client.get("/api/v1/trends/entities?entityType=GOVERNMENT")
        assert r.status_code == 400
        assert r.json()["errorCode"] == "ENTITY_TYPE_INVALID"


# ============================================================ /trends/wordcloud


class TestWordcloudEndpoint:
    def test_get_wordcloud(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(
                return_value=_wc_resp(
                    items=[
                        WordCloudItem(text="AI", value=80.0, type="KEYWORD", growth_rate=0.0),
                        WordCloudItem(text="OpenAI", value=60.0, type="COMPANY", growth_rate=0.0),
                    ]
                )
            )
            mp.setattr(svc_mod.TrendService, "get_wordcloud", fake)
            r = client.get("/api/v1/trends/wordcloud")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2


# ============================================================ /trends/overview


class TestOverviewEndpoint:
    def test_get_overview_default(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(return_value=_overview())
            mp.setattr(svc_mod.TrendService, "get_overview", fake)
            r = client.get("/api/v1/trends/overview")
        assert r.status_code == 200
        body = r.json()
        assert body["window"] == "7D"
        assert body["summary"]["totalEvents"] == 100


# ============================================================ /trends/keywords/{keyword}


class TestKeywordDetailEndpoint:
    def test_get_keyword_detail(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(return_value=_kw_detail())
            mp.setattr(svc_mod.TrendService, "get_keyword_detail", fake)
            r = client.get("/api/v1/trends/keywords/llm")
        assert r.status_code == 200
        body = r.json()
        assert body["keyword"] == "llm"
        assert body["window"] == "30D"

    def test_get_keyword_detail_with_window(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            from app.modules.trend import service as svc_mod

            fake = AsyncMock(return_value=_kw_detail(window="7D"))
            mp.setattr(svc_mod.TrendService, "get_keyword_detail", fake)
            r = client.get("/api/v1/trends/keywords/llm?window=7D")
        assert r.status_code == 200
        assert r.json()["window"] == "7D"


from app.modules.trend.exceptions import EntityTypeInvalidError, TrendLimitOutOfRangeError


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""trend 纯函数单测：归一化 / 增长率 / 窗口换算 / 聚合 / 停用词。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.trend.enums import EntityType, TrendMetric, TrendWindow
from app.modules.trend.exceptions import (
    EntityTypeInvalidError,
    TrendLimitOutOfRangeError,
    TrendMetricInvalidError,
    TrendWindowInvalidError,
)
from app.modules.trend.service import (
    DEFAULT_MIN_EVENT_COUNT,
    GROWTH_RATE_CAP,
    TrendService,
    _aggregate_keyword_rows,
    _aggregate_entity_rows,
    _smooth,
    growth_score,
    is_new_keyword,
    is_stopword,
    normalize_keyword,
    window_to_dates,
    window_to_days,
)


def _row(**kw):
    """构造一个 KeywordTrend 行（绕过 ORM 实例化校验，直接命名属性赋值）。"""

    class _Row:
        pass

    r = _Row()
    r.keyword = kw.get("keyword", "llm")
    r.display_name = kw.get("display_name", "LLM")
    r.stat_date = kw.get("stat_date", date(2026, 7, 29))
    r.event_count = kw.get("event_count", 0)
    r.article_count = kw.get("article_count", 0)
    r.heat_sum = kw.get("heat_sum", 0.0)
    return r


def _entity_row(**kw):
    class _Row:
        pass

    r = _Row()
    r.tag_id = kw.get("tag_id", 1)
    r.entity_type = kw.get("entity_type", "COMPANY")
    r.stat_date = kw.get("stat_date", date(2026, 7, 29))
    r.event_count = kw.get("event_count", 0)
    r.heat_sum = kw.get("heat_sum", 0.0)
    r.avg_value_score = kw.get("avg_value_score", None)
    return r


# ============================================================ normalize_keyword


class TestNormalizeKeyword:
    def test_basic(self) -> None:
        assert normalize_keyword("gpt-5") == "gpt-5"
        assert normalize_keyword("GPT 5") == "gpt-5"
        assert normalize_keyword("gpt_5") == "gpt-5"
        assert normalize_keyword("  GPT - 5  ") == "gpt-5"
        assert normalize_keyword("LLM") == "llm"

    def test_empty_and_strip(self) -> None:
        assert normalize_keyword("") == ""
        assert normalize_keyword("   ") == ""
        assert normalize_keyword("-") == ""

    def test_chinese_keywords_kept(self) -> None:
        # 中文不做大小写归一，但空白处理
        assert normalize_keyword("  机器学习  ") == "机器学习"
        assert normalize_keyword("深度__学习") == "深度-学习"


# ============================================================ is_stopword


class TestIsStopword:
    def test_single_char_filtered(self) -> None:
        assert is_stopword("a") is True
        assert is_stopword("中") is True
        assert is_stopword("好") is True

    def test_stopwords_filtered(self) -> None:
        assert is_stopword("ai") is True
        assert is_stopword("技术") is True
        assert is_stopword("the") is True

    def test_real_keywords_kept(self) -> None:
        assert is_stopword("gpt-5") is False
        assert is_stopword("anthropic") is False
        assert is_stopword("agent") is False

    def test_custom_stopwords(self) -> None:
        assert is_stopword("foo", stopwords={"foo"}) is True
        assert is_stopword("bar", stopwords={"foo"}) is False


# ============================================================ growth_score


class TestGrowthScore:
    def test_basic_growth(self) -> None:
        rate, abs_g, score = growth_score(10, 5)
        assert rate == 1.0  # (10-5)/5
        assert abs_g == 5
        # score = log10(1+10) * 1.0 ≈ 1.0414
        assert abs(score - 1.0414) < 0.01

    def test_decline(self) -> None:
        rate, abs_g, score = growth_score(2, 10)
        assert rate == -0.8
        assert abs_g == -8

    def test_growth_rate_cap(self) -> None:
        """爆发性增长：(50 - 1) / 1 = 49 → 截到 5.0。"""
        rate, _, _ = growth_score(50, 1)
        assert rate == GROWTH_RATE_CAP  # 5.0

    def test_new_keyword_zero_previous(self) -> None:
        rate, abs_g, _ = growth_score(3, 0)
        # (3-0)/max(0,1) = 3.0
        assert rate == 3.0
        assert abs_g == 3

    def test_zero_zero(self) -> None:
        rate, abs_g, _ = growth_score(0, 0)
        assert rate == 0.0
        assert abs_g == 0

    def test_score_uses_capped_rate(self) -> None:
        """growth_score 内部用 min(rate, 5.0)，避免 score 无限大。"""
        _, _, score = growth_score(50, 1)
        # score = log10(51) * 5.0 ≈ 8.53
        assert score < 10.0


# ============================================================ is_new_keyword


class TestIsNewKeyword:
    def test_true_when_prev_zero_and_current_le_min(self) -> None:
        assert is_new_keyword(3, 0) is True
        assert is_new_keyword(10, 0) is True

    def test_false_when_current_below_threshold(self) -> None:
        assert is_new_keyword(2, 0) is False
        assert is_new_keyword(1, 0) is False

    def test_false_when_prev_positive(self) -> None:
        assert is_new_keyword(5, 1) is False


# ============================================================ window_to_days / dates


class TestWindowUtils:
    def test_window_to_days(self) -> None:
        assert window_to_days(TrendWindow.D7) == 7
        assert window_to_days(TrendWindow.D30) == 30
        assert window_to_days(TrendWindow.Y1) == 365

    def test_window_to_days_invalid_string(self) -> None:
        with pytest.raises(TrendWindowInvalidError):
            window_to_days("2D")

    def test_window_to_dates_7d(self) -> None:
        today = date(2026, 7, 29)
        start, end, prev_start = window_to_dates(TrendWindow.D7, today=today)
        assert end == today
        assert start == date(2026, 7, 23)
        assert prev_start == date(2026, 7, 16)

    def test_window_to_dates_30d(self) -> None:
        today = date(2026, 7, 29)
        start, end, _ = window_to_dates(TrendWindow.D30, today=today)
        assert end == today
        assert start == date(2026, 6, 30)

    def test_window_to_dates_1y(self) -> None:
        today = date(2026, 7, 29)
        start, end, _ = window_to_dates(TrendWindow.Y1, today=today)
        assert end == today
        assert start == date(2025, 7, 30)


# ============================================================ smooth


class TestSmooth:
    def test_short_series_unchanged(self) -> None:
        assert _smooth([1.0, 2.0], window=3) == [1.0, 2.0]

    def test_three_day_window(self) -> None:
        # [1, 2, 3, 4, 5] → [1, 1.5, 2, 3, 4]
        out = _smooth([1.0, 2.0, 3.0, 4.0, 5.0], window=3)
        assert out[0] == 1.0
        assert out[1] == 1.5
        assert out[2] == 2.0
        assert out[3] == 3.0
        assert out[4] == 4.0

    def test_empty(self) -> None:
        assert _smooth([]) == []


# ============================================================ 聚合辅助


class TestAggregateKeywordRows:
    def test_aggregates_by_keyword(self) -> None:
        rows = [
            _row(keyword="llm", event_count=5, heat_sum=200.0, stat_date=date(2026, 7, 25)),
            _row(keyword="llm", event_count=3, heat_sum=120.0, stat_date=date(2026, 7, 26)),
            _row(keyword="agent", event_count=2, heat_sum=50.0, stat_date=date(2026, 7, 25)),
        ]
        agg = _aggregate_keyword_rows(rows)
        assert agg["llm"]["event_count"] == 8
        assert agg["llm"]["heat_sum"] == 320.0
        assert agg["agent"]["event_count"] == 2


class TestAggregateEntityRows:
    def test_aggregates_by_tag_id(self) -> None:
        rows = [
            _entity_row(tag_id=1, event_count=5, heat_sum=200.0),
            _entity_row(tag_id=1, event_count=3, heat_sum=120.0),
            _entity_row(tag_id=2, event_count=7, heat_sum=300.0),
        ]
        agg = _aggregate_entity_rows(rows)
        assert agg[1]["event_count"] == 8
        assert agg[1]["heat_sum"] == 320.0
        assert agg[2]["event_count"] == 7


# ============================================================ TrendService 校验（不需要 session）


class TestValidateLimit:
    @pytest.mark.asyncio
    async def test_limit_zero_raises(self) -> None:
        svc = TrendService(session=None)  # type: ignore[arg-type]
        with pytest.raises(TrendLimitOutOfRangeError):
            await svc.get_keyword_trends(limit=0)

    @pytest.mark.asyncio
    async def test_limit_too_large_raises(self) -> None:
        svc = TrendService(session=None)  # type: ignore[arg-type]
        with pytest.raises(TrendLimitOutOfRangeError):
            await svc.get_keyword_trends(limit=500)

    @pytest.mark.asyncio
    async def test_metric_invalid_raises(self) -> None:
        svc = TrendService(session=None)  # type: ignore[arg-type]
        with pytest.raises(TrendMetricInvalidError):
            await svc.get_keyword_trends(metric="WEIRD")

    @pytest.mark.asyncio
    async def test_entity_type_invalid_raises(self) -> None:
        svc = TrendService(session=None)  # type: ignore[arg-type]
        with pytest.raises(EntityTypeInvalidError):
            await svc.get_entity_trends(entity_type="GOVERNMENT")


# ============================================================ 噪声抑制/默认值


class TestConstants:
    def test_growth_rate_cap(self) -> None:
        assert GROWTH_RATE_CAP == 5.0

    def test_default_min_event_count(self) -> None:
        assert DEFAULT_MIN_EVENT_COUNT == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""pipeline rank 纯函数单测。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.admin.exceptions import RankWeightsSumInvalidError
from app.modules.pipeline.rank import (
    DEFAULT_METRIC_WEIGHTS,
    DEFAULT_RANK_WEIGHTS,
    engagement_score,
    freshness,
    freshness_from_last_seen,
    normalize_minmax,
    recommend_index,
    source_diversity,
    validate_rank_weights,
)


# ---------------------------------------------------------- source_diversity


class TestSourceDiversity:
    def test_single_source(self) -> None:
        assert source_diversity(1) == 1.0

    def test_two_sources(self) -> None:
        # 1 + sqrt(2) * 0.5 ≈ 1.707
        assert abs(source_diversity(2) - (1.0 + (2 ** 0.5) * 0.5)) < 1e-9

    def test_four_sources(self) -> None:
        # 1 + sqrt(4) * 0.5 = 2.0
        assert source_diversity(4) == 2.0

    def test_zero_or_negative(self) -> None:
        assert source_diversity(0) == 1.0
        assert source_diversity(-1) == 1.0


# ---------------------------------------------------------- engagement_score


class TestEngagementScore:
    def test_empty_metrics(self) -> None:
        assert engagement_score({}) == 1.0
        assert engagement_score(None) == 1.0  # type: ignore[arg-type]

    def test_with_weights(self) -> None:
        # 100 points × 1.0 + 50 comments × 2.0 = 200 → 1 + √200 ≈ 15.14
        out = engagement_score({"points": 100, "comments": 50})
        assert abs(out - (1.0 + (200 ** 0.5))) < 1e-6

    def test_unknown_metric_uses_default_weight_1(self) -> None:
        out = engagement_score({"foo": 100})
        assert abs(out - (1.0 + 10.0)) < 1e-6

    def test_invalid_value_ignored(self) -> None:
        out = engagement_score({"points": "abc", "comments": 4})
        # "abc" 抛 ValueError 被吞；只 comments=4 起作用：4 * 2.0 = 8
        # 1 + √8 ≈ 3.828
        assert abs(out - (1.0 + (8 ** 0.5))) < 1e-6

    def test_custom_weights(self) -> None:
        weights = {"points": 0.5, "comments": 0.5}
        out = engagement_score({"points": 100, "comments": 100}, weights)
        # 100*0.5 + 100*0.5 = 100 → 1 + 10 = 11
        assert abs(out - 11.0) < 1e-6


# ---------------------------------------------------------- freshness


class TestFreshness:
    def test_zero_delta(self) -> None:
        assert abs(freshness(0.0) - 1.0) < 1e-9

    def test_24h_half(self) -> None:
        # exp(-1) ≈ 0.3679
        assert abs(freshness(24.0) - 0.3678794412) < 1e-6

    def test_72h(self) -> None:
        # exp(-3) ≈ 0.0498
        assert abs(freshness(72.0) - 0.0497870684) < 1e-6

    def test_from_last_seen_now(self) -> None:
        now = datetime(2026, 7, 31, tzinfo=timezone.utc)
        assert freshness_from_last_seen(now, now=now) == pytest.approx(1.0)

    def test_from_last_seen_24h_ago(self) -> None:
        now = datetime(2026, 7, 31, tzinfo=timezone.utc)
        last = datetime(2026, 7, 30, tzinfo=timezone.utc)
        out = freshness_from_last_seen(last, now=now)
        assert abs(out - 0.3678794412) < 1e-6

    def test_negative_delta_clamped_to_zero(self) -> None:
        """未来时间不应返回 > 1。"""
        now = datetime(2026, 7, 31, tzinfo=timezone.utc)
        future = datetime(2026, 8, 1, tzinfo=timezone.utc)
        out = freshness_from_last_seen(future, now=now)
        assert out == pytest.approx(1.0)


# ---------------------------------------------------------- normalize_minmax


class TestNormalizeMinmax:
    def test_empty(self) -> None:
        assert normalize_minmax([]) == []

    def test_constant_sequence(self) -> None:
        # 全相同 → 全 100
        assert normalize_minmax([5.0, 5.0, 5.0]) == [100.0, 100.0, 100.0]

    def test_known_values(self) -> None:
        out = normalize_minmax([0.0, 50.0, 100.0])
        assert out == [0.0, 50.0, 100.0]

    def test_single_value(self) -> None:
        assert normalize_minmax([42.0]) == [100.0]


# ---------------------------------------------------------- recommend_index


class TestRecommendIndex:
    def test_full_ai_scores(self) -> None:
        out = recommend_index(
            heat=80.0,
            value_score=90,
            originality_score=70,
            trend_score=85,
        )
        # 全有：直接加权求和
        # 0.35*80 + 0.30*90 + 0.20*70 + 0.15*85 = 28+27+14+12.75 = 81.75
        assert out == 81.75

    def test_missing_ai_scores(self) -> None:
        """value/originality/trend 全 None → 只算 heat。"""
        out = recommend_index(heat=50.0, value_score=None, originality_score=None, trend_score=None)
        assert out == 0.35 * 50.0

    def test_partial_ai_scores(self) -> None:
        """只 value → 按已有分数归一化（total_w = 0.30）后乘回。"""
        out = recommend_index(heat=0, value_score=80, originality_score=None, trend_score=None)
        # total_w = 0.30, ai_part = 80 / 0.30 * 0.30 = 80, heat_part = 0
        assert out == 80.0

    def test_partial_two_scores(self) -> None:
        """value + trend 都有（orig 缺），按已有归一化。"""
        out = recommend_index(heat=10.0, value_score=20, originality_score=None, trend_score=40)
        # total_w = 0.30 + 0.15 = 0.45
        # ai_part = (20*0.30 + 40*0.15) / 0.45 = (6+6)/0.45 = 26.667
        # 0.35*10 + 26.667 = 30.167 → rounded 30.17
        assert out == 30.17

    def test_custom_weights(self) -> None:
        out = recommend_index(
            heat=10.0,
            value_score=20,
            originality_score=30,
            trend_score=40,
            weights={"heat": 0.5, "value": 0.3, "originality": 0.1, "trend": 0.1},
        )
        # 0.5*10 + 0.3*20 + 0.1*30 + 0.1*40 = 5+6+3+4 = 18
        assert out == 18.0

    def test_rounded_to_two_decimals(self) -> None:
        out = recommend_index(
            heat=33.333,
            value_score=66.666,
            originality_score=None,
            trend_score=None,
        )
        # 0.35*33.333 = 11.66655, ai_part = 66.666 (single field 不归一化),
        # heat_part = 0.35*33.333 = 11.67
        # 11.67 + 66.67 = 78.34 (or 78.33 视 round 边界)
        assert abs(out - 78.33) < 0.01


# ---------------------------------------------------------- validate_rank_weights


class TestValidateRankWeights:
    def test_valid_weights(self) -> None:
        validate_rank_weights(DEFAULT_RANK_WEIGHTS)  # 不抛

    def test_sum_one(self) -> None:
        validate_rank_weights({"heat": 0.25, "value": 0.25, "originality": 0.25, "trend": 0.25})

    def test_sum_too_low_raises(self) -> None:
        with pytest.raises(RankWeightsSumInvalidError):
            validate_rank_weights(
                {"heat": 0.25, "value": 0.25, "originality": 0.25, "trend": 0.10}
            )

    def test_sum_too_high_raises(self) -> None:
        with pytest.raises(RankWeightsSumInvalidError):
            validate_rank_weights(
                {"heat": 0.40, "value": 0.30, "originality": 0.20, "trend": 0.15}
            )

    def test_tolerance_for_floating_point(self) -> None:
        # 0.35 + 0.30 + 0.20 + 0.1499999 ≈ 0.9999 → 误差 < 1e-6，应通过
        validate_rank_weights(
            {"heat": 0.35, "value": 0.30, "originality": 0.20, "trend": 0.1499999}
        )


# ---------------------------------------------------------- 默认权重常量


def test_default_metric_weights_keys() -> None:
    assert set(DEFAULT_METRIC_WEIGHTS.keys()) == {"points", "comments", "stars", "upvotes"}


def test_default_rank_weights_keys() -> None:
    assert set(DEFAULT_RANK_WEIGHTS.keys()) == {"heat", "value", "originality", "trend"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""评分入榜纯函数。

把 heat_score / recommend_index 的纯计算从 tasks.py 抽出，单测友好。
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable

# 默认权重（与 system_config: rank_weights / metric_weights 对齐）
DEFAULT_RANK_WEIGHTS = {"heat": 0.35, "value": 0.30, "originality": 0.20, "trend": 0.15}
DEFAULT_METRIC_WEIGHTS = {"points": 1.0, "comments": 2.0, "stars": 0.5, "upvotes": 1.0}


def source_diversity(src_count: int) -> float:
    """单源 = 1.0；多源随 √n 增长（避免 1 vs 10 源的极端差距）。"""
    if src_count <= 1:
        return 1.0
    return 1.0 + (src_count ** 0.5) * 0.5


def engagement_score(metrics: dict, weights: dict | None = None) -> float:
    """1 + √(Σ metric × weight)。空 metrics → 1.0。"""
    weights = weights or DEFAULT_METRIC_WEIGHTS
    total = 0.0
    for k, v in (metrics or {}).items():
        try:
            total += float(v) * float(weights.get(k, 1.0))
        except (TypeError, ValueError):
            pass
    return 1.0 + math.sqrt(total)


def freshness(delta_hours: float) -> float:
    """exp(-Δh / 24)。24h 半衰。"""
    return math.exp(-delta_hours / 24.0)


def normalize_minmax(values: Iterable[float]) -> list[float]:
    """把一组数 min-max 归一化到 [0, 100]。常数序列 → 全 100。"""
    vals = list(values)
    if not vals:
        return []
    vmin, vmax = min(vals), max(vals)
    span = vmax - vmin
    if span <= 0:
        return [100.0] * len(vals)
    return [(v - vmin) / span * 100.0 for v in vals]


def recommend_index(
    heat: float,
    *,
    value_score: int | None,
    originality_score: int | None,
    trend_score: int | None,
    weights: dict | None = None,
) -> float:
    """weighted sum, 0-100。AI 分数缺失时按已有分数归一化权重。"""
    w = weights or DEFAULT_RANK_WEIGHTS

    ai_parts: list[tuple[float, float]] = []
    if value_score is not None:
        ai_parts.append((float(value_score), w.get("value", 0.0)))
    if originality_score is not None:
        ai_parts.append((float(originality_score), w.get("originality", 0.0)))
    if trend_score is not None:
        ai_parts.append((float(trend_score), w.get("trend", 0.0)))

    if len(ai_parts) == 3:
        # 全有：直接按权重相加
        ai_part = sum(s * t_w for s, t_w in ai_parts)
    elif ai_parts:
        # 部分缺失：按已有权重归一化
        total_w = sum(t[1] for t in ai_parts)
        if total_w <= 0:
            ai_part = 0.0
        else:
            ai_part = sum(s * t_w for s, t_w in ai_parts) / total_w
    else:
        ai_part = 0.0

    return round(w.get("heat", 0.0) * heat + ai_part, 2)


def validate_rank_weights(weights: dict) -> None:
    """4 个权重和必须 = 1（误差 < 1e-6）。"""
    fields = ("heat", "value", "originality", "trend")
    total = sum(float(weights.get(k, 0)) for k in fields)
    if abs(total - 1.0) > 1e-6:
        from app.modules.admin.exceptions import RankWeightsSumInvalidError
        raise RankWeightsSumInvalidError(
            f"rank_weights 四项之和必须等于 1，当前为 {total:.4f}",
            extra={"sum": total, "fields": list(weights.keys())},
        )


def freshness_from_last_seen(last_seen: datetime, now: datetime | None = None) -> float:
    """算 Δh 后转 exp(-Δh/24)。"""
    now = now or datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    delta_h = (now - last_seen).total_seconds() / 3600.0
    return freshness(max(delta_h, 0.0))
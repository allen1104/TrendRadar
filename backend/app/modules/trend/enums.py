"""trend 模块枚举。"""

from __future__ import annotations

from enum import StrEnum


class TrendWindow(StrEnum):
    """时间窗口。"""

    D7 = "7D"
    D30 = "30D"
    Y1 = "1Y"


class TrendMetric(StrEnum):
    """排行指标。"""

    GROWTH = "GROWTH"  # 增长最快
    HOT = "HOT"  # 最热门


class EntityType(StrEnum):
    """实体类型（与 tag.type 对齐）。"""

    COMPANY = "COMPANY"
    PRODUCT = "PRODUCT"
    TECH = "TECH"
    PERSON = "PERSON"
    ALL = "ALL"

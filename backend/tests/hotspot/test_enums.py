"""hotspot 模块枚举与白名单不变量测试。"""

from __future__ import annotations

import pytest

from app.modules.hotspot.enums import (
    AI_CATEGORY_GROUP,
    LOCKABLE_FIELDS,
    SORT_WHITELIST,
    CategoryFilter,
    Scope,
)


class TestScope:
    def test_members(self) -> None:
        assert {s.value for s in Scope} == {"TODAY", "WEEK", "MONTH", "ALL"}

    def test_str_roundtrip(self) -> None:
        for v in ("TODAY", "WEEK", "MONTH", "ALL"):
            assert Scope(v).value == v


class TestCategoryFilter:
    def test_tab_seven_count(self) -> None:
        # SPEC 要求 6 个 Tab + ALL = 7；此外再叠加 11 个业务分类
        # 本测试只保证 Tab 这 7 个一定存在
        for v in ("ALL", "GLOBAL", "CN", "AI", "GITHUB", "PAPER", "AGENT"):
            assert CategoryFilter(v).value == v

    def test_business_categories_present(self) -> None:
        # pipeline 的 11 个分类必须都能在 CategoryFilter 里找到（用于精确过滤）
        for v in (
            "AI",
            "AGENT",
            "LLM",
            "MCP",
            "PROGRAMMING",
            "OPENSOURCE",
            "PAPER",
            "STARTUP",
            "HARDWARE",
            "INTERNET",
            "BUSINESS",
        ):
            assert CategoryFilter(v).value == v


class TestSortWhitelist:
    def test_whitelist_exposes_only_safe_columns(self) -> None:
        # 不允许把 created_at / id / 任意内部字段做排序键
        assert set(SORT_WHITELIST.keys()) == {
            "recommendIndex",
            "heatScore",
            "lastSeenAt",
            "sourceCount",
        }

    def test_whitelist_values_are_real_columns(self) -> None:
        # 翻译：前端传的 camelCase 必须映射到 ORM 真实列
        assert SORT_WHITELIST["recommendIndex"] == "recommend_index"
        assert SORT_WHITELIST["heatScore"] == "heat_score"
        assert SORT_WHITELIST["lastSeenAt"] == "last_seen_at"
        assert SORT_WHITELIST["sourceCount"] == "source_count"


class TestAIGroup:
    def test_ai_tab_covers_related_categories(self) -> None:
        # SPEC：category=AI Tab 命中 categories 含 AI / LLM / AGENT / MCP 任一
        assert AI_CATEGORY_GROUP == ("AI", "LLM", "AGENT", "MCP")


class TestLockableFields:
    def test_exact_set(self) -> None:
        # SPEC：title / summaryOneLine / categories 三字段可锁定
        # 一旦改了这里，service 的 lock_name 映射也要同步
        assert set(LOCKABLE_FIELDS) == {"title", "summaryOneLine", "categories"}


@pytest.mark.parametrize("enum_cls", [Scope, CategoryFilter])
def test_all_enum_members_are_strings(enum_cls) -> None:
    """枚举必须是 StrEnum 兼容（与数据库 VARCHAR 列对齐）。"""
    for m in enum_cls:
        assert isinstance(m.value, str)
        assert m.value.isupper()
        assert " " not in m.value
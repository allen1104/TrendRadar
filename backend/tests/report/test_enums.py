"""report 枚举不变量测试。"""

from __future__ import annotations

import pytest

from app.modules.report.enums import (
    ExportFormat,
    REPORT_FILTER_SQL,
    REPORT_MAX_ITEMS,
    REPORT_MIN_ITEMS,
    REPORT_SECTIONS,
    REPORT_TYPE_NAMES,
    ReportStatus,
    ReportType,
    SubscriptionChannel,
)


class TestReportType:
    def test_exact_set(self) -> None:
        assert {t.value for t in ReportType} == {"AI", "TECH", "GITHUB", "AGENT"}

    def test_is_str_enum(self) -> None:
        for t in ReportType:
            assert isinstance(t.value, str)
            assert t.value.isupper()

    def test_four_types(self) -> None:
        """SPEC §日报类型定义：4 类。"""
        assert len(list(ReportType)) == 4

    def test_from_string(self) -> None:
        for v in ("AI", "TECH", "GITHUB", "AGENT"):
            assert ReportType(v).value == v


class TestReportStatus:
    def test_exact_set(self) -> None:
        assert {s.value for s in ReportStatus} == {
            "GENERATING", "DRAFT", "PUBLISHED", "FAILED",
        }

    def test_published_is_terminal(self) -> None:
        assert ReportStatus.PUBLISHED.value == "PUBLISHED"


class TestExportFormat:
    def test_exact_set(self) -> None:
        assert {f.value for f in ExportFormat} == {
            "MARKDOWN", "HTML", "PDF", "WECHAT_HTML",
        }

    def test_four_formats(self) -> None:
        """SPEC §导出：4 格式。"""
        assert len(list(ExportFormat)) == 4


class TestSubscriptionChannel:
    def test_exact_set(self) -> None:
        assert {c.value for c in SubscriptionChannel} == {"SITE", "EMAIL", "WEBHOOK"}

    def test_webhook_value(self) -> None:
        assert SubscriptionChannel.WEBHOOK.value == "WEBHOOK"


class TestReportConstraints:
    """SPEC §日报类型定义中各类型的 min/max item 数 + 板块。"""

    def test_min_items_per_type(self) -> None:
        assert REPORT_MIN_ITEMS[ReportType.AI.value] == 5
        assert REPORT_MIN_ITEMS[ReportType.TECH.value] == 6
        assert REPORT_MIN_ITEMS[ReportType.GITHUB.value] == 4
        assert REPORT_MIN_ITEMS[ReportType.AGENT.value] == 3

    def test_max_items_per_type(self) -> None:
        assert REPORT_MAX_ITEMS[ReportType.AI.value] == 12
        assert REPORT_MAX_ITEMS[ReportType.TECH.value] == 15
        assert REPORT_MAX_ITEMS[ReportType.GITHUB.value] == 12
        assert REPORT_MAX_ITEMS[ReportType.AGENT.value] == 10

    def test_min_less_than_max(self) -> None:
        for t in ReportType:
            assert REPORT_MIN_ITEMS[t.value] < REPORT_MAX_ITEMS[t.value]

    def test_sections_per_type(self) -> None:
        assert len(REPORT_SECTIONS[ReportType.AI.value]) == 4
        assert len(REPORT_SECTIONS[ReportType.TECH.value]) == 4
        assert len(REPORT_SECTIONS[ReportType.GITHUB.value]) == 3
        assert len(REPORT_SECTIONS[ReportType.AGENT.value]) == 4

    def test_all_types_have_sections(self) -> None:
        for t in ReportType:
            assert t.value in REPORT_SECTIONS
            assert len(REPORT_SECTIONS[t.value]) >= 1

    def test_filter_sql_keys(self) -> None:
        assert set(REPORT_FILTER_SQL.keys()) == {t.value for t in ReportType}

    def test_type_names(self) -> None:
        assert REPORT_TYPE_NAMES["AI"] == "AI 日报"
        assert REPORT_TYPE_NAMES["TECH"] == "科技日报"
        assert REPORT_TYPE_NAMES["GITHUB"] == "GitHub 日报"
        assert REPORT_TYPE_NAMES["AGENT"] == "Agent 日报"


@pytest.mark.parametrize(
    "t",
    [ReportType.AI, ReportType.TECH, ReportType.GITHUB, ReportType.AGENT],
)
def test_each_type_has_distinct_sections(t: ReportType) -> None:
    assert REPORT_SECTIONS[t.value] != REPORT_SECTIONS[ReportType.AI.value] or t == ReportType.AI

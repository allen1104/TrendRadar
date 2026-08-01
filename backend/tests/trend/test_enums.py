"""trend 枚举测试。"""

from __future__ import annotations

import pytest

from app.modules.trend.enums import EntityType, TrendMetric, TrendWindow


class TestTrendWindow:
    def test_values(self) -> None:
        assert TrendWindow.D7.value == "7D"
        assert TrendWindow.D30.value == "30D"
        assert TrendWindow.Y1.value == "1Y"

    def test_member_count(self) -> None:
        assert {m.value for m in TrendWindow} == {"7D", "30D", "1Y"}

    def test_from_string(self) -> None:
        assert TrendWindow("7D") is TrendWindow.D7


class TestTrendMetric:
    def test_values(self) -> None:
        assert TrendMetric.GROWTH.value == "GROWTH"
        assert TrendMetric.HOT.value == "HOT"

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            TrendMetric("WEIRD")


class TestEntityType:
    def test_values(self) -> None:
        assert EntityType.COMPANY.value == "COMPANY"
        assert EntityType.PRODUCT.value == "PRODUCT"
        assert EntityType.TECH.value == "TECH"
        assert EntityType.PERSON.value == "PERSON"
        assert EntityType.ALL.value == "ALL"

    def test_full_set(self) -> None:
        assert {t.value for t in EntityType} == {
            "COMPANY", "PRODUCT", "TECH", "PERSON", "ALL",
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

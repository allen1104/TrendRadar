"""creation 枚举不变量测试。"""

from __future__ import annotations

import pytest

from app.modules.creation.enums import DraftStatus, ExportFormat, Platform, Style


class TestPlatform:
    def test_exact_set(self) -> None:
        assert {p.value for p in Platform} == {
            "WECHAT", "BLOG", "WEIBO", "XHS", "ZHIHU", "MARKDOWN",
        }

    def test_is_str_enum(self) -> None:
        for p in Platform:
            assert isinstance(p.value, str)
            assert p.value.isupper()

    def test_from_string(self) -> None:
        for v in ("WECHAT", "BLOG", "WEIBO", "XHS", "ZHIHU", "MARKDOWN"):
            assert Platform(v).value == v

    def test_six_platforms(self) -> None:
        """SPEC §平台规格 6 个。"""
        assert len(list(Platform)) == 6


class TestStyle:
    def test_exact_set(self) -> None:
        assert {s.value for s in Style} == {
            "TECHNICAL", "MARKETING", "DEEP_DIVE", "NEWS", "CASUAL",
        }

    def test_five_styles(self) -> None:
        assert len(list(Style)) == 5


class TestDraftStatus:
    def test_exact_set(self) -> None:
        assert {s.value for s in DraftStatus} == {"GENERATING", "DONE", "FAILED"}

    def test_lifecycle_order(self) -> None:
        order = ["GENERATING", "DONE", "FAILED"]
        assert [s.value for s in DraftStatus] == order


class TestExportFormat:
    def test_exact_set(self) -> None:
        assert {f.value for f in ExportFormat} == {
            "MARKDOWN", "HTML", "WECHAT_HTML", "TXT",
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
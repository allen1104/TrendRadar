"""assistant 枚举不变量测试。"""

from __future__ import annotations

import pytest
from app.modules.assistant.enums import Feedback, MessageRole, MessageStatus


class TestMessageRole:
    def test_exact_set(self) -> None:
        assert {r.value for r in MessageRole} == {"USER", "ASSISTANT"}

    def test_is_str_enum(self) -> None:
        for r in MessageRole:
            assert isinstance(r.value, str)
            assert r.value.isupper()

    def test_from_string(self) -> None:
        for v in ("USER", "ASSISTANT"):
            assert MessageRole(v).value == v


class TestMessageStatus:
    def test_exact_set(self) -> None:
        assert {s.value for s in MessageStatus} == {"PENDING", "STREAMING", "DONE", "FAILED"}

    def test_order_matches_lifecycle(self) -> None:
        order = ["PENDING", "STREAMING", "DONE", "FAILED"]
        assert [s.value for s in MessageStatus] == order


class TestFeedback:
    def test_exact_set(self) -> None:
        assert {f.value for f in Feedback} == {"LIKE", "DISLIKE"}

    def test_from_string(self) -> None:
        assert Feedback("LIKE").value == "LIKE"
        assert Feedback("DISLIKE").value == "DISLIKE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
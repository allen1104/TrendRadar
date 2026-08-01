"""collection 枚举不变量测试。"""

from __future__ import annotations

import pytest

from app.modules.collection.enums import ReadStatus


class TestReadStatus:
    def test_exact_set(self) -> None:
        assert {s.value for s in ReadStatus} == {"UNREAD", "LATER", "READ"}

    def test_is_str_enum(self) -> None:
        for s in ReadStatus:
            assert isinstance(s.value, str)
            assert s.value.isupper()

    def test_from_string(self) -> None:
        for v in ("UNREAD", "LATER", "READ"):
            assert ReadStatus(v).value == v


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
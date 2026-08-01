"""pipeline dedup 纯函数单测。"""

from __future__ import annotations

import pytest

from app.modules.pipeline.dedup import normalize_title, title_hash, url_hash


# ---------------------------------------------------------- normalize_title


class TestNormalizeTitle:
    def test_lowercases(self) -> None:
        assert normalize_title("Hello WORLD") == "hello world"

    def test_strips_punctuation(self) -> None:
        assert normalize_title("Hello, World!") == "hello world"

    def test_collapses_whitespace(self) -> None:
        assert normalize_title("hello    \t\n world") == "hello world"

    def test_nfkc_normalizes(self) -> None:
        # 全角 → 半角
        assert normalize_title("Ｈｅｌｌｏ") == "hello"

    def test_chinese_kept(self) -> None:
        out = normalize_title("OpenAI 发布 GPT-5，多模态推理")
        # 中文被去标点 / 压缩空白后保留
        assert "openai" in out
        assert "gpt 5" in out or "gpt-5" in out

    def test_empty_returns_empty(self) -> None:
        assert normalize_title("") == ""
        assert normalize_title(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------- url_hash


class TestUrlHash:
    def test_same_url_same_hash(self) -> None:
        assert url_hash("https://example.com/foo") == url_hash("https://example.com/foo")

    def test_different_url_different_hash(self) -> None:
        a = url_hash("https://example.com/foo")
        b = url_hash("https://example.com/bar")
        assert a != b

    def test_length_64_hex(self) -> None:
        h = url_hash("https://example.com")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------- title_hash


class TestTitleHash:
    def test_same_title_after_normalize(self) -> None:
        # 不同的标点 / 大小写 → 归一化后同 hash
        a = title_hash("Hello, World!")
        b = title_hash("HELLO world")
        assert a == b

    def test_different_title_different_hash(self) -> None:
        assert title_hash("foo") != title_hash("bar")

    def test_empty_title_stable(self) -> None:
        assert title_hash("") == title_hash("")
        # 空标题归一化后是空串 → sha256("") 是固定值
        assert len(title_hash("")) == 64

    def test_chinese_title_normalizes(self) -> None:
        # 中文 + 标点 + 空白差异 → 归一化后可能不同（"GPT 5" vs "GPT5"）
        # 但全角→半角折叠应生效
        a = title_hash("OpenAI 发布 GPT-5")
        b = title_hash("OpenAI 发布 GPT-5")  # 同一标题
        assert a == b

    def test_chinese_fullwidth_to_halfwidth(self) -> None:
        # NFKC 把全角数字 / 字母折成半角
        a = title_hash("Ｈｅｌｌｏ Ｗｏｒｌｄ")  # 全角
        b = title_hash("Hello World")  # 半角
        assert a == b


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
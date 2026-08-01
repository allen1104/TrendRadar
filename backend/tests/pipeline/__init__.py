"""pipeline cleaner 纯函数单测。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.pipeline.cleaner import (
    extract_content,
    extract_keywords,
    normalize_published_at,
    should_discard,
    strip_ad_paragraphs,
    summarize,
    take_author,
    utcnow,
)


# ---------------------------------------------------------- extract_content


class TestExtractContent:
    def test_strips_script_and_style(self) -> None:
        html = "<p>Hello</p><script>alert(1)</script><style>.x{}</style><b>World</b>"
        out = extract_content(html)
        assert "Hello" in out
        assert "alert" not in out
        assert "World" in out
        assert "<" not in out

    def test_none_returns_empty(self) -> None:
        assert extract_content(None) == ""

    def test_empty_string_returns_empty(self) -> None:
        assert extract_content("") == ""

    def test_strips_comments(self) -> None:
        html = "<p>visible</p><!-- hidden -->"
        out = extract_content(html)
        assert "visible" in out
        assert "hidden" not in out


# ---------------------------------------------------------- strip_ad_paragraphs


class TestStripAdParagraphs:
    def test_removes_sponsored_line(self) -> None:
        content = "Real news first paragraph.\nSponsored: buy this product\nMore real news."
        out = strip_ad_paragraphs(content)
        assert "Real news" in out
        assert "Sponsored" not in out
        assert "More real news" in out

    def test_removes_chinese_ad(self) -> None:
        content = "第一段正文。\n广告：扫码关注\n第二段正文。"
        out = strip_ad_paragraphs(content)
        assert "第一段" in out
        assert "扫码" not in out
        assert "第二段" in out

    def test_empty_returns_empty(self) -> None:
        assert strip_ad_paragraphs("") == ""


# ---------------------------------------------------------- normalize_published_at


class TestNormalizePublishedAt:
    def test_iso_string_to_utc(self) -> None:
        out = normalize_published_at("2026-07-29T08:30:00+08:00")
        assert out == datetime(2026, 7, 29, 0, 30, tzinfo=timezone.utc)

    def test_naive_string_assumes_utc(self) -> None:
        out = normalize_published_at("2026-07-29T08:30:00")
        assert out.tzinfo == timezone.utc

    def test_datetime_passthrough_to_utc(self) -> None:
        dt = datetime(2026, 7, 29, 8, 30, tzinfo=timezone(timedelta(hours=8)))
        out = normalize_published_at(dt)
        assert out == datetime(2026, 7, 29, 0, 30, tzinfo=timezone.utc)

    def test_naive_datetime_assumes_utc(self) -> None:
        dt = datetime(2026, 7, 29, 8, 30)
        out = normalize_published_at(dt)
        assert out.tzinfo == timezone.utc

    def test_invalid_string_falls_back(self) -> None:
        fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = normalize_published_at("not a date", fallback=fallback)
        assert out == fallback

    def test_none_uses_fallback_or_now(self) -> None:
        fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert normalize_published_at(None, fallback=fallback) == fallback


# ---------------------------------------------------------- take_author


class TestTakeAuthor:
    def test_uses_hint_first(self) -> None:
        assert take_author("By Alice", content="By Bob in body") == "By Alice"

    def test_extracts_from_body_when_no_hint(self) -> None:
        content = "Some article body.\nBy Carol Smith\nMore body."
        assert take_author(None, content) == "Carol Smith"

    def test_returns_none_when_nothing(self) -> None:
        assert take_author(None, None) is None

    def test_truncates_long_author(self) -> None:
        long = "x" * 300
        out = take_author(long)
        assert out is not None
        assert len(out) <= 200


# ---------------------------------------------------------- summarize


class TestSummarize:
    def test_first_three_sentences(self) -> None:
        content = "Sentence one. Sentence two. Sentence three. Sentence four."
        out = summarize(content)
        assert "Sentence one" in out
        assert "Sentence two" in out
        assert "Sentence three" in out
        assert "Sentence four" not in out

    def test_chinese_punctuation(self) -> None:
        content = "第一句。第二句。第三句。第四句。"
        out = summarize(content)
        assert "第一句" in out
        assert "第四句" not in out

    def test_empty_returns_empty(self) -> None:
        assert summarize("") == ""
        assert summarize(None) == ""

    def test_max_chars_truncates(self) -> None:
        content = "X" * 500
        out = summarize(content, max_chars=100)
        assert len(out) <= 100


# ---------------------------------------------------------- extract_keywords


class TestExtractKeywords:
    def test_short_text_returns_empty(self) -> None:
        assert extract_keywords("too short", "en") == []

    def test_empty_returns_empty(self) -> None:
        assert extract_keywords("", "en") == []
        assert extract_keywords("", "zh") == []

    def test_chinese_returns_list_or_empty(self) -> None:
        content = (
            "人工智能技术正在快速发展，深度学习模型不断突破，"
            "大语言模型在各个领域得到广泛应用，自然语言处理能力持续提升。"
        )
        out = extract_keywords(content, "zh")
        assert isinstance(out, list)

    def test_english_returns_list_or_empty(self) -> None:
        content = (
            "Machine learning models are transforming software development. "
            "Deep learning algorithms enable new capabilities in natural language processing. "
            "Neural networks power modern AI applications across many domains."
        )
        out = extract_keywords(content, "en")
        assert isinstance(out, list)

    def test_unknown_lang_returns_empty(self) -> None:
        # lang 不在 jieba/yake 路径上 → 回退 []
        out = extract_keywords("a" * 100, "fr")
        assert out == []


# ---------------------------------------------------------- should_discard


class TestShouldDiscard:
    def test_short_content_short_title_discarded(self) -> None:
        is_discard, reason = should_discard(
            title="x",
            content="y",
            lang="en",
            published_at=utcnow(),
        )
        assert is_discard is True
        assert reason == "content too short"

    def test_normal_content_kept(self) -> None:
        is_discard, reason = should_discard(
            title="A reasonable article title",
            content="x" * 500,
            lang="en",
            published_at=utcnow(),
        )
        assert is_discard is False
        assert reason is None

    def test_unsupported_lang_discarded(self) -> None:
        is_discard, reason = should_discard(
            title="ok",
            content="x" * 500,
            lang="ja",
            published_at=utcnow(),
        )
        assert is_discard is True
        assert "unsupported lang" in reason

    def test_old_article_discarded(self) -> None:
        old = utcnow() - timedelta(days=10)
        is_discard, reason = should_discard(
            title="ok",
            content="x" * 500,
            lang="en",
            published_at=old,
        )
        assert is_discard is True
        assert "old" in reason

    def test_zh_lang_supported(self) -> None:
        is_discard, _ = should_discard(
            title="中文标题",
            content="x" * 500,
            lang="zh",
            published_at=utcnow(),
        )
        assert is_discard is False

    def test_missing_title_or_content_treated_as_empty(self) -> None:
        is_discard, reason = should_discard(
            title=None, content=None, lang="en", published_at=utcnow()
        )
        assert is_discard is True
        assert reason == "content too short"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
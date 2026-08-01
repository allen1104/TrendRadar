"""source 插件 parse/normalize 单测（不连网络，纯函数）。

每个插件 ≥ 2 用例：成功 fixture + 空响应。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.source.plugins.arxiv import ArxivPlugin
from app.modules.source.plugins.base import (
    RawItem,
    normalize_url,
)
from app.modules.source.plugins.github_trending import GitHubTrendingPlugin as GithubTrendingPlugin
from app.modules.source.plugins.hacker_news import HackerNewsPlugin
from app.modules.source.plugins.huggingface import HuggingFacePlugin


# ----------------------------------------------------------------- 通用


class TestNormalizeUrl:
    def test_strips_utm_and_lowercase_host(self) -> None:
        out = normalize_url("HTTPS://Example.com/post?utm_source=x&keep=ok#frag")
        assert out == "https://example.com/post?keep=ok"

    def test_strips_fbclid_gclid(self) -> None:
        out = normalize_url("https://example.com/p?fbclid=abc&gclid=def&keep=1")
        assert "fbclid" not in out
        assert "gclid" not in out
        assert "keep=1" in out

    def test_trims_trailing_slash(self) -> None:
        assert normalize_url("https://example.com/post/") == "https://example.com/post"
        # 根路径保留 /
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_keeps_query_order(self) -> None:
        out = normalize_url("https://example.com/?b=2&a=1&utm_source=z")
        assert out == "https://example.com/?b=2&a=1"

    def test_invalid_url_returns_input(self) -> None:
        bad = "not a url"
        assert normalize_url(bad) == bad


# ----------------------------------------------------------------- Hacker News


HN_FIXTURE = [
    {
        "id": 41234567,
        "type": "story",
        "by": "alice",
        "title": "Show HN: I built an AI agent",
        "url": "https://example.com/post?utm_source=hn",
        "score": 320,
        "descendants": 88,
        "time": 1722350400,  # 2024-07-30 12:00 UTC
        "kids": [1, 2, 3],
        "dead": False,
        "deleted": False,
    },
    {
        "id": 41234568,
        "type": "story",
        "by": "bob",
        "title": "Another story",
        "url": "https://example.com/b",
        "score": 50,
        "time": 1722350800,
    },
]


class TestHackerNewsPlugin:
    def test_parse_filters_dead_and_deleted(self) -> None:
        raw = [
            *HN_FIXTURE,
            {"id": 99, "type": "story", "dead": True, "title": "x"},
            {"id": 100, "type": "story", "deleted": True, "title": "y"},
            {"id": 101, "type": "comment", "title": "z"},  # 非 story
        ]
        out = HackerNewsPlugin({}).parse(raw)
        assert len(out) == 2
        assert all(r["type"] == "story" for r in out)

    def test_normalize_to_raw_items(self) -> None:
        out = HackerNewsPlugin({}).normalize(HN_FIXTURE)
        assert len(out) == 2

        first = out[0]
        assert isinstance(first, RawItem)
        assert first.external_id == "41234567"
        assert first.url == "https://example.com/post"  # utm 已剥
        assert first.title == "Show HN: I built an AI agent"
        assert first.author == "alice"
        assert first.lang == "en"
        assert first.metrics["points"] == 320
        assert first.metrics["comments"] == 88
        assert first.extra["type"] == "hn"
        assert first.extra["kids"] == [1, 2, 3]
        # published_at 转 UTC
        assert first.published_at is not None
        assert first.published_at.tzinfo == timezone.utc

    def test_normalize_handles_missing_url(self) -> None:
        raw = [{"id": 1, "type": "story", "title": "x", "score": 1, "time": 1722350000}]
        out = HackerNewsPlugin({}).normalize(raw)
        assert "news.ycombinator.com" in out[0].url

    def test_normalize_empty_returns_empty(self) -> None:
        assert HackerNewsPlugin({}).normalize([]) == []


# ----------------------------------------------------------------- arXiv


ARXIV_ENTRIES = [
    {
        "id": "http://arxiv.org/abs/2407.12345v1",
        "title": "Test Paper Title",
        "summary": "Abstract content here.",
        "author": "Alice",
        "published_parsed": (2024, 7, 30, 0, 0, 0, 0, 0, 0),
        "link": "http://arxiv.org/abs/2407.12345v1",
        "tags": [{"term": "cs.AI"}],
        "arxiv_primary_category": {"term": "cs.AI"},
    },
    {
        "id": "http://arxiv.org/abs/2407.67890v2",
        "title": "Another Paper",
        "summary": "Another abstract.",
        "author": "Bob",
        "published_parsed": (2024, 7, 29, 12, 0, 0, 0, 0, 0),
        "link": "http://arxiv.org/abs/2407.67890v2",
        "tags": [{"term": "cs.LG"}],
        "arxiv_primary_category": "cs.LG",
    },
]


class TestArxivPlugin:
    def test_parse_passthrough(self) -> None:
        out = ArxivPlugin({}).parse(ARXIV_ENTRIES)
        assert out == ARXIV_ENTRIES

    def test_normalize_to_raw_items(self) -> None:
        out = ArxivPlugin({}).normalize(ARXIV_ENTRIES)
        assert len(out) == 2
        first = out[0]
        assert first.external_id == "http://arxiv.org/abs/2407.12345v1"
        assert first.lang == "en"
        assert first.title == "Test Paper Title"
        assert first.published_at is not None
        assert first.published_at.tzinfo == timezone.utc
        assert first.extra["categories"] == ["cs.AI"]
        assert first.extra["tags"] == ["cs.AI"]

    def test_empty_returns_empty(self) -> None:
        assert ArxivPlugin({}).normalize([]) == []


# ----------------------------------------------------------------- GitHub Trending


GH_HTML = """
<html><body>
<article class="Box-row">
  <h2><a href="/owner/repo-1">owner / repo-1</a></h2>
  <p class="col-9">A short description of repo 1.</p>
  <span class="d-inline-block float-sm-right">123 stars today</span>
  <span itemprop="programmingLanguage">Python</span>
</article>
<article class="Box-row">
  <h2><a href="/owner/repo-2">owner / repo-2</a></h2>
  <p>Repo 2 description.</p>
  <span class="d-inline-block float-sm-right">45 stars today</span>
  <span itemprop="programmingLanguage">TypeScript</span>
</article>
</body></html>
"""


class TestGithubTrendingPlugin:
    def test_parse_extracts_repos(self) -> None:
        out = GithubTrendingPlugin({}).parse([{"html": GH_HTML, "url": "https://github.com/trending"}])
        assert len(out) == 2
        assert out[0]["full_name"] == "owner/repo-1"
        assert out[0]["stars_today"] == 123
        assert out[0]["language"] == "Python"

    def test_normalize_to_raw_items(self) -> None:
        out = GithubTrendingPlugin({}).parse([{"html": GH_HTML, "url": "https://github.com/trending"}])
        items = GithubTrendingPlugin({}).normalize(out)
        assert len(items) == 2
        first = items[0]
        assert first.external_id == "owner/repo-1"
        assert first.url == "https://github.com/owner/repo-1"
        assert first.lang == "en"
        assert first.extra["language"] == "Python"
        assert first.extra["type"] == "github-trending"
        assert first.metrics["stars_today"] == 123

    def test_empty_html_returns_empty(self) -> None:
        empty = "<html><body></body></html>"
        out = GithubTrendingPlugin({}).parse([{"html": empty, "url": "x"}])
        assert out == []


# ----------------------------------------------------------------- HuggingFace


HF_FIXTURE = [
    {
        "id": "openai/gpt-oss-120b",
        "modelId": "openai/gpt-oss-120b",
        "downloads": 12345,
        "likes": 67,
        "tags": ["text-generation"],
        "createdAt": "2024-07-30T12:00:00.000Z",
        "pipeline_tag": "text-generation",
    },
    {
        "id": "anthropic/claude-3",
        "modelId": "anthropic/claude-3",
        "downloads": 9999,
        "likes": 50,
        "tags": ["text-generation"],
        "createdAt": "2024-07-29T00:00:00.000Z",
        "pipeline_tag": "text-generation",
    },
]


class TestHuggingFacePlugin:
    def test_parse_passthrough(self) -> None:
        out = HuggingFacePlugin({}).parse(HF_FIXTURE)
        assert out == HF_FIXTURE

    def test_normalize_to_raw_items(self) -> None:
        out = HuggingFacePlugin({}).normalize(HF_FIXTURE)
        assert len(out) == 2
        first = out[0]
        assert first.external_id == "openai/gpt-oss-120b"
        assert first.url == "https://huggingface.co/openai/gpt-oss-120b"
        assert first.lang == "en"
        assert first.metrics["stars"] == 67
        assert first.metrics["downloads"] == 12345
        assert first.extra["pipeline_tag"] == "text-generation"
        assert first.published_at is not None
        assert first.published_at.tzinfo == timezone.utc

    def test_empty_returns_empty(self) -> None:
        assert HuggingFacePlugin({}).normalize([]) == []

    def test_missing_created_at_published_at_none(self) -> None:
        out = HuggingFacePlugin({}).normalize(
            [{"id": "x/y", "downloads": 1, "likes": 1, "tags": []}]
        )
        assert len(out) == 1
        assert out[0].published_at is None


# ----------------------------------------------------------------- 注册表


def test_all_real_plugins_registered() -> None:
    from app.modules.source.plugins import list_registered_plugins

    keys = {k for k, _ in list_registered_plugins()}
    for required in ("hacker_news", "github_trending", "arxiv", "huggingface"):
        assert required in keys, f"插件 {required} 未注册"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
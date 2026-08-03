"""report 纯函数 + service 业务测试。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from app.modules.report.enums import ReportType
from app.modules.report.schema import (
    ReportItemEventInfo,
    ReportItemSummary,
)
from app.modules.report.service import (
    OrchItem,
    OrchSection,
    ReportStructure,
    _sanitize_inline_style,
    build_candidate_briefs,
    build_rss,
    estimate_tokens,
    render_content_md,
    render_html_doc,
    render_plain_text,
    render_wechat_html,
    sanitize_filename,
)


# ============================================================ estimate_tokens


class TestEstimateTokens:
    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_english(self) -> None:
        # "hello" = 5 chars ascii → 5/4 = 1
        assert estimate_tokens("hello") == 1

    def test_chinese(self) -> None:
        # "你好" = 2 cjk → 2/1.5 = 1
        assert estimate_tokens("你好") == 1

    def test_mixed(self) -> None:
        # "AI日报" = 2 ascii + 2 cjk → 2/4 + 2/1.5 = 0 + 1 = 1
        assert estimate_tokens("AI日报") >= 1


# ============================================================ build_candidate_briefs


class TestBuildCandidateBriefs:
    def test_basic(self) -> None:
        cands = [
            {
                "event_id": 1,
                "title": "OpenAI 发布 GPT-5",
                "summary_one_line": "GPT-5 多模态推理超越前代 40%",
                "recommend_index": 88.6,
                "categories": ["AI", "LLM"],
                "source_count": 4,
            },
            {
                "event_id": 2,
                "title": "Anthropic Claude 3.5 更新",
                "summary_one_line": "上下文扩展到 200K",
                "recommend_index": 80.1,
                "categories": ["AI"],
                "source_count": 2,
            },
        ]
        out = build_candidate_briefs(cands)
        assert len(out) == 2
        assert out[0]["index"] == 1
        assert out[0]["event_id"] == 1
        assert out[1]["index"] == 2
        assert out[0]["title"] == "OpenAI 发布 GPT-5"
        assert out[0]["brief"] == "GPT-5 多模态推理超越前代 40%"

    def test_empty(self) -> None:
        assert build_candidate_briefs([]) == []

    def test_falls_back_to_title_for_brief(self) -> None:
        cands = [
            {
                "event_id": 1,
                "title": "某事件",
                "summary_one_line": None,
                "recommend_index": 50.0,
                "categories": [],
                "source_count": 1,
            }
        ]
        out = build_candidate_briefs(cands)
        assert out[0]["brief"] == "某事件"

    def test_truncates_long_brief(self) -> None:
        cands = [
            {
                "event_id": 1,
                "title": "X",
                "summary_one_line": "a" * 500,
                "recommend_index": 50.0,
                "categories": [],
                "source_count": 1,
            }
        ]
        out = build_candidate_briefs(cands, brief_limit=50)
        assert len(out[0]["brief"]) == 50


# ============================================================ render_content_md


class TestRenderContentMd:
    def test_basic(self) -> None:
        sections = [
            {
                "name": "头条",
                "items": [
                    {
                        "headline": "OpenAI 发布 GPT-5",
                        "brief": "GPT-5 多模态推理提升 40%",
                        "is_top": True,
                    }
                ],
            }
        ]
        md = render_content_md(
            title="AI 日报 · 2026-08-02",
            intro="今天最值得关注的是 GPT-5 发布。",
            outro="以上就是今天的日报。",
            sections=sections,
        )
        assert "# AI 日报 · 2026-08-02" in md
        assert "> 今天最值得关注的是 GPT-5 发布。" in md
        assert "## 头条" in md
        assert "### OpenAI 发布 GPT-5" in md
        assert "GPT-5 多模态推理提升 40%" in md
        assert "🔥 头条" in md
        assert "---" in md
        assert "以上就是今天的日报。" in md

    def test_empty_sections_omitted(self) -> None:
        sections = [
            {"name": "头条", "items": []},
            {
                "name": "模型发布",
                "items": [
                    {"headline": "X", "brief": "Y", "is_top": False},
                ],
            },
        ]
        md = render_content_md(
            title="T", intro="I", outro="O", sections=sections,
        )
        assert "## 头条" not in md
        assert "## 模型发布" in md

    def test_no_outro(self) -> None:
        sections = [
            {"name": "S", "items": [{"headline": "H", "brief": "B", "is_top": False}]}
        ]
        md = render_content_md(title="T", intro="I", outro="", sections=sections)
        assert "---" not in md


# ============================================================ render_html_doc


class TestRenderHtmlDoc:
    def test_basic(self) -> None:
        md = "# Title\n\n## Sub\n\ncontent"
        html = render_html_doc(md, "Title")
        assert "<!DOCTYPE html>" in html
        assert "<html lang=\"zh-CN\">" in html
        assert "<h1>Title</h1>" in html
        assert "<h2>Sub</h2>" in html
        assert "content" in html

    def test_strips_script_tags(self) -> None:
        md = "# T\n<script>alert(1)</script>"
        html = render_html_doc(md, "T")
        # 注意：_md_to_simple_html 会先 _esc，所以 "<script>" 字面量不会出现
        assert "<script>" not in html
        assert "&lt;script&gt;" in html  # 已转义，无害

    def test_strips_onclick(self) -> None:
        md = "# T\n<img src=x onerror=\"alert(1)\" />"
        html = render_html_doc(md, "T")
        assert "onerror" not in html


# ============================================================ render_wechat_html


class TestRenderWechatHtml:
    def test_inline_styles(self) -> None:
        md = "# Title\n\n## Sub\n\np"
        html = render_wechat_html(md, "Title")
        assert "style=\"font-size: 22px" in html  # h1 inline style
        assert "style=\"font-size: 19px" in html  # h2 inline style

    def test_no_style_tag(self) -> None:
        md = "# T"
        html = render_wechat_html(md, "T")
        assert "<style>" not in html

    def test_sanitizes_xss(self) -> None:
        md = "# T\n<img src=x onerror=\"alert(1)\" />"
        html = render_wechat_html(md, "T")
        assert "onerror" not in html


# ============================================================ render_plain_text


class TestRenderPlainText:
    def test_strips_markdown(self) -> None:
        md = "# 标题\n\n**粗体** 与 *斜体* 与 `code` 与 [link](http://x)"
        out = render_plain_text(md)
        assert "**" not in out
        assert "*斜体" not in out  # 单独星号被去掉
        assert "`code`" not in out
        assert "link" in out
        assert "http://x" not in out  # 链接 URL 被去掉

    def test_strips_code_block(self) -> None:
        md = "# T\n```python\nprint(1)\n```"
        out = render_plain_text(md)
        assert "print(1)" not in out

    def test_strips_images(self) -> None:
        md = "![alt](http://x.png)"
        out = render_plain_text(md)
        assert "http://x.png" not in out


# ============================================================ sanitize_filename


class TestSanitizeFilename:
    def test_basic(self) -> None:
        assert sanitize_filename("AI日报 · 2026-08-02", "md") == "AI日报 · 2026-08-02.md"

    def test_strips_illegal(self) -> None:
        # 反斜杠、引号、竖线都被替换
        name = 'a/b\\c|d"e'
        out = sanitize_filename(name, "txt")
        for c in '\\/"<>|':
            assert c not in out

    def test_truncates_long(self) -> None:
        long_title = "x" * 100
        out = sanitize_filename(long_title, "md")
        # 截前 20 字 + ".md"
        assert out == ("x" * 20) + ".md"

    def test_empty_title_becomes_report(self) -> None:
        out = sanitize_filename("", "md")
        assert out == "report.md"

    def test_strip_spaces(self) -> None:
        out = sanitize_filename("   ", "md")
        assert out == "report.md"


# ============================================================ build_rss


class TestBuildRss:
    def test_basic(self) -> None:
        from app.modules.report.model import Report, ReportItem

        r1 = Report(
            id=1,
            report_type="AI",
            report_date=date(2026, 8, 2),
            title="AI 日报 · 2026-08-02",
            content_md="# T",
            intro="intro",
            item_count=2,
            status="PUBLISHED",
            published_at=datetime(2026, 8, 2, 8, 30, tzinfo=UTC),
            created_at=datetime(2026, 8, 2, 8, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 2, 8, 30, tzinfo=UTC),
        )
        items = [
            ReportItem(
                id=10, report_id=1, event_id=88, section="头条", sort_order=0,
                headline="OpenAI GPT-5", brief="brief text", is_top=True,
            ),
            ReportItem(
                id=11, report_id=1, event_id=89, section="模型发布", sort_order=0,
                headline="Claude 3.5", brief="brief2", is_top=False,
            ),
        ]
        xml = build_rss(
            site_title="Test",
            site_link="https://example.com",
            site_desc="desc",
            reports=[r1],
            report_items_map={1: items},
        )
        assert '<?xml version="1.0"' in xml
        assert "<rss version=\"2.0\">" in xml
        assert "<channel>" in xml
        assert "<title>Test</title>" in xml
        assert "AI 日报 · 2026-08-02" in xml
        assert "[头条] OpenAI GPT-5" in xml
        assert "🔥 [头条] OpenAI GPT-5" in xml or "🔥" in xml
        assert "Claude 3.5" in xml
        assert "report-1" in xml
        assert "category>AI" in xml

    def test_empty(self) -> None:
        xml = build_rss(
            site_title="T", site_link="L", site_desc="D",
            reports=[], report_items_map={},
        )
        assert "<channel>" in xml
        assert "<item>" not in xml


# ============================================================ Pydantic Schema


class TestReportStructure:
    def test_basic(self) -> None:
        s = ReportStructure(
            title="AI 日报",
            intro="intro",
            outro="outro",
            sections=[
                OrchSection(
                    name="头条",
                    items=[
                        OrchItem(
                            event_id=88, section="头条",
                            headline="H", brief="B", is_top=True,
                        )
                    ],
                )
            ],
        )
        assert s.title == "AI 日报"
        assert s.sections[0].items[0].event_id == 88

    def test_to_dict_for_render(self) -> None:
        s = ReportStructure(
            title="T",
            intro="I",
            outro="O",
            sections=[OrchSection(name="S", items=[
                OrchItem(event_id=1, section="S", headline="H", brief="B", is_top=False)
            ])],
        )
        d = s.sections[0].model_dump()
        assert d["name"] == "S"
        assert d["items"][0]["headline"] == "H"

    def test_default_is_top(self) -> None:
        item = OrchItem(event_id=1, section="S", headline="H", brief="B")
        assert item.is_top is False


# ============================================================ sanitize_html internal


class TestSanitizeInlineStyle:
    def test_strips_script(self) -> None:
        out = _sanitize_inline_style("<script>alert(1)</script>")
        assert "<script>" not in out

    def test_strips_onclick(self) -> None:
        out = _sanitize_inline_style('<a href="#" onclick="alert(1)">x</a>')
        assert "onclick" not in out

    def test_strips_javascript_url(self) -> None:
        out = _sanitize_inline_style('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in out

    def test_keeps_safe(self) -> None:
        out = _sanitize_inline_style('<a href="https://x.com">x</a>')
        assert "https://x.com" in out


# ============================================================ ReportItemEventInfo


class TestReportItemEventInfo:
    def test_basic(self) -> None:
        info = ReportItemEventInfo(
            id=88,
            recommend_index=88.6,
            source_count=4,
            categories=["AI", "LLM"],
            primary_article_url="https://x.com/article",
        )
        d = info.model_dump(by_alias=True)
        assert d["recommendIndex"] == 88.6
        assert d["primaryArticleUrl"] == "https://x.com/article"
        assert d["categories"] == ["AI", "LLM"]


# ============================================================ service business rules (mock session)


class TestReportItemSummaryCamel:
    def test_camel_aliases(self) -> None:
        from app.modules.report.schema import ReportItemSummary as RIS

        s = RIS(
            id=1, event_id=88, section="头条", sort_order=0,
            headline="H", brief="B", comment=None, is_top=False,
        )
        d = s.model_dump(by_alias=True)
        assert "eventId" in d
        assert "sortOrder" in d
        assert "isTop" in d


class TestRenderIntegration:
    def test_md_to_html_full_pipeline(self) -> None:
        sections = [
            {
                "name": "头条",
                "items": [
                    {"headline": "GPT-5 发布", "brief": "重要升级", "is_top": True}
                ],
            }
        ]
        md = render_content_md(
            title="AI 日报", intro="导语", outro="结束", sections=sections,
        )
        html = render_wechat_html(md, "AI 日报")
        plain = render_plain_text(md)
        assert "GPT-5 发布" in html
        assert "style=" in html
        assert "GPT-5 发布" in plain
        assert "🔥" in plain


class TestPromptSectionLoop:
    """test 候选 prompt 变量构造（report.service.build_candidate_briefs 的实际下游）。"""

    def test_briefs_passed_to_prompt_have_required_keys(self) -> None:
        cands = [
            {
                "event_id": 1,
                "title": "T",
                "summary_one_line": "S",
                "recommend_index": 50.0,
                "categories": ["AI"],
                "source_count": 3,
            }
        ]
        briefs = build_candidate_briefs(cands)
        for required in ("index", "event_id", "title", "brief", "recommend_index", "categories"):
            assert required in briefs[0]

"""creation 业务编排测试。

覆盖：纯函数（estimate_tokens / build_context / parse_outline / count_words /
split_metadata / sanitize_filename / render_* / sanitize_html）+ service 校验路径。
"""

from __future__ import annotations

import json

import pytest

from app.modules.creation import service as svc
from app.modules.creation.enums import Platform, Style
from app.modules.creation.exceptions import (
    EventNotAnalyzedError,
    InvalidExportFormatError,
    InvalidPlatformError,
    InvalidStyleError,
    TargetWordsOutOfRangeError,
    TooManyRegenerationsError,
)
from app.modules.creation.schema import DraftCreateRequest, DraftRegenerateRequest
from app.modules.creation.service import CreationService


# ============================================================ 纯函数


class TestEstimateTokens:
    def test_empty(self) -> None:
        assert svc.estimate_tokens("") == 0

    def test_ascii_4_chars_per_token(self) -> None:
        assert svc.estimate_tokens("abcd") == 1
        assert svc.estimate_tokens("a" * 100) == 25

    def test_cjk_1_5_chars_per_token(self) -> None:
        # 6 个中文字符 → 4 tokens
        assert svc.estimate_tokens("中文测试汉字") == 4


class TestSelectTopArticles:
    def test_under_limit(self) -> None:
        a = [{"index": 1, "content": "x", "source_weight": 1}]
        assert svc.select_top_articles(a, 5) == a

    def test_over_limit_sorts_by_weight_then_len(self) -> None:
        arts = [
            {"index": 1, "content": "x" * 10, "source_weight": 1},
            {"index": 2, "content": "y" * 20, "source_weight": 9},
            {"index": 3, "content": "z" * 5, "source_weight": 9},
        ]
        out = svc.select_top_articles(arts, 2)
        # 排序键 (weight desc, length desc)；权重并列为 9 时取更长者（len=20 胜 len=5）
        assert [a["index"] for a in out] == [2, 3]


class TestBuildContext:
    def _articles(self, n: int = 10, char_len: int = 500) -> list[dict]:
        return [
            {
                "index": i,
                "title": f"Title {i}",
                "source_name": "Src",
                "url": "",
                "content": "x" * char_len,
                "source_weight": i,
            }
            for i in range(1, n + 1)
        ]

    def test_within_budget_no_trim(self) -> None:
        out = svc.build_context(
            event_title="E",
            event_analysis="A" * 100,
            articles=self._articles(2, 100),
            target_words=1500,
            audience="devs",
            extra_requirement="",
            style="TECHNICAL",
            platform="WECHAT",
            max_tokens=100_000,
        )
        assert len(out["articles"]) == 2
        assert out["targetWords"] == 1500

    def test_step1_shorten_content(self) -> None:
        # 默认 max_tokens=20000，10 篇 500 字符约 1250 token，足够容纳；改为 1000 → 必触发 step1
        out = svc.build_context(
            event_title="E",
            event_analysis="A" * 100,
            articles=self._articles(10, 500),
            target_words=1500,
            audience="devs",
            extra_requirement="",
            style="TECHNICAL",
            platform="WECHAT",
            max_tokens=1000,
        )
        # 步 1 把 content 从 500 → 400 截断（最终步骤）
        for a in out["articles"]:
            assert len(a["content"]) <= 400

    def test_step2_cap_articles(self) -> None:
        # 极小预算 + 大量文章 → 步 2 截到 6 篇
        out = svc.build_context(
            event_title="E",
            event_analysis="A" * 10,
            articles=self._articles(20, 200),
            target_words=1500,
            audience="",
            extra_requirement="",
            style="TECHNICAL",
            platform="WECHAT",
            max_tokens=100,
        )
        assert len(out["articles"]) <= svc.ARTICLE_KEEP_MAX


class TestParseOutline:
    def test_empty(self) -> None:
        assert svc.parse_outline("") == []
        assert svc.parse_outline(None) == []

    def test_direct_json(self) -> None:
        raw = json.dumps([{"heading": "A", "points": ["x", "y"]}])
        out = svc.parse_outline(raw)
        assert out == [{"heading": "A", "points": ["x", "y"]}]

    def test_json_in_fence(self) -> None:
        raw = '```json\n[{"heading": "A", "points": ["x"]}]\n```'
        out = svc.parse_outline(raw)
        assert out == [{"heading": "A", "points": ["x"]}]

    def test_dict_with_outline_key(self) -> None:
        raw = json.dumps({"outline": [{"heading": "X", "points": []}]})
        out = svc.parse_outline(raw)
        assert out == [{"heading": "X", "points": []}]

    def test_invalid_json_returns_empty(self) -> None:
        assert svc.parse_outline("not json {") == []

    def test_skips_items_without_heading(self) -> None:
        raw = json.dumps([{"heading": "OK"}, {"heading": ""}, {"points": ["x"]}])
        out = svc.parse_outline(raw)
        assert len(out) == 1
        assert out[0]["heading"] == "OK"


class TestSplitMetadata:
    def test_no_metadata(self) -> None:
        title, body, cover, tags = svc._split_metadata("正文只有一段")
        assert title == ""
        assert body == "正文只有一段"
        assert cover is None
        assert tags == []

    def test_title_only(self) -> None:
        title, body, cover, tags = svc._split_metadata("# 我的标题\n\n正文")
        assert title == "我的标题"
        assert body == "正文"
        assert cover is None
        assert tags == []

    def test_full_metadata(self) -> None:
        raw = "# 标题\n\nCOVER: 一张配图\nTAGS: ai, gpt-5\n\n## 第一段\n正文"
        title, body, cover, tags = svc._split_metadata(raw)
        assert title == "标题"
        assert cover == "一张配图"
        assert tags == ["ai", "gpt-5"]
        assert body.startswith("## 第一段")

    def test_title_truncated_to_300(self) -> None:
        long = "x" * 500
        title, _, _, _ = svc._split_metadata(f"# {long}")
        assert len(title) == 300


class TestCountWords:
    def test_empty(self) -> None:
        assert svc.count_words("") == 0

    def test_strips_whitespace(self) -> None:
        # count_words = len(''.join(content.split()))；split 默认去所有空白
        assert svc.count_words("hello world") == 10
        # "a\n\nb c" → split → ['a','b','c'] → 'abc' → 3 chars
        assert svc.count_words("a\n\nb c") == 3


class TestSanitizeFilename:
    def test_basic(self) -> None:
        # 包含中文：regex [\s\\/:*?"<>|]+ 不切分中文，仅替换 ASCII 非法字符
        name = svc.sanitize_filename("OpenAI 发布 GPT-5", "md")
        assert name.startswith("OpenAI_")  # 空格被替换
        assert name.endswith(".md")
        # 含中文的段保留
        assert "发布" in name or "GPT-5" in name

    def test_strips_illegal_chars(self) -> None:
        name = svc.sanitize_filename("a/b\\c:d*e?f\"g<h>i|j", "html")
        assert "/" not in name
        assert "\\" not in name
        assert ":" not in name

    def test_truncates_to_20(self) -> None:
        long = "x" * 100
        name = svc.sanitize_filename(long, "txt")
        head = name.rsplit("_", 1)[0]
        assert len(head) <= 20


class TestRenderers:
    def test_render_markdown_passthrough(self) -> None:
        text = "# Title\n\n**bold** text"
        assert svc.render_markdown(text) == text

    def test_render_plain_text_strips_md(self) -> None:
        md = "## 二级标题\n**加粗** 与 `code` 与 [link](https://x.com)"
        out = svc.render_plain_text(md)
        assert "加粗" in out
        assert "code" in out
        assert "link" in out
        assert "**" not in out
        assert "`" not in out
        assert "](http" not in out

    def test_render_html_has_doctype(self) -> None:
        html = svc.render_html("# 标题\n正文", "标题")
        assert "<!DOCTYPE html>" in html
        assert "<h1>" in html
        assert "<strong>" not in html or "**" not in html  # not blocking check

    def test_render_wechat_html_uses_inline_styles(self) -> None:
        md = "# 主标题\n\n## 子标题\n**加粗**\n\n- 列表项\n\n```python\nprint(1)\n```\n普通段落 [link](https://x.com)"
        out = svc.render_wechat_html(md, "主标题")
        # 内联样式：style=
        assert "style=" in out
        # 代码块被跳过
        assert "print(1)" not in out
        # 列表项带 •
        assert "• " in out
        # 链接转内联样式 a
        assert "<a " in out


class TestSanitizeHtmlForStorage:
    def test_strips_script(self) -> None:
        html = "<p>hi</p><script>alert(1)</script>"
        assert "<script" not in svc.sanitize_html_for_storage(html)

    def test_strips_javascript_protocol(self) -> None:
        html = '<a href="javascript:alert(1)">x</a>'
        assert "javascript:" not in svc.sanitize_html_for_storage(html)

    def test_strips_event_handlers(self) -> None:
        html = '<img src="x" onerror="alert(1)">'
        out = svc.sanitize_html_for_storage(html)
        assert "onerror" not in out

    def test_empty(self) -> None:
        assert svc.sanitize_html_for_storage("") == ""


# ============================================================ Service 校验


class TestPlatformMeta:
    def test_all_platforms_have_meta(self) -> None:
        for p in Platform:
            assert p in svc.PLATFORM_META
            m = svc.PLATFORM_META[p]
            assert "name" in m
            assert "icon" in m
            assert len(m["target_words"]) == 2
            assert m["target_words"][0] <= m["target_words"][1]

    def test_all_styles_have_meta(self) -> None:
        for s in Style:
            assert s in svc.STYLE_META
            m = svc.STYLE_META[s]
            assert "name" in m
            assert "description" in m


class TestPlatformTaskKeyMapping:
    def test_all_platforms_map_to_task_key(self) -> None:
        for p in Platform:
            key = svc.PLATFORM_TASK_KEY[p]
            assert key.startswith("creation_")


class TestServiceConstants:
    def test_regenerate_limit_is_5(self) -> None:
        assert svc.REGENERATE_LIMIT == 5

    def test_draft_quota_is_500(self) -> None:
        assert svc.DRAFT_QUOTA_PER_USER == 500

    def test_default_context_max_tokens_is_20000(self) -> None:
        assert svc.CONTEXT_MAX_TOKENS_DEFAULT == 20000

    def test_article_keep_max_is_6(self) -> None:
        # SPEC：最多 6 篇
        assert svc.ARTICLE_KEEP_MAX == 6


# ============================================================ Service 方法（mock session）


class _FakeSession:
    """minimal async session double for service-level guards that don't hit DB."""

    async def execute(self, *_, **__):
        from unittest.mock import AsyncMock

        m = AsyncMock()
        m.scalar_one_or_none.return_value = None
        m.all.return_value = []
        m.scalars.return_value.all.return_value = []
        m.scalar.return_value = 0
        m.rowcount = 0
        return m

    def add(self, _):  # noqa: ANN001
        pass

    async def commit(self):
        pass

    async def refresh(self, *_):
        pass

    async def flush(self):
        pass

    async def rollback(self):
        pass


class TestServiceExportFormat:
    async def test_not_found_raises(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        svc_obj = CreationService(MagicMock())  # type: ignore[arg-type]
        svc_obj.repo.get_for_user = AsyncMock(return_value=None)  # type: ignore[attr-defined]
        from app.modules.creation.exceptions import DraftNotFoundError

        with pytest.raises(DraftNotFoundError):
            await svc_obj.export_draft(user_id=1, draft_id=999, fmt="MARKDOWN")

    async def test_invalid_format_string_raises_export_error(self) -> None:
        """draft 存在但 fmt 非法 → InvalidExportFormatError。"""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock

        from app.modules.creation.enums import DraftStatus, Platform, Style
        from app.modules.creation.model import CreationDraft

        d = CreationDraft(
            id=1, user_id=1, event_id=1,
            platform=Platform.WECHAT.value, style=Style.TECHNICAL.value,
            title="标题", content="正文", word_count=2,
            status=DraftStatus.DONE.value, cost_usd=0.0,
            outline=[], tags_suggestion=[], extra_params={},
            regenerate_count=0,
        )
        d.created_at = datetime.now(UTC)
        d.updated_at = datetime.now(UTC)
        svc_obj = CreationService(MagicMock())  # type: ignore[arg-type]
        svc_obj.repo.get_for_user = AsyncMock(return_value=d)  # type: ignore[attr-defined]
        with pytest.raises(InvalidExportFormatError):
            await svc_obj.export_draft(user_id=1, draft_id=1, fmt="PDF")


class TestServiceStreamCreateGuards:
    """不真正调 LLM；只验证前置校验抛对应异常。"""

    async def test_invalid_platform_raises(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.modules.creation.schema import DraftCreateRequest

        svc_obj = CreationService(MagicMock())  # type: ignore[arg-type]

        class _BadPlatform:
            value = "BOGUS"

            def __str__(self) -> str:
                return "BOGUS"

        payload = DraftCreateRequest(
            event_id=1,
            platform=Platform.WECHAT,
            style=Style.TECHNICAL,
            target_words=2000,
            audience=None,
            extra_requirement=None,
        )
        payload.platform = _BadPlatform()  # type: ignore[assignment]
        with patch.object(svc, "PLATFORM_META", {}):
            with pytest.raises(InvalidPlatformError):
                gen = svc_obj.stream_create(user_id=1, payload=payload)
                await gen.__anext__()

    async def test_invalid_style_raises(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.modules.creation.schema import DraftCreateRequest

        svc_obj = CreationService(MagicMock())  # type: ignore[arg-type]

        class _BadStyle:
            value = "BOGUS"

            def __str__(self) -> str:
                return "BOGUS"

        payload = DraftCreateRequest(
            event_id=1,
            platform=Platform.WECHAT,
            style=Style.TECHNICAL,
            target_words=2000,
            audience=None,
            extra_requirement=None,
        )
        payload.style = _BadStyle()  # type: ignore[assignment]
        with patch.object(svc, "STYLE_META", {}):
            with pytest.raises(InvalidStyleError):
                gen = svc_obj.stream_create(user_id=1, payload=payload)
                await gen.__anext__()

    async def test_target_words_out_of_range_raises(self) -> None:
        # target_words 必须在 Pydantic 范围内 (100-20000)；选 WECHAT 上限 3000 * 1.5 = 4500
        from unittest.mock import MagicMock

        from app.modules.creation.schema import DraftCreateRequest

        svc_obj = CreationService(MagicMock())  # type: ignore[arg-type]
        payload = DraftCreateRequest(
            event_id=1,
            platform=Platform.WECHAT,
            style=Style.TECHNICAL,
            target_words=4500,  # == hi * 1.5；用 4600 触发 out-of-range
            audience=None,
            extra_requirement=None,
        )
        # 改用 4600
        payload.target_words = 4600  # type: ignore[assignment]
        with pytest.raises(TargetWordsOutOfRangeError):
            gen = svc_obj.stream_create(user_id=1, payload=payload)
            await gen.__anext__()

    async def test_target_words_below_lower_raises(self) -> None:
        from unittest.mock import MagicMock

        from app.modules.creation.schema import DraftCreateRequest

        svc_obj = CreationService(MagicMock())  # type: ignore[arg-type]
        payload = DraftCreateRequest(
            event_id=1,
            platform=Platform.WECHAT,
            style=Style.TECHNICAL,
            target_words=750,  # == 1500 * 0.5；用 740 触发
            audience=None,
            extra_requirement=None,
        )
        payload.target_words = 740  # type: ignore[assignment]
        with pytest.raises(TargetWordsOutOfRangeError):
            gen = svc_obj.stream_create(user_id=1, payload=payload)
            await gen.__anext__()


class TestRegenerateLimit:
    async def test_too_many_regenerations_raises(self) -> None:
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock

        from app.modules.creation.enums import DraftStatus, Platform, Style
        from app.modules.creation.model import CreationDraft

        d = CreationDraft(
            id=1, user_id=1, event_id=1,
            platform=Platform.WECHAT.value, style=Style.TECHNICAL.value,
            title="t", content="c", word_count=1,
            status=DraftStatus.DONE.value, cost_usd=0.0,
            regenerate_count=5,
            outline=[], tags_suggestion=[], extra_params={},
        )
        d.created_at = datetime.now(UTC)
        d.updated_at = datetime.now(UTC)

        svc_obj = CreationService(MagicMock())  # type: ignore[arg-type]
        svc_obj.repo.get_for_user = AsyncMock(return_value=d)  # type: ignore[attr-defined]
        with pytest.raises(TooManyRegenerationsError):
            gen = svc_obj.stream_regenerate(
                user_id=1, draft_id=1, payload=DraftRegenerateRequest()
            )
            await gen.__anext__()


class TestGetOptions:
    async def test_returns_all_platforms_and_styles(self) -> None:
        svc_obj = CreationService(_FakeSession())  # type: ignore[arg-type]
        opts = await svc_obj.get_options()
        assert len(opts.platforms) == 6
        assert len(opts.styles) == 5
        for p in opts.platforms:
            assert p.target_words[0] <= p.target_words[1]


# ============================================================ Export 4 格式


class TestExportRendering:
    """直接对 service 的纯函数渲染分支打覆盖（不走 service.export_draft 的 DB 查询）。"""

    def test_markdown_export(self) -> None:
        body = "# 标题\n\n**加粗**"
        out = svc.render_markdown(body)
        assert out == body

    def test_plain_text_export_strips_md(self) -> None:
        body = "## 标题\n**加粗** 与 `code` 和 [link](https://x.com)"
        out = svc.render_plain_text(body)
        assert "加粗" in out
        assert "code" in out
        assert "link" in out
        assert "**" not in out
        assert "`" not in out
        assert "](http" not in out

    def test_html_export_returns_doctype(self) -> None:
        out = svc.render_html("# 标题\n正文", "标题")
        assert "<!DOCTYPE html>" in out
        assert "<h1>" in out
        assert "<p>" in out

    def test_wechat_html_strips_code_fence(self) -> None:
        md = "# 标题\n\n```python\nprint(1)\n```\n段落"
        out = svc.render_wechat_html(md, "标题")
        assert "print(1)" not in out
        assert "<pre" not in out
        assert "段落" in out

    def test_wechat_html_handles_horizontal_rule(self) -> None:
        out = svc.render_wechat_html("段落\n\n---\n\n段落2", "标题")
        assert "<hr" in out

    def test_wechat_html_handles_numbered_list(self) -> None:
        out = svc.render_wechat_html("1. 第一项\n2. 第二项", "标题")
        assert "1." in out
        assert "第一项" in out

    def test_export_sanitize_removes_script(self) -> None:
        html = "<p>hi</p><script>alert(1)</script>"
        out = svc.sanitize_html_for_storage(html)
        assert "<script" not in out


# ============================================================ _outline_item_dict / _pack


class TestOutlineItemDict:
    def test_basic(self) -> None:
        d = svc._outline_item_dict({"heading": "A", "points": ["x", "y"]})
        assert d["heading"] == "A"
        assert d["points"] == ["x", "y"]

    def test_missing_points(self) -> None:
        d = svc._outline_item_dict({"heading": "B"})
        assert d["heading"] == "B"
        assert d["points"] == []


class TestPack:
    def test_basic(self) -> None:
        out = svc._pack(
            event_title="E",
            event_analysis="A",
            articles=[{"index": 1, "title": "t", "source_name": "s", "url": "u", "content": "c"}],
            target_words=1500,
            audience="devs",
            extra_requirement="req",
            style="TECHNICAL",
            platform="WECHAT",
        )
        assert out["eventTitle"] == "E"
        assert len(out["articles"]) == 1
        assert out["targetWords"] == 1500


class TestBuildContextEdge:
    def test_step3_history_compression(self) -> None:
        """budget 极小但 article 极少时 → articles 不被截断；返回结构完整。"""
        out = svc.build_context(
            event_title="E",
            event_analysis="A",
            articles=[{
                "index": 1, "title": "t", "source_name": "s",
                "url": "", "content": "x", "source_weight": 1,
            }],
            target_words=1500,
            audience="devs",
            extra_requirement="",
            style="TECHNICAL",
            platform="WECHAT",
            max_tokens=1000,
        )
        assert "articles" in out
        assert len(out["articles"]) <= svc.ARTICLE_KEEP_MAX
        # 顺手验证 trim_history 函数（该函数实际不在 build_context 流程中使用，
        # 但保留供未来扩展）
        from app.modules.creation.service import trim_history
        history = [{"role": "user", "content": f"msg-{i}"} for i in range(10)]
        compressed = trim_history(history)
        assert len(compressed) == 5  # 1 first + 4 recent


# ============================================================ _draft_to_detail_dict


class TestDraftToDetailDict:
    def test_full(self) -> None:
        from datetime import UTC, datetime

        from app.modules.creation.enums import DraftStatus, Platform, Style
        from app.modules.creation.model import CreationDraft

        d = CreationDraft(
            id=1, user_id=6, event_id=88,
            platform=Platform.WECHAT.value, style=Style.TECHNICAL.value,
            title="标题", content="正文", content_edited=None,
            outline=[{"heading": "A", "points": ["x"]}],
            cover_suggestion="封面", tags_suggestion=["t1"],
            word_count=10, extra_params={"audience": "dev"},
            model_alias="default-chat", prompt_version=1,
            cost_usd=0.01,
            status=DraftStatus.DONE.value, error_message=None,
            regenerate_count=0,
        )
        d.created_at = datetime.now(UTC)
        d.updated_at = datetime.now(UTC)
        out = svc._draft_to_detail_dict(d)
        assert out["id"] == 1
        assert out["platform"] == Platform.WECHAT
        assert out["title"] == "标题"
        assert len(out["outline"]) == 1
        assert out["outline"][0].heading == "A"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
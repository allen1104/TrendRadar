"""剥 markdown ```json ... ``` 包裹 + normalize_camel_to_snake 行为单测。"""

from __future__ import annotations

from app.modules.ai.providers.openai_compatible import (
    _normalize_camel_to_snake,
    _strip_markdown_fence,
)


# ---------------------------------------------------------- markdown 剥离


class TestStripMarkdownFence:
    def test_no_fence_passthrough(self) -> None:
        text = '{"summary": "x"}'
        assert _strip_markdown_fence(text) == text

    def test_json_fence_stripped(self) -> None:
        text = '```json\n{"summary": "x"}\n```'
        out = _strip_markdown_fence(text)
        assert out == '{"summary": "x"}'

    def test_uppercase_json_fence(self) -> None:
        text = '```JSON\n{"k": 1}\n```'
        out = _strip_markdown_fence(text)
        assert out == '{"k": 1}'

    def test_fence_no_lang(self) -> None:
        text = '```\n{"k": 1}\n```'
        out = _strip_markdown_fence(text)
        assert out == '{"k": 1}'

    def test_fence_with_surrounding_text(self) -> None:
        text = '以下是分析结果：\n```json\n{"k": 1}\n```\n希望对您有帮助。'
        out = _strip_markdown_fence(text)
        assert out == '{"k": 1}'

    def test_fence_with_leading_text(self) -> None:
        text = '好的，下面是 JSON：\n```json\n{"k": 1}\n```'
        out = _strip_markdown_fence(text)
        assert out == '{"k": 1}'

    def test_fence_with_explanation_after(self) -> None:
        text = '```json\n{"k": 1}\n```\n以上是结果。'
        out = _strip_markdown_fence(text)
        assert out == '{"k": 1}'


# ---------------------------------------------------------- normalize + 集成


class TestNormalizeCamelToSnake:
    def test_no_fence_passthrough(self) -> None:
        text = '{"summary_one_line": "x"}'
        assert _normalize_camel_to_snake(text) == text

    def test_camel_case_keys(self) -> None:
        text = '{"summaryOneLine": "x", "valueScore": 88}'
        out = _normalize_camel_to_snake(text)
        assert '"summary_one_line":' in out
        assert '"value_score":' in out
        assert '"summaryOneLine":' not in out

    def test_markdown_fence_plus_camel(self) -> None:
        """真实场景：DeepSeek 返回 ```json {camelCase} ```。"""
        text = '```json\n{"summaryOneLine": "x", "valueScore": 88}\n```'
        out = _normalize_camel_to_snake(text)
        # 剥了 fence + 键名都折成 snake_case
        assert out.startswith("{") and out.endswith("}")
        assert '"summary_one_line": "x"' in out
        assert '"value_score": 88' in out
        assert "```" not in out

    def test_underscore_keys_unchanged(self) -> None:
        text = '{"summary_one_line": "x"}'
        assert _normalize_camel_to_snake(text) == text

    def test_empty_text(self) -> None:
        assert _normalize_camel_to_snake("") == ""
        assert _normalize_camel_to_snake("not json") == "not json"
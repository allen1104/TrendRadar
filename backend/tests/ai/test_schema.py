"""ai schema 强约束单测。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.ai.schema import EventAnalysisResult


def _valid_payload() -> dict:
    return {
        "summary_one_line": "GPT-5 发布",
        "summary": "OpenAI 在 7 月 29 日发布 GPT-5...",
        "key_points": ["多模态推理提升 40%", "上下文扩展至 2M", "API 定价下降 30%"],
        "innovations": ["统一视觉-语言-代码的单一架构"],
        "audience": ["AI 应用开发者", "技术作者"],
        "categories": ["AI", "LLM"],
        "tags": [{"name": "OpenAI", "type": "COMPANY"}],
        "value_score": 88,
        "originality_score": 79,
        "trend_score": 91,
        "worth_article": True,
        "worth_article_why": "热度高且技术细节丰富",
        "worth_research": True,
        "worth_research_why": "统一架构的实现细节值得跟进",
    }


class TestEventAnalysisResult:
    def test_valid_payload_passes(self) -> None:
        out = EventAnalysisResult.model_validate(_valid_payload())
        assert out.value_score == 88
        assert out.worth_article is True

    def test_camelcase_alias_works(self) -> None:
        p = _valid_payload()
        camel = {
            "summaryOneLine": p["summary_one_line"],
            "summary": p["summary"],
            "keyPoints": p["key_points"],
            "innovations": p["innovations"],
            "audience": p["audience"],
            "categories": p["categories"],
            "tags": p["tags"],
            "valueScore": p["value_score"],
            "originalityScore": p["originality_score"],
            "trendScore": p["trend_score"],
            "worthArticle": p["worth_article"],
            "worthArticleWhy": p["worth_article_why"],
            "worthResearch": p["worth_research"],
            "worthResearchWhy": p["worth_research_why"],
        }
        out = EventAnalysisResult.model_validate(camel)
        assert out.value_score == 88

    def test_worth_article_reason_alias(self) -> None:
        """模型常返回 worth_article_reason 而非 worth_article_why，必须兼容。"""
        p = _valid_payload()
        del p["worth_article_why"]
        p["worth_article_reason"] = "reason via alias"
        out = EventAnalysisResult.model_validate(p)
        assert out.worth_article_why == "reason via alias"

    def test_worth_research_reason_alias(self) -> None:
        p = _valid_payload()
        del p["worth_research_why"]
        p["worth_research_reason"] = "research reason via alias"
        out = EventAnalysisResult.model_validate(p)
        assert out.worth_research_why == "research reason via alias"

    def test_key_points_too_few_raises(self) -> None:
        p = _valid_payload()
        p["key_points"] = ["only one"]
        with pytest.raises(ValidationError):
            EventAnalysisResult.model_validate(p)

    def test_key_points_too_many_raises(self) -> None:
        p = _valid_payload()
        p["key_points"] = [f"p{i}" for i in range(6)]
        with pytest.raises(ValidationError):
            EventAnalysisResult.model_validate(p)

    def test_scores_out_of_range_raise(self) -> None:
        for field in ("value_score", "originality_score", "trend_score"):
            p = _valid_payload()
            p[field] = 150  # > 100
            with pytest.raises(ValidationError):
                EventAnalysisResult.model_validate(p)

            p2 = _valid_payload()
            p2[field] = -5
            with pytest.raises(ValidationError):
                EventAnalysisResult.model_validate(p2)

    def test_summary_one_line_too_long_raises(self) -> None:
        p = _valid_payload()
        p["summary_one_line"] = "x" * 301
        with pytest.raises(ValidationError):
            EventAnalysisResult.model_validate(p)

    def test_categories_max_length(self) -> None:
        p = _valid_payload()
        p["categories"] = ["A", "B", "C", "D", "E"]  # 5 个 > 4 上限
        with pytest.raises(ValidationError):
            EventAnalysisResult.model_validate(p)

    def test_missing_required_field_raises(self) -> None:
        p = _valid_payload()
        del p["summary"]
        with pytest.raises(ValidationError):
            EventAnalysisResult.model_validate(p)

    def test_minimal_optional_fields(self) -> None:
        """innovations / categories / tags / *_why 都是可选。"""
        p = _valid_payload()
        p["innovations"] = []
        p["categories"] = []
        p["tags"] = []
        p["worth_article_why"] = None
        p["worth_research_why"] = None
        out = EventAnalysisResult.model_validate(p)
        assert out.innovations == []
        assert out.worth_article_why is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""pipeline 业务编排。"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.modules.pipeline.enums import ArticleStatus
from app.modules.pipeline.model import Article
from app.modules.pipeline.repository import ArticleRepository

log = structlog.get_logger()


class PipelineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ArticleRepository(session)

    async def clean_articles(self, article_ids: list[int]) -> tuple[int, int, int]:
        """清洗一批 article。

        返回 (cleaned_ok, discarded, failed)。
        """
        cleaned = 0
        discarded = 0
        failed = 0
        for aid in article_ids:
            art = await self.repo.get(aid)
            if art is None:
                failed += 1
                continue
            try:
                # 1. 正文抽取 + 去广告
                content = extract_content(art.raw_content)
                content = strip_ad_paragraphs(content)

                # 2. 时间归一化（已有 published_at 通常已是 UTC；raw_content 里若有更早时间优先用）
                published_at = normalize_published_at(art.published_at, fallback=utcnow())

                # 3. 作者
                author = take_author(art.author, content) or art.author

                # 4. 摘要（非 AI）
                summary = summarize(content)

                # 5. 关键词
                keywords = extract_keywords(content, art.lang)

                # 6. 丢弃判定
                is_discard, reason = should_discard(
                    title=art.title,
                    content=content,
                    lang=art.lang,
                    published_at=published_at,
                )
                if is_discard:
                    art.status = ArticleStatus.DISCARDED.value
                    art.fail_reason = reason
                    discarded += 1
                    await self.session.flush()
                    continue

                # 7. 落库
                art.content = content
                art.author = author
                art.published_at = published_at
                art.summary = summary
                art.keywords = keywords
                art.status = ArticleStatus.CLEANED.value
                cleaned += 1
                await self.session.flush()
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "pipeline.clean.failed",
                    article_id=aid,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
                art.status = ArticleStatus.FAILED.value
                art.fail_reason = f"{exc.__class__.__name__}: {exc}"[:500]
                failed += 1
                await self.session.flush()

        await self.session.commit()
        return cleaned, discarded, failed


def _utcnow_naive() -> datetime:
    """PG 用 naive UTC 存（列虽然 timezone=True 但我们保持 tz-aware 在应用层）。"""
    return datetime.now(timezone.utc)
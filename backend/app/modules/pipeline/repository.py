"""pipeline 仓库层。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pipeline.dedup import normalize_title, title_hash as _title_hash_fn, url_hash as _url_hash_fn
from app.modules.pipeline.enums import ArticleStatus
from app.modules.pipeline.model import Article, ArticleEmbedding


def url_hash(url: str) -> str:
    """代理：包一层以保持 repository.py 自洽。"""
    return _url_hash_fn(url)


def title_hash(title: str) -> str:
    return _title_hash_fn(title)


def normalize_title_for_dedup(title: str) -> str:
    return normalize_title(title)


class ArticleRepository:
    """article 表 CRUD。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(Article).where(Article.is_deleted.is_(False))

    async def get(self, article_id: int) -> Article | None:
        return await self.session.get(Article, article_id)

    async def get_by_url_hash(self, h: str) -> Article | None:
        stmt = self._base().where(Article.url_hash == h)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_title_hash(self, h: str) -> Article | None:
        stmt = self._base().where(Article.title_hash == h)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_many_from_raw(
        self,
        items: list[Any],
        *,
        source_id: int,
    ) -> tuple[int, list[int]]:
        """把 source 模块产出的 RawItem 列表批量 upsert 到 article 表。

        返回：(真正新插入的行数, 所有受影响 article id 列表)。
        失败：异常上抛，由调用方决定是否降级。
        """
        if not items:
            return 0, []

        now = datetime.now(timezone.utc)
        rows = []
        for it in items:
            # it.external_id, it.url, it.title, it.author, it.published_at,
            # it.lang, it.metrics, it.extra
            url = str(it.url)
            url_h = url_hash(url)
            title = (it.title or "").strip()
            title_h = title_hash(title)
            published_at = it.published_at or now
            rows.append(
                {
                    "source_id": source_id,
                    "external_id": it.external_id,
                    "url": url,
                    "url_hash": url_h,
                    "title": title,
                    "title_hash": title_h,
                    "raw_content": it.raw_content,
                    "author": it.author,
                    "lang": it.lang or "en",
                    "metrics": dict(it.metrics or {}),
                    "extra": dict(it.extra or {}),
                    "published_at": published_at,
                    "fetched_at": now,
                    "status": ArticleStatus.RAW.value,
                }
            )

        stmt = pg_insert(Article).values(rows)
        # 用 xmax=0 判定是否真插入（PG 技巧：xmax=0 表示全新行）
        from sqlalchemy import literal_column

        upsert = stmt.on_conflict_do_update(
            index_elements=[Article.url_hash],
            set_={
                "title": stmt.excluded.title,
                "raw_content": stmt.excluded.raw_content,
                "metrics": stmt.excluded.metrics,
                "extra": stmt.excluded.extra,
                "published_at": stmt.excluded.published_at,
                "fetched_at": stmt.excluded.fetched_at,
                "lang": stmt.excluded.lang,
                "is_deleted": False,
                "updated_at": func.now(),
            },
        ).returning(Article.id, (literal_column("xmax = 0")).label("inserted"))

        result = (await self.session.execute(upsert)).all()
        await self.session.commit()
        all_ids = [r[0] for r in result]
        new_count = sum(1 for r in result if r.inserted)
        return new_count, all_ids

    async def list_by_status(self, status: ArticleStatus, *, limit: int = 500) -> list[Article]:
        stmt = (
            self._base()
            .where(Article.status == status.value)
            .order_by(Article.published_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def list_by_ids(self, ids: list[int]) -> list[Article]:
        if not ids:
            return []
        stmt = self._base().where(Article.id.in_(ids))
        return list((await self.session.execute(stmt)).scalars())

    async def update_status(
        self,
        article_id: int,
        status: ArticleStatus,
        *,
        fail_reason: str | None = None,
    ) -> None:
        art = await self.get(article_id)
        if art is None:
            return
        art.status = status.value
        if fail_reason is not None:
            art.fail_reason = fail_reason
        await self.session.flush()


class ArticleEmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        article_id: int,
        *,
        model: str,
        embedding: list[float],
        dim: int,
    ) -> None:
        """用原生 SQL 写入向量列（pgvector 类型 ORM 不直接支持）。"""
        from sqlalchemy import text as sa_text

        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
        sql = sa_text(
            """
            INSERT INTO article_embedding (article_id, model, dim, embedding, created_at, updated_at, is_deleted)
            VALUES (:aid, :model, :dim, CAST(:vec AS vector), NOW(), NOW(), false)
            ON CONFLICT (article_id) DO UPDATE
            SET model = EXCLUDED.model,
                dim = EXCLUDED.dim,
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
            """
        )
        await self.session.execute(
            sql, {"aid": article_id, "model": model, "dim": dim, "vec": vec_str}
        )

    async def get_embedding(self, article_id: int) -> list[float] | None:
        from sqlalchemy import text as sa_text

        sql = sa_text(
            "SELECT embedding::text FROM article_embedding WHERE article_id = :aid AND is_deleted = false"
        )
        row = (await self.session.execute(sql, {"aid": article_id})).first()
        if row is None or row[0] is None:
            return None
        import json as _json

        text_val = row[0]
        # pgvector 返回 "[1.0,2.0,...]" 格式
        try:
            return _json.loads(text_val)
        except Exception:
            return [float(x) for x in text_val.strip("[]").split(",")]

    async def get(self, article_id: int) -> ArticleEmbedding | None:
        stmt = select(ArticleEmbedding).where(
            ArticleEmbedding.article_id == article_id,
            ArticleEmbedding.is_deleted.is_(False),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
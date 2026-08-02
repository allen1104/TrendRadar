"""creation 数据访问层。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.creation.model import CreationDraft


class CreationDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(CreationDraft).where(CreationDraft.is_deleted.is_(False))

    async def get_for_user(self, user_id: int, draft_id: int) -> CreationDraft | None:
        return (
            await self.session.execute(
                self._base().where(
                    CreationDraft.id == draft_id,
                    CreationDraft.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def get(self, draft_id: int) -> CreationDraft | None:
        return (
            await self.session.execute(
                self._base().where(CreationDraft.id == draft_id)
            )
        ).scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        *,
        event_id: int | None = None,
        platform: str | None = None,
        style: str | None = None,
        keyword: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[Sequence[CreationDraft], int]:
        """分页查询；返回 (rows, total)。"""
        from sqlalchemy import func, or_

        stmt = self._base().where(CreationDraft.user_id == user_id)
        if event_id is not None:
            stmt = stmt.where(CreationDraft.event_id == event_id)
        if platform is not None:
            stmt = stmt.where(CreationDraft.platform == platform)
        if style is not None:
            stmt = stmt.where(CreationDraft.style == style)
        if keyword:
            kw = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    CreationDraft.title.ilike(kw),
                    CreationDraft.content.ilike(kw),
                    CreationDraft.content_edited.ilike(kw),
                )
            )

        # count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)

        # sort 白名单：created_at / word_count / cost_usd
        sort_col = {
            "created_at": CreationDraft.created_at,
            "-created_at": CreationDraft.created_at.desc(),
            "word_count": CreationDraft.word_count,
            "-word_count": CreationDraft.word_count.desc(),
            "cost_usd": CreationDraft.cost_usd,
            "-cost_usd": CreationDraft.cost_usd.desc(),
        }.get(sort, CreationDraft.created_at.desc())
        offset = (page - 1) * size
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(sort_col, CreationDraft.id.desc()).offset(offset).limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def count_user_drafts(self, user_id: int) -> int:
        from sqlalchemy import func

        return int(
            (
                await self.session.execute(
                    select(func.count(CreationDraft.id)).where(
                        CreationDraft.user_id == user_id,
                        CreationDraft.is_deleted.is_(False),
                    )
                )
            ).scalar()
            or 0
        )

    async def create(self, **fields: Any) -> CreationDraft:
        d = CreationDraft(**fields)
        self.session.add(d)
        await self.session.flush()
        return d

    async def save(self, draft: CreationDraft) -> None:
        await self.session.flush()

    async def update_incremental(
        self,
        draft_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        content_edited: str | None = None,
        outline: list[dict[str, Any]] | None = None,
        cover_suggestion: str | None = None,
        tags_suggestion: list[str] | None = None,
        word_count: int | None = None,
        cost_usd: float | None = None,
        status: str | None = None,
        error_message: str | None = None,
        model_alias: str | None = None,
        prompt_version: int | None = None,
        latency_ms: int | None = None,
        regenerate_count: int | None = None,
        style: str | None = None,
    ) -> None:
        values: dict[str, Any] = {}
        if title is not None:
            values["title"] = title
        if content is not None:
            values["content"] = content
        if content_edited is not None:
            values["content_edited"] = content_edited
        if outline is not None:
            values["outline"] = outline
        if cover_suggestion is not None:
            values["cover_suggestion"] = cover_suggestion
        if tags_suggestion is not None:
            values["tags_suggestion"] = tags_suggestion
        if word_count is not None:
            values["word_count"] = word_count
        if cost_usd is not None:
            values["cost_usd"] = cost_usd
        if status is not None:
            values["status"] = status
        if error_message is not None:
            values["error_message"] = error_message
        if model_alias is not None:
            values["model_alias"] = model_alias
        if prompt_version is not None:
            values["prompt_version"] = prompt_version
        if latency_ms is not None:
            values["latency_ms"] = latency_ms
        if regenerate_count is not None:
            values["regenerate_count"] = regenerate_count
        if style is not None:
            values["style"] = style
        if not values:
            return
        await self.session.execute(
            update(CreationDraft)
            .where(CreationDraft.id == draft_id, CreationDraft.is_deleted.is_(False))
            .values(**values)
        )

    async def soft_delete(self, draft: CreationDraft) -> None:
        draft.is_deleted = True
        await self.session.flush()

    async def soft_delete_id(self, draft_id: int) -> int:
        result = await self.session.execute(
            update(CreationDraft)
            .where(CreationDraft.id == draft_id, CreationDraft.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
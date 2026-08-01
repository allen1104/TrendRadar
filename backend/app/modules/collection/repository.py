"""collection 数据访问层。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collection.model import CollectionFolder, CollectionItem


class CollectionFolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(CollectionFolder).where(CollectionFolder.is_deleted.is_(False))

    async def get(self, folder_id: int) -> CollectionFolder | None:
        return (
            await self.session.execute(
                self._base().where(CollectionFolder.id == folder_id)
            )
        ).scalar_one_or_none()

    async def get_for_user(self, user_id: int, folder_id: int) -> CollectionFolder | None:
        return (
            await self.session.execute(
                self._base().where(
                    CollectionFolder.id == folder_id,
                    CollectionFolder.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> Sequence[CollectionFolder]:
        return list(
            (
                await self.session.execute(
                    self._base()
                    .where(CollectionFolder.user_id == user_id)
                    .order_by(CollectionFolder.sort_order, CollectionFolder.id)
                )
            )
            .scalars()
            .all()
        )

    async def get_default(self, user_id: int) -> CollectionFolder | None:
        return (
            await self.session.execute(
                self._base().where(
                    CollectionFolder.user_id == user_id,
                    CollectionFolder.is_default.is_(True),
                )
            )
        ).scalar_one_or_none()

    async def get_by_name(self, user_id: int, name: str) -> CollectionFolder | None:
        return (
            await self.session.execute(
                self._base().where(
                    CollectionFolder.user_id == user_id,
                    CollectionFolder.name == name,
                )
            )
        ).scalar_one_or_none()

    async def count_for_user(self, user_id: int) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count(CollectionFolder.id)).where(
                        CollectionFolder.user_id == user_id,
                        CollectionFolder.is_deleted.is_(False),
                    )
                )
            ).scalar()
            or 0
        )

    async def create(self, **fields: Any) -> CollectionFolder:
        f = CollectionFolder(**fields)
        self.session.add(f)
        await self.session.flush()
        return f

    async def save(self, folder: CollectionFolder) -> None:
        await self.session.flush()

    async def soft_delete(self, folder: CollectionFolder) -> None:
        folder.is_deleted = True
        await self.session.flush()

    async def update_count(self, folder_id: int, delta: int) -> None:
        """原子 ±N 调整 item_count（不会变负数）。"""
        from sqlalchemy import update

        await self.session.execute(
            update(CollectionFolder)
            .where(CollectionFolder.id == folder_id, CollectionFolder.is_deleted.is_(False))
            .values(item_count=func.greatest(0, CollectionFolder.item_count + delta))
        )


class CollectionItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(CollectionItem).where(CollectionItem.is_deleted.is_(False))

    async def get(self, item_id: int) -> CollectionItem | None:
        return (
            await self.session.execute(
                self._base().where(CollectionItem.id == item_id)
            )
        ).scalar_one_or_none()

    async def get_for_user(self, user_id: int, item_id: int) -> CollectionItem | None:
        return (
            await self.session.execute(
                self._base().where(
                    CollectionItem.id == item_id,
                    CollectionItem.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def get_by_event(
        self, user_id: int, event_id: int
    ) -> CollectionItem | None:
        """同 user 收藏同 event 不重复（SPEC §业务规则）。"""
        return (
            await self.session.execute(
                self._base().where(
                    CollectionItem.user_id == user_id,
                    CollectionItem.event_id == event_id,
                )
            )
        ).scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        *,
        folder_id: int | None = None,
        read_status: str | None = None,
        user_tag: str | None = None,
        keyword: str | None = None,
        sort: str = "-createdAt",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[CollectionItem], int]:
        stmt = self._base().where(CollectionItem.user_id == user_id)
        if folder_id is not None:
            stmt = stmt.where(CollectionItem.folder_id == folder_id)
        if read_status is not None:
            stmt = stmt.where(CollectionItem.read_status == read_status)
        if user_tag is not None:
            # GIN 索引在迁移里建；这里直接 jsonb ?  即可
            stmt = stmt.where(CollectionItem.user_tags.op("?")(user_tag))
        if keyword is not None and keyword.strip():
            stmt = stmt.where(CollectionItem.note.ilike(f"%{keyword.strip()}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)

        # 排序
        desc = sort.startswith("-")
        col = sort[1:] if desc else sort
        sort_col = getattr(CollectionItem, col, CollectionItem.created_at)
        order = sort_col.desc() if desc else sort_col.asc()

        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(order, CollectionItem.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def list_collected_event_ids(
        self, user_id: int, event_ids: list[int]
    ) -> set[int]:
        """hotspot 集成：批量查 user 已收藏的 event_id 子集，无 N+1。"""
        if not event_ids:
            return set()
        rows = (
            await self.session.execute(
                select(CollectionItem.event_id).where(
                    CollectionItem.user_id == user_id,
                    CollectionItem.event_id.in_(event_ids),
                    CollectionItem.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        return set(rows)

    async def list_by_user_and_folder(
        self, user_id: int, folder_ids: list[int]
    ) -> list[CollectionItem]:
        """批量删 folder 时迁移 items 用。"""
        return list(
            (
                await self.session.execute(
                    self._base().where(
                        CollectionItem.user_id == user_id,
                        CollectionItem.folder_id.in_(folder_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

    async def count_for_user(self, user_id: int) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count(CollectionItem.id)).where(
                        CollectionItem.user_id == user_id,
                        CollectionItem.is_deleted.is_(False),
                    )
                )
            ).scalar()
            or 0
        )

    async def create(self, **fields: Any) -> CollectionItem:
        it = CollectionItem(**fields)
        self.session.add(it)
        await self.session.flush()
        return it

    async def save(self, item: CollectionItem) -> None:
        await self.session.flush()

    async def soft_delete(self, item: CollectionItem) -> None:
        item.is_deleted = True
        await self.session.flush()

    async def bulk_update_folder(self, item_ids: list[int], new_folder_id: int) -> int:
        from sqlalchemy import update

        if not item_ids:
            return 0
        result = await self.session.execute(
            update(CollectionItem)
            .where(
                CollectionItem.id.in_(item_ids),
                CollectionItem.is_deleted.is_(False),
            )
            .values(folder_id=new_folder_id)
        )
        return result.rowcount or 0

    async def bulk_soft_delete(self, item_ids: list[int]) -> int:
        from sqlalchemy import update

        if not item_ids:
            return 0
        result = await self.session.execute(
            update(CollectionItem)
            .where(
                CollectionItem.id.in_(item_ids),
                CollectionItem.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        return result.rowcount or 0

    async def bulk_set_read_status(
        self, item_ids: list[int], read_status: str
    ) -> int:
        from sqlalchemy import update

        if not item_ids:
            return 0
        from datetime import UTC
        from datetime import datetime as _dt

        now = _dt.now(UTC)
        values: dict[str, Any] = {"read_status": read_status}
        if read_status == "READ":
            values["read_at"] = now
        result = await self.session.execute(
            update(CollectionItem)
            .where(
                CollectionItem.id.in_(item_ids),
                CollectionItem.is_deleted.is_(False),
            )
            .values(**values)
        )
        return result.rowcount or 0

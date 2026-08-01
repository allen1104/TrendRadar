"""collection 业务编排层。

业务规则（doc/SPEC-collection.md §业务规则）：
- 同 user + 同 event 唯一（uk_item_user_event）
- 配额：≤50 收藏夹、≤10000 条目
- 默认收藏夹「我的收藏」用户首次 collect 时自动建，不可删
- 删收藏夹时其 items 迁到默认文件夹（原子调整 count）
- 跨用户访问 → 404（不暴露存在性）
- readStatus=READ 时自动写 readAt
- batch 操作 5 种 action
- hotspot 集成通过 list_collected_event_ids 批量查
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collection.enums import ReadStatus
from app.modules.collection.exceptions import (
    AlreadyCollectedError,
    CannotDeleteDefaultFolderError,
    EventNotFoundForCollectError,
    FolderNameExistsError,
    FolderNotFoundError,
    FolderQuotaExceededError,
    ItemNotFoundError,
    ItemQuotaExceededError,
)
from app.modules.collection.model import CollectionFolder, CollectionItem
from app.modules.collection.repository import (
    CollectionFolderRepository,
    CollectionItemRepository,
)
from app.modules.collection.schema import (
    BatchItemRequest,
    BatchItemResponse,
    CategoryCount,
    EventBrief,
    FolderCreateRequest,
    FolderResponse,
    FolderUpdateRequest,
    ItemCreateRequest,
    ItemResponse,
    ItemUpdateRequest,
    StatsResponse,
)

log = structlog.get_logger()

FOLDER_QUOTA = 50
ITEM_QUOTA = 10000
DEFAULT_FOLDER_NAME = "我的收藏"


def _folder_to_response(f: CollectionFolder) -> FolderResponse:
    return FolderResponse(
        id=f.id,
        name=f.name,
        description=f.description,
        color=f.color,
        sort_order=f.sort_order,
        is_default=f.is_default,
        item_count=f.item_count,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _item_to_response(it: CollectionItem, event_brief: EventBrief) -> ItemResponse:
    return ItemResponse(
        id=it.id,
        folder_id=it.folder_id,
        folder_name="",  # 由 service 层在 list/get 时 join folder 填
        note=it.note,
        user_tags=it.user_tags or [],
        read_status=ReadStatus(it.read_status),
        read_at=it.read_at,
        created_at=it.created_at,
        updated_at=it.updated_at,
        event=event_brief,
    )


class CollectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.folder_repo = CollectionFolderRepository(session)
        self.item_repo = CollectionItemRepository(session)

    # ============================================================ 收藏夹

    async def list_folders(self, user_id: int) -> list[FolderResponse]:
        rows = await self.folder_repo.list_for_user(user_id)
        return [_folder_to_response(r) for r in rows]

    async def create_folder(
        self, user_id: int, payload: FolderCreateRequest, actor: Any = None
    ) -> FolderResponse:
        # 配额
        if await self.folder_repo.count_for_user(user_id) >= FOLDER_QUOTA:
            raise FolderQuotaExceededError(
                f"收藏夹数量已达 {FOLDER_QUOTA} 个上限", extra={"quota": FOLDER_QUOTA}
            )
        # 唯一
        if await self.folder_repo.get_by_name(user_id, payload.name):
            raise FolderNameExistsError

        folder = await self.folder_repo.create(
            user_id=user_id,
            name=payload.name,
            description=payload.description,
            color=payload.color,
            sort_order=0,
            is_default=False,
            item_count=0,
        )
        await self.session.commit()
        # 审计（try/except 隔离，写失败不影响主流程）
        await self._audit(
            action="COLLECTION_FOLDER_CREATE",
            target_id=folder.id,
            after={"name": folder.name, "color": folder.color},
            actor=actor,
        )
        return _folder_to_response(folder)

    async def update_folder(
        self,
        user_id: int,
        folder_id: int,
        payload: FolderUpdateRequest,
        actor: Any = None,
    ) -> FolderResponse:
        folder = await self.folder_repo.get_for_user(user_id, folder_id)
        if folder is None:
            raise FolderNotFoundError

        if folder.is_default and (payload.name or payload.color is not None or payload.sort_order is not None):
            raise CannotDeleteDefaultFolderError("默认收藏夹不能改名 / 改色 / 改排序")

        before: dict = {}
        after: dict = {}
        if payload.name is not None and payload.name != folder.name:
            if await self.folder_repo.get_by_name(user_id, payload.name):
                raise FolderNameExistsError
            before["name"] = folder.name
            after["name"] = payload.name
            folder.name = payload.name
        if payload.description is not None and payload.description != folder.description:
            before["description"] = folder.description
            after["description"] = payload.description
            folder.description = payload.description
        if payload.color is not None and payload.color != folder.color:
            before["color"] = folder.color
            after["color"] = payload.color
            folder.color = payload.color
        if payload.sort_order is not None and payload.sort_order != folder.sort_order:
            before["sort_order"] = folder.sort_order
            after["sort_order"] = payload.sort_order
            folder.sort_order = payload.sort_order

        if after:
            await self.folder_repo.save(folder)
            await self.session.commit()
            await self._audit(
                action="COLLECTION_FOLDER_UPDATE",
                target_id=folder.id,
                before=before,
                after=after,
                actor=actor,
            )
        return _folder_to_response(folder)

    async def delete_folder(
        self, user_id: int, folder_id: int, actor: Any = None
    ) -> None:
        folder = await self.folder_repo.get_for_user(user_id, folder_id)
        if folder is None:
            raise FolderNotFoundError
        if folder.is_default:
            raise CannotDeleteDefaultFolderError

        # 1. items 迁到默认文件夹
        default = await self.ensure_default_folder(user_id)
        if default.id != folder.id:
            items = await self.item_repo.list_by_user_and_folder(
                user_id, [folder.id]
            )
            n = len(items)
            await self.item_repo.bulk_update_folder(
                [it.id for it in items], default.id
            )
            # 原子调整 count
            await self.folder_repo.update_count(folder.id, -n)
            await self.folder_repo.update_count(default.id, n)

        # 2. 软删除 folder
        await self.folder_repo.soft_delete(folder)
        await self.session.commit()

        await self._audit(
            action="COLLECTION_FOLDER_DELETE",
            target_id=folder.id,
            before={"name": folder.name, "item_count": folder.item_count},
            actor=actor,
        )

    async def ensure_default_folder(self, user_id: int) -> CollectionFolder:
        """首次 collect 时调用，找不到默认就建。"""
        default = await self.folder_repo.get_default(user_id)
        if default is not None:
            return default
        # 唯一约束保护：原子 create_or_get
        existing = await self.folder_repo.get_by_name(user_id, DEFAULT_FOLDER_NAME)
        if existing is not None and existing.is_default:
            return existing
        try:
            folder = await self.folder_repo.create(
                user_id=user_id,
                name=DEFAULT_FOLDER_NAME,
                description="默认收藏夹",
                color="#3b82f6",
                sort_order=0,
                is_default=True,
                item_count=0,
            )
            await self.session.commit()
            return folder
        except Exception:
            await self.session.rollback()
            existing = await self.folder_repo.get_by_name(user_id, DEFAULT_FOLDER_NAME)
            if existing is not None:
                return existing
            raise

    # ============================================================ 条目

    async def list_items(
        self,
        user_id: int,
        *,
        folder_id: int | None,
        read_status: str | None,
        user_tag: str | None,
        keyword: str | None,
        sort: str,
        page: int,
        size: int,
    ) -> tuple[list[ItemResponse], int]:
        rows, total = await self.item_repo.list_for_user(
            user_id,
            folder_id=folder_id,
            read_status=read_status,
            user_tag=user_tag,
            keyword=keyword,
            sort=sort,
            offset=(page - 1) * size,
            limit=size,
        )
        if not rows:
            return [], total
        # 关联 folder + event 简要
        from sqlalchemy import select as _select

        from app.modules.collection.model import CollectionFolder as _F
        from app.modules.pipeline.model import Event as _E

        folder_ids = {it.folder_id for it in rows}
        event_ids = [it.event_id for it in rows]
        folders = {
            f.id: f
            for f in (
                await self.session.execute(
                    _select(_F).where(
                        _F.id.in_(folder_ids), _F.is_deleted.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        }
        events = {
            ev.id: ev
            for ev in (
                await self.session.execute(
                    _select(_E).where(
                        _E.id.in_(event_ids), _E.is_deleted.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        }
        result: list[ItemResponse] = []
        for it in rows:
            ev = events.get(it.event_id)
            if ev is None:
                continue
            brief = EventBrief(
                id=ev.id,
                title=ev.title,
                summary_one_line=ev.summary_one_line,
                categories=ev.categories or [],
                recommend_index=float(ev.recommend_index or 0),
                source_count=ev.source_count,
                last_seen_at=ev.last_seen_at,
            )
            r = _item_to_response(it, brief)
            r.folder_name = folders[it.folder_id].name if it.folder_id in folders else ""
            result.append(r)
        return result, total

    async def get_item(
        self, user_id: int, item_id: int
    ) -> ItemResponse:
        it = await self.item_repo.get_for_user(user_id, item_id)
        if it is None:
            raise ItemNotFoundError
        return await self._hydrate_item(it)

    async def create_item(
        self,
        user_id: int,
        payload: ItemCreateRequest,
        actor: Any = None,
    ) -> ItemResponse:
        # 1. event 存在
        from sqlalchemy import select as _select

        from app.modules.pipeline.model import Event as _E

        ev = (
            await self.session.execute(
                _select(_E).where(
                    _E.id == payload.event_id, _E.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if ev is None:
            raise EventNotFoundForCollectError

        # 2. 配额
        if await self.item_repo.count_for_user(user_id) >= ITEM_QUOTA:
            raise ItemQuotaExceededError(
                f"收藏条目已达 {ITEM_QUOTA} 个上限", extra={"quota": ITEM_QUOTA}
            )

        # 3. 唯一
        existing = await self.item_repo.get_by_event(user_id, payload.event_id)
        if existing is not None:
            raise AlreadyCollectedError(
                extra={"existingItemId": existing.id}
            )

        # 4. 选 folder
        folder = None
        if payload.folder_id is not None:
            folder = await self.folder_repo.get_for_user(user_id, payload.folder_id)
            if folder is None:
                raise FolderNotFoundError
        else:
            folder = await self.ensure_default_folder(user_id)

        # 5. 写
        item = await self.item_repo.create(
            user_id=user_id,
            folder_id=folder.id,
            event_id=payload.event_id,
            note=payload.note,
            user_tags=payload.user_tags,
            read_status=payload.read_status.value,
            read_at=datetime.now(UTC) if payload.read_status == ReadStatus.READ else None,
        )
        # 6. 原子 +1 count
        await self.folder_repo.update_count(folder.id, +1)
        await self.session.commit()

        await self._audit(
            action="COLLECTION_ITEM_CREATE",
            target_id=item.id,
            after={
                "event_id": item.event_id,
                "folder_id": item.folder_id,
                "read_status": item.read_status,
            },
            actor=actor,
        )
        return await self._hydrate_item(item)

    async def update_item(
        self,
        user_id: int,
        item_id: int,
        payload: ItemUpdateRequest,
        actor: Any = None,
    ) -> ItemResponse:
        item = await self.item_repo.get_for_user(user_id, item_id)
        if item is None:
            raise ItemNotFoundError

        before: dict = {}
        after: dict = {}
        # folder 移动
        if payload.folder_id is not None and payload.folder_id != item.folder_id:
            new_folder = await self.folder_repo.get_for_user(user_id, payload.folder_id)
            if new_folder is None:
                raise FolderNotFoundError
            before["folder_id"] = item.folder_id
            after["folder_id"] = new_folder.id
            old_folder_id = item.folder_id
            item.folder_id = new_folder.id
            await self.folder_repo.update_count(old_folder_id, -1)
            await self.folder_repo.update_count(new_folder.id, +1)
        if payload.note is not None and payload.note != item.note:
            before["note"] = item.note
            after["note"] = payload.note
            item.note = payload.note
        if payload.user_tags is not None and payload.user_tags != item.user_tags:
            before["user_tags"] = item.user_tags
            after["user_tags"] = payload.user_tags
            item.user_tags = payload.user_tags
        if payload.read_status is not None and payload.read_status.value != item.read_status:
            before["read_status"] = item.read_status
            after["read_status"] = payload.read_status.value
            item.read_status = payload.read_status.value
            if payload.read_status == ReadStatus.READ:
                item.read_at = datetime.now(UTC)
            elif payload.read_status == ReadStatus.UNREAD:
                item.read_at = None

        if after:
            await self.item_repo.save(item)
            await self.session.commit()
            await self._audit(
                action="COLLECTION_ITEM_UPDATE",
                target_id=item.id,
                before=before,
                after=after,
                actor=actor,
            )
        return await self._hydrate_item(item)

    async def delete_item(
        self, user_id: int, item_id: int, actor: Any = None
    ) -> None:
        item = await self.item_repo.get_for_user(user_id, item_id)
        if item is None:
            raise ItemNotFoundError
        folder_id = item.folder_id
        # 软删除 + count -1
        await self.item_repo.soft_delete(item)
        await self.folder_repo.update_count(folder_id, -1)
        await self.session.commit()
        await self._audit(
            action="COLLECTION_ITEM_DELETE",
            target_id=item_id,
            before={"folder_id": folder_id, "event_id": item.event_id},
            actor=actor,
        )

    async def batch_items(
        self, user_id: int, payload: BatchItemRequest, actor: Any = None
    ) -> BatchItemResponse:
        from sqlalchemy import select as _s

        affected = 0
        if payload.action == "MOVE":
            if payload.target_folder_id is None:
                from app.modules.collection.exceptions import InvalidBatchActionError

                raise InvalidBatchActionError("MOVE 必须传 target_folder_id")
            new_folder = await self.folder_repo.get_for_user(user_id, payload.target_folder_id)
            if new_folder is None:
                raise FolderNotFoundError
            # 统计每 folder 增减
            rows = await self.item_repo.list_by_user_and_folder(user_id, payload.item_ids) if False else []

            rows = list(
                (
                    await self.session.execute(
                        _s(CollectionItem).where(
                            CollectionItem.id.in_(payload.item_ids),
                            CollectionItem.user_id == user_id,
                            CollectionItem.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            deltas: dict[int, int] = {}
            for it in rows:
                deltas[it.folder_id] = deltas.get(it.folder_id, 0) - 1
                deltas[new_folder.id] = deltas.get(new_folder.id, 0) + 1
            affected = await self.item_repo.bulk_update_folder(payload.item_ids, new_folder.id)
            for fid, d in deltas.items():
                if d:
                    await self.folder_repo.update_count(fid, d)
            await self.session.commit()
        elif payload.action == "DELETE":
            rows = list(
                (
                    await self.session.execute(
                        _s(CollectionItem).where(
                            CollectionItem.id.in_(payload.item_ids),
                            CollectionItem.user_id == user_id,
                            CollectionItem.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            deltas: dict[int, int] = {}
            for it in rows:
                deltas[it.folder_id] = deltas.get(it.folder_id, 0) - 1
            affected = await self.item_repo.bulk_soft_delete(payload.item_ids)
            for fid, d in deltas.items():
                if d:
                    await self.folder_repo.update_count(fid, d)
            await self.session.commit()
        elif payload.action == "MARK_READ":
            affected = await self.item_repo.bulk_set_read_status(
                payload.item_ids, ReadStatus.READ.value
            )
            await self.session.commit()
        elif payload.action in ("ADD_TAG", "REMOVE_TAG"):
            from app.modules.collection.exceptions import InvalidBatchActionError

            if not payload.tag:
                raise InvalidBatchActionError(f"{payload.action} 必须传 tag")
            rows = list(
                (
                    await self.session.execute(
                        _s(CollectionItem).where(
                            CollectionItem.id.in_(payload.item_ids),
                            CollectionItem.user_id == user_id,
                            CollectionItem.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for it in rows:
                tags = list(it.user_tags or [])
                if payload.action == "ADD_TAG":
                    if payload.tag not in tags:
                        tags.append(payload.tag)
                        tags = tags[:10]
                else:  # REMOVE_TAG
                    if payload.tag in tags:
                        tags.remove(payload.tag)
                it.user_tags = tags
            await self.session.commit()
            affected = len(rows)
        else:
            from app.modules.collection.exceptions import InvalidBatchActionError

            raise InvalidBatchActionError(f"不支持的 action: {payload.action}")

        await self._audit(
            action="COLLECTION_ITEM_UPDATE",
            target_id=None,
            after={"batch_action": payload.action, "affected": affected, "count": len(payload.item_ids)},
            actor=actor,
        )
        return BatchItemResponse(affected_count=affected)

    # ============================================================ 集成

    async def list_collected_event_ids(
        self, user_id: int, event_ids: list[int]
    ) -> set[int]:
        return await self.item_repo.list_collected_event_ids(user_id, event_ids)

    async def get_stats(self, user_id: int) -> StatsResponse:
        from sqlalchemy import func as _f
        from sqlalchemy import select as _s

        from app.modules.collection.model import CollectionItem as _I
        from app.modules.pipeline.model import Event as _E

        # 4 个 read_status 计数
        rows = (
            await self.session.execute(
                _s(_I.read_status, _f.count(_I.id))
                .where(_I.user_id == user_id, _I.is_deleted.is_(False))
                .group_by(_I.read_status)
            )
        ).all()
        status_count: dict[str, int] = {r[0]: int(r[1]) for r in rows}
        total = sum(status_count.values())
        unread = status_count.get(ReadStatus.UNREAD.value, 0)
        later = status_count.get(ReadStatus.LATER.value, 0)
        read = status_count.get(ReadStatus.READ.value, 0)

        folder_count = await self.folder_repo.count_for_user(user_id)

        # byCategory：从 event.categories JSONB 聚合
        cat_rows = (
            await self.session.execute(
                _s(_E.categories, _f.count(_I.id))
                .join(_I, _I.event_id == _E.id)
                .where(
                    _I.user_id == user_id,
                    _I.is_deleted.is_(False),
                    _E.is_deleted.is_(False),
                )
                .group_by(_E.categories)
            )
        ).all()
        cat_agg: dict[str, int] = {}
        for cats, c in cat_rows:
            for cat in (cats or []):
                cat_agg[cat] = cat_agg.get(cat, 0) + int(c)
        by_category = [
            CategoryCount(category=k, count=v) for k, v in sorted(cat_agg.items(), key=lambda x: -x[1])[:10]
        ]

        # recentMonths：按 created_at 月份聚合
        month_expr = _f.to_char(_I.created_at, "YYYY-MM")
        month_rows = (
            await self.session.execute(
                _s(month_expr.label("m"), _f.count(_I.id))
                .where(_I.user_id == user_id, _I.is_deleted.is_(False))
                .group_by("m")
                .order_by(_f.desc("m"))
                .limit(6)
            )
        ).all()
        recent_months = [MonthCount(month=r[0], count=int(r[1])) for r in month_rows]

        return StatsResponse(
            total_items=total,
            unread_count=unread,
            later_count=later,
            read_count=read,
            folder_count=folder_count,
            by_category=by_category,
            recent_months=recent_months,
        )

    # ============================================================ 内部

    async def _hydrate_item(self, it: CollectionItem) -> ItemResponse:
        from sqlalchemy import select as _s

        from app.modules.collection.model import CollectionFolder as _F
        from app.modules.pipeline.model import Event as _E

        folder = (
            await self.session.execute(
                _s(_F).where(_F.id == it.folder_id, _F.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        ev = (
            await self.session.execute(
                _s(_E).where(_E.id == it.event_id, _E.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if ev is None or folder is None:
            raise ItemNotFoundError
        brief = EventBrief(
            id=ev.id,
            title=ev.title,
            summary_one_line=ev.summary_one_line,
            categories=ev.categories or [],
            recommend_index=float(ev.recommend_index or 0),
            source_count=ev.source_count,
            last_seen_at=ev.last_seen_at,
        )
        r = _item_to_response(it, brief)
        r.folder_name = folder.name
        return r

    async def _audit(
        self,
        *,
        action: str,
        target_id: int | None,
        before: dict | None = None,
        after: dict | None = None,
        actor: Any = None,
    ) -> None:
        """写 audit_log（try/except 隔离，避免污染主流程）。"""
        try:
            from app.modules.admin.enums import TargetType as _TT
            from app.modules.admin.service import AuditService

            target_type = (
                _TT.COLLECTION_FOLDER
                if action.startswith("COLLECTION_FOLDER")
                else _TT.COLLECTION_ITEM
            )
            await AuditService(self.session).record(
                action=action,
                target_type=target_type,
                target_id=target_id,
                before=before,
                after=after,
                actor=actor,
            )
        except Exception as exc:
            log.warning(
                "collection.audit.write_failed", action=action, error=str(exc)
            )
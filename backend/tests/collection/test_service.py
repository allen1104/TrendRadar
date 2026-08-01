"""collection 业务规则单元测试（mock repo，避免连真实 DB）。

覆盖 SPEC §业务规则：
- 配额（folder 50 / item 10000）
- 默认收藏夹自动建 / 不可删 / 不可改名
- 跨用户 404 隔离
- 同 event 不重复
- 删 folder 迁 items + 原子 count
- readStatus=READ 自动写 readAt
- batch 5 种 action
- list_collected_event_ids 批量查
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
from app.modules.collection.schema import (
    BatchItemRequest,
    FolderCreateRequest,
    FolderUpdateRequest,
    ItemCreateRequest,
    ItemUpdateRequest,
)
from app.modules.collection.service import (
    FOLDER_QUOTA,
    ITEM_QUOTA,
    CollectionService,
)
from app.modules.pipeline.model import Event


def _folder(**kw) -> CollectionFolder:
    """构造一个 mock folder 对象。"""
    now = datetime(2026, 7, 30, tzinfo=UTC)
    defaults = dict(
        id=1, user_id=6, name="我的收藏", description="default",
        color="#3b82f6", sort_order=0, is_default=True, item_count=0,
        created_at=now, updated_at=now, is_deleted=False,
    )
    defaults.update(kw)
    return CollectionFolder(**defaults)


def _item(**kw) -> CollectionItem:
    now = datetime(2026, 7, 30, tzinfo=UTC)
    defaults = dict(
        id=10, user_id=6, folder_id=1, event_id=9, note=None,
        user_tags=[], read_status="UNREAD", read_at=None,
        created_at=now, updated_at=now, is_deleted=False,
    )
    defaults.update(kw)
    return CollectionItem(**defaults)


def _event(**kw) -> Event:
    """构造一个真实的 Event 对象（避免 MagicMock 触发 Pydantic datetime 校验失败）。"""
    now = datetime(2026, 7, 30, tzinfo=UTC)
    defaults = dict(
        id=9,  # TimestampMixin 继承的 id 字段需要显式给
        title="Test", summary_one_line="x",
        region="GLOBAL", categories=["AI"],
        source_count=3, article_count=5,
        heat_score=70.0, recommend_index=80.0,
        first_seen_at=now, last_seen_at=now,
        status="ANALYZED", is_pinned=False, is_hidden=False,
        is_manually_edited=False, manual_locked_fields=[],
    )
    defaults.update(kw)
    return Event(**defaults)


def _hyd_result(item: MagicMock | None = None) -> MagicMock:
    """构造 _hydrate_item 两次 execute 的 result mocks。"""
    f = MagicMock(scalar_one_or_none=MagicMock(return_value=_folder()))
    e = MagicMock(scalar_one_or_none=MagicMock(return_value=_event()))
    return f, e


# ============================================================ folders


class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_quota_exceeded_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.count_for_user = AsyncMock(return_value=FOLDER_QUOTA)
        with pytest.raises(FolderQuotaExceededError):
            await svc.create_folder(6, FolderCreateRequest(name="x"), actor=None)

    @pytest.mark.asyncio
    async def test_name_exists_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.count_for_user = AsyncMock(return_value=0)
        svc.folder_repo.get_by_name = AsyncMock(return_value=_folder())
        with pytest.raises(FolderNameExistsError):
            await svc.create_folder(6, FolderCreateRequest(name="dup"), actor=None)

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.count_for_user = AsyncMock(return_value=5)
        svc.folder_repo.get_by_name = AsyncMock(return_value=None)
        created = _folder(id=99, name="new", is_default=False, user_id=6)
        svc.folder_repo.create = AsyncMock(return_value=created)
        with patch("app.modules.admin.service.AuditService") as MockAudit:
            MockAudit.return_value.record = AsyncMock()
            resp = await svc.create_folder(6, FolderCreateRequest(name="new"), actor=None)
        assert resp.id == 99
        MockAudit.return_value.record.assert_called_once()
        assert MockAudit.return_value.record.call_args.kwargs["action"] == "COLLECTION_FOLDER_CREATE"


class TestUpdateFolder:
    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=None)
        with pytest.raises(FolderNotFoundError):
            await svc.update_folder(6, 99, MagicMock(), actor=None)

    @pytest.mark.asyncio
    async def test_default_rename_blocked(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=_folder(is_default=True))
        with pytest.raises(CannotDeleteDefaultFolderError):
            await svc.update_folder(6, 1, MagicMock(name="x"), actor=None)


class TestDeleteFolder:
    @pytest.mark.asyncio
    async def test_default_blocked(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=_folder(is_default=True))
        with pytest.raises(CannotDeleteDefaultFolderError):
            await svc.delete_folder(6, 1, actor=None)

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=None)
        with pytest.raises(FolderNotFoundError):
            await svc.delete_folder(6, 99, actor=None)

    @pytest.mark.asyncio
    async def test_moves_items_to_default_and_corrects_count(self) -> None:
        items = [_item(id=10, folder_id=2), _item(id=11, folder_id=2)]
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(
            side_effect=[
                _folder(id=2, name="to_delete", is_default=False),
                _folder(id=1, name="我的收藏", is_default=True),
            ]
        )
        svc.folder_repo.get_default = AsyncMock(return_value=_folder(id=1, is_default=True))
        svc.item_repo.list_by_user_and_folder = AsyncMock(return_value=items)
        svc.item_repo.bulk_update_folder = AsyncMock(return_value=2)
        svc.folder_repo.update_count = AsyncMock()
        svc.folder_repo.soft_delete = AsyncMock()
        with patch("app.modules.admin.service.AuditService"):
            await svc.delete_folder(6, 2, actor=None)
        svc.item_repo.bulk_update_folder.assert_called_once_with([10, 11], 1)
        calls = [c.args for c in svc.folder_repo.update_count.call_args_list]
        assert (2, -2) in calls
        assert (1, 2) in calls


# ============================================================ items


class TestCreateItem:
    @pytest.mark.asyncio
    async def test_event_not_found_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        result_mock = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        svc.session.execute = AsyncMock(return_value=result_mock)
        with pytest.raises(EventNotFoundForCollectError):
            await svc.create_item(6, ItemCreateRequest(event_id=999), actor=None)

    @pytest.mark.asyncio
    async def test_quota_exceeded_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        ev = _event()
        result_mock = MagicMock(scalar_one_or_none=MagicMock(return_value=ev))
        svc.session.execute = AsyncMock(return_value=result_mock)
        svc.item_repo.count_for_user = AsyncMock(return_value=ITEM_QUOTA)
        with pytest.raises(ItemQuotaExceededError):
            await svc.create_item(6, ItemCreateRequest(event_id=9), actor=None)

    @pytest.mark.asyncio
    async def test_already_collected_raises_with_id(self) -> None:
        svc = CollectionService(AsyncMock())
        ev = _event()
        result_mock = MagicMock(scalar_one_or_none=MagicMock(return_value=ev))
        svc.session.execute = AsyncMock(return_value=result_mock)
        svc.item_repo.count_for_user = AsyncMock(return_value=0)
        existing = _item(id=99, event_id=9)
        svc.item_repo.get_by_event = AsyncMock(return_value=existing)
        with pytest.raises(AlreadyCollectedError) as exc_info:
            await svc.create_item(6, ItemCreateRequest(event_id=9), actor=None)
        assert exc_info.value.extra.get("existingItemId") == 99

    @pytest.mark.asyncio
    async def test_success_creates_default_folder_if_missing(self) -> None:
        svc = CollectionService(AsyncMock())
        ev = _event()
        # execute 顺序：1) event 查询, 2) _hydrate_item: folder, 3) _hydrate_item: event
        r_ev = MagicMock(scalar_one_or_none=MagicMock(return_value=ev))
        r_folder = MagicMock(scalar_one_or_none=MagicMock(return_value=_folder(id=1, is_default=True)))
        r_ev2 = MagicMock(scalar_one_or_none=MagicMock(return_value=ev))
        svc.session.execute = AsyncMock(side_effect=[r_ev, r_folder, r_ev2])
        svc.item_repo.count_for_user = AsyncMock(return_value=0)
        svc.item_repo.get_by_event = AsyncMock(return_value=None)
        svc.folder_repo.get_default = AsyncMock(return_value=None)
        svc.folder_repo.get_by_name = AsyncMock(return_value=None)
        default_folder = _folder(id=1, is_default=True)
        svc.folder_repo.create = AsyncMock(return_value=default_folder)
        new_item = _item(id=100, folder_id=1, event_id=9)
        svc.item_repo.create = AsyncMock(return_value=new_item)
        svc.folder_repo.update_count = AsyncMock()
        with patch("app.modules.admin.service.AuditService"):
            item = await svc.create_item(6, ItemCreateRequest(event_id=9), actor=None)
        assert item.id == 100
        svc.folder_repo.update_count.assert_called_once_with(1, 1)


class TestUpdateItem:
    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=None)
        with pytest.raises(ItemNotFoundError):
            await svc.update_item(6, 99, MagicMock(), actor=None)

    @pytest.mark.asyncio
    async def test_no_change_skips_save(self) -> None:
        """payload 与当前一致 → 不 save 不 audit。"""
        item = _item(id=10, user_tags=["x"])
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=item)
        svc.item_repo.save = AsyncMock()
        r_folder, r_ev = _hyd_result()
        svc.session.execute = AsyncMock(side_effect=[r_folder, r_ev])
        with patch("app.modules.admin.service.AuditService") as MockAudit:
            await svc.update_item(6, 10, ItemUpdateRequest(user_tags=["x"]), actor=None)
        svc.item_repo.save.assert_not_called()
        MockAudit.return_value.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_status_unread_clears_read_at(self) -> None:
        item = _item(id=10, read_status="READ", read_at=datetime(2026, 7, 30, tzinfo=UTC))
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=item)
        svc.item_repo.save = AsyncMock()
        r_folder, r_ev = _hyd_result()
        svc.session.execute = AsyncMock(side_effect=[r_folder, r_ev])
        with patch("app.modules.admin.service.AuditService"):
            await svc.update_item(6, 10, ItemUpdateRequest(read_status=ReadStatus.UNREAD), actor=None)
        assert item.read_status == "UNREAD"
        assert item.read_at is None

    @pytest.mark.asyncio
    async def test_read_status_read_auto_sets_read_at(self) -> None:
        item = _item(id=10, read_status="UNREAD", read_at=None)
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=item)
        svc.item_repo.save = AsyncMock()
        r_folder, r_ev = _hyd_result()
        svc.session.execute = AsyncMock(side_effect=[r_folder, r_ev])
        with patch("app.modules.admin.service.AuditService"):
            await svc.update_item(
                6, 10, ItemUpdateRequest(read_status=ReadStatus.READ), actor=None
            )
        assert item.read_status == "READ"
        assert item.read_at is not None

    @pytest.mark.asyncio
    async def test_folder_move_adjusts_two_counts(self) -> None:
        item = _item(id=10, folder_id=2, event_id=9)
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=item)
        svc.folder_repo.get_for_user = AsyncMock(return_value=_folder(id=5, is_default=False))
        svc.folder_repo.update_count = AsyncMock()
        svc.item_repo.save = AsyncMock()
        r_folder, r_ev = _hyd_result()
        svc.session.execute = AsyncMock(side_effect=[r_folder, r_ev])
        with patch("app.modules.admin.service.AuditService"):
            await svc.update_item(
                6, 10, ItemUpdateRequest(folder_id=5), actor=None
        )
        calls = [c.args for c in svc.folder_repo.update_count.call_args_list]
        assert (2, -1) in calls
        assert (5, 1) in calls


class TestDeleteItem:
    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=None)
        with pytest.raises(ItemNotFoundError):
            await svc.delete_item(6, 99, actor=None)

    @pytest.mark.asyncio
    async def test_success_soft_delete_and_count_minus_1(self) -> None:
        item = _item(id=10, folder_id=2)
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=item)
        async def _set_deleted(it):
            it.is_deleted = True
        svc.item_repo.soft_delete = AsyncMock(side_effect=_set_deleted)
        svc.folder_repo.update_count = AsyncMock()
        with patch("app.modules.admin.service.AuditService"):
            await svc.delete_item(6, 10, actor=None)
        assert item.is_deleted is True
        svc.folder_repo.update_count.assert_called_once_with(2, -1)


# ============================================================ list_collected_event_ids


class TestListCollectedEventIds:
    @pytest.mark.asyncio
    async def test_returns_set(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.item_repo.list_collected_event_ids = AsyncMock(return_value={1, 5, 9})
        out = await svc.list_collected_event_ids(6, [1, 2, 5, 9])
        assert out == {1, 5, 9}

    @pytest.mark.asyncio
    async def test_empty_event_ids(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.item_repo.list_collected_event_ids = AsyncMock(return_value=set())
        out = await svc.list_collected_event_ids(6, [])
        assert out == set()


# ============================================================ batch


class TestBatchMove:
    @pytest.mark.asyncio
    async def test_move_adjusts_counts(self) -> None:
        items = [_item(id=10, folder_id=2), _item(id=11, folder_id=2), _item(id=12, folder_id=2)]
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=_folder(id=5, is_default=False))
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
        svc.session.execute = AsyncMock(return_value=result_mock)
        svc.item_repo.bulk_update_folder = AsyncMock(return_value=3)
        svc.folder_repo.update_count = AsyncMock()
        with patch("app.modules.admin.service.AuditService"):
            resp = await svc.batch_items(
                6, BatchItemRequest(item_ids=[10, 11, 12], action="MOVE", target_folder_id=5), actor=None
            )
        assert resp.affected_count == 3
        calls = [c.args for c in svc.folder_repo.update_count.call_args_list]
        assert (2, -3) in calls
        assert (5, 3) in calls


# ============================================================ ensure_default_folder / list_folders / list_items


class TestEnsureDefaultFolder:
    @pytest.mark.asyncio
    async def test_existing_default_returned(self) -> None:
        svc = CollectionService(AsyncMock())
        existing = _folder(id=1, is_default=True)
        svc.folder_repo.get_default = AsyncMock(return_value=existing)
        out = await svc.ensure_default_folder(6)
        assert out.id == 1

    @pytest.mark.asyncio
    async def test_creates_when_missing(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_default = AsyncMock(return_value=None)
        svc.folder_repo.get_by_name = AsyncMock(return_value=None)
        created = _folder(id=2, is_default=True, name="我的收藏")
        svc.folder_repo.create = AsyncMock(return_value=created)
        out = await svc.ensure_default_folder(6)
        assert out.id == 2
        assert out.is_default is True


class TestListFolders:
    @pytest.mark.asyncio
    async def test_returns_responses(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.list_for_user = AsyncMock(return_value=[_folder(id=1), _folder(id=2, is_default=False, name="待写作")])
        out = await svc.list_folders(6)
        assert len(out) == 2
        assert out[0].is_default is True
        assert out[1].name == "待写作"


class TestGetItem:
    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=None)
        with pytest.raises(ItemNotFoundError):
            await svc.get_item(6, 99)

    @pytest.mark.asyncio
    async def test_orphan_event_raises(self) -> None:
        """event 软删除 → 抛 ItemNotFoundError（与 404 行为一致）。"""
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=_item(id=10))
        r_folder = MagicMock(scalar_one_or_none=MagicMock(return_value=_folder()))
        r_ev = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        svc.session.execute = AsyncMock(side_effect=[r_folder, r_ev])
        with pytest.raises(ItemNotFoundError):
            await svc.get_item(6, 10)


class TestUpdateItemFolderMoveEdge:
    @pytest.mark.asyncio
    async def test_folder_move_to_default_keeps_count(self) -> None:
        """移动到的 folder 是默认收藏夹时，update_count 调用两次（-1 +1）。"""
        item = _item(id=10, folder_id=2)
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=item)
        svc.folder_repo.get_for_user = AsyncMock(return_value=_folder(id=1, is_default=True))
        svc.folder_repo.update_count = AsyncMock()
        svc.item_repo.save = AsyncMock()
        r_folder, r_ev = _hyd_result()
        svc.session.execute = AsyncMock(side_effect=[r_folder, r_ev])
        with patch("app.modules.admin.service.AuditService"):
            await svc.update_item(6, 10, ItemUpdateRequest(folder_id=1), actor=None)
        calls = [c.args for c in svc.folder_repo.update_count.call_args_list]
        assert (2, -1) in calls
        assert (1, 1) in calls

    @pytest.mark.asyncio
    async def test_folder_move_unknown_folder_raises(self) -> None:
        item = _item(id=10, folder_id=2)
        svc = CollectionService(AsyncMock())
        svc.item_repo.get_for_user = AsyncMock(return_value=item)
        svc.folder_repo.get_for_user = AsyncMock(return_value=None)
        from app.modules.collection.exceptions import FolderNotFoundError
        with pytest.raises(FolderNotFoundError):
            await svc.update_item(6, 10, ItemUpdateRequest(folder_id=99), actor=None)


class TestCreateItemFolderSelected:
    @pytest.mark.asyncio
    async def test_folder_id_not_belonging_to_user_raises(self) -> None:
        """显式传 folder_id 但属于其它用户 → 抛 FolderNotFoundError。"""
        svc = CollectionService(AsyncMock())
        ev = _event()
        r_ev = MagicMock(scalar_one_or_none=MagicMock(return_value=ev))
        svc.session.execute = AsyncMock(return_value=r_ev)
        svc.item_repo.count_for_user = AsyncMock(return_value=0)
        svc.item_repo.get_by_event = AsyncMock(return_value=None)
        svc.folder_repo.get_for_user = AsyncMock(return_value=None)
        from app.modules.collection.exceptions import FolderNotFoundError
        with pytest.raises(FolderNotFoundError):
            await svc.create_item(
                6, ItemCreateRequest(event_id=9, folder_id=99), actor=None
            )


class TestBatchInvalidAction:
    @pytest.mark.asyncio
    async def test_move_without_target_folder_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        from app.modules.collection.exceptions import InvalidBatchActionError
        with pytest.raises(InvalidBatchActionError):
            await svc.batch_items(
                6, BatchItemRequest(item_ids=[1], action="MOVE"), actor=None  # 缺 target_folder_id
            )

    @pytest.mark.asyncio
    async def test_move_target_folder_not_found(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=None)
        from app.modules.collection.exceptions import FolderNotFoundError
        with pytest.raises(FolderNotFoundError):
            await svc.batch_items(
                6, BatchItemRequest(item_ids=[1], action="MOVE", target_folder_id=99), actor=None
            )

    @pytest.mark.asyncio
    async def test_add_tag_without_tag_raises(self) -> None:
        svc = CollectionService(AsyncMock())
        from app.modules.collection.exceptions import InvalidBatchActionError
        with pytest.raises(InvalidBatchActionError):
            await svc.batch_items(
                6, BatchItemRequest(item_ids=[1], action="ADD_TAG"), actor=None  # 缺 tag
            )


class TestBatchDelete:
    @pytest.mark.asyncio
    async def test_delete_soft_deletes_and_decrements_counts(self) -> None:
        items = [_item(id=10, folder_id=2), _item(id=11, folder_id=3)]
        svc = CollectionService(AsyncMock())
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
        svc.session.execute = AsyncMock(return_value=result_mock)
        svc.item_repo.bulk_soft_delete = AsyncMock(return_value=2)
        svc.folder_repo.update_count = AsyncMock()
        with patch("app.modules.admin.service.AuditService"):
            resp = await svc.batch_items(
                6, BatchItemRequest(item_ids=[10, 11], action="DELETE"), actor=None
            )
        assert resp.affected_count == 2
        calls = [c.args for c in svc.folder_repo.update_count.call_args_list]
        assert (2, -1) in calls
        assert (3, -1) in calls


class TestBatchMarkRead:
    @pytest.mark.asyncio
    async def test_mark_read_no_count_change(self) -> None:
        svc = CollectionService(AsyncMock())
        svc.item_repo.bulk_set_read_status = AsyncMock(return_value=5)
        svc.folder_repo.update_count = AsyncMock()
        with patch("app.modules.admin.service.AuditService"):
            resp = await svc.batch_items(
                6, BatchItemRequest(item_ids=[1, 2, 3, 4, 5], action="MARK_READ"), actor=None
            )
        assert resp.affected_count == 5
        svc.folder_repo.update_count.assert_not_called()


class TestBatchAddRemoveTag:
    @pytest.mark.asyncio
    async def test_add_tag_appends_new(self) -> None:
        items = [_item(id=10, user_tags=[]), _item(id=11, user_tags=["x"])]
        svc = CollectionService(AsyncMock())
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
        svc.session.execute = AsyncMock(return_value=result_mock)
        with patch("app.modules.admin.service.AuditService"):
            resp = await svc.batch_items(
                6, BatchItemRequest(item_ids=[10, 11], action="ADD_TAG", tag="new"), actor=None
            )
        assert resp.affected_count == 2
        assert "new" in items[0].user_tags
        # item 1 已有 "x"，应追加 "new"
        assert "new" in items[1].user_tags
        assert items[1].user_tags == ["x", "new"]

    @pytest.mark.asyncio
    async def test_remove_tag_drops_value(self) -> None:
        items = [_item(id=10, user_tags=["x", "y"]), _item(id=11, user_tags=["x"])]
        svc = CollectionService(AsyncMock())
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
        svc.session.execute = AsyncMock(return_value=result_mock)
        with patch("app.modules.admin.service.AuditService"):
            resp = await svc.batch_items(
                6, BatchItemRequest(item_ids=[10, 11], action="REMOVE_TAG", tag="x"), actor=None
            )
        assert resp.affected_count == 2
        assert items[0].user_tags == ["y"]
        assert items[1].user_tags == []


class TestUpdateFolderEditFields:
    @pytest.mark.asyncio
    async def test_edit_description_and_color(self) -> None:
        folder = _folder(is_default=False, name="待写作", description="old desc", color="#000000")
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=folder)
        svc.folder_repo.save = AsyncMock()
        with patch("app.modules.admin.service.AuditService"):
            await svc.update_folder(
                6, 1, FolderUpdateRequest(description="new desc", color="#ffffff"), actor=None
            )
        assert folder.description == "new desc"
        assert folder.color == "#ffffff"
        svc.folder_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_rename_to_existing_name_raises(self) -> None:
        folder = _folder(is_default=False, name="A")
        svc = CollectionService(AsyncMock())
        svc.folder_repo.get_for_user = AsyncMock(return_value=folder)
        svc.folder_repo.get_by_name = AsyncMock(return_value=_folder(is_default=False, name="B"))
        with pytest.raises(FolderNameExistsError):
            await svc.update_folder(6, 1, FolderUpdateRequest(name="B"), actor=None)


class TestGetStats:
    @pytest.mark.asyncio
    async def test_returns_aggregated_counts(self) -> None:
        svc = CollectionService(AsyncMock())
        rows_mock = MagicMock()
        rows_mock.all = MagicMock(return_value=[("UNREAD", 5), ("LATER", 2), ("READ", 3)])
        cat_mock = MagicMock()
        cat_mock.all = MagicMock(return_value=[])
        month_mock = MagicMock()
        month_mock.all = MagicMock(return_value=[])
        svc.session.execute = AsyncMock(side_effect=[rows_mock, cat_mock, month_mock])
        svc.folder_repo.count_for_user = AsyncMock(return_value=2)
        stats = await svc.get_stats(6)
        assert stats.total_items == 10
        assert stats.unread_count == 5
        assert stats.later_count == 2
        assert stats.read_count == 3
        assert stats.folder_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
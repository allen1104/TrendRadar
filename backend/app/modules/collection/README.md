# Collection 模块（二期）

> 收藏系统。把发现变成沉淀——用户把感兴趣的热点事件收进收藏夹、加笔记、加自定义标签、标记稍后读。
>
> 需求：[doc/SPEC-collection.md](../../../doc/SPEC-collection.md)

## 状态

✅ 已完成 · 2026-08-01

## 模块文件

```
app/modules/collection/
  enums.py         ReadStatus 三态枚举
  exceptions.py    7 个业务异常（FolderNotFound / AlreadyCollected / CannotDeleteDefaultFolder / ItemNotFound / ItemQuotaExceeded / FolderQuotaExceeded / EventNotFoundForCollect）
  model.py         CollectionFolder + CollectionItem 模型
  schema.py        Folder{Create,Update,Response} / Item{Create,Update,Response} / BatchItemRequest / StatsResponse / EventBrief / CollectedEventIdsResponse
  repository.py    CollectionFolderRepository + CollectionItemRepository（含批量更新 / 批量软删 / 批量统计 / 标签统计）
  service.py       CollectionService（13 个方法：folder CRUD / item CRUD / batch 5 actions / default folder 自动建 / list_collected_event_ids / get_stats）
  api.py           folders_router + items_router + stats_router
  tasks.py         cleanup_task（每日校正 folder.item_count + 软删 30 天前条目）+ 注册到 admin.cleanup_task 内部调
```

测试：`backend/tests/collection/` — 3 文件，40 用例（service 23 + api 14 + enums 3）。

## 接口清单（11 个，全部需登录）

| 方法 | 路径 | 错误码 |
|------|------|--------|
| `GET /collections/folders` | 收藏夹列表 | — |
| `POST /collections/folders` | 新建收藏夹（≤50） | `400 FOLDER_NAME_REQUIRED` · `409 FOLDER_NAME_EXISTS` · `400 QUOTA_EXCEEDED` |
| `PATCH /collections/folders/{id}` | 改名称/描述/颜色/排序 | `404 FOLDER_NOT_FOUND` · `400 CANNOT_DELETE_DEFAULT_FOLDER`（默认不可改名/改色/改排序） · `409 FOLDER_NAME_EXISTS` |
| `DELETE /collections/folders/{id}` | 软删除（items 迁默认） | `404 FOLDER_NOT_FOUND` · `400 CANNOT_DELETE_DEFAULT_FOLDER` |
| `GET /collections/items` | 我的收藏条目（分页 + 过滤） | — |
| `GET /collections/items/event-ids?eventIds=1,2,5` | hotspot 内部用：返回用户已收藏的 event_ids | — |
| `GET /collections/items/{id}` | 条目详情 | `404 ITEM_NOT_FOUND`（含跨用户 404） |
| `POST /collections/items` | 收藏一个事件 | `404 EVENT_NOT_FOUND` · `409 ALREADY_COLLECTED`（body 带 `existingItemId`） · `400 QUOTA_EXCEEDED` |
| `PATCH /collections/items/{id}` | 改 folder/note/tags/readStatus | `404 ITEM_NOT_FOUND` · `404 FOLDER_NOT_FOUND`（跨用户） |
| `DELETE /collections/items/{id}` | 取消收藏 | `404 ITEM_NOT_FOUND` |
| `POST /collections/items/batch` | 批量：MOVE / DELETE / MARK_READ / ADD_TAG / REMOVE_TAG | `400 INVALID_BATCH_ACTION` |
| `GET /collections/stats` | 我的统计：总数/未读/稍后读/已读 + 按分类 + 最近 6 月 | — |

## 关键业务规则

1. **唯一性**：同 user 同 event 只能收藏一次（`uk_item_user_event`），重复 → 409 + `existingItemId`
2. **配额**：folder ≤50 (`FOLDER_QUOTA`)、item ≤10000 (`ITEM_QUOTA`)
3. **默认收藏夹**：首次收藏自动建「我的收藏」`is_default=true`，不可删不可改名，唯一的写入入口是 `ensure_default_folder()`
4. **删除保护**：删除 folder 时其 items 全部迁到默认文件夹并原子调整两个 folder 的 `item_count`
5. **跨用户隔离**：所有查询带 `WHERE user_id=? AND is_deleted=false`，跨用户访问返回 404（不暴露存在性）
6. **审计**：所有写操作（folder CRUD + item CRUD + batch）写 `audit_log`，`target_type` 用 `COLLECTION_FOLDER`/`COLLECTION_ITEM`
7. **readStatus=READ**：`PATCH /items/{id}` 时自动写 `read_at=now()`；反向改 `UNREAD` 时清空 `read_at`

## 与 hotspot 的集成点

hotspot 的 `_assemble_list_items` 和 `get_event_detail` 现在调 `CollectionService.list_collected_event_ids(user.id, [event_ids])`，`is_collected = e.id in collected_ids` 返回真实值（不再硬编码 False）。

**缓存策略**：
- 登录用户的 list/detail 请求**跳过缓存**（`is_collected` 个性化）
- 匿名请求正常进缓存（`is_collected=False`）

这样保持 SPEC §性能（热点榜 P95<300ms）的同时返回真实收藏状态。

## 关键 SQL

```sql
-- 批量查 isCollected
SELECT event_id FROM collection_item
WHERE user_id = ? AND event_id = ANY(:ids) AND is_deleted = false;
-- 单 SQL，无 N+1
```

GIN 索引 `idx_item_tags ON collection_item USING gin (user_tags)` 让自定义标签过滤走索引。

## 错误码完整列表

| errorCode | status | 触发场景 |
|-----------|--------|----------|
| `FOLDER_NOT_FOUND` | 404 | folder_id 不存在或跨用户 |
| `FOLDER_NAME_EXISTS` | 409 | 同用户下同名 folder |
| `FOLDER_NAME_REQUIRED` | 400 | 名称为空或纯空白（Pydantic 校验） |
| `CANNOT_DELETE_DEFAULT_FOLDER` | 400 | 默认收藏夹不可删/改 |
| `QUOTA_EXCEEDED` | 400 | folder >50 或 item >10000 |
| `ITEM_NOT_FOUND` | 404 | item_id 不存在或跨用户 |
| `ALREADY_COLLECTED` | 409 | 同 event 已收藏，body 带 `existingItemId` |
| `INVALID_BATCH_ACTION` | 400 | batch action 不在 5 种之内或缺必填字段 |

## 验证状态

| 时间 | 验证项 | 结果 |
|------|--------|------|
| 2026-08-01 | Alembic migration `20260731_0006_collection_tables.py` | 2 张表创建成功 |
| 2026-08-01 | 单测：test_enums (3) + test_service (23) + test_api (14) | 40 passed |
| 2026-08-01 | 全栈无回归：301 tests | all pass |
| 2026-08-01 | 前端 `pnpm typecheck` | exit 0 |
| 2026-08-01 | 前端 `pnpm build` | 1.6 MB bundle / 3154 modules |
| 2026-08-01 | 服务端 inline-import CollectionService 集成 hotspot | `_assemble_list_items` 返回真实 `is_collected` |

## 不在 MVP 范围（SPEC 列但本期末做）

- ❌ Folder 拖拽排序（仅 sort_order 字段 + PATCH 修改）
- ❌ Folder color picker（API 字段在，前端用默认调色板 6 色）
- ❌ 收藏夹封面图 / 描述编辑器
- ❌ 移动端拖拽重排
- ❌ 收藏 RSS 订阅
- ❌ 详情页 ⭐ 按钮（MVP 仅卡片上加）
- ❌ 软删除 180 天后的 audit 清理（与 admin.cleanup 重复）
- ❌ 推荐事件 / 相似事件（依赖二期 trend 模块）
- ❌ CSV 导出

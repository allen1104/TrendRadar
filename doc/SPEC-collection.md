# 收藏系统模块（collection）

所属项目: @SPEC.md
模块状态: ⏳ 未开始
一期范围: — 二期
最后更新: 2026-07-29

---

## 功能目标

把"发现"变成"沉淀"。用户可以把热点事件收进收藏夹、打自定义标签、写笔记、
标记稍后读，最终形成个人知识库。

四种能力：**收藏** · **标签** · **笔记** · **稍后读**

---

## 数据库设计

### `collection_folder` 表

| 字段        | 类型         | 必填 | 说明                                          |
| ----------- | ------------ | ---- | --------------------------------------------- |
| id          | BIGSERIAL    | 是   | 主键                                          |
| user_id     | BIGINT       | 是   | 所属用户                                      |
| name        | VARCHAR(100) | 是   | 收藏夹名，同用户下唯一                        |
| description | VARCHAR(500) | 否   | 描述                                          |
| color       | VARCHAR(16)  | 否   | 颜色标识（hex），用于前端区分                 |
| sort_order  | INTEGER      | 是   | 排序，默认 0                                  |
| is_default  | BOOLEAN      | 是   | 是否默认收藏夹，默认 false                    |
| item_count  | INTEGER      | 是   | 条目数（冗余计数），默认 0                    |
| created_at  | TIMESTAMPTZ  | -    | 创建时间                                      |
| updated_at  | TIMESTAMPTZ  | -    | 更新时间                                      |
| is_deleted  | BOOLEAN      | -    | 逻辑删除，默认 false                          |

索引：`uk_folder_user_name(user_id, name) WHERE is_deleted=false`、`idx_folder_user(user_id, sort_order)`

> 用户首次收藏时自动创建默认收藏夹「我的收藏」（`is_default=true`）。

### `collection_item` 表

| 字段        | 类型         | 必填 | 说明                                                |
| ----------- | ------------ | ---- | --------------------------------------------------- |
| id          | BIGSERIAL    | 是   | 主键                                                |
| user_id     | BIGINT       | 是   | 所属用户                                            |
| folder_id   | BIGINT       | 是   | 收藏夹 ID                                           |
| event_id    | BIGINT       | 是   | 收藏的事件 ID                                       |
| note        | TEXT         | 否   | 用户笔记（Markdown）                                |
| user_tags   | JSONB        | 是   | 用户自定义标签数组 `["待写作","竞品"]`，默认 `[]`   |
| read_status | VARCHAR(32)  | 是   | `UNREAD`/`LATER`/`READ`，默认 `UNREAD`              |
| read_at     | TIMESTAMPTZ  | 否   | 标记已读的时间                                      |
| created_at  | TIMESTAMPTZ  | -    | 收藏时间                                            |
| updated_at  | TIMESTAMPTZ  | -    | 更新时间                                            |
| is_deleted  | BOOLEAN      | -    | 逻辑删除，默认 false                                |

索引：`uk_item_user_event(user_id, event_id) WHERE is_deleted=false`、`idx_item_folder(folder_id, created_at DESC)`、`idx_item_read_status(user_id, read_status)`、`idx_item_tags` GIN on `user_tags`

> 同一用户对同一事件只能有一条收藏记录（可移动收藏夹，不可重复收藏）。

---

## 后端接口

### GET /api/v1/collections/folders
**说明**: 我的收藏夹列表。需登录

**Response 200**:
```json
[
  { "id": 1, "name": "我的收藏", "description": null, "color": "#3b82f6",
    "sortOrder": 0, "isDefault": true, "itemCount": 42 },
  { "id": 2, "name": "待写作", "description": "准备写公众号的选题", "color": "#f59e0b",
    "sortOrder": 1, "isDefault": false, "itemCount": 8 }
]
```

### POST /api/v1/collections/folders
**Request Body**: `{ "name": "待写作", "description": "...", "color": "#f59e0b" }`
**Response 201**: folder 对象
**错误情况**: 同名 → `409` `FOLDER_NAME_EXISTS`；数量超 50 → `400` `TOO_MANY_FOLDERS`

### PATCH /api/v1/collections/folders/{id}
可改 `name` / `description` / `color` / `sortOrder`。默认收藏夹不可改名为空

### DELETE /api/v1/collections/folders/{id}
**说明**: 删除收藏夹。其中的条目移动到默认收藏夹
**错误情况**: 删除默认收藏夹 → `400` `CANNOT_DELETE_DEFAULT_FOLDER`

---

### GET /api/v1/collections/items
**说明**: 我的收藏条目。需登录

**Query**: `page` `size` `folderId` `readStatus` `userTag` `keyword` `sort`（`createdAt`/`recommendIndex`，默认 `-createdAt`）

**Response 200**:
```json
{
  "items": [
    {
      "id": 501,
      "folderId": 2,
      "folderName": "待写作",
      "note": "重点看第三段的架构图\n\n- 和我们的 Agent 设计思路一致",
      "userTags": ["待写作", "Agent"],
      "readStatus": "LATER",
      "readAt": null,
      "createdAt": "2026-07-29T09:12:00Z",
      "event": {
        "id": 88,
        "title": "OpenAI 发布 GPT-5，多模态推理能力大幅提升",
        "summaryOneLine": "GPT-5 在多模态推理上超越前代 40%",
        "categories": ["AI", "LLM"],
        "recommendIndex": 88.6,
        "sourceCount": 4,
        "lastSeenAt": "2026-07-29T07:40:00Z"
      }
    }
  ],
  "total": 50, "page": 1, "size": 20, "pages": 3
}
```

### POST /api/v1/collections/items
**说明**: 收藏一个事件

**Request Body**:
```json
{ "eventId": 88, "folderId": null, "note": null, "userTags": [], "readStatus": "UNREAD" }
```
> `folderId` 为空时进默认收藏夹（不存在则自动创建）

**Response 201**: item 对象
**错误情况**:
- 已收藏 → `409` `ALREADY_COLLECTED`（响应体带已有 `itemId`，前端可直接跳转编辑）
- 事件不存在 → `404` `EVENT_NOT_FOUND`

### PATCH /api/v1/collections/items/{id}
**说明**: 修改笔记 / 标签 / 收藏夹 / 阅读状态

**Request Body**（均可选）:
```json
{ "folderId": 2, "note": "更新的笔记", "userTags": ["待写作"], "readStatus": "READ" }
```
> `readStatus` 改为 `READ` 时自动写 `readAt`

### DELETE /api/v1/collections/items/{id}
**说明**: 取消收藏（软删除），同步递减 `folder.item_count`
**Response 204**

### POST /api/v1/collections/items/batch
**说明**: 批量操作

**Request Body**:
```json
{ "itemIds": [501, 502], "action": "MOVE", "targetFolderId": 3 }
```
- `action`: `MOVE`（移动收藏夹） / `DELETE` / `MARK_READ` / `ADD_TAG` / `REMOVE_TAG`
- `ADD_TAG`/`REMOVE_TAG` 需额外传 `tag` 字段

**Response 200**: `{ "affectedCount": 2 }`

---

### GET /api/v1/collections/tags
**说明**: 我用过的所有自定义标签及使用次数

**Response 200**: `[{ "tag": "待写作", "count": 12 }, { "tag": "竞品", "count": 5 }]`

### GET /api/v1/collections/stats
**说明**: 收藏统计（用于个人中心）

**Response 200**:
```json
{
  "totalItems": 50,
  "unreadCount": 18,
  "laterCount": 12,
  "readCount": 20,
  "folderCount": 3,
  "byCategory": [{ "category": "AI", "count": 22 }],
  "recentMonths": [{ "month": "2026-07", "count": 31 }]
}
```

---

## 前端页面

### 收藏入口（嵌入热点中心与详情页）
- 事件卡片右下角 ⭐ 图标：
  - 未收藏 → 空心星，点击直接收进默认收藏夹（乐观更新 + Toast「已收藏到 我的收藏，点击更改」）
  - 已收藏 → 实心星（主题色），点击打开编辑弹窗
- Toast 上的「更改」→ 打开收藏编辑弹窗
- **收藏编辑弹窗**：
  - 收藏夹下拉（含「+ 新建收藏夹」内联选项）
  - 自定义标签 Combobox（可创建新标签，从 `/collections/tags` 提示历史标签）
  - 笔记 Markdown 编辑器（简版：加粗/列表/链接工具栏 + 预览切换）
  - 阅读状态 Segmented：未读 / 稍后读 / 已读
  - 「取消收藏」危险按钮（左下角）

### 我的收藏（`/collections`）
**左侧栏**
- 收藏夹列表（拖拽排序），每项显示颜色点 + 名称 + 条目数
- 「全部」「稍后读」「未读」三个虚拟视图置顶
- 底部「+ 新建收藏夹」
- 收藏夹右键菜单：重命名、改颜色、删除

**主区域**
- 顶部：搜索框 + 阅读状态筛选 + 自定义标签筛选（Chips 多选）+ 排序下拉
- 视图切换：列表视图 / 卡片视图
- 条目卡片：
  ```
  ┌────────────────────────────────────────────────┐
  │ ● 待写作            [待写作][Agent]   稍后读 ● │
  │ OpenAI 发布 GPT-5，多模态推理能力大幅提升        │
  │ GPT-5 在多模态推理上超越前代 40%                 │
  │ ┌──────────────────────────────────────────┐   │
  │ │ 📝 重点看第三段的架构图                    │   │  ← 笔记预览，2 行截断
  │ └──────────────────────────────────────────┘   │
  │ 收藏于 2 小时前          [编辑] [标已读] [移除] │
  └────────────────────────────────────────────────┘
  ```
- 批量模式：左上「选择」按钮 → 每条出现 checkbox → 底部浮出批量操作条（移动 / 打标签 / 标已读 / 删除）
- 空状态：插画 + "还没有收藏，去热点中心逛逛" + 跳转按钮

**右侧栏（桌面端）**
- 收藏统计卡：总数 / 未读 / 稍后读
- 分类分布饼图（ECharts）
- 我的标签云（点击加入筛选）

### 稍后读（`/collections?readStatus=LATER` 的快捷入口）
- 顶部导航栏显示未读徽标数
- 阅读模式：点击进入事件详情后自动提示「标记为已读？」

---

## 业务规则

- **收藏唯一性**：同用户同事件只能有一条 `collection_item`，重复收藏返回 409 并带上已有 ID
- **默认收藏夹**：用户首次收藏时自动创建「我的收藏」（`is_default=true`），不可删除、不可改为非默认
- **计数一致性**：`folder.item_count` 在收藏/取消/移动时用 `UPDATE ... SET item_count = item_count ± 1` 原子更新；每日 `cleanup_task` 校正一次
- **数量上限**：单用户收藏夹 ≤ 50，收藏条目 ≤ 10000（超出 `400 QUOTA_EXCEEDED`）
- **自定义标签**：不落独立表，直接存 `collection_item.user_tags` JSONB；`/collections/tags` 用 `jsonb_array_elements_text` 聚合统计
- **标签规范**：单标签 ≤ 20 字符，单条目 ≤ 10 个标签，自动去重去空白
- **笔记**：Markdown 文本，≤ 20000 字符；渲染时必须做 XSS 过滤（`rehype-sanitize`）
- **事件删除**：事件被软删除后，收藏条目保留但前端标记「原事件已下架」，仍可查看笔记
- **权限**：所有接口仅操作**当前登录用户自己的**数据；`user_id` 从 Token 取，**不接受请求参数传入**
- **`isCollected` 字段**：`hotspot` 模块的事件列表/详情接口返回该字段，实现为一次批量查询（`WHERE user_id=? AND event_id = ANY(?)`），不做 N+1

---

## 完成标准

- [ ] `collection_folder` / `collection_item` 表与迁移完成
- [ ] 收藏夹 CRUD 完成，默认收藏夹保护生效
- [ ] 收藏条目 CRUD 完成，唯一性约束生效（409 带已有 ID）
- [ ] 批量操作 5 种 action 全部生效
- [ ] `item_count` 计数原子更新，每日校正任务生效
- [ ] 自定义标签聚合统计正确
- [ ] 配额上限校验生效
- [ ] `user_id` 一律取自 Token，越权访问他人数据返回 404
- [ ] `hotspot` 的 `isCollected` 批量查询生效，无 N+1
- [ ] 事件卡片 ⭐ 一键收藏 + 乐观更新 + Toast 二次编辑
- [ ] 收藏编辑弹窗完成（收藏夹/标签/笔记/状态）
- [ ] 我的收藏页完成：左侧收藏夹树、筛选、批量模式、统计侧栏
- [ ] 笔记 Markdown 渲染做 XSS 过滤
- [ ] 单元测试：唯一性、计数一致性、配额、越权防护；覆盖率 ≥ 75%

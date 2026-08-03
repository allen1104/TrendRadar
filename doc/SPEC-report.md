# 日报中心模块（report）

所属项目: @SPEC.md
模块状态: ✅ 已完成
一期范围: — 二期
最后更新: 2026-08-02

---

## 功能目标

每天固定时间自动汇总当日最有价值的热点，生成四类日报：

**AI 日报** · **科技日报** · **GitHub 日报** · **Agent 日报**

支持 EDITOR 审核后发布，支持四种导出格式（Markdown / HTML / PDF / 微信公众号），
用户可订阅并通过 RSS 消费。

---

## 数据库设计

### `report` 表

| 字段            | 类型          | 必填 | 说明                                                       |
| --------------- | ------------- | ---- | ---------------------------------------------------------- |
| id              | BIGSERIAL     | 是   | 主键                                                       |
| report_type     | VARCHAR(32)   | 是   | `AI`/`TECH`/`GITHUB`/`AGENT`                               |
| report_date     | DATE          | 是   | 日报日期                                                   |
| title           | VARCHAR(300)  | 是   | 标题，如「AI 日报 · 2026年7月29日」                        |
| intro           | TEXT          | 否   | 开篇导语（AI 生成的当日综述，150-300 字）                  |
| outro           | TEXT          | 否   | 结尾语                                                     |
| content_md      | TEXT          | 是   | 完整 Markdown 正文                                         |
| content_edited  | TEXT          | 否   | EDITOR 编辑后的正文                                        |
| item_count      | SMALLINT      | 是   | 条目数，默认 0                                             |
| status          | VARCHAR(32)   | 是   | `GENERATING`/`DRAFT`/`PUBLISHED`/`FAILED`                  |
| published_at    | TIMESTAMPTZ   | 否   | 发布时间                                                   |
| published_by    | BIGINT        | 否   | 发布人                                                     |
| view_count      | INTEGER       | 是   | 阅读数，默认 0                                             |
| model_alias     | VARCHAR(100)  | 否   | 使用的模型                                                 |
| cost_usd        | NUMERIC(10,6) | 是   | 生成费用，默认 0                                           |
| error_message   | VARCHAR(500)  | 否   | 失败原因                                                   |
| created_at      | TIMESTAMPTZ   | -    | 创建时间                                                   |
| updated_at      | TIMESTAMPTZ   | -    | 更新时间                                                   |
| is_deleted      | BOOLEAN       | -    | 逻辑删除，默认 false                                       |

索引：`uk_report_type_date(report_type, report_date) WHERE is_deleted=false`、`idx_report_status_date(status, report_date DESC)`

### `report_item` 表

| 字段         | 类型         | 必填 | 说明                                          |
| ------------ | ------------ | ---- | --------------------------------------------- |
| id           | BIGSERIAL    | 是   | 主键                                          |
| report_id    | BIGINT       | 是   | 所属日报                                      |
| event_id     | BIGINT       | 是   | 关联事件                                      |
| section      | VARCHAR(64)  | 是   | 所属板块，如 `头条`/`模型发布`/`开源项目`     |
| sort_order   | SMALLINT     | 是   | 板块内排序，默认 0                            |
| headline     | VARCHAR(300) | 是   | 日报中的条目标题（可能与事件标题不同）        |
| brief        | TEXT         | 是   | 条目简述（AI 生成，80-150 字）                |
| comment      | TEXT         | 否   | 编辑点评（EDITOR 手动加）                     |
| is_top       | BOOLEAN      | 是   | 是否头条，默认 false                          |
| created_at   | TIMESTAMPTZ  | -    | 创建时间                                      |
| updated_at   | TIMESTAMPTZ  | -    | 更新时间                                      |
| is_deleted   | BOOLEAN      | -    | 逻辑删除，默认 false                          |

索引：`idx_report_item(report_id, section, sort_order)`、`idx_report_item_event(event_id)`

### `report_subscription` 表

| 字段          | 类型         | 必填 | 说明                                                |
| ------------- | ------------ | ---- | --------------------------------------------------- |
| id            | BIGSERIAL    | 是   | 主键                                                |
| user_id       | BIGINT       | 是   | 用户                                                |
| report_types  | JSONB        | 是   | 订阅的日报类型数组，默认 `[]`                       |
| channel       | VARCHAR(32)  | 是   | `SITE`/`EMAIL`/`WEBHOOK`，默认 `SITE`               |
| webhook_url   | VARCHAR(500) | 否   | `channel=WEBHOOK` 时必填                            |
| rss_token     | VARCHAR(64)  | 否   | 私有 RSS 订阅令牌（随机生成）                       |
| enabled       | BOOLEAN      | 是   | 默认 true                                           |
| created_at    | TIMESTAMPTZ  | -    | 创建时间                                            |
| updated_at    | TIMESTAMPTZ  | -    | 更新时间                                            |
| is_deleted    | BOOLEAN      | -    | 逻辑删除，默认 false                                |

索引：`uk_subscription_user(user_id) WHERE is_deleted=false`、`uk_subscription_rss_token(rss_token)`

---

## 日报类型定义

| report_type | 名称        | 选题范围                                                  | 条目数 | 板块划分                                    |
| ----------- | ----------- | --------------------------------------------------------- | ------ | ------------------------------------------- |
| `AI`        | AI 日报     | `categories` 含 `AI`/`LLM`/`AGENT`/`MCP`                  | 8-12   | 头条 / 模型发布 / 应用与产品 / 研究进展     |
| `TECH`      | 科技日报    | 全部分类，按 `recommendIndex` 取最高                      | 10-15  | 头条 / 行业动态 / 产品发布 / 商业与创投     |
| `GITHUB`    | GitHub 日报 | 关联文章来源 `source.category = CODE`                     | 8-12   | 今日最热 / 新星项目 / 重要更新              |
| `AGENT`     | Agent 日报  | `categories` 含 `AGENT`/`MCP`                             | 5-10   | 头条 / 框架与工具 / 实践案例 / 协议与标准   |

**选题规则**（`report_date` 当日）：
```
候选池 = event WHERE last_seen_at 在当日范围内
              AND status = 'ANALYZED'
              AND is_hidden = false
              AND 符合该日报类型的分类条件
排序   = recommend_index DESC
取     = 该类型的条目数上限 × 1.5（多取一些交给 AI 筛选与分板块）
```
若候选池不足最小条目数（`AI`=5、`TECH`=6、`GITHUB`=4、`AGENT`=3），跳过当日该类型日报，
写 `task_run_log` 标 `SKIPPED` 并记原因。

---

## 生成流程

```
[Celery Beat 每日 report_generate_cron（默认 08:00 本地时区）]
   │
   ▼
① 选题  report.select_events_task(report_type, date)
   按上述规则拉候选池
   │
   ▼
② 编排  ai-engine 调用 task_key = report_daily
   输入：日报类型、板块定义、候选事件列表（标题+一句话总结+分类+推荐指数）
   输出（结构化 JSON）：
     { "title": "...", "intro": "...", "outro": "...",
       "sections": [
         { "name": "头条",
           "items": [ { "eventId": 88, "headline": "...", "brief": "...", "isTop": true } ] }
       ] }
   AI 负责：挑选、分板块、排序、改写标题、写简述、写导语
   │
   ▼
③ 渲染  report.render_task(report_id)
   按模板把 sections 渲染成 content_md
   │
   ▼
④ 落库  status = DRAFT（等待 EDITOR 审核）
   │
   ▼
⑤ 审核发布  EDITOR 在后台编辑后点击「发布」
   status = PUBLISHED, published_at, published_by
   │
   ▼
⑥ 推送  report.notify_task(report_id)
   订阅用户按 channel 推送（SITE 站内 / EMAIL 邮件 / WEBHOOK 回调）
   RSS feed 自动包含新发布的日报
```

**自动发布开关**：`system_config.report_auto_publish`（默认 `false`）。
设为 `true` 时跳过审核，生成后直接 `PUBLISHED`。

---

## 后端接口

### GET /api/v1/reports
**说明**: 日报列表。`GUEST` 可访问（只返回 `PUBLISHED`）

**Query**: `page` `size` `reportType` `startDate` `endDate` `status`（仅 EDITOR 可传）

**Response 200**:
```json
{
  "items": [
    { "id": 42, "reportType": "AI", "reportDate": "2026-07-29",
      "title": "AI 日报 · 2026年7月29日",
      "intro": "今天最值得关注的是 OpenAI 发布 GPT-5……",
      "itemCount": 10, "status": "PUBLISHED",
      "publishedAt": "2026-07-29T08:30:00Z", "viewCount": 1284 }
  ],
  "total": 128, "page": 1, "size": 20, "pages": 7
}
```

### GET /api/v1/reports/{id}
**说明**: 日报详情（含全部条目）。`GUEST` 可访问已发布的

**Response 200**:
```json
{
  "id": 42,
  "reportType": "AI",
  "reportDate": "2026-07-29",
  "title": "AI 日报 · 2026年7月29日",
  "intro": "今天最值得关注的是……",
  "outro": "以上就是今天的 AI 日报，明天见。",
  "contentMd": "# AI 日报 · 2026年7月29日\n\n……",
  "status": "PUBLISHED",
  "publishedAt": "2026-07-29T08:30:00Z",
  "viewCount": 1285,
  "sections": [
    {
      "name": "头条",
      "items": [
        {
          "id": 501, "eventId": 88, "isTop": true, "sortOrder": 0,
          "headline": "OpenAI 发布 GPT-5：统一架构下的多模态跃迁",
          "brief": "GPT-5 在多模态推理上超越前代 40%，同时把 API 价格降低 30%……",
          "comment": "值得重点关注定价策略的变化",
          "event": {
            "id": 88, "recommendIndex": 88.6, "sourceCount": 4,
            "categories": ["AI", "LLM"],
            "primaryArticleUrl": "https://openai.com/blog/gpt-5"
          }
        }
      ]
    }
  ]
}
```

**错误情况**:
- 不存在 → `404` `REPORT_NOT_FOUND`
- `status != PUBLISHED` 且请求者非 EDITOR → `404` `REPORT_NOT_FOUND`

### GET /api/v1/reports/latest
**说明**: 各类型最新一期日报（首页入口卡片用）

**Response 200**: `[{ "reportType": "AI", "id": 42, "title": "...", "reportDate": "2026-07-29", "itemCount": 10 }]`

---

### GET /api/v1/reports/{id}/export
**说明**: 导出日报

**Query**: `format` — `MARKDOWN` / `HTML` / `PDF` / `WECHAT_HTML`

**Response 200**: 文件流，`Content-Disposition: attachment; filename="AI日报_20260729.pdf"`

**错误情况**: `format` 非法 → `400` `INVALID_EXPORT_FORMAT`

---

### GET /api/v1/reports/rss
**说明**: RSS 订阅源，无需登录（公开）或带 `token` 参数（私有订阅）

**Query**: `reportType`（可选，不传则全部）`token`（私有订阅令牌）

**Response 200**: `application/rss+xml`，最近 30 期

---

### POST /api/v1/admin/reports/generate
**说明**: 手动触发生成日报，`EDITOR` 及以上

**Request Body**: `{ "reportType": "AI", "reportDate": "2026-07-29", "force": false }`
> `force=true` 时覆盖已存在的同日同类型日报

**Response 202**: `{ "taskId": "...", "reportId": 43 }`

**错误情况**: 已存在且 `force=false` → `409` `REPORT_ALREADY_EXISTS`

### PATCH /api/v1/admin/reports/{id}
**说明**: 编辑日报（标题、导语、结尾、正文），`EDITOR` 及以上

**Request Body**: `{ "title": "...", "intro": "...", "outro": "...", "contentEdited": "..." }`

### PATCH /api/v1/admin/reports/{id}/items/{itemId}
**说明**: 编辑条目（改写标题/简述、加点评、调排序、换板块、设头条），`EDITOR` 及以上

**Request Body**: `{ "headline": "...", "brief": "...", "comment": "...", "section": "模型发布", "sortOrder": 2, "isTop": true }`

### DELETE /api/v1/admin/reports/{id}/items/{itemId}
**说明**: 从日报中移除某条目，`EDITOR` 及以上

### POST /api/v1/admin/reports/{id}/items
**说明**: 手动添加事件到日报，`EDITOR` 及以上

**Request Body**: `{ "eventId": 91, "section": "研究进展", "headline": "...", "brief": "..." }`
> `headline`/`brief` 不传时由后端从事件分析自动填充

### POST /api/v1/admin/reports/{id}/publish
**说明**: 发布日报，`EDITOR` 及以上。触发订阅推送

**Response 200**: report 对象

**错误情况**:
- 已发布 → `400` `REPORT_ALREADY_PUBLISHED`
- 条目数为 0 → `400` `REPORT_HAS_NO_ITEMS`

### POST /api/v1/admin/reports/{id}/unpublish
**说明**: 撤回发布（回到 `DRAFT`），`ADMIN`

---

### GET/PUT /api/v1/reports/subscription
**说明**: 我的订阅设置。需登录

**PUT Request Body**:
```json
{
  "reportTypes": ["AI", "AGENT"],
  "channel": "SITE",
  "webhookUrl": null,
  "enabled": true
}
```

**Response 200**:
```json
{
  "reportTypes": ["AI", "AGENT"],
  "channel": "SITE",
  "webhookUrl": null,
  "rssToken": "rt_a1b2c3...",
  "rssUrl": "https://trendradar.app/api/v1/reports/rss?token=rt_a1b2c3...",
  "enabled": true
}
```

**错误情况**: `channel=WEBHOOK` 但 `webhookUrl` 为空 → `400` `WEBHOOK_URL_REQUIRED`

### POST /api/v1/reports/subscription/rss-token/reset
**说明**: 重置 RSS 令牌（旧链接立即失效）

---

## 前端页面

### 日报中心（`/reports`）
- 顶部：四个类型 Tab（AI / 科技 / GitHub / Agent）+ 日期选择器
- 「最新一期」大卡片：封面样式，显示标题、日期、导语前 100 字、条目数、阅读数
- 下方：历史日报时间线（按月分组），每项显示日期 + 标题 + 条目数
- 右上角：「订阅设置」按钮 + 「RSS」图标（点击复制 RSS 链接）

### 日报阅读页（`/reports/:id`）
```
┌───────────────────────────────────────────────┐
│           AI 日报 · 2026年7月29日              │
│         2026-07-29 · 10 条 · 1285 阅读         │
│                                               │
│  ┌─────────────────────────────────────────┐  │
│  │ 今天最值得关注的是 OpenAI 发布 GPT-5…    │  │  ← 导语，引用块样式
│  └─────────────────────────────────────────┘  │
│                                               │
│  ## 🔥 头条                                    │
│                                               │
│  ┌─────────────────────────────────────────┐  │
│  │ 01  OpenAI 发布 GPT-5：统一架构下的…     │  │
│  │     GPT-5 在多模态推理上超越前代 40%…    │  │
│  │     💬 值得重点关注定价策略的变化         │  │  ← 编辑点评，浅色背景
│  │     [AI][LLM]  4个来源  推荐88.6  查看→  │  │
│  └─────────────────────────────────────────┘  │
│                                               │
│  ## 模型发布                                   │
│  …                                            │
│                                               │
│  ─────────────────────────────────────────    │
│  以上就是今天的 AI 日报，明天见。               │
│                                               │
│  [导出 ▾]  [复制链接]  [订阅]                 │
└───────────────────────────────────────────────┘
```
- 右侧悬浮目录（板块导航，滚动高亮当前板块）
- 每个条目「查看→」跳转事件详情页
- 顶部进度条显示阅读进度
- 导出下拉：Markdown / HTML / PDF / 微信 HTML
- 移动端：目录折叠为顶部下拉

### 日报审核（`/admin/reports`，EDITOR）
- 列表：类型、日期、状态 Badge、条目数、生成时间、费用
- 状态筛选：草稿 / 已发布 / 生成失败
- 「手动生成」按钮 → 弹窗选类型 + 日期 + 是否覆盖
- 点击进入**编辑页**（`/admin/reports/:id/edit`）：
  - 左侧：条目列表，**支持跨板块拖拽排序**
    - 每条：拖拽手柄、序号、标题（可内联编辑）、板块下拉、头条 Switch、删除按钮
    - 展开可编辑 `brief` 与 `comment`
    - 底部「+ 添加事件」→ 打开事件搜索 Combobox
  - 右侧：实时预览（与阅读页同样式）
  - 顶部：标题 / 导语 / 结尾语编辑区（Textarea）
  - 底部操作条：保存草稿 / 预览 / **发布**（二次确认，提示会推送给 N 位订阅者）
  - 已发布的日报显示「撤回」按钮（仅 ADMIN）

### 订阅设置（个人中心的一个 Tab）
- 日报类型多选（4 个 Checkbox 卡片）
- 推送渠道 Radio：站内 / 邮件 / Webhook
  - 选 Webhook 时展开 URL 输入 + 「测试推送」按钮
- RSS 区域：显示专属 RSS 链接（只读 Input + 复制按钮）+ 「重置令牌」危险按钮
- 底部「保存」

---

## 业务规则

### 生成
- 每日 `report_generate_cron`（默认 `0 8 * * *`，可配）为四种类型各生成一份
- 四个类型并行生成，互不阻塞；单个失败不影响其他
- 同日同类型唯一（唯一索引保证），重复生成需 `force=true`
- 候选池不足最小条目数 → 跳过，记 `SKIPPED`
- AI 编排的输出用 PydanticAI 强 schema 约束；返回的 `eventId` 必须在候选池内，否则丢弃该条目
- 生成失败重试 2 次，仍失败置 `FAILED` 并告警

### 审核与发布
- `report_auto_publish=false`（默认）时生成后为 `DRAFT`，需 EDITOR 发布
- `PUBLISHED` 后 `content_md` 冻结，再改需先撤回（仅 ADMIN 可撤回）
- 发布动作写 `audit_log`
- `content_edited` 非空时，导出与展示以它为准

### 推送
- 发布后触发 `notify_task`，按订阅者的 `channel` 分发：
  - `SITE`：写站内消息（复用一个轻量 `notification` 机制，或前端轮询 `/reports/latest`）
  - `EMAIL`：发送 HTML 邮件（一期用 SMTP，模板复用 HTML 导出）
  - `WEBHOOK`：POST 日报 JSON 到 `webhook_url`，超时 10 秒，失败重试 3 次，连续失败 5 次自动禁用该订阅
- 推送任务批量分片（每批 100 个订阅者），避免长任务

### 导出
- **Markdown**：`content_edited ?? content_md` 直出
- **HTML**：Markdown 渲染 + 内置排版样式的完整文档
- **PDF**：用 `weasyprint` 从 HTML 生成；中文字体需在 Docker 镜像中预装（`Noto Sans CJK`）
- **微信 HTML**：样式内联（同 creation 模块的处理）
- PDF 生成较慢（3-10 秒），异步生成 + 结果缓存到对象存储/本地磁盘，同一日报同格式只生成一次

### RSS
- `/reports/rss` 不带 `token` → 返回所有已发布日报（公开源）
- 带 `token` → 按该用户的 `reportTypes` 过滤（私有源）
- `token` 无效 → `401`（不是 404，便于客户端识别）
- Feed 含最近 30 期，每项包含标题、链接、导语、发布时间、全文（`content:encoded`）
- 缓存 15 分钟

### 阅读计数
- `GET /reports/{id}` 时 `view_count + 1`，同一 IP + 日报 10 分钟内只计一次（Redis 去重）
- 计数用异步递增（不阻塞响应）

---

## 完成标准

- [ ] `report` / `report_item` / `report_subscription` 表与迁移完成
- [ ] `report_daily` prompt 模板 seed 完成，四种类型的板块定义写入配置
- [ ] 选题逻辑正确，候选池不足时正确跳过
- [ ] AI 编排输出 schema 约束生效，越界 `eventId` 被丢弃
- [ ] 四种日报每日自动生成，互不阻塞，单个失败不影响其他
- [ ] 同日同类型唯一约束生效，`force` 覆盖正常
- [ ] `DRAFT` → `PUBLISHED` 审核流程完成，`audit_log` 记录
- [ ] `report_auto_publish` 开关生效
- [ ] 四种导出格式全部可用，PDF 中文不乱码
- [ ] PDF 结果缓存，重复导出不重复生成
- [ ] RSS 公开源与私有源均可用，主流阅读器（Feedly/Inoreader）解析正常
- [ ] 三种推送渠道全部生效，Webhook 失败重试与自动禁用正确
- [ ] 阅读计数去重生效
- [ ] 日报中心页 + 阅读页完成（含目录导航、进度条、移动端适配）
- [ ] 日报审核编辑页完成：拖拽排序、内联编辑、实时预览、发布确认
- [ ] 订阅设置页完成，RSS 令牌可重置
- [ ] 单元测试：选题规则、schema 校验、状态流转、RSS 生成、推送重试；覆盖率 ≥ 75%

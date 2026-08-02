# 内容创作模块（creation）

所属项目: @SPEC.md
模块状态: ✅ 已完成
一期范围: — 二期
最后更新: 2026-08-02

---

## 功能目标

把"发现的热点"直接变成"能发的内容"。用户在热点详情页一键生成多平台稿件：

**平台**：微信公众号 · 技术博客 · 微博 · 小红书 · 知乎回答 · 纯 Markdown

**写作风格**：技术分析 · 营销风格 · 深度解读 · 新闻报道 · 轻松科普

生成后可编辑、可重新生成、可导出（Markdown / HTML / 微信公众号富文本）。

---

## 数据库设计

### `creation_draft` 表

| 字段              | 类型         | 必填 | 说明                                                       |
| ----------------- | ------------ | ---- | ---------------------------------------------------------- |
| id                | BIGSERIAL    | 是   | 主键                                                       |
| user_id           | BIGINT       | 是   | 所属用户                                                   |
| event_id          | BIGINT       | 是   | 来源事件                                                   |
| platform          | VARCHAR(32)  | 是   | `WECHAT`/`BLOG`/`WEIBO`/`XHS`/`ZHIHU`/`MARKDOWN`           |
| style             | VARCHAR(32)  | 是   | `TECHNICAL`/`MARKETING`/`DEEP_DIVE`/`NEWS`/`CASUAL`        |
| title             | VARCHAR(300) | 是   | 标题（AI 生成，可编辑）                                    |
| content           | TEXT         | 是   | 正文 Markdown                                              |
| content_edited    | TEXT         | 否   | 用户编辑后的正文（为空表示未编辑）                         |
| outline           | JSONB        | 是   | 大纲结构 `[{"heading":"..","points":[".."]}]`，默认 `[]`   |
| cover_suggestion  | VARCHAR(500) | 否   | 封面图建议描述                                             |
| tags_suggestion   | JSONB        | 是   | 建议话题标签数组，默认 `[]`                                |
| word_count        | INTEGER      | 是   | 字数，默认 0                                               |
| extra_params      | JSONB        | 是   | 生成参数（目标字数、受众、附加要求），默认 `{}`             |
| model_alias       | VARCHAR(100) | 否   | 使用的模型                                                 |
| prompt_version    | INTEGER      | 否   | 使用的 prompt 版本                                         |
| cost_usd          | NUMERIC(10,6)| 是   | 生成费用，默认 0                                           |
| status            | VARCHAR(32)  | 是   | `GENERATING`/`DONE`/`FAILED`                               |
| error_message     | VARCHAR(500) | 否   | 失败原因                                                   |
| regenerate_count  | SMALLINT     | 是   | 重新生成次数，默认 0                                       |
| created_at        | TIMESTAMPTZ  | -    | 创建时间                                                   |
| updated_at        | TIMESTAMPTZ  | -    | 更新时间                                                   |
| is_deleted        | BOOLEAN      | -    | 逻辑删除，默认 false                                       |

索引：`idx_draft_user_time(user_id, created_at DESC)`、`idx_draft_event(event_id)`、`idx_draft_user_platform(user_id, platform)`

---

## 平台规格

每个平台的生成约束（存 `system_config.creation_platform_specs`，ADMIN 可调）：

| platform   | 名称       | 目标字数    | 标题长度 | 特殊要求                                                  |
| ---------- | ---------- | ----------- | -------- | --------------------------------------------------------- |
| `WECHAT`   | 微信公众号 | 1500-3000   | ≤ 30 字  | 开头钩子、小标题分段、结尾引导关注；不用 Markdown 表格     |
| `BLOG`     | 技术博客   | 2000-4000   | ≤ 60 字  | 标准 Markdown、代码块、可含表格与公式、结尾参考链接        |
| `WEIBO`    | 微博       | ≤ 140 字    | 无标题   | 带 #话题# 标签，含原文短链占位，可分 2-3 条串             |
| `XHS`      | 小红书     | 300-600     | ≤ 20 字  | emoji 分段、口语化、结尾话题标签 5-8 个                    |
| `ZHIHU`    | 知乎回答   | 800-2000    | 无标题   | 先给结论、分点论述、适度引用数据、避免营销腔              |
| `MARKDOWN` | 纯 Markdown| 1000-3000   | ≤ 60 字  | 无平台修饰，纯技术记录                                    |

## 风格规格

| style       | 名称     | 语气与结构                                              |
| ----------- | -------- | ------------------------------------------------------- |
| `TECHNICAL` | 技术分析 | 冷静客观、重原理与实现、少形容词、可含伪代码            |
| `MARKETING` | 营销风格 | 强钩子、痛点切入、场景化、有行动号召                    |
| `DEEP_DIVE` | 深度解读 | 背景→现状→影响→展望，长段论述，引用多方观点             |
| `NEWS`      | 新闻报道 | 倒金字塔、5W1H、中立陈述、时间线清晰                    |
| `CASUAL`    | 轻松科普 | 类比通俗、少术语、有画面感、适合非技术读者              |

---

## 后端接口

### GET /api/v1/creation/options
**说明**: 平台与风格选项（前端渲染选择器）。`GUEST` 可访问

**Response 200**:
```json
{
  "platforms": [
    { "key": "WECHAT", "name": "微信公众号", "icon": "wechat",
      "targetWords": [1500, 3000], "description": "带钩子开头与关注引导" }
  ],
  "styles": [
    { "key": "TECHNICAL", "name": "技术分析", "description": "冷静客观，重原理与实现" }
  ]
}
```

---

### POST /api/v1/creation/drafts
**说明**: 生成稿件，**SSE 流式返回**。需登录

**Request Body**:
```json
{
  "eventId": 88,
  "platform": "WECHAT",
  "style": "DEEP_DIVE",
  "extraParams": {
    "targetWords": 2500,
    "audience": "AI 应用开发者",
    "extraRequirement": "重点展开架构部分，加入与 LangGraph 的对比"
  }
}
```

**Response 200** — `text/event-stream`
```
event: start
data: {"draftId": 701, "modelAlias": "default-chat"}

event: outline
data: {"outline": [{"heading":"一、发布了什么","points":["核心参数","定价变化"]}]}

event: delta
data: {"content": "## 一、发布了什么\n\n"}

event: done
data: {"draftId": 701, "title": "GPT-5 深度解读...", "wordCount": 2480,
       "coverSuggestion": "GPT-5 logo 与架构示意图并置的封面",
       "tagsSuggestion": ["GPT-5","OpenAI","大模型"],
       "costUsd": 0.0182, "latencyMs": 28400}
```

**错误情况**:
- 事件未分析完成 → `409` `EVENT_NOT_ANALYZED`
- 超过用户限流 → `429` `AI_RATE_LIMIT_EXCEEDED`
- `platform`/`style` 非法 → `400` `INVALID_PLATFORM` / `INVALID_STYLE`
- `targetWords` 超出该平台范围 ±50% → `400` `TARGET_WORDS_OUT_OF_RANGE`

---

### GET /api/v1/creation/drafts
**说明**: 我的草稿列表。需登录

**Query**: `page` `size` `eventId` `platform` `style` `keyword` `sort`（默认 `-createdAt`）

**Response 200**:
```json
{
  "items": [
    { "id": 701, "eventId": 88, "eventTitle": "OpenAI 发布 GPT-5…",
      "platform": "WECHAT", "style": "DEEP_DIVE",
      "title": "GPT-5 深度解读：统一架构意味着什么",
      "wordCount": 2480, "isEdited": true, "status": "DONE",
      "regenerateCount": 1, "costUsd": 0.0182,
      "createdAt": "2026-07-29T10:00:00Z" }
  ],
  "total": 12, "page": 1, "size": 20, "pages": 1
}
```

### GET /api/v1/creation/drafts/{id}
**说明**: 草稿详情（含完整正文）。需登录且为本人

**Response 200**: 完整 draft 对象，`content` 与 `contentEdited` 都返回

### PATCH /api/v1/creation/drafts/{id}
**说明**: 保存编辑

**Request Body**: `{ "title": "改后的标题", "contentEdited": "改后的正文" }`

**Response 200**: draft 对象

### DELETE /api/v1/creation/drafts/{id}
**Response 204**

### POST /api/v1/creation/drafts/{id}/regenerate
**说明**: 重新生成（可换风格/参数），SSE 流式。原稿被覆盖前先备份到 `contentEdited` 提示用户

**Request Body**: `{ "style": "TECHNICAL", "extraParams": { "extraRequirement": "..." } }`（均可选，不传沿用原值）

**错误情况**: `regenerateCount >= 5` → `400` `TOO_MANY_REGENERATIONS`

---

### GET /api/v1/creation/drafts/{id}/export
**说明**: 导出草稿

**Query**: `format` — `MARKDOWN` / `HTML` / `WECHAT_HTML` / `TXT`

**Response 200**:
- `MARKDOWN` / `TXT` → `text/markdown` / `text/plain`，`Content-Disposition: attachment`
- `HTML` → 完整 HTML 文档（含基础样式）
- `WECHAT_HTML` → 微信公众号可直接粘贴的**内联样式** HTML（所有样式写在 `style` 属性上，因为公众号编辑器会剥离 `<style>` 标签）

**错误情况**: `format` 非法 → `400` `INVALID_EXPORT_FORMAT`

---

## 前端页面

### 生成入口（事件详情页）
- 右上角「✍️ 生成文章」按钮 → 打开**生成配置弹窗**
- 弹窗内容：
  - **平台选择**：6 个图标卡片（微信/博客/微博/小红书/知乎/Markdown），单选，选中高亮
  - **风格选择**：5 个 Segmented 按钮，每个 hover 显示说明 tooltip
  - **高级选项**（可折叠）：
    - 目标字数：滑块（范围随平台变化，显示推荐区间）
    - 目标受众：Input（带常用受众下拉建议）
    - 附加要求：Textarea（≤ 500 字）
  - 底部预估提示：「预计消耗约 $0.02，耗时 20-40 秒」
  - 「开始生成」按钮

### 创作工作台（`/creation/drafts/:id`）

生成开始后跳转到此页，实时流式渲染。

```
┌──────────────────────────────────────────────────────────────┐
│ ← 返回   GPT-5 深度解读：统一架构意味着什么       [编辑标题] │
│ 微信公众号 · 深度解读 · 2480 字 · $0.0182                     │
├────────────────────────┬─────────────────────────────────────┤
│ 大纲                   │  [编辑] [预览] [微信预览]            │
│ ─────                  │ ──────────────────────────────────  │
│ ▸ 一、发布了什么       │                                     │
│   · 核心参数           │  ## 一、发布了什么                   │
│   · 定价变化           │                                     │
│ ▸ 二、技术上的突破     │  2026 年 7 月 29 日，OpenAI 正式…    │
│   · 统一架构           │                                     │
│   · 原生工具调用       │  ### 核心参数                        │
│ ▸ 三、对开发者的影响   │                                     │
│                        │  …                                  │
│ ─────                  │                                     │
│ 💡 封面建议            │                                     │
│ GPT-5 logo 与架构示意  │                                     │
│ 图并置的封面           │                                     │
│                        │                                     │
│ 🏷 建议标签            │                                     │
│ #GPT-5 #OpenAI #大模型 │                                     │
├────────────────────────┴─────────────────────────────────────┤
│ [重新生成 ▾]  [保存]  [导出 ▾]  [复制全文]        自动保存 ✓ │
└──────────────────────────────────────────────────────────────┘
```

**交互细节**
- **生成中**：右侧正文区逐字流式渲染 + 打字光标；大纲区在 `outline` 事件到达时先渲染出来（用户能立刻看到结构）
- **三种视图**：
  - `编辑` — Markdown 源码编辑器（CodeMirror 6，语法高亮 + 行号）
  - `预览` — 渲染后的 Markdown（含 XSS 过滤）
  - `微信预览` — 手机壳 mockup + 公众号样式渲染（宽度 375px）；仅 `platform=WECHAT` 时显示
- **自动保存**：编辑后 3 秒 debounce 自动 PATCH，右下角显示"保存中…/已保存 ✓"
- **大纲导航**：点击大纲项滚动到对应正文位置（编辑与预览模式都支持）
- **重新生成下拉**：换风格 / 换参数 / 完全重来；点击前提示"当前编辑内容将被覆盖"，剩余次数显示 `(3/5)`
- **导出下拉**：Markdown / HTML / 微信 HTML / 纯文本；微信 HTML 选项额外有「复制到剪贴板」（一键粘贴到公众号编辑器）
- **复制全文**：复制当前视图内容到剪贴板 + Toast

### 我的草稿（`/creation/drafts`）
- 顶部筛选：平台多选 Chips、风格下拉、关键字搜索、排序
- 卡片网格（3 列）：
  - 平台图标 + 风格 Badge
  - 标题（2 行截断）
  - 正文前 100 字预览（灰色）
  - 底部：字数 · 来源事件（可点击跳转）· 创建时间
  - hover 浮出操作：编辑 / 导出 / 删除
  - 已编辑的标 ✏️ 角标
- 空状态：插画 + "还没有草稿，去热点中心找选题"

---

## 业务规则

### 生成
- 每个 `platform` 对应一个独立 `task_key`（`creation_wechat` / `creation_blog` / …），
  Prompt 中注入平台规格与风格规格
- 输入上下文：事件标题 + `event_analysis` 全文 + 来源文章（正文各截 1500 字，最多 6 篇）
- 上下文 token 上限 `creation_max_context_tokens`（默认 20000），超出按文章权重裁剪
- 输出先出 `outline`（结构化 JSON），再流式出正文——两段式调用或单次调用中先输出 JSON 块
- 字数控制：Prompt 明确目标字数区间；生成后若偏离 ±30% 记警告日志（不自动重试，避免成本翻倍）

### 编辑与版本
- `content` 保存 AI 原始输出，**永不被用户编辑覆盖**
- 用户编辑保存到 `content_edited`；导出与预览优先用 `content_edited`
- 「恢复 AI 原稿」按钮：清空 `content_edited`
- 重新生成会覆盖 `content`；若 `content_edited` 非空，前端强制二次确认

### 限流与配额
- 复用 `system_config.ai_user_rate_limit`（与 assistant 共享额度）
- 单草稿重新生成 ≤ 5 次
- 单用户草稿总数 ≤ 500（超出 `400 QUOTA_EXCEEDED`）

### 导出
- **微信 HTML**：用 `markdown-it` 渲染后，通过样式内联器（`juice` 或自研）把 CSS 打进 `style` 属性
  - 代码块转为带背景色的 `<pre>`，因公众号不支持代码高亮，用等宽字体 + 浅灰背景
  - 表格转为图片提示（公众号表格支持差）或简化为列表
- **HTML**：完整文档，含 `<meta charset>` 与基础排版样式
- 文件名：`{事件标题前20字}_{platform}_{yyyyMMdd}.{ext}`，中文字符做 URL 编码

### 安全
- 所有草稿只能被创建者访问，`user_id` 取自 Token，越权返回 `404`
- Markdown 渲染必须 XSS 过滤（`rehype-sanitize`），禁止 `<script>` `<iframe>` 与 `javascript:` 协议
- 导出的 HTML 同样做过滤

### 数据保留
- 草稿永久保留（用户主动删除除外）
- `status=FAILED` 的草稿 7 天后自动清理

---

## 完成标准

- [ ] `creation_draft` 表与迁移完成
- [ ] 6 个平台 × 5 种风格的 prompt 模板 seed 完成，规格约束写入 Prompt
- [ ] SSE 流式生成完成，`start`/`outline`/`delta`/`done`/`error` 事件正确
- [ ] `outline` 先于正文返回，前端可提前渲染结构
- [ ] 上下文裁剪生效，token 不超预算
- [ ] 草稿 CRUD 完成，`content` 与 `contentEdited` 双轨保存
- [ ] 重新生成次数限制 + 覆盖二次确认生效
- [ ] 四种导出格式全部可用，微信 HTML 样式内联正确（实测粘贴到公众号编辑器格式不丢）
- [ ] 用户限流与草稿配额生效
- [ ] 越权访问返回 404
- [ ] 生成配置弹窗完成：平台卡片、风格选择、高级选项、成本预估
- [ ] 创作工作台完成：流式渲染、大纲导航、三视图切换、自动保存
- [ ] 微信预览手机 mockup 还原度良好
- [ ] 我的草稿页完成：筛选、卡片网格、快捷操作
- [ ] Markdown 渲染 XSS 过滤生效（含恶意输入测试）
- [ ] 单元测试：平台规格校验、上下文裁剪、导出格式转换、配额；覆盖率 ≥ 75%

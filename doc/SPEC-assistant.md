# AI 助手模块（assistant）

所属项目: @SPEC.md
模块状态: ✅ 已完成
一期范围: — 二期
最后更新: 2026-08-02

---

## 功能目标

在每个热点事件上提供 **「问 AI」** 能力。用户可以就当前事件追问，AI 基于该事件的
全部来源文章与分析结果作答，支持多轮对话与流式输出。

预置快捷问题：
- 为什么重要？
- 和 Claude / 我关注的技术有什么关系？
- 有什么创新？
- 适合学习吗？
- 是否值得写文章？
- 是否有商业价值？

**不是通用聊天机器人**——上下文严格限定在当前事件，超出范围时明确说明。

---

## 数据库设计

### `assistant_thread` 表

| 字段          | 类型         | 必填 | 说明                                          |
| ------------- | ------------ | ---- | --------------------------------------------- |
| id            | BIGSERIAL    | 是   | 主键                                          |
| user_id       | BIGINT       | 是   | 所属用户                                      |
| event_id      | BIGINT       | 是   | 关联事件                                      |
| title         | VARCHAR(200) | 是   | 会话标题（取首个问题前 50 字）                |
| message_count | SMALLINT     | 是   | 消息数，默认 0                                |
| total_cost_usd| NUMERIC(10,6)| 是   | 该会话累计费用，默认 0                        |
| last_message_at | TIMESTAMPTZ| 否   | 最后消息时间                                  |
| created_at    | TIMESTAMPTZ  | -    | 创建时间                                      |
| updated_at    | TIMESTAMPTZ  | -    | 更新时间                                      |
| is_deleted    | BOOLEAN      | -    | 逻辑删除，默认 false                          |

索引：`idx_thread_user_event(user_id, event_id, created_at DESC)`、`idx_thread_user_time(user_id, last_message_at DESC)`

> 同一用户对同一事件可以有多个会话（不同话题分开问）。

### `assistant_message` 表

| 字段              | 类型         | 必填 | 说明                                          |
| ----------------- | ------------ | ---- | --------------------------------------------- |
| id                | BIGSERIAL    | 是   | 主键                                          |
| thread_id         | BIGINT       | 是   | 所属会话                                      |
| role              | VARCHAR(32)  | 是   | `USER` / `ASSISTANT`                          |
| content           | TEXT         | 是   | 消息内容（Markdown）                          |
| quick_question_key| VARCHAR(64)  | 否   | 若来自快捷问题，记录其 key                    |
| citations         | JSONB        | 是   | 引用的来源文章 `[{"articleId":1024,"title":"..","url":".."}]`，默认 `[]` |
| model_alias       | VARCHAR(100) | 否   | ASSISTANT 消息使用的模型                      |
| prompt_tokens     | INTEGER      | 是   | 默认 0                                        |
| completion_tokens | INTEGER      | 是   | 默认 0                                        |
| cost_usd          | NUMERIC(10,6)| 是   | 默认 0                                        |
| latency_ms        | INTEGER      | 否   | 耗时                                          |
| status            | VARCHAR(32)  | 是   | `PENDING`/`STREAMING`/`DONE`/`FAILED`         |
| error_message     | VARCHAR(500) | 否   | 失败原因                                      |
| feedback          | VARCHAR(32)  | 否   | 用户反馈 `LIKE`/`DISLIKE`                     |
| created_at        | TIMESTAMPTZ  | -    | 创建时间                                      |
| updated_at        | TIMESTAMPTZ  | -    | 更新时间                                      |
| is_deleted        | BOOLEAN      | -    | 逻辑删除，默认 false                          |

索引：`idx_msg_thread(thread_id, created_at)`

---

## 快捷问题定义

存 `system_config.assistant_quick_questions`（JSON 数组），ADMIN 可增删改：

```json
[
  { "key": "why_important", "label": "为什么重要？",
    "question": "这件事为什么重要？它对行业意味着什么？" },
  { "key": "relation",      "label": "和我有什么关系？",
    "question": "这件事和 AI 应用开发者的日常工作有什么关系？会影响哪些技术选型？" },
  { "key": "innovation",    "label": "有什么创新？",
    "question": "这件事的技术创新点具体是什么？和已有方案相比强在哪？" },
  { "key": "worth_learn",   "label": "适合学习吗？",
    "question": "如果我想深入学习这个方向，应该从哪里入手？需要什么前置知识？" },
  { "key": "worth_write",   "label": "值得写文章吗？",
    "question": "这个话题适合写成公众号文章吗？切入角度可以是什么？" },
  { "key": "business",      "label": "有商业价值吗？",
    "question": "这件事有什么商业机会？独立开发者能做什么产品？" }
]
```

---

## 上下文构造

调用 `ai-engine` 的 `assistant_qa` 任务，注入变量：

| 变量            | 内容                                                             |
| --------------- | ---------------------------------------------------------------- |
| `eventTitle`    | 事件标题                                                         |
| `eventAnalysis` | `event_analysis` 的总结 + 核心观点 + 创新点（JSON 序列化）        |
| `articles`      | 全部来源文章：编号 + 标题 + 来源名 + 正文前 2000 字               |
| `history`       | 该会话最近 10 轮消息（超出则保留首轮 + 最近 8 轮）                |
| `question`      | 用户本次问题                                                     |

**上下文预算**：总输入 token ≤ `assistant_max_context_tokens`（默认 24000）。
超出时按以下顺序裁剪：
1. 缩短每篇文章正文（2000 → 1000 → 500 字）
2. 只保留权重最高的 5 篇文章
3. 压缩历史（只留首轮 + 最近 4 轮）

**引用要求**：System Prompt 要求 AI 在引述具体事实时用 `[1]` `[2]` 标注来源编号，
后端解析这些标注生成 `citations` 数组。

---

## 后端接口

### GET /api/v1/events/{eventId}/assistant/threads
**说明**: 我在该事件下的会话列表。需登录

**Response 200**:
```json
[
  { "id": 301, "title": "这件事为什么重要？", "messageCount": 4,
    "lastMessageAt": "2026-07-29T09:20:00Z", "createdAt": "2026-07-29T09:12:00Z" }
]
```

### POST /api/v1/events/{eventId}/assistant/threads
**说明**: 创建新会话（不发消息）

**Response 201**: `{ "id": 302, "title": "新对话", "messageCount": 0 }`

### GET /api/v1/assistant/threads/{threadId}/messages
**说明**: 会话消息列表。需登录且为本人

**Response 200**:
```json
[
  { "id": 1001, "role": "USER", "content": "这件事为什么重要？",
    "quickQuestionKey": "why_important", "createdAt": "2026-07-29T09:12:00Z" },
  { "id": 1002, "role": "ASSISTANT",
    "content": "这次发布的重要性主要体现在三点：\n\n1. **架构统一**[1]……",
    "citations": [
      { "index": 1, "articleId": 1024, "title": "Introducing GPT-5",
        "url": "https://openai.com/blog/gpt-5", "sourceName": "OpenAI Blog" }
    ],
    "modelAlias": "default-chat", "costUsd": 0.00412, "latencyMs": 6120,
    "status": "DONE", "feedback": null, "createdAt": "2026-07-29T09:12:08Z" }
]
```

---

### POST /api/v1/assistant/threads/{threadId}/messages
**说明**: 发送问题，**SSE 流式返回**。需登录

**Request Body**:
```json
{ "question": "这件事为什么重要？", "quickQuestionKey": "why_important" }
```
> 传 `quickQuestionKey` 时 `question` 可省略，由后端从配置取

**Response 200** — `Content-Type: text/event-stream`
```
event: start
data: {"messageId": 1002, "modelAlias": "default-chat"}

event: delta
data: {"content": "这次发布的"}

event: delta
data: {"content": "重要性主要体现在"}

event: citations
data: {"citations": [{"index":1,"articleId":1024,"title":"...","url":"..."}]}

event: done
data: {"messageId": 1002, "promptTokens": 8420, "completionTokens": 612, "costUsd": 0.00412, "latencyMs": 6120}
```

**错误事件**:
```
event: error
data: {"errorCode": "LLM_UNAVAILABLE", "detail": "所有模型均不可用，请稍后重试"}
```

**错误情况（HTTP 层）**:
- 会话不属于当前用户 → `404` `THREAD_NOT_FOUND`
- 超过用户限流 → `429` `AI_RATE_LIMIT_EXCEEDED`（`Retry-After` 头给出秒数）
- 问题为空且无 `quickQuestionKey` → `400` `QUESTION_REQUIRED`
- 问题超 1000 字 → `400` `QUESTION_TOO_LONG`
- 事件 `status != ANALYZED` → `409` `EVENT_NOT_ANALYZED`

---

### POST /api/v1/assistant/messages/{messageId}/feedback
**说明**: 对回答点赞/点踩

**Request Body**: `{ "feedback": "LIKE" }`（`LIKE`/`DISLIKE`/`null` 取消）

**Response 204**

### POST /api/v1/assistant/messages/{messageId}/regenerate
**说明**: 重新生成该回答（删除原回答，用相同上下文重新调用）。SSE 流式返回

**错误情况**: 非 ASSISTANT 消息 → `400` `NOT_ASSISTANT_MESSAGE`

### DELETE /api/v1/assistant/threads/{threadId}
**说明**: 删除会话（级联软删消息）
**Response 204**

### GET /api/v1/assistant/quick-questions
**说明**: 快捷问题列表。`GUEST` 可访问（用于前端展示，点击时才要求登录）

**Response 200**: 快捷问题数组

---

## 前端页面

### 问 AI 面板（事件详情页的右侧抽屉）

**入口**：事件详情页右上角「💬 问 AI」按钮 → 从右侧滑出宽 480px 的抽屉（移动端全屏）

**未登录态**：抽屉内显示快捷问题列表（灰化不可点）+ 「登录后即可提问」按钮

**抽屉布局**
```
┌────────────────────────────────────┐
│ 💬 问 AI                     ⟳  ✕ │  ← ⟳ 新建会话
│ 关于：OpenAI 发布 GPT-5…            │
├────────────────────────────────────┤
│ 会话: [为什么重要？ ▾]              │  ← 会话切换下拉，含历史会话
├────────────────────────────────────┤
│                                    │
│  ┌──────────────────────────────┐  │
│  │ 这件事为什么重要？          🧑│  │  ← 用户消息，右对齐
│  └──────────────────────────────┘  │
│                                    │
│ 🤖 这次发布的重要性主要体现在三点： │  ← AI 消息，Markdown 渲染
│                                    │
│    1. **架构统一** [1]              │  ← [1] 可点击，hover 显示来源卡片
│    2. **成本下降** [2][3]           │
│                                    │
│    ─────────────────────────       │
│    📎 引用来源                      │
│    [1] Introducing GPT-5 · OpenAI  │
│    [2] GPT-5 定价分析 · InfoQ      │
│                                    │
│    👍 👎  ⟳重新生成  📋复制         │
│    default-chat · 6.1s · $0.0041   │  ← 灰色小字
│                                    │
├────────────────────────────────────┤
│ 快捷提问：                          │
│ [为什么重要？][有什么创新？][+4]    │  ← Chips，横向滚动
├────────────────────────────────────┤
│ ┌────────────────────────────┐ 发送│
│ │ 输入你的问题…               │  ↑  │
│ └────────────────────────────┘     │
│ 本小时剩余 17/20 次                 │  ← 限流提示
└────────────────────────────────────┘
```

**交互细节**
- 快捷问题 Chips 点击即发送，发送后该 Chip 变灰（本会话内已问过）
- 流式输出：逐字追加 + 光标闪烁动画；输出中「发送」变「停止」按钮
- 停止：前端 `AbortController` 中断 SSE，后端保存已生成部分并标 `status=DONE`
- 引用标注 `[1]`：渲染为可点击上标，hover 弹出来源卡片（标题+来源+摘要），点击在新标签打开原文
- 消息底部工具条：👍👎（点击后高亮，可取消）、重新生成、复制 Markdown
- 输入框：Shift+Enter 换行，Enter 发送；字数计数（超 1000 变红）
- 限流剩余次数实时显示，剩余 0 时输入框禁用并提示恢复时间
- 网络错误：消息气泡内显示错误提示 + 「重试」按钮
- 会话切换：下拉列表显示历史会话（标题 + 时间），可删除

**移动端**：抽屉改为全屏 Sheet，快捷问题改为可横向滚动的一行

---

## 业务规则

### 上下文与成本
- 上下文严格限定当前事件，System Prompt 明确要求：
  - 只基于提供的来源材料回答，不编造
  - 材料中没有的信息，明确说"提供的资料中没有提到"
  - 引用具体事实时用 `[编号]` 标注
- 输入 token 超预算时按裁剪策略降级（见上方"上下文构造"）
- 每条 ASSISTANT 消息独立写 `ai_call_log`（`task_key=assistant_qa`，`target_type=EVENT`）
- `thread.total_cost_usd` 累加，会话超 `assistant_thread_cost_limit_usd`（默认 0.5）时禁止继续提问，提示「本次会话已达成本上限，请新建会话」

### 限流
- 用户级：`system_config.ai_user_rate_limit`（默认 20 次/小时），Redis 滑动窗口
- 会话级：单会话最多 30 轮（超出提示新建会话）
- 触发限流返回 `429` + `Retry-After`

### 流式实现
- FastAPI `StreamingResponse` + SSE 协议
- 消息在 `start` 事件时就落库（`status=STREAMING`），逐块更新 `content`（每 2 秒或每 200 字符落一次盘，避免频繁写库）
- 客户端断连（`request.is_disconnected()`）→ 保存已生成内容，标 `DONE`，记录 `latency_ms`
- LLM 全链失败 → 发 `error` 事件，消息标 `FAILED`，不计费（若已产生部分 token 则按实际计费）
- Nginx / 反向代理需配 `proxy_buffering off` 保证流式不被缓冲

### 引用解析
- AI 输出中的 `[n]` 对应传入 `articles` 列表的第 n 篇
- 后端在流结束后解析全文中出现的所有 `[n]`，去重后生成 `citations`
- 越界编号（如 `[9]` 但只有 5 篇）直接丢弃，不报错

### 权限与隔离
- 所有会话/消息接口只操作当前用户自己的数据，`user_id` 取自 Token
- 越权访问返回 `404`（不暴露存在性）
- `GUEST` 只能读快捷问题列表，不能创建会话

### 数据保留
- 会话与消息保留 180 天，超期由 `cleanup_task` 软删除
- 用户可主动删除会话

---

## 完成标准

- [ ] `assistant_thread` / `assistant_message` 表与迁移完成
- [ ] `assistant_qa` prompt 模板 seed 完成，含引用标注与不编造要求
- [ ] 上下文构造与三级裁剪策略生效，token 不超预算
- [ ] SSE 流式接口完成，`start`/`delta`/`citations`/`done`/`error` 五种事件正确
- [ ] 客户端断连时已生成内容正确保存
- [ ] 引用解析正确，越界编号被丢弃
- [ ] 用户限流 + 会话轮数上限 + 会话成本上限三重保护生效
- [ ] 点赞/点踩、重新生成、删除会话接口完成
- [ ] 每条回答写 `ai_call_log`，成本累加到 thread
- [ ] 越权访问返回 404
- [ ] 问 AI 抽屉完成：流式渲染、快捷问题 Chips、会话切换、停止生成
- [ ] 引用上标可点击、hover 显示来源卡片
- [ ] 限流剩余次数实时显示，触顶时禁用输入
- [ ] 移动端全屏 Sheet 适配
- [ ] 单元测试：上下文裁剪、引用解析、限流、断连保存；覆盖率 ≥ 75%

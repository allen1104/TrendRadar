# Assistant 模块（二期）

> AI 助手（问 AI）。在每个热点事件上提供「问 AI」能力：多轮对话、SSE 流式输出、引用解析、快捷问题。
>
> 需求：[doc/SPEC-assistant.md](../../../doc/SPEC-assistant.md)

## 状态

✅ 已完成 · 2026-08-02

## 模块文件

```
app/modules/assistant/
  __init__.py        module marker
  enums.py           MessageRole (USER/ASSISTANT) + MessageStatus (PENDING/STREAMING/DONE/FAILED) + Feedback (LIKE/DISLIKE)
  exceptions.py      9 个业务异常（404 / 400 / 409 / 429）
  model.py           AssistantThread + AssistantMessage（含 JSONB citations）
  schema.py          10 个 DTO（请求 / 响应 / 流式事件 5 种）
  repository.py      Thread/Message Repository（含 soft_delete_cascade / incremental_update）
  service.py         AssistantService + 纯函数（build_context / trim_context / parse_citations / parse_quick_questions）
  api.py             events_assistant_router + threads_router，2 个 SSE 流式接口
  tasks.py           assistant.cleanup_old_threads (04:30, 软删 180 天前)
  README.md
```

## 接口清单（8 个）

| 方法 | 路径 | 说明 | 错误码 |
|------|------|------|--------|
| `GET /api/v1/events/{event_id}/assistant/threads` | 列表（登录） | — |
| `POST /api/v1/events/{event_id}/assistant/threads` | 创建空 thread（登录） | `409 EVENT_NOT_ANALYZED` |
| `GET /api/v1/assistant/threads/{thread_id}/messages` | 消息列表（登录本人） | `404 THREAD_NOT_FOUND` |
| `POST /api/v1/assistant/threads/{thread_id}/messages` | **SSE 流式** | `400 QUESTION_REQUIRED` / `400 QUESTION_TOO_LONG` / `404 THREAD_NOT_FOUND` / `409 EVENT_NOT_ANALYZED` / `429 AI_RATE_LIMIT_EXCEEDED` / `429 THREAD_TURN_LIMIT_EXCEEDED` / `429 THREAD_COST_LIMIT_EXCEEDED` |
| `POST /api/v1/assistant/messages/{message_id}/regenerate` | **SSE 流式** 重新生成 | `400 NOT_ASSISTANT_MESSAGE` |
| `POST /api/v1/assistant/messages/{message_id}/feedback` | 点赞/点踩 | `400 NOT_ASSISTANT_MESSAGE` |
| `DELETE /api/v1/assistant/threads/{thread_id}` | 删会话（级联软删 message） | `404 THREAD_NOT_FOUND` |
| `GET /api/v1/assistant/quick-questions` | 快捷问题（GUEST 可访问） | — |

## SSE 协议（5 种事件）

```
event: start
data: {"messageId": 1002, "modelAlias": "default-chat"}

event: delta
data: {"content": "这次发布的"}

event: citations
data: {"citations": [{"index":1,"articleId":1024,"title":"...","url":"...","sourceName":"..."}]}

event: done
data: {"messageId": 1002, "promptTokens": 8420, "completionTokens": 612, "costUsd": 0.00412, "latencyMs": 6120}

event: error
data: {"errorCode": "LLM_UNAVAILABLE", "detail": "所有模型均不可用"}
```

HTTP 头：`Content-Type: text/event-stream` + `Cache-Control: no-cache, no-transform` + `X-Accel-Buffering: no`。

## 上下文三级裁剪

总输入 token 超 `assistant_max_context_tokens`（默认 24000）时按 SPEC 顺序降级：

1. **缩短每篇 content**（2000 → 1000 → 500 字符）
2. **只保留权重最高的 5 篇**（按 `source.weight + content.length` 排序）
3. **压缩历史**（保留首轮 + 最近 4 轮）

token 估算：英文 `len/4`、中文 `len/1.5`（粗略够用）。

## 引用解析

AI 输出中的 `[n]` 标注对应 prompt 变量 `articles` 列表的第 n 项：
- 提取 → 去重 → 越界丢弃 → 生成 `{index, articleId, title, url, sourceName}`
- 仅在流结束（done 事件前）发送 `citations` 事件

## 三重限流

| 层级 | 上限 | 实现 |
|------|------|------|
| 用户级 | `ai_user_rate_limit`（默认 20/h） | Redis 滑动窗口 `INCR + EXPIRE 3600` |
| 会话轮数 | 硬编码 30 轮 | DB count `role=ASSISTANT AND status=DONE` |
| 会话成本 | `assistant_thread_cost_limit_usd`（默认 0.5 USD） | DB 读 `thread.total_cost_usd` |

触发限流 → `429` + `Retry-After` 头。Redis 故障 → 降级放行（避免单点故障把问 AI 拖死）。

## 关键业务规则

1. **流式中断保护**：`provider.stream_chat` 每个 chunk 之前探测 `request.is_disconnected()`，断连则 break + 标 DONE（已生成部分保留）
2. **每 200 字符 / 2 秒刷盘**：避免高频 IO；流结束 / 断连时全量写一次终态
3. **ai_call_log 自动记账**：每条 ASSISTANT 消息写 `task_key=assistant_qa, target_type=EVENT`，失败只 log 不抛
4. **thread cost 累加**：流结束时 `thread.total_cost_usd += cost_usd`，超限时禁止继续
5. **轮次计数**：只统计 `status=DONE` 的 ASSISTANT 消息（半成品不计入）
6. **快捷问题可配置**：存在 `system_config.assistant_quick_questions` JSON，ADMIN 可改；key 唯一
7. **client 越权防护**：`get_for_user` 在 repo 层强制 user_id 过滤，越权 → 404（不暴露存在性）

## 与其他模块的关系

- **ai.gateway**：复用 `_get_active_prompt` / `_get_model_by_alias` / `_build_provider` + 新增 `provider.stream_chat` 流式接口；prompt `assistant_qa` seed 完成
- **ai.providers.openai_compatible**：新增 `stream_chat(request) -> AsyncIterator[str]`，使用 `stream_options.include_usage` 取 token
- **pipeline.model.Event / Article / EventArticle / Source**：构造 context 时跨模块 join
- **ai.model.EventAnalysis**：摘要 + 核心观点 + 创新点拼装进 `eventSummary`
- **admin.configs**：`assistant_max_context_tokens` / `assistant_thread_cost_limit_usd` / `assistant_quick_questions` 3 项（seed 已加）
- **admin.enums.TargetType**：加 `ASSISTANT_THREAD` / `ASSISTANT_MESSAGE`
- **admin.enums.AuditAction**：加 `ASSISTANT_THREAD_CREATE` / `THREAD_DELETE` / `MESSAGE_CREATE` / `MESSAGE_REGENERATE` / `MESSAGE_FEEDBACK`

## 不在 MVP 范围（SPEC 列但本期末做）

- ❌ 多模型降级链（流式场景下中途切换模型语义不清；仅主模型）
- ❌ markdown fence 处理（普通文本输出，不要求 JSON）
- ❌ 历史压缩的智能摘要（保留首末，中间的历史消息原样保留）
- ❌ 异步 ai_call_log 写（写失败只 log，不阻塞主流程）
- ❌ 引用上标在内容中位置保留（解析时只保留 articleId 等元数据，渲染由前端处理）
- ❌ 快捷问题 ADMIN 在线编辑 UI（API 走 system_config，但本期前端无对应页面）
- ❌ thread rename / 自动 rename（仅在 title 为「新对话」时自动用首问前 50 字）

## 验证状态

| 时间 | 验证项 | 结果 |
|------|--------|------|
| 2026-08-02 | Alembic migration `20260802_0008_assistant_tables.py` | 2 张表创建成功 |
| 2026-08-02 | OpenAPI: 8 个端点注册到 `/api/v1/{events/assistant,assistant}` | ✅ |
| 2026-08-02 | `ruff check app/modules/assistant/` | All checks passed |
| 2026-08-02 | 单测（test_enums 7 + test_service 46 + test_api 14） | 67 passed |
| 2026-08-02 | 全栈无回归 | 439 passed |
| 2026-08-02 | `pnpm typecheck` | exit 0 |
| 2026-08-02 | `pnpm build` | 1.82 MB / 585 KB gzip |
# Creation 模块（二期）

> 内容创作（按 SPEC-creation.md）：6 平台 × 5 风格 = 30 个 Prompt 模板，
> SSE 流式生成（outline 先于正文）、Markdown 编辑、4 种格式导出（Markdown / HTML / 微信 HTML / TXT）。

## 状态

✅ 已完成 · 2026-08-02

## 模块文件

```
app/modules/creation/
  __init__.py         module marker
  enums.py            Platform (6) + Style (5) + DraftStatus (3) + ExportFormat (4)
  exceptions.py       9 个业务异常（404/400/409）
  model.py            CreationDraft（含 JSONB outline / content_edited 双轨）
  schema.py           12 个 DTO（含 SSE 5 事件 payload）
  repository.py       CreationDraftRepository（分页 + 模糊搜索 + 事件批量查）
  service.py          CreationService + 纯函数（build_context / parse_outline / count_words /
                      render_markdown / render_html / render_wechat_html / render_plain_text /
                      sanitize_html_for_storage / _split_metadata / sanitize_filename）
  api.py              router，7 个端点（2 SSE 流式 + 4 格式导出）
  tasks.py            creation.cleanup_failed_drafts（03:30，软删 7 天前 FAILED）
  README.md
```

## 接口清单（7 个）

| 方法 | 路径 | 说明 | 错误码 |
|------|------|------|--------|
| `GET /api/v1/creation/options` | 平台与风格选项（GUEST 可访问） | — |
| `POST /api/v1/creation/drafts` | **SSE 流式** 生成 | `400 INVALID_PLATFORM/INVALID_STYLE/TARGET_WORDS_OUT_OF_RANGE` / `409 EVENT_NOT_ANALYZED` / `429 AI_RATE_LIMIT_EXCEEDED` / `400 QUOTA_EXCEEDED` |
| `GET /api/v1/creation/drafts` | 我的草稿列表（分页） | — |
| `GET /api/v1/creation/drafts/{id}` | 草稿详情（仅本人） | `404 DRAFT_NOT_FOUND` |
| `PATCH /api/v1/creation/drafts/{id}` | 保存编辑（title / content_edited） | `404 DRAFT_NOT_FOUND` |
| `DELETE /api/v1/creation/drafts/{id}` | 软删（仅本人） | `404 DRAFT_NOT_FOUND` |
| `POST /api/v1/creation/drafts/{id}/regenerate` | **SSE 流式** 重新生成 | `400 TOO_MANY_REGENERATIONS` / `400 INVALID_STYLE` / `404 DRAFT_NOT_FOUND` |
| `GET /api/v1/creation/drafts/{id}/export?format=` | 导出 4 格式 | `400 INVALID_EXPORT_FORMAT`（Pydantic 422）/ `404 DRAFT_NOT_FOUND` |

## SSE 协议（5 事件）

```
event: start
data: {"draftId": 701, "modelAlias": "default-chat"}

event: outline
data: {"outline": [{"heading":"一、发布了什么","points":["核心参数","定价变化"]}]}

event: delta
data: {"content": "## 一、发布了什么\n\n"}

event: done
data: {"draftId": 701, "title": "GPT-5 深度解读...", "wordCount": 2480,
       "coverSuggestion": "...", "tagsSuggestion": ["GPT-5","OpenAI","大模型"],
       "costUsd": 0.0182, "latencyMs": 28400}

event: error
data: {"errorCode": "LLM_UNAVAILABLE", "detail": "所有模型均不可用"}
```

HTTP 头：`Content-Type: text/event-stream` + `Cache-Control: no-cache, no-transform` + `X-Accel-Buffering: no`。

## 上下文三级裁剪

总输入 token 超 `creation_max_context_tokens`（默认 20000）时按 SPEC 顺序降级：

1. **缩短每篇 content**（1500 → 800 → 400 字符）
2. **只保留权重最高的 6 篇**（SPEC：最多 6 篇，比 assistant 多）
3. 历史由 build_context 内部不传（content 优先）

token 估算：英文 `len/4`、中文 `len/1.5`（粗略够用）。

## 输出解析约定

AI 输出的格式约定（写入 prompt + 由 `_split_metadata` 解析）：

```
# 标题
COVER: 一段封面描述
TAGS: tag1, tag2, tag3

## 正文 Markdown 第一段
...
```

提取后写回 `draft.title` / `cover_suggestion` / `tags_suggestion`，
正文写入 `draft.content`，大纲由 outline 事件单独发送。

## 平台与风格矩阵

| | WECHAT | BLOG | WEIBO | XHS | ZHIHU | MARKDOWN |
|--|--------|------|-------|-----|-------|----------|
| 字数 | 1500-3000 | 2000-4000 | 60-140 | 300-600 | 800-2000 | 1000-3000 |
| TECHNICAL | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| MARKETING | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| DEEP_DIVE | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| NEWS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CASUAL | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

`targetWords` 校验：超出该平台 `[lo, hi]` 范围 ±50% → `400 TARGET_WORDS_OUT_OF_RANGE`。

## 三重保护

| 层级 | 上限 | 实现 |
|------|------|------|
| 用户级 | `ai_user_rate_limit`（默认 20/h） | Redis 滑动窗口 `INCR + EXPIRE 3600` |
| 单用户草稿数 | `DRAFT_QUOTA_PER_USER=500` | DB count，超限 → `400 QUOTA_EXCEEDED` |
| 重新生成次数 | `REGENERATE_LIMIT=5` | DB 字段 `regenerate_count`，超限 → `400 TOO_MANY_REGENERATIONS` |

触发限流 → `429` + `Retry-After` 头。Redis 故障 → 降级放行。

## 导出 4 格式

| format | content-type | 关键处理 |
|--------|-------------|----------|
| `MARKDOWN` | text/markdown | 原样输出 |
| `TXT` | text/plain | 去掉 markdown 标记（**bold** / `code` / [link](url)） |
| `HTML` | text/html | 完整 HTML 文档 + 内置样式 + XSS 过滤（去 `<script>` / `javascript:` / `onerror=`） |
| `WECHAT_HTML` | text/html | **所有样式写到 `style` 属性**（公众号编辑器剥离 `<style>`）；代码块转 `<pre>`；表格简化为列表 |

文件名：`{事件标题前20字(去非法字符)}_{yyyymmdd}.{ext}`

## 关键业务规则

1. **流式中断保护**：`provider.stream_chat` 每个 chunk 之前探测 `request.is_disconnected()`，断连则 break + 标 DONE（已生成部分保留）
2. **每 200 字符 / 2 秒刷盘**：避免高频 IO；流结束 / 断连时全量写一次终态
3. **ai_call_log 自动记账**：每条创建写 `task_key=creation_draft, target_type=EVENT, target_id=event_id`，失败只 log 不抛
4. **content vs contentEdited 双轨**：
   - `content` 保存 AI 原始输出，**永不被用户编辑覆盖**
   - `contentEdited` 是用户编辑后正文；为空时导出与预览回退用 `content`
   - "恢复 AI 原稿"按钮：清空 `contentEdited`
5. **重新生成计数**：`regenerate_count` 单调递增；前端显示 `(regenerateRemaining/5)`
6. **client 越权防护**：`repo.get_for_user` 在 repo 层强制 user_id 过滤，越权 → 404（不暴露存在性）
7. **XSS 过滤**：导出 HTML / Markdown 渲染前端统一走 `rehype-sanitize` + 服务端 `sanitize_html_for_storage`
8. **Celery 清理**：每日 03:30 软删 `status=FAILED` 且超过 7 天的 draft（防止永久残留）

## 与其他模块的关系

- **ai.gateway**：复用 `_get_active_prompt` / `_build_chain` / `_get_model_by_alias` / `_build_provider` + 新增 `provider.stream_chat` 流式接口
- **ai.providers.openai_compatible**：已有 `stream_chat(request) -> AsyncIterator[str]`（assistant 模块添加）
- **ai.enums.TaskKey**：新增 6 个 `CREATION_WECHAT/BLOG/WEIBO/XHS/ZHIHU/MARKDOWN`
- **pipeline.model.Event / Article / EventArticle / Source**：构造 context 时跨模块 join（最多 6 篇，每篇前 1500 字）
- **ai.model.EventAnalysis**：summary + key_points + innovations + summary_one_line 拼装进 `eventAnalysis`
- **admin.configs**：`creation_max_context_tokens`（seed 已加，默认 20000）
- **admin.enums.TargetType**：加 `CREATION_DRAFT`
- **admin.enums.AuditAction**：加 5 个 `CREATION_DRAFT_CREATE/UPDATE/DELETE/REGENERATE/EXPORT`

## 不在 MVP 范围（SPEC 列但本期末做）

- ❌ 多模型降级链（流式场景下中途切换模型语义不清；仅主模型）
- ❌ markdown fence 处理（普通文本输出，不要求 JSON）
- ❌ 历史压缩的智能摘要（content 优先，不依赖 history）
- ❌ 异步 ai_call_log 写（写失败只 log，不阻塞主流程）
- ❌ 草稿配额与 regenerate 计数走 Redis（DB 字段足够）
- ❌ 微信预览的字符级精度（后端 `render_wechat_html` 已实现；前端简版 `_inline` 近似）
- ❌ 封面图上传 / 自动生成（仅建议描述）
- ❌ 编辑器 CodeMirror 6（用 `<textarea>` 简化；Markdown 高亮下一期）
- ❌ 拖拽排序 / 封面图 / 右键菜单（与 collection 同样的「跳过」决定）

## 验证状态

| 时间 | 验证项 | 结果 |
|------|--------|------|
| 2026-08-02 | Alembic migration `20260802_0009_creation_tables.py` | 1 张表创建成功 |
| 2026-08-02 | OpenAPI: 7 个端点注册到 `/api/v1/creation/*` | ✅ |
| 2026-08-02 | `ruff check app/modules/creation/` | All checks passed |
| 2026-08-02 | 单测（test_enums 9 + test_service 58 + test_api 22） | 89 passed |
| 2026-08-02 | 全栈无回归 | 528 passed |
| 2026-08-02 | `pnpm typecheck` | exit 0 |
| 2026-08-02 | `pnpm build` | 1.85 MB / 590 KB gzip |
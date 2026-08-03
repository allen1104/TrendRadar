# Report 模块（二期）

> 日报中心（按 SPEC-report.md）：4 类日报（AI / TECH / GITHUB / AGENT）+ AI 编排 + 4 格式导出 + RSS + 订阅推送。

## 状态

✅ 已完成 · 2026-08-02

## 模块文件

```
app/modules/report/
  __init__.py         module marker
  enums.py            ReportType (4) + ReportStatus (4) + ExportFormat (4)
                      + SubscriptionChannel (3) + 4 张静态配置表
                      (REPORT_MIN_ITEMS / MAX_ITEMS / SECTIONS / FILTER_SQL)
  exceptions.py       8 个业务异常（含 CandidatesInsufficientError 候选不足）
  model.py            Report / ReportItem / ReportSubscription 三表
  schema.py           17 个 DTO（含 Pydantic ReportStructure 编排 schema）
  repository.py       3 个 Repository（Report / ReportItem / ReportSubscription）
  service.py          ReportService + 纯函数（build_candidate_briefs /
                      render_content_md / render_html_doc / render_wechat_html /
                      render_plain_text / build_rss / _sanitize_inline_style /
                      sanitize_filename / estimate_tokens）+ 编排 Pydantic
                      schema（OrchItem / OrchSection / ReportStructure）
  api.py              router + admin_router，14 个端点
  tasks.py            report.generate_daily_reports（每日 08:00 并行生成 4 类）
  README.md
```

## 接口清单（14 个）

| 方法 | 路径 | 说明 | 错误码 |
|------|------|------|--------|
| `GET /api/v1/reports` | 日报列表（GUEST 只看 PUBLISHED） | `400 INVALID_REPORT_TYPE` |
| `GET /api/v1/reports/latest` | 各类型最新一期 | — |
| `GET /api/v1/reports/rss` | RSS 2.0 XML（公开 + token 私有） | `404 REPORT_NOT_FOUND`（token 无效） |
| `GET /api/v1/reports/{id}` | 详情（view_count 10 分钟同 IP 去重） | `404 REPORT_NOT_FOUND` |
| `GET /api/v1/reports/{id}/export?format=` | 导出（Markdown/HTML/PDF/WECHAT_HTML） | `400 INVALID_EXPORT_FORMAT` / `404` |
| `GET /api/v1/reports/subscription` | 我的订阅 | — |
| `PUT /api/v1/reports/subscription` | 保存订阅 | `400 WEBHOOK_URL_REQUIRED` |
| `POST /api/v1/reports/subscription/rss-token/reset` | 重置 RSS 令牌 | — |
| `POST /api/v1/admin/reports/generate` | 手动生成（EDITOR） | `409 REPORT_ALREADY_EXISTS` / `200 skipped`（候选不足） |
| `PATCH /api/v1/admin/reports/{id}` | 编辑日报 | — |
| `POST /api/v1/admin/reports/{id}/publish` | 发布 | `400 REPORT_ALREADY_PUBLISHED` / `400 REPORT_HAS_NO_ITEMS` |
| `POST /api/v1/admin/reports/{id}/unpublish` | 撤回（ADMIN） | `403 ADMIN_ONLY` |
| `PATCH /api/v1/admin/reports/{id}/items/{itemId}` | 编辑条目 | — |
| `DELETE /api/v1/admin/reports/{id}/items/{itemId}` | 删除条目 | `404 REPORT_ITEM_NOT_FOUND` |
| `POST /api/v1/admin/reports/{id}/items` | 添加条目 | — |

## 生成流程（按 SPEC §生成流程）

```
[Cron 每日 08:00（可配 report_generate_cron）]
  │
  ▼
① 选题  ReportService.select_candidates(report_type, report_date)
   SELECT ANALYZED + 非 hidden + last_seen_at 当日事件
   GITHUB 类型额外 EXISTS JOIN source.category='CODE'
   候选池不足 REPORT_MIN_ITEMS → 跳过当日
  │
  ▼
② AI 编排  ReportService._orchestrate(report_type, candidates)
   LLMGateway.call(task_key='report_daily', response_schema=ReportStructure)
   PydanticAI 强 schema：title / intro / outro / sections[*]/items[*]
   越界 eventId 自动丢弃
  │
  ▼
③ 渲染  ReportService.render_content_md(structure)
   sections → Markdown（h1 / 引用 / 板块 / 条目 / 头条角标 / hr / outro）
  │
  ▼
④ 落库 + audit
   status = auto_publish ? PUBLISHED : DRAFT
  │
  ▼
⑤ 发布推送（仅 PUBLISHED）
   ReportService._notify_publish(report_id)
   按 subscription.channel 分发：WEBHOOK（httpx + 3 次重试）/ EMAIL（日志占位）/ SITE
```

## 导出 4 格式

| format | 关键处理 |
|--------|---------|
| `MARKDOWN` | contentEdited 优先，否则 contentMd |
| `HTML` | `_md_to_simple_html` + `_sanitize_inline_style`（去 `<script>` / `on*=` / `javascript:`） + 内置 `<style>` |
| `WECHAT_HTML` | 所有样式写到 `style=` 属性（公众号剥离 `<style>` `<script>`） |
| `PDF` | weasyprint 渲染 → HTML 渲染；不可用时降级返回 HTML |

文件名：`{title前20字(去非法字符)}_{yyyymmdd}.{ext}`

## RSS XML 结构

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>TrendRadar 日报</title>
    <link>/reports</link>
    <description>AI 自动生成的科技热点日报</description>
    <language>zh-CN</language>
    <lastBuildDate>...</lastBuildDate>
    <item>
      <title>AI 日报 · 2026-08-02</title>
      <link>/reports/42</link>
      <guid isPermaLink="false">report-42</guid>
      <pubDate>...</pubDate>
      <description>🔥 [头条] OpenAI GPT-5 ...</description>
      <category>AI</category>
    </item>
  </channel>
</rss>
```

- 公开源：无 token 返回所有已发布日报
- 私有源：带 token 按 subscription.report_types 过滤
- 包含最近 30 期

## 视图计数去重

读 `GET /reports/{id}` 时 `view_count + 1`；Redis `report:view:{id}:{ip}` 10 分钟内同 IP 只计一次（失败降级放行）。

## 推送渠道

| channel | 行为 |
|---------|------|
| `SITE` | 一期占位：写日志 + 推送计数 +1；前端通过 `/reports/latest` 轮询 |
| `EMAIL` | 一期 SMTP 未实现，log 记录占位 |
| `WEBHOOK` | httpx POST payload（json），超时 10s，3 次重试，仅 5xx 重试 |

仅推送 `subscription.enabled=true` 且 `report_type ∈ subscription.report_types` 的订阅者；WEBHOOK URL 必填在 put 时校验（`WEBHOOK_URL_REQUIRED`）。

## 关键业务规则

1. **同日同类型唯一**：DB 唯一约束 `uk_report_type_date(report_type, report_date)`；`force=true` 才允许覆盖
2. **候选池不足跳过**：返回 `200 {skipped:true, detail}` 而非错误（便于 UI 区分）
3. **越界 eventId 丢弃**：AI 返回的 sections.items 中 eventId 不在候选池 → 不入库
4. **编排 schema 强约束**：`ReportStructure` Pydantic 模型 → gateway response_schema → 解析失败重试
5. **contentMd vs contentEdited 双轨**：导出与展示优先 `contentEdited`，便于 EDITOR 微调不丢原稿
6. **view_count 去重**：Redis 10 分钟同 IP 只计一次（避免刷新刷量）
7. **unpublish 仅 ADMIN**：EDITOR 撤回触发 `403 ADMIN_ONLY`
8. **越界订阅 channel**：未在 enum 内 → service 校验抛 `InvalidReportTypeError`
9. **敏感字段脱敏**：Webhook payload 不包含 apiKey 等敏感数据
10. **idempotent**：候选池不足重试仍返回 skipped；force 重跑会清空旧 items

## 与其他模块的关系

- **ai.gateway**：复用 `LLMGateway.call(response_schema=ReportStructure)` + `_get_active_prompt` + `_build_chain` + `_get_model_by_alias` + `_build_provider`
- **ai.enums.TaskKey**：新增 `report_daily`（seed v1）
- **pipeline.model.Event**：选题 SQL 与 view 详情的事件信息加载
- **admin.configs**：`report_generate_cron` / `report_auto_publish` / `report_min_items` / `report_max_items` / `report_webhook_timeout` / `report_webhook_retries`（seed 已加）
- **admin.enums.TargetType**：加 `REPORT` / `REPORT_ITEM` / `REPORT_SUBSCRIPTION`
- **admin.enums.AuditAction**：加 7 个 `REPORT_GENERATE` / `REPORT_UPDATE` / `REPORT_PUBLISH` / `REPORT_UNPUBLISH` / `REPORT_ITEM_CREATE` / `REPORT_ITEM_UPDATE` / `REPORT_ITEM_DELETE`

## 不在 MVP 范围（SPEC 列但本期末做）

- ❌ 邮件 SMTP（仅日志占位）
- ❌ Webhook 失败 5 次自动禁用订阅（一期仅重试 + 日志）
- ❌ PDF 异步生成 + 缓存（同步 weasyprint；不可用时降级 HTML）
- ❌ 手动生成异步化（直接同步；前端需等待 LLM 完成）
- ❌ 阅读页右侧目录导航 / 阅读进度条
- ❌ 板块拖拽排序 + 实时预览（编辑器 UI 简化）
- ❌ 「+ 添加事件」Combobox 弹窗（API 暴露，前端留作下一期）
- ❌ 站内通知机制（SITE 推送占位）
- ❌ 同一 IP 跨日报的去重（仅单条 10 分钟去重）
- ❌ 日报 CSV 导出

## 验证状态

| 时间 | 验证项 | 结果 |
|------|--------|------|
| 2026-08-02 | Alembic migration `20260802_0010_report_tables.py` | 3 张表创建成功 |
| 2026-08-02 | OpenAPI: 14 端点注册到 `/api/v1/reports/*` + `/api/v1/admin/reports/*` | ✅ |
| 2026-08-02 | `report_daily` prompt + 6 项系统配置 seed | ✅ |
| 2026-08-02 | `ruff check app/modules/report/` | All checks passed |
| 2026-08-02 | 单测（test_enums 21 + test_service 38 + test_api 30） | 89 passed |
| 2026-08-02 | 全栈无回归 | 617 passed |
| 2026-08-02 | `pnpm typecheck` | exit 0 |
| 2026-08-02 | `pnpm build` | 1.86 MB / 594 KB gzip |
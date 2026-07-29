# TrendRadar 趋势雷达 — 需求总览

最后更新: 2026-07-29
项目状态: 设计完成，一期开发中

---

## 系统概述

TrendRadar 是一套 **AI 驱动的全球科技热点发现平台**。

它不是 RSS 阅读器，也不是新闻聚合器。核心理念是：
> 不是帮助用户看新闻，而是帮助用户发现趋势。

系统每天自动从全球与国内 20+ 科技信息源采集内容，经过清洗、去重聚合、AI 分析评分，
把散落在多个来源的同一件事收敛成 **一个热点事件**，并给出价值判断，
帮助 AI 开发者 / 技术作者 / 独立开发者快速找到值得深入研究和创作的话题。

**技术形态**：前后端分离，React 19 + Vite（SPA） / FastAPI + Celery（Python 3.12），
PostgreSQL 17 + pgvector + Redis，Docker Compose 一键部署，多用户 SaaS。

---

## 角色定义

| 角色      | 标识     | 说明                                                                       |
| --------- | -------- | -------------------------------------------------------------------------- |
| 游客      | `GUEST`  | 未登录。只读浏览公开热点榜单与事件详情；收藏、问 AI、创作等功能需登录       |
| 普通用户  | `USER`   | 浏览/搜索/过滤/排序热点、收藏、稍后读、问 AI、生成创作稿、订阅日报          |
| 编辑/运营 | `EDITOR` | USER 全部权限 + 置顶/隐藏事件、编辑事件内容与聚合关系、审核发布日报、手动重跑采集与分析 |
| 管理员    | `ADMIN`  | EDITOR 全部权限 + 采集源与插件管理、AI 模型与 Prompt 配置、任务调度、用户管理、成本统计 |

权限模型：**单角色 RBAC**（`user.role` 单值），权限自上而下包含：
`GUEST < USER < EDITOR < ADMIN`。后端用 `require_role(min_role)` 依赖统一校验。

---

## 模块列表

| #    | 模块         | 文件                      | 一期 | 状态       | 依赖                          |
| ---- | ------------ | ------------------------- | ---- | ---------- | ----------------------------- |
| 1    | 认证与权限   | @doc/SPEC-auth.md         | ✅    | ⏳ 未开始   | 无                            |
| 2    | 采集源与插件 | @doc/SPEC-source.md       | ✅    | ⏳ 未开始   | auth                          |
| 3    | 清洗与去重   | @doc/SPEC-pipeline.md     | ✅    | ⏳ 未开始   | source, ai-engine             |
| 4    | AI 引擎      | @doc/SPEC-ai-engine.md    | ✅    | ⏳ 未开始   | auth                          |
| 5    | 热点中心     | @doc/SPEC-hotspot.md      | ✅    | ⏳ 未开始   | pipeline, ai-engine, auth     |
| 6    | 管理后台     | @doc/SPEC-admin.md        | ✅    | ⏳ 未开始   | auth, source, ai-engine       |
| 7    | 收藏系统     | @doc/SPEC-collection.md   | —    | ⏳ 未开始   | hotspot, auth                 |
| 8    | 趋势分析     | @doc/SPEC-trend.md        | —    | ⏳ 未开始   | pipeline, hotspot             |
| 9    | AI 助手      | @doc/SPEC-assistant.md    | —    | ⏳ 未开始   | hotspot, ai-engine            |
| 10   | 内容创作     | @doc/SPEC-creation.md     | —    | ⏳ 未开始   | hotspot, ai-engine            |
| 11   | 日报中心     | @doc/SPEC-report.md       | —    | ⏳ 未开始   | hotspot, ai-engine, trend     |

状态图例：`⏳ 未开始` / `🔄 开发中` / `✅ 已完成`
"一期" 列打 ✅ 的是 MVP 范围，其余模块本文档已完整定义需求，实现排在二期。

---

## 模块关系图

```
                          ┌──────────────┐
                          │     auth     │  用户 / 角色 / JWT
                          └──────┬───────┘
                                 │ 为所有模块提供身份与权限
   ┌─────────────────────────────┼─────────────────────────────┐
   │                             │                             │
┌──▼───────┐   article    ┌──────▼───────┐   event      ┌──────▼───────┐
│  source  ├─────────────►│   pipeline   ├─────────────►│   hotspot    │
│ 采集插件 │              │ 清洗/去重聚合 │              │ 榜单/搜索/详情│
└──────────┘              └──────┬───────┘              └──┬────┬───┬──┘
                                 │ 调用 embedding          │    │   │
                          ┌──────▼───────┐                 │    │   │
                          │  ai-engine   │◄────────────────┘    │   │
                          │ LLM网关/Prompt│  分析·问答·创作·日报  │   │
                          └──────┬───────┘◄─────────┬──────┬────┘   │
                                 │                  │      │        │
                    ┌────────────┼──────────┐  ┌────▼───┐ ┌▼──────┐ ├─────────┐
                    │            │          │  │assistant│ │creation│ │collection│
              ┌─────▼────┐  ┌────▼────┐ ┌───▼──┴─┐      │ └────────┘ └──────────┘
              │  trend   │  │ report  │ │ admin  │      │
              │ 趋势/词云 │  │  日报   │ │后台配置 │      │
              └──────────┘  └─────────┘ └────────┘      │
```

**关键依赖说明**

- `source` 只负责"把原始条目抓下来并规范化"，产出 `article`，不做任何语义处理。
- `pipeline` 是唯一写 `event` 的模块；`hotspot` 只读 `event`（EDITOR 的人工干预除外）。
- `ai-engine` 是横切模块：`pipeline` 用它做 embedding、`hotspot`/`assistant`/`creation`/`report` 用它做生成。所有 LLM 调用必须经过它，禁止业务模块直连模型 SDK。
- `admin` 不拥有业务表，只是 `source` / `ai-engine` / `auth` / 调度日志的管理界面聚合。

---

## 核心业务流程

### 流程一：热点生产流水线（系统自动，核心）

```
[Celery Beat 每小时]
   │
   ▼
① 采集  source.fetch_task(source_id)
   每个采集源一个独立 Celery 任务，互不阻塞
   SourcePlugin: initialize() → fetch() → parse() → normalize()
   产出 RawItem → 落 article 表（status=RAW）
   同 URL 已存在则跳过（url_hash 唯一索引）
   │
   ▼
② 清洗  pipeline.clean_task(article_ids)
   去 HTML / 去广告 / 正文抽取(trafilatura) / 发布时间归一化(UTC)
   / 作者提取 / 标签提取 / 关键词提取(TF-IDF+规则)
   article.status = CLEANED
   │
   ▼
③ 去重聚合  pipeline.dedupe_task()   —— 三级级联
   Level 1 指纹：url_hash / title_hash(归一化后 SHA256) 精确命中 → 直接合并
   Level 2 标题：pg_trgm similarity(title) > 0.75 → 进入候选集
   Level 3 向量：pgvector 余弦相似度 > 0.85（阈值可后台配置）→ 判定同一事件
   命中 → 挂到已有 event（写 event_article）
   未命中 → 新建 event（status=PENDING_AI）
   │
   ▼
④ AI 分析  ai-engine.analyze_event_task(event_id)   —— 每 6 小时批量
   作用对象是 **event 而非 article**（成本更低、语义更完整）
   输入：event 下所有 article 的标题 + 摘要 + 正文片段
   输出（一次结构化调用，PydanticAI 强约束 JSON）：
     summary_one_line / summary / key_points[] / innovations[]
     / audience[] / categories[] / value_score / originality_score
     / trend_score / worth_article / worth_research
   event.status = ANALYZED
   │
   ▼
⑤ 评分入榜  pipeline.rank_task()
   heat_score  = 算法计算（源权重 × 来源数 × 互动数 × 时间衰减），不走 AI
   value/originality/trend_score = AI 打分 (0-100)
   recommend_index = 加权综合（权重可后台配置）
   写 event.heat_score / recommend_index，刷新榜单缓存（Redis）
   │
   ▼
⑥ 展示  hotspot 前端首页按 维度 Tab + 排序 拉取
```

### 流程二：用户浏览与消费（一期）

```
用户打开首页
  → 选择时间维度（今日/本周/本月）+ 分类维度（全球/国内/AI/GitHub/论文/Agent）
  → GET /api/v1/events?scope=today&category=AI&sort=recommend&page=1
  → 卡片流展示：标题 / 一句话总结 / 分类标签 / 推荐指数 / 来源数 / 热度趋势
  → 点击卡片进入详情 GET /api/v1/events/{id}
  → 详情页展示：AI 完整分析 + 评分雷达图 + 全部来源文章列表
  → [二期] 收藏 / 问 AI / 生成创作稿
```

### 流程三：运营人工干预（EDITOR）

```
EDITOR 在热点中心开启"运营模式"
  → 置顶事件      PATCH /api/v1/events/{id}  { "isPinned": true }
  → 隐藏事件      PATCH /api/v1/events/{id}  { "isHidden": true }
  → 编辑标题/摘要/分类   PATCH /api/v1/events/{id}   （记 is_manually_edited=true，
                                                    后续 AI 重跑不覆盖已编辑字段）
  → 拆分错误聚合  POST /api/v1/events/{id}/split  { "articleIds": [...] }
  → 合并两个事件  POST /api/v1/events/merge      { "sourceId": x, "targetId": y }
  → 手动重跑      POST /api/v1/admin/tasks/rerun { "task": "analyze_event", "eventId": x }
  所有干预写 audit_log
```

### 流程四：管理员配置（ADMIN）

```
新增采集源  → 后台填写 plugin_key + config(JSON) + cron + weight → 立即试跑一次 → 预览结果 → 启用
配置 AI     → 新增 Provider(base_url/api_key/协议) → 新增 Model → 设为默认 → 配置降级链
调 Prompt   → 编辑 prompt_template（带版本号），可对单条事件试运行 diff 对比
看成本      → Token/费用按 模型 / 任务类型 / 日期 三维统计
```

---

## 数据库表清单

| 表名                | 说明                        | 所属模块   | 一期 |
| ------------------- | --------------------------- | ---------- | ---- |
| `user`              | 用户                        | auth       | ✅    |
| `user_preference`   | 用户偏好（关注分类/标签）   | auth       | ✅    |
| `source`            | 采集源配置                  | source     | ✅    |
| `source_run_log`    | 采集运行日志                | source     | ✅    |
| `article`           | 原始文章（每源一条）        | pipeline   | ✅    |
| `article_embedding` | 文章向量（pgvector）        | pipeline   | ✅    |
| `event`             | 热点事件（聚合单元）        | pipeline   | ✅    |
| `event_article`     | 事件-文章多对多关联         | pipeline   | ✅    |
| `tag`               | 标签字典                    | pipeline   | ✅    |
| `event_tag`         | 事件-标签关联               | pipeline   | ✅    |
| `ai_provider`       | LLM 服务商配置              | ai-engine  | ✅    |
| `ai_model`          | 模型配置（含定价）          | ai-engine  | ✅    |
| `prompt_template`   | Prompt 模板（带版本）       | ai-engine  | ✅    |
| `ai_call_log`       | 每次 LLM 调用的 Token/成本  | ai-engine  | ✅    |
| `event_analysis`    | 事件的 AI 分析结果          | ai-engine  | ✅    |
| `system_config`     | 系统配置项（KV）            | admin      | ✅    |
| `task_run_log`      | Celery 任务运行日志         | admin      | ✅    |
| `audit_log`         | 操作审计日志                | admin      | ✅    |
| `collection_folder` | 收藏夹                      | collection | —    |
| `collection_item`   | 收藏条目（含笔记/稍后读）   | collection | —    |
| `keyword_trend`     | 关键词按日统计              | trend      | —    |
| `entity_trend`      | 公司/项目/技术按日统计      | trend      | —    |
| `assistant_thread`  | 问 AI 会话                  | assistant  | —    |
| `assistant_message` | 问 AI 消息                  | assistant  | —    |
| `creation_draft`    | 创作草稿                    | creation   | —    |
| `report`            | 日报                        | report     | —    |
| `report_item`       | 日报条目                    | report     | —    |

---

## 全局约定

### 数据库

- 所有业务表必须包含：`id`（BIGSERIAL 主键）、`created_at`、`updated_at`、`is_deleted`
- 软删除统一用 `is_deleted`（BOOLEAN，默认 `false`），所有查询默认带 `is_deleted = false`
- 时间字段统一 `TIMESTAMPTZ`，**数据库内一律存 UTC**，展示时前端按浏览器时区渲染
- 枚举统一用 `VARCHAR(32)` 存 **枚举名大写下划线**（如 `PENDING_AI`），不用数字；Python 侧用 `enum.StrEnum`
- 布尔开关用 `BOOLEAN`，不用 `TINYINT`
- 分数字段统一 `SMALLINT`，取值 `0-100`；`heat_score` 为 `NUMERIC(6,2)`
- 表名/字段名 `snake_case` 单数（`user` 而非 `users`）
- 向量列用 `vector(1024)`（默认 embedding 维度），建 HNSW 索引
- 迁移工具：Alembic，一个模块一个 revision，禁止手改已合并的迁移

### API

- 前缀：`/api/v1/`，路由按模块分组（`/auth` `/sources` `/events` `/admin/...`）
- 风格：**RESTful 原生状态码**。2xx 直接返回数据体，不做 `{code,message,data}` 包裹
- 错误响应统一结构：
  ```json
  { "detail": "事件不存在", "errorCode": "EVENT_NOT_FOUND" }
  ```
  - `400` 参数/业务校验失败 · `401` 未登录/Token 失效 · `403` 权限不足
  - `404` 资源不存在 · `409` 冲突（唯一约束） · `422` FastAPI 校验失败 · `429` 限流 · `5xx` 服务端错误
- 认证：JWT，Header `Authorization: Bearer <accessToken>`
- 分页入参 `page`（**从 1 开始**）/ `size`（默认 20，最大 100），出参：
  ```json
  { "items": [], "total": 128, "page": 1, "size": 20, "pages": 7 }
  ```
- 排序入参 `sort`，格式 `field` 或 `-field`（前缀 `-` 表示倒序），允许字段由各模块白名单限定
- JSON 字段名统一 **camelCase**（Pydantic 配 `alias_generator=to_camel`，`populate_by_name=True`）
- 时间统一 ISO 8601 带时区：`2026-07-29T08:30:00Z`
- 所有列表接口必须支持分页，禁止无界返回
- OpenAPI 文档：`/docs`（Swagger）、`/openapi.json`；前端类型由此自动生成

### 后端代码

- 分层：`api`（路由/DTO） → `service`（业务编排） → `repository`（数据访问） → `model`（ORM）
- 领域按模块划分包（DDD 轻量版），跨模块调用只允许通过 `service` 层公开接口，禁止跨模块直接查表
- 依赖注入用 FastAPI `Depends`；数据库会话按请求生命周期
- 插件（采集器、LLM Provider、导出器）通过 **注册表 + 抽象基类** 实现，禁止 `if/elif` 分发
- 所有外部 IO（HTTP、LLM）必须带超时、重试（tenacity）、熔断
- 异常：业务异常继承 `AppException(status_code, error_code, detail)`，由全局 handler 转 HTTP 响应
- 日志：structlog JSON 格式，必带 `trace_id`
- 每个模块必须可独立测试：`tests/{module}/`，外部依赖用 fixture 打桩

### 前端代码

- 目录按 feature 组织：`src/features/{module}/{api,components,hooks,pages,types}`
- 服务端状态一律用 TanStack Query，禁止把接口数据塞进 Zustand
- 客户端状态（UI 状态、筛选条件）用 Zustand + URL SearchParams（筛选条件必须可分享）
- API 类型从 `openapi.json` 自动生成到 `src/lib/api/schema.d.ts`，**禁止手写接口类型**
- 组件库固定 shadcn/ui + Tailwind CSS v4，图表固定 ECharts
- 路由用 React Router v7，鉴权用 `<RequireRole>` 包装
- 所有异步区域必须有 loading skeleton 与 error 边界

### AI 调用

- 所有 LLM 调用经 `ai-engine` 的 `LLMGateway`，业务代码不得 import 任何模型 SDK
- Prompt 一律来自 `prompt_template` 表（带版本号），禁止硬编码在代码里
- 结构化输出用 PydanticAI 强制 schema，解析失败自动重试（最多 3 次）
- 每次调用必须写 `ai_call_log`（模型、输入/输出 token、耗时、费用、成功与否）
- 单模型失败按 `system_config.ai_fallback_chain` 自动降级到下一个模型
- 成本兜底：单任务超过 `ai_task_cost_limit_usd` 直接中止并告警

### 命名与规范

- Python：ruff + mypy(strict)，行宽 100
- TypeScript：ESLint + Prettier，strict 模式
- Git 提交：Conventional Commits（`feat(hotspot): ...`）
- 分支：`main` 保护，功能分支 `feat/{module}-{desc}`

---

## 一期（MVP）验收标准

- [ ] Docker Compose 一键起全栈（pg + redis + api + worker + beat + web）
- [ ] 6-8 个采集源能定时抓取并入库，后台可见运行日志
- [ ] 清洗后正文抽取准确率人工抽检 ≥ 90%
- [ ] 同一事件跨源聚合正确率人工抽检 ≥ 85%，误合并率 ≤ 5%
- [ ] AI 分析产出结构化 JSON，字段完整率 100%
- [ ] 首页热点榜按 6 个维度 Tab 正常展示，搜索/过滤/排序可用
- [ ] 详情页展示完整 AI 分析 + 评分雷达图 + 多来源列表
- [ ] EDITOR 可置顶/隐藏/编辑/拆分合并事件
- [ ] ADMIN 可增删改采集源、切换 AI 模型、查看 Token 成本统计
- [ ] 后端单测覆盖率 ≥ 70%，核心 pipeline ≥ 85%

---

## 待定问题（全局）

- [ ] 采集源反爬如何处理？一期只做 `User-Agent` 轮换 + 请求间隔，需代理池的源（如 Reddit）延后
- [ ] Embedding 用什么模型？暂定 `bge-m3`（1024 维，本地 ONNX 部署，零调用成本），可后台切云端
- [ ] 事件生命周期：一个事件持续多久算"活跃"？暂定 72 小时内有新来源就续期，之后归档
- [ ] 全文搜索一期用 PG `tsvector` + `pg_trgm`；中文分词方案暂定 `zhparser`，若部署困难降级为 trigram
- [ ] 是否需要邮件/Webhook 通知？一期不做，二期随 report 模块一起
- [ ] 多语言：一期界面仅中文，英文源的 AI 分析结果统一输出中文

---

## 变更记录

| 日期       | 模块 | 变更内容                                                        |
| ---------- | ---- | --------------------------------------------------------------- |
| 2026-07-29 | 全局 | 初版：访谈确认 4 角色 / 11 模块 / MVP 范围 / 技术选型 / 全局约定 |

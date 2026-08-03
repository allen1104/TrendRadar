# TrendRadar 趋势雷达

AI 驱动的全球科技热点发现平台。不是帮你看新闻，是帮你发现趋势。

## 技术栈

**Backend**  Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Celery + Beat · PydanticAI
**Frontend** React 19 · Vite · TypeScript · Tailwind CSS v4 · shadcn/ui · TanStack Query · Zustand · React Router v7 · ECharts
**Data**     PostgreSQL 17 (+pgvector +pg_trgm) · Redis 7
**AI**       统一 LLM 网关，多 Provider 可配置（OpenAI 兼容 / Anthropic / Gemini）· 本地 bge-m3 embedding
**Deploy**   Docker Compose

## ⚡ 当前模块：report

（每次开始新模块时更新这一行，例如：⚡ 当前模块：管理后台 admin）

## 模块列表与状态

一期（MVP）：
- [x] auth — 认证与权限
- [x] ai-engine — LLM 统一网关 · [Prompt 索引](backend/app/modules/ai/PROMPTS.md)
- [x] source — 采集源与插件 · [Module README](backend/app/modules/source/README.md)
- [x] pipeline — 清洗与去重聚合 · [Module README](backend/app/modules/pipeline/README.md)
- [x] hotspot — 热点中心 · [Module README](backend/app/modules/hotspot/README.md)
- [x] admin — 管理后台 · [Module README](backend/app/modules/admin/README.md)
- [x] 一期联调验收 — 9/10 项通过，27/27 冒烟全过 · [验收报告](doc/ACCEPTANCE.md)

二期：
- [x] collection — 收藏系统 · [Module README](backend/app/modules/collection/README.md)
- [x] trend — 趋势分析 · [Module README](backend/app/modules/trend/README.md)
- [x] assistant — AI 助手 · [Module README](backend/app/modules/assistant/README.md)
- [x] creation — 内容创作 · [Module README](backend/app/modules/creation/README.md)
- [x] report — 日报中心 · [Module README](backend/app/modules/report/README.md)

**开发顺序**：`auth` → `ai-engine` → `source` → `pipeline` → `hotspot` → `admin`
（`ai-engine` 排在 `pipeline` 之前，因为 pipeline 依赖它的 embedding 能力）

## 快速命令

```bash
# 环境
docker compose up -d                          # 起 pg + redis + api + worker + beat + web
docker compose logs -f api worker             # 看日志
docker compose down -v                        # 清空重来

# 后端（backend/）
uv sync                                       # 装依赖
uv run alembic revision --autogenerate -m "x" # 生成迁移
uv run alembic upgrade head                   # 执行迁移
uv run python -m app.scripts.seed             # 初始化配置/Prompt/管理员
uv run uvicorn app.main:app --reload          # 本地起服务
uv run celery -A app.worker worker -l info    # 起 worker
uv run celery -A app.worker beat -l info      # 起 beat
uv run pytest                                 # 跑测试
uv run pytest --cov=app --cov-report=term     # 覆盖率
uv run ruff check . --fix && uv run ruff format .
uv run mypy app

# 前端（frontend/）
pnpm install
pnpm dev                                      # 起开发服务器 :5173
pnpm gen:api                                  # 从 openapi.json 生成类型
pnpm typecheck
pnpm lint --fix
pnpm build

# 全栈验证
cd backend && uv run pytest && uv run mypy app && cd ../frontend && pnpm typecheck && pnpm build
```

## 前后端约定

- **API 前缀**：`/api/v1/`
- **认证**：JWT，Header `Authorization: Bearer <accessToken>`；access 2h / refresh 14d，refresh 旋转
- **响应格式**：**RESTful 原生状态码**。2xx 直接返回数据体，**不做 `{code,message,data}` 包裹**
- **错误格式**：`{ "detail": "事件不存在", "errorCode": "EVENT_NOT_FOUND" }`
  - `400` 业务校验 · `401` 未登录 · `403` 权限不足 · `404` 不存在 · `409` 冲突 · `422` 参数校验 · `429` 限流
- **分页**：入参 `page`（**从 1**）/ `size`（默认 20，最大 100）
  出参 `{ items, total, page, size, pages }`
- **排序**：`sort=field` 或 `sort=-field`（`-` 前缀倒序），字段走后端白名单
- **字段命名**：JSON 一律 **camelCase**（Pydantic `alias_generator=to_camel`）
- **时间**：ISO 8601 带时区，`2026-07-29T08:30:00Z`；数据库存 UTC，前端按浏览器时区渲染
- **枚举**：大写下划线字符串（`PENDING_AI`），不用数字
- **流式接口**：SSE（`text/event-stream`），事件名 `start` / `delta` / `done` / `error`
- **类型生成**：前端接口类型**必须**由 `openapi.json` 生成，禁止手写

## 铁律

1. **AI 调用只走 `ai-engine` 的 `LLMGateway`**，业务代码不得 import 任何模型 SDK
2. **Prompt 只从 `prompt_template` 表读**，代码中禁止硬编码 prompt 字符串
3. **采集器只实现 `SourcePlugin` + 打 `@register_plugin`**，禁止 `if/elif` 分发插件
4. **跨模块调用只经 `service` 层**，禁止跨模块直接查表
5. **软删除统一 `is_deleted`**，所有查询默认带 `is_deleted = false`
6. **`user_id` 一律从 Token 取**，禁止接受请求参数传入
7. **列表接口必须分页**，禁止无界返回
8. **所有 Celery 任务必须幂等**，重复执行不产生脏数据
9. **敏感字段（apiKey / password）**：加密存储、出参脱敏、日志脱敏
10. **写操作必须写 `audit_log`**（运营与管理类操作）

## 目录结构

```
backend/app/
  core/           配置、安全、异常、日志、依赖
  db/             session、base model、迁移
  modules/
    auth/         api/ service/ repository/ model/ schema/
    source/       plugins/ 下每个采集器一个文件
    pipeline/     cleaner/ dedupe/ ranker/
    ai/           gateway/ providers/ prompts/
    hotspot/
    admin/
  worker/         Celery app、任务注册、Beat 调度
  scripts/        seed、一次性脚本
  tests/          按模块分目录

frontend/src/
  app/            路由、Providers、布局
  features/
    auth/         api/ components/ hooks/ pages/ types/
    hotspot/
    admin/
    ...
  components/ui/  shadcn 组件
  lib/            api client、utils、hooks
  stores/         Zustand
```

## 参考文件

- 需求总览: @SPEC.md
- 模块需求: @doc/SPEC-auth.md · @doc/SPEC-source.md · @doc/SPEC-ai-engine.md · @doc/SPEC-pipeline.md · @doc/SPEC-hotspot.md · @doc/SPEC-admin.md · @doc/SPEC-collection.md · @doc/SPEC-trend.md · @doc/SPEC-assistant.md · @doc/SPEC-creation.md · @doc/SPEC-report.md
- Prompt 索引: @backend/app/modules/ai/PROMPTS.md（ai-engine 模块所有 Prompt 模板的索引与修改 SOP）
- source 模块: @backend/app/modules/source/README.md（插件表 + 注册表机制 + 待办）
- 开发进度: @.claude/progress/PROGRESS.md
- 后端规范: @backend/CLAUDE.md
- 前端规范: @frontend/CLAUDE.md

## 开发流程

每个模块严格按顺序：**先设计 → 再编码 → 再测试 → 最后写 README**

1. 读该模块的 `doc/SPEC-{module}.md`，确认字段、接口、页面、规则
2. 写 model + 迁移 → `alembic upgrade head` 验证
3. 写 repository → service → api，每层配单测
4. `pnpm gen:api` 生成前端类型
5. 写前端页面
6. 跑全栈验证命令
7. 更新本文件的模块状态与 `.claude/progress/PROGRESS.md`

**不要一次生成整个项目。一次只做一个模块。**

---

## 维护规范（每次任务结束必做，不等用户提醒）

完成任意子任务（A/B/C…/全模块/修 bug/加字段）后，**在回消息之前先改这三处**：

1. **`CLAUDE.md`（本文件）**：
   - 顶部「⚡ 当前模块」改为当前正在做的模块
   - 「模块列表与状态」表：完成模块从 `[ ]` 改 `[x]`，补一行链接到该模块的 README
2. **`.claude/progress/PROGRESS.md`**：
   - 「阶段」勾选对应阶段
   - 「模块完成度」表格里 model/迁移/repo/service/api/前端/测试 各列 ⬜ 改 ✅
   - 「当前工作」段更新为下一阶段（写下"下一步：xx"）
3. **`backend/app/modules/{module}/README.md`** 或 `frontend/...`：
   - 每完成一个子阶段，末尾「验证状态」表追加一行（实测 SQL 输出 / API 响应 / 单测结果）
4. **`doc/SPEC-{module}.md`** 顶部「模块状态」字段从 `⏳ 未开始` / `🔄 开发中` 改成 `✅ 已完成`，最后更新日期同步

> 这条规则不需要用户再说一遍，写到这里的瞬间就在上下文里一直生效。
> **写完代码没改文档 = 任务未完成。**

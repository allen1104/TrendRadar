# TrendRadar 趋势雷达

> AI 驱动的全球科技热点发现平台
> **不是帮你看新闻，是帮你发现趋势。**

面向 AI 开发者、技术作者、公众号作者、独立开发者、科技媒体从业者。

每天自动从全球与国内 20+ 科技信息源采集内容，经过清洗、跨源去重聚合、AI 分析评分，
把散落在多个来源的同一件事收敛成**一个热点事件**，并给出价值判断。

---

## 核心能力

| 能力     | 说明                                                                 |
| -------- | -------------------------------------------------------------------- |
| 插件采集 | 统一 `SourcePlugin` 接口，新增一个源 = 新增一个文件，不改已有代码     |
| 智能聚合 | 指纹 → 标题 trigram → 向量余弦，三级级联把跨源同一事件合并            |
| AI 分析  | 总结、核心观点、创新点、适合人群、分类、价值/原创/趋势评分            |
| 热点中心 | 今日/本周/本月 × 全球/国内/AI/GitHub/论文/Agent 多维榜单              |
| 趋势分析 | 关键词增长率、热门公司/项目/技术排行、词云（二期）                    |
| AI 助手  | 针对每个热点追问，基于来源材料作答并标注引用（二期）                  |
| 内容创作 | 一键生成公众号/博客/微博/小红书/知乎稿件，5 种写作风格（二期）        |
| 每日日报 | AI/科技/GitHub/Agent 四类日报，支持 MD/HTML/PDF/公众号导出（二期）    |

---

## 技术栈

**Backend**  Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Celery · PydanticAI
**Frontend** React 19 · Vite · TypeScript · Tailwind v4 · shadcn/ui · TanStack Query · ECharts
**Data**     PostgreSQL 17 (+pgvector +pg_trgm) · Redis 7
**AI**       统一 LLM 网关，多 Provider 可配置 · 本地 bge-m3 embedding

---

## 快速开始

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，至少替换 SECRET_KEY 与 JWT_REFRESH_SECRET_KEY
#   openssl rand -hex 32

# 2. 一键起全栈
docker compose up -d

# 3. 初始化数据（配置项、Prompt 模板、管理员账号）
docker compose exec api python -m app.scripts.seed

# 4. 访问
#   前端      http://localhost:5173
#   API 文档  http://localhost:8000/docs
```

### 本地开发

```bash
# 只起依赖
docker compose up -d postgres redis

# 后端
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.scripts.seed
uv run uvicorn app.main:app --reload
uv run celery -A app.worker worker -l info -P solo   # 另开一个终端
uv run celery -A app.worker beat -l info             # 再开一个

# 前端
cd frontend
pnpm install
pnpm gen:api      # 后端起着的时候跑
pnpm dev
```

---

## 项目文档

| 文档                     | 内容                                       |
| ------------------------ | ------------------------------------------ |
| [SPEC.md](./SPEC.md)     | 需求总览：角色、模块索引、全局约定、核心流程 |
| [doc/](./doc/)           | 11 个模块的完整需求（字段/接口/页面/规则）  |
| [CLAUDE.md](./CLAUDE.md) | 开发约定与铁律                             |
| [backend/CLAUDE.md](./backend/CLAUDE.md) | 后端分层规范           |
| [frontend/CLAUDE.md](./frontend/CLAUDE.md) | 前端规范             |
| [.claude/progress/PROGRESS.md](./.claude/progress/PROGRESS.md) | 开发进度 |

---

## 模块状态

一期（MVP）：`auth` · `ai-engine` · `source` · `pipeline` · `hotspot` · `admin` — 全部 ⏳ 未开始
二期：`collection` · `trend` · `assistant` · `creation` · `report` — ⏳ 未开始

开发顺序：`auth → ai-engine → source → pipeline → hotspot → admin`

---

## 架构概览

```
Celery Beat ─┬─► source.fetch      每源独立 cron，插件化采集      → article(RAW)
             │
             ├─► pipeline.clean    正文抽取/去广告/关键词/粗摘要  → article(CLEANED)
             │
             ├─► pipeline.embed    bge-m3 向量化                  → article_embedding
             │
             ├─► pipeline.dedupe   指纹→标题→向量 三级聚合         → event + event_article
             │
             ├─► ai.analyze_event  结构化 AI 分析与评分            → event_analysis
             │
             └─► pipeline.rank     热度算法 + 加权推荐指数         → 榜单缓存

FastAPI ────────► hotspot / collection / trend / assistant / creation / report / admin
React SPA ──────► 热点中心 · 详情 · 趋势 · 收藏 · 创作 · 日报 · 后台
```

---

## License

MIT

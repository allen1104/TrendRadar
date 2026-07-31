# 热点中心模块（hotspot）

所属项目: @SPEC.md
模块状态: ✅ 已完成
一期范围: ✅ 是
最后更新: 2026-07-30

---

## 功能目标

系统的**门面**。把 `pipeline` 产出的热点事件以多维榜单形式呈现，并提供：

- 六大维度榜单：今日 / 本周 / 本月 × 全球 / 国内 / AI / GitHub / 论文 / Agent
- 搜索（标题 + 摘要 + 标签，中英文）
- 过滤（分类、标签、来源、时间范围、推荐指数区间）
- 排序（推荐指数 / 热度 / 最新 / 来源数）
- 事件详情：完整 AI 分析、评分雷达图、全部来源文章
- 趋势变化：事件热度的时间序列（近 7 天）
- EDITOR 运营能力：置顶、隐藏、编辑内容、拆分/合并聚合

**只读 `event`**（运营干预除外），不参与数据生产。

---

## 数据库设计

本模块**不新建业务表**，读取 `event` / `event_article` / `article` / `event_analysis` / `tag` / `event_tag`（见 @doc/SPEC-pipeline.md 与 @doc/SPEC-ai-engine.md）。

新增两项基础设施：

### `event` 表的全文检索列（在 pipeline 迁移中追加）

```sql
ALTER TABLE event ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(title,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(summary_one_line,'')), 'B')
  ) STORED;
CREATE INDEX idx_event_search ON event USING GIN (search_vector);
```
> 中文分词一期用 `simple` + `pg_trgm` 组合兜底；若 `zhparser` 部署成功则切换配置项 `search_text_config`。

### Redis 榜单缓存

| 键                                         | 类型   | TTL   | 说明                       |
| ------------------------------------------ | ------ | ----- | -------------------------- |
| `hotspot:rank:{scope}:{category}:{sort}`   | STRING | 5 分钟 | 榜单首页（前 60 条）JSON   |
| `hotspot:event:{eventId}`                  | STRING | 10 分钟| 事件详情 JSON              |
| `hotspot:trend:{eventId}`                  | STRING | 1 小时 | 事件 7 日热度曲线          |

`rank_task` 完成后主动失效 `hotspot:rank:*`；事件被编辑后失效对应 `hotspot:event:{id}`。

---

## 榜单维度定义

| Tab 名称     | `scope` | `category` | 过滤条件                                                   |
| ------------ | ------- | ---------- | ---------------------------------------------------------- |
| 今日热点     | `TODAY` | `ALL`      | `last_seen_at >= 今日 00:00`（用户时区）                    |
| 本周热点     | `WEEK`  | `ALL`      | `last_seen_at >= 本周一 00:00`                             |
| 本月热点     | `MONTH` | `ALL`      | `last_seen_at >= 本月 1 日 00:00`                          |
| 全球热点     | 任意    | `GLOBAL`   | `region IN ('GLOBAL','MIXED')`                             |
| 国内热点     | 任意    | `CN`       | `region IN ('CN','MIXED')`                                 |
| AI 热点      | 任意    | `AI`       | `categories @> '["AI"]'` 或含 `LLM`/`AGENT`/`MCP`          |
| GitHub 热点  | 任意    | `GITHUB`   | 关联文章的 `source.category = 'CODE'`                      |
| 论文热点     | 任意    | `PAPER`    | `categories @> '["PAPER"]'` 或来源 `source.category='PAPER'` |
| Agent 热点   | 任意    | `AGENT`    | `categories @> '["AGENT"]'`                                |

`scope` 与 `category` 正交，可自由组合（如 `scope=WEEK&category=AGENT`）。
所有榜单默认排除 `is_hidden=true` 与 `is_deleted=true`。

---

## 后端接口

### GET /api/v1/events
**说明**: 热点榜单。`GUEST` 可访问

**Query 参数**:

| 参数            | 类型      | 默认        | 说明                                                              |
| --------------- | --------- | ----------- | ----------------------------------------------------------------- |
| `scope`         | enum      | `TODAY`     | `TODAY`/`WEEK`/`MONTH`/`ALL`                                      |
| `category`      | enum      | `ALL`       | `ALL`/`GLOBAL`/`CN`/`AI`/`GITHUB`/`PAPER`/`AGENT` + 11 个分类枚举 |
| `sort`          | string    | `-recommendIndex` | 白名单：`recommendIndex`/`heatScore`/`lastSeenAt`/`sourceCount`，前缀 `-` 倒序 |
| `keyword`       | string    | -           | 全文搜索关键词                                                    |
| `tagIds`        | int[]     | -           | 标签过滤（AND 关系）                                              |
| `sourceIds`     | int[]     | -           | 来源过滤（OR 关系）                                               |
| `minRecommend`  | int       | -           | 推荐指数下限 0-100                                                |
| `startDate`     | date      | -           | `last_seen_at` 起（覆盖 scope）                                   |
| `endDate`       | date      | -           | `last_seen_at` 止                                                 |
| `includeHidden` | bool      | `false`     | 仅 EDITOR 及以上可传 true                                         |
| `page` / `size` | int       | `1` / `20`  | 分页                                                              |

**Response 200**:
```json
{
  "items": [
    {
      "id": 88,
      "title": "OpenAI 发布 GPT-5，多模态推理能力大幅提升",
      "summaryOneLine": "GPT-5 在多模态推理上超越前代 40%，同步开放 API",
      "region": "MIXED",
      "categories": ["AI", "LLM"],
      "tags": [{ "id": 12, "displayName": "OpenAI", "type": "COMPANY" }],
      "sourceCount": 4,
      "articleCount": 7,
      "sources": [
        { "id": 1, "name": "Hacker News", "homeUrl": "https://news.ycombinator.com" },
        { "id": 6, "name": "机器之心", "homeUrl": "https://jiqizhixin.com" }
      ],
      "heatScore": 92.4,
      "valueScore": 88,
      "originalityScore": 79,
      "trendScore": 91,
      "recommendIndex": 88.6,
      "worthArticle": true,
      "primaryArticleUrl": "https://openai.com/blog/gpt-5",
      "firstSeenAt": "2026-07-29T02:10:00Z",
      "lastSeenAt": "2026-07-29T07:40:00Z",
      "isPinned": false,
      "isHidden": false,
      "isManuallyEdited": false,
      "isCollected": false
    }
  ],
  "total": 128, "page": 1, "size": 20, "pages": 7
}
```

**说明**:
- `isCollected` 仅登录用户返回真实值，`GUEST` 恒为 `false`（二期 collection 模块生效前恒 false）
- `isPinned=true` 的事件恒排在最前（不受 `sort` 影响），其内部按 `sort` 排序
- 用户已登录且设置了 `mutedSources` → 自动排除仅来自被屏蔽源的事件

**错误情况**: `sort` 字段不在白名单 → `400` `INVALID_SORT_FIELD`

---

### GET /api/v1/events/{id}
**说明**: 事件详情。`GUEST` 可访问

**Response 200**:
```json
{
  "id": 88,
  "title": "OpenAI 发布 GPT-5，多模态推理能力大幅提升",
  "region": "MIXED",
  "categories": ["AI", "LLM"],
  "tags": [{ "id": 12, "displayName": "OpenAI", "type": "COMPANY", "weight": 1.0 }],
  "sourceCount": 4,
  "articleCount": 7,
  "heatScore": 92.4,
  "recommendIndex": 88.6,
  "status": "ANALYZED",
  "isPinned": false,
  "isHidden": false,
  "isManuallyEdited": false,
  "manualLockedFields": [],
  "firstSeenAt": "2026-07-29T02:10:00Z",
  "lastSeenAt": "2026-07-29T07:40:00Z",
  "analysis": {
    "summaryOneLine": "GPT-5 在多模态推理上超越前代 40%，同步开放 API",
    "summary": "2026 年 7 月 29 日，OpenAI 正式发布 GPT-5……",
    "keyPoints": ["多模态推理提升 40%", "上下文扩展至 2M", "API 定价下降 30%"],
    "innovations": ["统一视觉-语言-代码的单一架构", "原生工具调用无需 function schema"],
    "audience": ["AI 应用开发者", "技术内容创作者", "产品经理"],
    "valueScore": 88,
    "originalityScore": 79,
    "trendScore": 91,
    "worthArticle": true,
    "worthArticleWhy": "发布事件热度高且技术细节丰富，适合做深度解读",
    "worthResearch": true,
    "worthResearchWhy": "统一架构的实现细节值得跟进论文与实测",
    "modelAlias": "default-chat",
    "promptVersion": 3,
    "analyzedAt": "2026-07-29T08:05:00Z"
  },
  "articles": [
    {
      "id": 1024,
      "title": "Introducing GPT-5",
      "url": "https://openai.com/blog/gpt-5",
      "author": "OpenAI",
      "lang": "en",
      "publishedAt": "2026-07-29T02:10:00Z",
      "summary": "Today we're releasing GPT-5...",
      "metrics": { "points": 1820, "comments": 430 },
      "source": { "id": 1, "name": "Hacker News", "weight": 9 },
      "isPrimary": true,
      "matchLevel": "MANUAL",
      "similarity": null
    }
  ],
  "isCollected": false
}
```

**错误情况**:
- 事件不存在或已删除 → `404` `EVENT_NOT_FOUND`
- 事件 `is_hidden=true` 且请求者非 EDITOR → `404` `EVENT_NOT_FOUND`（不暴露存在性）
- `status != ANALYZED` → `analysis` 为 `null`，前端显示"AI 分析中"

---

### GET /api/v1/events/{id}/trend
**说明**: 事件近 7 天热度与来源增长曲线

**Response 200**:
```json
{
  "eventId": 88,
  "points": [
    { "date": "2026-07-29", "heatScore": 92.4, "sourceCount": 4, "articleCount": 7 },
    { "date": "2026-07-28", "heatScore": 61.2, "sourceCount": 2, "articleCount": 3 }
  ]
}
```
> 数据来自按日快照（`rank_task` 每次运行时写入 `event_daily_snapshot`，由 trend 模块建表；一期用 `event_article.created_at` 按日聚合近似计算）

---

### GET /api/v1/events/{id}/related
**说明**: 相关事件推荐（向量相似 Top 5，排除自身）

**Response 200**: 精简的事件卡片数组（id / title / summaryOneLine / recommendIndex / lastSeenAt）

---

### GET /api/v1/tags
**说明**: 标签列表，用于过滤器。`GUEST` 可访问

**Query**: `keyword` `type` `limit`（默认 50，最大 200）

**Response 200**:
```json
[{ "id": 12, "displayName": "OpenAI", "type": "COMPANY", "eventCount": 84 }]
```
> 默认按 `eventCount DESC` 返回热门标签

---

### PATCH /api/v1/events/{id}
**说明**: 运营干预。`EDITOR` 及以上

**Request Body**（字段均可选）:
```json
{
  "title": "手工修正后的标题",
  "summaryOneLine": "手工修正后的一句话",
  "categories": ["AI", "AGENT"],
  "isPinned": true,
  "isHidden": false
}
```

**Response 200**: 事件详情对象

**规则**:
- 修改 `title` / `summaryOneLine` / `categories` 任一 → 该字段名写入 `manual_locked_fields`，`isManuallyEdited=true`
- `isPinned` / `isHidden` 不进 `manual_locked_fields`
- 写 `audit_log`（记录变更前后值）
- 自动失效 `hotspot:event:{id}` 与 `hotspot:rank:*` 缓存

**错误情况**: 同时置 `isPinned=true` 与 `isHidden=true` → `400` `PIN_AND_HIDE_CONFLICT`

---

### DELETE /api/v1/events/{id}/manual-lock/{field}
**说明**: 解除某字段的人工锁定，下次 AI 重跑可覆盖。`EDITOR` 及以上

**Response 204**

---

> 拆分 / 合并接口见 @doc/SPEC-pipeline.md（`POST /events/{id}/split`、`POST /events/merge`）

---

## 前端页面

### 热点中心（`/`，首页）

**顶部导航区**
- 时间维度 Tab：`今日` `本周` `本月` `全部`（Segmented Control）
- 分类维度 Tab（第二行）：`全部` `全球` `国内` `AI` `GitHub` `论文` `Agent`
- 两组 Tab 状态同步到 URL SearchParams（`?scope=WEEK&category=AI`），**可分享可刷新保持**

**筛选栏（可折叠）**
- 搜索框：输入 300ms debounce 触发，带清除按钮，支持回车立即搜
- 排序下拉：推荐指数 / 热度 / 最新 / 来源数（默认推荐指数）
- 标签多选 Combobox：远程搜索 `/tags`，已选显示为可删 Chips
- 来源多选：从 `/sources` 拉取
- 推荐指数滑块：0-100 双端范围
- 日期范围选择器
- 「重置筛选」按钮
- EDITOR 额外：`显示已隐藏` Switch

**事件卡片流**
每张卡片：
```
┌──────────────────────────────────────────────────────┐
│ [置顶] [AI][LLM]                        推荐 88.6 ●  │  ← 推荐指数环形进度
│ OpenAI 发布 GPT-5，多模态推理能力大幅提升              │
│ GPT-5 在多模态推理上超越前代 40%，同步开放 API          │  ← 一句话总结，2 行截断
│ ─────────────────────────────────────────────────── │
│ 🌐4个来源  [HN][机器之心][InfoQ][+1]   🔥92.4  2小时前 │
│ [OpenAI] [GPT-5] [多模态]              ⭐收藏  ↗原文  │
└──────────────────────────────────────────────────────┘
```
- 来源用 favicon 小图标堆叠展示，hover 显示全部来源名
- 「值得写公众号」的事件右上角加 ✍️ 角标
- `isManuallyEdited` 显示 "已校对" 小 Badge
- EDITOR 模式下卡片右上角出现「⋯」菜单：置顶 / 隐藏 / 编辑 / 重跑分析
- 骨架屏加载态，滚动到底自动加载下一页（或分页器，二选一，一期用分页器）
- 空状态：插画 + "当前筛选条件下暂无热点" + 「重置筛选」按钮

**右侧栏（桌面端，≥1280px 显示）**
- 「今日 Top 标签」词条云（点击加入筛选）
- 「活跃来源」列表（今日采集量 Top 5）
- 「AI 正在分析」计数（`status=PENDING_AI` 数量，实时感）

### 事件详情页（`/events/:id`）

**头部**
- 面包屑：热点中心 / {分类} / 当前事件
- 大标题 + 分类 Badges + 区域标记
- 元信息行：首次出现时间、最后更新时间、来源数、文章数
- 右上角操作：⭐收藏（二期）、💬问 AI（二期）、✍️生成文章（二期）、🔗分享链接

**左主栏**
1. **AI 一句话总结**：高亮引用块样式
2. **完整总结**：正文排版
3. **核心观点**：带序号的列表卡片
4. **创新点**：图标列表（无则不显示该区块）
5. **适合人群**：Chips
6. **值得关注判断**：两张并排卡片
   - 「值得写公众号吗」✅/❌ + 理由
   - 「值得深入研究吗」✅/❌ + 理由
7. **来源文章列表**：
   - 每行：源 favicon + 源名、标题（外链）、作者、发布时间、互动指标
   - 主文章标 「主」 Badge
   - EDITOR 可见：`matchLevel` Badge + `similarity` 数值、行前 checkbox

**右侧栏**
1. **评分雷达图**（ECharts radar）：热度 / 价值 / 原创 / 趋势 / 推荐 五维
2. **7 日热度曲线**（ECharts line）：热度分 + 来源数双 Y 轴
3. **标签云**：事件的全部标签，点击跳转到该标签筛选的榜单
4. **相关事件**：Top 5 卡片列表

**EDITOR 运营区**（悬浮在页面底部的操作条，仅 EDITOR 可见）
- 置顶 Switch / 隐藏 Switch
- 「编辑内容」→ 弹窗可改标题、一句话总结、分类；已锁定字段显示 🔒 图标与「解除锁定」按钮
- 「重跑 AI 分析」按钮（二次确认，提示会消耗 token）
- 选中来源文章后浮出「拆分为新事件」
- 「合并到其他事件」→ 事件搜索 Combobox

**加载/错误态**
- `analysis` 为 null → 左主栏显示"AI 正在分析中，稍后刷新"占位 + 自动 30 秒轮询一次（最多 10 次）
- 404 → 独立的"事件不存在或已下架"页面

---

## 业务规则

### 排序
- 置顶事件（`is_pinned=true`）恒定排在最前，内部按用户选择的 `sort` 排序
- 默认排序 `-recommendIndex`，同分时按 `-lastSeenAt` 二次排序（保证稳定分页）
- 分页必须带稳定 tiebreaker（末尾追加 `, id DESC`），避免翻页重复/漏项

### 搜索
- `keyword` 非空时：`search_vector @@ plainto_tsquery(:kw)` **OR** `title % :kw`（trigram 模糊）
- 命中排序：全文匹配 `ts_rank` 优先，其次 trigram similarity，最后 `recommendIndex`
- 关键词长度 < 2 → `400` `KEYWORD_TOO_SHORT`
- 搜索结果不走 Redis 缓存（组合太多）

### 缓存
- 仅缓存**无 keyword、无自定义筛选**的默认榜单首 3 页
- 缓存 key 含 `scope` / `category` / `sort` / `page`
- 登录用户若配置了 `mutedSources` → 跳过缓存直查（保证个性化正确）
- `rank_task` 完成 / 事件被编辑 → 主动失效

### 权限
- `GUEST` / `USER`：只能看 `is_hidden=false` 的事件；`includeHidden=true` 被忽略
- `EDITOR` / `ADMIN`：可传 `includeHidden=true`，隐藏事件在列表中显示灰色遮罩 + 「已隐藏」标记
- 运营操作全部写 `audit_log`

### 性能
- 列表接口 P95 < 300ms（缓存命中 < 50ms）
- 详情接口 P95 < 200ms
- 列表查询必须避免 N+1：`sources` / `tags` 用一次批量查询后在内存组装
- `size` 上限 100，超出 → `400`

---

## 完成标准

- [ ] `search_vector` 生成列与 GIN 索引创建成功
- [ ] `GET /events` 支持全部筛选/排序/分页参数，`sort` 白名单校验生效
- [ ] 六大维度 Tab 组合查询结果正确
- [ ] 置顶事件恒排最前，分页稳定无重复
- [ ] 全文搜索中英文均可命中，trigram 兜底生效
- [ ] `GET /events/{id}` 返回完整分析 + 来源列表，无 N+1 查询
- [ ] 隐藏事件对非 EDITOR 返回 404
- [ ] `PATCH /events/{id}` 运营干预生效，`manual_locked_fields` 正确写入，`audit_log` 完整
- [ ] Redis 榜单缓存生效且能正确失效
- [ ] 首页 Tab / 筛选条件同步 URL，刷新与分享保持状态
- [ ] 事件卡片流、骨架屏、空状态、分页完成
- [ ] 详情页完成：AI 分析全区块、雷达图、7 日曲线、来源列表、相关事件
- [ ] EDITOR 运营条完成：置顶/隐藏/编辑/拆分/合并/重跑
- [ ] 列表接口 P95 < 300ms（5000 事件数据量下压测）
- [ ] 单元测试：筛选组合、排序稳定性、权限过滤、缓存失效；覆盖率 ≥ 75%

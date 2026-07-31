# 清洗与去重聚合模块（pipeline）

所属项目: @SPEC.md
模块状态: ✅ 已完成
一期范围: ✅ 是
最后更新: 2026-07-30

---

## 功能目标

把 `source` 采集到的零散 `article`，加工成可展示的 **热点事件 `event`**：

1. **清洗**：去 HTML / 去广告 / 抽正文 / 归一化时间 / 提取作者、标签、关键词 / 生成粗摘要
2. **向量化**：调用 `ai-engine` 的 embedding 能力，为文章生成向量
3. **去重聚合**：三级级联把跨源的同一件事收敛成一个 `event`
4. **评分入榜**：算法计算 `heat_score`，融合 AI 打分得出 `recommend_index`

本模块是**唯一写 `event` 表的地方**（EDITOR 人工干预除外）。

> "OpenAI 发布 GPT" 被 机器之心 / InfoQ / Reddit / OpenAI Blog 各报一次
> → 聚合成 **1 个热点事件**，而不是 4 篇新闻。

---

## 数据库设计

### `article` 表

| 字段            | 类型          | 必填 | 说明                                                            |
| --------------- | ------------- | ---- | --------------------------------------------------------------- |
| id              | BIGSERIAL     | 是   | 主键                                                            |
| source_id       | BIGINT        | 是   | 采集源 ID                                                       |
| external_id     | VARCHAR(200)  | 是   | 源站唯一 ID                                                     |
| url             | VARCHAR(1000) | 是   | 归一化后的原文链接                                              |
| url_hash        | CHAR(64)      | 是   | `sha256(url)`，**全局唯一索引**                                 |
| title           | VARCHAR(500)  | 是   | 原始标题                                                        |
| title_hash      | CHAR(64)      | 是   | 归一化标题（去符号/小写/去停用词）的 sha256                     |
| raw_content     | TEXT          | 否   | 原始 HTML / 原始正文                                            |
| content         | TEXT          | 否   | 清洗后纯文本正文                                                |
| summary         | TEXT          | 否   | 抽取式粗摘要（非 AI，取前 3 句或 meta description）             |
| author          | VARCHAR(200)  | 否   | 作者                                                            |
| lang            | VARCHAR(8)    | 是   | `en` / `zh` / …                                                 |
| keywords        | JSONB         | 否   | 关键词数组 `["LLM","Agent"]`，默认 `[]`                          |
| metrics         | JSONB         | 否   | 互动指标 `{"points":320,"comments":88}`，默认 `{}`               |
| extra           | JSONB         | 否   | 源特有字段，默认 `{}`                                            |
| published_at    | TIMESTAMPTZ   | 是   | 发布时间（UTC）                                                 |
| fetched_at      | TIMESTAMPTZ   | 是   | 采集时间                                                        |
| status          | VARCHAR(32)   | 是   | `RAW`/`CLEANED`/`EMBEDDED`/`CLUSTERED`/`FAILED`/`DISCARDED`     |
| fail_reason     | VARCHAR(500)  | 否   | 处理失败原因                                                    |
| event_id        | BIGINT        | 否   | 归属的事件 ID（冗余，方便反查；权威关系在 `event_article`）      |
| created_at      | TIMESTAMPTZ   | -    | 创建时间                                                        |
| updated_at      | TIMESTAMPTZ   | -    | 更新时间                                                        |
| is_deleted      | BOOLEAN       | -    | 逻辑删除，默认 false                                            |

索引：
- `uk_article_url_hash(url_hash)` 唯一
- `idx_article_status(status) WHERE is_deleted=false`
- `idx_article_title_hash(title_hash)`
- `idx_article_published(published_at DESC)`
- `idx_article_title_trgm` — GIN `gin_trgm_ops` on `title`
- `idx_article_event(event_id)`

### `article_embedding` 表

| 字段         | 类型         | 必填 | 说明                                    |
| ------------ | ------------ | ---- | --------------------------------------- |
| id           | BIGSERIAL    | 是   | 主键                                    |
| article_id   | BIGINT       | 是   | 文章 ID，唯一                           |
| model        | VARCHAR(64)  | 是   | embedding 模型名，如 `bge-m3`           |
| dim          | SMALLINT     | 是   | 向量维度，默认 1024                     |
| embedding    | vector(1024) | 是   | pgvector 向量（title + summary 拼接生成）|
| created_at   | TIMESTAMPTZ  | -    | 创建时间                                |
| updated_at   | TIMESTAMPTZ  | -    | 更新时间                                |
| is_deleted   | BOOLEAN      | -    | 逻辑删除，默认 false                    |

索引：`uk_art_emb_article(article_id)`、HNSW `idx_art_emb_vec ON article_embedding USING hnsw (embedding vector_cosine_ops)`

### `event` 表

| 字段                | 类型          | 必填 | 说明                                                      |
| ------------------- | ------------- | ---- | --------------------------------------------------------- |
| id                  | BIGSERIAL     | 是   | 主键                                                      |
| title               | VARCHAR(500)  | 是   | 事件标题（默认取主文章标题，AI 分析后可能被改写）          |
| summary_one_line    | VARCHAR(300)  | 否   | 一句话总结（AI 产出）                                      |
| primary_article_id  | BIGINT        | 否   | 主文章 ID（源权重最高 + 正文最全的一篇）                   |
| region              | VARCHAR(32)   | 是   | `GLOBAL`/`CN`/`MIXED`（跨区域来源时为 MIXED）              |
| categories          | JSONB         | 是   | 分类数组，默认 `[]`。枚举见下方「分类枚举」                |
| source_count        | SMALLINT      | 是   | 关联的**不同采集源**数量，默认 1                           |
| article_count       | SMALLINT      | 是   | 关联的文章总数，默认 1                                     |
| heat_score          | NUMERIC(6,2)  | 是   | 热度分（算法计算），默认 0                                 |
| value_score         | SMALLINT      | 否   | 价值分 0-100（AI）                                         |
| originality_score   | SMALLINT      | 否   | 原创价值分 0-100（AI）                                     |
| trend_score         | SMALLINT      | 否   | 趋势分 0-100（AI）                                         |
| recommend_index     | NUMERIC(5,2)  | 是   | 推荐指数 0-100（加权综合），默认 0                         |
| first_seen_at       | TIMESTAMPTZ   | 是   | 首次出现时间（最早文章的 published_at）                    |
| last_seen_at        | TIMESTAMPTZ   | 是   | 最近一次有新来源加入的时间                                 |
| status              | VARCHAR(32)   | 是   | `PENDING_AI`/`ANALYZING`/`ANALYZED`/`ARCHIVED`/`AI_FAILED` |
| is_pinned           | BOOLEAN       | 是   | 是否置顶（EDITOR），默认 false                             |
| is_hidden           | BOOLEAN       | 是   | 是否隐藏（EDITOR），默认 false                             |
| is_manually_edited  | BOOLEAN       | 是   | 是否被人工编辑过，默认 false                               |
| manual_locked_fields| JSONB         | 是   | 人工锁定的字段名数组，AI 重跑不覆盖，默认 `[]`             |
| created_at          | TIMESTAMPTZ   | -    | 创建时间                                                   |
| updated_at          | TIMESTAMPTZ   | -    | 更新时间                                                   |
| is_deleted          | BOOLEAN       | -    | 逻辑删除，默认 false                                       |

索引：
- `idx_event_status(status)`
- `idx_event_recommend(recommend_index DESC, last_seen_at DESC) WHERE is_deleted=false AND is_hidden=false`
- `idx_event_heat(heat_score DESC)`
- `idx_event_last_seen(last_seen_at DESC)`
- `idx_event_categories` — GIN on `categories`
- `idx_event_title_trgm` — GIN `gin_trgm_ops` on `title`

### `event_article` 表

| 字段         | 类型          | 必填 | 说明                                          |
| ------------ | ------------- | ---- | --------------------------------------------- |
| id           | BIGSERIAL     | 是   | 主键                                          |
| event_id     | BIGINT        | 是   | 事件 ID                                       |
| article_id   | BIGINT        | 是   | 文章 ID                                       |
| match_level  | VARCHAR(32)   | 是   | `FINGERPRINT`/`TITLE`/`VECTOR`/`MANUAL`       |
| similarity   | NUMERIC(5,4)  | 否   | 匹配相似度（`FINGERPRINT` 为 1.0）            |
| is_primary   | BOOLEAN       | 是   | 是否主文章，默认 false                        |
| created_at   | TIMESTAMPTZ   | -    | 创建时间                                      |
| updated_at   | TIMESTAMPTZ   | -    | 更新时间                                      |
| is_deleted   | BOOLEAN       | -    | 逻辑删除，默认 false                          |

索引：`uk_event_article(event_id, article_id)` 唯一、`idx_ea_article(article_id)`

### `tag` 表

| 字段        | 类型         | 必填 | 说明                                       |
| ----------- | ------------ | ---- | ------------------------------------------ |
| id          | BIGSERIAL    | 是   | 主键                                       |
| name        | VARCHAR(100) | 是   | 标签名（归一化：小写、去空格），全局唯一   |
| display_name| VARCHAR(100) | 是   | 展示名（保留原始大小写，如 `LangGraph`）   |
| type        | VARCHAR(32)  | 是   | `TECH`/`COMPANY`/`PRODUCT`/`PERSON`/`OTHER`|
| event_count | INTEGER      | 是   | 关联事件数（冗余计数），默认 0             |
| created_at  | TIMESTAMPTZ  | -    | 创建时间                                   |
| updated_at  | TIMESTAMPTZ  | -    | 更新时间                                   |
| is_deleted  | BOOLEAN      | -    | 逻辑删除，默认 false                       |

索引：`uk_tag_name(name)`、`idx_tag_count(event_count DESC)`

### `event_tag` 表

| 字段       | 类型         | 必填 | 说明                                      |
| ---------- | ------------ | ---- | ----------------------------------------- |
| id         | BIGSERIAL    | 是   | 主键                                      |
| event_id   | BIGINT       | 是   | 事件 ID                                   |
| tag_id     | BIGINT       | 是   | 标签 ID                                   |
| weight     | NUMERIC(4,3) | 是   | 标签权重 0-1，默认 1.0                    |
| created_at | TIMESTAMPTZ  | -    | 创建时间                                  |
| updated_at | TIMESTAMPTZ  | -    | 更新时间                                  |
| is_deleted | BOOLEAN      | -    | 逻辑删除，默认 false                      |

索引：`uk_event_tag(event_id, tag_id)` 唯一、`idx_et_tag(tag_id)`

---

## 分类枚举（`categories`）

固定 11 个，与需求文档一致：

`AI` · `AGENT` · `LLM` · `MCP` · `PROGRAMMING` · `OPENSOURCE` · `PAPER` · `STARTUP` · `HARDWARE` · `INTERNET` · `BUSINESS`

一个事件可属于多个分类（数组），由 AI 判定。

---

## 处理流水线

### 阶段 1：清洗 `pipeline.clean_task(article_ids)`

输入：`status=RAW` 的文章
处理步骤（顺序执行，任一步失败降级但不中断）：

| 步骤       | 实现                                                                       |
| ---------- | -------------------------------------------------------------------------- |
| 正文抽取   | `raw_content` 为空 → 用 httpx 二次抓原文；再用 `trafilatura.extract()` 抽正文 |
| 去 HTML    | `bleach.clean(strip=True)` 兜底，去除残留标签                              |
| 去广告     | 规则库匹配删除：`赞助内容`/`广告`/`点击关注`/`Sponsored`/`Advertisement` 段落 |
| 时间归一化 | `dateutil.parser` 解析 → 统一转 UTC；解析失败用 `fetched_at`               |
| 作者提取   | 优先插件给的 `author`；否则从 `<meta name="author">` / JSON-LD 提取         |
| 标签提取   | 从 `<meta name="keywords">` / 原站分类 + 规则词典（技术名词表）匹配        |
| 关键词提取 | 中文 `jieba.analyse.textrank`，英文 `yake`，各取 Top 10                     |
| 粗摘要     | `meta description` 优先；否则取正文前 3 句（≤ 300 字），**非 AI 生成**       |

产出：`status = CLEANED`

**丢弃规则**（置 `DISCARDED`）：
- 正文 < 100 字符 **且** 标题 < 10 字符
- 标题命中垃圾词黑名单（可后台配置）
- `published_at` 早于 7 天前
- 语言不在 `["en","zh"]` 白名单内

### 阶段 2：向量化 `pipeline.embed_task(article_ids)`

- 输入文本：`f"{title}\n{summary[:500]}"`
- 调用 `ai-engine.embed(texts)` → 批量（每批 32 条）
- 写入 `article_embedding`，`status = EMBEDDED`
- 失败重试 3 次，仍失败置 `FAILED` 并记 `fail_reason`

### 阶段 3：去重聚合 `pipeline.dedupe_task()` —— 三级级联

对每篇 `status=EMBEDDED` 的文章，**按 `published_at` 升序**逐篇处理：

```
Level 1 · 指纹匹配（精确，零成本）
  ├─ url_hash 已存在 → 该文章本就不该入库（采集层已挡），跳过
  └─ title_hash 在候选窗口内命中已有文章 → 直接挂到该文章的 event
     match_level = FINGERPRINT, similarity = 1.0
  └─ 未命中 → 进 Level 2

Level 2 · 标题相似（粗筛，pg_trgm）
  SELECT a.id, a.event_id, similarity(a.title, :title) AS sim
  FROM article a
  WHERE a.published_at BETWEEN :t - INTERVAL '72 hours' AND :t + INTERVAL '72 hours'
    AND a.event_id IS NOT NULL
    AND a.title % :title                      -- trigram 索引加速
  ORDER BY sim DESC LIMIT 20;
  ├─ sim > 0.75 → 判定同一事件，match_level = TITLE
  └─ 0.35 < sim ≤ 0.75 → 作为候选集进 Level 3
  └─ 无任何候选 → 进 Level 3（用全库向量检索）

Level 3 · 向量相似（精判，pgvector 余弦）
  SELECT e.id, 1 - (ae.embedding <=> :vec) AS cos
  FROM article_embedding ae JOIN article a ON a.id = ae.article_id
  WHERE a.event_id IS NOT NULL
    AND a.published_at BETWEEN :t - INTERVAL '72 hours' AND :t + INTERVAL '72 hours'
  ORDER BY ae.embedding <=> :vec LIMIT 10;
  ├─ cos > dedupe_vector_threshold（默认 0.85）→ 合并，match_level = VECTOR
  └─ 否则 → 新建 event
```

**合并动作**：
1. 写 `event_article`（含 `match_level` / `similarity`）
2. `article.event_id = event.id`，`status = CLUSTERED`
3. 重算 `event.source_count` / `article_count` / `region`
4. `event.last_seen_at = max(last_seen_at, article.published_at)`
5. 重选 `primary_article_id`（见业务规则）
6. 若 `event.status = ANALYZED` 且新增来源使 `source_count` 增加 → 重置为 `PENDING_AI` 触发重新分析

**新建动作**：创建 `event`（`status=PENDING_AI`，`first_seen_at = last_seen_at = article.published_at`），写关联，标 `is_primary=true`

### 阶段 4：AI 分析（由 `ai-engine` 执行，见 @doc/SPEC-ai-engine.md）

`pipeline` 只负责把 `status=PENDING_AI` 的事件投递给 `ai-engine.analyze_event_task`。

### 阶段 5：评分入榜 `pipeline.rank_task()`

**热度分（纯算法，不走 AI）**

```
heat_score = 100 × normalize( source_weight_sum × source_diversity × engagement × freshness )

source_weight_sum = Σ(该事件所有不同来源的 source.weight)          # 1..~50
source_diversity  = 1 + log2(source_count)                          # 单源=1, 4源=3
engagement        = 1 + log10(1 + Σ 各文章 metrics 归一化互动数)
freshness         = exp(-Δh / 24)   # Δh = 距 last_seen_at 的小时数，24h 衰减到 0.37

normalize: 对当日全量事件做 min-max 归一化到 [0,1]
```

各 `metrics` 归一化权重（可在 `system_config` 调）：
`points × 1.0` + `comments × 2.0` + `stars × 0.5` + `upvotes × 1.0`

**推荐指数**

```
recommend_index = 0.35 × heat_score
                + 0.30 × value_score
                + 0.20 × originality_score
                + 0.15 × trend_score
```
四个权重存 `system_config.rank_weights`，ADMIN 可调，改后触发全量重算。
AI 分数缺失（`AI_FAILED`）时，按已有分数重新归一化权重。

**归档**：`last_seen_at` 超过 72 小时且无新来源 → `status = ARCHIVED`（仍可查询，但不进"今日/本周"实时榜）

---

## 后端接口

> 事件的**读取**接口在 @doc/SPEC-hotspot.md。本模块只暴露运维与人工干预接口。

### POST /api/v1/events/{id}/split
**说明**: 拆分错误聚合——把指定文章从事件中移出，另立新事件。`EDITOR` 及以上

**Request Body**:
```json
{ "articleIds": [1024, 1025], "newEventTitle": "另一个事件的标题" }
```

**Response 200**:
```json
{ "sourceEvent": { "id": 88, "articleCount": 3 },
  "newEvent": { "id": 91, "articleCount": 2, "status": "PENDING_AI" } }
```

**错误情况**:
- 文章不属于该事件 → `400` `ARTICLE_NOT_IN_EVENT`
- 拆走全部文章 → `400` `CANNOT_SPLIT_ALL`

---

### POST /api/v1/events/merge
**说明**: 合并两个事件——把 `sourceId` 的所有文章并入 `targetId`，`sourceId` 软删除。`EDITOR` 及以上

**Request Body**: `{ "sourceId": 91, "targetId": 88 }`

**Response 200**: 合并后的 target 事件对象

**错误情况**:
- `sourceId == targetId` → `400` `CANNOT_MERGE_SELF`
- 任一事件不存在 → `404` `EVENT_NOT_FOUND`

---

### POST /api/v1/admin/pipeline/rerun
**说明**: 手动重跑流水线某阶段。`EDITOR` 及以上

**Request Body**:
```json
{ "stage": "CLEAN", "scope": "ARTICLE", "ids": [1024], "since": null }
```
- `stage`: `CLEAN` / `EMBED` / `DEDUPE` / `RANK`
- `scope`: `ARTICLE` / `EVENT` / `SOURCE` / `ALL`
- `since`: ISO 时间，`scope=ALL` 时限定范围，防止误触发全量

**Response 202**: `{ "taskId": "...", "affectedCount": 1 }`

**错误情况**: `scope=ALL` 且 `since` 为空 → `400` `FULL_RERUN_REQUIRES_SINCE`

---

### GET /api/v1/admin/pipeline/stats
**说明**: 流水线健康度。`EDITOR` 及以上

**Response 200**:
```json
{
  "articleByStatus": { "RAW": 12, "CLEANED": 5, "EMBEDDED": 3,
                       "CLUSTERED": 8420, "FAILED": 7, "DISCARDED": 331 },
  "eventByStatus": { "PENDING_AI": 4, "ANALYZED": 1203, "ARCHIVED": 5891, "AI_FAILED": 2 },
  "todayNewArticles": 412,
  "todayNewEvents": 87,
  "avgSourcePerEvent": 1.83,
  "dedupeRate": 0.42,
  "matchLevelDistribution": { "FINGERPRINT": 120, "TITLE": 380, "VECTOR": 265, "MANUAL": 9 }
}
```

---

## 前端页面

> 本模块无独立用户页面，能力嵌入其他页面：

### 事件详情页的运营区（EDITOR 可见，见 @doc/SPEC-hotspot.md）
- 来源文章列表每行显示 `matchLevel` Badge + `similarity`（如 `向量 0.891`）
- 每行 checkbox → 选中后底部浮出「拆分为新事件」按钮
- 顶部「合并到其他事件」按钮 → 打开事件搜索 Combobox 选目标

### 流水线监控（`/admin/pipeline`，EDITOR）
- 顶部横向漏斗图（ECharts funnel）：RAW → CLEANED → EMBEDDED → CLUSTERED
- 状态分布饼图 ×2（article / event）
- 关键指标卡：今日新增文章 / 今日新增事件 / 平均来源数 / 去重率
- 匹配层级分布柱状图（判断阈值是否合理）
- 「重跑」面板：阶段下拉 + 范围下拉 + ID 输入 / 时间选择，`scope=ALL` 时强制填时间
- 失败文章表格：文章标题、来源、失败阶段、`failReason`、单条重跑按钮

---

## 业务规则

### 主文章选择
按优先级依次比较，取最优：
1. 官方/一手来源优先（`source.category = BLOG` 且 `region` 与事件主导区域一致）
2. `source.weight` 更高
3. `content` 长度更长
4. `published_at` 更早（首发优先）

### 事件区域判定
- 全部来源 `region=GLOBAL` → `GLOBAL`
- 全部来源 `region=CN` → `CN`
- 混合 → `MIXED`（同时出现在"全球热点"和"国内热点"榜单）

### 阈值配置（`system_config`，ADMIN 可调，改后不追溯已聚合数据）
| 键                          | 默认值 | 说明                     |
| --------------------------- | ------ | ------------------------ |
| `dedupe_title_threshold`    | 0.75   | 标题相似度直接合并阈值   |
| `dedupe_title_candidate`    | 0.35   | 进入向量判定的候选阈值   |
| `dedupe_vector_threshold`   | 0.85   | 向量余弦相似度合并阈值   |
| `dedupe_time_window_hours`  | 72     | 聚合时间窗口             |
| `event_archive_hours`       | 72     | 事件归档阈值             |
| `article_max_age_days`      | 7      | 超龄文章丢弃阈值         |

### 人工编辑保护
- EDITOR 编辑 `title` / `summary_one_line` / `categories` 后，字段名写入 `manual_locked_fields`
- 后续 AI 重跑时，**跳过 `manual_locked_fields` 中的字段**，只更新未锁定字段
- `is_manually_edited = true` 的事件在前端显示"已人工校对"小标

### 幂等与并发
- 所有 pipeline 任务必须**幂等**：重复执行不产生重复数据
- `dedupe_task` 全局唯一锁 `lock:pipeline:dedupe`，同时只允许一个实例运行
- 单篇文章的聚合在一个数据库事务内完成，失败整体回滚
- `event` 的计数字段（`source_count`/`article_count`）用 `SELECT ... FOR UPDATE` 保证并发正确

### 性能
- `dedupe_task` 每批处理 200 篇，单批超过 60 秒记警告日志
- 向量检索必须走 HNSW 索引，禁止全表扫描（用 `EXPLAIN` 在测试中断言）
- `heat_score` 归一化只对"最近 72 小时活跃事件"计算，避免全表

---

## 完成标准

- [ ] `article` / `article_embedding` / `event` / `event_article` / `tag` / `event_tag` 表与迁移完成
- [ ] pgvector 扩展与 HNSW 索引、pg_trgm 扩展与 GIN 索引创建成功
- [ ] 清洗流水线 8 个步骤全部实现，任一步失败可降级不中断
- [ ] 正文抽取准确率人工抽检 ≥ 90%（抽 50 篇）
- [ ] 丢弃规则生效，垃圾内容不进入聚合
- [ ] 向量化批量调用，失败重试生效
- [ ] 三级级联去重实现，`match_level` 与 `similarity` 正确记录
- [ ] 跨源聚合正确率人工抽检 ≥ 85%，误合并率 ≤ 5%（构造 100 条测试集）
- [ ] `heat_score` 与 `recommend_index` 计算正确，权重可配置且改后可重算
- [ ] 事件归档逻辑生效
- [ ] 拆分 / 合并接口正确，计数字段同步更新
- [ ] 人工锁定字段在 AI 重跑时不被覆盖
- [ ] 所有任务幂等，重复执行不产生脏数据
- [ ] 流水线监控页完成
- [ ] 单元测试：清洗各步骤、三级匹配逻辑、评分公式、主文章选择、拆分合并；覆盖率 ≥ 85%

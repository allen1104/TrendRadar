# 趋势分析模块（trend）

所属项目: @SPEC.md
模块状态: ✅ 已完成
一期范围: — 二期
最后更新: 2026-08-02

---

## 功能目标

从"看单个热点"升级到"看趋势走向"。基于历史事件数据做时间序列统计，回答：

- 最近 7 天 / 30 天 / 一年，**哪些关键词增长最快**
- **哪些公司最热门**（OpenAI vs Anthropic vs Google）
- **哪些项目增长最快**（GitHub 项目、开源框架）
- **哪些技术最热门**（Agent / RAG / MCP / 多模态）

产出三类可视化：**趋势图** · **词云** · **排行榜**

---

## 数据库设计

### `event_daily_snapshot` 表

事件每日快照，是所有趋势计算的基础事实表。由 `pipeline.rank_task` 每次运行时写入。

| 字段          | 类型         | 必填 | 说明                                  |
| ------------- | ------------ | ---- | ------------------------------------- |
| id            | BIGSERIAL    | 是   | 主键                                  |
| event_id      | BIGINT       | 是   | 事件 ID                               |
| stat_date     | DATE         | 是   | 统计日期（UTC）                       |
| heat_score    | NUMERIC(6,2) | 是   | 当日热度分                            |
| recommend_index | NUMERIC(5,2)| 是   | 当日推荐指数                          |
| source_count  | SMALLINT     | 是   | 当日来源数                            |
| article_count | SMALLINT     | 是   | 当日文章数                            |
| created_at    | TIMESTAMPTZ  | -    | 创建时间                              |
| updated_at    | TIMESTAMPTZ  | -    | 更新时间                              |
| is_deleted    | BOOLEAN      | -    | 逻辑删除，默认 false                  |

索引：`uk_snapshot_event_date(event_id, stat_date)` 唯一、`idx_snapshot_date(stat_date)`

> 保留 400 天（覆盖"最近一年"查询）。

### `keyword_trend` 表

关键词按日统计。由 `trend.aggregate_task` 每日凌晨计算。

| 字段          | 类型         | 必填 | 说明                                          |
| ------------- | ------------ | ---- | --------------------------------------------- |
| id            | BIGSERIAL    | 是   | 主键                                          |
| keyword       | VARCHAR(100) | 是   | 关键词（归一化：小写去空格）                  |
| display_name  | VARCHAR(100) | 是   | 展示名                                        |
| stat_date     | DATE         | 是   | 统计日期                                      |
| event_count   | INTEGER      | 是   | 当日关联事件数，默认 0                        |
| article_count | INTEGER      | 是   | 当日关联文章数，默认 0                        |
| heat_sum      | NUMERIC(10,2)| 是   | 当日关联事件热度之和，默认 0                  |
| created_at    | TIMESTAMPTZ  | -    | 创建时间                                      |
| updated_at    | TIMESTAMPTZ  | -    | 更新时间                                      |
| is_deleted    | BOOLEAN      | -    | 逻辑删除，默认 false                          |

索引：`uk_kw_trend(keyword, stat_date)` 唯一、`idx_kw_trend_date(stat_date, event_count DESC)`

### `entity_trend` 表

实体（公司 / 项目 / 技术 / 人物）按日统计。结构同 `keyword_trend`，多一个类型维度。

| 字段          | 类型         | 必填 | 说明                                                    |
| ------------- | ------------ | ---- | ------------------------------------------------------- |
| id            | BIGSERIAL    | 是   | 主键                                                    |
| tag_id        | BIGINT       | 是   | 关联 `tag.id`                                           |
| entity_type   | VARCHAR(32)  | 是   | `COMPANY`/`PRODUCT`/`TECH`/`PERSON`（同 `tag.type`）    |
| stat_date     | DATE         | 是   | 统计日期                                                |
| event_count   | INTEGER      | 是   | 当日关联事件数，默认 0                                  |
| heat_sum      | NUMERIC(10,2)| 是   | 当日热度之和，默认 0                                    |
| avg_value_score | NUMERIC(5,2)| 否  | 当日关联事件的平均价值分                                |
| created_at    | TIMESTAMPTZ  | -    | 创建时间                                                |
| updated_at    | TIMESTAMPTZ  | -    | 更新时间                                                |
| is_deleted    | BOOLEAN      | -    | 逻辑删除，默认 false                                    |

索引：`uk_entity_trend(tag_id, stat_date)` 唯一、`idx_entity_trend_type_date(entity_type, stat_date, event_count DESC)`

---

## 增长率算法

**核心指标：增长率（Growth Rate）**

```
对时间窗口 W（7/30/365 天）：
  current  = Σ event_count(最近 W 天)
  previous = Σ event_count(前一个 W 天)

  growth_rate = (current - previous) / max(previous, 1)      # 相对增长
  growth_abs  = current - previous                            # 绝对增长

  # 综合增长分：兼顾相对增长与绝对量级，避免小基数噪声
  growth_score = log10(1 + current) × min(growth_rate, 5.0)
```

**新兴指标（Emerging）**：`previous == 0 且 current >= 3` → 标记 `isNew=true`，
排行榜单独开「新出现」分组，避免它们的无穷大增长率污染主榜。

**热度指标**：`heat_sum` 直接作为"最热门"排序依据（区别于"增长最快"）。

**平滑**：日粒度数据做 3 日移动平均后再算增长率，抑制单日抖动。

---

## 后端接口

### GET /api/v1/trends/keywords
**说明**: 关键词趋势排行。`GUEST` 可访问

**Query**:
| 参数     | 类型 | 默认        | 说明                                        |
| -------- | ---- | ----------- | ------------------------------------------- |
| `window` | enum | `7D`        | `7D` / `30D` / `1Y`                         |
| `metric` | enum | `GROWTH`    | `GROWTH`（增长最快）/ `HOT`（最热门）       |
| `limit`  | int  | `20`        | 最大 100                                    |
| `includeNew` | bool | `true`  | 是否包含新出现的关键词                      |

**Response 200**:
```json
{
  "window": "7D",
  "metric": "GROWTH",
  "items": [
    {
      "keyword": "mcp",
      "displayName": "MCP",
      "current": 42, "previous": 8,
      "growthRate": 4.25, "growthAbs": 34, "growthScore": 6.94,
      "heatSum": 3210.5,
      "isNew": false,
      "series": [
        { "date": "2026-07-23", "eventCount": 3 },
        { "date": "2026-07-24", "eventCount": 5 }
      ]
    }
  ],
  "newcomers": [
    { "keyword": "gpt-5", "displayName": "GPT-5", "current": 12, "isNew": true }
  ]
}
```

---

### GET /api/v1/trends/entities
**说明**: 实体趋势排行（公司 / 项目 / 技术）

**Query**: `window` `metric` `entityType`（`COMPANY`/`PRODUCT`/`TECH`/`PERSON`/`ALL`）`limit`

**Response 200**:
```json
{
  "window": "30D",
  "entityType": "COMPANY",
  "items": [
    {
      "tagId": 12, "displayName": "OpenAI", "entityType": "COMPANY",
      "current": 128, "previous": 96,
      "growthRate": 0.333, "growthAbs": 32, "growthScore": 0.70,
      "heatSum": 11204.8, "avgValueScore": 82.4,
      "series": [{ "date": "2026-07-01", "eventCount": 4, "heatSum": 320.5 }]
    }
  ]
}
```

---

### GET /api/v1/trends/wordcloud
**说明**: 词云数据

**Query**: `window` `limit`（默认 100，最大 300）`type`（`KEYWORD`/`ENTITY`/`ALL`）

**Response 200**:
```json
{
  "window": "7D",
  "items": [
    { "text": "Agent", "value": 128, "type": "TECH", "growthRate": 0.42, "tagId": 34 },
    { "text": "OpenAI", "value": 96, "type": "COMPANY", "growthRate": 0.15, "tagId": 12 }
  ]
}
```
> `value` = 归一化后的 `heat_sum`（0-100），前端据此定字号；`growthRate` 决定颜色（正=暖色、负=冷色）

---

### GET /api/v1/trends/overview
**说明**: 趋势总览（趋势页首屏）

**Query**: `window`

**Response 200**:
```json
{
  "window": "7D",
  "summary": {
    "totalEvents": 612,
    "totalArticles": 2840,
    "avgEventsPerDay": 87.4,
    "eventGrowthRate": 0.18
  },
  "dailySeries": [
    { "date": "2026-07-23", "eventCount": 78, "articleCount": 340, "avgRecommend": 62.4 }
  ],
  "categoryDistribution": [
    { "category": "AI", "count": 240, "growthRate": 0.22 }
  ],
  "regionDistribution": [
    { "region": "GLOBAL", "count": 380 },
    { "region": "CN", "count": 190 },
    { "region": "MIXED", "count": 42 }
  ],
  "topRisingKeywords": [{ "displayName": "MCP", "growthRate": 4.25 }],
  "topCompanies": [{ "displayName": "OpenAI", "current": 128 }],
  "topProjects": [{ "displayName": "LangGraph", "current": 34, "growthRate": 1.83 }]
}
```

---

### GET /api/v1/trends/keywords/{keyword}
**说明**: 单个关键词的详细趋势（下钻页）

**Query**: `window`

**Response 200**:
```json
{
  "keyword": "mcp",
  "displayName": "MCP",
  "window": "30D",
  "series": [{ "date": "2026-07-01", "eventCount": 2, "articleCount": 5, "heatSum": 120.4 }],
  "growthRate": 4.25,
  "relatedKeywords": [{ "displayName": "Agent", "coOccurrence": 28 }],
  "topEvents": [
    { "id": 88, "title": "Anthropic 发布 MCP 1.0", "recommendIndex": 91.2,
      "lastSeenAt": "2026-07-28T10:00:00Z" }
  ]
}
```

---

## 前端页面

### 趋势分析（`/trends`）

**顶部控制区**
- 时间窗口 Segmented：`最近 7 天` `最近 30 天` `最近一年`
- 同步到 URL SearchParams

**第一屏 · 总览**
- 4 个指标卡：总事件数 / 总文章数 / 日均事件 / 环比增长（带 ↑↓ 箭头与百分比）
- **大图：每日事件量趋势**（ECharts line + area，双 Y 轴：事件数 + 平均推荐指数）
  - 支持 dataZoom 缩放
  - hover 显示当日 Top 3 事件（tooltip 自定义渲染）
- **分类分布**（ECharts 玫瑰图）+ **区域分布**（ECharts 环形图），并排

**第二屏 · 关键词趋势**
- Tab 切换：`增长最快` / `最热门`
- **左侧：排行榜表格**
  - 列：排名（前三名奖牌图标）、关键词、当前值、增长率（带彩色箭头）、迷你走势图（sparkline）
  - 「新出现」的关键词标 🆕 Badge，可折叠单独分组
  - 点击行 → 右侧图表联动显示该关键词曲线
- **右侧：多关键词对比折线图**
  - 默认展示 Top 5，可从左侧表格勾选最多 8 个对比
  - 图例可点击隐藏/显示

**第三屏 · 实体排行**
- 三列并排卡片，每列一个 Tab 组：
  - **最热门公司**：横向条形图（ECharts bar，带 logo）
  - **增长最快项目**：卡片列表（项目名 + 增长率 + 迷你曲线）
  - **最热门技术**：气泡图（ECharts scatter，X=当前热度，Y=增长率，气泡大小=事件数）
- 每项可点击下钻到 `/trends/keywords/{keyword}`

**第四屏 · 词云**
- ECharts wordCloud（`echarts-wordcloud` 插件）
- 字号 = 热度，颜色 = 增长率（红→暖=上升，蓝→冷=下降）
- 点击词条 → 跳转热点中心并按该标签筛选
- 右上角切换：全部 / 仅关键词 / 仅实体

### 关键词下钻页（`/trends/keywords/:keyword`）
- 头部：关键词大标题 + 类型 Badge + 窗口选择
- 主图：该关键词的事件数/文章数/热度三线图
- 「共现关键词」网络图（ECharts graph，力导向布局）
- 「相关热点事件」列表（复用事件卡片组件）

---

## 业务规则

### 数据聚合
- `trend.aggregate_task` 每日 02:00 执行，计算**前一天**的 `keyword_trend` 与 `entity_trend`
- 关键词来源：`article.keywords` 聚合 + `event_analysis.tags`
- 实体来源：`event_tag` 关联的 `tag`（按 `tag.type` 分类）
- 聚合用 `INSERT ... ON CONFLICT (keyword, stat_date) DO UPDATE`，保证幂等可重跑
- 首次部署或补数据时支持 `POST /admin/tasks/trigger` 指定日期范围回填

### 关键词归一化
- 统一小写、去首尾空白、连字符与下划线归一（`gpt-5` / `gpt_5` / `GPT 5` → `gpt-5`）
- 同义词映射表存 `system_config.keyword_aliases`（如 `大语言模型` → `llm`）
- 停用词过滤：`system_config.keyword_stopwords`（`ai`、`技术`、`模型` 这类过泛词单独配置）
- 单字符关键词直接丢弃

### 计算与缓存
- 排行榜结果缓存 Redis，key `trend:{type}:{window}:{metric}:{limit}`，TTL 1 小时
- `aggregate_task` 完成后主动失效 `trend:*`
- "最近一年"窗口的查询走预聚合月表（`mv_keyword_trend_monthly` 物化视图），避免扫描 365 天明细
- 单次查询扫描行数上限 100 万，超出则降级到物化视图

### 噪声抑制
- `event_count < 3` 的关键词不进排行榜（可配 `trend_min_event_count`）
- 增长率上限截断为 5.0（500%），避免小基数刷榜
- 3 日移动平均平滑

### 数据保留
- `event_daily_snapshot` 保留 400 天
- `keyword_trend` / `entity_trend` 保留 400 天
- 超期数据在 `cleanup_task` 中删除；删除前按月聚合归档到物化视图

---

## 完成标准

- [ ] `event_daily_snapshot` / `keyword_trend` / `entity_trend` 表与迁移完成
- [ ] `rank_task` 每次运行写入当日快照，幂等
- [ ] `trend.aggregate_task` 每日聚合，可指定日期回填，重跑不产生重复
- [ ] 关键词归一化 + 同义词映射 + 停用词过滤生效
- [ ] 增长率算法实现，含 3 日平滑、上限截断、新兴标记
- [ ] 4 个查询接口全部完成，`window` 三档均正确
- [ ] "最近一年"查询走物化视图，响应 < 500ms
- [ ] Redis 缓存生效且能正确失效
- [ ] 趋势页四屏全部完成：总览、关键词趋势、实体排行、词云
- [ ] 多关键词对比折线图联动正确
- [ ] 词云点击可跳转筛选
- [ ] 关键词下钻页完成，含共现网络图
- [ ] 单元测试：增长率计算、归一化、平滑、边界（previous=0、单日数据）；覆盖率 ≥ 75%

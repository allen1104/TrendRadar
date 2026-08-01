# Trend 模块（二期）

> 趋势分析。从「看单个热点」升级到「看趋势走向」。
>
> 需求：[doc/SPEC-trend.md](../../../doc/SPEC-trend.md)

## 状态

✅ 已完成 · 2026-08-02

## 模块文件

```
app/modules/trend/
  enums.py         TrendWindow / TrendMetric / EntityType
  exceptions.py    4 个 400 业务异常（window / metric / entityType / limit）
  model.py         EventDailySnapshot + KeywordTrend + EntityTrend
  schema.py        14 个 DTO（Keyword / Entity / WordCloud / Overview / Detail）
  repository.py    EventDailySnapshotRepository + KeywordTrendRepository + EntityTrendRepository（PG/SQLite 双 dialect 兼容 upsert）
  service.py       TrendService（7 个方法：3 个聚合任务 + 5 个查询入口 + 纯函数：normalize_keyword / growth_score / _smooth / window_to_dates）
  api.py           5 个 GET 路由
  tasks.py         trend.aggregate_task (02:00) + trend.cleanup_old_trends (04:00) + Celery 调度
```

测试：`backend/tests/trend/` — 3 文件，51 用例（enums 7 + service 32 + api 12）。

## 接口清单（5 个，GUEST 可访问）

| 方法 | 路径 | 错误码 |
|------|------|--------|
| `GET /api/v1/trends/keywords` | 关键词趋势排行（GROWTH/HOT） | `400 TREND_WINDOW_INVALID` · `400 TREND_METRIC_INVALID` · `400 TREND_LIMIT_OUT_OF_RANGE` |
| `GET /api/v1/trends/entities` | 实体趋势排行（COMPANY/PRODUCT/TECH/PERSON/ALL） | `400 ENTITY_TYPE_INVALID` |
| `GET /api/v1/trends/wordcloud` | 词云数据 | — |
| `GET /api/v1/trends/overview` | 趋势总览（4 卡 + 日时序 + 分类 + 区域 + Top 3） | — |
| `GET /api/v1/trends/keywords/{kw}` | 关键词下钻（曲线 + 共现词 + 相关事件） | — |

## 关键算法

```
增长率：
  raw_rate = (current - previous) / max(previous, 1)
  rate     = min(raw_rate, 5.0)              # 上限截断
  abs_g    = current - previous
  score    = log10(1 + current) × min(rate, 5.0)

新出现（emerging）：
  previous == 0 且 current >= 3 → isNew = true

归一化：
  keyword → normalize_keyword(s)             # 小写 + 空白/连字符/下划线 → '-'
  + is_stopword(k)                            # 1 字符 + 默认停用词集（ai/技术/模型/the/a/an）

窗口：7D / 30D / 1Y
  current = [today - (W-1), today]
  prev    = [current_start - W, current_start - 1]
```

## 关键业务规则

1. **聚合幂等**：3 个表全部 `ON CONFLICT DO UPDATE`（PG）/ select-then-update（SQLite 测试库）；重跑不产生重复
2. **每日 02:00**：`trend.aggregate_task` 计算前一天 keyword_trend + entity_trend + event_daily_snapshot
3. **每日 04:00**：`trend.cleanup_old_trends` 物理删 400 天前的 trend 数据
4. **GUEST 可访问**：所有 5 个查询接口无需登录；frontend 直接展示
5. **跨模块引用**：`aggregate_entity` 跨模块 join `event_tag`（pipeline.model）和 `event_analysis`（ai.model）
6. **跨模块调用**：不在本模块 service 内调其他 module 的 service（保持单向数据流：pipeline → trend）
7. **环境兼容**：repository 层检测 dialect（`session.get_bind().dialect.name`），PG 用 upsert/SQLite 用 select-then-update；本地 pytest 跑 SQLite，生产跑 PG 一致行为
8. **下钻共现词**：keyword_detail 返回与目标关键词同日出现的其他关键词 Top 10（counter dict）

## 与其他模块的关系

- **pipeline.model.Event**：聚合任务读取 `keywords`/`heat_score`/`last_seen_at`
- **pipeline.model.event_tag + tag**：entity 聚合 join 这两张表取 `tag_id` + `tag.type`
- **ai.model.EventAnalysis**：entity 聚合 join 取 `value_score` 算 avg
- **admin.configs**：`keyword_aliases` / `keyword_stopwords` / `trend_min_event_count`（3 个 TREND 配置项 seed 已加）
- **celery_app.beat_schedule**：注册 `trend-aggregate-daily` (02:00) + `trend-cleanup-old` (04:00)

## 验证状态

| 时间 | 验证项 | 结果 |
|------|--------|------|
| 2026-08-02 | Alembic migration `20260731_0007_trend_tables.py` | 3 张表创建成功 |
| 2026-08-02 | 单测：test_enums (7) + test_service (32) + test_api (12) | 51 passed |
| 2026-08-02 | 全栈无回归 | 372 passed |
| 2026-08-02 | `ruff check app/modules/trend/` | All checks passed |
| 2026-08-02 | `pnpm typecheck` | exit 0 |
| 2026-08-02 | `pnpm build` | 1.65 MB / 530 KB gzip |
| 2026-08-02 | OpenAPI: 5 个 trend 端点注册到 `/api/v1/trends/*` | ✅ |

## 不在 MVP 范围（SPEC 列但本期末做）

- ❌ Redis 缓存（先不上；聚合数据 02:00 才更新一次，缓存收益不大）
- ❌ 月度物化视图（`mv_keyword_trend_monthly`，1Y 查询走明细数据即可）
- ❌ 完整 entity_type=ALL 优化（目前 ALL 全表扫描 + 类型过滤；上线后再加索引/视图）
- ❌ 同义词映射 `keyword_aliases` 实际生效（结构已 seed，service 暂未消费）
- ❌ 排序切换的「最热门」联动到 entity 排行榜（默认只 GROWTH）
- ❌ 共现网络图（graph layout）前端
- ❌ 趋势 Top 词的「详情页跳转」外链（已实现）
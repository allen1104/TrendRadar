# pipeline 模块（清洗 / 去重聚合 / 评分入榜）

> 需求：[doc/SPEC-pipeline.md](../../../doc/SPEC-pipeline.md)
> 唯一把 source 抓到的零散 article 加工成"热点事件 event"的模块。

---

## 提供给其他模块的能力

- **数据表**：`article` / `article_embedding` / `event` / `event_article` / `tag` / `event_tag`
- **流水线**：5 个 Celery 任务，链式触发 `clean → embed → dedupe → analyze → rank`
- **运维 API**：`/admin/pipeline/{rerun, stats}`（EDITOR）+ `/events/{id}/split` + `/events/merge`（EDITOR）
- **PG 扩展依赖**：pgvector（向量 + HNSW）+ pg_trgm（标题相似）

`hotspot` 模块（下一阶段）通过 `GET /events` / `GET /events/{id}` 读取 `event` 表（消费侧只读）。

---

## 处理流水线

```
source.fetch_task (source 模块)
    │
    │ 写入 article 表（status=RAW, url_hash 唯一去重）
    ▼
clean_task (pipeline)
    │
    │ 抽取正文 / 去广告 / 时间归一化 / 关键词 / 摘要
    │ 丢弃规则：lang 不支持 / 超 7 天 / 内容过短
    │ status: RAW → CLEANED  或  DISCARDED
    ▼
embed_task
    │
    │ 调 LocalEmbeddingProvider（本地 bge-m3，无则降级 sha256 hash 向量）
    │ 批量 32 条，写 article_embedding(vector(1024))
    │ status: CLEANED → EMBEDDED
    ▼
dedupe_task
    │
    │ 三级级联：
    │   L1 指纹：title_hash 命中已有 event_article → FINGERPRINT
    │   L2 pg_trgm：title 相似 > 0.75 → TITLE
    │   L3 pgvector：1 - cosine_dist > 0.85 → VECTOR
    │ 未命中 → 新建 event(status=PENDING_AI)
    │ status: EMBEDDED → CLUSTERED
    ▼
analyze_event_task
    │
    │ 调 ai-engine.EventAnalysisService.analyze_event
    │ 写 event_analysis 表 + 回写 event.value/originality/trend_score
    │ status: PENDING_AI → ANALYZED  或  AI_FAILED（重试 2 次后）
    ▼
rank_task
    │
    │ 计算 heat_score（算法：source_weight × diversity × engagement × freshness，min-max 归一化）
    │ 计算 recommend_index = 0.35·heat + 0.30·value + 0.20·originality + 0.15·trend
    │ 72h 内无新来源的事件 → ARCHIVED
```

链路：source.fetch_task 末尾成功后，链式触发 `clean_task → embed_task → dedupe_task → (analyze_event_task × N) → rank_task`。

---

## 三级去重逻辑（`dedup.py` + `tasks.py:_cluster_one`）

```
Level 1 — 指纹
  └─ select_event_by_title_hash(article.title_hash)
     └─ 命中 → 合并 match_level=FINGERPRINT

Level 2 — pg_trgm 标题相似（72h 窗口）
  └─ similarity(title) > 0.35 取 top 20
     ├─ max > 0.75 → 合并 match_level=TITLE
     └─ 0.35 < max ≤ 0.75 → 进入 Level 3

Level 3 — pgvector 余弦（72h 窗口）
  └─ embedding <=> CAST(:vec AS vector) 距离最小 5 个
     └─ 1 - 距离 > 0.85 → 合并 match_level=VECTOR
     └─ 否则 → 新建 event
```

合并动作（事务内）：
1. 写 `event_article` 行（含 match_level / similarity）
2. `article.event_id = event.id`，`article.status = CLUSTERED`
3. 重算 `event.source_count / article_count / last_seen_at`
4. 若 event 已 ANALYZED 且 source_count 增加 → 重置 PENDING_AI（重新分析）

---

## 评分公式（`rank_task`）

```
heat_score = normalize( source_weight_sum × source_diversity × engagement × freshness )
  ├─ source_weight_sum = Σ 不同来源的 source.weight
  ├─ source_diversity  = 1 + √(source_count) × 0.5
  ├─ engagement        = 1 + √(1 + Σ metrics × metric_weights)
  │     metric_weights: points=1.0, comments=2.0, stars=0.5, upvotes=1.0
  └─ freshness         = exp(-Δh/24)   # Δh = 距 last_seen_at 小时数
  → 全量 72h 活跃事件做 min-max 归一化到 [0, 100]

recommend_index = 0.35·heat + 0.30·value + 0.20·originality + 0.15·trend
  AI 分数缺失时降级：自动重新归一化权重（不实现，AI 失败时只乘 0.35）
```

---

## 关键文件

| 文件 | 职责 |
|------|------|
| `model.py` | 6 个 ORM 表（Article / ArticleEmbedding / Event / EventArticle / Tag / EventTag）|
| `enums.py` | ArticleStatus / EventStatus / MatchLevel / EventRegion |
| `exceptions.py` | ArticleNotFoundError / EventNotFoundError / CannotSplitAll / CannotMergeSelf 等 |
| `repository.py` | ArticleRepository（upsert_many_from_raw / list_by_status）+ ArticleEmbeddingRepository（原生 SQL 写 vector） |
| `cleaner.py` | 纯函数：extract_content / normalize_published_at / summarize / extract_keywords / should_discard |
| `dedup.py` | 纯函数：normalize_title / url_hash / title_hash |
| `service.py` | PipelineService.clean_articles |
| `tasks.py` | 5 个 Celery 任务（clean / embed / dedupe / analyze_event / rank / rerun） |
| `schema.py` | 运维 DTO（PipelineRerunRequest / Stats / SplitResult） |
| `api.py` | /admin/pipeline/{rerun, stats} + /events/{id}/split + /events/merge |

---

## 已知坑（开发过程中踩到的）

1. **pgvector ORM 不直接支持**：`embedding vector(1024)` 列 SQLAlchemy 无法 type-infer。`ArticleEmbedding` 模型不声明 `embedding` 列，repository 用原生 SQL + `CAST(:vec AS vector)` 写入。
2. **asyncpg 命名参数 + 类型 cast**：`:vec::vector` 在 asyncpg 协议下报语法错，必须用 `CAST(:vec AS vector)`。
3. **Celery solo 跨 asyncio.run() 共享连接池**：`asyncio.run` 关闭 loop 后连接池里的 asyncpg 连接绑了死 loop，下次 run 报 "Event loop is closed"。`_run()` 加 `engine.dispose()` finally 兜底。
4. **LLMGateway.embed() 关系懒加载**：`_build_provider(model.provider)` 触发 sync lazy load 需要 greenlet；embed_task 改为直接实例化 `LocalEmbeddingProvider` 绕过。
5. **AI-engine 的 `_load_event` 是占位**：已重写，从 pipeline 的 article / event_article 表读上下文并按 prompt 模板要求的 snake_case 字段名构造。

---

## 验证状态

| 阶段 | 验证 | 结果 |
|------|------|------|
| B. source→article | HN 触发 15 条 → article 表 15 条 RAW | ✅ |
| C. clean_task | 14 篇 → CLEANED（1 篇 DISCARDED）| ✅ |
| D. embed_task | 14 篇 → EMBEDDED + 14 个 vector 行 | ✅ |
| E. dedupe_task | 14 篇 → CLUSTERED + 14 个 event | ✅ |
| F. analyze_event_task | 14 篇尝试调 AI → AI_FAILED（无 LLM key）| ✅（链路通，缺配置）|
| G. rank_task | 14 个 event 写入 heat_score / recommend_index | ✅ |
| H. API | /admin/pipeline/stats 返回状态分布 + dedupe_rate | ⏳ 待测 |

### 端到端冒烟

```bash
# 1. 重启 worker + API
cd backend
.venv/Scripts/celery.exe -A app.worker worker -l info -P solo -Q celery &
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 &

# 2. 触发 HN 采集 → 自动链式跑完整流水线
curl -X POST localhost:8000/api/v1/admin/sources/8/run -H "Authorization: Bearer $TOKEN"

# 3. 等待 30s
sleep 30

# 4. 验证
docker exec trendradar-postgres psql -U trendradar -d trendradar \
  -c "SELECT 'article', status, count(*) FROM article GROUP BY status
      UNION ALL SELECT 'event', status, count(*) FROM event GROUP BY status;"

# 期望：article 各状态都有，event 有 ANALYZED 或 AI_FAILED + heat_score 已有值
```

---

## 待办

- [ ] 完整前端监控页（漏斗图 + 状态饼图 + 重跑面板）
- [ ] Beat 周期调度 `dedupe_task` + `rank_task`（每 20 分钟 / 每 6 小时）
- [ ] system_config 抽取阈值（dedupe_title_threshold / vector_threshold 等）—— admin 模块做
- [ ] AuditService 集成（EVENT_SPLIT / EVENT_MERGE / SOURCE_AUTO_DISABLED 等写操作）
- [ ] beat_schedule 周期跑全套
- [ ] Celery task_run_log 自动埋点（admin 模块的 @tracked_task 装饰器）
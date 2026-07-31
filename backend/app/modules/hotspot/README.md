# hotspot 模块（热点中心）

> 需求：[doc/SPEC-hotspot.md](../../../doc/SPEC-hotspot.md)
> pipeline 的下游纯消费侧，把 `event` 加工成榜单 + 详情 + 趋势，并对 EDITOR 提供置顶 / 隐藏 / 编辑 / 解锁能力。

---

## 提供给其他模块的能力

- **路由**：`GET /events`（榜单 GUEST）/ `GET /events/{id}`（详情 GUEST）/ `GET /events/{id}/trend`（7 日曲线 GUEST）/ `GET /events/{id}/related`（向量相似 Top N GUEST）/ `GET /tags`（GUEST）/ `PATCH /events/{id}`（EDITOR）/ `DELETE /events/{id}/manual-lock/{field}`（EDITOR）
- **Redis 缓存**：`hotspot:rank:{scope}:{category}:{sort}:{page}`（5 min）/ `hotspot:event:{id}`（10 min）/ `hotspot:trend:{id}`（1 h）
- **跨模块消费**：只读 `pipeline.event` `pipeline.event_article` `pipeline.tag` `pipeline.event_tag` `pipeline.article` + `ai.event_analysis` + `source.source`

`collection` 模块（二期）会在 event 列表 / 详情里填 `isCollected` 字段；当前统一返回 `false`。

---

## 文件清单

```
app/modules/hotspot/
  enums.py          Scope / CategoryFilter / SORT_WHITELIST / LOCKABLE_FIELDS
  exceptions.py     EventNotFoundError / InvalidSortFieldError / KeywordTooShortError / PinAndHideConflictError / ManualLockFieldNotFoundError
  schema.py         EventListItem / EventDetail / EventAnalysisDetail / EventArticleItem / EventTrendResponse / RelatedEventItem / EventUpdateRequest + 公共片段 SourceBrief / TagItem
  repository.py     HotspotRepository（list_events / get_event / get_analysis / list_event_articles / map_* 批量组装 / trend_points / related_events / list_tags）
  service.py        HotspotService（缓存编排 / 运营干预 / 屏蔽源合并 / 排序解析）
  api.py            router + tags_router
```

---

## 榜单查询流程

```
GET /events?scope=TODAY&category=AI&sort=-recommendIndex&keyword=mcp&page=1
   │
   ▼
1.  _parse_sort("-recommendIndex") → ("recommendIndex", True)        # 白名单校验
2.  keyword 长度 < 2 → 400 KEYWORD_TOO_SHORT
3.  includeHidden 仅 EDITOR 生效
4.  _muted_sources(user) → 读 auth.AuthService.get_me(user).preference.muted_sources
5.  cacheable 判断：无 keyword / 无 tagIds / 无 sourceIds / 无 min_recommend / 无 startDate / 无 endDate
                    / 无 includeHidden / 无 muted / page <= 3
   ├─ 命中 → 走 RedisKey.hotspot_rank(scope, category, sort, page)
   └─ 未命中 → 拼 SQL：
        ├─ _base_filters：is_deleted=false、is_hidden（按权限）、last_seen_at 窗口、
        │    分类维度（jsonb_exists_any / region in / Article JOIN Source EXISTS for GITHUB/PAPER）、
        │    muted_sources → EXISTS（至少一篇来源非屏蔽）
        ├─ keyword：tsvector @@ plainto_tsquery OR title % :kw OR title ILIKE
        ├─ tagIds：每个 tag 一个 AND-EXISTS
        ├─ sourceIds：一个 OR-EXISTS
        └─ 排序：is_pinned DESC, <sort_col> DESC/ASC, last_seen_at DESC, id DESC
6.  一次批量取 sources / tags / primary_article_url / worth_article（map_*）
7.  Page.create(items, total, page, size)
8.  cacheable → Redis setex 5min
```

---

## 详情页组装

```
GET /events/{id}
   │
   ├─ 非 EDITOR：先读 RedisKey.hotspot_event({id}) 缓存
   ├─ get_event → 404 EventNotFoundError（隐藏事件对非 EDITOR 也是 404）
   ├─ get_analysis → 读 event_analysis（status=ANALYZED 才返回）
   ├─ list_event_articles → Article LEFT JOIN Source LEFT JOIN EventArticle
   │   按 is_primary DESC, published_at ASC
   └─ 组装：
        analysis.{summaryOneLine, summary, keyPoints, innovations, audience,
                 worthArticle/Research + why, scores, modelAlias, promptVersion, analyzedAt}
        articles[]  = {matchLevel, similarity, isPrimary}
        tags[]      = {weight}
   └─ 非 EDITOR 写缓存 10 min
```

---

## 趋势 / 相关

- **趋势**（`/events/{id}/trend`）：一期无 `event_daily_snapshot`（trend 模块建表），用 `event_article.created_at` 按日累计近似：截至当天累计文章数 / 累计去重来源数；热度按累计比例近似。缓存 1 h。
- **相关**（`/events/{id}/related`）：取主文章 embedding 走 HNSW（`<=>` 距离升序），聚合到 event 级别去重，Top N。返回 1-距离 作为 `similarity`。

---

## EDITOR 运营干预

### PATCH /events/{id}
```json
{ "title": "…", "summaryOneLine": "…", "categories": ["AI","LLM"],
  "isPinned": true, "isHidden": false }
```

校验：
- 同时 `isPinned=true` + `isHidden=true` → 400 `PIN_AND_HIDE_CONFLICT`
- 当前是隐藏但 PATCH 改为置顶（未传 `isHidden=false`）→ 400（防歧义）
- 当前是置顶但 PATCH 改为隐藏（未传 `isPinned=false`）→ 400

行为：
- `title` / `summary_one_line` / `categories` 任一变更 → `is_manually_edited=true` + 字段名写入 `manual_locked_fields`
- `is_pinned` / `is_hidden` 不进 `manual_locked_fields`
- 写完 `commit` → 失效 `hotspot:event:{id}` / `hotspot:trend:{id}` / 全部 `hotspot:rank:*`
- `TODO(admin)`：调 `AuditService.record("EVENT_EDIT", "EVENT", id, before, after)`

### DELETE /events/{id}/manual-lock/{field}
- 解除 `manual_locked_fields` 中某字段的锁定，下次 AI 重跑可覆盖
- `field` 必须是 `LOCKABLE_FIELDS = ("title", "summaryOneLine", "categories")` 之一
- 未锁 → 404 `MANUAL_LOCK_FIELD_NOT_FOUND`
- 全部解锁后 `is_manually_edited = false`

---

## 跨模块调用规范

| 目标 | 走 | 备注 |
|------|----|------|
| `pipeline.event` / `event_article` / `tag` / `event_tag` / `article` 等 ORM | `from app.modules.pipeline.model import …` | hotspot 是**唯一读 event 表**的模块（EDITOR 写除外） |
| `ai.event_analysis` | `from app.modules.ai.model import EventAnalysis` | 读最新一条分析 |
| `source.source` | `from app.modules.source.model import Source` | 来源 favicon / 名称 / 权重 |
| `auth.User` 屏蔽源 | `from app.modules.auth.service import AuthService` | 调 `get_me(user).preference.muted_sources` |

**禁止**：跨模块 import 对方的 `repository` / 业务实现。读 model 是允许的（hotspot 唯一消费者）。

---

## 验证状态

| 阶段 | 验证 | 结果 |
|------|------|------|
| A. import | `from app.main import app` | ✅ |
| B. 路由注册 | `main.py` 加 2 个 router | ✅ |
| C. 榜单 (GUEST) | `GET /events?scope=ALL&size=3` | ✅ 200，14 条 event |
| D. 详情 (GUEST) | `GET /events/9` | ✅ 200，含 articles + analysis:null（AI_FAILED）|
| E. 趋势 (GUEST) | `GET /events/9/trend` | ✅ 200，7 日点 |
| F. 相关 (GUEST) | `GET /events/9/related?limit=3` | ✅ 200，3 个相关 + similarity |
| G. 标签 (GUEST) | `GET /tags?limit=5` | ✅ 200，[]（AI 未产出 tag）|
| H. sort 白名单 | `GET /events?sort=evil` | ✅ 400 `INVALID_SORT_FIELD` |
| I. keyword 校验 | `GET /events?keyword=a` | ✅ 400 `KEYWORD_TOO_SHORT` |
| J. 搜索 | `GET /events?keyword=AI` | ✅ 200，命中"AI's top startups..." |
| K. 分类=AI | `GET /events?category=AI` | ✅ 200，[]（categories 暂空） |
| L. 分类=GITHUB | `GET /events?category=GITHUB` | ✅ 200，[]（Source category=CODE 不在事件里）|
| M. 404 | `GET /events/999999` | ✅ 404 `EVENT_NOT_FOUND` |
| N. PATCH 未登录 | `PATCH /events/9` 不带 token | ✅ 401 `UNAUTHORIZED` |
| O. PATCH EDITOR | 改 title + isPinned=true | ✅ isPinned=True, isManuallyEdited=True, locked=['title'] |
| P. 置顶置首 | 列表 sort=lastSeenAt | ✅ event 9 排首位 |
| Q. pin+hide 冲突 | 同时置顶+隐藏 | ✅ 400 `PIN_AND_HIDE_CONFLICT` |
| R. 解锁 | DELETE /events/9/manual-lock/title | ✅ 204 |
| S. 还原 | PATCH 回原值 | ✅ isPinned=False，locked=[]（再次解锁 204） |
| T. 分页 | size=2 → 14 条 → 7 页 | ✅ |
| U. 前端 | `pnpm typecheck` | ✅ |

### 端到端冒烟

```bash
# 1. API / Web 都在跑
B=http://127.0.0.1:8000/api/v1
curl -s "$B/health"; echo
curl -s "$B/events?scope=ALL&size=2" | python -m json.tool | head -30

# 2. EDITOR 运营
TOKEN=$(curl -s -X POST "$B/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"admin@trendradar.dev","password":"Admin1234!"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
curl -s -X PATCH "$B/events/9" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"isPinned":true,"title":"EDITED"}' | python -m json.tool | head

# 3. 前端 http://localhost:5173/
```

---

## 已知坑 & 待办

- 趋势用 `event_article.created_at` 累计近似，二期 `event_daily_snapshot` 落地后切到精确快照
- `is_collected` 暂恒 false，等 collection 模块
- 缺 EDITOR 运营的"拆分 / 合并"前端入口（后端 `pipeline/api.py` 已实现 `/events/{id}/split` / `/events/merge`，前端按钮在事件详情页 EDITOR 浮栏里加）
- 缺 AuditService 集成（admin 模块做）
- pipeline 监控页（漏斗图 / 状态饼图 / 重跑面板）也在 admin 模块

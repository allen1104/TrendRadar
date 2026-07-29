# 管理后台模块（admin）

所属项目: @SPEC.md
模块状态: ⏳ 未开始
一期范围: ✅ 是
最后更新: 2026-07-29

---

## 功能目标

系统的运维与配置中枢。本模块**不拥有业务实体**，提供三类横切能力：

1. **系统配置**（`system_config`）：阈值、权重、限额等全局参数的读写与热生效
2. **任务监控**（`task_run_log`）：Celery 任务运行状态、失败重试、手动触发
3. **操作审计**（`audit_log`）：所有写操作留痕
4. **总览仪表盘**：数据量、流水线健康度、AI 成本、采集源状态的聚合视图

采集源管理界面见 @doc/SPEC-source.md，AI 配置界面见 @doc/SPEC-ai-engine.md，
用户管理界面见 @doc/SPEC-auth.md。本文档只定义本模块自有的表、接口与页面。

---

## 数据库设计

### `system_config` 表

| 字段        | 类型         | 必填 | 说明                                                       |
| ----------- | ------------ | ---- | ---------------------------------------------------------- |
| id          | BIGSERIAL    | 是   | 主键                                                       |
| config_key  | VARCHAR(100) | 是   | 配置键，全局唯一                                           |
| config_value| JSONB        | 是   | 配置值（统一用 JSONB，标量也包一层）                       |
| value_type  | VARCHAR(32)  | 是   | `INT`/`FLOAT`/`BOOL`/`STRING`/`JSON`，用于前端渲染控件     |
| group_name  | VARCHAR(64)  | 是   | 分组：`DEDUPE`/`RANK`/`AI`/`SCHEDULE`/`SEARCH`/`GENERAL`   |
| display_name| VARCHAR(200) | 是   | 中文显示名                                                 |
| description | VARCHAR(500) | 否   | 说明与影响范围                                             |
| min_value   | NUMERIC      | 否   | 数值下限（校验用）                                         |
| max_value   | NUMERIC      | 否   | 数值上限                                                   |
| is_editable | BOOLEAN      | 是   | 是否允许后台修改，默认 true                                |
| requires_rerun | BOOLEAN   | 是   | 修改后是否需要重跑数据，默认 false（前端提示用）           |
| created_at  | TIMESTAMPTZ  | -    | 创建时间                                                   |
| updated_at  | TIMESTAMPTZ  | -    | 更新时间                                                   |
| is_deleted  | BOOLEAN      | -    | 逻辑删除，默认 false                                       |

索引：`uk_config_key(config_key)`、`idx_config_group(group_name)`

### `task_run_log` 表

| 字段          | 类型          | 必填 | 说明                                                    |
| ------------- | ------------- | ---- | ------------------------------------------------------- |
| id            | BIGSERIAL     | 是   | 主键                                                    |
| task_name     | VARCHAR(120)  | 是   | Celery 任务全名，如 `pipeline.dedupe_task`              |
| task_id       | VARCHAR(64)   | 是   | Celery task id                                          |
| trigger_type  | VARCHAR(32)   | 是   | `SCHEDULED` / `MANUAL` / `CHAINED`                      |
| triggered_by  | BIGINT        | 否   | 手动触发的用户 ID                                       |
| args_summary  | JSONB         | 否   | 入参摘要（不存大对象），默认 `{}`                        |
| status        | VARCHAR(32)   | 是   | `PENDING`/`RUNNING`/`SUCCESS`/`FAILED`/`RETRYING`/`SKIPPED` |
| result_summary| JSONB         | 否   | 结果摘要，如 `{"processed":200,"created":12}`           |
| duration_ms   | INTEGER       | 否   | 耗时                                                    |
| retry_count   | SMALLINT      | 是   | 重试次数，默认 0                                        |
| error_message | TEXT          | 否   | 失败原因（截断 4000 字）                                |
| traceback     | TEXT          | 否   | 异常堆栈（截断 8000 字）                                |
| started_at    | TIMESTAMPTZ   | 否   | 开始时间                                                |
| finished_at   | TIMESTAMPTZ   | 否   | 结束时间                                                |
| created_at    | TIMESTAMPTZ   | -    | 创建时间                                                |
| updated_at    | TIMESTAMPTZ   | -    | 更新时间                                                |
| is_deleted    | BOOLEAN       | -    | 逻辑删除，默认 false                                    |

索引：`uk_task_run_task_id(task_id)`、`idx_task_run_name_time(task_name, started_at DESC)`、`idx_task_run_status(status)`

> 保留 30 天，`cleanup_task` 定期物理删除。

### `audit_log` 表

| 字段         | 类型          | 必填 | 说明                                                        |
| ------------ | ------------- | ---- | ----------------------------------------------------------- |
| id           | BIGSERIAL     | 是   | 主键                                                        |
| user_id      | BIGINT        | 否   | 操作人（系统操作为空）                                      |
| username     | VARCHAR(50)   | 否   | 操作人昵称（冗余，用户删了也能追溯）                        |
| action       | VARCHAR(64)   | 是   | 动作，如 `EVENT_PIN`/`SOURCE_UPDATE`/`PROMPT_ACTIVATE`      |
| target_type  | VARCHAR(32)   | 是   | `EVENT`/`SOURCE`/`USER`/`PROMPT`/`MODEL`/`CONFIG`/`SYSTEM`  |
| target_id    | BIGINT        | 否   | 目标对象 ID                                                 |
| before_value | JSONB         | 否   | 变更前（仅变更字段）                                        |
| after_value  | JSONB         | 否   | 变更后（仅变更字段）                                        |
| ip           | VARCHAR(64)   | 否   | 来源 IP                                                     |
| user_agent   | VARCHAR(500)  | 否   | UA                                                          |
| note         | VARCHAR(500)  | 否   | 备注                                                        |
| created_at   | TIMESTAMPTZ   | -    | 创建时间                                                    |
| updated_at   | TIMESTAMPTZ   | -    | 更新时间                                                    |
| is_deleted   | BOOLEAN       | -    | 逻辑删除，默认 false                                        |

索引：`idx_audit_time(created_at DESC)`、`idx_audit_user(user_id, created_at DESC)`、`idx_audit_target(target_type, target_id)`

> 保留 180 天，**只增不改不删**（业务代码禁止 UPDATE/DELETE）。

---

## 系统配置项清单（seed 初始化）

| config_key                      | 默认值 | 分组     | 说明                              | 需重跑 |
| ------------------------------- | ------ | -------- | --------------------------------- | ------ |
| `dedupe_title_threshold`        | 0.75   | DEDUPE   | 标题相似度直接合并阈值            | 否     |
| `dedupe_title_candidate`        | 0.35   | DEDUPE   | 进入向量判定的候选阈值            | 否     |
| `dedupe_vector_threshold`       | 0.85   | DEDUPE   | 向量余弦相似度合并阈值            | 否     |
| `dedupe_time_window_hours`      | 72     | DEDUPE   | 聚合时间窗口（小时）              | 否     |
| `event_archive_hours`           | 72     | DEDUPE   | 事件归档阈值（小时）              | 否     |
| `article_max_age_days`          | 7      | DEDUPE   | 超龄文章丢弃阈值（天）            | 否     |
| `rank_weights`                  | `{"heat":0.35,"value":0.30,"originality":0.20,"trend":0.15}` | RANK | 推荐指数权重 | 是 |
| `metric_weights`                | `{"points":1.0,"comments":2.0,"stars":0.5,"upvotes":1.0}` | RANK | 互动指标权重 | 是 |
| `default_chat_model`            | `default-chat` | AI | 默认对话模型别名                  | 否     |
| `default_embedding_model`       | `local-bge-m3` | AI | 默认 embedding 模型别名           | 是     |
| `ai_fallback_chain`             | `[]`   | AI       | 降级链（模型别名数组）            | 否     |
| `ai_single_call_cost_limit_usd` | 0.5    | AI       | 单次调用费用上限                  | 否     |
| `ai_daily_cost_limit_usd`       | 20     | AI       | 单日费用上限，超限暂停系统任务    | 否     |
| `ai_user_rate_limit`            | 20     | AI       | 单用户每小时 AI 调用次数上限      | 否     |
| `analyze_batch_cron`            | `0 */6 * * *` | SCHEDULE | 事件分析批量任务调度        | 否     |
| `rank_cron`                     | `10 */6 * * *` | SCHEDULE | 评分入榜任务调度           | 否     |
| `cleanup_cron`                  | `0 3 * * *` | SCHEDULE | 日志清理任务调度              | 否     |
| `search_text_config`            | `simple` | SEARCH | PG 全文检索配置（`simple`/`zhparser`） | 是 |
| `title_blacklist`               | `[]`   | GENERAL  | 标题垃圾词黑名单                  | 否     |
| `site_notice`                   | `""`   | GENERAL  | 全站公告（前台顶部横幅）          | 否     |

---

## Celery 任务清单

| 任务名                          | 类型     | 调度                   | 说明                                |
| ------------------------------- | -------- | ---------------------- | ----------------------------------- |
| `source.fetch_task`             | 采集     | 每源独立 cron          | 单个采集源抓取                      |
| `pipeline.clean_task`           | 清洗     | 采集完成后链式触发     | 批量清洗 RAW 文章                   |
| `pipeline.embed_task`           | 向量化   | 清洗完成后链式触发     | 批量生成 embedding                  |
| `pipeline.dedupe_task`          | 聚合     | `*/20 * * * *`         | 三级级联去重（全局锁）              |
| `ai.analyze_event_task`         | AI 分析  | `analyze_batch_cron`   | 批量分析 PENDING_AI 事件            |
| `pipeline.rank_task`            | 评分     | `rank_cron`            | 热度与推荐指数计算 + 缓存刷新       |
| `pipeline.archive_task`         | 归档     | `0 * * * *`            | 超期事件归档                        |
| `admin.cleanup_task`            | 清理     | `cleanup_cron`         | 清理过期日志、刷新物化视图          |
| `admin.health_check_task`       | 健康检查 | `*/5 * * * *`          | 检查采集源失败率、AI 成本、队列积压 |

---

## 后端接口

### GET /api/v1/admin/dashboard
**说明**: 总览仪表盘数据，`EDITOR` 及以上

**Response 200**:
```json
{
  "overview": {
    "totalEvents": 7094,
    "totalArticles": 18320,
    "todayNewEvents": 87,
    "todayNewArticles": 412,
    "activeSources": 8,
    "totalUsers": 132
  },
  "pipelineHealth": {
    "pendingClean": 12,
    "pendingEmbed": 5,
    "pendingAi": 4,
    "failedArticles": 7,
    "aiFailedEvents": 2,
    "avgSourcePerEvent": 1.83,
    "dedupeRate": 0.42
  },
  "aiCost": {
    "todayUsd": 1.2043,
    "monthUsd": 28.91,
    "dailyLimitUsd": 20,
    "limitReached": false
  },
  "sourceStatus": [
    { "id": 1, "name": "Hacker News", "lastRunStatus": "SUCCESS",
      "lastRunAt": "2026-07-29T08:00:12Z", "todayCount": 87, "consecutiveFails": 0 }
  ],
  "recentAlerts": [
    { "level": "WARN", "message": "采集源「Product Hunt」连续失败 3 次",
      "createdAt": "2026-07-29T07:45:00Z" }
  ],
  "trend7d": [
    { "date": "2026-07-29", "articles": 412, "events": 87, "aiCostUsd": 1.2043 }
  ]
}
```

---

### GET /api/v1/admin/configs
**说明**: 系统配置列表，仅 `ADMIN`

**Query**: `group`

**Response 200**:
```json
[
  {
    "id": 3,
    "configKey": "dedupe_vector_threshold",
    "configValue": 0.85,
    "valueType": "FLOAT",
    "groupName": "DEDUPE",
    "displayName": "向量相似度合并阈值",
    "description": "余弦相似度超过此值判定为同一事件。调高更保守（少合并），调低更激进（易误合并）",
    "minValue": 0.5,
    "maxValue": 0.99,
    "isEditable": true,
    "requiresRerun": false,
    "updatedAt": "2026-07-20T10:00:00Z"
  }
]
```

### PUT /api/v1/admin/configs/{configKey}
**说明**: 修改配置，仅 `ADMIN`。立即热生效（写库 + 失效 Redis 配置缓存）

**Request Body**: `{ "configValue": 0.88 }`

**Response 200**: 配置对象

**错误情况**:
- 配置不存在 → `404` `CONFIG_NOT_FOUND`
- `isEditable=false` → `403` `CONFIG_READONLY`
- 超出 `minValue`/`maxValue` → `400` `CONFIG_VALUE_OUT_OF_RANGE`
- 类型不匹配 → `400` `CONFIG_TYPE_MISMATCH`
- `rank_weights` 四项之和不等于 1 → `400` `RANK_WEIGHTS_SUM_INVALID`

---

### GET /api/v1/admin/tasks
**说明**: 任务运行日志，`EDITOR` 及以上

**Query**: `page` `size` `taskName` `status` `triggerType` `startDate` `endDate`

**Response 200**: 分页的 `task_run_log`，`traceback` 仅在单条详情接口返回

### GET /api/v1/admin/tasks/{id}
**说明**: 任务详情（含完整 `traceback`），`EDITOR` 及以上

### GET /api/v1/admin/tasks/definitions
**说明**: 所有注册的 Celery 任务定义与当前调度，`EDITOR` 及以上

**Response 200**:
```json
[
  { "taskName": "pipeline.dedupe_task", "displayName": "去重聚合",
    "cron": "*/20 * * * *", "cronConfigKey": null, "enabled": true,
    "nextRunAt": "2026-07-29T08:40:00Z", "lastRunAt": "2026-07-29T08:20:00Z",
    "lastRunStatus": "SUCCESS", "manualTriggerable": true }
]
```

### POST /api/v1/admin/tasks/trigger
**说明**: 手动触发任务，`EDITOR` 及以上

**Request Body**:
```json
{ "taskName": "pipeline.dedupe_task", "args": {} }
```

**Response 202**: `{ "taskId": "c1a2...", "runLogId": 5021 }`

**错误情况**:
- 任务名未注册 → `400` `TASK_NOT_FOUND`
- 该任务 `manualTriggerable=false` → `403` `TASK_NOT_MANUALLY_TRIGGERABLE`
- 任务已在运行（持有全局锁） → `409` `TASK_ALREADY_RUNNING`

### POST /api/v1/admin/tasks/{id}/retry
**说明**: 重试失败的任务（用原参数重新投递），`EDITOR` 及以上

**Response 202**: `{ "taskId": "...", "runLogId": 5022 }`

**错误情况**: 状态非 `FAILED` → `400` `TASK_NOT_FAILED`

---

### GET /api/v1/admin/audit-logs
**说明**: 审计日志，仅 `ADMIN`

**Query**: `page` `size` `userId` `action` `targetType` `targetId` `startDate` `endDate`

**Response 200**:
```json
{
  "items": [
    { "id": 8821, "userId": 3, "username": "小编A", "action": "EVENT_PIN",
      "targetType": "EVENT", "targetId": 88,
      "beforeValue": { "isPinned": false }, "afterValue": { "isPinned": true },
      "ip": "10.0.0.12", "createdAt": "2026-07-29T08:12:00Z" }
  ],
  "total": 8821, "page": 1, "size": 20, "pages": 442
}
```

---

### GET /api/v1/health · GET /api/v1/health/ready
**说明**: 健康检查，无需认证

- `/health` → `200 {"status":"ok"}`（存活探针，不查依赖）
- `/health/ready` → 检查 PG / Redis / Celery broker 连通性
  ```json
  { "status": "ok", "checks": { "postgres": "ok", "redis": "ok", "celery": "ok" } }
  ```
  任一失败 → `503`，`status` 为 `degraded`

---

## 前端页面

### 总览仪表盘（`/admin`，EDITOR）
- 顶部告警横幅：AI 日限额触顶 / 采集源自动禁用 / 队列积压（红/黄色，可关闭）
- 6 个指标卡（2 行 3 列）：事件总数 / 文章总数 / 今日新增事件 / 今日新增文章 / 启用源数 / 用户数
  - 每张卡右下角显示环比昨日的 ↑↓ 百分比
- **流水线漏斗图**（ECharts funnel）：RAW → CLEANED → EMBEDDED → CLUSTERED → ANALYZED
  - 每层显示当前积压数，积压 > 阈值时标黄
- **7 日趋势图**（ECharts line，三条线双 Y 轴）：文章数 / 事件数 / AI 费用
- **AI 成本卡**：今日费用 / 本月费用 + 日限额进度条（>80% 变橙，>100% 变红）
- **采集源状态表**：名称、最后运行、状态 Badge、今日采集数、连续失败数；失败的行可直接点「立即重跑」
- **最近告警时间线**：最近 10 条 WARN/ERROR

### 系统配置（`/admin/config`，ADMIN）
- 左侧分组导航：去重聚合 / 评分权重 / AI 设置 / 任务调度 / 搜索 / 通用
- 右侧配置项卡片列表，每项：
  - 显示名 + 说明文字（灰色小字）
  - 根据 `valueType` 渲染控件：
    - `FLOAT`/`INT` 且有 min/max → 滑块 + 数字输入联动
    - `BOOL` → Switch
    - `STRING` → Input
    - `JSON` → Monaco Editor（JSON 模式，实时校验）
  - `requiresRerun=true` 的项显示 ⚠️ "修改后需重跑数据才生效" 提示
  - `isEditable=false` 的项置灰只读
- **权重配置特殊处理**：`rank_weights` 用 4 个联动滑块，总和实时显示，不等于 1 时提交按钮禁用并标红
- 底部「保存」按钮（脏检查，无改动时禁用），保存后 Toast + 若 `requiresRerun` 则弹出「是否立即重跑评分？」

### 任务监控（`/admin/tasks`，EDITOR）
- **Tab 1 · 任务定义**
  - 卡片列表：任务名、中文名、cron、下次运行倒计时、最后运行状态
  - 每张卡「立即执行」按钮（二次确认），执行中显示进行中动画
- **Tab 2 · 运行日志**
  - 表格：任务名、触发方式 Badge、状态 Badge、耗时、结果摘要、开始时间
  - 筛选：任务名下拉、状态、触发方式、日期范围
  - 状态自动刷新（`RUNNING` 状态的行每 5 秒轮询一次）
  - 点击行 → 抽屉展示详情：完整入参、结果摘要 JSON、错误信息、traceback（等宽字体、可折叠、可复制）
  - `FAILED` 行有「重试」按钮

### 审计日志（`/admin/audit`，ADMIN）
- 表格：时间、操作人、动作（中文映射 + Badge）、对象类型、对象 ID（可点击跳转）、IP
- 筛选：操作人搜索、动作下拉、对象类型、日期范围
- 点击行 → 抽屉展示 before/after 的 JSON diff（用 diff 高亮：删除红色、新增绿色）
- 支持导出 CSV（当前筛选条件下，最多 10000 条）

---

## 业务规则

### 配置热生效
- 配置读取封装为 `ConfigService.get(key, default)`，内部走 Redis 缓存（TTL 60 秒）
- 修改配置后立即删除 Redis 缓存键 `config:{key}`
- `cron` 类配置（`analyze_batch_cron` 等）修改后通过 Redis pub/sub 通知 Beat 热重载
- 配置值校验在**服务层**做，不依赖前端

### 任务日志
- 所有 Celery 任务用统一装饰器 `@tracked_task` 包装，自动写 `task_run_log`
  - 任务开始 → 插入 `RUNNING`
  - 成功 → 更新 `SUCCESS` + `result_summary` + `duration_ms`
  - 异常 → 更新 `FAILED` + `error_message` + `traceback`
  - 被全局锁挡住 → 更新 `SKIPPED`
- 装饰器必须保证**即使写日志失败也不影响任务本身**（日志写入包 try/except）
- 长任务每处理一批更新一次 `result_summary`，前端可见进度

### 审计日志
- 统一由 `AuditService.record(action, target_type, target_id, before, after)` 写入
- 需要审计的动作：
  - 事件：`EVENT_PIN` `EVENT_HIDE` `EVENT_EDIT` `EVENT_SPLIT` `EVENT_MERGE` `EVENT_REANALYZE`
  - 采集源：`SOURCE_CREATE` `SOURCE_UPDATE` `SOURCE_DELETE` `SOURCE_MANUAL_RUN` `SOURCE_AUTO_DISABLED`
  - AI：`PROVIDER_CREATE/UPDATE/DELETE` `MODEL_CREATE/UPDATE/DELETE` `PROMPT_CREATE` `PROMPT_ACTIVATE`
  - 用户：`USER_ROLE_CHANGE` `USER_STATUS_CHANGE`
  - 配置：`CONFIG_UPDATE`
  - 系统：`AI_DAILY_LIMIT_REACHED` `SYSTEM_TASK_PAUSED`
- `before_value` / `after_value` **只记录变更的字段**，不记录全对象
- 敏感字段（`apiKey`、`passwordHash`）一律记为 `"***"`

### 告警
- `health_check_task` 每 5 分钟检查：
  - 任一采集源 `consecutive_fails >= 3` → WARN
  - 采集源被自动禁用 → ERROR
  - AI 当日费用 > 80% 限额 → WARN；> 100% → ERROR + 暂停系统任务
  - Celery 队列积压 > 1000 → WARN
  - `article.status=FAILED` 今日新增 > 50 → WARN
- 告警写 `audit_log`（`target_type=SYSTEM`），前端仪表盘顶部横幅展示
- 一期不做外部通知（邮件/Webhook），二期随 report 模块补

### 数据清理
- `cleanup_task` 每日 03:00 执行：
  - `source_run_log` / `task_run_log` 保留 30 天
  - `ai_call_log` 保留 90 天（聚合后写入 `mv_ai_cost_daily`）
  - `audit_log` 保留 180 天
  - `article.status=DISCARDED` 保留 30 天
  - 刷新物化视图 `mv_ai_cost_daily`
- 清理用 `DELETE ... WHERE created_at < :cutoff` 分批（每批 5000 行），避免长事务锁表

### 权限
- `/admin/dashboard` `/admin/tasks*` → `EDITOR` 及以上
- `/admin/configs*` `/admin/audit-logs` `/admin/users*` `/admin/ai/*` `/admin/sources`（写操作）→ `ADMIN`
- `/health` `/health/ready` → 无需认证

---

## 完成标准

- [ ] `system_config` / `task_run_log` / `audit_log` 表与迁移完成
- [ ] 22 个系统配置项 seed 完成，含 min/max 与说明
- [ ] `ConfigService` 带 Redis 缓存，修改后热生效
- [ ] cron 类配置修改后 Beat 热重载生效
- [ ] `@tracked_task` 装饰器完成，所有 Celery 任务自动写日志
- [ ] 日志写入失败不影响任务本身（构造异常测试验证）
- [ ] `AuditService` 完成，全部 20+ 动作正确记录 before/after，敏感字段脱敏
- [ ] 手动触发/重试任务接口生效，全局锁冲突返回 409
- [ ] `health_check_task` 五类告警全部生效
- [ ] `cleanup_task` 分批清理生效，物化视图刷新正常
- [ ] `/health` 与 `/health/ready` 探针可用，依赖异常时返回 503
- [ ] 总览仪表盘完成：告警横幅、指标卡、漏斗图、趋势图、成本卡、源状态表
- [ ] 系统配置页完成：分组导航、按类型动态控件、权重联动校验、重跑提示
- [ ] 任务监控页完成：定义卡片、日志表格、运行中自动刷新、traceback 抽屉、重试
- [ ] 审计日志页完成：筛选、JSON diff 抽屉、CSV 导出
- [ ] 单元测试：配置校验、装饰器行为、审计脱敏、清理分批；覆盖率 ≥ 70%

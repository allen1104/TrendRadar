# admin 模块（管理后台）

> 需求：[doc/SPEC-admin.md](../../../doc/SPEC-admin.md)
> 系统的运维与配置中枢：dashboard / system_config / task_run_log / audit_log / 健康检查 / 告警。

---

## 提供给其他模块的能力

- **横切基础设施**：`AuditService.record()`（5+ 写操作已接入）/ `@tracked_task` 装饰器 / `ConfigService.get()` / `RequestContextMiddleware`
- **路由**（全在 `/api/v1/admin`）：
  - `GET /admin/dashboard`（EDITOR+）
  - `GET/PUT /admin/configs[/{key}]`（ADMIN）
  - `GET/POST /admin/tasks[/{id}/retry]` + `GET /admin/tasks/definitions` + `POST /admin/tasks/trigger`（EDITOR+）
  - `GET /admin/audit-logs[/{id}]`（ADMIN）
- **健康探针**：`/api/v1/health` / `/api/v1/health/ready`（已存在 main.py，被 admin service 接管逻辑）
- **Celery 任务**：`admin.health_check`（5 分钟）+ `admin.cleanup`（每日 03:00）
- **Redis pub/sub**：`ops:beat:reload` 通道；cron 类配置改动后 publish 通知 Beat

---

## 文件清单

```
app/modules/admin/
  enums.py          ConfigGroup / ValueType / TriggerType / TaskRunStatus / TargetType / AuditAction / AlertLevel
  exceptions.py     ConfigNotFoundError / ConfigReadOnlyError / ConfigValueOutOfRangeError /
                    ConfigTypeMismatchError / RankWeightsSumInvalidError / TaskNotFoundError /
                    TaskNotTriggerableError / TaskAlreadyRunningError / TaskNotFailedError
  model.py          SystemConfig / TaskRunLog / AuditLog
  schema.py         ConfigItem / TaskRunLogItem+Detail / TaskDefinitionItem / AuditLogItem+Detail /
                    DashboardResponse (OverviewCard / PipelineHealth / AiCostCard / SourceStatusItem /
                    AlertItem / TrendPoint) / HealthCheck
  repository.py     SystemConfigRepository / TaskRunLogRepository / AuditLogRepository
  service.py        ConfigService (Redis 缓存 + 校验 + 改 cron 触发 ops:beat:reload) /
                    AuditService (敏感字段脱敏 + try/except 隔离) /
                    TaskRunLogService / DashboardService (聚合 6 类)
  decorator.py      @tracked_task + TASK_REGISTRY (display_name / manual_triggerable)
  tasks.py          cleanup_task (分批物理删除 30/90/180 天) / health_check_task (5 类告警)
  api.py            admin_router (9 个端点)
```

---

## 数据库设计

3 张表，索引与约束见 `alembic/versions/20260731_0005_admin_tables.py`。

| 表 | 保留 | 清理 |
|----|------|------|
| `system_config` | 永久 | 仅软删除 |
| `task_run_log` | 30 天 | `cleanup_task` 分批 5000 行 |
| `audit_log` | 180 天 | `cleanup_task` 分批 5000 行（只增不改不删） |

---

## ConfigService 热生效

```
ConfigService.get(key)  业务读取
  ├─ 内存缓存（_mem_cache）     ← 命中即返回
  ├─ Redis 缓存 60s（config:cache:{key}）
  └─ DB 兜底 → 写回 Redis + 内存

PUT /admin/configs/{key}  后台写入
  ├─ 校验 is_editable（403）
  ├─ 类型强转 + min/max（400 CONFIG_VALUE_OUT_OF_RANGE / CONFIG_TYPE_MISMATCH）
  ├─ rank_weights 和 ≠ 1 → 400 RANK_WEIGHTS_SUM_INVALID
  ├─ DB 写值 + commit
  ├─ 失效 Redis + 内存
  └─ 若 group=SCHEDULE 或 key 含 _cron → publish "ops:beat:reload"
```

> Beat 端订阅本期未实现：Celery Beat 自身每分钟 reload，下一轮自然生效。
> 一期简化：cron 改动后等下一次 tick。

---

## @tracked_task 装饰器

```python
@tracked_task(manual_triggerable=True, display_name="单源采集")
@celery_app.task(name="source.fetch", bind=True, max_retries=2, default_retry_delay=60)
def fetch_task(self, source_id, ...):
    ...
```

行为：
- 在 Celery `@task` **外层**包一层
- 调用时独立开 `AsyncSessionLocal()` 插 `RUNNING` 行
- 业务函数返回值（dict）摘要写 `result_summary`
- 异常路径写 `FAILED` + `error_message` + `traceback`（截断 4000/8000 字），再 re-raise
- **日志写失败只 log 不抛**（用 `try/except` 隔离 `engine.dispose()`）
- 元数据（display_name / manual_triggerable）写到模块级 `TASK_REGISTRY`，因为 Celery `@task` 装饰器会丢 wrapper 属性

`/admin/tasks/definitions` 端点从 `TASK_REGISTRY` + `celery_app.tasks` + `beat_schedule` 拼装。

---

## AuditService 接入的 5 个高价值 hook

| 文件 | 调用点 | 动作 |
|------|--------|------|
| `app/modules/hotspot/service.py` | `update_event` | `EVENT_PIN` / `EVENT_HIDE` / `EVENT_EDIT`（按字段集合自动归类） |
| `app/modules/hotspot/service.py` | `unlock_field` | `EVENT_EDIT`（note=unlock field） |
| `app/modules/auth/service.py` | `update_user` | `USER_ROLE_CHANGE` / `USER_STATUS_CHANGE`（捕获 before 写 before/after） |
| `app/modules/source/service.py` | `create/update/delete` | `SOURCE_CREATE` / `SOURCE_UPDATE` / `SOURCE_DELETE`（user 参数从 API 路由透传） |
| `app/modules/ai/service.py` | `activate` | `PROMPT_ACTIVATE`（含旧激活版本号） |

剩余 13 个写操作（hotspot.split/merge、ai provider/model CRUD、auth.register）留 TODO，下阶段补齐。

---

## health_check_task 5 类告警

| 检查 | 阈值 | 等级 | 处理 |
|------|------|------|------|
| 采集源连续失败 | ≥3 | WARN | 写 SYSTEM_ALERT |
| 采集源被自动禁用 | consecutive_fails ≥ 5 且 enabled=false | ERROR | 写 SYSTEM_ALERT |
| AI 当日费用 | > 80% 限额 | WARN | 写 SYSTEM_ALERT |
| AI 当日费用 | ≥ 100% 限额 | ERROR | 写 AI_DAILY_LIMIT_REACHED + SYSTEM_ALERT |
| Celery 队列积压 | RUNNING > 1000 | WARN | 写 SYSTEM_ALERT |
| article FAILED 今日新增 | > 50 | WARN | 写 SYSTEM_ALERT |

每条告警 = 一行 `audit_log`（`target_type=SYSTEM`），dashboard 拉最近 10 条展示。

---

## cleanup_task 分批清理

每批 5000 行 + 事务提交，避免长事务锁表。删除：

| 表 | 阈值 |
|----|------|
| `source_run_log` / `task_run_log` | 30 天 |
| `ai_call_log` | 90 天 |
| `audit_log` | 180 天 |
| `article WHERE status=DISCARDED` | 30 天 |

---

## 跨模块调用规范

| 目标 | 走 | 备注 |
|------|----|------|
| 读 `event` / `article` 等业务表 | 直接 import model | dashboard 只读，不写 |
| 写 `audit_log` | `AuditService.record(...)` | try/except 隔离 |
| 写 `task_run_log` | 装饰器自动 | 业务代码不感知 |
| 跨模块 import 对方的 `service` 即可 | `from app.modules.X.service import ...` | 跨模块禁止 import 对方的 `repository` |

---

## 验证状态

| 阶段 | 验证 | 结果 |
|------|------|------|
| A. 骨架 + 迁移 | `alembic upgrade head` + `\dt` | ✅ 3 张表（system_config / task_run_log / audit_log） |
| A. 注册 | `GET /openapi.json` 查 admin paths | ✅ 9 个端点（dashboard / configs×2 / tasks×5 / audit×2） |
| B. 配置读 | `GET /admin/configs` | ✅ 22 项 |
| B. 改配置 + 校验 | `PUT /admin/configs/dedupe_vector_threshold` 值越界 | ✅ 400 CONFIG_VALUE_OUT_OF_RANGE |
| B. rank_weights | `PUT /admin/configs/rank_weights` 和 = 0.95 | ✅ 400 RANK_WEIGHTS_SUM_INVALID |
| C. audit 写入 | `PATCH /events/{id}` | ✅ audit_log 出现 EVENT_EDIT/PIN/HIDE |
| C. 敏感字段 | `AuditService.record` 传 `apiKey="sk-xxx"` | ✅ before_value.apiKey == "***" |
| D. task_run_log | 触发 source.fetch | ✅ task_run_log 出现 SUCCESS 行 |
| D. 装饰器元数据 | `TASK_REGISTRY.get("source.fetch")` | ✅ display_name="单源采集", manual=True |
| E. Dashboard | `GET /admin/dashboard` | ✅ 46 events / 46 articles / 4 sources |
| E. /health/ready | `GET /api/v1/health/ready` | ✅ {status:ok, checks:{postgres:ok,redis:ok}} |
| F. 单测 | `pytest tests/admin/ --cov` | ✅ 28 passed；45%（API/router 与 dashboard aggregator 待补） |
| F. 前端 typecheck | `pnpm typecheck` | ✅ |

### 端到端冒烟

```bash
# 1. 改 dedupe_vector_threshold → 0.88，期望 Redis 失效缓存
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@trendradar.dev","password":"Admin1234!"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
curl -s -X PUT localhost:8000/api/v1/admin/configs/dedupe_vector_threshold \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"configValue": 0.88}' | python -m json.tool

# 2. 手动触发 dedupe_task
curl -s -X POST localhost:8000/api/v1/admin/tasks/trigger \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"taskName": "pipeline.dedupe"}'
sleep 60
curl -s "localhost:8000/api/v1/admin/tasks?taskName=pipeline.dedupe" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool | head -30

# 3. 查看 audit_log
curl -s "localhost:8000/api/v1/admin/audit-logs?page=1&size=10" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool | head -30

# 4. 前端 http://localhost:5173/admin → 切换 4 个 Tab
```

### 单测结构

```
tests/admin/
  test_enums.py     # ConfigGroup / ValueType / TaskRunStatus / TargetType / AuditAction 不变量
  test_service.py   # _redact_sensitive / _coerce_and_check_type / rank_weights / AuditService 隔离 /
                    # ConfigService 校验 + @tracked_task 注册表元数据
```

API 层 / repository 层 / dashboard 聚合 / cleanup 任务留作下阶段（需要测试 DB + Celery worker 集成）补齐。

---

## 已知坑 & 待办

- Beat 端订阅 `ops:beat:reload` 未实现（Celery Beat 每分钟自然 reload，下轮自然生效；急用可重启 beat）
- `mv_ai_cost_daily` 物化视图未建（一期 SQL 聚合足够，二期加）
- CSV 导出审计日志未做（一期前端不导出）
- Audit hook 剩余 13 个写操作未接入（hotspot.split/merge、ai provider/model CRUD、auth.register）
- task_run_log 后端测试需要 DB + Celery worker 集成测试（已用 tracked_task 单测覆盖装饰器逻辑本身）
- `request.state.user_agent` 字段存在但尚未在 AuditService 写入 audit_log（IP 已写入）
- admin service dashboard 的 dashboard 数据查询部分没单测覆盖（45%）——下阶段补
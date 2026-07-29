# 后端开发规范（backend/）

## 分层

```
api          路由 + 请求/响应 DTO。只做参数校验与调用 service，不写业务逻辑
service      业务编排。跨模块调用的唯一入口
repository   数据访问。只有这一层能碰 ORM Session
model        SQLAlchemy ORM 定义
schema       Pydantic DTO
```

依赖方向单向：`api → service → repository → model`。禁止反向依赖，禁止 api 直接用 repository。

## 模块结构

```
app/modules/{module}/
  __init__.py
  api.py            APIRouter
  service.py
  repository.py
  model.py
  schema.py
  exceptions.py     该模块的业务异常（继承 AppException）
  tasks.py          该模块的 Celery 任务（如有）
```

## 规范

### 模型
- 所有表继承 `Base, TimestampMixin`（自带 id / created_at / updated_at / is_deleted）
- 字段类型严格按 SPEC；枚举用 `enum.StrEnum` + `VARCHAR(32)` 列
- 表名 snake_case 单数（`__tablename__ = "user"`）
- 索引在 `__table_args__` 中显式声明，命名 `idx_{表}_{字段}` / `uk_{表}_{字段}`

### Schema
- 统一继承 `CamelModel`（配 `alias_generator=to_camel, populate_by_name=True`）
- 请求 DTO 后缀 `Request` / `Create` / `Update`，响应 DTO 后缀 `Response` / `Detail` / `Item`
- 分页响应统一用 `Page[T]` 泛型

### Repository
- 所有查询默认带 `.where(Model.is_deleted.is_(False))`
- 删除一律软删除（`is_deleted = True`），除清理任务外禁止物理删除
- 禁止在循环里查询（N+1）；批量场景用 `WHERE id = ANY(:ids)` 一次取回后内存组装

### Service
- 业务校验在此层，抛 `AppException` 子类
- 需要事务的操作显式用 `async with session.begin_nested()`
- 跨模块调用只 import 对方的 `service`，禁止 import 对方的 `repository` / `model`

### API
- 路由函数只做：解析依赖 → 调 service → 返回
- 权限用 `Depends(require_role(Role.EDITOR))`
- 每个路由必须写 `summary` 与 `response_model`（OpenAPI 要给前端生成类型）
- 列表接口必须分页，`size` 上限 100

### 异步
- 全链路 async；禁止在 async 函数里做阻塞 IO
- CPU 密集操作（正文抽取、分词、embedding）放 Celery worker，或用 `run_in_threadpool`

### 外部 IO
- HTTP 一律用 `httpx.AsyncClient`，必须设 timeout
- 重试用 `tenacity`，指数退避；`4xx`（除 429）不重试
- 禁止在业务代码里直接 import 模型 SDK，一律走 `app.modules.ai.gateway.LLMGateway`

### 日志
- `structlog`，JSON 输出，必带 `trace_id`
- 敏感字段（`api_key` / `password` / `token`）在日志中必须脱敏
- 异常必须记录，禁止静默 `except: pass`

### 测试
- 目录 `tests/{module}/`，与模块一一对应
- 纯函数（parse / normalize / 评分公式 / 归一化）用固定 fixture 做单测，不连数据库
- 需要数据库的测试用独立测试库 + 每个测试回滚事务
- 外部 IO 一律打桩（`respx` 打 httpx，`monkeypatch` 打 LLMGateway）
- 每个模块必须可独立测试

## 常用命令

```bash
uv sync
uv run alembic revision --autogenerate -m "add user table"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run python -m app.scripts.seed
uv run uvicorn app.main:app --reload
uv run celery -A app.worker worker -l info -P solo    # Windows 用 -P solo
uv run celery -A app.worker beat -l info
uv run pytest --cov=app --cov-report=term-missing
uv run ruff check . --fix && uv run ruff format .
uv run mypy app
```

## 新增模块的步骤

1. 读 `doc/SPEC-{module}.md`
2. `app/modules/{module}/` 建包，写 `model.py`
3. 在 `alembic/env.py` 中 import 该 model
4. `alembic revision --autogenerate` → 人工检查生成的迁移 → `upgrade head`
5. `schema.py` → `repository.py` → `service.py` → `api.py`，每层配单测
6. 在 `app/main.py` 注册路由
7. 有 Celery 任务的话在 `app/worker/celery_app.py` 的 `autodiscover_tasks` 加上
8. 跑 `pytest` + `mypy` + `ruff`

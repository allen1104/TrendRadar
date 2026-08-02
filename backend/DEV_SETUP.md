# 开发环境启动手册（DEV_SETUP）

> 本地开发时的账号、密码、连接信息与首次启动步骤。
>
> ⚠️ **本文件只用于本地开发**。生产环境必须替换所有 `.env` 中的密钥与密码，且 **JWT SECRET 必须用 `openssl rand -hex 32` 生成新值**。

---

## 默认管理员账号（seed 创建）

`seed` 脚本启动时**只创建这一个账号**（角色 `ADMIN`），其他账号需通过 `POST /api/v1/auth/register` 注册。

| 字段 | 值 |
| --- | --- |
| 邮箱（登录用） | `admin@trendradar.dev` |
| 用户名 | `admin` |
| 密码 | `Admin1234!` |
| 角色 | `ADMIN` |

凭证来源：`backend/.env` 中的 `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD`。改 `.env` 后重跑 `uv run python -m app.scripts.seed` 会用新值更新（已存在的账号邮箱不变，密码在 `get_by_email` 命中时会跳过）。

---

## 其他关键连接信息（同 `.env`）

| 用途 | 值 |
| --- | --- |
| PostgreSQL | `trendradar:trendradar@localhost:5432/trendradar` |
| Redis | `localhost:6379/0`（Celery broker 用 DB 1，result 用 DB 2） |
| API base URL | `http://localhost:8000/api/v1` |
| Web base URL | `http://localhost:5173` |

> ⚠️ 当前 `backend/.env` 已被提交进 git 仓库（创建于 2026-07-29）。在仓库对外公开或多人协作前，请执行：
> 1. `git rm --cached backend/.env` 取消跟踪
> 2. 把 `.env` 加入 `.gitignore`
> 3. 用 `git filter-repo`（或 BFG）清理历史
> 4. 重新生成两个 `SECRET_KEY`（`openssl rand -hex 32`）并修改管理员密码

---

## 首次启动顺序

```bash
# 1. 起基础设施（PG + Redis）
docker compose up -d postgres redis

# 2. 装依赖
cd backend && uv sync

# 3. 跑迁移（建表）
uv run alembic upgrade head

# 4. 初始化配置 / Prompt / 管理员
uv run python -m app.scripts.seed

# 5. 起 API
uv run uvicorn app.main:app --reload

# 6. 起 worker（Windows 用 -P solo）
uv run celery -A app.worker worker -l info -P solo

# 7. 起 beat（另开终端）
uv run celery -A app.worker beat -l info

# 8. 起前端
cd ../frontend && pnpm install && pnpm dev
```

---

## 快速验证登录

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@trendradar.dev","password":"Admin1234!"}'
```

返回示例：

```json
{
  "accessToken": "eyJhbGci...",
  "refreshToken": "eyJhbGci...",
  "tokenType": "Bearer",
  "expiresIn": 7200,
  "user": {
    "userId": 1,
    "email": "admin@trendradar.dev",
    "username": "admin",
    "role": "ADMIN"
  }
}
```

之后用 `Authorization: Bearer <accessToken>` 调其他接口。

---

## 创建测试账号（USER 视角）

要测普通用户行为（收藏 / 问 AI / 趋势分析），不能复用 admin——admin 没有「用户」的体感。建一个 USER 角色账号：

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","username":"阿伦","password":"Pass1234!"}'
```

> 密码规则：≥8 位，含大小写字母 + 数字。弱密码会被后端拒（`400 WEAK_PASSWORD`）。

需要 EDITOR 视角测试（如运营后台、置顶事件）？用 admin 登录后调 `PATCH /api/v1/admin/users/{userId}` 把 dev 账号升级到 `EDITOR`，或直接用 admin 视角测。

---

## 前端登录页

`http://localhost:5173/login` 直接用 `admin@trendradar.dev / Admin1234!` 进。

未注册的账号可以先到 `/register` 注册，注册成功自动登录并跳回来源页。
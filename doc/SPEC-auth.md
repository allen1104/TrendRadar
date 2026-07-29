# 认证与权限模块（auth）

所属项目: @SPEC.md
模块状态: ⏳ 未开始
一期范围: ✅ 是
最后更新: 2026-07-29

---

## 功能目标

提供注册、登录、登出、Token 刷新、当前用户信息、用户偏好设置能力，
建立基于 JWT 的认证体系与单角色 RBAC 权限体系，为其他所有模块提供权限控制基础。

**不做**：第三方 OAuth 登录、手机验证码、多租户组织隔离（均延后）。

---

## 数据库设计

### `user` 表

| 字段            | 类型         | 必填 | 说明                                    |
| --------------- | ------------ | ---- | --------------------------------------- |
| id              | BIGSERIAL    | 是   | 主键                                    |
| email           | VARCHAR(120) | 是   | 登录邮箱，全局唯一（小写存储）          |
| username        | VARCHAR(50)  | 是   | 昵称，全局唯一                          |
| password_hash   | VARCHAR(128) | 是   | Argon2id 哈希，禁止 MD5/SHA             |
| avatar_url      | VARCHAR(500) | 否   | 头像地址                                |
| role            | VARCHAR(32)  | 是   | `USER` / `EDITOR` / `ADMIN`，默认 `USER` |
| status          | VARCHAR(32)  | 是   | `ACTIVE` / `DISABLED`，默认 `ACTIVE`    |
| last_login_at   | TIMESTAMPTZ  | 否   | 最后登录时间                            |
| created_at      | TIMESTAMPTZ  | -    | 创建时间                                |
| updated_at      | TIMESTAMPTZ  | -    | 更新时间                                |
| is_deleted      | BOOLEAN      | -    | 逻辑删除，默认 false                    |

索引：`uk_user_email(email) WHERE is_deleted=false`、`uk_user_username(username) WHERE is_deleted=false`

> `GUEST` 不落库，指未携带有效 Token 的匿名请求。

### `user_preference` 表

| 字段                | 类型        | 必填 | 说明                                          |
| ------------------- | ----------- | ---- | --------------------------------------------- |
| id                  | BIGSERIAL   | 是   | 主键                                          |
| user_id             | BIGINT      | 是   | 用户ID，唯一                                  |
| default_scope       | VARCHAR(32) | 是   | 默认时间维度 `TODAY`/`WEEK`/`MONTH`，默认 `TODAY` |
| followed_categories | JSONB       | 否   | 关注的分类，如 `["AI","AGENT","LLM"]`，默认 `[]` |
| followed_tags       | JSONB       | 否   | 关注的标签 ID 数组，默认 `[]`                 |
| muted_sources       | JSONB       | 否   | 屏蔽的采集源 ID 数组，默认 `[]`               |
| daily_report_opt_in | BOOLEAN     | 是   | 是否订阅日报，默认 false                      |
| created_at          | TIMESTAMPTZ | -    | 创建时间                                      |
| updated_at          | TIMESTAMPTZ | -    | 更新时间                                      |
| is_deleted          | BOOLEAN     | -    | 逻辑删除，默认 false                          |

索引：`uk_user_pref_user(user_id)`

> 用户注册成功后自动创建一条默认 `user_preference`。

### Redis 键设计（不落库）

| 键                             | 类型   | TTL          | 说明                       |
| ------------------------------ | ------ | ------------ | -------------------------- |
| `auth:blacklist:{jti}`         | STRING | = Token 剩余有效期 | 登出后的 access token 黑名单 |
| `auth:refresh:{userId}:{jti}`  | STRING | 14 天        | 有效 refresh token 白名单  |
| `auth:login_fail:{email}`      | STRING | 15 分钟      | 登录失败计数，用于锁定     |

---

## 后端接口

### POST /api/v1/auth/register
**说明**: 用户注册，默认角色 `USER`

**Request Body**:
```json
{
  "email": "dev@example.com",
  "username": "阿伦",
  "password": "Pass1234!"
}
```

**Response 201**:
```json
{
  "userId": 1,
  "email": "dev@example.com",
  "username": "阿伦",
  "role": "USER"
}
```

**错误情况**:
- 邮箱已注册 → `409` `{ "errorCode": "EMAIL_EXISTS", "detail": "该邮箱已被注册" }`
- 用户名已占用 → `409` `USERNAME_EXISTS`
- 密码强度不足 → `400` `WEAK_PASSWORD`（规则：≥8 位，含大小写字母 + 数字）

---

### POST /api/v1/auth/login
**说明**: 登录，返回双 Token

**Request Body**:
```json
{ "email": "dev@example.com", "password": "Pass1234!" }
```

**Response 200**:
```json
{
  "accessToken": "eyJhbGci...",
  "refreshToken": "eyJhbGci...",
  "tokenType": "Bearer",
  "expiresIn": 7200,
  "user": {
    "userId": 1,
    "email": "dev@example.com",
    "username": "阿伦",
    "avatarUrl": null,
    "role": "USER"
  }
}
```

**错误情况**:
- 邮箱不存在 / 密码错误 → `401` `INVALID_CREDENTIALS`，文案统一"邮箱或密码错误"（不区分，防枚举）
- 账号被禁用 → `403` `ACCOUNT_DISABLED`
- 15 分钟内失败 ≥ 5 次 → `429` `TOO_MANY_ATTEMPTS`，锁定 15 分钟

---

### POST /api/v1/auth/refresh
**说明**: 用 refreshToken 换新的 accessToken（refreshToken 旋转，旧的立即失效）

**Request Body**: `{ "refreshToken": "eyJhbGci..." }`

**Response 200**: 同 login，返回新的 accessToken + refreshToken

**错误情况**:
- refreshToken 无效/过期/已被使用 → `401` `INVALID_REFRESH_TOKEN`

---

### POST /api/v1/auth/logout
**说明**: 登出。access token 的 `jti` 加入 Redis 黑名单，该用户所有 refresh token 作废

**Headers**: `Authorization: Bearer {accessToken}`

**Response 204**: 无响应体

---

### GET /api/v1/auth/me
**说明**: 获取当前登录用户信息 + 偏好设置

**Headers**: `Authorization: Bearer {accessToken}`

**Response 200**:
```json
{
  "userId": 1,
  "email": "dev@example.com",
  "username": "阿伦",
  "avatarUrl": null,
  "role": "USER",
  "lastLoginAt": "2026-07-29T08:30:00Z",
  "preference": {
    "defaultScope": "TODAY",
    "followedCategories": ["AI", "AGENT"],
    "followedTags": [12, 34],
    "mutedSources": [],
    "dailyReportOptIn": false
  }
}
```

---

### PATCH /api/v1/auth/me
**说明**: 修改自己的昵称/头像

**Request Body**（字段均可选）:
```json
{ "username": "新昵称", "avatarUrl": "https://..." }
```

**Response 200**: 同 GET /auth/me

---

### PUT /api/v1/auth/me/password
**说明**: 修改密码，成功后所有 Token 作废，需重新登录

**Request Body**:
```json
{ "oldPassword": "Pass1234!", "newPassword": "NewPass5678!" }
```

**Response 204**

**错误情况**: 旧密码错误 → `400` `WRONG_OLD_PASSWORD`

---

### PUT /api/v1/auth/me/preference
**说明**: 更新个人偏好

**Request Body**:
```json
{
  "defaultScope": "WEEK",
  "followedCategories": ["AI", "LLM", "AGENT"],
  "followedTags": [12],
  "mutedSources": [3],
  "dailyReportOptIn": true
}
```

**Response 200**: 返回更新后的 preference 对象

---

### GET /api/v1/admin/users
**说明**: 用户列表（仅 `ADMIN`）

**Query**: `page` `size` `keyword`（匹配 email/username）`role` `status` `sort`（白名单：`createdAt` `lastLoginAt`）

**Response 200**:
```json
{
  "items": [
    { "userId": 1, "email": "dev@example.com", "username": "阿伦",
      "role": "USER", "status": "ACTIVE", "lastLoginAt": "2026-07-29T08:30:00Z",
      "createdAt": "2026-07-01T00:00:00Z" }
  ],
  "total": 1, "page": 1, "size": 20, "pages": 1
}
```

---

### PATCH /api/v1/admin/users/{userId}
**说明**: 修改用户角色或状态（仅 `ADMIN`）

**Request Body**: `{ "role": "EDITOR", "status": "DISABLED" }`（均可选）

**Response 200**: 用户对象

**错误情况**:
- 修改自己的角色 → `400` `CANNOT_MODIFY_SELF_ROLE`
- 系统中最后一个 ADMIN 被降级/禁用 → `400` `LAST_ADMIN_PROTECTED`

---

## 前端页面

### 登录页（`/login`）
- 邮箱输入框：必填，前端做格式校验
- 密码输入框：必填，密文显示，带显示/隐藏切换
- 「登录」按钮：提交中禁用并显示 spinner
- 底部「还没有账号？去注册」跳 `/register`
- 成功：`accessToken` 存内存 + `refreshToken` 存 `localStorage`，写入 Zustand `authStore`，跳转来源页或 `/`
- 失败：表单下方红色 Alert 显示后端 `detail`

### 注册页（`/register`）
- 邮箱 / 昵称 / 密码 / 确认密码
- 密码强度实时提示条（弱/中/强）
- 两次密码不一致时提交按钮禁用
- 成功后自动登录并跳转 `/`

### 个人中心（`/me`）
Tab 布局：
- **基本资料**：昵称、头像上传（一期只支持填 URL）
- **偏好设置**：默认时间维度（Select）、关注分类（多选 Chips）、关注标签（Combobox 多选）、屏蔽采集源（多选）、订阅日报（Switch）
- **安全**：修改密码表单，成功后弹 Toast 并强制跳 `/login`

### 用户管理（`/admin/users`，ADMIN）
- 表格：邮箱、昵称、角色（Badge 彩色）、状态、最后登录、注册时间
- 顶部筛选：关键字搜索、角色下拉、状态下拉
- 行内操作：改角色（Select 直接改）、启用/禁用（Switch）
- 操作前二次确认 Dialog

### 认证基础设施
- **Axios 拦截器**：
  - 请求拦截：自动注入 `Authorization: Bearer <accessToken>`
  - 响应拦截：`401` 且非 refresh 接口 → 自动调 `/auth/refresh` 重试一次；再失败清空登录态跳 `/login`
  - 并发 401 需请求队列去重，避免同时多次 refresh
- **`<RequireRole minRole="EDITOR">`**：
  - 未登录 → 重定向 `/login?redirect={当前路径}`
  - 已登录但角色不足 → 渲染 403 页面
- **侧边栏菜单按角色渲染**：
  - `GUEST`/`USER`：热点中心、趋势分析、我的收藏、个人中心
  - `EDITOR`：+ 运营模式开关、日报审核
  - `ADMIN`：+ 采集源管理、AI 配置、任务监控、用户管理、成本统计

---

## 业务规则

- **密码哈希**：Argon2id（`argon2-cffi`），参数 `time_cost=3, memory_cost=65536, parallelism=4`。禁止 MD5/SHA1/明文
- **accessToken**：HS256，有效期 **2 小时**，payload 含 `sub`(userId)、`role`、`jti`、`exp`、`iat`
- **refreshToken**：HS256，有效期 **14 天**，单独密钥，payload 含 `sub`、`jti`、`exp`
- **refreshToken 旋转**：每次刷新签发新的并删除旧 `jti`；检测到已失效 `jti` 被复用 → 判定为泄露，作废该用户全部 refresh token
- **登出**：`jti` 写入 Redis 黑名单，TTL = token 剩余有效期；鉴权中间件每次校验黑名单
- **角色包含关系**：`ADMIN(30) > EDITOR(20) > USER(10) > GUEST(0)`，用数值比较实现 `require_role`
- **登录失败锁定**：同一邮箱 15 分钟内失败 5 次锁定 15 分钟，成功登录清零
- **邮箱大小写不敏感**：存储与比较统一 `lower()`
- **最后一个 ADMIN 保护**：系统必须至少保留一个 `ACTIVE` 的 ADMIN
- **匿名访问白名单**：`GET /api/v1/events*`、`GET /api/v1/tags`、`GET /api/v1/sources`（只读）允许 GUEST 访问，其余接口一律需登录
- **限流**：`/auth/login` `/auth/register` 按 IP 限流 10 次/分钟

---

## 完成标准

- [ ] `user` / `user_preference` 表与 Alembic 迁移完成
- [ ] 注册、登录、刷新、登出、`/auth/me` 五个接口联调通过
- [ ] JWT 鉴权中间件生效，黑名单校验有效
- [ ] `require_role` 依赖生效，越权返回 403
- [ ] refreshToken 旋转 + 复用检测有效
- [ ] 登录失败锁定生效
- [ ] 前端登录/注册/个人中心页面完成
- [ ] Axios 401 自动刷新 + 并发去重生效
- [ ] `<RequireRole>` 路由守卫与角色菜单生效
- [ ] 用户管理页 ADMIN 可改角色/状态，最后一个 ADMIN 受保护
- [ ] 单元测试覆盖：密码哈希、Token 签发/校验/黑名单、角色比较、锁定逻辑

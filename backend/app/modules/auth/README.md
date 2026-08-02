# auth 模块

认证与权限。为其他所有模块提供身份识别与 RBAC 基础。

需求：[doc/SPEC-auth.md](../../../../doc/SPEC-auth.md)
开发账号与首次启动：[DEV_SETUP.md](../../DEV_SETUP.md)

---

## 提供给其他模块的能力

其他模块**只从 `app.modules.auth.deps` import**，不要碰本模块的 repository / model。

```python
from app.modules.auth.deps import AdminUser, CurrentUser, EditorUser, OptionalUser
from app.modules.auth.enums import Role, has_role

@router.get("/events")
async def list_events(user: OptionalUser):        # GUEST 可访问
    ...

@router.post("/collections")
async def collect(user: CurrentUser):             # 需登录
    ...

@router.patch("/events/{id}")
async def pin_event(user: EditorUser):            # EDITOR 及以上
    ...

@router.get("/admin/configs")
async def configs(user: AdminUser):               # 仅 ADMIN
    ...
```

`OptionalUser` 在无 Token / Token 无效 / 账号禁用时返回 `None`，**不抛异常** ——
GUEST 可访问的接口用它，然后用 `current_role(user)` 折叠成角色做可见性判断。

---

## 关键设计

### 双 Token + 旋转

| Token | 有效期 | 密钥 | 存储位置 |
| --- | --- | --- | --- |
| access | 2 小时 | `SECRET_KEY` | 前端内存 |
| refresh | 14 天 | `JWT_REFRESH_SECRET_KEY` | 前端 localStorage |

- 两者 payload 都带 `jti`，且带 `type` 字段，**互不通用**（用错密钥或类型一律拒绝）
- 每次 `/auth/refresh` 签发新的一对，旧 refresh 的 `jti` 用 `GETDEL` 原子消费
- **复用检测**：签名有效但 `jti` 不在白名单 → 判定为泄露，作废该用户全部 refresh token

### Redis 键

| 键 | 用途 | TTL |
| --- | --- | --- |
| `auth:blacklist:{jti}` | 登出后的 access token 黑名单 | = token 剩余寿命 |
| `auth:refresh:{userId}:{jti}` | 有效 refresh token 白名单 | 14 天 |
| `auth:login_fail:{email}` | 登录失败计数 | 15 分钟 |
| `ratelimit:login:{ip}` | 登录接口 IP 限流 | 60 秒 |

### 安全要点

- 密码 **Argon2id**（`time_cost=3, memory_cost=64MB, parallelism=4`）
- 登录失败**不区分**"邮箱不存在"和"密码错误"，统一 `INVALID_CREDENTIALS`（防用户枚举）
- 同一邮箱 15 分钟内失败 5 次锁定 15 分钟
- 改密后作废该用户全部 refresh token
- 邮箱大小写不敏感（存储与比较统一 `lower()`）
- 最后一个启用中的 ADMIN 受保护，不能被降级或禁用
- ADMIN 不能改自己的角色/状态

---

## 前端集成

- `useAuthBootstrap()` 在 `RootLayout` / `AuthLayout` 里调用一次：
  启动时用 localStorage 的 refreshToken 静默恢复会话，并订阅"会话失效"广播
- axios 拦截器在 `401` 时自动刷新一次并重试；**并发 401 复用同一个 refresh Promise**（`refreshPromise` 去重）
- `<RequireRole minRole="EDITOR">` 包路由；未登录跳 `/login?redirect=...`，角色不足渲染 403
- `client.ts` 不 import `authStore`（避免循环依赖），改用 `onSessionExpired()` 发布订阅

---

## 待办

- [ ] 集成测试：需要测试库 + `httpx.AsyncClient`（等 db fixture 落地）
- [ ] 头像上传（当前只支持填 URL）
- [ ] 接入 `admin` 模块的 `AuditService`，记录 `USER_ROLE_CHANGE` / `USER_STATUS_CHANGE`
      （`service.py` 中已留 TODO 位）
- [ ] 前端接口类型改用 `pnpm gen:api` 生成的 schema 替换手写的 `types.ts`

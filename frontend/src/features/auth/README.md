# auth 模块（前端）

需求：[doc/SPEC-auth.md](../../../doc/SPEC-auth.md)

## 文件结构

```
features/auth/
  types.ts                    手写过渡类型，跑通 pnpm gen:api 后改用生成的 schema
  api/auth.ts                 纯接口函数
  hooks/useAuth.ts            Query hooks + 会话恢复 + 401 刷新订阅
  components/
    RequireRole.tsx           路由守卫
    PasswordStrengthMeter.tsx 密码强度条（与后端 validate_password_strength 同源）
  pages/
    LoginPage.tsx
    RegisterPage.tsx
    ProfilePage.tsx
```

## 关键设计

### accessToken 在内存，refreshToken 在 localStorage
- 避免 XSS 通过 localStorage 拿到长期凭证
- 浏览器关闭再开能用 refreshToken 静默恢复会话
- 会话恢复失败自动清空登录态

### 401 自动刷新（并发去重）
- axios 拦截器在 `401` 时自动调 `/auth/refresh` 并重试一次
- 同一时刻只允许一个 refresh 在飞（`refreshPromise` 模块级 Promise）
- 并发的 401 复用同一个 Promise，不会触发 race condition
- refresh 失败 → 广播"会话失效"→ `authStore.clear()` → 跳 `/login`

### 路由守卫
- `<RequireRole minRole="EDITOR">`：未登录跳 `/login?redirect=...`；角色不足渲染 403
- `<RedirectIfAuthenticated>`：已登录访问 `/login` / `/register` 跳走

### 前后端密码规则一致
- `PasswordStrengthMeter.evaluatePassword` 与后端 `validate_password_strength` 用同一规则
- 都用：≥8 位 + 大写 + 小写 + 数字
- 真实校验永远在服务端（前端只是体验优化）

## 已实现

- [x] 登录 / 注册 / 登出
- [x] 当前用户信息、修改昵称/头像、修改密码、更新偏好
- [x] JWT 双 Token，401 自动刷新
- [x] 会话恢复（启动时用 refreshToken 静默登录）
- [x] RequireRole 路由守卫
- [x] ADMIN 用户管理页（列表 + 改角色 + 启用/禁用，最后一个 ADMIN 保护由后端保证）
- [x] 密码强度条
- [x] 操作成功/失败 Toast 反馈

## 待办

- [ ] 后端起来后跑 `pnpm gen:api`，用 `components['schemas']['MeResponse']` 等替换手写的 `types.ts`
- [ ] 头像上传（当前只支持填 URL）
- [ ] 邮件找回密码

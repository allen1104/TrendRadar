# 前端开发规范（frontend/）

## 目录结构

```
src/
  app/               路由表、Providers、全局布局
  features/{module}/ 按业务模块组织
    api/             该模块的接口调用（用 http client）
    components/      该模块专属组件
    hooks/           TanStack Query hooks
    pages/           路由页面
    types/           该模块的本地类型（接口类型走生成）
  components/ui/     shadcn/ui 组件（generated，尽量不手改）
  lib/               http client、utils、通用 hooks
  stores/            Zustand（只放客户端状态）
  styles/            全局样式
```

## 铁律

1. **接口类型必须由 `pnpm gen:api` 从 `openapi.json` 生成**，禁止手写接口 DTO 类型
2. **服务端状态一律 TanStack Query**，禁止把接口数据塞进 Zustand
3. **筛选条件必须同步到 URL SearchParams**（可分享、可刷新保持）
4. **所有异步区域必须有 loading skeleton 与 error 边界**，不允许白屏
5. **Markdown 渲染必须 XSS 过滤**（`rehype-sanitize`）
6. 图表统一 ECharts；组件统一 shadcn/ui；图标统一 lucide-react

## 约定

### API 层
- 每个 feature 的 `api/` 下按资源分文件，导出纯函数（`getEvents(params)`）
- 错误统一抛 `ApiError`（含 `status` / `errorCode` / `detail`）
- 后端是 RESTful 原生状态码，**不要写 `if (res.code === 200)` 这类判断**

### Query hooks
- key 规范：`['events', 'list', params]` / `['events', 'detail', id]`
- 变更后用 `invalidateQueries` 精确失效，不要全量 `invalidateQueries()`
- 乐观更新（收藏、置顶这类）用 `onMutate` + `onError` 回滚

### 状态
- 服务端数据 → TanStack Query
- URL 可表达的状态（筛选、分页、Tab）→ `useSearchParams`
- 纯 UI 状态（抽屉开关、选中项）→ `useState`
- 跨页面共享的客户端状态（登录态、主题）→ Zustand

### 组件
- 页面组件只负责组装，逻辑抽到 hooks
- 列表项组件必须 memo（`React.memo`）避免整列表重渲染
- 表单用受控组件 + zod 校验（与后端校验规则保持一致）

### 权限
- 路由用 `<RequireRole minRole="EDITOR">` 包装
- 菜单按 `useAuthStore().user?.role` 过滤
- **前端权限只是体验优化，真正的校验在后端**

### 时间
- 后端返回 UTC ISO 8601，前端用 `date-fns` 按浏览器时区渲染
- 列表用相对时间（"2 小时前"），详情用绝对时间

### 命名
- 组件 `PascalCase.tsx`，hooks `useXxx.ts`，工具 `camelCase.ts`
- 事件处理函数 `handleXxx`，传给子组件的 prop 叫 `onXxx`

## 常用命令

```bash
pnpm install
pnpm dev                # :5173，/api 代理到 :8000
pnpm gen:api            # 后端起着的时候跑，生成 src/lib/api/schema.d.ts
pnpm typecheck
pnpm lint --fix
pnpm build
```

## 新增模块的步骤

1. 读 `doc/SPEC-{module}.md` 的「前端页面」章节
2. 后端接口就绪后跑 `pnpm gen:api`
3. `features/{module}/api/` 写接口函数
4. `features/{module}/hooks/` 写 Query hooks
5. `features/{module}/components/` + `pages/` 写 UI
6. 在 `app/router.tsx` 注册路由
7. `pnpm typecheck && pnpm build`

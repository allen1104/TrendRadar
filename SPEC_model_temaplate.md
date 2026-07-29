# 认证模块（auth）

所属项目: @SPEC.md
模块状态: ✅ 已完成
最后更新: 2024-01-15

---

## 功能目标
提供用户登录、登出、当前用户信息查询功能，
建立 JWT 认证体系，为其他所有模块提供权限控制基础。

---

## 数据库设计

### user 表
| 字段       | 类型         | 必填 | 说明                      |
| ---------- | ------------ | ---- | ------------------------- |
| id         | BIGINT       | 是   | 主键，自增                |
| username   | VARCHAR(50)  | 是   | 登录名，全局唯一          |
| password   | VARCHAR(100) | 是   | BCrypt 加密               |
| real_name  | VARCHAR(50)  | 是   | 真实姓名                  |
| dept_id    | BIGINT       | 是   | 所属部门ID                |
| role       | VARCHAR(20)  | 是   | 角色: STAFF/MANAGER/ADMIN |
| status     | TINYINT      | 是   | 1=启用 0=禁用，默认1      |
| created_at | DATETIME     | -    | 创建时间                  |
| updated_at | DATETIME     | -    | 更新时间                  |
| is_deleted | TINYINT      | -    | 逻辑删除，默认0           |

### dept 表
| 字段       | 类型        | 必填 | 说明               |
| ---------- | ----------- | ---- | ------------------ |
| id         | BIGINT      | 是   | 主键，自增         |
| name       | VARCHAR(50) | 是   | 部门名称，全局唯一 |
| created_at | DATETIME    | -    | 创建时间           |
| updated_at | DATETIME    | -    | 更新时间           |
| is_deleted | TINYINT     | -    | 逻辑删除，默认0    |

---

## 后端接口

### POST /api/v1/auth/login
**说明**: 用户登录，返回 JWT Token

**Request Body**:
```json
{
  "username": "zhangsan",
  "password": "Pass1234"
}
```

**Response**:
```json
{
  "code": 200,
  "data": {
    "token": "eyJhbGci...",
    "userId": 1,
    "realName": "张三",
    "role": "STAFF",
    "deptId": 2,
    "deptName": "技术部"
  }
}
```

**错误情况**:
- 用户名不存在 → code: 400, message: "用户名或密码错误"
- 密码错误 → code: 400, message: "用户名或密码错误"
- 账号禁用 → code: 400, message: "账号已被禁用"

---

### POST /api/v1/auth/logout
**说明**: 登出，将当前 Token 加入黑名单（Redis，TTL同Token过期时间）

**Headers**: Authorization: Bearer {token}

**Response**:
```json
{ "code": 200, "message": "ok" }
```

---

### GET /api/v1/auth/me
**说明**: 获取当前登录用户信息

**Headers**: Authorization: Bearer {token}

**Response**:
```json
{
  "code": 200,
  "data": {
    "userId": 1,
    "realName": "张三",
    "role": "STAFF",
    "deptId": 2,
    "deptName": "技术部"
  }
}
```

---

## 前端页面

### 登录页（/login）
- 用户名输入框：必填
- 密码输入框：必填，密文显示
- 登录按钮：点击后调用登录接口
- 成功后：Token 存入 localStorage，跳转 /dashboard
- 失败后：在表单下方显示错误信息

### 权限路由守卫
- 未登录访问任何 /dashboard/* 路由 → 跳转 /login
- 已登录访问 /login → 跳转 /dashboard
- 根据 role 控制侧边菜单显示项：
  - STAFF: 我的申请
  - MANAGER: 我的申请、待审批、审批历史
  - ADMIN: 我的申请、所有记录、假期类型管理

---

## 业务规则
- JWT Token 有效期 8 小时
- 登出后 Token 立即失效（黑名单机制）
- 密码存储必须 BCrypt 加密，禁止 MD5

## 完成标准
- [x] 登录接口联调通过
- [x] JWT 鉴权中间件生效
- [x] 前端登录页完成
- [x] 权限路由守卫生效
- [x] /auth/me 接口返回正确
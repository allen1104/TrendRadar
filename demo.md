好，用一个完整的真实例子走一遍——**从零开始开发一个"员工请假管理"系统**，4个模块，全程展示每一步输入什么、Claude 输出什么。

------

## 第一步：项目初始化

```bash
mkdir enterprise-leave
cd enterprise-leave
claude
```

------

## 第二步：生成全局 SPEC

输入：

```
我要开发一个TrendRadar（趋势雷达）软件，需求在当前目录下“TrendRadar.md”文件中。
用 AskUserQuestion 访谈我，搞清楚：
1. 有哪些角色
2. 有哪些功能模块
3. 模块间的关系
4. 核心业务流程
访谈结束后参考SPEC_template.md生成总的SPEC.md，参考SPEC_model_temaplate.md生成doc/SPEC-{model}.md，参考CLAUDE_template.md生成CLAUDE.md
其中：
SPEC.md          →  目录 + 索引 + 全局约定 + 模块状态总览
SPEC-{module}.md →  单模块的完整需求：字段、接口、页面、规则、完成标准
最后创建 backend 和 frontend 目录及基础文件
```

**Claude 开始访谈：**

```
Q1: 系统有哪些角色？他们分别能做什么？
```

你回答：

```
三种角色：
- 员工：提交请假申请、查看自己的申请记录
- 部门经理：审批本部门员工的请假申请
- HR/管理员：管理假期类型、查看所有人的请假记录、导出报表
Q2: 请假申请有哪些字段？流程是怎样的？
```

你回答：

```
字段：假期类型（年假/病假/事假等）、开始时间、结束时间、天数（自动算）、申请原因
流程：员工提交 → 部门经理审批（同意/拒绝，可填备注）→ 结束
状态：待审批、已同意、已拒绝、已撤销
Q3: 假期类型有哪些规则？比如年假有天数限制吗？
```

你回答：

```
假期类型由HR配置，包含：类型名称、年度可用天数（0表示不限制）
员工每年剩余天数需要展示，但这期不做自动扣减，先做基础流程
Q4: 有哪些列表和查询需求？
```

你回答：

```
员工：看自己的申请列表，可按状态筛选
经理：看待审批列表（默认）和历史审批列表，可按员工姓名搜索
HR：看所有人的记录，可按部门、员工、时间范围、状态筛选，能导出Excel
```

**访谈结束，Claude 生成 `SPEC.md`：**

```markdown
# 员工请假管理系统 — 需求文档

最后更新: 2024-01-20
状态: 已确认

---

## 系统概述
企业内部请假管理系统，支持员工申请、经理审批、HR管理的完整流程。

## 角色与权限
| 角色 | 标识 | 核心权限 |
|------|------|------|
| 员工 | STAFF | 提交/撤销自己的申请，查看自己的记录 |
| 部门经理 | MANAGER | 审批本部门申请，查看本部门所有记录 |
| HR管理员 | ADMIN | 管理假期类型，查看/导出所有记录 |

## 模块列表
1. 认证模块（auth）— 登录、JWT、权限控制
2. 假期类型模块（leave-type）— HR 配置假期种类
3. 请假申请模块（leave-apply）— 核心业务模块
4. 审批模块（leave-approve）— 经理审批流程

---

## 模块1：认证（auth）

### 接口
- POST /api/v1/auth/login → 返回 JWT token + 用户信息
- POST /api/v1/auth/logout → 使 token 失效
- GET /api/v1/auth/me → 获取当前用户信息

### 用户表字段
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键 |
| username | String | 登录名，唯一 |
| password | String | BCrypt加密 |
| realName | String | 真实姓名 |
| deptId | Long | 部门ID |
| role | Enum | STAFF/MANAGER/ADMIN |
| status | Integer | 1启用 0禁用 |

---

## 模块2：假期类型（leave-type）

### 功能描述
HR配置系统中的假期种类，员工申请时从此列表选择。

### 数据字段
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | Long | - | 主键 |
| name | String | 是 | 类型名称，如"年假"，全局唯一 |
| annualDays | Integer | 是 | 年度可用天数，0表示不限制 |
| description | String | 否 | 说明备注 |
| status | Integer | 是 | 1启用 0禁用 |

### 前端页面
- 列表页（仅ADMIN可访问）：展示所有假期类型，含启用/禁用切换
- 表单：新增/编辑（抽屉形式）

### 后端接口
- GET /api/v1/leave-types → 列表（全部角色可查，用于申请时的下拉）
- GET /api/v1/leave-types/page → 分页（仅ADMIN）
- POST /api/v1/leave-types → 新增（仅ADMIN）
- PUT /api/v1/leave-types/{id} → 编辑（仅ADMIN）
- PATCH /api/v1/leave-types/{id}/status → 启用/禁用（仅ADMIN）

### 业务规则
- 名称全局唯一
- 禁用的假期类型不出现在申请下拉中
- 有申请记录引用的假期类型不允许删除

---

## 模块3：请假申请（leave-apply）

### 功能描述
员工提交请假申请，查看自己的申请状态。

### 数据字段
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | Long | - | 主键 |
| userId | Long | - | 申请人ID（取当前登录用户） |
| leaveTypeId | Long | 是 | 假期类型ID |
| startDate | Date | 是 | 开始日期 |
| endDate | Date | 是 | 结束日期 |
| days | Integer | - | 请假天数（后端自动计算，endDate-startDate+1） |
| reason | String | 是 | 申请原因，10-200字 |
| status | Enum | - | PENDING/APPROVED/REJECTED/CANCELLED |
| createdAt | DateTime | - | 提交时间 |

### 前端页面

**员工视角 — 我的申请列表**
- 列：假期类型、开始日期、结束日期、天数、状态、提交时间、操作
- 筛选：状态（全部/待审批/已同意/已拒绝/已撤销）
- 操作：新建申请（按钮）、撤销（仅待审批状态可撤销）

**申请表单（抽屉）**
- 假期类型：下拉选择（仅显示启用的类型）
- 开始/结束日期：日期选择器，结束不能早于开始
- 天数：自动计算展示，不可编辑
- 申请原因：文本域，10-200字

### 后端接口
- GET /api/v1/leave-applies/my → 我的申请列表，支持status筛选和分页
- POST /api/v1/leave-applies → 提交申请
- PATCH /api/v1/leave-applies/{id}/cancel → 撤销（仅本人且状态为PENDING）

### 业务规则
- 申请日期不能是过去的日期
- 同一时间段不能有重叠的申请（状态为PENDING或APPROVED的）
- 撤销后状态改为CANCELLED，不可恢复

---

## 模块4：审批（leave-approve）

### 功能描述
经理审批本部门员工的请假申请；HR查看所有记录并可导出。

### 审批字段
在 leave_apply 表新增：
| 字段 | 类型 | 说明 |
|------|------|------|
| approverId | Long | 审批人ID |
| approveTime | DateTime | 审批时间 |
| approveComment | String | 审批备注（可选） |

### 前端页面

**经理视角 — 审批列表**
- 默认显示"待审批"Tab，另有"已审批"Tab
- 列：员工姓名、假期类型、开始日期、结束日期、天数、申请原因、提交时间
- 搜索：员工姓名关键词
- 操作：同意、拒绝（弹窗填写备注，备注可选）

**HR视角 — 全部记录**
- 筛选：部门、员工姓名、假期类型、时间范围、状态
- 列：员工、部门、假期类型、时间、天数、状态、审批人、审批时间
- 导出：按当前筛选条件导出Excel

### 后端接口
- GET /api/v1/leave-applies/dept → 本部门申请列表（MANAGER）
- GET /api/v1/leave-applies/all → 所有申请列表（ADMIN）
- POST /api/v1/leave-applies/{id}/approve → 审批（MANAGER）
  Body: { approved: boolean, comment?: string }
- GET /api/v1/leave-applies/export → 导出Excel（ADMIN）

### 业务规则
- 经理只能审批本部门（deptId匹配）的申请
- 审批同意/拒绝后状态不可再更改
- 导出Excel包含当前所有筛选条件的全量数据（不分页）

## 待定问题
- [ ] 节假日/周末是否计入请假天数？（暂定：直接计算自然日）
- [ ] 是否需要邮件通知？（暂不做）
```

你确认后，Claude 继续生成 `CLAUDE.md`：

```markdown
# 员工请假管理系统

## 技术栈
Next.js 15 App Router · TypeScript strict · Tailwind CSS · Ant Design
Spring Boot 3 · MyBatis-Plus · Maven · Spring Security + JWT
MySQL 8 · Docker Compose

## ⚡ 当前模块：骨架期

## 模块状态
- [ ] 骨架（auth + 基础设施）
- [ ] 假期类型（leave-type）
- [ ] 请假申请（leave-apply）
- [ ] 审批（leave-approve）

## 快速命令
- 启动: `docker-compose up -d`
- 导出API: `curl http://localhost:8080/v3/api-docs > openapi.json`
- 更新类型: `cd frontend && pnpm gen:api`
- 验证: `cd backend && mvn test && cd ../frontend && pnpm typecheck`

## 前后端约定
- API前缀: `/api/v1/`
- 认证: JWT Header `Authorization: Bearer <token>`
- 响应: `{ code, message, data }`
- 分页入参: `page(从0)/size`，出参: `{ records, total, current, size }`
- 时间格式: ISO 8601，日期格式: yyyy-MM-dd

## 参考文件
- @SPEC.md
- @.claude/progress/PROGRESS.md
- @frontend/CLAUDE.md
- @backend/CLAUDE.md
```

提交：

```bash
git init
git add SPEC.md CLAUDE.md
git commit -m "docs: 初始化项目需求文档"
```

------

## 第三步：骨架期

根目录 session，输入：

```
读 CLAUDE.md，当前是骨架期。
初始化前后端项目并建立完整技术骨架：

后端（backend/）：
- Spring Boot 3 + Maven 项目结构
- Spring Security + JWT 过滤器
- 统一响应 Result<T> 和全局异常处理
- Swagger/OpenAPI 配置
- docker-compose.yml

前端（frontend/）：
- Next.js 15 App Router
- lib/axios.ts（JWT自动附加+统一解包）
- 登录页 app/login/page.tsx
- 后台布局 app/(dashboard)/layout.tsx（含侧边菜单）
- 权限路由守卫（未登录跳转登录页）

完成后用 docker-compose up -d 验证所有服务启动正常。
```

Claude 完成骨架，所有服务启动后，输入：

```
骨架验证通过，/switch-phase 切换到假期类型模块
```

Claude 更新 `CLAUDE.md`：

```markdown
## ⚡ 当前模块：假期类型（leave-type）

## 模块状态
- [x] 骨架（auth + 基础设施）
- [ ] 假期类型（leave-type）  ← 当前
- [ ] 请假申请（leave-apply）
- [ ] 审批（leave-approve）
```

------

## 第四步：开发第一个业务模块

输入：

```
读 SPEC.md 的"假期类型"章节，用 /build-module 全栈实现。
```

Claude 按 Skill 步骤依次执行，你能看到完整过程：

**后端部分：**

```java
// 1. Entity
@Data @Builder @TableName("leave_type")
public class LeaveType {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String name;
    private Integer annualDays;
    private String description;
    private Integer status;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
    @TableLogic
    private Integer isDeleted;
}
// 2. Controller（含 Swagger 注解）
@Tag(name = "假期类型管理")
@RestController
@RequestMapping("/api/v1/leave-types")
@RequiredArgsConstructor
public class LeaveTypeController {

    private final LeaveTypeService leaveTypeService;

    @Operation(summary = "获取启用的假期类型列表（申请用下拉）")
    @GetMapping
    public Result<List<LeaveTypeResponse>> listEnabled() {
        return Result.ok(leaveTypeService.listEnabled());
    }

    @Operation(summary = "分页查询（ADMIN）")
    @GetMapping("/page")
    @RequiresRole("ADMIN")
    public Result<PageResponse<LeaveTypeResponse>> page(LeaveTypePageRequest req) {
        return Result.ok(leaveTypeService.page(req));
    }

    @Operation(summary = "新增假期类型")
    @PostMapping
    @RequiresRole("ADMIN")
    public Result<LeaveTypeResponse> create(@Valid @RequestBody LeaveTypeCreateRequest req) {
        return Result.ok(leaveTypeService.create(req));
    }

    @Operation(summary = "编辑假期类型")
    @PutMapping("/{id}")
    @RequiresRole("ADMIN")
    public Result<LeaveTypeResponse> update(
            @PathVariable Long id,
            @Valid @RequestBody LeaveTypeUpdateRequest req) {
        return Result.ok(leaveTypeService.update(id, req));
    }

    @Operation(summary = "启用/禁用")
    @PatchMapping("/{id}/status")
    @RequiresRole("ADMIN")
    public Result<Void> updateStatus(
            @PathVariable Long id,
            @Valid @RequestBody StatusRequest req) {
        leaveTypeService.updateStatus(id, req.getStatus());
        return Result.ok();
    }
}
```

**Hook 自动触发：**

```
[Hook] Stop → mvn compile
✅ BUILD SUCCESS，0 errors
```

**导出接口文档：**

```
[执行] curl http://localhost:8080/v3/api-docs > openapi.json
✅ openapi.json 已更新
```

**前端部分：**

```
[执行] cd frontend && pnpm gen:api
✅ src/types/api.generated.ts 已更新
// hooks/useLeaveType.ts
export function useLeaveTypeList() {
  return useQuery({
    queryKey: ['leaveType', 'list'],
    queryFn: () => api.get<LeaveTypeResponse[]>('/leave-types'),
  })
}

export function useLeaveTypePage(params: LeaveTypePageRequest) {
  return useQuery({
    queryKey: ['leaveType', 'page', params],
    queryFn: () => api.get<PageResponse<LeaveTypeResponse>>('/leave-types/page', { params }),
  })
}

export function useCreateLeaveType() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: LeaveTypeCreateRequest) =>
      api.post<LeaveTypeResponse>('/leave-types', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leaveType'] }),
  })
}
```

**Hook 再次自动触发：**

```
[Hook] Stop → pnpm typecheck
✅ 0 errors
```

完成后输入：

```
/done-check
```

Claude 输出验收报告：

```
假期类型模块验收报告

✅ 所有 SPEC 接口已实现（5个）
✅ ADMIN 权限控制正确
✅ 名称唯一性校验已实现
✅ 禁用类型不出现在申请下拉
✅ 前端列表页、表单、启用/禁用全部完成
✅ TypeScript 类型 0 错误，编译 0 错误

⚠️ 建议：有申请记录时不允许删除——
   当前未实现删除接口，SPEC 中也未要求（仅禁用），符合需求

❌ 无必须修复项

结论：模块验收通过 ✅
```

提交：

```bash
git add .
git commit -m "feat: 完成假期类型模块全栈实现"
```

------

## 第五步：上下文满了怎么办

开发到请假申请模块中途，上下文到 50%，输入：

```
上下文快满了，把当前进度更新到
.claude/progress/PROGRESS.md，我要 /clear
```

Claude 更新 `PROGRESS.md`：

```markdown
## 当前模块：请假申请（leave-apply）

### 后端 🔄 进行中
已完成:
- entity/LeaveApply.java
- mapper/LeaveApplyMapper.java
- dto/leaveapply/（CreateRequest、MyListRequest、Response、Converter）
- service/LeaveApplyService.java（接口定义完成）

进行中:
- service/impl/LeaveApplyServiceImpl.java
  - listMy() 已完成
  - create() 进行中（日期重叠校验逻辑未完成）

下一步:
- 完成 create() 的重叠校验：
  查询同一用户 status IN (PENDING, APPROVED) 且日期范围有交叉的记录
  SQL条件：NOT (endDate < :startDate OR startDate > :endDate)
- 实现 cancel() 方法
- 实现 Controller

### 前端 ⏳ 待开始
```

`/clear` 后新 session 输入：

```
读 CLAUDE.md 和 .claude/progress/PROGRESS.md，继续请假申请模块。
```

Claude 读完进度文件，直接从 `create()` 的重叠校验继续，没有任何上下文丢失。

------

## 整体节奏回顾

```
Day 1 上午   规划访谈 → 生成 SPEC.md + CLAUDE.md（1小时）
Day 1 下午   骨架期：Spring Boot + Next.js + Docker（2小时）

Day 2        假期类型模块（最简单，热身）（半天）

Day 3        请假申请模块（核心，日期校验/重叠检查）（1天）

Day 4        审批模块（含Excel导出）（1天）

Day 5        全量联调 + /done-check 所有模块 + 修复（半天）
```

前期花 1 小时把 SPEC 写清楚，后面 4 天开发期 Claude 每次启动都知道做什么、做到哪了，不需要重复解释背景。这是最大的收益。
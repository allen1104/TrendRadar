# 企业内部管理系统

## 技术栈
Next.js 15 + TypeScript · Spring Boot 3 + MyBatis-Plus + Maven
MySQL 8 · Spring Security + JWT · Docker Compose

## ⚡ 当前模块：骨架期
（每次开始新模块时更新这一行，例如：⚡ 当前模块：部门管理 dept）

## 模块列表与状态
- [ ] 骨架（auth + 基础设施）
- [ ] 模块A
- [ ] 模块B
- [ ] 模块C
- [ ] 模块D

## 快速命令
- 启动环境:   `docker-compose up -d`
- 导出API:    `curl http://localhost:8080/v3/api-docs > openapi.json`
- 更新类型:   `cd frontend && pnpm gen:api`
- 全栈验证:   `cd backend && mvn test && cd ../frontend && pnpm typecheck`

## 前后端约定
- API 前缀: `/api/v1/`
- 认证: JWT，Header `Authorization: Bearer <token>`
- 响应格式: `{ code, message, data }`
- 分页入参: `page(从0)/size`，出参: `{ records, total, current, size }`
- 时间: ISO 8601

## 参考文件
- 需求: @SPEC.md
- 开发进度: @.claude/progress/PROGRESS.md
- 前端规范: @frontend/CLAUDE.md
- 后端规范: @backend/CLAUDE.md
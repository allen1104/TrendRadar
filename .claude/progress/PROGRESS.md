# 开发进度

最后更新: 2026-08-01

## 阶段

- [x] 阶段 0 · 需求访谈与 SPEC 文档
- [x] 阶段 1 · 项目骨架（目录、配置、Docker Compose）
- [x] 阶段 2 · auth 认证与权限
- [x] 阶段 3 · ai-engine LLM 统一网关
- [x] 阶段 4 · source 采集源与插件
- [x] 阶段 5 · pipeline 清洗与去重聚合
- [x] 阶段 6 · hotspot 热点中心
- [x] 阶段 7 · admin 管理后台
- [x] 阶段 8 · 一期联调与验收（27/27 冒烟全过，详见 doc/ACCEPTANCE.md）
- [x] 阶段 9 · 二期首模块 collection（40 单测 + typecheck/build 通过）
- [ ] 阶段 10 · 后续二期模块（trend / assistant / creation / report）

## 当前工作

阶段 9 collection 模块完成：2 张表 + 11 个 API + 13 个 service 方法，hotspot 集成 `isCollected` 真实值（全栈 301 测试无回归），前端 MVP（⭐ 按钮 + /collections 页面 + 编辑弹窗 + 批量操作）通过 typecheck 与 build。

下一步：
1. 后续二期模块按 SPEC 顺序：trend → assistant → creation → report
2. 文档补完（hotspot+collection 跨模块联动写进 doc/ACCEPTANCE.md）
3. 端到端冒烟补 collection 段（需要实跑的 Docker 环境）

## 测试覆盖：301 passed

## 模块完成度

| 模块       | 一期 | model | 迁移 | repo | service | api | 前端 | 测试 | 状态     |
| ---------- | ---- | ----- | ---- | ---- | ------- | --- | ---- | ---- | -------- |
| auth       | ✅    | ✅     | ✅    | ✅    | ✅       | ✅   | ✅    | ✅    | ✅ 已完成 |
| ai-engine  | ✅    | ✅     | ✅    | ✅    | ✅       | ✅   | ✅    | —    | ✅ 已完成 |
| source     | ✅    | ✅     | ✅    | ✅    | ✅       | ✅   | ✅    | —    | ✅ 已完成 |
| pipeline   | ✅    | ✅     | ✅    | ✅    | ✅       | ✅   | —    | —    | ✅ 已完成 |
| hotspot    | ✅    | —     | —    | ✅    | ✅       | ✅   | ✅    | ✅    | ✅ 已完成 |
| admin      | ✅    | ✅     | ✅    | ✅    | ✅       | ✅   | ✅    | ✅    | ✅ 已完成 |
| collection | —    | ✅     | ✅    | ✅    | ✅       | ✅   | ✅    | ✅    | ✅ 已完成 |
| trend      | —    | ⬜     | ⬜    | ⬜    | ⬜       | ⬜   | ⬜    | ⬜    | ⏳ 未开始 |
| assistant  | —    | ⬜     | ⬜    | ⬜    | ⬜       | ⬜   | ⬜    | ⬜    | ⏳ 未开始 |
| creation   | —    | ⬜     | ⬜    | ⬜    | ⬜       | ⬜   | ⬜    | ⬜    | ⏳ 未开始 |
| report     | —    | ⬜     | ⬜    | ⬜    | ⬜       | ⬜   | ⬜    | ⬜    | ⏳ 未开始 |

## 决策记录

| 日期       | 决策                                       | 理由                                        |
| ---------- | ------------------------------------------ | ------------------------------------------- |
| 2026-07-29 | 一期用 PG + pgvector + Redis，不上 ES/Milvus | 部署成本；搜索层与向量层做可插拔抽象，后期可切 |
| 2026-07-29 | AI 分析作用在 event 而非 article           | 成本低 3-5 倍，语义更完整                    |
| 2026-07-29 | 热度分用算法算，价值/原创/趋势分用 AI       | 可解释、可复现，避免分数随机波动             |
| 2026-07-29 | API 用 RESTful 原生状态码，不做统一包裹     | OpenAPI 类型生成更干净，符合 FastAPI 惯例    |
| 2026-07-29 | 前端 Vite SPA 而非 Next.js                 | 无 SEO 硬需求，少一层 Node 服务             |
| 2026-07-29 | 一期只做 8 个采集源                        | 插件接口统一，扩展不改已有代码               |
| 2026-07-29 | 双 Token + 旋转 + 黑名单 + 复用检测         | access 短命 + refresh 旋转 + 泄露立即作废，全部用 Redis 原子操作 |
| 2026-07-29 | 客户端 fetcher 与 authStore 通过发布订阅解耦 | 避免循环依赖，便于单测                       |
| 2026-07-30 | Celery worker 用 `@celery_app.task` 而非 `@shared_task` | shared_task 默认 AMQP broker，必须绑到配置好的 celery_app |
| 2026-07-30 | pgvector 列在 SQLAlchemy ORM 中不建模，repository 用原生 SQL `CAST(:vec AS vector)` 写入 | ORM 不识别 vector 类型；命名参数 + `::vector` cast 在 asyncpg 下报语法错 |
| 2026-07-30 | `_run()` 协程桥接里 finally 调 `engine.dispose()` | Celery solo 跨多次 `asyncio.run()` 共享连接池，旧 loop 关闭后 asyncpg 连接失效 |
| 2026-07-30 | pipeline embed_task 直接用 `LocalEmbeddingProvider`，不走 LMGateway.embed() | gateway 内部 `_build_provider(model.provider)` 触发 sync lazy load，在 Celery 异步上下文里崩 |
| 2026-08-01 | hotspot 调 collection 用 inline import | hotspot service 与 collection service 无循环依赖（collection 依赖 pipeline，与 hotspot 同向）；inline import 避免顶层副作用 |
| 2026-08-01 | 登录用户跳过 hotspot cache | `is_collected` 是 per-user 状态，混合缓存会泄漏 A 给 B |
| 2026-08-01 | collection API 用 Query(alias) + 字符串自己 split 逗号分隔 | FastAPI `list[int]` Query 不解析逗号分隔，前端要重发 4 次；改手工 split 后 `/event-ids?eventIds=1,2,3,4` 一发搞定 |
| 2026-08-01 | `event_ids` API 返回 `set[int]` 而非 Pydantic DTO | service 内部统一 `set`（去重 + O(1) `in` 查询）；前端 API 层再自己包 `CollectedEventIdsResponse` |

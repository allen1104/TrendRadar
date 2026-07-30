# ai-engine Prompt 索引

> 本文件是 ai-engine 模块 Prompt 模板的**索引与设计文档**。
> 数据来源：`backend/app/scripts/seed_prompts.py`（权威）。本文档与 seed 脚本必须同步更新。

---

## 1. 任务索引

每个 task_key 都至少有一个 active 版本，且每个 task_key 在数据库层面只允许一个 active 版本（PG 部分唯一索引 `uk_prompt_task_active` 强制约束）。

| task_key | 版本 | 温度 | max_tokens | 输入变量 | 输出 schema | 当前状态 |
|---|---|---|---|---|---|---|
| `event_analysis` | v2 ★ | 0.3 | 2000 | eventTitle, eventSummary, articles, categoriesEnum | [EventAnalysisResult](schema.py) | active |
| `event_analysis` | v1 | 0.3 | 2000 | 同上 | 同上 | inactive（历史保留）|
| `embedding` | v1 | 0.0 | 16 | text | — | active（实际走本地 ONNX，prompt 是占位）|
| `assistant_qa` | v1 ★ | 0.3 | 1500 | eventTitle, eventSummary, articles, history, question | 流式 Markdown | active |
| `creation_wechat` | v1 ★ | 0.7 | 4000 | eventTitle, eventSummary, categories, key_points, innovations, audience, targetWords, style, audienceHint, extraRequirement | Markdown 长文 | active |
| `creation_blog` | v1 ★ | 0.5 | 5000 | 同上 | Markdown 长文（含代码块、参考链接占位）| active |
| `creation_weibo` | v1 ★ | 0.7 | 500 | eventTitle, eventSummary, style, audienceHint, extraRequirement | 1-3 条 ≤140 字微博 | active |
| `creation_xhs` | v1 ★ | 0.8 | 1500 | eventTitle, eventSummary, style, audienceHint | emoji 分段 + 5-8 标签 | active |
| `creation_zhihu` | v1 ★ | 0.5 | 3000 | eventTitle, eventSummary, categories, key_points, innovations, targetWords, audienceHint, style | Markdown 结论先行 | active |
| `creation_markdown` | v1 ★ | 0.5 | 3500 | 同 wechat 变量 | 纯 Markdown 笔记 | active |
| `report_daily` | v1 ★ | 0.3 | 3000 | events, sections | JSON（intro + outro + sections） | active |

★ = 当前生效；= 不可用

---

## 2. 设计原则（所有 Prompt 通用）

1. **角色明确** — system prompt 第一段就给出具体身份、专业领域、分析原则
2. **输出明确** — user prompt 列出每个字段的含义和评判标准（如 value_score 的 5 档参考分）
3. **限制明确** — 禁止编造、禁止超范围、明确引用规则（如 assistant_qa 的 [N] 引用必须对应现有材料）
4. **结构化** — 严格按 JSON schema 输出（event_analysis, report_daily）或 Markdown（creation_*）
5. **反例** — 高风险场景给出反例（event_analysis v2 的"见 OpenAI 新模型就一律 90+"）
6. **温度梯度** — 客观任务用 0.3-0.5（事件分析、问答），创意任务用 0.5-0.8（创作类）

---

## 3. 各 Prompt 设计要点

### 3.1 event_analysis v2（核心 — pipeline 模块会调）

**输入**：事件标题 + 摘要 + 来源文章列表 + 11 个分类枚举
**输出**：强约束 JSON，含 11 个字段
**关键约束**：
- `value_score` 5 档参考分（90+/70-89/50-69/30-49/<30）
- `categories` 必须从枚举选，禁止自造
- `summary_one_line` ≤ 30 字不带形容词堆砌
- `innovations` 无则空数组，**禁止编造**

### 3.2 embedding v1（占位）

**实际处理路径**：`LLMGateway.embed()` → 直接调 `Provider.embed()`，**不**走 LLM
**prompt 状态**：seed 里只放占位文本，等真正打通 ONNX 后删除整个任务

### 3.3 assistant_qa v1（二期 assistant 模块）

**关键约束（硬规则）**：
- 只用 `[N]` 编号引用现有材料
- 材料外内容必须明确说"现有材料中未提及"
- 越界编号（如 `[4]` 但只有 3 篇材料）禁止出现
- 系统已有 `citations` 字段负责解析

### 3.4 creation_wechat v1

**平台特点**：1500-3000 字，开头钩子 + 4 段式
**硬性约束**：
- 禁表格（公众号编辑器会丢格式）
- 禁"震惊体"、"或将颠覆"等夸张表达
- 温度 0.7（高创造性）

### 3.5 creation_blog v1

**平台特点**：2000-4000 字，工程师视角
**必备元素**：背景 → 核心原理 → 与已有方案对比 → 实测/代码 → 局限
**支持代码块**（```python 等）和表格

### 3.6 creation_weibo v1

**平台特点**：≤ 140 字 × 多条
**格式**：开头钩子 + 1-3 个 `#话题#` 标签 + 文末 `{{ url }}` 占位

### 3.7 creation_xhs v1

**平台特点**：300-600 字，emoji 分段
**格式**：标题 ≤ 20 字（前后各一 emoji）+ 正文 + 5-8 个标签
**约束**：emoji 用 1-2 个就够，不堆砌

### 3.8 creation_zhihu v1

**平台特点**：800-2000 字，结论先行
**风格**：理性、克制、不确定时承认
**禁**：禁"强烈推荐"、"一键"、"即将颠覆"

### 3.9 creation_markdown v1

**平台特点**：1000-3000 字，纯技术笔记
**风格**：第一人称，可有"踩坑记录"、"实测对比"
**无平台修饰**：不上公众号钩子、不上知乎"先说结论"、不上微博 140 字限制

### 3.10 report_daily v1

**任务**：从候选事件选 8-15 条，按板块编排成日报
**选稿原则**：
- 优先推荐指数 ≥ 70
- 避免同类堆叠（同公司/同技术只选 1 篇）
- 国内外都覆盖
**输出 JSON**：`{intro, outro, sections: [{name, items: [{eventId, headline, brief}]}]}`

---

## 4. CHANGELOG

### 2026-07-29 — 设计阶段首批

- **event_analysis** v2：完整角色 + 4 条原则 + 3 条反例 + 字段评判标准。覆盖 v1。
- **embedding** v1：占位（实际走本地 ONNX）。
- **assistant_qa** v1：硬规则用 `[N]` 引用、诚实性优先。
- **creation_wechat** v1：钩子+4 段式、禁表格、禁夸张表达。
- **creation_blog** v1：工程师视角，必含代码块与参考链接。
- **creation_weibo** v1：140 字限制 + 多条 + 话题标签。
- **creation_xhs** v1：emoji 分段 + 5-8 标签 + 口语化。
- **creation_zhihu** v1：结论先行 + 数据引用 + 承认不确定。
- **creation_markdown** v1：第一人称 + 无平台修饰。
- **report_daily** v1：选稿原则 + JSON 输出 schema。

---

## 5. 修改流程 SOP

### 5.1 修改现有 Prompt

```bash
# 前端 /admin/ai → Prompt Tab → 选 task_key → 点「编辑」
# 顶部「+ 新建版本」按钮 → 弹窗 → 系统自动 version+1
# 等提交后点「激活此版本」
```

> 注意：一旦激活某个版本，**该版本不能再编辑**（`PROMPT_READONLY`）。要改只能再「+ 新建版本」。
> 永远不要直接改 active 版本。

### 5.2 新增一个 task_key

如果未来要新增新类型（例如 `creation_bilibili`）：

**Step 1**：后端枚举加值
```python
# backend/app/modules/ai/enums.py
class TaskKey(StrEnum):
    ...
    CREATION_BILIBILI = "creation_bilibili"  # 新增
```

**Step 2**：如果有强约束输出，写 Pydantic schema
```python
# backend/app/modules/ai/schema.py
class BilibiliVideoResult(CamelModel):
    title: str = Field(max_length=80)
    description: str = Field(max_length=250)
    tags: list[str] = Field(max_length=10, max_length=20)
```

**Step 3**：改 PromptCreateRequest.task_key 的校验（自动，因为它是 TaskKey enum）

**Step 4**：seed_prompts.py 加新条目
```python
PROMPTS.append({
    "task_key": TaskKey.CREATION_BILIBILI.value,
    "version": 1,
    "system_prompt": "...",
    "user_prompt": "...",
    ...
})
```

**Step 5**：跑 seed
```bash
.venv/Scripts/python -m app.scripts.seed_prompts
```

**Step 6**：`LLMGateway.call(task_key="creation_bilibili", ...)` 就能用了

### 5.3 回滚到旧版本

```bash
# 找到想激活的版本 id
curl http://localhost:8000/api/v1/admin/ai/prompts?task_key=event_analysis
#   → 拿 v1 的 id，假设是 5

# 激活它
curl -X POST http://localhost:8000/api/v1/admin/ai/prompts/5/activate \
     -H "Authorization: Bearer ..."
```

PG 部分唯一索引会自动把当前 active 版本切到 inactive。

### 5.4 调试一个新 Prompt

```bash
# 用 dry-run 真实跑一次 LLM（不落库）
curl -X POST http://localhost:8000/api/v1/admin/ai/prompts/{id}/dry-run \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer ..." \
     -d '{
       "variables": {
         "eventTitle": "测试",
         "articles": [...],
         ...
       }
     }'
```

返回 `renderedSystemPrompt`、`renderedUserPrompt`、`output`（解析后的 JSON）、token 数、费用。

> 注意：dry-run 会真发一次 LLM 调用并记 `ai_call_log`，消耗 token 和成本。

---

## 6. 已知 LIMIT（开放问题）

1. **TaskKey 是代码 enum**，不是数据库表 → 加新类型需要改代码 + 重启
2. **embedding prompt 是死代码**，实际不调 LLM → 后续应该删掉还是改成都走 LLM 还没决定
3. **`report_daily` 的 `sections` 是输入**，改输出板块需要改 `system_config.report_daily_sections` 或 hardcode（见 SPEC）
4. **没有自动化测试** Prompt 质量 → 改 prompt 后只能人工 dry-run 验证

---

## 7. 相关文件

| 文件 | 说明 |
|---|---|
| `backend/app/scripts/seed_prompts.py` | **权威**：所有 Prompt 模板的源 |
| `backend/app/scripts/update_v2_prompt.py` | 一次性脚本：把 event_analysis v2 覆盖成设计版 |
| `backend/app/modules/ai/schema.py` | 请求/响应 DTO + `EventAnalysisResult` 强约束 schema |
| `backend/app/modules/ai/enums.py` | `TaskKey` 枚举 |
| `backend/app/modules/ai/gateway/gateway.py` | `LLMGateway.call()` 入口 |
| `frontend/src/features/admin/pages/AiConfigPage.tsx` | UI 入口：CRUD + dry-run |
| `doc/SPEC-ai-engine.md` | 模块需求规格 |
| `backend/app/modules/ai/PROMPTS.md` | 本文件 |

# AI 引擎模块（ai-engine）

所属项目: @SPEC.md
模块状态: ⏳ 未开始
一期范围: ✅ 是
最后更新: 2026-07-29

---

## 功能目标

作为系统唯一的 **LLM 统一网关**，向所有业务模块提供：

1. **多 Provider 可配置**：OpenAI / Claude / Gemini / DeepSeek / Qwen / Kimi 及任意 OpenAI 兼容端点
2. **模型切换与降级链**：主模型失败自动降级到备用模型
3. **Prompt 管理**：模板存库、带版本、可试运行、禁止硬编码
4. **结构化输出**：PydanticAI 强制 JSON schema，解析失败自动重试
5. **Embedding 服务**：为 `pipeline` 提供向量化能力
6. **Token 与成本统计**：每次调用留痕，按模型/任务/日期多维统计
7. **事件分析**：一期核心业务能力——对 `event` 产出完整结构化分析

**铁律**：业务模块不得 import 任何模型 SDK，一律通过 `LLMGateway` 调用。

---

## 核心抽象

```python
# backend/app/modules/ai/gateway/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel

class LLMRequest(BaseModel):
    messages: list[dict]              # [{"role":"system","content":"..."}]
    model: str
    temperature: float = 0.3
    max_tokens: int | None = None
    response_schema: type[BaseModel] | None = None   # 传入则强制结构化输出
    timeout: int = 120

class LLMResponse(BaseModel):
    content: str
    parsed: BaseModel | None          # response_schema 存在时的解析结果
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    finish_reason: str

class LLMProvider(ABC):
    provider_key: str                 # "openai" | "anthropic" | "gemini" | "openai_compatible"

    @abstractmethod
    async def initialize(self, config: dict) -> None: ...

    @abstractmethod
    async def chat(self, req: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...

    @abstractmethod
    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float: ...
```

**一期实现的 Provider**：
| provider_key        | 说明                                                                 |
| ------------------- | -------------------------------------------------------------------- |
| `openai_compatible` | 通用实现，覆盖 OpenAI / DeepSeek / Qwen / Kimi / 本地 vLLM / Ollama  |
| `anthropic`         | Claude Messages API（原生，支持 prompt caching）                     |
| `gemini`            | Google Generative AI                                                 |
| `local_embedding`   | 本地 ONNX `bge-m3`，只实现 `embed()`，零调用成本                     |

`LLMGateway` 是对外唯一入口，负责：模型解析 → Provider 路由 → 重试 → 降级 → 记账 → 返回。

---

## 数据库设计

### `ai_provider` 表

| 字段         | 类型         | 必填 | 说明                                                |
| ------------ | ------------ | ---- | --------------------------------------------------- |
| id           | BIGSERIAL    | 是   | 主键                                                |
| provider_key | VARCHAR(64)  | 是   | 对应实现类，如 `openai_compatible`                  |
| name         | VARCHAR(100) | 是   | 显示名，如 "DeepSeek 官方"，全局唯一                |
| base_url     | VARCHAR(500) | 否   | API 地址，如 `https://api.deepseek.com/v1`          |
| api_key      | VARCHAR(500) | 否   | **AES-GCM 加密存储**                                |
| extra_config | JSONB        | 是   | 额外配置（proxy、organization、headers），默认 `{}` |
| enabled      | BOOLEAN      | 是   | 是否启用，默认 true                                 |
| created_at   | TIMESTAMPTZ  | -    | 创建时间                                            |
| updated_at   | TIMESTAMPTZ  | -    | 更新时间                                            |
| is_deleted   | BOOLEAN      | -    | 逻辑删除，默认 false                                |

索引：`uk_ai_provider_name(name) WHERE is_deleted=false`

### `ai_model` 表

| 字段                 | 类型          | 必填 | 说明                                                       |
| -------------------- | ------------- | ---- | ---------------------------------------------------------- |
| id                   | BIGSERIAL     | 是   | 主键                                                       |
| provider_id          | BIGINT        | 是   | 所属 Provider                                              |
| model_name           | VARCHAR(120)  | 是   | 传给 API 的真实模型名，如 `deepseek-chat`                  |
| alias                | VARCHAR(100)  | 是   | 系统内引用别名，如 `default-chat`，全局唯一                |
| model_type           | VARCHAR(32)   | 是   | `CHAT` / `EMBEDDING`                                       |
| context_window       | INTEGER       | 是   | 上下文长度，默认 128000                                    |
| max_output_tokens    | INTEGER       | 是   | 最大输出，默认 4096                                        |
| supports_json_schema | BOOLEAN       | 是   | 是否原生支持结构化输出，默认 false                         |
| price_input_per_1m   | NUMERIC(10,4) | 是   | 输入价格 USD/1M tokens，默认 0                             |
| price_output_per_1m  | NUMERIC(10,4) | 是   | 输出价格 USD/1M tokens，默认 0                             |
| embedding_dim        | SMALLINT      | 否   | EMBEDDING 类型必填，如 1024                                |
| enabled              | BOOLEAN       | 是   | 是否启用，默认 true                                        |
| created_at           | TIMESTAMPTZ   | -    | 创建时间                                                   |
| updated_at           | TIMESTAMPTZ   | -    | 更新时间                                                   |
| is_deleted           | BOOLEAN       | -    | 逻辑删除，默认 false                                       |

索引：`uk_ai_model_alias(alias) WHERE is_deleted=false`、`idx_ai_model_provider(provider_id)`

### `prompt_template` 表

| 字段            | 类型         | 必填 | 说明                                                       |
| --------------- | ------------ | ---- | ---------------------------------------------------------- |
| id              | BIGSERIAL    | 是   | 主键                                                       |
| task_key        | VARCHAR(64)  | 是   | 任务标识，如 `event_analysis`（见下方任务清单）            |
| version         | INTEGER      | 是   | 版本号，从 1 递增                                          |
| system_prompt   | TEXT         | 是   | System 提示词                                              |
| user_prompt     | TEXT         | 是   | User 提示词模板，`{{变量}}` 占位（Jinja2 语法）            |
| variables       | JSONB        | 是   | 变量名数组，用于校验与前端提示，默认 `[]`                  |
| model_alias     | VARCHAR(100) | 否   | 指定模型别名；为空则用该任务类型的默认模型                 |
| temperature     | NUMERIC(3,2) | 是   | 默认 0.30                                                  |
| max_tokens      | INTEGER      | 否   | 输出上限                                                   |
| is_active       | BOOLEAN      | 是   | 是否为该 `task_key` 的生效版本，默认 false                 |
| note            | VARCHAR(500) | 否   | 版本说明                                                   |
| created_by      | BIGINT       | 否   | 创建人                                                     |
| created_at      | TIMESTAMPTZ  | -    | 创建时间                                                   |
| updated_at      | TIMESTAMPTZ  | -    | 更新时间                                                   |
| is_deleted      | BOOLEAN      | -    | 逻辑删除，默认 false                                       |

索引：`uk_prompt_task_version(task_key, version)` 唯一
约束：同一 `task_key` 下 **有且仅有一条** `is_active=true`（部分唯一索引保证）

### `ai_call_log` 表

| 字段              | 类型          | 必填 | 说明                                                |
| ----------------- | ------------- | ---- | --------------------------------------------------- |
| id                | BIGSERIAL     | 是   | 主键                                                |
| trace_id          | VARCHAR(64)   | 是   | 链路追踪 ID                                         |
| task_key          | VARCHAR(64)   | 是   | 任务标识                                            |
| model_id          | BIGINT        | 否   | 实际使用的模型 ID                                   |
| model_alias       | VARCHAR(100)  | 是   | 实际使用的模型别名（冗余，模型删了也能统计）        |
| prompt_version    | INTEGER       | 否   | 使用的 prompt 版本                                  |
| target_type       | VARCHAR(32)   | 否   | `EVENT`/`ARTICLE`/`THREAD`/`REPORT`                 |
| target_id         | BIGINT        | 否   | 目标对象 ID                                         |
| user_id           | BIGINT        | 否   | 触发用户（系统任务为空）                            |
| prompt_tokens     | INTEGER       | 是   | 输入 token，默认 0                                  |
| completion_tokens | INTEGER       | 是   | 输出 token，默认 0                                  |
| cost_usd          | NUMERIC(10,6) | 是   | 本次费用，默认 0                                    |
| latency_ms        | INTEGER       | 否   | 耗时                                                |
| status            | VARCHAR(32)   | 是   | `SUCCESS`/`FAILED`/`FALLBACK`（降级后成功）         |
| retry_count       | SMALLINT      | 是   | 重试次数，默认 0                                    |
| error_message     | VARCHAR(1000) | 否   | 失败原因                                            |
| created_at        | TIMESTAMPTZ   | -    | 创建时间                                            |
| updated_at        | TIMESTAMPTZ   | -    | 更新时间                                            |
| is_deleted        | BOOLEAN       | -    | 逻辑删除，默认 false                                |

索引：`idx_call_log_time(created_at DESC)`、`idx_call_log_task(task_key, created_at DESC)`、`idx_call_log_model(model_alias, created_at DESC)`、`idx_call_log_target(target_type, target_id)`

> 保留 90 天；按日聚合结果写入物化视图 `mv_ai_cost_daily`，每小时刷新。

### `event_analysis` 表

| 字段              | 类型         | 必填 | 说明                                                    |
| ----------------- | ------------ | ---- | ------------------------------------------------------- |
| id                | BIGSERIAL    | 是   | 主键                                                    |
| event_id          | BIGINT       | 是   | 事件 ID，唯一（一个事件一条最新分析）                   |
| summary_one_line  | VARCHAR(300) | 是   | 一句话总结                                              |
| summary           | TEXT         | 是   | 完整总结（200-400 字）                                  |
| key_points        | JSONB        | 是   | 核心观点数组，3-5 条，默认 `[]`                          |
| innovations       | JSONB        | 是   | 创新点数组，0-5 条，默认 `[]`                            |
| audience          | JSONB        | 是   | 适合人群数组，默认 `[]`                                  |
| categories        | JSONB        | 是   | 分类数组（11 选 N），默认 `[]`                           |
| tags              | JSONB        | 是   | 提取的实体标签 `[{"name":"OpenAI","type":"COMPANY"}]`   |
| value_score       | SMALLINT     | 是   | 价值分 0-100                                            |
| originality_score | SMALLINT     | 是   | 原创价值分 0-100                                        |
| trend_score       | SMALLINT     | 是   | 趋势分 0-100                                            |
| worth_article     | BOOLEAN      | 是   | 是否值得写公众号                                        |
| worth_article_why | VARCHAR(500) | 否   | 理由                                                    |
| worth_research    | BOOLEAN      | 是   | 是否值得深入研究                                        |
| worth_research_why| VARCHAR(500) | 否   | 理由                                                    |
| model_alias       | VARCHAR(100) | 是   | 产出该分析的模型                                        |
| prompt_version    | INTEGER      | 是   | 使用的 prompt 版本                                      |
| analyzed_at       | TIMESTAMPTZ  | 是   | 分析时间                                                |
| created_at        | TIMESTAMPTZ  | -    | 创建时间                                                |
| updated_at        | TIMESTAMPTZ  | -    | 更新时间                                                |
| is_deleted        | BOOLEAN      | -    | 逻辑删除，默认 false                                    |

索引：`uk_event_analysis_event(event_id) WHERE is_deleted=false`

---

## 任务清单（`task_key`）

| task_key           | 所属模块  | 一期 | 说明                          |
| ------------------ | --------- | ---- | ----------------------------- |
| `event_analysis`   | pipeline  | ✅    | 事件完整分析与评分（核心）    |
| `embedding`        | pipeline  | ✅    | 向量化（走 embedding 模型）   |
| `assistant_qa`     | assistant | —    | 热点问答                      |
| `creation_wechat`  | creation  | —    | 公众号文章生成                |
| `creation_blog`    | creation  | —    | 技术博客生成                  |
| `creation_weibo`   | creation  | —    | 微博生成                      |
| `creation_xhs`     | creation  | —    | 小红书生成                    |
| `creation_zhihu`   | creation  | —    | 知乎回答生成                  |
| `report_daily`     | report    | —    | 日报编排                      |

---

## 事件分析的结构化输出 Schema

```python
class EventAnalysisResult(BaseModel):
    summary_one_line: str = Field(max_length=300, description="一句话说清这件事")
    summary: str = Field(description="200-400字完整总结")
    key_points: list[str] = Field(min_length=3, max_length=5)
    innovations: list[str] = Field(max_length=5, default_factory=list)
    audience: list[str] = Field(description="适合哪些人阅读")
    categories: list[Category] = Field(min_length=1, max_length=4)
    tags: list[TagItem] = Field(max_length=8)
    value_score: int = Field(ge=0, le=100, description="值得关注程度")
    originality_score: int = Field(ge=0, le=100, description="原创/独创价值")
    trend_score: int = Field(ge=0, le=100, description="趋势代表性")
    worth_article: bool
    worth_article_why: str = Field(max_length=500)
    worth_research: bool
    worth_research_why: str = Field(max_length=500)
```

分析结果写入 `event_analysis`，同时回写 `event` 的
`summary_one_line` / `categories` / `value_score` / `originality_score` / `trend_score`
（跳过 `manual_locked_fields` 中的字段）。

---

## 后端接口

### GET /api/v1/admin/ai/providers
**说明**: Provider 列表，仅 `ADMIN`。`apiKey` 脱敏返回

**Response 200**:
```json
{
  "items": [
    { "id": 1, "providerKey": "openai_compatible", "name": "DeepSeek 官方",
      "baseUrl": "https://api.deepseek.com/v1", "apiKey": "sk-****a1b2",
      "enabled": true, "modelCount": 2 }
  ],
  "total": 1, "page": 1, "size": 20, "pages": 1
}
```

### POST /api/v1/admin/ai/providers
**说明**: 新建 Provider，仅 `ADMIN`

**Request Body**:
```json
{
  "providerKey": "openai_compatible",
  "name": "DeepSeek 官方",
  "baseUrl": "https://api.deepseek.com/v1",
  "apiKey": "sk-xxxxxxxx",
  "extraConfig": {},
  "enabled": true
}
```
**Response 201**: provider 对象（apiKey 脱敏）
**错误情况**: 名称重复 → `409` `PROVIDER_NAME_EXISTS`；`providerKey` 未注册 → `400` `PROVIDER_NOT_FOUND`

### PATCH /api/v1/admin/ai/providers/{id} · DELETE /api/v1/admin/ai/providers/{id}
标准更新与软删除。删除前校验无关联的启用中模型，否则 `409` `PROVIDER_IN_USE`

### POST /api/v1/admin/ai/providers/{id}/test
**说明**: 连通性测试。发一个极短请求验证 key 与网络

**Response 200**:
```json
{ "success": true, "latencyMs": 620, "message": "连接正常", "availableModels": ["deepseek-chat", "deepseek-reasoner"] }
```
> `availableModels` 在 Provider 支持 `/models` 接口时返回，用于前端新建模型时下拉选择

---

### GET/POST/PATCH/DELETE /api/v1/admin/ai/models
**说明**: 模型 CRUD，仅 `ADMIN`

**POST Request Body**:
```json
{
  "providerId": 1,
  "modelName": "deepseek-chat",
  "alias": "default-chat",
  "modelType": "CHAT",
  "contextWindow": 128000,
  "maxOutputTokens": 8192,
  "supportsJsonSchema": true,
  "priceInputPer1m": 0.27,
  "priceOutputPer1m": 1.10,
  "enabled": true
}
```
**错误情况**: 别名重复 → `409` `MODEL_ALIAS_EXISTS`；`EMBEDDING` 类型缺 `embeddingDim` → `400` `EMBEDDING_DIM_REQUIRED`

---

### GET /api/v1/admin/ai/prompts
**说明**: Prompt 模板列表（按 `task_key` 分组），仅 `ADMIN`

**Query**: `taskKey` `onlyActive`

**Response 200**:
```json
{
  "items": [
    { "id": 3, "taskKey": "event_analysis", "version": 3, "modelAlias": "default-chat",
      "temperature": 0.3, "isActive": true, "note": "增加创新点字段约束",
      "variables": ["eventTitle", "articles"], "createdAt": "2026-07-20T10:00:00Z" }
  ],
  "total": 3, "page": 1, "size": 20, "pages": 1
}
```

### GET /api/v1/admin/ai/prompts/{id}
返回完整模板内容（`systemPrompt` / `userPrompt`）

### POST /api/v1/admin/ai/prompts
**说明**: 新建版本（version 自动 = 该 `task_key` 当前最大版本 + 1），仅 `ADMIN`。新建后默认 `isActive=false`

### POST /api/v1/admin/ai/prompts/{id}/activate
**说明**: 激活该版本，自动把同 `task_key` 其他版本置为 `isActive=false`

**Response 200**: prompt 对象

### POST /api/v1/admin/ai/prompts/{id}/dry-run
**说明**: 用指定版本对某个真实对象试运行，**不写库**，返回渲染后的 prompt 与模型输出

**Request Body**: `{ "targetType": "EVENT", "targetId": 88 }`

**Response 200**:
```json
{
  "renderedSystemPrompt": "你是一名科技趋势分析师...",
  "renderedUserPrompt": "事件标题：OpenAI 发布 GPT-5\n来源文章：\n1. ...",
  "output": { "summaryOneLine": "...", "valueScore": 88, "...": "..." },
  "modelAlias": "default-chat",
  "promptTokens": 3120,
  "completionTokens": 640,
  "costUsd": 0.001548,
  "latencyMs": 4210,
  "parseSuccess": true
}
```
> 前端在此基础上做「当前生效版本 vs 新版本」并排 diff 对比

---

### GET /api/v1/admin/ai/cost
**说明**: 成本统计，仅 `ADMIN`

**Query**: `startDate` `endDate` `groupBy`（`DAY`/`MODEL`/`TASK`）

**Response 200**:
```json
{
  "totalCostUsd": 12.4831,
  "totalCalls": 8420,
  "totalPromptTokens": 24810332,
  "totalCompletionTokens": 3120884,
  "successRate": 0.9932,
  "series": [
    { "key": "2026-07-28", "costUsd": 1.2043, "calls": 812,
      "promptTokens": 2410332, "completionTokens": 302118 }
  ],
  "byModel": [ { "modelAlias": "default-chat", "costUsd": 11.90, "calls": 8100 } ],
  "byTask":  [ { "taskKey": "event_analysis", "costUsd": 11.20, "calls": 1203 } ]
}
```

### GET /api/v1/admin/ai/logs
**说明**: 调用日志明细，仅 `ADMIN`

**Query**: `page` `size` `taskKey` `modelAlias` `status` `startDate` `endDate` `targetId`

---

### POST /api/v1/admin/ai/analyze
**说明**: 手动触发事件分析（异步），`EDITOR` 及以上

**Request Body**: `{ "eventIds": [88, 91], "force": true }`
- `force=true` 时即使 `status=ANALYZED` 也重跑

**Response 202**: `{ "taskId": "...", "queuedCount": 2 }`

---

## 前端页面

### AI 配置（`/admin/ai`，ADMIN）

**Tab 1 · Provider 管理**
- 卡片网格：每个 Provider 一张卡（图标、名称、baseUrl、启用 Switch、模型数）
- 卡片操作：编辑、连通性测试（点击后卡片显示 spinner → 绿勾/红叉 + 延迟毫秒）、删除
- 「新建 Provider」→ 弹窗：`providerKey` 下拉、名称、baseUrl、apiKey（password 输入，编辑时占位 `••••` 表示不修改）

**Tab 2 · 模型管理**
- 表格：别名（Badge，默认模型高亮）、真实模型名、所属 Provider、类型、上下文、输入/输出单价、启用 Switch
- 「设为默认对话模型 / 默认 Embedding 模型」快捷按钮（写 `system_config`）
- **降级链配置区**：可拖拽排序的模型别名列表，第一个为主模型，依次降级；保存到 `system_config.ai_fallback_chain`

**Tab 3 · Prompt 管理**
- 左侧：`task_key` 列表（显示中文名 + 当前生效版本号）
- 右侧：
  - 版本时间线（版本号、创建时间、创建人、note、生效标记）
  - 编辑器：Monaco Editor 双栏（System / User），支持 `{{变量}}` 语法高亮与变量校验（用了未声明的变量报错）
  - 底部：模型别名下拉、temperature 滑块、maxTokens
  - 「试运行」按钮 → 弹出事件选择器 → 展示渲染后的 prompt + 模型输出 JSON（带语法高亮）
  - 「与生效版本对比」→ 并排 diff（左：当前生效输出，右：新版本输出）
  - 「保存为新版本」/「激活此版本」（激活需二次确认）

**Tab 4 · 成本统计**
- 顶部日期范围选择器（快捷：今天 / 近 7 天 / 近 30 天 / 本月）
- 4 个指标卡：总费用 USD / 总调用次数 / 总 Token / 成功率
- ECharts 折线图：每日费用趋势（双 Y 轴：费用 + 调用次数）
- ECharts 饼图 ×2：按模型分布 / 按任务分布
- 明细表格：可按任务/模型/状态过滤，失败行标红可展开看 `errorMessage`

---

## 业务规则

### 调用流程
```
LLMGateway.call(task_key, variables, target=None)
  ① 查 prompt_template WHERE task_key AND is_active
     └─ 不存在 → 抛 PromptNotConfiguredError (500 PROMPT_NOT_CONFIGURED)
  ② Jinja2 渲染 user_prompt，校验所有 variables 已提供
  ③ 解析模型：prompt.model_alias → 无则 system_config 默认模型
  ④ 构造降级链：[主模型] + system_config.ai_fallback_chain
  ⑤ 对链上每个模型依次尝试：
       Provider.chat(req)
       ├─ 成功 → 若有 response_schema，解析 JSON
       │    ├─ 解析失败 → 追加"输出必须是合法 JSON"重试，最多 3 次
       │    └─ 3 次仍失败 → 视为该模型失败，降级
       ├─ 超时/5xx/429 → 指数退避重试 3 次（2s/6s/18s）
       └─ 仍失败 → 降级到链上下一个模型（status 标 FALLBACK）
  ⑥ 无论成败，写 ai_call_log（含 cost_usd）
  ⑦ 全链失败 → 抛 LLMUnavailableError，调用方按业务降级
```

### 成本控制
- `cost_usd = prompt_tokens/1e6 × price_input + completion_tokens/1e6 × price_output`
- 单次调用超 `system_config.ai_single_call_cost_limit_usd`（默认 0.5）→ 拒绝执行并告警
- 单日总费用超 `ai_daily_cost_limit_usd`（默认 20）→ 暂停所有非用户触发的系统任务，写 `audit_log` 并在后台顶部横幅告警
- 用户触发的任务（问 AI / 创作）不受日限影响，但按用户限流

### Prompt 管理
- 同一 `task_key` 有且仅有一个 `is_active=true`，用部分唯一索引 `UNIQUE(task_key) WHERE is_active AND NOT is_deleted` 保证
- 已激活过的版本**不可编辑**，只能基于它创建新版本（保证历史可追溯）
- 系统初始化时通过 seed 脚本插入所有 `task_key` 的 v1 模板

### Embedding
- 默认使用 `local_embedding` Provider（本地 ONNX `bge-m3`，1024 维），成本记 0
- 批量接口，单批 ≤ 32 条，超长文本截断到 512 token
- 切换 embedding 模型属于**破坏性变更**：维度不同则需全量重算，后台切换时必须二次确认并提示影响范围

### 并发与限流
- 每个 Provider 独立并发信号量，上限存 `provider.extra_config.max_concurrency`（默认 5）
- `429` 响应遵守 `Retry-After` 头
- 用户触发的 AI 调用按用户限流：20 次/小时（`system_config.ai_user_rate_limit`）

### 安全
- `api_key` AES-GCM 加密，密钥来自环境变量 `SECRET_KEY`
- 出参一律脱敏，**任何接口都不返回 key 原文**
- `ai_call_log` 不记录 prompt/response 全文（避免敏感信息与存储膨胀），只记 token 与元信息；`dry-run` 的内容只在响应中返回不落库

---

## 完成标准

- [ ] `LLMProvider` 抽象 + 4 个 Provider 实现（openai_compatible / anthropic / gemini / local_embedding）
- [ ] `LLMGateway` 完成：模型解析、重试、降级链、结构化输出重试、记账
- [ ] `ai_provider` / `ai_model` / `prompt_template` / `ai_call_log` / `event_analysis` 表与迁移完成
- [ ] `api_key` 加密存储 + 出参脱敏
- [ ] `EventAnalysisResult` schema 强约束生效，非法输出自动重试
- [ ] `event_analysis` 结果正确回写 `event`，且跳过 `manual_locked_fields`
- [ ] Prompt 从数据库读取，代码中无任何硬编码 prompt（CI 加 grep 检查）
- [ ] 同 `task_key` 单一生效版本约束在数据库层生效
- [ ] `dry-run` 不写库，能返回渲染结果与模型输出
- [ ] 降级链生效：主模型不可用时自动切换，日志标 `FALLBACK`
- [ ] 成本统计准确，单次/单日限额触发拦截与告警
- [ ] 本地 embedding 可用，批量向量化 1000 条 < 30 秒
- [ ] 后台 AI 配置四个 Tab 全部完成
- [ ] 单元测试：降级链、重试、成本计算、Prompt 渲染与变量校验、schema 解析失败重试；覆盖率 ≥ 80%

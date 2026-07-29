# 采集源与插件模块（source）

所属项目: @SPEC.md
模块状态: ⏳ 未开始
一期范围: ✅ 是
最后更新: 2026-07-29

---

## 功能目标

以**插件化**方式从全球与国内科技信息源抓取原始内容，统一规范化后写入 `article` 表。

本模块只负责"把东西抓下来并规范成统一结构"，**不做任何语义处理**（清洗正文、去重、AI 分析均属 `pipeline` / `ai-engine`）。

核心产物：统一的 `SourcePlugin` 抽象 + 插件注册表 + 采集调度 + 运行日志。

---

## 插件接口规范

所有采集器必须继承 `SourcePlugin` 抽象基类，实现四个生命周期方法：

```python
# backend/app/modules/source/plugins/base.py
from abc import ABC, abstractmethod
from datetime import datetime
from pydantic import BaseModel, HttpUrl

class RawItem(BaseModel):
    """采集器产出的统一条目结构。所有插件必须返回它。"""
    external_id: str            # 源站唯一 ID（如 HN 的 story id、GitHub repo full_name）
    url: HttpUrl                # 原文链接（去除 utm_* 等追踪参数）
    title: str                  # 标题（原语言）
    raw_content: str | None     # 原始正文/HTML 片段，拿不到则 None，由 pipeline 二次抓取
    author: str | None
    published_at: datetime | None   # 必须是带时区的 UTC datetime
    lang: str                   # ISO 639-1，如 "en" / "zh"
    metrics: dict[str, int]     # 互动指标 {"points": 320, "comments": 88, "stars": 1200}
    extra: dict                 # 源特有字段（arXiv 分类、GitHub 语言…）

class SourcePlugin(ABC):
    plugin_key: str             # 全局唯一，如 "hacker_news"
    display_name: str
    region: str                 # "GLOBAL" | "CN"
    default_cron: str           # 默认调度 cron
    default_weight: int         # 默认源权重 1-10，用于热度计算

    @abstractmethod
    async def initialize(self, config: dict) -> None:
        """注入配置（API Key、条数上限、分类过滤等），建立 HTTP client。
        必须校验 config 合法性，非法直接抛 PluginConfigError。"""

    @abstractmethod
    async def fetch(self) -> list[dict]:
        """执行网络请求，返回原始响应片段列表。只负责 IO，不做解析。"""

    @abstractmethod
    def parse(self, raw: list[dict]) -> list[dict]:
        """把原始响应解析成中间字典。纯函数，可离线用固定 fixture 单测。"""

    @abstractmethod
    def normalize(self, parsed: list[dict]) -> list[RawItem]:
        """映射到 RawItem。纯函数。时间统一转 UTC，URL 统一清洗追踪参数。"""

    async def run(self) -> list[RawItem]:
        """模板方法，框架调用入口，禁止子类覆盖。"""
        raw = await self.fetch()
        return self.normalize(self.parse(raw))

    async def close(self) -> None:
        """释放 HTTP client 等资源。默认空实现。"""
```

**插件注册**：用装饰器自动注册到全局注册表，**禁止 if/elif 分发**。

```python
@register_plugin
class HackerNewsPlugin(SourcePlugin):
    plugin_key = "hacker_news"
    ...
```

新增一个源 = 新增一个文件 + 打装饰器 + 后台配一条 `source` 记录，**不改任何已有代码**。

---

## 一期采集器清单（8 个）

| plugin_key       | 名称           | 区域   | 抓取方式                                    | 默认 cron      | 权重 |
| ---------------- | -------------- | ------ | ------------------------------------------- | -------------- | ---- |
| `hacker_news`    | Hacker News    | GLOBAL | 官方 Firebase API（topstories + item）      | `0 * * * *`    | 9    |
| `github_trending`| GitHub Trending| GLOBAL | HTML 解析 `github.com/trending`（daily）    | `30 * * * *`   | 9    |
| `arxiv`          | arXiv          | GLOBAL | 官方 Atom API，分类 `cs.AI/cs.CL/cs.LG`     | `0 */2 * * *`  | 8    |
| `huggingface`    | HuggingFace    | GLOBAL | `huggingface.co/api/models?sort=trending`   | `15 * * * *`   | 8    |
| `product_hunt`   | Product Hunt   | GLOBAL | GraphQL API（需 token）                     | `45 * * * *`   | 6    |
| `jiqizhixin`     | 机器之心       | CN     | RSS / 列表页 HTML 解析                      | `10 * * * *`   | 8    |
| `qbitai`         | 量子位         | CN     | RSS / 列表页 HTML 解析                      | `20 * * * *`   | 7    |
| `infoq_cn`       | InfoQ 中国     | CN     | 列表页 API                                  | `40 * * * *`   | 7    |

**二期扩展**（接口已就绪，仅需新增插件文件）：
GitHub Release、GitHub Explore、Reddit、OpenAI Blog、Anthropic Blog、Google AI Blog、
Google Research、Microsoft Research、Meta AI、NVIDIA Blog、Apple Developer、
新智元、智东西、极客公园、CSDN 精选、开源中国、腾讯云开发者、阿里云开发者。

---

## 数据库设计

### `source` 表

| 字段              | 类型         | 必填 | 说明                                                    |
| ----------------- | ------------ | ---- | ------------------------------------------------------- |
| id                | BIGSERIAL    | 是   | 主键                                                    |
| plugin_key        | VARCHAR(64)  | 是   | 对应插件的 `plugin_key`                                 |
| name              | VARCHAR(100) | 是   | 显示名称，全局唯一                                      |
| region            | VARCHAR(32)  | 是   | `GLOBAL` / `CN`                                         |
| category          | VARCHAR(32)  | 是   | `NEWS`/`CODE`/`PAPER`/`PRODUCT`/`BLOG`/`MODEL`          |
| home_url          | VARCHAR(500) | 否   | 站点主页，前端展示 favicon 用                           |
| config            | JSONB        | 是   | 插件配置（apiKey、limit、分类过滤等），默认 `{}`        |
| cron              | VARCHAR(64)  | 是   | 调度表达式（5 段标准 cron）                             |
| weight            | SMALLINT     | 是   | 源权重 1-10，参与热度计算，默认 5                       |
| enabled           | BOOLEAN      | 是   | 是否启用，默认 true                                     |
| last_run_at       | TIMESTAMPTZ  | 否   | 最后一次运行时间                                        |
| last_run_status   | VARCHAR(32)  | 否   | `SUCCESS` / `PARTIAL` / `FAILED`                        |
| consecutive_fails | SMALLINT     | 是   | 连续失败次数，默认 0；达 5 自动置 `enabled=false` 并告警 |
| created_at        | TIMESTAMPTZ  | -    | 创建时间                                                |
| updated_at        | TIMESTAMPTZ  | -    | 更新时间                                                |
| is_deleted        | BOOLEAN      | -    | 逻辑删除，默认 false                                    |

索引：`uk_source_name(name) WHERE is_deleted=false`、`idx_source_enabled(enabled, cron)`

> `config` 中的 `apiKey` 等敏感字段：入库前用 `SECRET_KEY` 做 AES-GCM 加密，
> 出参一律脱敏为 `"sk-****abcd"`，只有 ADMIN 可写不可读原文。

### `source_run_log` 表

| 字段            | 类型         | 必填 | 说明                                          |
| --------------- | ------------ | ---- | --------------------------------------------- |
| id              | BIGSERIAL    | 是   | 主键                                          |
| source_id       | BIGINT       | 是   | 采集源 ID                                     |
| task_id         | VARCHAR(64)  | 否   | Celery task id                                |
| trigger_type    | VARCHAR(32)  | 是   | `SCHEDULED` / `MANUAL`                        |
| triggered_by    | BIGINT       | 否   | 手动触发时的用户 ID                           |
| status          | VARCHAR(32)  | 是   | `RUNNING`/`SUCCESS`/`PARTIAL`/`FAILED`        |
| fetched_count   | INTEGER      | 是   | 抓到的条目数，默认 0                          |
| new_count       | INTEGER      | 是   | 实际新增入库数（去掉 url 重复），默认 0       |
| duration_ms     | INTEGER      | 否   | 耗时                                          |
| error_message   | TEXT         | 否   | 失败原因（截断 2000 字）                      |
| started_at      | TIMESTAMPTZ  | 是   | 开始时间                                      |
| finished_at     | TIMESTAMPTZ  | 否   | 结束时间                                      |
| created_at      | TIMESTAMPTZ  | -    | 创建时间                                      |
| updated_at      | TIMESTAMPTZ  | -    | 更新时间                                      |
| is_deleted      | BOOLEAN      | -    | 逻辑删除，默认 false                          |

索引：`idx_run_log_source_time(source_id, started_at DESC)`

> 保留 30 天，超期由 `cleanup_task` 物理删除。

---

## 后端接口

### GET /api/v1/sources
**说明**: 采集源列表。`GUEST` 可访问（仅返回启用中的源的公开字段）；`ADMIN` 返回完整字段

**Query**: `page` `size` `region` `category` `enabled` `keyword`

**Response 200**（ADMIN 视角）:
```json
{
  "items": [
    {
      "id": 1,
      "pluginKey": "hacker_news",
      "name": "Hacker News",
      "region": "GLOBAL",
      "category": "NEWS",
      "homeUrl": "https://news.ycombinator.com",
      "config": { "limit": 100, "apiKey": null },
      "cron": "0 * * * *",
      "weight": 9,
      "enabled": true,
      "lastRunAt": "2026-07-29T08:00:12Z",
      "lastRunStatus": "SUCCESS",
      "consecutiveFails": 0,
      "todayArticleCount": 87
    }
  ],
  "total": 8, "page": 1, "size": 20, "pages": 1
}
```

---

### GET /api/v1/admin/plugins
**说明**: 列出所有已注册的插件（用于新建采集源时选择），仅 `ADMIN`

**Response 200**:
```json
[
  {
    "pluginKey": "hacker_news",
    "displayName": "Hacker News",
    "region": "GLOBAL",
    "defaultCron": "0 * * * *",
    "defaultWeight": 9,
    "configSchema": {
      "type": "object",
      "properties": {
        "limit": { "type": "integer", "default": 100, "maximum": 500 }
      }
    },
    "registered": true
  }
]
```

> `configSchema` 由插件的 Pydantic Config 模型自动导出，前端据此动态渲染配置表单。

---

### POST /api/v1/admin/sources
**说明**: 新建采集源，仅 `ADMIN`

**Request Body**:
```json
{
  "pluginKey": "hacker_news",
  "name": "Hacker News",
  "region": "GLOBAL",
  "category": "NEWS",
  "homeUrl": "https://news.ycombinator.com",
  "config": { "limit": 100 },
  "cron": "0 * * * *",
  "weight": 9,
  "enabled": false
}
```

**Response 201**: source 对象

**错误情况**:
- `pluginKey` 未注册 → `400` `PLUGIN_NOT_FOUND`
- 名称重复 → `409` `SOURCE_NAME_EXISTS`
- cron 表达式非法 → `400` `INVALID_CRON`
- config 不满足插件 schema → `400` `INVALID_PLUGIN_CONFIG`

---

### PATCH /api/v1/admin/sources/{id}
**说明**: 修改采集源（字段均可选），仅 `ADMIN`。修改 `cron` 后自动刷新 Beat 调度表

**Response 200**: source 对象

---

### DELETE /api/v1/admin/sources/{id}
**说明**: 软删除采集源，仅 `ADMIN`。已采集的 `article` 保留，`source_id` 不置空

**Response 204**

---

### POST /api/v1/admin/sources/{id}/test
**说明**: **试跑**——用当前配置执行一次采集，**不写库**，返回前 10 条预览。用于新建源时验证配置

**Response 200**:
```json
{
  "success": true,
  "durationMs": 1820,
  "fetchedCount": 100,
  "preview": [
    {
      "externalId": "41234567",
      "url": "https://example.com/post",
      "title": "Show HN: I built an AI agent framework",
      "author": "pg",
      "publishedAt": "2026-07-29T07:12:00Z",
      "lang": "en",
      "metrics": { "points": 320, "comments": 88 }
    }
  ],
  "errorMessage": null
}
```

**错误情况**: 插件抛异常时 `success=false` + `errorMessage`，HTTP 仍返回 `200`（这是试跑结果而非接口错误）

---

### POST /api/v1/admin/sources/{id}/run
**说明**: 手动触发一次真实采集（异步），`EDITOR` 及以上

**Response 202**:
```json
{ "taskId": "c1a2b3...", "runLogId": 1024 }
```

---

### GET /api/v1/admin/sources/{id}/logs
**说明**: 某采集源的运行日志，`EDITOR` 及以上

**Query**: `page` `size` `status` `startDate` `endDate`

**Response 200**: 分页的 `source_run_log` 列表

---

## 前端页面

### 采集源管理（`/admin/sources`，ADMIN）

**列表区**
- 表格列：图标+名称、插件、区域 Badge、分类、cron、权重、启用 Switch、最后运行时间、最后状态 Badge、今日采集数
- 顶部：区域/分类/状态筛选 + 关键字搜索 + 「新建采集源」按钮
- 连续失败 ≥3 的行标黄，被自动禁用的行标红并显示告警图标
- 行内操作：编辑、试跑、立即运行、查看日志、删除

**新建/编辑弹窗**
1. 选择插件（下拉，展示 `displayName` + 区域）→ 自动带出默认 cron / weight
2. 基本信息：名称、区域、分类、主页 URL
3. 配置表单：**根据 `configSchema` 动态渲染**（用 `@rjsf/core` 或自研简版）
4. 调度：cron 输入框 + 右侧实时显示「下次运行时间」预览
5. 底部「先试跑一下」按钮 → 打开试跑结果抽屉，展示前 10 条预览表格
6. 试跑成功后「保存并启用」才可点

**运行日志抽屉**
- 时间线样式，每条显示：触发方式 Badge、状态、抓取数/新增数、耗时
- 失败条目可展开看 `errorMessage` 全文（等宽字体、可复制）
- 支持按状态过滤、按日期范围过滤

**源健康度卡片**（列表页顶部）
- 4 个统计卡：启用源数 / 今日采集总数 / 今日失败次数 / 平均耗时
- 一张 ECharts 折线图：最近 7 天每日采集量按源堆叠

---

## 业务规则

### 调度
- Celery Beat 启动时从 `source` 表加载所有 `enabled=true` 的记录动态注册周期任务
- `cron` 或 `enabled` 变更后，通过 Redis pub/sub 通知 Beat 热重载，无需重启
- 每个源一个独立任务，**互不阻塞**；同一源的任务加分布式锁 `lock:source:{id}`，上一轮未结束则跳过本轮并记 `PARTIAL`
- 单次采集超时 **180 秒**，超时判 `FAILED`

### 抓取礼貌性
- 统一 `User-Agent` 池轮换（5 个常见浏览器 UA）
- 同域名请求间隔 ≥ 1 秒（`asyncio.Semaphore` + 令牌桶）
- 遵守 `robots.txt`（`urllib.robotparser` 缓存 24 小时）
- HTTP 重试：`429`/`5xx`/超时 → 指数退避重试 3 次（1s/4s/16s）；`4xx`（除 429）不重试

### 数据写入
- `url_hash = sha256(normalized_url)`，`article` 表上唯一索引，重复直接跳过（`ON CONFLICT DO NOTHING`）
- URL 归一化：去 `utm_*` / `ref` / `from` / `spm` 等追踪参数，去 fragment，统一小写 host，去尾部 `/`
- 单次采集批量插入，分批 500 条
- `published_at` 缺失时用采集时间兜底，并在 `extra.published_at_inferred = true` 标记
- 超过 **7 天** 的历史条目直接丢弃（避免首次接入源时灌入大量陈旧数据）

### 失败处理
- 连续失败 5 次 → 自动 `enabled=false`，写 `audit_log`，后台列表红色告警
- `PARTIAL` 状态：部分条目解析失败但整体成功，记录失败条目数到 `error_message`
- 任何异常都必须写 `source_run_log`，禁止静默吞掉

### 敏感信息
- `config` 中键名匹配 `/(key|token|secret|password)/i` 的字段加密存储
- 出参脱敏：保留前 3 后 4 字符，中间 `****`
- 修改时前端传 `null` 表示"不修改"，传空字符串表示"清空"

---

## 完成标准

- [ ] `SourcePlugin` 抽象基类 + `RawItem` 模型 + 注册表装饰器完成
- [ ] 8 个一期插件全部实现，每个都有基于固定 fixture 的 `parse`/`normalize` 单元测试
- [ ] `source` / `source_run_log` 表与迁移完成
- [ ] Celery Beat 从数据库动态加载调度，cron 变更可热重载
- [ ] 分布式锁防止同源任务重入
- [ ] URL 归一化 + `url_hash` 去重生效，重复采集不产生重复 article
- [ ] 试跑接口不写库，能正确返回预览与错误信息
- [ ] 连续失败自动禁用 + 告警生效
- [ ] `config` 敏感字段加密存储 + 出参脱敏
- [ ] 后台采集源管理页完成：CRUD、动态配置表单、试跑抽屉、日志时间线、健康度图表
- [ ] 8 个源连续运行 24 小时无异常，日志完整

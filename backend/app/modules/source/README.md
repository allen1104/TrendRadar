# source 模块（采集源与插件）

> 需求：[doc/SPEC-source.md](../../../doc/SPEC-source.md)
> 声明式、可热加的采集器系统——新增一个源 = 新增一个插件文件 + 打装饰器，不改任何已有代码。

---

## 提供给其他模块的能力

- **采集器**：`SourcePlugin` ABC + 8 个内置插件 + `@register_plugin` 自动注册
- **数据库表**：`source`（配置）+ `source_run_log`（每次执行的记录）
- **CRUD / 试跑 / 运行**：[`api.py`](api.py) 11 个端点（前缀 `/admin/sources`）
- **Celery 任务**：[`tasks.py`](tasks.py) `fetch_task`（单源采集）

其他模块要采集内容时：

```python
from app.modules.source.service import SourceService

# 列出已启用的源
async with AsyncSessionLocal() as session:
    svc = SourceService(session)
    enabled = await svc.list(enabled_only=True)

# 或直接调插件（pipeline 模块完成后调）
from app.modules.source.plugins import list_registered_plugins
for key, cls in list_registered_plugins():
    plugin = cls({})
    items = await plugin.run()
```

---

## 8 个插件

按需扩展。新增插件时：建 `plugins/<key>.py` → 在 `plugins/__init__.py` 加一行 import → 自动注册。**0 行 if/elif**。

| plugin_key | 类型 | 实现 | 默认 cron | 备注 |
|---|---|---|---|---|
| `hacker_news` | REAL | ✅ | `0 * * * *` | HN Firebase API，并行 item 抓取 |
| `arxiv` | REAL | ✅ | `0 */2 * * *` | Atom API，feedparser 解析 |
| `github_trending` | REAL | ✅ | `30 * * * *` | GitHub Trending HTML，selectolax 解析 |
| `huggingface` | REAL | ✅ | `15 * * * *` | HuggingFace Models REST API |
| `product_hunt` | STUB | ❌ | `45 * * * *` | 需 GraphQL token，等 token 配置后实现 |
| `jiqizhixin` | STUB | ❌ | `10 * * * *` | 机器之心 RSS / HTML，抓取策略待定 |
| `qbitai` | STUB | ❌ | `20 * * * *` | 量子位 RSS / HTML，抓取策略待定 |
| `infoq_cn` | STUB | ❌ | `40 * * * *` | InfoQ 中国 API |

STUB 调会抛 `NotImplementedError`，正常路径上 source_service 自动捕获并返回 error。

---

## 设计关键

### `SourcePlugin` 抽象（[`plugins/base.py`](plugins/base.py)）

- `fetch()` 纯 IO（HTTP）
- `parse()` 纯函数（dict 转换）
- `normalize()` 纯函数（→ `RawItem`）
- `run()` 模板方法：fetch → parse → normalize，子类一般不覆盖

### URL 归一化（`normalize_url`）

去 `utm_*` / `ref` / `from` / `spm` 等追踪参数，统一 host 小写，去 fragment，去尾 `/`。**纯函数**，可离线单测。

### 注册表 vs `if/elif` 分发

```python
@register_plugin  # 装饰器，无 if/elif
class HackerNewsPlugin(SourcePlugin):
    plugin_key = "hacker_news"
    ...
```

`get_plugin_class("hacker_news")` 直接返回类对象。**新增源 = 加一个文件**，不需要改任何 if/elif。

### 失败自处理（[`service.py:record_run`](service.py)）

- 连续失败 5 次 → 自动 `enabled=false`
- 写 `source_run_log`，保留完整错误信息
- frontend 显示「连续失败 N」红字 + 「→ 自动禁用」标签

### 试跑与真跑

- **试跑** (`/admin/sources/{id}/test`)：fetch → parse → normalize → 返回前 10 条预览 + 错误，**不写库**
- **运行** (`/admin/sources/{id}/run`)：`Celery.delay(fetch_task)` 队列化，无 worker 时返回 500

---

## 验证状态

| 端点 | 状态 |
|---|---|
| `GET /admin/sources/plugins` | ✅ 8 个插件（4 real + 4 stub）|
| `GET /admin/sources` | ✅ 分页 + 过滤 + 关键词搜索 |
| `POST /admin/sources` | ✅ 201，重复名 → 409 |
| `PATCH /admin/sources/{id}` | ✅ 多字段更新 |
| `DELETE /admin/sources/{id}` | ✅ 软删除 |
| `POST /admin/sources/{id}/test` | ✅ 试跑不写库 |
| `POST /admin/sources/{id}/run` | ⚠️ 需要 Celery worker |
| `GET /admin/sources/{id}/logs` | ⚠️ 试跑不写日志，只有 Celery fetch_task 写 |

### 真实插件试跑结果（直连测试）

| 插件 | 状态 | 数量 | 耗时 |
|---|---|---|---|
| Hacker News | ✅ | 13 items | 2.0s |
| arXiv | ✅ | 5 items | 2.6s |
| GitHub Trending | ✅ | 17 items | 1.8s |
| HuggingFace | ❌ | 0 items | 21s 网络超时 |

HF 超时是本机网络限制（huggingface.co API 不可达），不是代码 bug。

---

## 待办

- [ ] `product_hunt` / `jiqizhixin` / `qbitai` / `infoq_cn` 4 个 stub 实现（HTML/RSS 选择器会随站点变化，过几周会失效）
- [ ] Celery Beat 动态加载源 cron（本期 Beat 只跑了静态 beat_schedule；动态加载见 SPEC-source.md 调度节）
- [ ] 通过 Redis pub/sub 热重载 Beat（cron 修改后免重启）
- [ ] 集成到 `pipeline`：`fetch_task` 拿到 RawItem 后调 `article_repository.upsert_many_from_raw(items)`；pipeline 模块完成后放开 `tasks.py` 末尾被注释的导入
- [ ] 接 `AuditService`：SOURCE_CREATE / SOURCE_UPDATE / SOURCE_DELETE / SOURCE_MANUAL_RUN / SOURCE_AUTO_DISABLED
- [ ] 单元测试：用 `respx` 模拟 httpx；离线跑 8 个插件的 `parse()` / `normalize()`

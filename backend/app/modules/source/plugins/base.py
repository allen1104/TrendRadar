"""采集器插件抽象基类 + 注册表 + 通用工具。"""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import structlog

log = structlog.get_logger()


# ---------------------------------------------------------------- 数据契约


@dataclass
class RawItem:
    """采集器产出的统一条目结构。所有插件必须返回它。"""

    external_id: str  # 源站唯一 ID
    url: str  # 原文链接（去除 utm_* 等追踪参数）
    title: str  # 标题（原语言）
    raw_content: str | None  # 原始正文/HTML（pipeline 二次抽取）
    author: str | None
    published_at: datetime | None  # 带时区的 UTC datetime
    lang: str  # ISO 639-1，如 "en" / "zh"
    metrics: dict[str, int]  # {"points": 320, "comments": 88, ...}
    extra: dict  # 源特有字段


# ---------------------------------------------------------------- URL 归一化（截 u8.9 节）

_TRACKING_PARAMS = re.compile(
    r"^(utm_|ref$|ref_|from$|from_|spm$|spm_|fbclid$|gclid$|mc_eid$|_ga$|_gl$)"
)


def normalize_url(url: str) -> str:
    """去掉 utm_* / ref / from / spm 等追踪参数，统一 host 小写，去尾斜杠，去 fragment。

    >>> normalize_url("HTTPS://Example.com/post?utm_source=x&keep=ok#frag")
    'https://example.com/post?keep=ok'
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    scheme = parsed.scheme.lower()
    host = (parsed.netloc or "").lower()
    # 过滤掉追踪参数
    filtered_qs = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        if not k:
            continue
        if _TRACKING_PARAMS.match(k):
            continue
        filtered_qs.append((k, v))
    # 注意：不要 dict 去重，会改变顺序；保持原本顺序
    query = urlencode(filtered_qs, doseq=True)
    # 去尾 /（仅根路径保留）
    path = parsed.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    return urlunparse((scheme, host, path, "", query, ""))


# ---------------------------------------------------------------- 抽象基类


class SourcePlugin(ABC):
    """所有采集器必须实现。注册用 @register_plugin 装饰器。"""

    plugin_key: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    region: ClassVar[str] = "GLOBAL"
    category: ClassVar[str] = "NEWS"
    default_cron: ClassVar[str] = "0 * * * *"
    default_weight: ClassVar[int] = 5
    config_schema: ClassVar[dict] = {}

    def __init__(self, config: dict) -> None:
        self.config = config or {}

    @abstractmethod
    async def fetch(self) -> list[dict]:
        """执行网络请求，返回原始响应片段列表（dict）。只负责 IO，不做解析。"""

    @abstractmethod
    def parse(self, raw: list[dict]) -> list[dict]:
        """把原始响应解析成中间字典。纯函数，可离线用 fixture 单测。"""

    @abstractmethod
    def normalize(self, parsed: list[dict]) -> list[RawItem]:
        """映射到 RawItem。纯函数。时间统一转 UTC，URL 归一化。"""

    async def run(self) -> list[RawItem]:
        """模板方法：fetch → parse → normalize。子类一般不覆盖。"""
        raw = await self.fetch()
        return self.normalize(self.parse(raw))

    async def close(self) -> None:
        """释放 HTTP client 等资源。子类按需实现。"""


# ---------------------------------------------------------------- 注册表


_REGISTRY: dict[str, type[SourcePlugin]] = {}


def register_plugin(cls: type[SourcePlugin]) -> type[SourcePlugin]:
    """装饰器：把 SourcePlugin 子类注册到全局表。禁止 if/elif 分发。"""
    if not cls.plugin_key:
        raise ValueError(f"{cls.__name__}.plugin_key is empty")
    if cls.plugin_key in _REGISTRY:
        raise ValueError(f"plugin_key '{cls.plugin_key}' already registered")
    _REGISTRY[cls.plugin_key] = cls
    return cls


def get_plugin_class(plugin_key: str) -> type[SourcePlugin]:
    if plugin_key not in _REGISTRY:
        raise KeyError(f"plugin_key '{plugin_key}' not registered")
    return _REGISTRY[plugin_key]


def list_registered_plugins() -> list[tuple[str, type[SourcePlugin]]]:
    return sorted(_REGISTRY.items())


# ---------------------------------------------------------------- 后台运行 helpers


async def run_safely(
    plugin: SourcePlugin,
    *,
    on_start: Callable | None = None,
    on_done: Callable | None = None,
    timeout: int = 180,
) -> tuple[list[RawItem], str | None]:
    """带超时 + 异常聚合地运行插件。"""

    async def _run() -> tuple[list[RawItem], str | None]:
        if on_start:
            on_start()
        try:
            items = await plugin.run()
        except Exception as exc:  # noqa: BLE001
            log.warning("plugin.error", plugin=plugin.plugin_key, error=str(exc))
            return [], f"{exc.__class__.__name__}: {exc}"
        else:
            return items, None
        finally:
            if on_done:
                on_done()

    try:
        items, err = await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        return [], f"Timeout after {timeout}s"
    return items, err


def utcnow() -> datetime:
    return datetime.now(UTC)

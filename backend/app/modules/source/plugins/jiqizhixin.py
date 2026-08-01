"""机器之心 — RSS 列表页。"""

from __future__ import annotations

from datetime import UTC, datetime

import feedparser

from app.modules.source.plugins.base import (
    RawItem,
    SourcePlugin,
    normalize_url,
    register_plugin,
)


@register_plugin
class JiqizhixinPlugin(SourcePlugin):
    """机器之心 ProAI 趋势频道（公开 RSS，无需鉴权）。

    配置: { "feed_url": str (default RSS) }
    """

    plugin_key = "jiqizhixin"
    display_name = "机器之心"
    region = "CN"
    category = "NEWS"
    default_cron = "10 * * * *"
    default_weight = 8
    config_schema = {
        "type": "object",
        "properties": {
            "feed_url": {
                "type": "string",
                "default": "https://www.jiqizhixin.com/rss",
                "description": "机器之心 RSS 地址",
            },
            "limit": {"type": "integer", "default": 30, "maximum": 100},
        },
    }

    async def fetch(self) -> list[dict]:
        import httpx

        url = self.config.get("feed_url", "https://www.jiqizhixin.com/rss")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            feed = feedparser.parse(r.text)
            return list(feed.entries)

    def parse(self, raw: list[dict]) -> list[dict]:
        return raw

    def normalize(self, parsed: list[dict]) -> list[RawItem]:
        items: list[RawItem] = []
        for e in parsed:
            link = e.get("link") or ""
            if not link:
                continue
            published = None
            if e.get("published_parsed"):
                try:
                    published = datetime(*e["published_parsed"][:6], tzinfo=UTC)
                except Exception:  # noqa: BLE001
                    published = None
            items.append(
                RawItem(
                    external_id=e.get("id") or link,
                    url=normalize_url(link),
                    title=(e.get("title") or "").strip().replace("\n", " "),
                    raw_content=e.get("summary") or None,
                    author=e.get("author") or None,
                    published_at=published,
                    lang="zh",
                    metrics={},
                    extra={"source_feed": "jiqizhixin"},
                )
            )
        return items
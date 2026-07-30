"""Hacker News — Firebase API，公开无需鉴权。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from app.modules.source.plugins.base import (
    RawItem,
    SourcePlugin,
    normalize_url,
    register_plugin,
)


@register_plugin
class HackerNewsPlugin(SourcePlugin):
    """topstories + item 两个端点，官方 JSON API。

    配置: { "limit": int = 100 }
    """

    plugin_key = "hacker_news"
    display_name = "Hacker News"
    region = "GLOBAL"
    category = "NEWS"
    default_cron = "0 * * * *"
    default_weight = 9
    config_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 100, "maximum": 500},
            "min_points": {"type": "integer", "default": 0, "minimum": 0},
        },
    }

    HN_BASE = "https://hacker-news.firebaseio.com/v0"

    async def fetch(self) -> list[dict]:
        limit = min(int(self.config.get("limit", 100)), 500)
        min_pts = int(self.config.get("min_points", 0))

        async with httpx.AsyncClient(timeout=15) as client:
            ids_resp = await client.get(f"{self.HN_BASE}/topstories.json")
            ids_resp.raise_for_status()
            ids = ids_resp.json()[:limit]

            # 并行批量抓详情（带并发上限防止打爆）
            sem = asyncio.Semaphore(20)

            async def fetch_one(item_id: int) -> dict | None:
                async with sem:
                    try:
                        r = await client.get(f"{self.HN_BASE}/item/{item_id}.json")
                        return r.json() if r.status_code == 200 else None
                    except Exception:  # noqa: BLE001
                        return None

            results = await asyncio.gather(*(fetch_one(i) for i in ids))
            results = [r for r in results if r]

        if min_pts > 0:
            results = [it for it in results if (it.get("score") or 0) >= min_pts]
        return results


    def _hn_time(self, ts) -> datetime | None:
        if not isinstance(ts, (int, float)):
            return None
        return datetime.fromtimestamp(ts, tz=UTC)

    def parse(self, raw: list[dict]) -> list[dict]:
        # HN 数据已经是我们想要的格式，parse 就是过滤掉 deleted/dead
        return [
            it
            for it in raw
            if it and it.get("type") == "story" and not it.get("dead") and not it.get("deleted")
        ]

    def normalize(self, parsed: list[dict]) -> list[RawItem]:
        items: list[RawItem] = []
        for it in parsed:
            url = normalize_url(it.get("url") or f"https://news.ycombinator.com/item?id={it['id']}")
            items.append(
                RawItem(
                    external_id=str(it["id"]),
                    url=url,
                    title=(it.get("title") or "").strip(),
                    raw_content=(it.get("text") or None) or None,
                    author=it.get("by"),
                    published_at=self._hn_time(it.get("time")),
                    lang="en",
                    metrics={
                        "points": int(it.get("score") or 0),
                        "comments": int(it.get("descendants") or 0),
                    },
                    extra={"type": "hn", "kids": it.get("kids") or []},
                )
            )
        return items

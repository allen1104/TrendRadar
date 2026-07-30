"""arXiv — 官方 Atom API，分类 cs.AI/cs.CL/cs.LG 等。"""

from __future__ import annotations

from datetime import datetime

import feedparser
import httpx

from app.modules.source.plugins.base import (
    RawItem,
    SourcePlugin,
    normalize_url,
    register_plugin,
)


@register_plugin
class ArxivPlugin(SourcePlugin):
    """arXiv Atom API。

    配置: { "categories": ["cs.AI", "cs.CL", "cs.LG"] (default), "max_results": int = 50 }
    """

    plugin_key = "arxiv"
    display_name = "arXiv"
    region = "GLOBAL"
    category = "PAPER"
    default_cron = "0 */2 * * *"
    default_weight = 8
    config_schema = {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["cs.AI", "cs.CL", "cs.LG"],
            },
            "max_results": {"type": "integer", "default": 50, "maximum": 200},
        },
    }

    ARXIV_URL = "https://export.arxiv.org/api/query"

    async def fetch(self) -> list[dict]:
        cats = self.config.get("categories") or ["cs.AI", "cs.CL", "cs.LG"]
        max_r = min(int(self.config.get("max_results", 50)), 200)
        # arXiv 搜索语法：cat:cs.AI OR cat:cs.CL OR cat:cs.LG
        cat_query = " OR ".join(f"cat:{c}" for c in cats)
        params = {
            "search_query": cat_query,
            "start": 0,
            "max_results": max_r,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self.ARXIV_URL, params=params)
            r.raise_for_status()
            feed = feedparser.parse(r.text)
            return list(feed.entries)

    def _to_dt(self, struct) -> datetime | None:
        try:
            return datetime(*struct[:6], tzinfo=__import__("datetime").UTC)
        except Exception:  # noqa: BLE001
            return None

    def parse(self, raw: list[dict]) -> list[dict]:
        # arXiv feedparser 返回的 entries 已经是 dict
        return raw

    def normalize(self, parsed: list[dict]) -> list[RawItem]:
        items: list[RawItem] = []
        for e in parsed:
            url = normalize_url(e.get("link", ""))
            if not url:
                continue
            # arXiv id: "http://arxiv.org/abs/2401.01234v1" 末尾
            ext_id = e.get("id") or url.split("/")[-1]
            tags = [
                t.get("term") if isinstance(t, dict) else t
                for t in e.get("tags", [])
                if (isinstance(t, dict) and t.get("term")) or (isinstance(t, str) and t)
            ]
            # arxiv_primary_category 在不同版本的 feedparser 里可能是 dict 或 string
            cat_raw = e.get("arxiv_primary_category")
            cats: list[str] = []
            if isinstance(cat_raw, dict):
                cats = [
                    v for v in cat_raw.values() if isinstance(v, str) and v
                ]
            elif isinstance(cat_raw, str) and cat_raw:
                cats = [cat_raw]

            published = None
            if e.get("published_parsed"):
                published = self._to_dt(e["published_parsed"])
            items.append(
                RawItem(
                    external_id=ext_id,
                    url=url,
                    title=(e.get("title") or "").strip().replace("\n", " "),
                    raw_content=(e.get("summary") or None) or None,
                    author=(e.get("author") or None) or None,
                    published_at=published,
                    lang="en",
                    metrics={},
                    extra={"tags": tags, "categories": cats},
                )
            )
        return items

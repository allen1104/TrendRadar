"""GitHub Trending — HTML 解析 github.com/trending。

用 selectolax 做 CSS 选择（快、纯 Python）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from selectolax.parser import HTMLParser

from app.modules.source.plugins.base import (
    RawItem,
    SourcePlugin,
    normalize_url,
    register_plugin,
)


@register_plugin
class GitHubTrendingPlugin(SourcePlugin):
    plugin_key = "github_trending"
    display_name = "GitHub Trending"
    region = "GLOBAL"
    category = "CODE"
    default_cron = "30 * * * *"
    default_weight = 9
    config_schema = {
        "type": "object",
        "properties": {
            "languages": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "空数组 = 全部。例：['python', 'typescript']",
            },
            "since": {
                "type": "string",
                "enum": ["daily", "weekly", "monthly"],
                "default": "daily",
            },
        },
    }

    async def fetch(self) -> list[dict]:
        languages = self.config.get("languages") or []
        since = self.config.get("since", "daily")
        url = "https://github.com/trending"
        if languages:
            url += "/" + ",".join(languages)
        url += f"?since={since}"

        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 TrendRadar/1.0"},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            return [{"html": r.text, "url": url}]

    def parse(self, raw: list[dict]) -> list[dict]:
        out = []
        for item in raw:
            tree = HTMLParser(item["html"])
            # 每个 repo 在 article.Box-row 里
            for article in tree.css("article.Box-row"):
                # 仓库名 / 描述 / 语言 / stars / forks
                a = article.css_first("h2 a")
                if not a:
                    continue
                full_name = (a.text() or "").strip().replace("\n", "").replace(" ", "")
                if not full_name:
                    continue
                desc_el = article.css_first("p")
                desc = (desc_el.text() or "").strip() if desc_el else ""
                # stars today / this week
                today_el = article.css_first("span.d-inline-block.float-sm-right")
                stars_today = 0
                if today_el:
                    m_today = next(
                        (
                            int(m.group(1).replace(",", ""))
                            for m in [
                                __import__("re").search(
                                    r"([\d,]+)\s+stars?\s+(?:today|this\s+week|this\s+month)",
                                    today_el.text() or "",
                                )
                            ]
                            if m
                        ),
                        None,
                    )
                    if m_today is not None:
                        stars_today = m_today
                # total stars 在 a[href$='/stargazers'] 后的 span
                total_stars = 0
                total_forks = 0
                for link in article.css("a"):
                    href = link.attrs.get("href", "")
                    if href.endswith("/stargazers"):
                        try:
                            total_stars = int(
                                (link.text() or "").strip().replace(",", "").replace(" ", "")
                            )
                        except ValueError:
                            pass
                    elif href.endswith("/forks"):
                        try:
                            total_forks = int(
                                (link.text() or "").strip().replace(",", "").replace(" ", "")
                            )
                        except ValueError:
                            pass
                lang_el = article.css_first("span[itemprop='programmingLanguage']")
                lang = (lang_el.text() or "").strip() if lang_el else ""

                out.append({
                    "full_name": full_name,
                    "url": f"https://github.com/{full_name}",
                    "description": desc,
                    "language": lang,
                    "stars": total_stars,
                    "forks": total_forks,
                    "stars_today": stars_today,
                })
        return out

    def normalize(self, parsed: list[dict]) -> list[RawItem]:
        return [
            RawItem(
                external_id=p["full_name"],
                url=normalize_url(p["url"]),
                title=p["full_name"] + (f": {p['description']}" if p.get("description") else ""),
                raw_content=p.get("description") or None,
                author=p["full_name"].split("/")[0] if "/" in p["full_name"] else None,
                published_at=datetime.now(UTC),
                lang="en",
                metrics={
                    "stars": p.get("stars", 0),
                    "forks": p.get("forks", 0),
                    "stars_today": p.get("stars_today", 0),
                },
                extra={"language": p.get("language", ""), "type": "github-trending"},
            )
            for p in parsed
        ]

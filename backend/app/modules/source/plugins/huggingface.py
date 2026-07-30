"""HuggingFace — 公开 REST API，按 trending 排序。"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.modules.source.plugins.base import (
    RawItem,
    SourcePlugin,
    normalize_url,
    register_plugin,
)


@register_plugin
class HuggingFacePlugin(SourcePlugin):
    plugin_key = "huggingface"
    display_name = "HuggingFace Models"
    region = "GLOBAL"
    category = "MODEL"
    default_cron = "15 * * * *"
    default_weight = 8
    config_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 30, "maximum": 100},
            "pipeline_tag": {
                "type": "string",
                "default": "",
                "description": "空 = 全部。例：text-generation",
            },
        },
    }

    HF_URL = "https://huggingface.co/api/models"

    async def fetch(self) -> list[dict]:
        limit = min(int(self.config.get("limit", 30)), 100)
        params = {
            "sort": "downloads",
            "direction": -1,
            "limit": limit,
        }
        if tag := self.config.get("pipeline_tag"):
            params["pipeline_tag"] = tag
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(self.HF_URL, params=params)
            r.raise_for_status()
            return r.json()

    def parse(self, raw: list[dict]) -> list[dict]:
        return raw

    def normalize(self, parsed: list[dict]) -> list[RawItem]:
        items: list[RawItem] = []
        for m in parsed:
            model_id = m.get("id") or m.get("modelId")
            if not model_id:
                continue
            downloads = int(m.get("downloads") or 0)
            likes = int(m.get("likes") or 0)
            pipeline_tag = (m.get("pipeline_tag") or "")
            items.append(
                RawItem(
                    external_id=model_id,
                    url=normalize_url(f"https://huggingface.co/{model_id}"),
                    title=model_id + (f"（{pipeline_tag}）" if pipeline_tag else ""),
                    raw_content=None,
                    author=model_id.split("/")[0] if "/" in model_id else None,
                    published_at=(
                        datetime.fromisoformat(m["createdAt"].replace("Z", "+00:00"))
                        if m.get("createdAt")
                        else None
                    ),
                    lang="en",
                    metrics={"downloads": downloads, "stars": likes},
                    extra={"pipeline_tag": pipeline_tag, "tags": m.get("tags") or []},
                )
            )
        return items

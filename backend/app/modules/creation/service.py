"""creation 业务编排层。

业务流程（SPEC-creation.md）：
  ① 上下文构造：event 标题 + event_analysis 全文 + 来源文章（最多 6 篇，每篇前 1500 字）
  ② 三级裁剪：总 token ≤ creation_max_context_tokens（默认 20000）
  ③ LLM 流式生成：
      start（带 draftId）→ outline（结构化 JSON，先于正文）→ delta → done
  ④ SSE 5 事件：start / outline / delta / done / error
  ⑤ 限流与配额：复用 ai_user_rate_limit；单用户草稿 ≤ 500；regenerate ≤ 5
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RateLimitError
from app.core.redis import redis_client
from app.modules.admin.service import ConfigService
from app.modules.ai.enums import CallStatus, TaskKey
from app.modules.ai.gateway.gateway import LLMGateway
from app.modules.ai.gateway.types import LLMRequest
from app.modules.ai.model import AICallLog, AIModel, PromptTemplate
from app.modules.creation.enums import DraftStatus, Platform, Style
from app.modules.creation.exceptions import (
    DraftNotFoundError,
    EventNotAnalyzedError,
    InvalidPlatformError,
    InvalidStyleError,
    QuotaExceededError,
    TargetWordsOutOfRangeError,
    TooManyRegenerationsError,
)
from app.modules.creation.model import CreationDraft
from app.modules.creation.repository import CreationDraftRepository
from app.modules.creation.schema import (
    DraftCreateRequest,
    DraftRegenerateRequest,
    DraftUpdateRequest,
    OptionsResponse,
    OutlineItem,
    PlatformOption,
    StyleOption,
)

log = structlog.get_logger()

# 上下文与限制
CONTEXT_MAX_TOKENS_DEFAULT = 20000
ARTICLE_TRIM_STEPS = (1500, 800, 400)
ARTICLE_KEEP_MAX = 6
HISTORY_KEEP_FIRST = 1
HISTORY_KEEP_RECENT = 4

# 业务配额
DRAFT_QUOTA_PER_USER = 500
REGENERATE_LIMIT = 5

# 平台与风格元数据（也可放 system_config，但前端需要静态渲染，且 ADMIN 不常改）
PLATFORM_META: dict[Platform, dict[str, Any]] = {
    Platform.WECHAT: {
        "name": "微信公众号",
        "icon": "wechat",
        "target_words": [1500, 3000],
        "description": "带钩子开头与关注引导",
    },
    Platform.BLOG: {
        "name": "技术博客",
        "icon": "blog",
        "target_words": [2000, 4000],
        "description": "标准 Markdown、代码块、参考链接",
    },
    Platform.WEIBO: {
        "name": "微博",
        "icon": "weibo",
        "target_words": [60, 140],
        "description": "≤140 字 + 话题标签，可分条串",
    },
    Platform.XHS: {
        "name": "小红书",
        "icon": "xhs",
        "target_words": [300, 600],
        "description": "emoji 分段、口语化、结尾话题标签 5-8 个",
    },
    Platform.ZHIHU: {
        "name": "知乎回答",
        "icon": "zhihu",
        "target_words": [800, 2000],
        "description": "先给结论、分点论述、适度引用数据",
    },
    Platform.MARKDOWN: {
        "name": "纯 Markdown",
        "icon": "markdown",
        "target_words": [1000, 3000],
        "description": "无平台修饰，纯技术记录",
    },
}

STYLE_META: dict[Style, dict[str, str]] = {
    Style.TECHNICAL: {
        "name": "技术分析",
        "description": "冷静客观、重原理与实现、少形容词、可含伪代码",
    },
    Style.MARKETING: {
        "name": "营销风格",
        "description": "强钩子、痛点切入、场景化、有行动号召",
    },
    Style.DEEP_DIVE: {
        "name": "深度解读",
        "description": "背景→现状→影响→展望，长段论述，引用多方观点",
    },
    Style.NEWS: {
        "name": "新闻报道",
        "description": "倒金字塔、5W1H、中立陈述、时间线清晰",
    },
    Style.CASUAL: {
        "name": "轻松科普",
        "description": "类比通俗、少术语、有画面感、适合非技术读者",
    },
}

PLATFORM_TASK_KEY: dict[Platform, str] = {
    Platform.WECHAT: TaskKey.CREATION_WECHAT.value,
    Platform.BLOG: TaskKey.CREATION_BLOG.value,
    Platform.WEIBO: TaskKey.CREATION_WEIBO.value,
    Platform.XHS: TaskKey.CREATION_XHS.value,
    Platform.ZHIHU: TaskKey.CREATION_ZHIHU.value,
    Platform.MARKDOWN: TaskKey.CREATION_MARKDOWN.value,
}

USER_RATE_LIMIT_KEY_PREFIX = "creation:user_rate"
USER_RATE_LIMIT_WINDOW = 3600


# ============================================================ 纯函数


def _truncate(s: str, limit: int) -> str:
    return s if not s or len(s) <= limit else s[:limit]


def estimate_tokens(s: str) -> int:
    """极简 token 估算：英文 4 字符 / token，中文 1.5 字符 / token。"""
    if not s:
        return 0
    ascii_chars = sum(1 for c in s if ord(c) < 128)
    cjk_chars = len(s) - ascii_chars
    return int(ascii_chars / 4 + cjk_chars / 1.5)


def select_top_articles(articles: list[dict[str, Any]], keep: int) -> list[dict[str, Any]]:
    """按 source.weight + content 长度挑前 keep 篇。"""
    if len(articles) <= keep:
        return articles

    def _score(a: dict[str, Any]) -> tuple[int, int]:
        return (int(a.get("source_weight") or 0), len(a.get("content") or ""))

    return sorted(articles, key=_score, reverse=True)[:keep]


def trim_history(
    history: list[dict[str, Any]],
    *,
    keep_first: int = HISTORY_KEEP_FIRST,
    keep_recent: int = HISTORY_KEEP_RECENT,
) -> list[dict[str, Any]]:
    if len(history) <= keep_first + keep_recent:
        return history
    return history[:keep_first] + history[-keep_recent:]


def build_context(
    *,
    event_title: str,
    event_analysis: str,
    articles: list[dict[str, Any]],
    target_words: int,
    audience: str,
    extra_requirement: str,
    style: str,
    platform: str,
    max_tokens: int = CONTEXT_MAX_TOKENS_DEFAULT,
) -> dict[str, Any]:
    """三级裁剪构造 prompt 变量。"""
    trimmed = [dict(a) for a in articles]
    for step in ARTICLE_TRIM_STEPS:
        total = (
            estimate_tokens(event_title)
            + estimate_tokens(event_analysis)
            + estimate_tokens(str(target_words))
            + estimate_tokens(audience or "")
            + estimate_tokens(extra_requirement or "")
            + estimate_tokens(style)
            + estimate_tokens(platform)
        )
        for a in trimmed:
            total += estimate_tokens(a.get("content") or "") + estimate_tokens(a.get("title") or "")
        if total <= max_tokens:
            return _pack(
                event_title, event_analysis, trimmed, target_words,
                audience, extra_requirement, style, platform,
            )
        for a in trimmed:
            a["content"] = _truncate(a.get("content") or "", step)

    trimmed = select_top_articles(trimmed, ARTICLE_KEEP_MAX)
    return _pack(
        event_title, event_analysis, trimmed, target_words,
        audience, extra_requirement, style, platform,
    )


def _pack(
    event_title: str,
    event_analysis: str,
    articles: list[dict[str, Any]],
    target_words: int,
    audience: str,
    extra_requirement: str,
    style: str,
    platform: str,
) -> dict[str, Any]:
    return {
        "eventTitle": event_title,
        "eventAnalysis": event_analysis,
        "articles": [
            {
                "index": a["index"],
                "title": a["title"],
                "source_name": a.get("source_name", ""),
                "url": a.get("url", ""),
                "content": a.get("content") or "",
            }
            for a in articles
        ],
        "targetWords": target_words,
        "audience": audience,
        "extraRequirement": extra_requirement,
        "style": style,
        "platform": platform,
    }


def parse_outline(raw: str | None) -> list[dict[str, Any]]:
    """从 AI 输出中提取大纲 JSON 块。"""
    if not raw:
        return []
    raw = raw.strip()
    # 尝试直接解析
    try:
        data = json.loads(raw)
        return _normalize_outline(data)
    except (json.JSONDecodeError, TypeError):
        pass
    # 尝试从 markdown fence 里抽
    import re as _re

    m = _re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", raw)
    if m:
        try:
            data = json.loads(m.group(1))
            return _normalize_outline(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _normalize_outline(data: Any) -> list[dict[str, Any]]:
    """outline 统一为 [{heading, points}] 格式。"""
    out: list[dict[str, Any]] = []
    items = (
        data
        if isinstance(data, list)
        else data.get("outline")
        if isinstance(data, dict)
        else []
    )
    if not isinstance(items, list):
        return []
    for it in items:
        if not isinstance(it, dict):
            continue
        heading = str(it.get("heading") or "").strip()
        if not heading:
            continue
        pts_raw = it.get("points") or []
        if isinstance(pts_raw, list):
            points = [str(p).strip() for p in pts_raw if str(p).strip()]
        else:
            points = []
        out.append({"heading": heading, "points": points[:8]})
    return out


def count_words(content: str) -> int:
    """粗略字数：去掉空白后字符数。"""
    if not content:
        return 0
    return len("".join(content.split()))


def title_from_event(event_title: str) -> str:
    return (event_title or "")[:120]


def sanitize_filename(s: str, ext: str) -> str:
    """生成安全的导出文件名：事件标题前 20 字 + _platform_yyyyMMdd.ext。"""
    import re as _re

    s = _re.sub(r"[\\/:*?\"<>|\s]+", "_", (s or "").strip())[:20] or "draft"
    date = datetime.now(UTC).strftime("%Y%m%d")
    return f"{s}_{date}.{ext}"


def render_markdown(content: str) -> str:
    """导出用：原样返回。"""
    return content or ""


def render_plain_text(content: str) -> str:
    """导出 TXT：去掉 markdown 标记。"""
    import re as _re

    if not content:
        return ""
    s = _re.sub(r"^#{1,6}\s+", "", content, flags=_re.MULTILINE)
    s = _re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = _re.sub(r"\*([^*]+)\*", r"\1", s)
    s = _re.sub(r"`([^`]+)`", r"\1", s)
    s = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s.strip()


def render_html(content: str, title: str) -> str:
    """导出 HTML：完整 HTML 文档（含基础排版样式）。"""
    import html as _html
    import re as _re

    body = _html.escape(content or "")
    body = _re.sub(r"^### (.+)$", r"<h3>\1</h3>", body, flags=_re.MULTILINE)
    body = _re.sub(r"^## (.+)$", r"<h2>\1</h2>", body, flags=_re.MULTILINE)
    body = _re.sub(r"^# (.+)$", r"<h1>\1</h1>", body, flags=_re.MULTILINE)
    body = _re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", body)
    body = _re.sub(r"\*([^*]+)\*", r"<em>\1</em>", body)
    body = _re.sub(r"`([^`]+)`", r"<code>\1</code>", body)
    body = _re.sub(r"\n\n", "</p><p>", body)
    body = f"<p>{body}</p>"
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
        f"<title>{_html.escape(title)}</title>"
        "<style>body{font-family:-apple-system,sans-serif;max-width:720px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.75;color:#222;}"
        "h1,h2,h3{margin-top:1.6em;} code{background:#f4f4f5;padding:0.1em 0.3em;"
        "border-radius:3px;font-size:0.92em;}</style></head>"
        f"<body><h1>{_html.escape(title)}</h1>{body}</body></html>"
    )


def render_wechat_html(content: str, title: str) -> str:
    """导出微信公众号 HTML：所有样式写到 style 属性（公众号编辑器会剥离 <style>）。

    规则：只保留标题/段落/列表/行内强调；代码块转为带背景色的 <pre>（不支持高亮）；
    表格简化为列表；忽略图片（公众号图需单独上传）。
    """
    import html as _html
    import re as _re

    if not content:
        return ""

    paragraphs: list[str] = []
    # 按行解析，逐段构造
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            # 跳过代码块（公众号不支持）
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                i += 1
            i += 1
            continue

        if stripped.startswith("# "):
            paragraphs.append(
                f'<p style="font-size:20px;font-weight:bold;margin:1.4em 0 0.6em;">'
                f"{_html.escape(stripped[2:])}</p>"
            )
        elif stripped.startswith("## "):
            paragraphs.append(
                f'<p style="font-size:17px;font-weight:bold;margin:1.2em 0 0.5em;color:#333;">'
                f"{_html.escape(stripped[3:])}</p>"
            )
        elif stripped.startswith("### "):
            paragraphs.append(
                f'<p style="font-size:15px;font-weight:bold;margin:1em 0 0.4em;color:#555;">'
                f"{_html.escape(stripped[4:])}</p>"
            )
        elif _re.match(r"^[-*]\s+", stripped):
            paragraphs.append(
                f'<p style="margin:0.3em 0;padding-left:1.2em;">'
                f"• {_inline(_html.escape(stripped[2:].strip()))}</p>"
            )
        elif _re.match(r"^\d+\.\s+", stripped):
            paragraphs.append(
                f'<p style="margin:0.3em 0;padding-left:1.2em;">'
                f"{_html.escape(stripped[:3])}"
                f"{_inline(_html.escape(stripped[3:].strip()))}</p>"
            )
        elif stripped == "---":
            paragraphs.append('<hr style="border:none;border-top:1px solid #eee;margin:1.5em 0;">')
        else:
            paragraphs.append(
                f'<p style="margin:0.6em 0;line-height:1.8;">'
                f"{_inline(_html.escape(stripped))}</p>"
            )
        i += 1

    body = "\n".join(paragraphs)
    return (
        f'<section style="font-family:-apple-system,sans-serif;font-size:15px;color:#222;'
        f'line-height:1.8;max-width:100%;">'
        f'<h1 style="font-size:20px;font-weight:bold;margin:0 0 1em;text-align:center;">'
        f"{_html.escape(title)}</h1>"
        f"{body}</section>"
    )


def _inline(s: str) -> str:
    """行内 markdown → 内联样式 HTML（**bold** / *em* / `code` / [text](url)）。"""
    import re as _re

    s = _re.sub(r"\*\*([^*]+)\*\*", r'<strong style="font-weight:bold;">\1</strong>', s)
    s = _re.sub(r"\*([^*]+)\*", r'<em style="font-style:italic;">\1</em>', s)
    s = _re.sub(r"`([^`]+)`", r'<code style="background:#f4f4f5;padding:0 4px;">\1</code>', s)
    s = _re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a style="color:#1e6bb8;text-decoration:underline;" href="\2">\1</a>',
        s,
    )
    return s


def sanitize_html_for_storage(content: str) -> str:
    """防止 XSS：导出的 HTML 同样过滤 <script>/javascript: 等。"""
    import re as _re

    if not content:
        return ""
    s = _re.sub(r"<script[\s\S]*?</script>", "", content, flags=_re.IGNORECASE)
    s = _re.sub(r"javascript:", "", s, flags=_re.IGNORECASE)
    s = _re.sub(r"\son\w+\s*=", "", s, flags=_re.IGNORECASE)
    return s


# ============================================================ Service


class CreationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CreationDraftRepository(session)

    # ============================================================ options

    async def get_options(self) -> OptionsResponse:
        platforms = [
            PlatformOption(
                key=k,
                name=v["name"],
                icon=v["icon"],
                target_words=v["target_words"],
                description=v["description"],
            )
            for k, v in PLATFORM_META.items()
        ]
        styles = [
            StyleOption(
                key=k,
                name=v["name"],
                description=v["description"],
            )
            for k, v in STYLE_META.items()
        ]
        return OptionsResponse(platforms=platforms, styles=styles)

    # ============================================================ 列表 / 详情

    async def list_drafts(
        self,
        user_id: int,
        *,
        event_id: int | None = None,
        platform: str | None = None,
        style: str | None = None,
        keyword: str | None = None,
        sort: str = "-created_at",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows, total = await self.repo.list_for_user(
            user_id,
            event_id=event_id,
            platform=platform,
            style=style,
            keyword=keyword,
            sort=sort,
            page=page,
            size=size,
        )
        # 批量查 event title（避免 N+1）
        event_ids = {r.event_id for r in rows}
        event_titles = await self._load_event_titles(event_ids) if event_ids else {}
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r.id,
                    "event_id": r.event_id,
                    "event_title": event_titles.get(r.event_id),
                    "platform": Platform(r.platform),
                    "style": Style(r.style),
                    "title": r.title,
                    "word_count": r.word_count,
                    "is_edited": r.content_edited is not None,
                    "status": DraftStatus(r.status),
                    "regenerate_count": r.regenerate_count,
                    "cost_usd": float(r.cost_usd or 0),
                    "created_at": r.created_at,
                }
            )
        return out, total

    async def get_draft(self, user_id: int, draft_id: int) -> dict[str, Any]:
        d = await self.repo.get_for_user(user_id, draft_id)
        if d is None:
            raise DraftNotFoundError
        return _draft_to_detail_dict(d)

    async def update_draft(
        self, user_id: int, draft_id: int, payload: DraftUpdateRequest
    ) -> dict[str, Any]:
        d = await self.repo.get_for_user(user_id, draft_id)
        if d is None:
            raise DraftNotFoundError
        values: dict[str, Any] = {}
        if payload.title is not None:
            values["title"] = payload.title
        if payload.content_edited is not None:
            # 显式 None 表示清空（恢复 AI 原稿）
            values["content_edited"] = payload.content_edited
        if values:
            await self.repo.update_incremental(draft_id, **values)
            await self.session.commit()
            await self.session.refresh(d)
        return _draft_to_detail_dict(d)

    async def delete_draft(self, user_id: int, draft_id: int) -> None:
        d = await self.repo.get_for_user(user_id, draft_id)
        if d is None:
            raise DraftNotFoundError
        await self.repo.soft_delete_id(draft_id)
        await self.session.commit()

    # ============================================================ 流式生成

    async def stream_create(
        self,
        *,
        user_id: int,
        payload: DraftCreateRequest,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """生成草稿。SSE：start / outline / delta / done / error。"""
        # 1. 校验
        platform_meta = PLATFORM_META.get(payload.platform)
        if platform_meta is None:
            raise InvalidPlatformError
        if payload.style not in STYLE_META:
            raise InvalidStyleError
        target_words = payload.target_words or platform_meta["target_words"][0]
        # 50% 范围
        lo, hi = platform_meta["target_words"]
        if target_words < lo * 0.5 or target_words > hi * 1.5:
            raise TargetWordsOutOfRangeError(
                extra={"platform": payload.platform.value, "lo": lo, "hi": hi}
            )

        # 2. event 已分析
        await self._ensure_event_analyzed(payload.event_id)

        # 3. 配额
        current = await self.repo.count_user_drafts(user_id)
        if current >= DRAFT_QUOTA_PER_USER:
            raise QuotaExceededError(
                extra={"limit": DRAFT_QUOTA_PER_USER, "current": current}
            )

        # 4. 用户限流
        await self._check_user_rate_limit(user_id)

        # 5. 建草稿（GENERATING 状态）
        extra_params = {
            "target_words": target_words,
            "audience": payload.audience or "",
            "extra_requirement": payload.extra_requirement or "",
        }
        draft = await self.repo.create(
            user_id=user_id,
            event_id=payload.event_id,
            platform=payload.platform.value,
            style=payload.style.value,
            title="",
            content="",
            outline=[],
            cover_suggestion=None,
            tags_suggestion=[],
            word_count=0,
            extra_params=extra_params,
            cost_usd=0,
            status=DraftStatus.GENERATING.value,
            regenerate_count=0,
        )
        await self.session.commit()
        await self.session.refresh(draft)

        async for ev in self._stream_into_draft(
            draft=draft,
            user_id=user_id,
            target_words=target_words,
            audience=payload.audience or "",
            extra_requirement=payload.extra_requirement or "",
            is_disconnected=is_disconnected,
        ):
            yield ev

    async def stream_regenerate(
        self,
        *,
        user_id: int,
        draft_id: int,
        payload: DraftRegenerateRequest,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """重新生成：原 content 备份到 content_edited（若有用户编辑）；正文清空从头生成。"""
        d = await self.repo.get_for_user(user_id, draft_id)
        if d is None:
            raise DraftNotFoundError
        if d.regenerate_count >= REGENERATE_LIMIT:
            raise TooManyRegenerationsError(
                extra={"limit": REGENERATE_LIMIT, "current": d.regenerate_count}
            )
        # 更新可改字段
        new_style = payload.style.value if payload.style else d.style
        if new_style not in STYLE_META:
            raise InvalidStyleError
        platform_meta = PLATFORM_META.get(Platform(d.platform))
        target_words = payload.target_words or (d.extra_params or {}).get("target_words") or (
            platform_meta["target_words"][0] if platform_meta else 1500
        )
        audience = payload.audience or (d.extra_params or {}).get("audience", "")
        extra_req = payload.extra_requirement or (d.extra_params or {}).get("extra_requirement", "")
        # 若用户有编辑 → 备份到 content_edited（强制二次确认的兜底）
        backup = d.content_edited if d.content_edited else d.content
        await self.repo.update_incremental(
            draft_id,
            content="",
            outline=[],
            cover_suggestion=None,
            tags_suggestion=[],
            word_count=0,
            status=DraftStatus.GENERATING.value,
            error_message=None,
            style=new_style,
            regenerate_count=d.regenerate_count + 1,
            cost_usd=0,
        )
        if backup and not d.content_edited:
            await self.repo.update_incremental(draft_id, content_edited=backup)
        await self.session.commit()
        await self.session.refresh(d)

        async for ev in self._stream_into_draft(
            draft=d,
            user_id=user_id,
            target_words=target_words,
            audience=audience,
            extra_requirement=extra_req,
            is_disconnected=is_disconnected,
            force_style=new_style,
        ):
            yield ev

    # ============================================================ 导出

    async def export_draft(
        self, user_id: int, draft_id: int, fmt: str
    ) -> tuple[bytes, str, str]:
        """返回 (bytes, content_type, filename)。"""
        d = await self.repo.get_for_user(user_id, draft_id)
        if d is None:
            raise DraftNotFoundError
        body = d.content_edited if d.content_edited else d.content
        title = d.title or title_from_event("")
        ext_map = {"MARKDOWN": "md", "HTML": "html", "WECHAT_HTML": "html", "TXT": "txt"}
        if fmt == "MARKDOWN":
            text = render_markdown(body)
            return (
                text.encode("utf-8"),
                "text/markdown; charset=utf-8",
                sanitize_filename(title, ext_map[fmt]),
            )
        if fmt == "TXT":
            text = render_plain_text(body)
            return (
                text.encode("utf-8"),
                "text/plain; charset=utf-8",
                sanitize_filename(title, ext_map[fmt]),
            )
        if fmt == "HTML":
            text = render_html(body, title)
            text = sanitize_html_for_storage(text)
            return (
                text.encode("utf-8"),
                "text/html; charset=utf-8",
                sanitize_filename(title, ext_map[fmt]),
            )
        if fmt == "WECHAT_HTML":
            text = render_wechat_html(body, title)
            text = sanitize_html_for_storage(text)
            return (
                text.encode("utf-8"),
                "text/html; charset=utf-8",
                sanitize_filename(title, ext_map[fmt]),
            )
        from app.modules.creation.exceptions import InvalidExportFormatError
        raise InvalidExportFormatError

    # ============================================================ 内部：核心流式循环

    async def _stream_into_draft(
        self,
        *,
        draft: CreationDraft,
        user_id: int,
        target_words: int,
        audience: str,
        extra_requirement: str,
        is_disconnected: Callable[[], Awaitable[bool]] | None,
        force_style: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """实际驱动 LLM 流式；共用 create 与 regenerate。"""
        style = force_style or draft.style
        platform = draft.platform
        task_key_str = PLATFORM_TASK_KEY.get(Platform(platform))
        if task_key_str is None:
            yield {
                "event": "error",
                "data": {"errorCode": "INVALID_PLATFORM", "detail": f"未知平台 {platform}"},
            }
            return

        # 组装上下文
        event_ctx = await self._load_event_context(draft.event_id)
        max_tokens = int(
            await ConfigService(self.session).get(
                "creation_max_context_tokens", CONTEXT_MAX_TOKENS_DEFAULT
            )
        )
        variables = build_context(
            event_title=event_ctx["title"],
            event_analysis=event_ctx["analysis"],
            articles=event_ctx["articles"],
            target_words=target_words,
            audience=audience,
            extra_requirement=extra_requirement,
            style=style,
            platform=platform,
            max_tokens=max_tokens,
        )

        # start 事件
        prompt_alias = await self._get_active_model_alias(task_key_str)
        yield {
            "event": "start",
            "data": {"draftId": draft.id, "modelAlias": prompt_alias},
        }

        full_content = ""
        outline_emitted = False
        prompt_tokens = 0
        completion_tokens = 0
        cost_usd = 0.0
        latency_ms = 0
        model_alias_used: str | None = prompt_alias
        cover_suggestion: str | None = None
        tags_suggestion: list[str] = []
        final_title: str = ""
        start_ts = datetime.now(UTC).timestamp()

        try:
            gateway = LLMGateway(self.session)
            prompt = await gateway._get_active_prompt(task_key_str)
            chain = await gateway._build_chain(prompt, None)
            primary_alias = chain[0]
            model = await gateway._get_model_by_alias(primary_alias)
            provider = await gateway._build_provider(model.provider)
            model_alias_used = model.alias

            rendered_system = _render(prompt.system_prompt, variables)
            rendered_user = _render(prompt.user_prompt, variables)
            request = LLMRequest(
                messages=[
                    {"role": "system", "content": rendered_system},
                    {"role": "user", "content": rendered_user},
                ],
                model=model.model_name,
                temperature=float(prompt.temperature or 0.3),
                max_tokens=prompt.max_tokens,
                response_schema=None,
                supports_json_schema=False,
            )

            chunk_buf: list[str] = []
            last_flush_at = datetime.now(UTC).timestamp()
            last_flush_len = 0

            async for delta in provider.stream_chat(request):
                if not delta:
                    continue
                if is_disconnected is not None and await is_disconnected():
                    log.info(
                        "creation.stream.client_disconnected",
                        draft_id=draft.id, partial_len=len(full_content),
                    )
                    break
                full_content += delta
                chunk_buf.append(delta)

                # outline 提取：首段 JSON 块（仅一次）
                if not outline_emitted:
                    parsed = parse_outline(delta if not chunk_buf[:-1] else "".join(chunk_buf))
                    if parsed:
                        outline_emitted = True
                        yield {
                            "event": "outline",
                            "data": {"outline": [_outline_item_dict(o) for o in parsed]},
                        }

                yield {"event": "delta", "data": {"content": delta}}

                now = datetime.now(UTC).timestamp()
                if (
                    len(full_content) - last_flush_len >= 200
                    or now - last_flush_at >= 2
                ):
                    try:
                        await self.repo.update_incremental(
                            draft.id, content=full_content, word_count=count_words(full_content)
                        )
                        await self.session.commit()
                    except Exception as exc:
                        log.warning("creation.flush_failed", error=str(exc))
                    last_flush_len = len(full_content)
                    last_flush_at = now

            # 完成：解析最终 title / cover / tags（约定：标题在文首第一行）
            title, body, cover, tags = _split_metadata(full_content)
            final_title = title
            cover_suggestion = cover
            tags_suggestion = tags
            full_content = body

            prompt_tokens = getattr(provider, "_last_prompt_tokens", 0) or 0
            completion_tokens = getattr(provider, "_last_completion_tokens", 0) or 0
            latency_ms = int((datetime.now(UTC).timestamp() - start_ts) * 1000)
            cost_usd = (
                float(model.price_input_per_1m or 0) * prompt_tokens / 1e6
                + float(model.price_output_per_1m or 0) * completion_tokens / 1e6
            )
            word_count = count_words(full_content)

            await self.repo.update_incremental(
                draft.id,
                title=final_title or title_from_event(event_ctx["title"]),
                content=full_content,
                cover_suggestion=cover_suggestion,
                tags_suggestion=tags_suggestion,
                word_count=word_count,
                cost_usd=cost_usd,
                status=DraftStatus.DONE.value,
                model_alias=model_alias_used,
                prompt_version=prompt.version,
            )
            await self.session.commit()

            yield {
                "event": "done",
                "data": {
                    "draftId": draft.id,
                    "title": final_title or title_from_event(event_ctx["title"]),
                    "wordCount": word_count,
                    "coverSuggestion": cover_suggestion,
                    "tagsSuggestion": tags_suggestion,
                    "costUsd": round(cost_usd, 6),
                    "latencyMs": latency_ms,
                },
            }

            # ai_call_log
            await self._log_ai_call(
                model_alias=model_alias_used or "unknown",
                prompt_version=prompt.version,
                event_id=draft.event_id,
                user_id=user_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                status=CallStatus.SUCCESS.value,
            )
        except Exception as exc:
            log.exception("creation.stream.error", draft_id=draft.id, error=str(exc))
            try:
                await self.repo.update_incremental(
                    draft.id,
                    content=full_content,
                    word_count=count_words(full_content),
                    status=DraftStatus.FAILED.value,
                    error_message=str(exc)[:500],
                    latency_ms=int((datetime.now(UTC).timestamp() - start_ts) * 1000),
                )
                await self.session.commit()
            except Exception:
                try:  # noqa: SIM105
                    await self.session.rollback()
                except Exception:  # noqa: S110
                    pass
            yield {
                "event": "error",
                "data": {
                    "errorCode": "LLM_UNAVAILABLE",
                    "detail": f"生成失败：{exc}"[:200],
                },
            }

    # ============================================================ 内部 helper

    async def _ensure_event_analyzed(self, event_id: int) -> None:
        from app.modules.pipeline.enums import EventStatus
        from app.modules.pipeline.model import Event

        ev = (
            await self.session.execute(
                select(Event).where(Event.id == event_id, Event.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if ev is None:
            raise EventNotAnalyzedError("事件不存在")
        if ev.status != EventStatus.ANALYZED.value:
            raise EventNotAnalyzedError(f"事件当前状态 {ev.status}，需 ANALYZED")

    async def _load_event_context(self, event_id: int) -> dict[str, Any]:
        """加载 event + analysis + 来源文章（最多 6 篇，每篇前 1500 字）。"""
        from sqlalchemy import select as _select

        from app.modules.ai.model import EventAnalysis
        from app.modules.pipeline.model import Article, Event, EventArticle
        from app.modules.source.model import Source

        ev = (
            await self.session.execute(
                select(Event).where(Event.id == event_id, Event.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if ev is None:
            return {"title": "", "analysis": "", "articles": []}

        analysis = (
            await self.session.execute(
                select(EventAnalysis).where(
                    EventAnalysis.event_id == event_id,
                    EventAnalysis.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()

        analysis_parts: list[str] = []
        if analysis is not None:
            if analysis.summary:
                analysis_parts.append(f"# 完整分析\n{analysis.summary}")
            if analysis.key_points:
                kp = "\n".join(f"- {p}" for p in (analysis.key_points or [])[:5])
                analysis_parts.append(f"核心观点：\n{kp}")
            if analysis.innovations:
                inn = "\n".join(f"- {p}" for p in (analysis.innovations or [])[:5])
                analysis_parts.append(f"创新点：\n{inn}")
            if analysis.summary_one_line:
                analysis_parts.append(f"一句话：{analysis.summary_one_line}")
        analysis_text = "\n\n".join(analysis_parts) or (ev.summary_one_line or "")

        rows = (
            (
                await self.session.execute(
                    _select(Article, EventArticle, Source)
                    .join(EventArticle, EventArticle.article_id == Article.id)
                    .join(Source, Source.id == Article.source_id)
                    .where(
                        EventArticle.event_id == event_id,
                        EventArticle.is_deleted.is_(False),
                        Article.is_deleted.is_(False),
                        Source.is_deleted.is_(False),
                    )
                    .order_by(EventArticle.is_primary.desc(), Article.published_at.asc())
                    .limit(ARTICLE_KEEP_MAX + 3)  # 多取，trim 后仍能保留 6 篇
                )
            )
            .all()
        )
        articles: list[dict[str, Any]] = []
        for idx, (art, _ea, src) in enumerate(rows, start=1):
            content = (art.content or "")[:1500]
            articles.append(
                {
                    "index": idx,
                    "title": art.title,
                    "source_name": src.name,
                    "url": art.url,
                    "content": content,
                    "source_weight": int(src.weight or 0),
                }
            )
        return {"title": ev.title, "analysis": analysis_text, "articles": articles}

    async def _load_event_titles(self, event_ids: set[int]) -> dict[int, str]:
        from app.modules.pipeline.model import Event

        if not event_ids:
            return {}
        rows = (
            await self.session.execute(
                select(Event.id, Event.title).where(
                    Event.id.in_(event_ids), Event.is_deleted.is_(False)
                )
            )
        ).all()
        return {r[0]: r[1] for r in rows}

    async def _check_user_rate_limit(self, user_id: int) -> None:
        limit = int(
            await ConfigService(self.session).get("ai_user_rate_limit", 20)
        )
        try:
            key = f"{USER_RATE_LIMIT_KEY_PREFIX}:{user_id}"
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, USER_RATE_LIMIT_WINDOW)
            if count > limit:
                ttl = await redis_client.ttl(key)
                retry_after = max(int(ttl or 0), 1)
                raise RateLimitError(
                    f"本小时 AI 调用已达 {limit} 次上限",
                    error_code="AI_RATE_LIMIT_EXCEEDED",
                    extra={"retryAfter": retry_after, "limit": limit},
                )
        except RateLimitError:
            raise
        except Exception as exc:
            log.warning("creation.ratelimit.redis_failed", error=str(exc))

    async def _get_active_model_alias(self, task_key: str) -> str | None:
        try:
            prompt = (
                await self.session.execute(
                    select(PromptTemplate).where(
                        PromptTemplate.is_active.is_(True),
                        PromptTemplate.is_deleted.is_(False),
                        PromptTemplate.task_key == task_key,
                    )
                )
            ).scalar_one_or_none()
            if prompt is None:
                return None
            return prompt.model_alias or "default-chat"
        except Exception:
            return None

    async def _log_ai_call(
        self,
        *,
        model_alias: str,
        prompt_version: int | None,
        event_id: int,
        user_id: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        status: str,
    ) -> None:
        try:
            model_row = (
                await self.session.execute(
                    select(AIModel).where(
                        AIModel.alias == model_alias, AIModel.is_deleted.is_(False)
                    )
                )
            ).scalar_one_or_none()
            log_row = AICallLog(
                trace_id="",
                task_key="creation_draft",  # 统一 task_key（细分走 prompt_version 区分）
                model_id=model_row.id if model_row else None,
                model_alias=model_alias,
                prompt_version=prompt_version,
                target_type="EVENT",
                target_id=event_id,
                user_id=user_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                status=status,
            )
            self.session.add(log_row)
            await self.session.commit()
        except Exception as exc:
            log.warning("creation.ai_call_log_failed", error=str(exc))
            try:  # noqa: SIM105
                await self.session.rollback()
            except Exception:  # noqa: S110
                pass


# ============================================================ 模块级 helper


def _render(template: str, variables: dict[str, Any]) -> str:
    from jinja2 import Environment, StrictUndefined, TemplateError

    env = Environment(undefined=StrictUndefined, autoescape=False)  # noqa: S701
    try:
        return env.from_string(template).render(**variables)
    except TemplateError as exc:
        raise ValueError(f"Prompt 渲染失败：{exc}") from exc


def _split_metadata(content: str) -> tuple[str, str, str | None, list[str]]:
    """约定：AI 输出首行是标题（# 标题），正文从第二行开始。
    元数据约定（可选）：
      COVER: <一段描述>
      TAGS: tag1, tag2, tag3
    没匹配就返回原内容，标题留空。
    """
    import re as _re

    if not content:
        return "", "", None, []
    lines = content.splitlines()
    title = ""
    body_lines: list[str] = []
    cover: str | None = None
    tags: list[str] = []
    i = 0
    if lines and lines[0].lstrip().startswith("# "):
        title = lines[0].lstrip()[2:].strip()[:300]
        i = 1
        # 跳过紧随的空行
        while i < len(lines) and not lines[i].strip():
            i += 1
    # COVER / TAGS 元数据（最多取 5 行）
    meta_count = 0
    while i < len(lines) and meta_count < 10:
        s = lines[i].strip()
        if s.startswith("COVER:"):
            cover = s[len("COVER:"):].strip()[:500]
            i += 1
            meta_count += 1
            continue
        if s.startswith("TAGS:"):
            raw = s[len("TAGS:"):].strip()
            tags = [t.strip() for t in _re.split(r"[,，;；\s]+", raw) if t.strip()][:8]
            i += 1
            meta_count += 1
            continue
        break
    body_lines = lines[i:]
    return title, "\n".join(body_lines).strip(), cover, tags


def _outline_item_dict(d: dict[str, Any]) -> dict[str, Any]:
    return OutlineItem(heading=d.get("heading", ""), points=d.get("points") or []).model_dump()


def _draft_to_detail_dict(d: CreationDraft) -> dict[str, Any]:
    return {
        "id": d.id,
        "user_id": d.user_id,
        "event_id": d.event_id,
        "platform": Platform(d.platform),
        "style": Style(d.style),
        "title": d.title,
        "content": d.content,
        "content_edited": d.content_edited,
        "outline": [OutlineItem(**o) for o in (d.outline or [])],
        "cover_suggestion": d.cover_suggestion,
        "tags_suggestion": list(d.tags_suggestion or []),
        "word_count": d.word_count,
        "extra_params": dict(d.extra_params or {}),
        "model_alias": d.model_alias,
        "prompt_version": d.prompt_version,
        "cost_usd": float(d.cost_usd or 0),
        "status": DraftStatus(d.status),
        "error_message": d.error_message,
        "regenerate_count": d.regenerate_count,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }
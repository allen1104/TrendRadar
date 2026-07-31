"""清洗纯函数。

无状态、可降级、单测友好。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import bleach
from dateutil import parser as date_parser

# jieba / yake 是可选依赖；任一缺失时静默回退到空关键词
try:
    import jieba.analyse  # type: ignore[import-untyped]

    JIEBA_OK = True
except Exception:  # noqa: BLE001
    JIEBA_OK = False

try:
    import yake  # type: ignore[import-untyped]

    YAKE_OK = True
except Exception:  # noqa: BLE001
    YAKE_OK = False


# 广告/赞助段正则（粗筛；后续可扩）
_AD_RE = re.compile(
    r"(?im)^\s*(?:"
    r"sponsored|advertisement|adsense|广告|赞助内容|推广|"
    r"click here to subscribe|点击关注|扫码关注"
    r")\s*[:：\-]?"
)

_DISCARD_MIN_CONTENT = 100
_DISCARD_MIN_TITLE = 10
_DISCARD_MAX_AGE_DAYS = 7
_ALLOWED_LANGS = {"en", "zh"}

# 时间归一化失败兜底
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def extract_content(raw_html: str | None) -> str:
    """bleach.clean 兜底去 HTML 标签。失败或无输入返回空串。"""
    if not raw_html:
        return ""
    try:
        cleaned = bleach.clean(raw_html, tags=[], strip=True, strip_comments=True)
        return cleaned.strip()
    except Exception:  # noqa: BLE001
        return ""


def strip_ad_paragraphs(content: str) -> str:
    """按行粗筛删除广告段。"""
    if not content:
        return content
    out_lines: list[str] = []
    for line in content.splitlines():
        if _AD_RE.match(line.strip()):
            continue
        out_lines.append(line)
    return "\n".join(out_lines).strip()


def normalize_published_at(raw: Any, *, fallback: datetime | None = None) -> datetime:
    """解析任意时间字符串到 UTC；失败回退到 fallback 或当前时间。"""
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    if raw is None:
        return fallback or utcnow()
    try:
        dt = date_parser.parse(str(raw), fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return fallback or utcnow()


def take_author(author_hint: str | None, content: str | None = None) -> str | None:
    """优先用插件给的 author；否则尝试从正文找 'By XXX' 行（暂简化）。"""
    if author_hint:
        a = author_hint.strip()
        if a:
            return a[:200]
    if not content:
        return None
    m = re.search(r"(?im)^\s*(?:by|author)\s*[：:]\s*(.+)$", content)
    if m:
        return m.group(1).strip()[:200]
    return None


def summarize(content: str | None, *, max_chars: int = 300) -> str:
    """前 3 句抽取式摘要，非 AI。"""
    if not content:
        return ""
    # 按句号/问号/感叹号/换行切
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", content)
    summary_parts: list[str] = []
    total = 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if total + len(p) > max_chars and summary_parts:
            break
        summary_parts.append(p)
        total += len(p)
        if len(summary_parts) >= 3:
            break
    return " ".join(summary_parts).strip()[:max_chars]


def extract_keywords(content: str, lang: str, *, top_k: int = 10) -> list[str]:
    """中文 jieba.textrank / 英文 yake。失败回退空列表。"""
    if not content or len(content) < 30:
        return []
    try:
        if lang == "zh" and JIEBA_OK:
            kws = jieba.analyse.textrank(content, topK=top_k, withWeight=False)
            return [str(k) for k in kws][:top_k]
        if lang == "en" and YAKE_OK:
            extractor = yake.KeywordExtractor(top=top_k, lan="en", n=3)
            kws = [k for k, _ in extractor.extract_keywords(content)]
            return kws[:top_k]
    except Exception:  # noqa: BLE001
        pass
    return []


def should_discard(
    *,
    title: str | None,
    content: str | None,
    lang: str | None,
    published_at: datetime,
) -> tuple[bool, str | None]:
    """返回 (是否丢弃, 原因)。"""
    title = title or ""
    content = content or ""
    if lang not in _ALLOWED_LANGS:
        return True, f"unsupported lang: {lang}"
    age_days = (utcnow() - published_at).total_seconds() / 86400
    if age_days > _DISCARD_MAX_AGE_DAYS:
        return True, f"article too old: {age_days:.1f}d"
    if len(content) < _DISCARD_MIN_CONTENT and len(title) < _DISCARD_MIN_TITLE:
        return True, "content too short"
    return False, None
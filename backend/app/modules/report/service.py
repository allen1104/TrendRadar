"""report 业务编排层。

流程（SPEC-report.md）：
  ① 选题：按 report_type 当日 ANALYZED 事件，按 recommend_index 排序
  ② AI 编排：调 LLMGateway.call(task_key=report_daily, response_schema=ReportStructure)
  ③ 渲染：sections → content_md
  ④ 发布：DRAFT → PUBLISHED（含 audit_log）
  ⑤ 导出：4 格式（MARKDOWN / HTML / PDF / WECHAT_HTML）
  ⑥ RSS：XML 生成（公开 / 私有 token）
  ⑦ 订阅：SITE / EMAIL / WEBHOOK 推送（webhook 用 httpx，超时+重试）
"""

from __future__ import annotations

import re
import xml.sax.saxutils as saxutils
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.service import ConfigService
from app.modules.ai.enums import TaskKey
from app.modules.ai.gateway.gateway import LLMGateway
from app.modules.report.enums import (
    REPORT_FILTER_SQL,
    REPORT_MAX_ITEMS,
    REPORT_MIN_ITEMS,
    REPORT_SECTIONS,
    REPORT_TYPE_NAMES,
    ExportFormat,
    ReportStatus,
    ReportType,
    SubscriptionChannel,
)
from app.modules.report.exceptions import (
    CandidatesInsufficientError,
    InvalidExportFormatError,
    InvalidReportTypeError,
    ReportAlreadyExistsError,
    ReportAlreadyPublishedError,
    ReportHasNoItemsError,
    ReportItemNotFoundError,
    ReportNotFoundError,
    WebhookUrlRequiredError,
)
from app.modules.report.model import Report, ReportItem, ReportSubscription
from app.modules.report.repository import (
    ReportItemRepository,
    ReportRepository,
    ReportSubscriptionRepository,
)
from app.modules.report.schema import (
    ReportItemEventInfo,
    ReportItemWithEvent,
    ReportSection,
    SubscriptionResponse,
)

log = structlog.get_logger()

# ============================================================ 常量


# 每条 item 注入 prompt 的最大正文长度（用于 AI 编排阶段）
CANDIDATE_BRIEF_LIMIT = 200
# AI 编排超时（秒）
ORCHESTRATE_TIMEOUT = 180


# ============================================================ Pydantic schema（编排输出）


# 下面这些类仅用于 response_schema 约束；字段名为 snake_case 走 model_json_schema
from pydantic import BaseModel, Field  # noqa: E402


class OrchItem(BaseModel):
    event_id: int = Field(description="候选事件 ID")
    section: str = Field(description="板块名，必须在指定 sections 列表内")
    headline: str = Field(max_length=200, description="日报条目标题，可改写事件标题")
    brief: str = Field(description="80-150 字简述")
    is_top: bool = Field(default=False, description="是否板块头条")


class OrchSection(BaseModel):
    name: str = Field(description="板块名")
    items: list[OrchItem] = Field(default_factory=list)


class ReportStructure(BaseModel):
    title: str = Field(description="日报标题，如「AI 日报 · 2026年7月29日」")
    intro: str = Field(description="导语，150-300 字综述")
    outro: str = Field(default="以上就是今天的日报，明天见。", description="结尾语")
    sections: list[OrchSection]


# ============================================================ 纯函数


def _truncate(s: str, limit: int) -> str:
    if not s:
        return ""
    return s if len(s) <= limit else s[:limit]


def estimate_tokens(s: str) -> int:
    """与 assistant 共用的极简估算。"""
    if not s:
        return 0
    ascii_chars = sum(1 for c in s if ord(c) < 128)
    cjk_chars = len(s) - ascii_chars
    return int(ascii_chars / 4 + cjk_chars / 1.5)


def build_candidate_briefs(
    candidates: list[dict[str, Any]],
    *,
    brief_limit: int = CANDIDATE_BRIEF_LIMIT,
) -> list[dict[str, Any]]:
    """把 candidates 转成 AI 编排所需的轻量 dict（含编号）。"""
    out: list[dict[str, Any]] = []
    for idx, c in enumerate(candidates, start=1):
        out.append(
            {
                "index": idx,
                "event_id": int(c["event_id"]),
                "title": c.get("title") or "",
                "summary_one_line": c.get("summary_one_line") or "",
                "recommend_index": float(c.get("recommend_index") or 0),
                "categories": list(c.get("categories") or []),
                "source_count": int(c.get("source_count") or 0),
                "brief": _truncate(c.get("summary_one_line") or c.get("title") or "", brief_limit),
            }
        )
    return out


def render_content_md(
    *,
    title: str,
    intro: str,
    outro: str,
    sections: list[dict[str, Any]],
) -> str:
    """把编排输出渲染为完整 Markdown。

    sections 元素：{name, items: [{event_id, headline, brief, is_top, sort_order}]}
    """
    out: list[str] = []
    out.append(f"# {title}")
    out.append("")
    if intro:
        out.append(f"> {intro}")
        out.append("")
    # 按板块渲染
    for sec in sections:
        name = sec.get("name") or ""
        items = sec.get("items") or []
        if not items:
            continue
        out.append(f"## {name}")
        out.append("")
        for it in items:
            headline = it.get("headline") or ""
            brief = it.get("brief") or ""
            out.append(f"### {headline}")
            out.append("")
            if brief:
                out.append(brief)
                out.append("")
            if it.get("is_top"):
                # 头条标记：在尾部加 ⭐
                out.append("> 🔥 头条")
                out.append("")
    if outro:
        out.append("---")
        out.append("")
        out.append(outro)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def build_rss(
    *,
    site_title: str,
    site_link: str,
    site_desc: str,
    reports: list[Report],
    report_items_map: dict[int, list[ReportItem]],
) -> str:
    """生成 RSS 2.0 XML。"""
    items_xml: list[str] = []
    for r in reports:
        items = report_items_map.get(r.id, [])
        # 取 items 中的 headline 列表作为 description
        parts: list[str] = []
        for it in items:
            prefix = "🔥 " if it.is_top else ""
            parts.append(f"{prefix}[{it.section}] {it.headline}")
            if it.brief:
                parts.append(f"  {it.brief[:200]}")
        desc = "\n".join(parts) if parts else (r.intro or "")
        link = f"{site_link}/reports/{r.id}"
        pub = (r.published_at or r.updated_at or r.created_at).strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )
        items_xml.append(
            "    <item>\n"
            f"      <title>{saxutils.escape(r.title)}</title>\n"
            f"      <link>{saxutils.escape(link)}</link>\n"
            f"      <guid isPermaLink=\"false\">report-{r.id}</guid>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <description>{saxutils.escape(desc[:1000])}</description>\n"
            f"      <category>{saxutils.escape(r.report_type)}</category>\n"
            "    </item>"
        )
    last_build = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{saxutils.escape(site_title)}</title>\n"
        f"    <link>{saxutils.escape(site_link)}</link>\n"
        f"    <description>{saxutils.escape(site_desc)}</description>\n"
        f"    <language>zh-CN</language>\n"
        f"    <lastBuildDate>{last_build}</lastBuildDate>\n"
        + "\n".join(items_xml)
        + "\n  </channel>\n</rss>\n"
    )


def _sanitize_inline_style(html: str) -> str:
    """极简的 inline style 净化：去掉 <script> 与 on*= 属性。
    公众号编辑器会剥离 <script> 与 <style>，但客户端 XSS 仍可能注入 onerror=。
    """
    if not html:
        return ""
    # 去 <script> 与 <style> 标签
    html = re.sub(r"<\s*script\b[^>]*>.*?</\s*script\s*>", "", html, flags=re.S | re.I)
    html = re.sub(r"<\s*style\b[^>]*>.*?</\s*style\s*>", "", html, flags=re.S | re.I)
    # 去 on*= 属性
    html = re.sub(r'\s+on\w+\s*=\s*"[^"]*"', "", html, flags=re.I)
    html = re.sub(r"\s+on\w+\s*=\s*'[^']*'", "", html, flags=re.I)
    html = re.sub(r"\s+on\w+\s*=\s*\S+", "", html, flags=re.I)
    # 去 javascript: 协议
    html = re.sub(r'href\s*=\s*"javascript:[^"]*"', 'href="#"', html, flags=re.I)
    html = re.sub(r"href\s*=\s*'javascript:[^']*'", "href='#'", html, flags=re.I)
    return html


def render_html_doc(content_md: str, title: str) -> str:
    """完整 HTML 文档（基础排版）。"""
    body = _md_to_simple_html(content_md)
    body = _sanitize_inline_style(body)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="UTF-8" />\n'
        f"<title>{_esc(title)}</title>\n"
        "<style>\n"
        "body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;"
        " max-width: 760px; margin: 40px auto; padding: 0 16px; line-height: 1.7; color: #222; }\n"
        "h1 { font-size: 28px; border-bottom: 2px solid #eee; padding-bottom: 12px; }\n"
        "h2 { font-size: 22px; margin-top: 32px; border-left: 4px solid #3b82f6; padding-left: 12px; }\n"
        "h3 { font-size: 18px; margin-top: 24px; }\n"
        "blockquote { background: #f7f7f7; border-left: 4px solid #ddd; padding: 8px 16px; color: #555; }\n"
        "hr { border: 0; border-top: 1px solid #eee; margin: 32px 0; }\n"
        "</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def render_wechat_html(content_md: str, title: str) -> str:
    """公众号 HTML：所有样式写到 style 属性（公众号剥离 <style>）。"""
    body = _md_to_simple_html(content_md)
    body = _sanitize_inline_style(body)
    # 给关键标签加 inline style
    body = re.sub(
        r"<h1>",
        '<h1 style="font-size: 22px; font-weight: bold; margin: 20px 0 12px; color: #222;">',
        body,
    )
    body = re.sub(
        r"<h2>",
        '<h2 style="font-size: 19px; font-weight: bold; margin: 24px 0 10px;'
        ' padding-left: 10px; border-left: 4px solid #3b82f6; color: #222;">',
        body,
    )
    body = re.sub(
        r"<h3>",
        '<h3 style="font-size: 17px; font-weight: bold; margin: 18px 0 8px; color: #222;">',
        body,
    )
    body = re.sub(
        r"<blockquote>",
        '<blockquote style="background: #f7f7f7; border-left: 4px solid #ddd;'
        ' padding: 10px 14px; color: #555; margin: 12px 0;">',
        body,
    )
    body = re.sub(
        r"<p>",
        '<p style="margin: 10px 0; line-height: 1.75; color: #333;">',
        body,
    )
    body = re.sub(
        r"<hr ?/>",
        '<hr style="border: 0; border-top: 1px solid #eee; margin: 24px 0;" />',
        body,
    )
    return body


def render_plain_text(content_md: str) -> str:
    """Markdown 去标记（用于 TXT 导出与邮件预览）。"""
    txt = content_md
    # 去代码块
    txt = re.sub(r"```[\s\S]*?```", "", txt)
    # 去行内代码
    txt = re.sub(r"`([^`]+)`", r"\1", txt)
    # 去图片
    txt = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", txt)
    # 链接保留文本
    txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", txt)
    # 标题 / 引用 / 列表
    txt = re.sub(r"^#{1,6}\s*", "", txt, flags=re.M)
    txt = re.sub(r"^>\s?", "", txt, flags=re.M)
    txt = re.sub(r"^[-*]\s+", "• ", txt, flags=re.M)
    # 加粗/斜体
    txt = re.sub(r"\*\*([^*]+)\*\*", r"\1", txt)
    txt = re.sub(r"\*([^*]+)\*", r"\1", txt)
    return txt.strip() + "\n"


def _md_to_simple_html(md: str) -> str:
    """非常轻量的 Markdown → HTML（只覆盖日报用到的元素：h1/h2/h3/p/blockquote/hr/code/列表）。
    公众号与 HTML 导出共用。
    """
    lines = md.split("\n")
    out: list[str] = []
    in_code = False
    in_list = False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                out.append("</pre>")
                in_code = False
            else:
                out.append("<pre>")
                in_code = True
            continue
        if in_code:
            out.append(_esc(line))
            continue
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("")
            continue
        if line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{_esc(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{_esc(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{_esc(line[2:])}</h1>")
        elif line.startswith("> "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<blockquote>{_esc(line[2:])}</blockquote>")
        elif line == "---":
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("<hr />")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_esc(line[2:])}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{_esc(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def sanitize_filename(title: str, ext: str) -> str:
    """从 title 截前 20 字做文件名；去非法字符。"""
    base = title[:20]
    base = re.sub(r"[\\/:*?\"<>|]", "_", base)
    base = base.strip() or "report"
    return f"{base}.{ext}"


# ============================================================ Service


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.report_repo = ReportRepository(session)
        self.item_repo = ReportItemRepository(session)
        self.sub_repo = ReportSubscriptionRepository(session)

    # ============================================================ 列表 / 详情

    async def list_reports(
        self,
        *,
        report_type: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        only_published: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[Sequence[Report], int]:
        # GUEST 只看 PUBLISHED；EDITOR/ADMIN 可传 status
        eff_status = status
        if only_published and eff_status is None:
            eff_status = ReportStatus.PUBLISHED.value
        return await self.report_repo.list_paginated(
            report_type=report_type,
            status=eff_status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            size=size,
        )

    async def get_report(
        self,
        report_id: int,
        *,
        is_editor: bool = False,
        client_ip: str | None = None,
    ) -> Report:
        r = await self.report_repo.get(report_id)
        if r is None:
            raise ReportNotFoundError
        # 非 EDITOR 看不到非 PUBLISHED
        if not is_editor and r.status != ReportStatus.PUBLISHED.value:
            raise ReportNotFoundError
        return r

    async def get_report_with_sections(
        self,
        report_id: int,
        *,
        is_editor: bool = False,
        client_ip: str | None = None,
    ) -> tuple[Report, list[ReportSection], dict[int, ReportItemEventInfo]]:
        r = await self.get_report(report_id, is_editor=is_editor, client_ip=client_ip)
        items = await self.item_repo.list_for_report(r.id)
        event_map = await self._load_event_info([it.event_id for it in items])
        # 按 section 分组
        grouped: dict[str, list[ReportItemWithEvent]] = {}
        for it in items:
            grouped.setdefault(it.section, []).append(
                ReportItemWithEvent(
                    id=it.id,
                    event_id=it.event_id,
                    section=it.section,
                    sort_order=it.sort_order,
                    headline=it.headline,
                    brief=it.brief,
                    comment=it.comment,
                    is_top=it.is_top,
                    event=event_map.get(it.event_id),
                )
            )
        sections = [
            ReportSection(name=name, items=grouped[name]) for name in grouped
        ]
        return r, sections, event_map

    async def list_latest(self) -> list[Report]:
        return await self.report_repo.list_latest_published()

    # ============================================================ 选题

    async def select_candidates(
        self,
        report_type: str,
        report_date: date,
    ) -> list[dict[str, Any]]:
        """按 report_type + 当日筛选候选事件。"""
        if report_type not in {t.value for t in ReportType}:
            raise InvalidReportTypeError

        # 当日 00:00 UTC ~ 次日 00:00 UTC（report_date 是本地日，对齐到 UTC 起止）
        start_dt = datetime(report_date.year, report_date.month, report_date.day, tzinfo=UTC)
        end_dt = start_dt + timedelta(days=1)

        filter_extra = REPORT_FILTER_SQL.get(report_type, "")
        sql = text(
            f"""
            SELECT id, title, summary_one_line, recommend_index, categories, source_count
            FROM event
            WHERE is_deleted = false
              AND status = 'ANALYZED'
              AND is_hidden = false
              AND last_seen_at >= :start_dt
              AND last_seen_at < :end_dt
              {filter_extra}
            ORDER BY recommend_index DESC NULLS LAST, last_seen_at DESC
            LIMIT 50
            """
        )
        rows = (await self.session.execute(sql, {"start_dt": start_dt, "end_dt": end_dt})).all()
        return [
            {
                "event_id": r[0],
                "title": r[1] or "",
                "summary_one_line": r[2] or "",
                "recommend_index": float(r[3] or 0),
                "categories": list(r[4] or []) if r[4] else [],
                "source_count": int(r[5] or 0),
            }
            for r in rows
        ]

    # ============================================================ 生成（异步任务调用）

    async def generate_report(
        self,
        *,
        report_type: str,
        report_date: date,
        force: bool = False,
        user_id: int | None = None,
    ) -> Report:
        """生成一份日报（同步路径，由 Celery 任务或 API 调用）。
        已存在且未 force → ReportAlreadyExistsError。
        候选池不足 → CandidatesInsufficientError（200，但状态记 SKIPPED 由任务层处理）。
        """
        existing = await self.report_repo.get_by_type_and_date(report_type, report_date)
        if existing and not force:
            raise ReportAlreadyExistsError(
                extra={"reportId": existing.id, "reportDate": str(report_date)}
            )
        # 选题
        candidates = await self.select_candidates(report_type, report_date)
        min_items = REPORT_MIN_ITEMS.get(report_type, 3)
        max_items = REPORT_MAX_ITEMS.get(report_type, 10)
        if len(candidates) < min_items:
            raise CandidatesInsufficientError(
                extra={
                    "reportType": report_type,
                    "reportDate": str(report_date),
                    "candidates": len(candidates),
                    "minItems": min_items,
                }
            )
        # 取 max * 1.5 给 AI 多选
        take = min(len(candidates), max(1, int(max_items * 1.5)))
        candidates = candidates[:take]

        # 创建 Report 行（GENERATING）
        fields = dict(
            report_type=report_type,
            report_date=report_date,
            title=f"{REPORT_TYPE_NAMES.get(report_type, report_type)} · {report_date}",
            intro=None,
            outro=None,
            content_md="",
            content_edited=None,
            item_count=0,
            status=ReportStatus.GENERATING.value,
            published_at=None,
            published_by=None,
            view_count=0,
            model_alias=None,
            cost_usd=0,
            error_message=None,
        )
        if existing and force:
            # 覆盖：删除旧 items，update 关键字段
            await self.item_repo.delete_all_for_report(existing.id)
            await self.report_repo.update_incremental(
                existing.id,
                **{k: v for k, v in fields.items() if k != "report_type" and k != "report_date"},
            )
            report = await self.report_repo.get(existing.id)
        else:
            report = await self.report_repo.create(**fields)
        await self.session.flush()

        # AI 编排
        try:
            structure = await self._orchestrate(report_type, candidates)
        except Exception as exc:
            log.exception(
                "report.orchestrate_failed",
                report_id=report.id,
                report_type=report_type,
                error=str(exc),
            )
            await self.report_repo.update_incremental(
                report.id,
                status=ReportStatus.FAILED.value,
                error_message=str(exc)[:500],
            )
            await self.session.commit()
            # 抛回上层
            raise

        # 写 items + 渲染 content_md
        candidates_by_id = {c["event_id"]: c for c in candidates}
        items_to_create: list[dict[str, Any]] = []
        sort_counter = 0
        for sec in structure.sections:
            for it in sec.items:
                # 越界 eventId 丢弃
                if it.event_id not in candidates_by_id:
                    continue
                items_to_create.append(
                    dict(
                        report_id=report.id,
                        event_id=int(it.event_id),
                        section=sec.name,
                        sort_order=sort_counter,
                        headline=it.headline,
                        brief=it.brief,
                        comment=None,
                        is_top=bool(it.is_top),
                    )
                )
                sort_counter += 1
        if items_to_create:
            await self.item_repo.bulk_create(items_to_create)

        # 计算成本
        cost = float(getattr(structure, "_cost_usd", 0.0))
        model_alias = getattr(structure, "_model_alias", None)
        content_md = render_content_md(
            title=structure.title,
            intro=structure.intro,
            outro=structure.outro,
            sections=[sec.model_dump() for sec in structure.sections],
        )

        # 是否 auto_publish
        auto_publish = bool(
            await ConfigService(self.session).get("report_auto_publish", False)
        )
        target_status = (
            ReportStatus.PUBLISHED.value if auto_publish else ReportStatus.DRAFT.value
        )
        update_fields: dict[str, Any] = dict(
            title=structure.title,
            intro=structure.intro,
            outro=structure.outro,
            content_md=content_md,
            item_count=len(items_to_create),
            status=target_status,
            cost_usd=cost,
            model_alias=model_alias,
            error_message=None,
        )
        if auto_publish:
            update_fields["published_at"] = datetime.now(UTC)
            update_fields["published_by"] = user_id
        await self.report_repo.update_incremental(report.id, **update_fields)
        await self.session.commit()

        # 写 audit
        try:
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action="REPORT_GENERATE",
                target_type="REPORT",
                target_id=report.id,
                before=None,
                after={
                    "reportType": report_type,
                    "reportDate": str(report_date),
                    "status": target_status,
                    "itemCount": len(items_to_create),
                    "costUsd": round(cost, 6),
                },
                user_id=user_id,
            )
            await self.session.commit()
        except Exception as exc:
            log.warning("report.audit_failed", error=str(exc))

        # auto_publish 时直接发推送
        if auto_publish:
            try:
                await self._notify_publish(report.id)
            except Exception as exc:
                log.warning("report.notify_failed", report_id=report.id, error=str(exc))

        return await self.report_repo.get(report.id)  # type: ignore[return-value]

    async def _orchestrate(
        self, report_type: str, candidates: list[dict[str, Any]]
    ) -> ReportStructure:
        """调 LLMGateway.call 用结构化 schema 输出 ReportStructure。"""
        gateway = LLMGateway(self.session)
        # 拿 prompt 元信息（model_alias 等）
        prompt = await gateway._get_active_prompt(TaskKey.REPORT_DAILY.value)
        max_items = REPORT_MAX_ITEMS.get(report_type, 10)
        min_items = REPORT_MIN_ITEMS.get(report_type, 3)
        sections = REPORT_SECTIONS.get(report_type, ["头条"])
        variables = {
            "reportType": REPORT_TYPE_NAMES.get(report_type, report_type),
            "reportDate": str(date.today()),
            "sections": sections,
            "minItems": min_items,
            "maxItems": max_items,
            "candidates": build_candidate_briefs(candidates),
        }
        resp = await gateway.call(
            task_key=TaskKey.REPORT_DAILY.value,
            variables=variables,
            target_type="REPORT",
            target_id=None,
            user_id=None,
            response_schema=ReportStructure,
        )
        parsed = resp.parsed
        if parsed is None:
            raise ValueError("LLM 未返回结构化 JSON")
        # 注入成本 / model 字段便于上层回写
        parsed._cost_usd = float(  # type: ignore[attr-defined]
            resp.prompt_tokens / 1e6 * 0 + resp.completion_tokens / 1e6 * 0
        )
        # 实际成本应由 LLMResponse 已经算好（provider.estimate_cost）。重新计算：
        try:
            model = await gateway._get_model_by_alias(resp.model)
            pi = float(model.price_input_per_1m or 0)
            po = float(model.price_output_per_1m or 0)
            parsed._cost_usd = (  # type: ignore[attr-defined]
                resp.prompt_tokens * pi / 1e6
                + resp.completion_tokens * po / 1e6
            )
        except Exception:
            pass
        parsed._model_alias = resp.model  # type: ignore[attr-defined]
        return parsed

    # ============================================================ 编辑 / 发布 / 撤回

    async def update_report(
        self,
        *,
        user_id: int,
        report_id: int,
        title: str | None = None,
        intro: str | None = None,
        outro: str | None = None,
        content_edited: str | None = None,
    ) -> Report:
        r = await self.report_repo.get(report_id)
        if r is None:
            raise ReportNotFoundError
        before = {"title": r.title, "intro": r.intro, "outro": r.outro}
        await self.report_repo.update_incremental(
            report_id,
            title=title,
            intro=intro,
            outro=outro,
            content_edited=content_edited,
        )
        await self.session.commit()
        # audit
        try:
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action="REPORT_UPDATE",
                target_type="REPORT",
                target_id=report_id,
                before=before,
                after={"title": title, "intro": intro, "outro": outro},
                user_id=user_id,
            )
            await self.session.commit()
        except Exception as exc:
            log.warning("report.audit_failed", error=str(exc))
        return await self.report_repo.get(report_id)  # type: ignore[return-value]

    async def update_item(
        self,
        *,
        user_id: int,
        report_id: int,
        item_id: int,
        headline: str | None = None,
        brief: str | None = None,
        comment: str | None = None,
        section: str | None = None,
        sort_order: int | None = None,
        is_top: bool | None = None,
    ) -> ReportItem:
        it = await self.item_repo.get(item_id)
        if it is None or it.report_id != report_id:
            raise ReportItemNotFoundError
        await self.item_repo.update_incremental(
            item_id,
            headline=headline,
            brief=brief,
            comment=comment,
            section=section,
            sort_order=sort_order,
            is_top=is_top,
        )
        await self.session.commit()
        try:
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action="REPORT_ITEM_UPDATE",
                target_type="REPORT_ITEM",
                target_id=item_id,
                before=None,
                after={
                    "headline": headline,
                    "brief": brief,
                    "section": section,
                    "sortOrder": sort_order,
                    "isTop": is_top,
                },
                user_id=user_id,
            )
            await self.session.commit()
        except Exception as exc:
            log.warning("report.audit_failed", error=str(exc))
        return await self.item_repo.get(item_id)  # type: ignore[return-value]

    async def delete_item(
        self, *, user_id: int, report_id: int, item_id: int
    ) -> None:
        it = await self.item_repo.get(item_id)
        if it is None or it.report_id != report_id:
            raise ReportItemNotFoundError
        await self.item_repo.soft_delete_id(item_id)
        # 同步 item_count
        r = await self.report_repo.get(report_id)
        if r is not None:
            new_count = max(0, int(r.item_count or 0) - 1)
            await self.report_repo.update_incremental(report_id, item_count=new_count)
        await self.session.commit()
        try:
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action="REPORT_ITEM_DELETE",
                target_type="REPORT_ITEM",
                target_id=item_id,
                before=None,
                after=None,
                user_id=user_id,
            )
            await self.session.commit()
        except Exception as exc:
            log.warning("report.audit_failed", error=str(exc))

    async def add_item(
        self,
        *,
        user_id: int,
        report_id: int,
        event_id: int,
        section: str,
        headline: str | None,
        brief: str | None,
    ) -> ReportItem:
        r = await self.report_repo.get(report_id)
        if r is None:
            raise ReportNotFoundError
        # 自动从事件填充
        if headline is None or brief is None:
            ev_info = (await self._load_event_info([event_id])).get(event_id)
            if ev_info is None:
                raise ReportItemNotFoundError("事件不存在")
            if headline is None:
                headline = f"事件 #{event_id} 摘要"
            if brief is None:
                brief = "（无简述）"
        # 排序：插到 section 末尾
        existing = await self.item_repo.list_for_report(report_id)
        max_sort = max(
            (it.sort_order for it in existing if it.section == section),
            default=-1,
        )
        it = await self.item_repo.create(
            report_id=report_id,
            event_id=event_id,
            section=section,
            sort_order=max_sort + 1,
            headline=headline,
            brief=brief or "",
            comment=None,
            is_top=False,
        )
        await self.report_repo.update_incremental(
            report_id, item_count=int(r.item_count or 0) + 1
        )
        await self.session.commit()
        try:
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action="REPORT_ITEM_CREATE",
                target_type="REPORT_ITEM",
                target_id=it.id,
                before=None,
                after={
                    "reportId": report_id,
                    "eventId": event_id,
                    "section": section,
                },
                user_id=user_id,
            )
            await self.session.commit()
        except Exception as exc:
            log.warning("report.audit_failed", error=str(exc))
        return it

    async def publish(
        self, *, user_id: int, report_id: int
    ) -> Report:
        r = await self.report_repo.get(report_id)
        if r is None:
            raise ReportNotFoundError
        if r.status == ReportStatus.PUBLISHED.value:
            raise ReportAlreadyPublishedError
        if (r.item_count or 0) == 0:
            raise ReportHasNoItemsError
        await self.report_repo.update_incremental(
            report_id,
            status=ReportStatus.PUBLISHED.value,
            published_at=datetime.now(UTC),
            published_by=user_id,
        )
        await self.session.commit()
        # audit
        try:
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action="REPORT_PUBLISH",
                target_type="REPORT",
                target_id=report_id,
                before={"status": r.status},
                after={"status": ReportStatus.PUBLISHED.value},
                user_id=user_id,
            )
            await self.session.commit()
        except Exception as exc:
            log.warning("report.audit_failed", error=str(exc))

        # 推送订阅（失败不阻塞）
        try:
            await self._notify_publish(report_id)
        except Exception as exc:
            log.warning("report.notify_failed", report_id=report_id, error=str(exc))
        return await self.report_repo.get(report_id)  # type: ignore[return-value]

    async def unpublish(self, *, user_id: int, report_id: int) -> Report:
        r = await self.report_repo.get(report_id)
        if r is None:
            raise ReportNotFoundError
        await self.report_repo.update_incremental(
            report_id,
            status=ReportStatus.DRAFT.value,
            published_at=None,
            published_by=None,
        )
        await self.session.commit()
        try:
            from app.modules.admin.service import AuditService

            await AuditService(self.session).record(
                action="REPORT_UNPUBLISH",
                target_type="REPORT",
                target_id=report_id,
                before={"status": ReportStatus.PUBLISHED.value},
                after={"status": ReportStatus.DRAFT.value},
                user_id=user_id,
            )
            await self.session.commit()
        except Exception as exc:
            log.warning("report.audit_failed", error=str(exc))
        return await self.report_repo.get(report_id)  # type: ignore[return-value]

    # ============================================================ 导出

    async def export(
        self,
        *,
        report_id: int,
        format: str,
        is_editor: bool = False,
    ) -> tuple[bytes, str, str]:
        r = await self.get_report(report_id, is_editor=is_editor)
        # 优先 content_edited（EDITOR 已编辑）
        content = r.content_edited or r.content_md or ""
        if format == ExportFormat.MARKDOWN.value:
            data = content.encode("utf-8")
            return data, "text/markdown; charset=utf-8", sanitize_filename(r.title, "md")
        if format == ExportFormat.HTML.value:
            html = render_html_doc(content, r.title)
            return html.encode("utf-8"), "text/html; charset=utf-8", sanitize_filename(r.title, "html")
        if format == ExportFormat.WECHAT_HTML.value:
            html = render_wechat_html(content, r.title)
            return html.encode("utf-8"), "text/html; charset=utf-8", sanitize_filename(r.title, "html")
        if format == ExportFormat.PDF.value:
            pdf_bytes = await self._render_pdf(content, r.title)
            return pdf_bytes, "application/pdf", sanitize_filename(r.title, "pdf")
        raise InvalidExportFormatError

    async def _render_pdf(self, content_md: str, title: str) -> bytes:
        """PDF 导出：尝试 weasyprint；不可用时降级返回 HTML 字节（带 warning）。"""
        try:
            from weasyprint import HTML  # type: ignore[import-not-found]

            html = render_html_doc(content_md, title)
            return HTML(string=html).write_pdf()
        except Exception as exc:
            log.warning("report.pdf_failed_fallback_html", error=str(exc))
            # 降级：返回 HTML（前端按 text/html 处理）
            html = render_html_doc(content_md, title)
            return html.encode("utf-8")

    # ============================================================ RSS

    async def build_rss_for_token(self, token: str | None) -> str:
        """RSS 入口。无 token：公开最近 30 期；有 token：按订阅的 report_types 过滤。"""
        site_title = "TrendRadar 日报"
        site_link = ""
        site_desc = "AI 自动生成的科技热点日报"
        if token:
            sub = await self.sub_repo.get_by_rss_token(token)
            if sub is None:
                raise ReportNotFoundError("RSS token 无效")
            types = list(sub.report_types or [])
        else:
            types = None
        reports = await self.report_repo.list_recent_published(
            report_types=types, limit=30
        )
        # 批量拿 items
        items_map: dict[int, list[ReportItem]] = {}
        for r in reports:
            items_map[r.id] = await self.item_repo.list_for_report(r.id)
        return build_rss(
            site_title=site_title,
            site_link=site_link,
            site_desc=site_desc,
            reports=reports,
            report_items_map=items_map,
        )

    # ============================================================ 订阅

    async def get_subscription(self, user_id: int) -> SubscriptionResponse | None:
        sub = await self.sub_repo.get_for_user(user_id)
        if sub is None:
            return None
        return self._sub_to_response(sub)

    async def put_subscription(
        self,
        *,
        user_id: int,
        report_types: list[str],
        channel: str,
        webhook_url: str | None,
        enabled: bool,
    ) -> SubscriptionResponse:
        if channel == SubscriptionChannel.WEBHOOK.value and not webhook_url:
            raise WebhookUrlRequiredError
        # 校验 report_types 合法
        valid = {t.value for t in ReportType}
        cleaned = [t for t in report_types if t in valid]
        sub = await self.sub_repo.upsert(
            user_id=user_id,
            report_types=cleaned,
            channel=channel,
            webhook_url=webhook_url,
            enabled=enabled,
        )
        await self.session.commit()
        return self._sub_to_response(sub)

    async def reset_rss_token(self, user_id: int) -> SubscriptionResponse:
        sub = await self.sub_repo.reset_rss_token(user_id)
        if sub is None:
            raise ReportNotFoundError("订阅不存在")
        await self.session.commit()
        return self._sub_to_response(sub)

    def _sub_to_response(self, sub: ReportSubscription) -> SubscriptionResponse:
        rss_url = None
        if sub.rss_token:
            # 公开 RSS URL：站点公开 base url + token
            # 一期由前端拼接完整 URL（更灵活），后端只给 token
            rss_url = f"/api/v1/reports/rss?token={sub.rss_token}"
        return SubscriptionResponse(
            report_types=[ReportType(t) for t in (sub.report_types or []) if t in {x.value for x in ReportType}],
            channel=SubscriptionChannel(sub.channel),
            webhook_url=sub.webhook_url,
            rss_token=sub.rss_token,
            rss_url=rss_url,
            enabled=sub.enabled,
        )

    # ============================================================ 推送（webhook 等）

    async def _notify_publish(self, report_id: int) -> int:
        """发布后给所有启用且订阅了该类型的用户推 webhook / 邮件 / 站内。
        返回成功数。
        """
        r = await self.report_repo.get(report_id)
        if r is None:
            return 0
        items = await self.item_repo.list_for_report(r.id)
        event_map = await self._load_event_info([it.event_id for it in items])

        payload = {
            "reportId": r.id,
            "reportType": r.report_type,
            "title": r.title,
            "reportDate": str(r.report_date),
            "intro": r.intro,
            "contentMd": r.content_md,
            "items": [
                {
                    "section": it.section,
                    "headline": it.headline,
                    "brief": it.brief,
                    "eventId": it.event_id,
                    "isTop": it.is_top,
                }
                for it in items
            ],
        }

        subs = await self.sub_repo.list_enabled()
        n_ok = 0
        for sub in subs:
            types = list(sub.report_types or [])
            if types and r.report_type not in types:
                continue
            try:
                if sub.channel == SubscriptionChannel.WEBHOOK.value and sub.webhook_url:
                    await self._send_webhook(sub.webhook_url, payload)
                    n_ok += 1
                elif sub.channel == SubscriptionChannel.EMAIL.value:
                    # 一期 SMTP 不实现，记日志占位
                    log.info(
                        "report.email_notify_placeholder",
                        user_id=sub.user_id,
                        report_id=r.id,
                    )
                    n_ok += 1
                else:  # SITE：站内通知一期仅占位
                    n_ok += 1
            except Exception as exc:
                log.warning(
                    "report.notify_one_failed",
                    sub_id=sub.id,
                    error=str(exc),
                )
        return n_ok

    async def _send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        """POST payload 到 webhook url；超时 10s，重试 3 次。"""
        import httpx

        from app.core.config import settings

        timeout = 10.0
        retries = 3
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        url,
                        json=payload,
                        headers={"User-Agent": settings.user_agent or "TrendRadar/1.0"},
                    )
                    if resp.status_code < 500:
                        return
                    last_exc = RuntimeError(f"status {resp.status_code}")
            except Exception as exc:
                last_exc = exc
        raise last_exc or RuntimeError("webhook failed")

    # ============================================================ 内部：批量事件信息

    async def _load_event_info(
        self, event_ids: list[int]
    ) -> dict[int, ReportItemEventInfo]:
        if not event_ids:
            return {}
        from app.modules.pipeline.model import Event

        rows = (
            (
                await self.session.execute(
                    select(Event).where(
                        Event.id.in_(event_ids),
                        Event.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        out: dict[int, ReportItemEventInfo] = {}
        for ev in rows:
            primary_url = None
            if ev.primary_article_id:
                # 单查 url；不多走 N+1 的写法：再发一次 IN 查询更省事；这里只取 title+url 走单独查
                from app.modules.pipeline.model import Article

                art = (
                    await self.session.execute(
                        select(Article).where(
                            Article.id == ev.primary_article_id,
                            Article.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if art is not None:
                    primary_url = art.url
            out[ev.id] = ReportItemEventInfo(
                id=ev.id,
                recommend_index=float(ev.recommend_index or 0),
                source_count=int(ev.source_count or 0),
                categories=list(ev.categories or []),
                primary_article_url=primary_url,
            )
        return out


# ============================================================ Service

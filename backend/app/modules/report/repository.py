"""report 数据访问层。"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.report.model import Report, ReportItem, ReportSubscription

# ============================================================ Report


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(Report).where(Report.is_deleted.is_(False))

    async def get(self, report_id: int) -> Report | None:
        return (
            await self.session.execute(self._base().where(Report.id == report_id))
        ).scalar_one_or_none()

    async def get_by_type_and_date(
        self, report_type: str, report_date: date
    ) -> Report | None:
        return (
            await self.session.execute(
                self._base().where(
                    Report.report_type == report_type,
                    Report.report_date == report_date,
                )
            )
        ).scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        report_type: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[Sequence[Report], int]:
        from sqlalchemy import func

        stmt = self._base()
        if report_type:
            stmt = stmt.where(Report.report_type == report_type)
        if status:
            stmt = stmt.where(Report.status == status)
        if start_date:
            stmt = stmt.where(Report.report_date >= start_date)
        if end_date:
            stmt = stmt.where(Report.report_date <= end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar() or 0)

        offset = (page - 1) * size
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Report.report_date.desc(), Report.id.desc())
                    .offset(offset)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def list_latest_published(
        self, *, report_types: list[str] | None = None
    ) -> list[Report]:
        """各类型最新一期已发布日报（用于 GET /reports/latest）。"""
        stmt = self._base().where(Report.status == "PUBLISHED")
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Report.report_date.desc(), Report.id.desc()).limit(200)
                )
            )
            .scalars()
            .all()
        )
        latest_by_type: dict[str, Report] = {}
        for r in rows:
            if r.report_type not in latest_by_type:
                latest_by_type[r.report_type] = r
        if report_types:
            return [latest_by_type[t] for t in report_types if t in latest_by_type]
        return list(latest_by_type.values())

    async def list_recent_published(
        self,
        *,
        report_types: list[str] | None = None,
        token: str | None = None,
        limit: int = 30,
    ) -> list[Report]:
        """RSS 用：最近 N 期已发布日报。
        若提供 report_types，则过滤；否则全部类型。
        """
        stmt = self._base().where(Report.status == "PUBLISHED")
        if report_types:
            stmt = stmt.where(Report.report_type.in_(report_types))
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(Report.report_date.desc(), Report.id.desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create(self, **fields: Any) -> Report:
        r = Report(**fields)
        self.session.add(r)
        await self.session.flush()
        return r

    async def update_incremental(
        self,
        report_id: int,
        *,
        title: str | None = None,
        intro: str | None = None,
        outro: str | None = None,
        content_md: str | None = None,
        content_edited: str | None = None,
        item_count: int | None = None,
        status: str | None = None,
        published_at: Any = None,
        published_by: int | None = None,
        model_alias: str | None = None,
        cost_usd: float | None = None,
        error_message: str | None = None,
        view_count: int | None = None,
    ) -> None:
        values: dict[str, Any] = {}
        if title is not None:
            values["title"] = title
        if intro is not None:
            values["intro"] = intro
        if outro is not None:
            values["outro"] = outro
        if content_md is not None:
            values["content_md"] = content_md
        if content_edited is not None:
            values["content_edited"] = content_edited
        if item_count is not None:
            values["item_count"] = item_count
        if status is not None:
            values["status"] = status
        if published_at is not None:
            values["published_at"] = published_at
        if published_by is not None:
            values["published_by"] = published_by
        if model_alias is not None:
            values["model_alias"] = model_alias
        if cost_usd is not None:
            values["cost_usd"] = cost_usd
        if error_message is not None:
            values["error_message"] = error_message
        if view_count is not None:
            values["view_count"] = view_count
        if not values:
            return
        await self.session.execute(
            update(Report)
            .where(Report.id == report_id, Report.is_deleted.is_(False))
            .values(**values)
        )

    async def increment_view_count(self, report_id: int) -> None:
        """读详情时自增 view_count（一次性原子操作）。"""
        from sqlalchemy import func as _func

        await self.session.execute(
            update(Report)
            .where(Report.id == report_id, Report.is_deleted.is_(False))
            .values(view_count=Report.view_count + 1)
        )
        del _func  # noop

    async def soft_delete(self, report: Report) -> None:
        report.is_deleted = True
        await self.session.flush()


# ============================================================ ReportItem


class ReportItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(ReportItem).where(ReportItem.is_deleted.is_(False))

    async def list_for_report(self, report_id: int) -> list[ReportItem]:
        rows = (
            (
                await self.session.execute(
                    self._base()
                    .where(ReportItem.report_id == report_id)
                    .order_by(
                        ReportItem.is_top.desc(),
                        ReportItem.section,
                        ReportItem.sort_order,
                        ReportItem.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def get(self, item_id: int) -> ReportItem | None:
        return (
            await self.session.execute(self._base().where(ReportItem.id == item_id))
        ).scalar_one_or_none()

    async def create(self, **fields: Any) -> ReportItem:
        i = ReportItem(**fields)
        self.session.add(i)
        await self.session.flush()
        return i

    async def bulk_create(self, items: list[dict[str, Any]]) -> list[ReportItem]:
        rows = [ReportItem(**x) for x in items]
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def update_incremental(
        self,
        item_id: int,
        *,
        section: str | None = None,
        sort_order: int | None = None,
        headline: str | None = None,
        brief: str | None = None,
        comment: str | None = None,
        is_top: bool | None = None,
    ) -> None:
        values: dict[str, Any] = {}
        if section is not None:
            values["section"] = section
        if sort_order is not None:
            values["sort_order"] = sort_order
        if headline is not None:
            values["headline"] = headline
        if brief is not None:
            values["brief"] = brief
        if comment is not None:
            values["comment"] = comment
        if is_top is not None:
            values["is_top"] = is_top
        if not values:
            return
        await self.session.execute(
            update(ReportItem)
            .where(ReportItem.id == item_id, ReportItem.is_deleted.is_(False))
            .values(**values)
        )

    async def soft_delete_id(self, item_id: int) -> int:
        result = await self.session.execute(
            update(ReportItem)
            .where(ReportItem.id == item_id, ReportItem.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def delete_all_for_report(self, report_id: int) -> int:
        """重新生成时清空旧 items。"""
        result = await self.session.execute(
            update(ReportItem)
            .where(ReportItem.report_id == report_id, ReportItem.is_deleted.is_(False))
            .values(is_deleted=True)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


# ============================================================ ReportSubscription


class ReportSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(ReportSubscription).where(ReportSubscription.is_deleted.is_(False))

    async def get_for_user(self, user_id: int) -> ReportSubscription | None:
        return (
            await self.session.execute(
                self._base().where(ReportSubscription.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def get_by_rss_token(self, token: str) -> ReportSubscription | None:
        return (
            await self.session.execute(
                self._base().where(ReportSubscription.rss_token == token)
            )
        ).scalar_one_or_none()

    async def list_enabled(self) -> list[ReportSubscription]:
        rows = (
            (
                await self.session.execute(
                    self._base()
                    .where(ReportSubscription.enabled.is_(True))
                    .order_by(ReportSubscription.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def upsert(
        self,
        user_id: int,
        report_types: list[str],
        channel: str,
        webhook_url: str | None,
        enabled: bool,
    ) -> ReportSubscription:
        sub = await self.get_for_user(user_id)
        if sub is None:
            # 首次订阅 → 生成 RSS token
            sub = ReportSubscription(
                user_id=user_id,
                report_types=report_types,
                channel=channel,
                webhook_url=webhook_url,
                rss_token=self._gen_token(),
                enabled=enabled,
            )
            self.session.add(sub)
        else:
            sub.report_types = report_types
            sub.channel = channel
            sub.webhook_url = webhook_url
            sub.enabled = enabled
        await self.session.flush()
        return sub

    async def reset_rss_token(self, user_id: int) -> ReportSubscription | None:
        sub = await self.get_for_user(user_id)
        if sub is None:
            return None
        sub.rss_token = self._gen_token()
        await self.session.flush()
        return sub

    @staticmethod
    def _gen_token() -> str:
        return "rt_" + secrets.token_urlsafe(24)

    async def update_failure_count(
        self, user_id: int, delta: int
    ) -> None:
        """占位：webhook 失败计数（不在表里；先用日志或 audit 记录）。"""
        # 一期不落库；保留接口便于后续扩展
        return None

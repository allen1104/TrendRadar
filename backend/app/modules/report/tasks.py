"""report Celery 任务。

- generate_daily_reports：每日 08:00（可配 report_generate_cron）触发，
  并行生成 4 类日报（AI / TECH / GITHUB / AGENT），互不阻塞。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import structlog

from app.worker.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="report.generate_daily_reports",
    bind=True,
    max_retries=1,
)
def generate_daily_reports(self, target_date: str | None = None) -> dict[str, int]:
    """并行生成 4 类日报。
    target_date 格式 YYYY-MM-DD；为空则用 UTC 当天。
    """
    from app.db.session import AsyncSessionLocal, engine
    from app.modules.report.enums import ReportType
    from app.modules.report.exceptions import CandidatesInsufficientError
    from app.modules.report.service import ReportService

    if target_date:
        try:
            y, m, d = target_date.split("-")
            run_date = date(int(y), int(m), int(d))
        except Exception:
            run_date = datetime.now(UTC).date()
    else:
        run_date = datetime.now(UTC).date()

    async def _run() -> dict[str, int]:
        result = {"generated": 0, "skipped": 0, "failed": 0}
        for rtype in [
            ReportType.AI.value,
            ReportType.TECH.value,
            ReportType.GITHUB.value,
            ReportType.AGENT.value,
        ]:
            try:
                async with AsyncSessionLocal() as session:
                    svc = ReportService(session)
                    try:
                        await svc.generate_report(
                            report_type=rtype,
                            report_date=run_date,
                            force=False,
                            user_id=None,
                        )
                        result["generated"] += 1
                    except CandidatesInsufficientError:
                        result["skipped"] += 1
                        log.info(
                            "report.skip_insufficient",
                            report_type=rtype,
                            date=str(run_date),
                        )
            except Exception as exc:
                result["failed"] += 1
                log.exception(
                    "report.generate_failed",
                    report_type=rtype,
                    date=str(run_date),
                    error=str(exc),
                )
        return result

    try:
        try:
            return asyncio.run(_run())
        finally:
            asyncio.run(engine.dispose())
    except Exception as exc:
        log.exception("report.generate_daily_reports.failed", error=str(exc))
        raise self.retry(exc=exc) from exc

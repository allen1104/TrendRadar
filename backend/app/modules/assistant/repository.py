"""assistant 数据访问层。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assistant.model import AssistantMessage, AssistantThread


class AssistantThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(AssistantThread).where(AssistantThread.is_deleted.is_(False))

    async def get_for_user(self, user_id: int, thread_id: int) -> AssistantThread | None:
        return (
            await self.session.execute(
                self._base().where(
                    AssistantThread.id == thread_id,
                    AssistantThread.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def get(self, thread_id: int) -> AssistantThread | None:
        return (
            await self.session.execute(
                self._base().where(AssistantThread.id == thread_id)
            )
        ).scalar_one_or_none()

    async def list_for_user_event(
        self, user_id: int, event_id: int
    ) -> Sequence[AssistantThread]:
        return list(
            (
                await self.session.execute(
                    self._base()
                    .where(
                        AssistantThread.user_id == user_id,
                        AssistantThread.event_id == event_id,
                    )
                    .order_by(
                        AssistantThread.last_message_at.desc().nullslast(),
                        AssistantThread.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )

    async def count_user_threads(self, user_id: int) -> int:
        from sqlalchemy import func

        return int(
            (
                await self.session.execute(
                    select(func.count(AssistantThread.id)).where(
                        AssistantThread.user_id == user_id,
                        AssistantThread.is_deleted.is_(False),
                    )
                )
            ).scalar()
            or 0
        )

    async def create(self, **fields: Any) -> AssistantThread:
        t = AssistantThread(**fields)
        self.session.add(t)
        await self.session.flush()
        return t

    async def save(self, thread: AssistantThread) -> None:
        await self.session.flush()

    async def touch(
        self,
        thread_id: int,
        *,
        title: str | None = None,
        message_count_delta: int = 0,
        cost_delta: float = 0.0,
        last_message_at: Any = None,
    ) -> None:
        values: dict[str, Any] = {}
        if title is not None:
            values["title"] = title
        if message_count_delta:
            # GREATEST(0, ...) 兜底，避免负数
            from sqlalchemy import func

            values["message_count"] = func.greatest(
                0, AssistantThread.message_count + message_count_delta
            )
        if cost_delta:
            values["total_cost_usd"] = AssistantThread.total_cost_usd + cost_delta
        if last_message_at is not None:
            values["last_message_at"] = last_message_at
        if not values:
            return
        await self.session.execute(
            update(AssistantThread)
            .where(AssistantThread.id == thread_id, AssistantThread.is_deleted.is_(False))
            .values(**values)
        )

    async def soft_delete(self, thread: AssistantThread) -> None:
        thread.is_deleted = True
        await self.session.flush()

    async def soft_delete_cascade(self, thread_id: int) -> int:
        """软删 thread 时同步软删其所有未删 message。返回受影响 message 数。"""
        thread = await self.get(thread_id)
        if thread is None:
            return 0
        thread.is_deleted = True
        result = await self.session.execute(
            update(AssistantMessage)
            .where(
                AssistantMessage.thread_id == thread_id,
                AssistantMessage.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        return result.rowcount or 0


class AssistantMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base(self):
        return select(AssistantMessage).where(AssistantMessage.is_deleted.is_(False))

    async def get(self, message_id: int) -> AssistantMessage | None:
        return (
            await self.session.execute(
                self._base().where(AssistantMessage.id == message_id)
            )
        ).scalar_one_or_none()

    async def get_for_user_thread(
        self, user_id: int, thread_id: int, message_id: int
    ) -> AssistantMessage | None:
        """取一条属于某 user 的 thread 内的 message（防越权）。"""
        from app.modules.assistant.model import AssistantThread

        return (
            await self.session.execute(
                select(AssistantMessage)
                .join(AssistantThread, AssistantThread.id == AssistantMessage.thread_id)
                .where(
                    AssistantMessage.id == message_id,
                    AssistantMessage.thread_id == thread_id,
                    AssistantThread.user_id == user_id,
                    AssistantMessage.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()

    async def list_for_thread(self, thread_id: int) -> Sequence[AssistantMessage]:
        return list(
            (
                await self.session.execute(
                    self._base()
                    .where(AssistantMessage.thread_id == thread_id)
                    .order_by(AssistantMessage.created_at, AssistantMessage.id)
                )
            )
            .scalars()
            .all()
        )

    async def create(self, **fields: Any) -> AssistantMessage:
        m = AssistantMessage(**fields)
        self.session.add(m)
        await self.session.flush()
        return m

    async def save(self, msg: AssistantMessage) -> None:
        await self.session.flush()

    async def update_content_incremental(
        self,
        message_id: int,
        *,
        content: str | None = None,
        citations: list[dict[str, Any]] | None = None,
        status: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        cost_usd: float | None = None,
        latency_ms: int | None = None,
        model_alias: str | None = None,
        error_message: str | None = None,
    ) -> None:
        values: dict[str, Any] = {}
        if content is not None:
            values["content"] = content
        if citations is not None:
            values["citations"] = citations
        if status is not None:
            values["status"] = status
        if prompt_tokens is not None:
            values["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            values["completion_tokens"] = completion_tokens
        if cost_usd is not None:
            values["cost_usd"] = cost_usd
        if latency_ms is not None:
            values["latency_ms"] = latency_ms
        if model_alias is not None:
            values["model_alias"] = model_alias
        if error_message is not None:
            values["error_message"] = error_message
        if not values:
            return
        await self.session.execute(
            update(AssistantMessage)
            .where(AssistantMessage.id == message_id, AssistantMessage.is_deleted.is_(False))
            .values(**values)
        )

    async def set_feedback(self, message_id: int, feedback: str | None) -> None:
        await self.session.execute(
            update(AssistantMessage)
            .where(AssistantMessage.id == message_id, AssistantMessage.is_deleted.is_(False))
            .values(feedback=feedback)
        )

    async def soft_delete(self, msg: AssistantMessage) -> None:
        msg.is_deleted = True
        await self.session.flush()

    async def soft_delete_id(self, message_id: int) -> int:
        result = await self.session.execute(
            update(AssistantMessage)
            .where(
                AssistantMessage.id == message_id,
                AssistantMessage.is_deleted.is_(False),
            )
            .values(is_deleted=True)
        )
        return result.rowcount or 0

    async def count_assistant_turns(self, thread_id: int) -> int:
        """统计该 thread 内 ASSISTANT 消息数（用于轮数上限）。"""
        from sqlalchemy import func

        from app.modules.assistant.enums import MessageRole

        return int(
            (
                await self.session.execute(
                    select(func.count(AssistantMessage.id)).where(
                        AssistantMessage.thread_id == thread_id,
                        AssistantMessage.role == MessageRole.ASSISTANT.value,
                        AssistantMessage.is_deleted.is_(False),
                    )
                )
            ).scalar()
            or 0
        )
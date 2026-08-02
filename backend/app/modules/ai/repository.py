"""ai-engine 数据访问层。"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.model import (
    AIModel,
    AIProvider,
    EventAnalysis,
    PromptTemplate,
)


class AIProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, provider_id: int) -> AIProvider | None:
        return await self.session.get(AIProvider, provider_id)

    async def get_by_name(self, name: str) -> AIProvider | None:
        result = await self.session.execute(
            select(AIProvider).where(
                AIProvider.is_deleted.is_(False), AIProvider.name == name
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self, *, include_disabled: bool = True
    ) -> list[AIProvider]:
        stmt = select(AIProvider).where(AIProvider.is_deleted.is_(False))
        if not include_disabled:
            stmt = stmt.where(AIProvider.enabled.is_(True))
        stmt = stmt.order_by(AIProvider.id.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> AIProvider:
        provider = AIProvider(**kwargs)
        self.session.add(provider)
        await self.session.flush()
        return provider

    async def soft_delete(self, provider: AIProvider) -> None:
        provider.is_deleted = True
        await self.session.flush()

    async def count_enabled_models(self, provider_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(AIModel).where(
                AIModel.is_deleted.is_(False),
                AIModel.provider_id == provider_id,
                AIModel.enabled.is_(True),
            )
        )
        return int(result.scalar_one() or 0)


class AIModelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, model_id: int) -> AIModel | None:
        return await self.session.get(AIModel, model_id)

    async def get_by_alias(self, alias: str) -> AIModel | None:
        result = await self.session.execute(
            select(AIModel).where(
                AIModel.is_deleted.is_(False), AIModel.alias == alias
            )
        )
        return result.scalar_one_or_none()

    async def list(self) -> Sequence[AIModel]:
        result = await self.session.execute(
            select(AIModel)
            .where(AIModel.is_deleted.is_(False))
            .order_by(AIModel.id.asc())
        )
        return result.scalars().all()

    async def create(self, **kwargs: Any) -> AIModel:
        model = AIModel(**kwargs)
        self.session.add(model)
        await self.session.flush()
        return model

    async def save(self, model: AIModel) -> None:
        await self.session.flush()

    async def soft_delete(self, model: AIModel) -> None:
        model.is_deleted = True
        await self.session.flush()


class PromptTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, prompt_id: int) -> PromptTemplate | None:
        return await self.session.get(PromptTemplate, prompt_id)

    async def get_active(self, task_key: str) -> PromptTemplate | None:
        result = await self.session.execute(
            select(PromptTemplate).where(
                PromptTemplate.task_key == task_key,
                PromptTemplate.is_active.is_(True),
                PromptTemplate.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self, *, task_key: str | None = None, only_active: bool = False
    ) -> list[PromptTemplate]:
        stmt = select(PromptTemplate).where(PromptTemplate.is_deleted.is_(False))
        if task_key:
            stmt = stmt.where(PromptTemplate.task_key == task_key)
        if only_active:
            stmt = stmt.where(PromptTemplate.is_active.is_(True))
        stmt = stmt.order_by(PromptTemplate.task_key.asc(), PromptTemplate.version.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def next_version(self, task_key: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(PromptTemplate.version), 0)).where(
                PromptTemplate.task_key == task_key,
                PromptTemplate.is_deleted.is_(False),
            )
        )
        return int(result.scalar_one()) + 1

    async def create(self, **kwargs: Any) -> PromptTemplate:
        prompt = PromptTemplate(**kwargs)
        self.session.add(prompt)
        await self.session.flush()
        return prompt


class EventAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_event(self, event_id: int) -> EventAnalysis | None:
        result = await self.session.execute(
            select(EventAnalysis).where(
                EventAnalysis.event_id == event_id,
                EventAnalysis.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, event_id: int, result_obj: Any, model_alias: str, prompt_version: int) -> EventAnalysis:
        existing = await self.get_by_event(event_id)
        if existing is None:
            row = EventAnalysis(
                event_id=event_id,
                model_alias=model_alias,
                prompt_version=prompt_version,
                **result_obj.model_dump(),
            )
            self.session.add(row)
        else:
            for k, v in result_obj.model_dump().items():
                setattr(existing, k, v)
            existing.model_alias = model_alias
            existing.prompt_version = prompt_version
            existing.analyzed_at = datetime.utcnow()
            row = existing
        await self.session.flush()
        await self.session.commit()
        return row

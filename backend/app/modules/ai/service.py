"""ai-engine 业务层。

所有 LLM 调用都从 LLMGateway 走；业务模块禁止直接 import Provider SDK。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.modules.ai.enums import CallStatus, ModelType, ProviderKey, TaskKey
from app.modules.ai.exceptions import (
    EmbeddingDimRequiredError,
    LLMUnavailableError,
    ModelAliasExistsError,
    ModelNotFoundError,
    ProviderInUseError,
    ProviderNameExistsError,
    ProviderNotFoundError,
    ProviderNotRegisteredError,
    PromptNotConfiguredError,
    PromptNotFoundError,
    PromptReadonlyError,
)
from app.modules.ai.gateway.base import list_registered_providers
from app.modules.ai.gateway.gateway import LLMGateway
from app.modules.ai.model import (
    AICallLog,
    AIModel,
    AIProvider,
    EventAnalysis,
    PromptTemplate,
)
from app.modules.ai.repository import (
    AIModelRepository,
    AIProviderRepository,
    EventAnalysisRepository,
    PromptTemplateRepository,
)
from app.modules.ai.schema import (
    CallLogItem,
    CostSeriesPoint,
    CostStatsResponse,
    EventAnalysisResult,
    ModelCreateRequest,
    ModelResponse,
    ModelUpdateRequest,
    ProviderCreateRequest,
    ProviderListItem,
    ProviderResponse,
    ProviderTestResponse,
    PromptCreateRequest,
    PromptDryRunRequest,
    PromptDryRunResponse,
    PromptListItem,
    PromptResponse,
    PromptUpdateRequest,
    RegisteredProviderInfo,
)

log = structlog.get_logger()


# ============================================================ Provider


class ProviderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AIProviderRepository(session)

    async def list(self) -> list[ProviderListItem]:
        providers = await self.repo.list()
        items: list[ProviderListItem] = []
        for p in providers:
            count = await self.repo.count_enabled_models(p.id)
            items.append(
                ProviderListItem(
                    id=p.id,
                    provider_key=p.provider_key,  # type: ignore[arg-type]
                    name=p.name,
                    base_url=p.base_url,
                    api_key=mask_secret(p.api_key) if p.api_key else None,
                    extra_config=p.extra_config,
                    enabled=p.enabled,
                    model_count=count,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                )
            )
        return items

    async def create(self, payload: ProviderCreateRequest) -> ProviderResponse:
        # 校验 provider_key 已注册
        try:
            from app.modules.ai.gateway.base import get_provider_class

            get_provider_class(payload.provider_key.value)
        except KeyError as exc:
            raise ProviderNotRegisteredError(
                f"provider_key '{payload.provider_key.value}' 未在代码中注册"
            ) from exc

        if await self.repo.get_by_name(payload.name):
            raise ProviderNameExistsError

        api_key_enc = encrypt_secret(payload.api_key) if payload.api_key else None
        provider = await self.repo.create(
            provider_key=payload.provider_key.value,
            name=payload.name,
            base_url=payload.base_url,
            api_key=api_key_enc,
            extra_config=payload.extra_config,
            enabled=payload.enabled,
        )
        log.info("ai.provider.created", id=provider.id, name=provider.name)
        return await self._to_response(provider)

    async def update(self, provider_id: int, payload: ProviderCreateRequest) -> ProviderResponse:
        provider = await self.repo.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError
        if await self.repo.get_by_name(payload.name) and (await self.repo.get_by_name(payload.name)).id != provider_id:
            raise ProviderNameExistsError
        provider.name = payload.name
        provider.base_url = payload.base_url
        provider.extra_config = payload.extra_config
        provider.enabled = payload.enabled
        if payload.api_key:
            provider.api_key = encrypt_secret(payload.api_key)
        await self.session.flush()
        return await self._to_response(provider)

    async def delete(self, provider_id: int) -> None:
        provider = await self.repo.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError
        if await self.repo.count_enabled_models(provider_id) > 0:
            raise ProviderInUseError
        await self.repo.soft_delete(provider)

    async def test_connection(self, provider_id: int) -> ProviderTestResponse:
        """调 Provider 的 /models 验证连通性。"""
        from app.modules.ai.gateway.base import get_provider_class

        provider = await self.repo.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError
        try:
            cls = get_provider_class(provider.provider_key)
        except KeyError as exc:
            raise ProviderNotRegisteredError(
                f"provider_key '{provider.provider_key}' 未注册"
            ) from exc

        if provider.provider_key == ProviderKey.LOCAL_EMBEDDING.value:
            instance = cls(dim=provider.extra_config.get("dim", 1024))  # type: ignore[abstract]
        else:
            instance = cls(  # type: ignore[abstract]
                base_url=provider.base_url,
                api_key=provider.api_key,
                timeout=10,
            )

        import time

        start = time.perf_counter()
        try:
            models = await instance.list_remote_models()
            latency = int((time.perf_counter() - start) * 1000)
            return ProviderTestResponse(
                success=True,
                latency_ms=latency,
                message="连接正常",
                available_models=models[:50],
            )
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - start) * 1000)
            return ProviderTestResponse(
                success=False,
                latency_ms=latency,
                message=f"连接失败：{exc.__class__.__name__}: {exc}",
                available_models=[],
            )

    async def list_registered(self) -> list[RegisteredProviderInfo]:
        """列出代码里注册的可选 Provider（给新建下拉用）。"""
        from app.modules.ai.providers.local_embedding import LocalEmbeddingProvider
        from app.modules.ai.providers.openai_compatible import OpenAICompatibleProvider

        info_map: dict[str, RegisteredProviderInfo] = {
            OpenAICompatibleProvider.provider_key: RegisteredProviderInfo(
                provider_key=OpenAICompatibleProvider.provider_key,
                display_name="OpenAI 兼容",
                region="GLOBAL",
                config_schema={
                    "type": "object",
                    "properties": {
                        "base_url": {"type": "string"},
                        "api_key": {"type": "string"},
                        "timeout": {"type": "integer", "default": 120},
                    },
                    "required": ["base_url", "api_key"],
                },
            ),
            "anthropic": RegisteredProviderInfo(
                provider_key="anthropic",
                display_name="Anthropic Claude",
                region="GLOBAL",
                config_schema={"type": "object", "properties": {}},
            ),
            "gemini": RegisteredProviderInfo(
                provider_key="gemini",
                display_name="Google Gemini",
                region="GLOBAL",
                config_schema={"type": "object", "properties": {}},
            ),
            LocalEmbeddingProvider.provider_key: RegisteredProviderInfo(
                provider_key=LocalEmbeddingProvider.provider_key,
                display_name="本地 bge-m3 (embedding only)",
                region="LOCAL",
                config_schema={
                    "type": "object",
                    "properties": {"dim": {"type": "integer", "default": 1024}},
                },
            ),
        }
        # 只返回代码里已注册 @register_provider 的
        registered_keys = {k for k, _ in list_registered_providers()}
        return [v for v in info_map.values() if v.provider_key in registered_keys]

    async def _to_response(self, p: AIProvider) -> ProviderResponse:
        return ProviderResponse(
            id=p.id,
            provider_key=p.provider_key,  # type: ignore[arg-type]
            name=p.name,
            base_url=p.base_url,
            api_key=mask_secret(p.api_key) if p.api_key else None,
            extra_config=p.extra_config,
            enabled=p.enabled,
            model_count=await self.repo.count_enabled_models(p.id),
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


# ============================================================ Model


class ModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AIModelRepository(session)
        self.providers = AIProviderRepository(session)

    async def list(self) -> list[ModelResponse]:
        rows = await self.repo.list()
        # 一次性把 provider 名查出来，避免 N+1
        provider_ids = {m.provider_id for m in rows}
        provider_map: dict[int, str] = {}
        for pid in provider_ids:
            p = await self.providers.get(pid)
            if p:
                provider_map[pid] = p.name
        return [
            ModelResponse(
                id=m.id,
                provider_id=m.provider_id,
                provider_name=provider_map.get(m.provider_id, ""),
                model_name=m.model_name,
                alias=m.alias,
                model_type=m.model_type,  # type: ignore[arg-type]
                context_window=m.context_window,
                max_output_tokens=m.max_output_tokens,
                supports_json_schema=m.supports_json_schema,
                price_input_per_1m=float(m.price_input_per_1m),
                price_output_per_1m=float(m.price_output_per_1m),
                embedding_dim=m.embedding_dim,
                enabled=m.enabled,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in rows
        ]

    async def create(self, payload: ModelCreateRequest) -> ModelResponse:
        if await self.repo.get_by_alias(payload.alias):
            raise ModelAliasExistsError
        if (await self.providers.get(payload.provider_id)) is None:
            raise ProviderNotFoundError
        if payload.model_type == ModelType.EMBEDDING and payload.embedding_dim is None:
            raise EmbeddingDimRequiredError

        model = await self.repo.create(
            provider_id=payload.provider_id,
            model_name=payload.model_name,
            alias=payload.alias,
            model_type=payload.model_type.value,
            context_window=payload.context_window,
            max_output_tokens=payload.max_output_tokens,
            supports_json_schema=payload.supports_json_schema,
            price_input_per_1m=payload.price_input_per_1m,
            price_output_per_1m=payload.price_output_per_1m,
            embedding_dim=payload.embedding_dim,
            enabled=payload.enabled,
        )
        return (await self.list())[next(
            i for i, m in enumerate(await self.list()) if m.id == model.id
        )]

    async def update(self, model_id: int, payload: ModelUpdateRequest) -> ModelResponse:
        model = await self.repo.get(model_id)
        if model is None:
            raise ModelNotFoundError
        for field in [
            "model_name",
            "context_window",
            "max_output_tokens",
            "supports_json_schema",
            "price_input_per_1m",
            "price_output_per_1m",
            "embedding_dim",
            "enabled",
        ]:
            v = getattr(payload, field)
            if v is not None:
                setattr(model, field, v)
        await self.repo.save(model)
        items = await self.list()
        return next(m for m in items if m.id == model_id)

    async def delete(self, model_id: int) -> None:
        model = await self.repo.get(model_id)
        if model is None:
            raise ModelNotFoundError
        await self.repo.soft_delete(model)


# ============================================================ Prompt


class PromptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PromptTemplateRepository(session)
        self.models = AIModelRepository(session)

    async def list(self, task_key: str | None = None, only_active: bool = False) -> list[PromptListItem]:
        rows = await self.repo.list(task_key=task_key, only_active=only_active)
        return [
            PromptListItem(
                id=p.id,
                task_key=p.task_key,  # type: ignore[arg-type]
                version=p.version,
                model_alias=p.model_alias,
                temperature=p.temperature,
                is_active=p.is_active,
                note=p.note,
                variables=p.variables,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in rows
        ]

    async def get(self, prompt_id: int) -> PromptResponse:
        p = await self.repo.get(prompt_id)
        if p is None:
            raise PromptNotFoundError
        return self._to_response(p)

    async def create(self, payload: PromptCreateRequest, *, created_by: int | None) -> PromptResponse:
        version = await self.repo.next_version(payload.task_key.value)
        prompt = await self.repo.create(
            task_key=payload.task_key.value,
            version=version,
            system_prompt=payload.system_prompt,
            user_prompt=payload.user_prompt,
            variables=payload.variables,
            model_alias=payload.model_alias,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            is_active=False,
            note=payload.note,
            created_by=created_by,
        )
        log.info(
            "ai.prompt.created",
            id=prompt.id, task_key=prompt.task_key, version=prompt.version
        )
        return self._to_response(prompt)

    async def update(self, prompt_id: int, payload: PromptUpdateRequest) -> PromptResponse:
        p = await self.repo.get(prompt_id)
        if p is None:
            raise PromptNotFoundError
        if p.is_active:
            raise PromptReadonlyError
        for f in [
            "system_prompt",
            "user_prompt",
            "variables",
            "model_alias",
            "temperature",
            "max_tokens",
            "note",
        ]:
            v = getattr(payload, f)
            if v is not None:
                setattr(p, f, v)
        await self.session.flush()
        return self._to_response(p)

    async def activate(self, prompt_id: int) -> PromptResponse:
        """把某版本激活，自动把同 task_key 的其他版本置为非激活。"""
        p = await self.repo.get(prompt_id)
        if p is None:
            raise PromptNotFoundError
        # 同 task_key 其他版本置为非激活
        others = await self.repo.list(task_key=p.task_key, only_active=True)
        for o in others:
            if o.id != p.id:
                o.is_active = False
        p.is_active = True
        await self.session.flush()
        # flush 后属性过期，refresh 一下再读
        await self.session.refresh(p)
        log.info("ai.prompt.activated", id=p.id, task_key=p.task_key, version=p.version)
        return self._to_response(p)

    async def dry_run(
        self, prompt_id: int, payload: PromptDryRunRequest
    ) -> PromptDryRunResponse:
        p = await self.repo.get(prompt_id)
        if p is None:
            raise PromptNotFoundError
        variables = payload.variables or {}
        # 简单变量提取校验
        from app.modules.ai.gateway.gateway import _render

        rendered_system = _render(p.system_prompt, variables)
        rendered_user = _render(p.user_prompt, variables)

        # 真正调一次 LLM
        gateway = LLMGateway(self.session)
        from app.modules.ai.schema import EventAnalysisResult  # noqa: F401

        # 简化：若 task_key = event_analysis，用 EventAnalysisResult 强约束
        response_schema = None
        if p.task_key == TaskKey.EVENT_ANALYSIS.value:
            response_schema = EventAnalysisResult
        try:
            resp = await gateway.call(
                task_key=p.task_key,
                variables=variables,
                target_type=payload.target_type,
                target_id=payload.target_id,
                response_schema=response_schema,
            )
            output = resp.parsed.model_dump() if resp.parsed else resp.content
            return PromptDryRunResponse(
                rendered_system_prompt=rendered_system,
                rendered_user_prompt=rendered_user,
                output=output,
                model_alias=p.model_alias or "(default)",
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                cost_usd=0.0,  # gateway 已经记到 log
                latency_ms=resp.latency_ms,
                parse_success=resp.parsed is not None,
            )
        except LLMUnavailableError:
            # 仅返回渲染结果，不调 LLM
            return PromptDryRunResponse(
                rendered_system_prompt=rendered_system,
                rendered_user_prompt=rendered_user,
                output="(LLM 不可用，仅返回渲染结果)",
                model_alias=p.model_alias or "(default)",
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                latency_ms=0,
                parse_success=False,
            )

    def _to_response(self, p: PromptTemplate) -> PromptResponse:
        return PromptResponse(
            id=p.id,
            task_key=p.task_key,  # type: ignore[arg-type]
            version=p.version,
            system_prompt=p.system_prompt,
            user_prompt=p.user_prompt,
            variables=p.variables,
            model_alias=p.model_alias,
            temperature=p.temperature,
            max_tokens=p.max_tokens,
            is_active=p.is_active,
            note=p.note,
            created_by=p.created_by,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


# ============================================================ Cost / Log


class CostService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def stats(
        self,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "DAY",
    ) -> CostStatsResponse:
        from sqlalchemy import case

        # 总数
        success_case = case(
            (AICallLog.status == CallStatus.SUCCESS.value, 1),
            else_=0,
        )
        total_stmt = select(
            func.count(AICallLog.id),
            func.coalesce(func.sum(AICallLog.prompt_tokens), 0),
            func.coalesce(func.sum(AICallLog.completion_tokens), 0),
            func.coalesce(func.sum(AICallLog.cost_usd), 0),
            func.coalesce(func.sum(success_case), 0),
        ).where(
            AICallLog.created_at >= start_date,
            AICallLog.created_at < end_date,
            AICallLog.is_deleted.is_(False),
        )
        row = (await self.session.execute(total_stmt)).one()
        total_calls = int(row[0])
        total_prompt = int(row[1])
        total_completion = int(row[2])
        total_cost = float(row[3])
        success = int(row[4])
        success_rate = success / total_calls if total_calls else 0.0

        # 时序
        date_trunc = func.date_trunc(group_by.lower(), AICallLog.created_at)
        series_stmt = (
            select(
                date_trunc.label("key"),
                func.coalesce(func.sum(AICallLog.cost_usd), 0),
                func.count(AICallLog.id),
                func.coalesce(func.sum(AICallLog.prompt_tokens), 0),
                func.coalesce(func.sum(AICallLog.completion_tokens), 0),
            )
            .where(
                AICallLog.created_at >= start_date,
                AICallLog.created_at < end_date,
                AICallLog.is_deleted.is_(False),
            )
            .group_by("key")
            .order_by("key")
        )
        series = [
            CostSeriesPoint(
                key=str(r[0]),
                cost_usd=float(r[1]),
                calls=int(r[2]),
                prompt_tokens=int(r[3]),
                completion_tokens=int(r[4]),
            )
            for r in (await self.session.execute(series_stmt)).all()
        ]

        # 按模型
        by_model_stmt = (
            select(
                AICallLog.model_alias,
                func.coalesce(func.sum(AICallLog.cost_usd), 0),
                func.count(AICallLog.id),
                func.coalesce(func.sum(AICallLog.prompt_tokens), 0),
                func.coalesce(func.sum(AICallLog.completion_tokens), 0),
            )
            .where(
                AICallLog.created_at >= start_date,
                AICallLog.created_at < end_date,
                AICallLog.is_deleted.is_(False),
            )
            .group_by(AICallLog.model_alias)
            .order_by(func.sum(AICallLog.cost_usd).desc())
        )
        by_model = [
            CostSeriesPoint(
                key=r[0], cost_usd=float(r[1]), calls=int(r[2]),
                prompt_tokens=int(r[3]), completion_tokens=int(r[4]),
            )
            for r in (await self.session.execute(by_model_stmt)).all()
        ]

        # 按任务
        by_task_stmt = by_model_stmt.with_only_columns(
            AICallLog.task_key,
            func.coalesce(func.sum(AICallLog.cost_usd), 0),
            func.count(AICallLog.id),
            func.coalesce(func.sum(AICallLog.prompt_tokens), 0),
            func.coalesce(func.sum(AICallLog.completion_tokens), 0),
        ).group_by(AICallLog.task_key).order_by(func.sum(AICallLog.cost_usd).desc())
        by_task = [
            CostSeriesPoint(
                key=r[0], cost_usd=float(r[1]), calls=int(r[2]),
                prompt_tokens=int(r[3]), completion_tokens=int(r[4]),
            )
            for r in (await self.session.execute(by_task_stmt)).all()
        ]

        return CostStatsResponse(
            total_cost_usd=total_cost,
            total_calls=total_calls,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            success_rate=success_rate,
            series=series,
            by_model=by_model,
            by_task=by_task,
        )

    async def list_logs(
        self,
        *,
        page: int,
        size: int,
        task_key: str | None,
        model_alias: str | None,
        status: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> tuple[list[CallLogItem], int]:
        stmt = select(AICallLog).where(AICallLog.is_deleted.is_(False))
        if task_key:
            stmt = stmt.where(AICallLog.task_key == task_key)
        if model_alias:
            stmt = stmt.where(AICallLog.model_alias == model_alias)
        if status:
            stmt = stmt.where(AICallLog.status == status)
        if start_date:
            stmt = stmt.where(AICallLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AICallLog.created_at < end_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        rows = (
            await self.session.execute(
                stmt.order_by(AICallLog.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).scalars().all()
        items = [
            CallLogItem(
                id=r.id,
                trace_id=r.trace_id,
                task_key=r.task_key,
                model_alias=r.model_alias,
                prompt_version=r.prompt_version,
                target_type=r.target_type,
                target_id=r.target_id,
                user_id=r.user_id,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                cost_usd=float(r.cost_usd),
                latency_ms=r.latency_ms,
                status=r.status,  # type: ignore[arg-type]
                retry_count=r.retry_count,
                error_message=r.error_message,
                created_at=r.created_at,
            )
            for r in rows
        ]
        return items, total

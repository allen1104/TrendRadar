"""LLM 统一网关。

调用流程（见 doc/SPEC-ai-engine.md）：
  ① 查 prompt_template WHERE task_key AND is_active
  ② Jinja2 渲染 user_prompt
  ③ 解析模型：prompt.model_alias → system_config 默认 → 降级链
  ④ 构造降级链：[主模型] + system_config.ai_fallback_chain
  ⑤ 对链上每个模型依次尝试：chat → 解析 schema → 失败降级
  ⑥ 写 ai_call_log
  ⑦ 全链失败 → 抛 LLMUnavailableError
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from jinja2 import Environment, StrictUndefined, TemplateError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.redis import RedisKey, redis_client
from app.modules.ai.enums import CallStatus, ModelType, ProviderKey, TaskKey
from app.modules.ai.exceptions import (
    LLMUnavailableError,
    ModelNotFoundError,
    PromptNotConfiguredError,
    ProviderNotRegisteredError,
)
from app.modules.ai.gateway.base import get_provider_class
from app.modules.ai.gateway.types import LLMRequest, LLMResponse
from app.modules.ai.model import AICallLog, AIModel, AIProvider, PromptTemplate
from sqlalchemy import select
from sqlalchemy.orm import selectinload

log = structlog.get_logger()

_jinja = Environment(undefined=StrictUndefined, autoescape=False)


def _render(template: str, variables: dict[str, Any]) -> str:
    try:
        return _jinja.from_string(template).render(**variables)
    except TemplateError as exc:
        raise ValueError(f"Prompt 渲染失败：{exc}") from exc


class LLMGateway:
    """唯一对外入口。业务代码只能 import 这个类。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ============================================================ chat

    async def call(
        self,
        task_key: str,
        variables: dict[str, Any],
        *,
        target_type: str | None = None,
        target_id: int | None = None,
        user_id: int | None = None,
        fallback_chain: list[str] | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """主入口：完成 prompt 查找 + 渲染 + 模型解析 + 降级 + 重试 + 记账。"""
        prompt = await self._get_active_prompt(task_key)
        chain = await self._build_chain(prompt, fallback_chain)

        rendered_system = _render(prompt.system_prompt, variables)
        rendered_user = _render(prompt.user_prompt, variables)
        messages = [
            {"role": "system", "content": rendered_system},
            {"role": "user", "content": rendered_user},
        ]

        last_error: Exception | None = None
        for idx, model_alias in enumerate(chain):
            is_fallback = idx > 0
            try:
                resp = await self._call_one(
                    model_alias=model_alias,
                    messages=messages,
                    temperature=prompt.temperature,
                    max_tokens=prompt.max_tokens,
                    response_schema=response_schema,
                    task_key=task_key,
                    prompt_version=prompt.version,
                    target_type=target_type,
                    target_id=target_id,
                    user_id=user_id,
                )
                if is_fallback:
                    log.info("llm.fallback_success", task_key=task_key, model=model_alias)
                return resp
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning(
                    "llm.call_failed",
                    task_key=task_key,
                    model=model_alias,
                    is_fallback=is_fallback,
                    error=str(exc),
                )
                if not is_fallback:
                    # 主模型失败也要写一条失败日志
                    await self._log_call(
                        model_alias=model_alias,
                        task_key=task_key,
                        prompt_version=prompt.version,
                        target_type=target_type,
                        target_id=target_id,
                        user_id=user_id,
                        prompt_tokens=0,
                        completion_tokens=0,
                        cost_usd=0.0,
                        latency_ms=0,
                        status=CallStatus.FAILED,
                        error_message=str(exc)[:1000],
                    )
                continue

        raise LLMUnavailableError(
            f"所有模型均不可用，最后错误：{last_error}",
        )

    async def _call_one(
        self,
        *,
        model_alias: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
        response_schema: type[BaseModel] | None,
        task_key: str,
        prompt_version: int,
        target_type: str | None,
        target_id: int | None,
        user_id: int | None,
    ) -> LLMResponse:
        model = await self._get_model_by_alias(model_alias)
        provider = await self._build_provider(model.provider)

        request = LLMRequest(
            messages=messages,
            model=model.model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            response_schema=response_schema,
            supports_json_schema=bool(model.supports_json_schema),
        )

        # 指数退避重试 3 次（2s/6s/18s）
        retryer = AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=18),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        )
        retry_count = 0
        try:
            async for attempt in retryer:
                with attempt:
                    if retry_count > 0:
                        retry_count = attempt.retry_state.attempt_number
                    resp = await provider.chat(request)
        except RetryError as exc:
            raise exc.last_attempt.exception() if exc.last_attempt else exc  # type: ignore[misc]

        cost = float(model.price_input_per_1m or 0) * resp.prompt_tokens / 1e6 + float(model.price_output_per_1m or 0) * resp.completion_tokens / 1e6
        await self._log_call(
            model_alias=model.alias,
            task_key=task_key,
            prompt_version=prompt_version,
            target_type=target_type,
            target_id=target_id,
            user_id=user_id,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            cost_usd=float(cost),
            latency_ms=resp.latency_ms,
            status=CallStatus.SUCCESS,
            model_id=model.id,
        )
        return resp

    # ============================================================ embed

    async def embed(
        self,
        texts: list[str],
        *,
        model_alias: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
    ) -> list[list[float]]:
        """向量化。优先用本地 embedding（零成本）。"""
        alias = model_alias or "local-bge-m3"  # 默认走本地
        model = await self._get_model_by_alias(alias)
        if model.model_type != ModelType.EMBEDDING.value:
            raise ValueError(f"模型 {alias} 不是 EMBEDDING 类型")
        provider = await self._build_provider(model.provider)
        return await provider.embed(texts, model.model_name)

    # ============================================================ 辅助

    async def _get_active_prompt(self, task_key: str) -> PromptTemplate:
        result = await self.session.execute(
            select(PromptTemplate).where(
                PromptTemplate.is_active.is_(True),
                PromptTemplate.is_deleted.is_(False),
                PromptTemplate.task_key == task_key,
            )
        )
        prompt = result.scalar_one_or_none()
        if prompt is None:
            raise PromptNotConfiguredError
        return prompt

    async def _build_chain(self, prompt: PromptTemplate, fallback: list[str] | None) -> list[str]:
        # 主模型：prompt.model_alias 优先；否则从 system_config 读
        primary = prompt.model_alias or "default-chat"
        if fallback is not None:
            return [primary, *[a for a in fallback if a != primary]]
        # 不传 fallback 时，主模型单独（不强行套默认降级链，避免误用）
        return [primary]

    async def _get_model_by_alias(self, alias: str) -> AIModel:
        # eager load provider — 否则 _build_provider 同步访问 model.provider 时
        # 触发 lazy load，在 Celery 异步上下文里报 greenlet_spawn。
        result = await self.session.execute(
            select(AIModel)
            .options(selectinload(AIModel.provider))
            .where(
                AIModel.is_deleted.is_(False),
                AIModel.enabled.is_(True),
                AIModel.alias == alias,
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ModelNotFoundError(f"模型 '{alias}' 未启用或不存在")
        return model

    async def _build_provider(self, provider: AIProvider) -> Any:
        try:
            cls = get_provider_class(provider.provider_key)
        except KeyError as exc:
            raise ProviderNotRegisteredError(
                f"Provider '{provider.provider_key}' 未注册"
            ) from exc
        if provider.provider_key == ProviderKey.LOCAL_EMBEDDING.value:
            return cls(dim=provider.extra_config.get("dim", 1024))  # type: ignore[abstract]
        return cls(
            base_url=provider.base_url,
            api_key=provider.api_key,
            timeout=int(provider.extra_config.get("timeout", 120)),
        )

    async def _log_call(
        self,
        *,
        model_alias: str,
        task_key: str,
        prompt_version: int | None,
        target_type: str | None,
        target_id: int | None,
        user_id: int | None,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        status: str,
        model_id: int | None = None,
        error_message: str | None = None,
        retry_count: int = 0,
    ) -> None:
        try:
            log_row = AICallLog(
                trace_id=uuid.uuid4().hex,
                task_key=task_key,
                model_id=model_id,
                model_alias=model_alias,
                prompt_version=prompt_version,
                target_type=target_type,
                target_id=target_id,
                user_id=user_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                status=status,
                retry_count=retry_count,
                error_message=error_message,
            )
            self.session.add(log_row)
            await self.session.flush()
        except Exception as exc:  # noqa: BLE001
            # 记账失败不能把整个 session 搞挂。回滚这一行，保留 session 可用
            try:
                await self.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            log.error("llm.log_failed", error=str(exc))


# 可重试的瞬时错误
_RETRYABLE = (TimeoutError, ConnectionError, OSError)


# 触发 import 注册 Provider 子类
def _ensure_providers_registered() -> None:
    """显式触发所有 provider 模块的 import，让装饰器跑起来。"""
    from app.modules.ai.providers import (  # noqa: F401
        local_embedding,
        openai_compatible,
    )


_ensure_providers_registered()

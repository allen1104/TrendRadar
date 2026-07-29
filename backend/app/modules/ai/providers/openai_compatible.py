"""OpenAI 兼容协议 Provider。

覆盖：OpenAI 官方、DeepSeek、Qwen、Kimi，以及本地 vLLM / Ollama / LM Studio。
任意外部配置 base_url + api_key 都走这个实现。
"""

import time

import httpx
import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.security import decrypt_secret
from app.modules.ai.gateway.base import LLMProvider, register_provider
from app.modules.ai.gateway.types import LLMRequest, LLMResponse

log = structlog.get_logger()


@register_provider
class OpenAICompatibleProvider(LLMProvider):
    """通过 OpenAI 协议调任意兼容端点。"""

    provider_key = "openai_compatible"

    def __init__(self, base_url: str | None, api_key: str | None, *, timeout: int = 120) -> None:
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        # api_key 入库是加密的，这里解密
        self.api_key = decrypt_secret(api_key) if api_key else "no-key"
        self.timeout = timeout
        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
            max_retries=0,  # 重试由 Gateway 层做
        )

    async def chat(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        kwargs: dict = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        # 结构化输出优先用 response_format（OpenAI JSON schema）
        if request.response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema.__name__,
                    "schema": request.response_schema.model_json_schema(),
                    "strict": True,
                },
            }
        elif "json" in (request.extra.get("force_json") or ""):
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0]
        content = choice.message.content or ""

        parsed = None
        if request.response_schema is not None:
            try:
                parsed = request.response_schema.model_validate_json(content)
            except ValidationError as exc:
                raise ValueError(
                    f"LLM output failed schema validation: {exc.error_count()} errors"
                ) from exc

        usage = resp.usage
        return LLMResponse(
            content=content,
            parsed=parsed,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "stop",
            raw=resp,
        )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        # 走 OpenAI 协议的 embed 接口
        resp = await self._client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        # 真实价格在 AIModel 表里。这里只用于非数据库场景的兜底。
        return 0.0

    async def list_remote_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if r.status_code == 200:
                    data = r.json()
                    return [m["id"] for m in data.get("data", []) if "id" in m]
        except Exception as exc:  # noqa: BLE001
            log.warning("openai_compatible.list_models_failed", error=str(exc))
        return []

"""OpenAI 兼容协议 Provider。

覆盖：OpenAI 官方、DeepSeek、Qwen、Kimi，以及本地 vLLM / Ollama / LM Studio。
任意外部配置 base_url + api_key 都走这个实现。
"""

import re
import time
from collections.abc import AsyncIterator

import httpx
import structlog
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.core.security import decrypt_secret
from app.modules.ai.gateway.base import LLMProvider, register_provider
from app.modules.ai.gateway.types import LLMRequest, LLMResponse

log = structlog.get_logger()

_CAMEL_KEY_RE = re.compile(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:')
# 抓被 ```json ... ``` 包裹的整块
_MD_BLOCK_RE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
# 剥单独的 ``` 行（无匹配块时回退用）
_MD_FENCE_LINE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*$", re.MULTILINE)


def _strip_markdown_fence(text: str) -> str:
    """剥 markdown 三反引号包裹（DeepSeek/Qwen 经常把 JSON 放在 ```json ... ``` 里）。"""
    if not text or "```" not in text:
        return text
    m = _MD_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    return _MD_FENCE_LINE_RE.sub("", text).strip()


def _normalize_camel_to_snake(text: str) -> str:
    """把 JSON 文本里所有 `"camelCase":` 键替换成 `"snake_case":`。

    模型经常把 snake_case 字段写成 camelCase（DeepSeek / Qwen 常见）。
    只动键名（引号后到冒号前），不动值。
    """
    if not text or "{" not in text:
        return text

    text = _strip_markdown_fence(text)

    def _key(m: re.Match[str]) -> str:
        k = m.group(1)
        if "_" in k:
            return m.group(0)
        # summaryOneLine → summary_one_line（不是 summary_One_Line）
        # 第一步：处理连续大写 + 后面小写（少见）；第二步：小写/数字 → 大写边界
        s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", k)
        s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
        return f'"{s2.lower()}":'

    return _CAMEL_KEY_RE.sub(_key, text)


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
        # 流式 token / latency 缓存（assistant 流式场景使用）
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0
        self._last_latency_ms = 0

    async def chat(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        kwargs: dict = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        # 结构化输出：仅当模型声明支持 OpenAI-style json_schema 时才发 response_format
        # （DeepSeek / 多数 OpenAI 兼容端点不接 json_schema 严格模式，强行发会 400）
        if request.response_schema is not None and request.supports_json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema.__name__,
                    "schema": request.response_schema.model_json_schema(),
                    "strict": True,
                },
            }

        resp = await self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0]
        content = choice.message.content or ""

        parsed = None
        if request.response_schema is not None:
            # 模型经常把 snake_case 字段名写成 camelCase（DeepSeek / Qwen 都常见），
            # 在 parse 前归一化一次。schema 是 Pydantic BaseModel，按字段名再映射回 snake。
            content = _normalize_camel_to_snake(content)
            try:
                parsed = request.response_schema.model_validate_json(content)
            except ValidationError as exc:
                raise ValueError(
                    f"LLM output failed schema validation: {exc.error_count()} errors | "
                    f"content[:300]={content[:300]!r} | errors={exc.errors()[:3]}"
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

    async def stream_chat(self, request: LLMRequest) -> AsyncIterator[str]:
        """流式生成（assistant 模块用）。

        与 chat() 的差异：
          - 不解析 schema（流式场景不需要结构化）
          - 返回 AsyncIterator[str]，每次 yield 一个增量 delta
          - token / latency 由 provider 自己写到 _last_* 属性，service 层读
        """
        kwargs: dict = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},  # 末次 chunk 带回 usage
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        start = time.perf_counter()
        # 结构化输出与流式互斥（OpenAI json_schema 不支持 stream）
        # response_schema 在 service 层就不会传，这里也再保险一次
        if request.response_schema is not None:
            raise ValueError("流式模式不支持 response_schema")

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            # 取 delta content
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
            # 末次 chunk 携带 usage
            if hasattr(chunk, "usage") and chunk.usage is not None:
                self._last_prompt_tokens = int(getattr(chunk.usage, "prompt_tokens", 0) or 0)
                self._last_completion_tokens = int(getattr(chunk.usage, "completion_tokens", 0) or 0)
        self._last_latency_ms = int((time.perf_counter() - start) * 1000)

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
        except Exception as exc:
            log.warning("openai_compatible.list_models_failed", error=str(exc))
        return []

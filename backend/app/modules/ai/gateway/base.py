"""LLM Provider 抽象基类与注册表。"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import ClassVar

from app.modules.ai.gateway.types import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """所有 LLM Provider 必须实现。注册用 @register_provider 装饰器。"""

    provider_key: ClassVar[str] = ""  # 子类必须覆盖

    @abstractmethod
    async def chat(self, request: LLMRequest) -> LLMResponse: ...

    @abstractmethod
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...

    @abstractmethod
    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float: ...

    @abstractmethod
    async def list_remote_models(self) -> list[str]:
        """通过 /models 接口拉可用模型。失败返回 []。"""

    async def stream_chat(self, request: LLMRequest) -> AsyncIterator[str]:  # type: ignore[override]
        """流式生成。子类按需 override（仅 OpenAI 兼容实现支持）。"""
        raise NotImplementedError(
            f"Provider {self.provider_key} 不支持流式生成"
        )
        # 让类型检查器把 generator 视为 AsyncIterator[str]
        yield ""  # pragma: no cover


# ---------------------------------------------------------------- 注册表

_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {}


def register_provider(cls: type[LLMProvider]) -> type[LLMProvider]:
    """装饰器：把 Provider 子类注册到全局表。禁止 if/elif 分发。"""
    if not cls.provider_key:
        raise ValueError(f"{cls.__name__}.provider_key is empty")
    if cls.provider_key in _PROVIDER_REGISTRY:
        raise ValueError(f"Provider key '{cls.provider_key}' already registered")
    _PROVIDER_REGISTRY[cls.provider_key] = cls
    return cls


def get_provider_class(provider_key: str) -> type[LLMProvider]:
    if provider_key not in _PROVIDER_REGISTRY:
        raise KeyError(f"Provider '{provider_key}' not registered")
    return _PROVIDER_REGISTRY[provider_key]


def list_registered_providers() -> AsyncIterator[tuple[str, type[LLMProvider]]]:
    for k, v in _PROVIDER_REGISTRY.items():
        yield k, v

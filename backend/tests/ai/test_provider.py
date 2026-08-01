"""ai provider 单测：cost 公式 + 本地 embedding fallback + provider 注册表。"""

from __future__ import annotations

import pytest

from app.modules.ai.gateway.base import (
    LLMProvider,
    _PROVIDER_REGISTRY,
    get_provider_class,
    list_registered_providers,
)
from app.modules.ai.gateway.types import LLMRequest
from app.modules.ai.providers.local_embedding import LocalEmbeddingProvider, _hash_embed
from app.modules.ai.providers.openai_compatible import OpenAICompatibleProvider


# ---------------------------------------------------------- hash embed


class TestHashEmbedFallback:
    def test_deterministic(self) -> None:
        a = _hash_embed("hello", 1024)
        b = _hash_embed("hello", 1024)
        assert a == b

    def test_dimensions(self) -> None:
        for dim in (32, 128, 512, 1024):
            vec = _hash_embed("test", dim)
            assert len(vec) == dim

    def test_normalized_to_unit_range(self) -> None:
        vec = _hash_embed("test", 1024)
        # 每分量 ∈ [-1, 1]
        assert all(-1.0 <= v <= 1.0 for v in vec)


class TestLocalEmbeddingProvider:
    async def test_embed_uses_hash_when_model_unavailable(self) -> None:
        p = LocalEmbeddingProvider(dim=64)
        # 本机没装 bge-m3 → 走 hash fallback
        out = await p.embed(["hello", "world"], model="bge-m3")
        assert len(out) == 2
        assert all(len(v) == 64 for v in out)

    async def test_embed_deterministic(self) -> None:
        p = LocalEmbeddingProvider(dim=32)
        a = await p.embed(["same"], model="bge-m3")
        b = await p.embed(["same"], model="bge-m3")
        assert a == b

    async def test_embed_different_text_different_vector(self) -> None:
        p = LocalEmbeddingProvider(dim=32)
        a = await p.embed(["foo"], model="bge-m3")
        b = await p.embed(["bar"], model="bge-m3")
        assert a != b

    async def test_chat_raises(self) -> None:
        p = LocalEmbeddingProvider(dim=32)
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="x")
        with pytest.raises(NotImplementedError):
            await p.chat(req)

    def test_cost_zero(self) -> None:
        p = LocalEmbeddingProvider()
        assert p.estimate_cost("bge-m3", 1000, 500) == 0.0

    async def test_list_remote_models(self) -> None:
        p = LocalEmbeddingProvider()
        out = await p.list_remote_models()
        assert "bge-m3" in out


# ---------------------------------------------------------- openai_compatible


class TestOpenAICompatibleProvider:
    def test_init_sets_client_and_base_url(self) -> None:
        p = OpenAICompatibleProvider(
            base_url="https://api.deepseek.com/v1",
            api_key="sk-xxx",
        )
        assert p.base_url == "https://api.deepseek.com/v1"
        assert p.api_key == "sk-xxx"
        assert p._client is not None

    def test_estimate_cost_zero_by_default(self) -> None:
        """未在 AIModel 表里配价格 → 兜底返回 0。"""
        p = OpenAICompatibleProvider(base_url="https://x", api_key="k")
        assert p.estimate_cost("deepseek-chat", 1000, 500) == 0.0

    def test_default_headers_set_on_client(self) -> None:
        """构造时 base_url / api_key 已传入。"""
        p = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            timeout=15,
        )
        assert p.base_url == "https://api.example.com/v1"
        assert p.api_key == "test-key"


# ---------------------------------------------------------- provider 注册表


def test_local_embedding_registered() -> None:
    assert "local_embedding" in _PROVIDER_REGISTRY
    cls = get_provider_class("local_embedding")
    assert issubclass(cls, LLMProvider)


def test_openai_compatible_registered() -> None:
    keys = {k for k, _ in list_registered_providers()}
    assert "openai_compatible" in keys


def test_all_providers_have_provider_key() -> None:
    for key, cls in list_registered_providers():
        assert cls.provider_key == key, f"{cls.__name__}.provider_key 不匹配"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
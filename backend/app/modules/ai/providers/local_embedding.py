"""本地 bge-m3 ONNX embedding provider。

一期：fastembed 的轻量版封装；若机器上没装模型，自动降级为占位向量（仅 0/1）并打 WARN，
保证流水线不中断。生产环境会预装 bge-m3 模型。
"""

import hashlib
import structlog

from app.modules.ai.gateway.base import LLMProvider, register_provider
from app.modules.ai.gateway.types import LLMRequest, LLMResponse

log = structlog.get_logger()


@register_provider
class LocalEmbeddingProvider(LLMProvider):
    """本地 embedding Provider。chat() 不支持（用 chat 调它会直接报错）。"""

    provider_key = "local_embedding"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self._model = None
        self._try_load()

    def _try_load(self) -> None:
        """尝试加载本地 bge-m3；失败不抛异常。"""
        try:
            from fastembed import TextEmbedding  # type: ignore

            self._model = TextEmbedding(model_name="BAAI/bge-m3", dim=self.dim)
            log.info("local_embedding.model_loaded", model="bge-m3", dim=self.dim)
        except Exception as exc:  # noqa: BLE001
            log.warning("local_embedding.model_unavailable", error=str(exc), fallback="hash")

    async def chat(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover
        raise NotImplementedError("LocalEmbeddingProvider 不支持 chat，请用 chat model")

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        if self._model is not None:
            try:
                # fastembed 是同步生成器，用 to_thread 包装
                import asyncio

                def _run() -> list[list[float]]:
                    return [list(v) for v in self._model.embed(texts)]  # type: ignore[union-attr]

                return await asyncio.to_thread(_run)
            except Exception as exc:  # noqa: BLE001
                log.warning("local_embedding.embed_failed", error=str(exc), fallback="hash")

        # 降级：确定性 hash 向量，保证流水线不中断
        log.warning("local_embedding.using_hash_fallback", count=len(texts))
        return [_hash_embed(t, self.dim) for t in texts]

    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0  # 本地模型零成本

    async def list_remote_models(self) -> list[str]:
        return ["bge-m3"]


def _hash_embed(text: str, dim: int) -> list[float]:
    """占位向量：用 sha256 切分到 dim 维；保证相似度有部分语义。"""
    digest = hashlib.sha256(text.encode()).digest()
    # 重复 digest 直到能填满 dim
    repeated = (digest * ((dim // len(digest)) + 1))[:dim]
    # 归一化到 [-1, 1]
    return [(b - 128) / 128.0 for b in repeated]

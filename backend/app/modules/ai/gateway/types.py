"""LLM 抽象类型。

业务模块通过 LLMGateway.call() 调模型，永远不直接 import 各 Provider SDK。
"""

from typing import Any

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    """LLM 调用请求。"""

    messages: list[dict[str, str]]
    model: str  # 真实模型名（不是 alias）
    temperature: float = 0.3
    max_tokens: int | None = None
    response_schema: type[BaseModel] | None = None
    timeout: int = 120
    extra: dict[str, Any] = Field(default_factory=dict)
    supports_json_schema: bool = True  # 模型是否原生支持结构化输出（OpenAI-style json_schema）


class LLMResponse(BaseModel):
    """LLM 调用响应。"""

    content: str
    parsed: BaseModel | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = "stop"
    raw: Any = None  # 原始响应，调试用

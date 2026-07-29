"""ai-engine 模块枚举。

全局约定：枚举用大写下划线字符串存储，不用数字。
"""

from enum import StrEnum


class ProviderKey(StrEnum):
    """Provider 实现类注册键。"""

    OPENAI_COMPATIBLE = "openai_compatible"  # OpenAI / DeepSeek / Qwen / Kimi / 本地 vLLM
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    LOCAL_EMBEDDING = "local_embedding"  # 本地 bge-m3 ONNX，仅 embed


class ModelType(StrEnum):
    CHAT = "CHAT"
    EMBEDDING = "EMBEDDING"


class TaskKey(StrEnum):
    """Prompt 模板任务标识。"""

    EVENT_ANALYSIS = "event_analysis"
    EMBEDDING = "embedding"
    ASSISTANT_QA = "assistant_qa"
    CREATION_WECHAT = "creation_wechat"
    CREATION_BLOG = "creation_blog"
    CREATION_WEIBO = "creation_weibo"
    CREATION_XHS = "creation_xhs"
    CREATION_ZHIHU = "creation_zhihu"
    CREATION_MARKDOWN = "creation_markdown"
    REPORT_DAILY = "report_daily"


class CallStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    FALLBACK = "FALLBACK"  # 主模型失败后备用模型成功


class EventAnalysisStatus(StrEnum):
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    DONE = "DONE"
    FAILED = "FAILED"

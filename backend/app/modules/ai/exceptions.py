"""ai-engine 模块业务异常。"""

from app.core.exceptions import AppException


class ProviderNotFoundError(AppException):
    status_code = 404
    error_code = "PROVIDER_NOT_FOUND"
    detail = "Provider 不存在"


class ProviderNameExistsError(AppException):
    status_code = 409
    error_code = "PROVIDER_NAME_EXISTS"
    detail = "Provider 名称已被使用"


class ProviderInUseError(AppException):
    status_code = 409
    error_code = "PROVIDER_IN_USE"
    detail = "该 Provider 下还有启用的模型，无法删除"


class ProviderNotRegisteredError(AppException):
    status_code = 400
    error_code = "PROVIDER_NOT_REGISTERED"
    detail = "未注册的 provider_key"


class ModelNotFoundError(AppException):
    status_code = 404
    error_code = "MODEL_NOT_FOUND"
    detail = "模型不存在"


class ModelAliasExistsError(AppException):
    status_code = 409
    error_code = "MODEL_ALIAS_EXISTS"
    detail = "模型别名已被使用"


class EmbeddingDimRequiredError(AppException):
    status_code = 400
    error_code = "EMBEDDING_DIM_REQUIRED"
    detail = "EMBEDDING 类型必须指定 embedding_dim"


class PromptNotFoundError(AppException):
    status_code = 404
    error_code = "PROMPT_NOT_FOUND"
    detail = "Prompt 模板不存在"


class PromptNotConfiguredError(AppException):
    status_code = 500
    error_code = "PROMPT_NOT_CONFIGURED"
    detail = "该任务类型未配置生效中的 Prompt 模板"


class PromptReadonlyError(AppException):
    status_code = 400
    error_code = "PROMPT_READONLY"
    detail = "已激活的 Prompt 版本不可编辑，只能创建新版本"


class LLMUnavailableError(AppException):
    """降级链全部失败。"""

    status_code = 503
    error_code = "LLM_UNAVAILABLE"
    detail = "所有模型均不可用，请稍后重试"


class LLMCallFailedError(AppException):
    status_code = 502
    error_code = "LLM_CALL_FAILED"
    detail = "LLM 调用失败"


class LLMOutputInvalidError(AppException):
    status_code = 502
    error_code = "LLM_OUTPUT_INVALID"
    detail = "LLM 输出无法解析为预期结构"


class AICostLimitExceededError(AppException):
    status_code = 429
    error_code = "AI_COST_LIMIT_EXCEEDED"
    detail = "已达 AI 成本上限"


class AIRateLimitError(AppException):
    status_code = 429
    error_code = "AI_RATE_LIMIT_EXCEEDED"
    detail = "AI 调用过于频繁，请稍后重试"

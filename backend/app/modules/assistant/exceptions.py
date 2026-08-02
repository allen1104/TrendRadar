"""assistant 模块业务异常。

全部继承 AppException，由 app/main.py 全局 handler 转 HTTP 响应。
状态码 / 错误码按 SPEC-assistant.md「错误情况」对齐。
"""

from __future__ import annotations

from app.core.exceptions import AppException


class ThreadNotFoundError(AppException):
    status_code = 404
    error_code = "THREAD_NOT_FOUND"
    detail = "会话不存在"


class MessageNotFoundError(AppException):
    status_code = 404
    error_code = "MESSAGE_NOT_FOUND"
    detail = "消息不存在"


class EventNotAnalyzedError(AppException):
    status_code = 409
    error_code = "EVENT_NOT_ANALYZED"
    detail = "事件尚未完成 AI 分析，暂不能提问"


class QuestionRequiredError(AppException):
    status_code = 400
    error_code = "QUESTION_REQUIRED"
    detail = "问题不能为空"


class QuestionTooLongError(AppException):
    status_code = 400
    error_code = "QUESTION_TOO_LONG"
    detail = "问题不能超过 1000 字"


class NotAssistantMessageError(AppException):
    status_code = 400
    error_code = "NOT_ASSISTANT_MESSAGE"
    detail = "只能对 AI 回复做重新生成"


class ThreadTurnLimitExceededError(AppException):
    status_code = 429
    error_code = "THREAD_TURN_LIMIT_EXCEEDED"
    detail = "单会话已达最大轮数，请新建会话继续"


class ThreadCostLimitExceededError(AppException):
    status_code = 429
    error_code = "THREAD_COST_LIMIT_EXCEEDED"
    detail = "本次会话已达成本上限，请新建会话"


class InvalidQuickQuestionKeyError(AppException):
    status_code = 400
    error_code = "INVALID_QUICK_QUESTION_KEY"
    detail = "快捷问题 key 无效"
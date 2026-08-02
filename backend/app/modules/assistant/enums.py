"""assistant 模块枚举（按 SPEC-assistant.md）。"""

from __future__ import annotations

from enum import StrEnum


class MessageRole(StrEnum):
    """assistant_message.role。"""

    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageStatus(StrEnum):
    """assistant_message.status。"""

    PENDING = "PENDING"
    STREAMING = "STREAMING"
    DONE = "DONE"
    FAILED = "FAILED"


class Feedback(StrEnum):
    """用户对 ASSISTANT 消息的反馈。"""

    LIKE = "LIKE"
    DISLIKE = "DISLIKE"
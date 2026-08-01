"""collection 模块枚举。"""

from __future__ import annotations

from enum import StrEnum


class ReadStatus(StrEnum):
    """条目阅读状态。"""

    UNREAD = "UNREAD"
    LATER = "LATER"
    READ = "READ"
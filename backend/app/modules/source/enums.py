"""source 模块枚举。"""

from enum import StrEnum


class Region(StrEnum):
    GLOBAL = "GLOBAL"
    CN = "CN"


class SourceCategory(StrEnum):
    NEWS = "NEWS"
    CODE = "CODE"
    PAPER = "PAPER"
    PRODUCT = "PRODUCT"
    BLOG = "BLOG"
    MODEL = "MODEL"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class TriggerType(StrEnum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"

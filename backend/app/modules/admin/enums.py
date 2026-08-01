"""admin 模块枚举。

全局约定：枚举用大写下划线字符串存储，不用数字。
"""

from __future__ import annotations

from enum import StrEnum


class ConfigGroup(StrEnum):
    """system_config 分组。"""

    DEDUPE = "DEDUPE"
    RANK = "RANK"
    AI = "AI"
    SCHEDULE = "SCHEDULE"
    SEARCH = "SEARCH"
    GENERAL = "GENERAL"


class ValueType(StrEnum):
    """system_config 值类型，决定前端控件渲染。"""

    INT = "INT"
    FLOAT = "FLOAT"
    BOOL = "BOOL"
    STRING = "STRING"
    JSON = "JSON"


class TriggerType(StrEnum):
    """task_run_log 触发方式。"""

    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    CHAINED = "CHAINED"


class TaskRunStatus(StrEnum):
    """task_run_log 状态机。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    SKIPPED = "SKIPPED"


class TargetType(StrEnum):
    """audit_log 操作对象类型。"""

    EVENT = "EVENT"
    SOURCE = "SOURCE"
    USER = "USER"
    PROMPT = "PROMPT"
    MODEL = "MODEL"
    PROVIDER = "PROVIDER"
    CONFIG = "CONFIG"
    SYSTEM = "SYSTEM"


class AuditAction(StrEnum):
    """所有需要审计的动作（与 SPEC-admin.md 对齐）。"""

    # 事件
    EVENT_PIN = "EVENT_PIN"
    EVENT_HIDE = "EVENT_HIDE"
    EVENT_EDIT = "EVENT_EDIT"
    EVENT_SPLIT = "EVENT_SPLIT"
    EVENT_MERGE = "EVENT_MERGE"
    EVENT_REANALYZE = "EVENT_REANALYZE"

    # 采集源
    SOURCE_CREATE = "SOURCE_CREATE"
    SOURCE_UPDATE = "SOURCE_UPDATE"
    SOURCE_DELETE = "SOURCE_DELETE"
    SOURCE_MANUAL_RUN = "SOURCE_MANUAL_RUN"
    SOURCE_AUTO_DISABLED = "SOURCE_AUTO_DISABLED"

    # AI
    PROVIDER_CREATE = "PROVIDER_CREATE"
    PROVIDER_UPDATE = "PROVIDER_UPDATE"
    PROVIDER_DELETE = "PROVIDER_DELETE"
    MODEL_CREATE = "MODEL_CREATE"
    MODEL_UPDATE = "MODEL_UPDATE"
    MODEL_DELETE = "MODEL_DELETE"
    PROMPT_CREATE = "PROMPT_CREATE"
    PROMPT_ACTIVATE = "PROMPT_ACTIVATE"

    # 用户
    USER_ROLE_CHANGE = "USER_ROLE_CHANGE"
    USER_STATUS_CHANGE = "USER_STATUS_CHANGE"

    # 配置
    CONFIG_UPDATE = "CONFIG_UPDATE"

    # 系统告警
    SYSTEM_ALERT = "SYSTEM_ALERT"
    AI_DAILY_LIMIT_REACHED = "AI_DAILY_LIMIT_REACHED"
    SYSTEM_TASK_PAUSED = "SYSTEM_TASK_PAUSED"


class AlertLevel(StrEnum):
    """告警等级。"""

    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
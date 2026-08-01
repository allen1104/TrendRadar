"""admin 模块枚举不变量测试。"""

from __future__ import annotations

from app.modules.admin.enums import (
    AlertLevel,
    AuditAction,
    ConfigGroup,
    TargetType,
    TaskRunStatus,
    TriggerType,
    ValueType,
)


class TestConfigGroup:
    def test_exact_six(self) -> None:
        assert {g.value for g in ConfigGroup} == {"DEDUPE", "RANK", "AI", "SCHEDULE", "SEARCH", "GENERAL"}


class TestValueType:
    def test_set(self) -> None:
        assert {v.value for v in ValueType} == {"INT", "FLOAT", "BOOL", "STRING", "JSON"}


class TestTaskRunStatus:
    def test_set(self) -> None:
        assert {s.value for s in TaskRunStatus} == {
            "PENDING", "RUNNING", "SUCCESS", "FAILED", "RETRYING", "SKIPPED",
        }


class TestTriggerType:
    def test_set(self) -> None:
        assert {t.value for t in TriggerType} == {"SCHEDULED", "MANUAL", "CHAINED"}


class TestTargetType:
    def test_set(self) -> None:
        assert {t.value for t in TargetType} == {
            "EVENT", "SOURCE", "USER", "PROMPT", "MODEL", "PROVIDER", "CONFIG", "SYSTEM",
            "COLLECTION_FOLDER", "COLLECTION_ITEM",
        }


class TestAuditAction:
    def test_includes_required_24_actions(self) -> None:
        # SPEC 列了 25+ 动作；至少这些必须存在
        required = {
            "EVENT_PIN", "EVENT_HIDE", "EVENT_EDIT", "EVENT_SPLIT", "EVENT_MERGE", "EVENT_REANALYZE",
            "SOURCE_CREATE", "SOURCE_UPDATE", "SOURCE_DELETE", "SOURCE_MANUAL_RUN", "SOURCE_AUTO_DISABLED",
            "PROVIDER_CREATE", "PROVIDER_UPDATE", "PROVIDER_DELETE",
            "MODEL_CREATE", "MODEL_UPDATE", "MODEL_DELETE",
            "PROMPT_CREATE", "PROMPT_ACTIVATE",
            "USER_ROLE_CHANGE", "USER_STATUS_CHANGE",
            "CONFIG_UPDATE",
            "SYSTEM_ALERT", "AI_DAILY_LIMIT_REACHED", "SYSTEM_TASK_PAUSED",
        }
        actual = {a.value for a in AuditAction}
        assert required <= actual, f"缺失动作: {required - actual}"


class TestAlertLevel:
    def test_set(self) -> None:
        assert {l.value for l in AlertLevel} == {"INFO", "WARN", "ERROR"}
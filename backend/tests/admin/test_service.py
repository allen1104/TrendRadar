"""admin service 业务逻辑测试：校验 + 脱敏 + 元数据注册。"""

from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AppException
from app.modules.admin.decorator import (
    TASK_REGISTRY,
    get_task_metadata,
    tracked_task,
)
from app.modules.admin.enums import (
    AuditAction,
    TargetType,
    ValueType,
)
from app.modules.admin.exceptions import (
    ConfigNotFoundError,
    ConfigReadOnlyError,
    ConfigTypeMismatchError,
    ConfigValueOutOfRangeError,
    RankWeightsSumInvalidError,
)
from app.modules.admin.model import SystemConfig
from app.modules.admin.service import (
    _coerce_and_check_type,
    _redact_sensitive,
    AuditService,
    ConfigService,
)


# ----------------------------------------------------------- 脱敏


class TestRedactSensitive:
    def test_api_key_in_dict(self) -> None:
        out = _redact_sensitive({"api_key": "sk-xxx", "name": "OpenAI"})
        assert out == {"api_key": "***", "name": "OpenAI"}

    def test_case_insensitive_key_match(self) -> None:
        assert _redact_sensitive({"APIKey": "k"})["APIKey"] == "***"
        assert _redact_sensitive({"PASSWORD": "p"})["PASSWORD"] == "***"
        assert _redact_sensitive({"Access_Token": "t"})["Access_Token"] == "***"

    def test_nested_dict(self) -> None:
        out = _redact_sensitive({"extra": {"token": "abc", "x": 1}})
        assert out == {"extra": {"token": "***", "x": 1}}

    def test_nested_list(self) -> None:
        out = _redact_sensitive([{"apiKey": "k1"}, {"name": "ok"}])
        assert out == [{"apiKey": "***"}, {"name": "ok"}]

    def test_non_sensitive_unchanged(self) -> None:
        data = {"name": "OpenAI", "weight": 9, "tags": ["ai", "ml"]}
        assert _redact_sensitive(data) == data


# ----------------------------------------------------------- 类型校验


def _row(**kw) -> SystemConfig:
    defaults = dict(
        id=1,
        config_key="x",
        config_value=0,
        value_type=ValueType.INT.value,
        group_name="GENERAL",
        display_name="X",
        description=None,
        min_value=None,
        max_value=None,
        is_editable=True,
        requires_rerun=False,
        is_deleted=False,
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    defaults.update(kw)
    return SystemConfig(**defaults)


class TestCoerceAndCheckType:
    def test_int_in_range(self) -> None:
        row = _row(value_type=ValueType.INT.value, min_value=1, max_value=10)
        assert _coerce_and_check_type(row, 5) == 5

    def test_int_below_min_raises(self) -> None:
        row = _row(value_type=ValueType.INT.value, min_value=1, max_value=10)
        with pytest.raises(ConfigValueOutOfRangeError):
            _coerce_and_check_type(row, 0)

    def test_int_above_max_raises(self) -> None:
        row = _row(value_type=ValueType.INT.value, min_value=1, max_value=10)
        with pytest.raises(ConfigValueOutOfRangeError):
            _coerce_and_check_type(row, 11)

    def test_int_string_mismatch_raises(self) -> None:
        row = _row(value_type=ValueType.INT.value)
        with pytest.raises(ConfigTypeMismatchError):
            _coerce_and_check_type(row, "abc")

    def test_float_string_coerced(self) -> None:
        row = _row(value_type=ValueType.FLOAT.value)
        assert _coerce_and_check_type(row, "3.14") == 3.14

    def test_bool_must_be_bool(self) -> None:
        row = _row(value_type=ValueType.BOOL.value)
        with pytest.raises(ConfigTypeMismatchError):
            _coerce_and_check_type(row, 1)

    def test_string_must_be_string(self) -> None:
        row = _row(value_type=ValueType.STRING.value)
        with pytest.raises(ConfigTypeMismatchError):
            _coerce_and_check_type(row, 123)

    def test_json_must_be_dict_or_list(self) -> None:
        row = _row(value_type=ValueType.JSON.value)
        assert _coerce_and_check_type(row, {"k": 1}) == {"k": 1}
        with pytest.raises(ConfigTypeMismatchError):
            _coerce_and_check_type(row, "raw")


# ----------------------------------------------------------- rank_weights


class TestRankWeightsValidation:
    @pytest.mark.asyncio
    async def test_sum_must_equal_one(self) -> None:
        """rank_weights 四项和不等于 1 → RankWeightsSumInvalidError。"""
        session = AsyncMock()
        svc = ConfigService(session)
        svc.repo.get_by_key = AsyncMock(
            return_value=_row(config_key="rank_weights", value_type=ValueType.JSON.value)
        )

        with pytest.raises(RankWeightsSumInvalidError):
            await svc.update(
                "rank_weights",
                type("P", (), {"config_value": {"heat": 0.4, "value": 0.3, "originality": 0.2, "trend": 0.05}})(),
            )

    @pytest.mark.asyncio
    async def test_sum_one_passes(self) -> None:
        session = AsyncMock()
        svc = ConfigService(session)
        row = _row(config_key="rank_weights", value_type=ValueType.JSON.value)
        svc.repo.get_by_key = AsyncMock(return_value=row)
        svc.repo.update_value = AsyncMock(return_value=row)
        # session.commit() 是 AsyncMock，不需要 stub
        # redis_client / publish 是 mocked via patch

        with patch("app.modules.admin.service.redis_client", MagicMock()):
            with patch("app.modules.admin.service.redis_client.publish", AsyncMock()):
                with patch("app.modules.admin.service.redis_client.delete", AsyncMock()):
                    await svc.update(
                        "rank_weights",
                        type("P", (), {"config_value": {"heat": 0.35, "value": 0.30, "originality": 0.20, "trend": 0.15}})(),
                    )
        # 未抛异常即通过


# ----------------------------------------------------------- ConfigService.update


class TestConfigServiceUpdate:
    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        svc = ConfigService(session)
        svc.repo.get_by_key = AsyncMock(return_value=None)
        with pytest.raises(ConfigNotFoundError):
            await svc.update(
                "missing",
                type("P", (), {"config_value": 1})(),
            )

    @pytest.mark.asyncio
    async def test_not_editable_raises(self) -> None:
        session = AsyncMock()
        svc = ConfigService(session)
        svc.repo.get_by_key = AsyncMock(return_value=_row(is_editable=False))
        with pytest.raises(ConfigReadOnlyError):
            await svc.update(
                "x",
                type("P", (), {"config_value": 1})(),
            )


# ----------------------------------------------------------- AuditService.record 隔离


class TestAuditServiceIsolation:
    @pytest.mark.asyncio
    async def test_write_failure_does_not_propagate(self) -> None:
        """AuditService 写 audit_log 失败时 → 不抛异常（避免污染业务）。"""
        session = AsyncMock()
        session.add = MagicMock(side_effect=RuntimeError("db dead"))
        session.commit = AsyncMock(side_effect=RuntimeError("db dead"))
        session.rollback = AsyncMock()
        svc = AuditService(session)
        # 不应抛
        await svc.record(
            action=AuditAction.EVENT_PIN,
            target_type=TargetType.EVENT,
            target_id=1,
        )


# ----------------------------------------------------------- tracked_task 注册表


class TestTrackedTaskRegistry:
    def test_decorator_registers_metadata(self) -> None:
        @tracked_task(manual_triggerable=True, display_name="测试任务 X")
        def fake_task(self):
            return {"ok": 1}

        meta = get_task_metadata("fake_task")
        assert meta["display_name"] == "测试任务 X"
        assert meta["manual_triggerable"] is True

    def test_metadata_default_for_unknown(self) -> None:
        meta = get_task_metadata("does.not.exist")
        assert meta["manual_triggerable"] is True
        assert meta["display_name"] == "does.not.exist"


# ----------------------------------------------------------- 元数据冲突 / 边界


class TestAppExceptionBase:
    def test_inherits_app_exception(self) -> None:
        # 所有自定义异常都应继承 AppException
        for cls in [ConfigNotFoundError, ConfigReadOnlyError, ConfigTypeMismatchError,
                    ConfigValueOutOfRangeError, RankWeightsSumInvalidError]:
            assert issubclass(cls, AppException), cls.__name__


# 兜底，避免未用 import 警告
_ = AppException
_ = TASK_REGISTRY
"""角色包含关系与密码强度策略。"""

import pytest
from app.modules.auth.enums import ASSIGNABLE_ROLES, Role, has_role, role_level
from app.modules.auth.exceptions import WeakPasswordError
from app.modules.auth.service import validate_password_strength


class TestRoleHierarchy:
    def test_levels_are_strictly_increasing(self) -> None:
        assert (
            role_level(Role.GUEST)
            < role_level(Role.USER)
            < role_level(Role.EDITOR)
            < role_level(Role.ADMIN)
        )

    @pytest.mark.parametrize(
        ("actual", "required", "expected"),
        [
            (Role.ADMIN, Role.ADMIN, True),
            (Role.ADMIN, Role.EDITOR, True),
            (Role.ADMIN, Role.USER, True),
            (Role.EDITOR, Role.ADMIN, False),
            (Role.EDITOR, Role.EDITOR, True),
            (Role.EDITOR, Role.USER, True),
            (Role.USER, Role.EDITOR, False),
            (Role.USER, Role.USER, True),
            (Role.GUEST, Role.USER, False),
            (Role.GUEST, Role.GUEST, True),
        ],
    )
    def test_has_role(self, actual: Role, required: Role, expected: bool) -> None:
        assert has_role(actual, required) is expected

    def test_accepts_plain_strings(self) -> None:
        assert has_role("ADMIN", "EDITOR") is True
        assert has_role("USER", "ADMIN") is False

    def test_guest_is_not_assignable(self) -> None:
        assert Role.GUEST not in ASSIGNABLE_ROLES
        assert set(ASSIGNABLE_ROLES) == {Role.USER, Role.EDITOR, Role.ADMIN}


class TestPasswordPolicy:
    @pytest.mark.parametrize(
        "password",
        ["Pass1234", "aB3defgh", "Str0ngPassword!", "12345678aA"],
    )
    def test_accepts_valid(self, password: str) -> None:
        validate_password_strength(password)  # 不抛异常即通过

    @pytest.mark.parametrize(
        ("password", "reason"),
        [
            ("Pass123", "少于 8 位"),
            ("password1", "没有大写字母"),
            ("PASSWORD1", "没有小写字母"),
            ("PasswordAbc", "没有数字"),
            ("", "空密码"),
            ("        ", "全空格"),
        ],
    )
    def test_rejects_invalid(self, password: str, reason: str) -> None:
        with pytest.raises(WeakPasswordError):
            validate_password_strength(password)

"""密码哈希、JWT、敏感字段加解密的单元测试。不连数据库。"""

import time

import jwt
import pytest
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    mask_secret,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_argon2id_and_not_plaintext(self) -> None:
        hashed = hash_password("Pass1234")
        assert hashed.startswith("$argon2id$")
        assert "Pass1234" not in hashed

    def test_hash_is_salted(self) -> None:
        assert hash_password("Pass1234") != hash_password("Pass1234")

    def test_verify_roundtrip(self) -> None:
        hashed = hash_password("Pass1234")
        assert verify_password("Pass1234", hashed) is True
        assert verify_password("pass1234", hashed) is False
        assert verify_password("", hashed) is False

    def test_verify_rejects_garbage_hash(self) -> None:
        # 不应抛异常，只返回 False
        assert verify_password("Pass1234", "not-a-hash") is False
        assert verify_password("Pass1234", "") is False


class TestAccessToken:
    def test_roundtrip(self) -> None:
        token, jti, expires_in = create_access_token(42, "EDITOR")
        payload = decode_token(token, "access")

        assert payload is not None
        assert payload.user_id == 42
        assert payload.role == "EDITOR"
        assert payload.jti == jti
        assert payload.type == "access"
        assert expires_in == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_jti_is_unique_per_token(self) -> None:
        _, jti1, _ = create_access_token(1, "USER")
        _, jti2, _ = create_access_token(1, "USER")
        assert jti1 != jti2

    def test_ttl_seconds_is_positive_and_bounded(self) -> None:
        token, _, expires_in = create_access_token(1, "USER")
        payload = decode_token(token, "access")
        assert payload is not None
        assert 0 < payload.ttl_seconds <= expires_in

    def test_rejects_tampered_signature(self) -> None:
        token, _, _ = create_access_token(1, "USER")
        assert decode_token(token + "x", "access") is None

    def test_rejects_wrong_secret(self) -> None:
        forged = jwt.encode(
            {"sub": "1", "jti": "x", "type": "access", "exp": int(time.time()) + 60},
            "wrong-secret",
            algorithm="HS256",
        )
        assert decode_token(forged, "access") is None

    def test_rejects_expired(self) -> None:
        expired = jwt.encode(
            {"sub": "1", "jti": "x", "type": "access", "exp": int(time.time()) - 10},
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        assert decode_token(expired, "access") is None


class TestRefreshToken:
    def test_roundtrip(self) -> None:
        token, jti, expires_in = create_refresh_token(7)
        payload = decode_token(token, "refresh")

        assert payload is not None
        assert payload.user_id == 7
        assert payload.jti == jti
        assert expires_in == settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    def test_access_token_is_not_accepted_as_refresh(self) -> None:
        """两种 Token 用不同密钥且带 type 字段，必须互不通用。"""
        access, _, _ = create_access_token(1, "USER")
        assert decode_token(access, "refresh") is None

    def test_refresh_token_is_not_accepted_as_access(self) -> None:
        refresh, _, _ = create_refresh_token(1)
        assert decode_token(refresh, "access") is None

    def test_type_mismatch_is_rejected_even_with_right_secret(self) -> None:
        forged = jwt.encode(
            {"sub": "1", "jti": "x", "type": "refresh", "exp": int(time.time()) + 60},
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        assert decode_token(forged, "access") is None


class TestSecretEncryption:
    @pytest.mark.parametrize("plain", ["sk-abcdef123456", "短", "a" * 500])
    def test_roundtrip(self, plain: str) -> None:
        encrypted = encrypt_secret(plain)
        assert encrypted.startswith("enc:v1:")
        assert plain not in encrypted
        assert decrypt_secret(encrypted) == plain

    def test_nonce_makes_ciphertext_differ(self) -> None:
        assert encrypt_secret("sk-same") != encrypt_secret("sk-same")

    def test_empty_passthrough(self) -> None:
        assert encrypt_secret("") == ""
        assert decrypt_secret("") == ""

    def test_plaintext_passthrough_for_legacy_values(self) -> None:
        assert decrypt_secret("legacy-plain-value") == "legacy-plain-value"

    def test_mask(self) -> None:
        assert mask_secret("sk-1234567890abcd") == "sk-****abcd"
        assert mask_secret("short") == "****"
        assert mask_secret(None) is None
        assert mask_secret("") is None

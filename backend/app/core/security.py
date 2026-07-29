"""安全工具：密码哈希、JWT 签发与校验、敏感字段加解密。

约定（见 doc/SPEC-auth.md「业务规则」）：
- 密码 Argon2id，禁止 MD5/SHA
- accessToken 2 小时，refreshToken 14 天且单独密钥
- payload 含 jti，用于黑名单与旋转检测
"""

import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# ---------------------------------------------------------------- 密码

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def password_needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


# ---------------------------------------------------------------- JWT

TokenType = Literal["access", "refresh"]


class TokenPayload:
    """解码后的 Token 载荷。"""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.user_id: int = int(raw["sub"])
        self.jti: str = raw["jti"]
        self.type: str = raw["type"]
        self.role: str | None = raw.get("role")
        self.exp: int = raw["exp"]

    @property
    def expires_at(self) -> datetime:
        return datetime.fromtimestamp(self.exp, tz=UTC)

    @property
    def ttl_seconds(self) -> int:
        """距过期还剩多少秒（用于黑名单 TTL）。"""
        return max(0, int((self.expires_at - datetime.now(UTC)).total_seconds()))


def _encode(payload: dict[str, Any], secret: str) -> str:
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: int, role: str) -> tuple[str, str, int]:
    """返回 (token, jti, expires_in_seconds)。"""
    now = datetime.now(UTC)
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": jti,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    return _encode(payload, settings.SECRET_KEY), jti, expires_in


def create_refresh_token(user_id: int) -> tuple[str, str, int]:
    """返回 (token, jti, expires_in_seconds)。"""
    now = datetime.now(UTC)
    expires_in = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    return _encode(payload, settings.JWT_REFRESH_SECRET_KEY), jti, expires_in


def decode_token(token: str, token_type: TokenType) -> TokenPayload | None:
    """解码并校验 Token。签名错误 / 过期 / 类型不符一律返回 None。"""
    secret = (
        settings.SECRET_KEY
        if token_type == "access"  # noqa: S105 (string literal is a type discriminator, not a password)
        else settings.JWT_REFRESH_SECRET_KEY
    )
    try:
        raw = jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if raw.get("type") != token_type:
        return None
    if "sub" not in raw or "jti" not in raw or "exp" not in raw:
        return None
    return TokenPayload(raw)


# ---------------------------------------------------------------- 敏感字段加解密
#
# 用于 source.config.apiKey / ai_provider.api_key（见 doc/SPEC-source.md、SPEC-ai-engine.md）

_ENC_PREFIX = "enc:v1:"


def _aes_key() -> bytes:
    """从 SECRET_KEY 派生 32 字节 AES 密钥。"""
    return hashlib.sha256(settings.SECRET_KEY.encode()).digest()


def encrypt_secret(plain: str) -> str:
    """AES-GCM 加密，输出 `enc:v1:<base64(nonce||ciphertext)>`。"""
    if not plain:
        return plain
    nonce = os.urandom(12)
    ct = AESGCM(_aes_key()).encrypt(nonce, plain.encode(), None)
    return _ENC_PREFIX + base64.b64encode(nonce + ct).decode()


def decrypt_secret(stored: str) -> str:
    """解密。非本格式的值原样返回（兼容历史明文）。"""
    if not stored or not stored.startswith(_ENC_PREFIX):
        return stored
    blob = base64.b64decode(stored[len(_ENC_PREFIX) :])
    return AESGCM(_aes_key()).decrypt(blob[:12], blob[12:], None).decode()


def mask_secret(plain: str | None) -> str | None:
    """出参脱敏：保留前 3 后 4，中间 ****。"""
    if not plain:
        return None
    if len(plain) <= 8:
        return "****"
    return f"{plain[:3]}****{plain[-4:]}"

"""Token 黑名单、refresh 旋转与复用检测、登录失败锁定。

这些逻辑只依赖 Redis，不碰数据库，因此用 FakeRedis + session=None 直接测。
"""

import pytest
from app.core.exceptions import RateLimitError
from app.core.redis import RedisKey
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.modules.auth.exceptions import InvalidRefreshTokenError
from app.modules.auth.service import LOGIN_FAIL_LIMIT, AuthService

from tests.conftest import FakeRedis


def make_service(redis: FakeRedis) -> AuthService:
    # 这些用例只走 Redis 分支，不触碰 session
    return AuthService(session=None, redis=redis)  # type: ignore[arg-type]


class TestTokenBlacklist:
    async def test_logout_blacklists_access_token(self, fake_redis: FakeRedis) -> None:
        service = make_service(fake_redis)
        token, jti, _ = create_access_token(1, "USER")
        payload = decode_token(token, "access")
        assert payload is not None

        assert await service.is_token_blacklisted(jti) is False
        await service.logout(payload)
        assert await service.is_token_blacklisted(jti) is True

    async def test_blacklist_ttl_matches_token_remaining_life(
        self, fake_redis: FakeRedis
    ) -> None:
        service = make_service(fake_redis)
        token, jti, expires_in = create_access_token(1, "USER")
        payload = decode_token(token, "access")
        assert payload is not None

        await service.logout(payload)
        ttl = await fake_redis.ttl(RedisKey.token_blacklist(jti))
        # 不应设成永不过期，也不应超过 token 本身寿命
        assert 0 < ttl <= expires_in

    async def test_logout_revokes_all_refresh_tokens_of_user(
        self, fake_redis: FakeRedis
    ) -> None:
        service = make_service(fake_redis)
        # 该用户有 3 个有效 refresh token（多设备）
        for _ in range(3):
            _, jti, ttl = create_refresh_token(1)
            await fake_redis.setex(RedisKey.refresh_whitelist(1, jti), ttl, "1")
        # 另一个用户的不应被误删
        _, other_jti, other_ttl = create_refresh_token(2)
        await fake_redis.setex(RedisKey.refresh_whitelist(2, other_jti), other_ttl, "1")

        access, _, _ = create_access_token(1, "USER")
        payload = decode_token(access, "access")
        assert payload is not None
        await service.logout(payload)

        remaining = [k async for k in fake_redis.scan_iter(RedisKey.refresh_user_pattern(1))]
        assert remaining == []
        assert await fake_redis.exists(RedisKey.refresh_whitelist(2, other_jti)) == 1


class TestRefreshRotation:
    async def test_invalid_signature_is_rejected(self, fake_redis: FakeRedis) -> None:
        service = make_service(fake_redis)
        with pytest.raises(InvalidRefreshTokenError):
            await service.refresh("not-a-token")

    async def test_token_not_in_whitelist_triggers_reuse_revocation(
        self, fake_redis: FakeRedis
    ) -> None:
        """签名有效但不在白名单 → 判定泄露复用，作废该用户全部 refresh token。"""
        service = make_service(fake_redis)

        # 用户还有一个正常的 refresh token
        _, live_jti, ttl = create_refresh_token(9)
        await fake_redis.setex(RedisKey.refresh_whitelist(9, live_jti), ttl, "1")

        # 攻击者拿着一个已被消费过（不在白名单）的 token 来刷新
        stolen, _, _ = create_refresh_token(9)

        with pytest.raises(InvalidRefreshTokenError):
            await service.refresh(stolen)

        # 该用户所有 refresh token 都应被作废
        remaining = [k async for k in fake_redis.scan_iter(RedisKey.refresh_user_pattern(9))]
        assert remaining == []

    async def test_whitelist_entry_is_consumed_atomically(self, fake_redis: FakeRedis) -> None:
        """旋转语义：白名单项被 getdel 取走后立即失效，第二次用同一个必然失败。"""
        _, jti, ttl = create_refresh_token(5)
        key = RedisKey.refresh_whitelist(5, jti)
        await fake_redis.setex(key, ttl, "1")

        assert await fake_redis.getdel(key) == "1"
        assert await fake_redis.getdel(key) is None


class TestLoginFailureLock:
    async def test_lock_after_threshold(self, fake_redis: FakeRedis) -> None:
        service = make_service(fake_redis)
        email = "victim@example.com"

        # 未达阈值不锁
        for _ in range(LOGIN_FAIL_LIMIT - 1):
            await service._record_login_failure(email)
        await service._assert_not_locked(email)

        # 达到阈值即锁
        await service._record_login_failure(email)
        with pytest.raises(RateLimitError) as exc:
            await service._assert_not_locked(email)
        assert exc.value.error_code == "TOO_MANY_ATTEMPTS"
        assert exc.value.status_code == 429
        assert exc.value.extra["retryAfter"] >= 1

    async def test_successful_login_clears_counter(self, fake_redis: FakeRedis) -> None:
        service = make_service(fake_redis)
        email = "user@example.com"

        for _ in range(LOGIN_FAIL_LIMIT):
            await service._record_login_failure(email)
        await service._clear_login_failures(email)

        await service._assert_not_locked(email)  # 不抛异常

    async def test_counter_is_scoped_per_email(self, fake_redis: FakeRedis) -> None:
        service = make_service(fake_redis)
        for _ in range(LOGIN_FAIL_LIMIT):
            await service._record_login_failure("a@example.com")

        await service._assert_not_locked("b@example.com")

    async def test_email_is_case_insensitive(self, fake_redis: FakeRedis) -> None:
        service = make_service(fake_redis)
        for _ in range(LOGIN_FAIL_LIMIT):
            await service._record_login_failure("Mixed@Example.COM")

        with pytest.raises(RateLimitError):
            await service._assert_not_locked("mixed@example.com")

    async def test_failure_counter_has_expiry(self, fake_redis: FakeRedis) -> None:
        service = make_service(fake_redis)
        await service._record_login_failure("x@example.com")
        ttl = await fake_redis.ttl(RedisKey.login_fail("x@example.com"))
        assert ttl > 0  # 不能是永久锁定

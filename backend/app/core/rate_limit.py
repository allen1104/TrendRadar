"""基于 Redis 的固定窗口限流。"""

from fastapi import Request

from app.core.exceptions import RateLimitError
from app.core.redis import RedisKey, redis_client


async def check_rate_limit(scope: str, identity: str, *, limit: int, window: int) -> None:
    """固定窗口计数。超限抛 RateLimitError（429）。

    Args:
        scope: 限流场景，如 "login" / "register" / "ai_call"
        identity: 限流主体，如 IP 或 userId
        limit: 窗口内允许的次数
        window: 窗口长度（秒）
    """
    key = RedisKey.rate_limit(scope, identity)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window)
    if count > limit:
        ttl = await redis_client.ttl(key)
        raise RateLimitError(
            f"操作过于频繁，请 {max(ttl, 1)} 秒后重试",
            error_code="TOO_MANY_ATTEMPTS",
            extra={"retryAfter": max(ttl, 1)},
        )


def client_ip(request: Request) -> str:
    """取真实客户端 IP（考虑反向代理）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

"""Redis 客户端与通用键工具。"""

from redis.asyncio import Redis, from_url

from app.core.config import settings

redis_client: Redis = from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> Redis:
    """FastAPI 依赖。"""
    return redis_client


class RedisKey:
    """集中管理 Redis 键，避免散落在各处拼字符串。"""

    @staticmethod
    def token_blacklist(jti: str) -> str:
        return f"auth:blacklist:{jti}"

    @staticmethod
    def refresh_whitelist(user_id: int, jti: str) -> str:
        return f"auth:refresh:{user_id}:{jti}"

    @staticmethod
    def refresh_user_pattern(user_id: int) -> str:
        return f"auth:refresh:{user_id}:*"

    @staticmethod
    def login_fail(email: str) -> str:
        return f"auth:login_fail:{email.lower()}"

    @staticmethod
    def rate_limit(scope: str, identity: str) -> str:
        return f"ratelimit:{scope}:{identity}"
